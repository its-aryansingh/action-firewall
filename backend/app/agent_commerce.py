"""Agent Commerce Gateway API router — /agent-commerce/v1 facade.

Translates external AI buyer proposals into server-resolved catalog facts,
envelope activations, and deterministic Action Firewall authorizations.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any
from fastapi import APIRouter, Header, HTTPException, Query

from . import autopilot, catalog, store
from .authorization import canonical_json
from .approval_tokens import (
    ApprovalTokenAlreadyRedeemedError,
    ApprovalTokenConflictError,
    ApprovalTokenError,
    ApprovalTokenExpiredError,
    ApprovalTokenNotFoundError,
    lookup_approval_token,
    redeem_approval_token,
)
from .buyer_auth import (
    check_replay_or_mutation,
    mint_shopper_session,
    record_successful_request,
    verify_buyer_agent,
    verify_merchant_access,
    verify_shopper_session,
)
from .buyer_models import (
    AgentCommerceMetricsResponse,
    CatalogSearchResponseItem,
    CommerceAttemptRequest,
    CommerceAttemptResponse,
    CommerceAttemptStage,
    IntentCreateRequest,
    IntentCreateResponse,
    MerchantCapabilities,
    QuoteItemRequest,
    QuoteRequest,
    QuoteResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    BuyerPlanRequest,
    BuyerPlanResponse,
)
from .commerce_metrics import (
    AgentOrderSummary,
    get_agent_orders,
    get_comprehensive_metrics,
    record_agent_order,
)
from .config import get_settings
from .envelope import compute_quote_hash
from .mcp_client import unwrap
from .merchant import CATALOG_REVISION, DEFAULT_MERCHANT_ID, get_merchant_capabilities
from .openai_buyer import OpenAIBuyer
from .replay_buyer import ReplayBuyer
from .models import (
    AutopilotExecuteRequest,
    Cart,
    CartLine,
    EnvelopeActivateRequest,
    EnvelopeDraftRequest,
    MerchantQuote,
    PurchaseEnvelope,
)
from .rate_limit import enforce_rate_limit
from .receipts import build_receipt

router = APIRouter(tags=["agent-commerce"])


@router.get("/merchant", response_model=MerchantCapabilities)
def get_merchant() -> MerchantCapabilities:
    """Return public merchant identity, catalog revision, and supported capabilities."""
    return get_merchant_capabilities(DEFAULT_MERCHANT_ID)


@router.get("/catalog")
def get_agent_catalog(
    category: str | None = Query(default=None, description="Filter products by category"),
    limit: int = Query(default=50, ge=1, le=100, description="Max products to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
) -> dict[str, Any]:
    """Public read-only catalog projection for external AI buyers."""
    all_items = catalog.load_catalog()
    if category:
        all_items = [item for item in all_items if item.get("category", "").lower() == category.lower()]

    paged = all_items[offset : offset + limit]
    return {
        "merchant_id": DEFAULT_MERCHANT_ID,
        "catalog_revision": CATALOG_REVISION,
        "total_products": len(all_items),
        "count": len(paged),
        "offset": offset,
        "products": [
            {
                "sku": item["sku"],
                "name": item["name"],
                "category": item["category"],
                "price_paise": item["price_paise"],
                "currency": item.get("currency", "INR"),
                "unit": item.get("unit", "each"),
                "in_stock": item.get("stock", 1) > 0,
                "tags": item.get("tags", []),
            }
            for item in paged
        ],
    }


@router.get("/catalog/jsonld")
def get_catalog_jsonld() -> dict[str, Any]:
    """Public Schema.org JSON-LD ItemList representation of the catalog.

    Conforms to Schema.org Product specifications without cost or margin fields.
    """
    items = catalog.load_catalog()
    elements = []
    for item in items:
        in_stock = item.get("stock", 1) > 0
        price_in_rupees = f"{item['price_paise'] / 100:.2f}"
        product_node = {
            "@type": "Product",
            "sku": item["sku"],
            "name": item["name"],
            "category": item.get("category", "General"),
            "offers": {
                "@type": "Offer",
                "price": price_in_rupees,
                "priceCurrency": item.get("currency", "INR"),
                "availability": "https://schema.org/InStock" if in_stock else "https://schema.org/OutOfStock",
            },
        }
        if item.get("description"):
            product_node["description"] = item["description"]
        elements.append(product_node)

    return {
        "@context": "https://schema.org/",
        "@type": "ItemList",
        "name": "FreshBasket for Business Catalog",
        "numberOfItems": len(elements),
        "itemListElement": elements,
    }


@router.get("/catalog/search", response_model=list[CatalogSearchResponseItem])
def search_agent_catalog(
    q: str = Query(default="", description="Search query for catalog items"),
    limit: int = Query(default=6, ge=1, le=50, description="Max products to return"),
) -> list[CatalogSearchResponseItem]:
    """Return server-owned catalog candidates with price in integer paise.

    Descriptions and user queries are treated as untrusted text.
    """
    if q.strip():
        items = catalog.search(q, top_k=limit)
    else:
        items = catalog.load_catalog()[:limit]

    return [
        CatalogSearchResponseItem(
            sku=item["sku"],
            name=item["name"],
            category=item["category"],
            price_paise=item["price_paise"],
            in_stock=item.get("stock", 1) > 0,
            tags=item.get("tags", []),
            revision=CATALOG_REVISION,
        )
        for item in items
    ]


@router.post("/sessions", response_model=SessionCreateResponse)
def create_session(req: SessionCreateRequest | None = None) -> SessionCreateResponse:
    """Mint a signed, short-lived shopper session token."""
    uid = req.user_id if req else "user_demo"
    ttl = req.ttl_seconds if req else 3600
    sid_req = req.session_id if req else None
    sid, token = mint_shopper_session(user_id=uid, ttl_seconds=ttl, session_id=sid_req)
    return SessionCreateResponse(
        session_id=sid,
        token=token,
        user_id=uid,
        expires_at=time.time() + ttl,
    )


@router.post("/intents", response_model=IntentCreateResponse)
def create_intent(
    req: IntentCreateRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    session_token: str | None = Header(None, alias="X-Shopper-Session"),
) -> IntentCreateResponse:
    """Propose purchase intent and draft a Purchase Envelope for human activation.

    Proposal-only: Never calls a provider and never mints an Action Grant.
    """
    buyer_principal = verify_buyer_agent(authorization)
    shopper_principal = verify_shopper_session(session_token, expected_session_id=req.shopper_session_id)
    verify_merchant_access(req.merchant_id, buyer_principal)
    enforce_rate_limit(buyer_principal, shopper_principal.shopper_session_id)

    # Transport identity is authoritative; request body overrides are strictly rejected
    if req.buyer_agent_id and req.buyer_agent_id != buyer_principal.buyer_agent_id:
        raise HTTPException(
            status_code=403,
            detail=f"Identity mismatch: body-supplied buyer_agent_id '{req.buyer_agent_id}' does not match transport principal '{buyer_principal.buyer_agent_id}'. Body overrides are prohibited.",
        )

    cached = check_replay_or_mutation(
        agent_request_id=req.agent_request_id,
        merchant_id=req.merchant_id,
        buyer_agent_id=buyer_principal.buyer_agent_id,
        shopper_session_id=shopper_principal.shopper_session_id,
        body_data=req.model_dump(mode="json"),
    )
    if cached:
        return IntentCreateResponse(**cached)

    goal = req.voice_transcript.strip() if req.voice_transcript else req.natural_language_intent.strip()
    if not goal:
        raise HTTPException(422, "Goal intent cannot be empty")

    budget_paise = req.budget_paise or 60000  # Default ₹600.00
    max_rupees = max(1, budget_paise // 100)

    draft_req = EnvelopeDraftRequest(
        goal=goal,
        max_total_rupees=max_rupees,
        merchant_id=req.merchant_id,
    )
    try:
        draft = autopilot.create_draft(draft_req)
    except ValueError as exc:
        raise HTTPException(422, f"Intent could not be structured: {exc}") from exc

    intent_id = f"int_{uuid.uuid4().hex[:12]}"
    settings = get_settings()

    resp = IntentCreateResponse(
        intent_id=intent_id,
        agent_request_id=req.agent_request_id,
        buyer_agent_id=buyer_principal.buyer_agent_id,
        shopper_session_id=shopper_principal.shopper_session_id,
        natural_language_intent=req.natural_language_intent,
        normalized_intent={
            "goal": draft.goal,
            "budget_paise": draft.max_total_paise,
            "merchant_id": draft.merchant_id,
            "slots": [slot.label for slot in draft.slots],
        },
        missing_fields=[],
        draft_envelope=draft,
        evidence_mode=settings.envelope_drafting_mode,
        message="Draft Purchase Envelope prepared for shopper review. No payment authority active.",
        provider_action_called=False,
    )
    record_successful_request(
        agent_request_id=req.agent_request_id,
        merchant_id=req.merchant_id,
        buyer_agent_id=buyer_principal.buyer_agent_id,
        shopper_session_id=shopper_principal.shopper_session_id,
        body_data=req.model_dump(mode="json"),
        response_data=resp.model_dump(mode="json"),
    )
    return resp


@router.post("/envelopes/{envelope_id}/activate", response_model=PurchaseEnvelope)
def activate_envelope(
    envelope_id: str,
    body: EnvelopeActivateRequest,
    session_token: str | None = Header(None, alias="X-Shopper-Session"),
) -> PurchaseEnvelope:
    """Human-only activation binding the canonical envelope version and hash."""
    verify_shopper_session(session_token)
    try:
        return autopilot.activate(envelope_id, body)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/approvals/{token}")
def get_approval(token: str) -> dict[str, Any]:
    """Retrieve details for an opaque human approval token."""
    token_data = lookup_approval_token(token)
    if not token_data:
        raise HTTPException(404, "Unknown approval token")
    envelope = store.get_envelope(token_data["envelope_id"])
    return {
        "token": token,
        "envelope_id": token_data["envelope_id"],
        "envelope_hash": token_data["envelope_hash"],
        "expires_at": token_data["expires_at"],
        "redeemed_at": token_data["redeemed_at"],
        "expired": token_data["expires_at"] <= time.time(),
        "redeemed": token_data["redeemed_at"] is not None,
        "envelope": envelope,
    }


@router.post("/approvals/{token}/redeem", response_model=PurchaseEnvelope)
def redeem_approval(token: str) -> PurchaseEnvelope:
    """Atomically redeem an opaque approval token and activate the bound envelope."""
    try:
        return redeem_approval_token(token)
    except ApprovalTokenNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalTokenExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except (ApprovalTokenAlreadyRedeemedError, ApprovalTokenConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApprovalTokenError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/quotes", response_model=QuoteResponse)
def request_quote(
    req: QuoteRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    session_token: str | None = Header(None, alias="X-Shopper-Session"),
) -> QuoteResponse:
    """Compute an authoritative merchant quote from current server catalog facts.

    Discards any client-supplied prices, totals, or stock assertions.
    """
    buyer_principal = verify_buyer_agent(authorization)
    shopper_principal = verify_shopper_session(session_token)
    verify_merchant_access(req.merchant_id, buyer_principal)
    enforce_rate_limit(buyer_principal, shopper_principal.shopper_session_id)
    catalog_items = {item["sku"]: item for item in catalog.load_catalog()}
    lines: list[CartLine] = []

    for item_req in req.items:
        product = catalog_items.get(item_req.sku)
        if not product:
            raise HTTPException(422, f"Unknown SKU: {item_req.sku}")
        lines.append(
            CartLine(
                sku=product["sku"],
                name=product["name"],
                category=product["category"],
                unit_price_paise=product["price_paise"],
                qty=item_req.quantity,
            )
        )

    cart = Cart(lines=lines)
    quote = MerchantQuote(
        merchant_id=req.merchant_id,
        currency="INR",
        fulfillment_profile_id=req.fulfillment_profile_id,
        delivery_eta=time.time() + 2700,
        cart=cart,
        substitutions=[],
        quote_hash="",
    )
    quote = quote.model_copy(update={"quote_hash": compute_quote_hash(quote)})

    quote_id = f"q_{uuid.uuid4().hex[:12]}"
    valid_until = time.time() + 900
    canonical_cart_items = [
        {"sku": line.sku, "qty": line.qty, "price_paise": line.unit_price_paise}
        for line in cart.lines
    ]
    canonical_cart_json = canonical_json(canonical_cart_items)
    cart_hash = hashlib.sha256(canonical_cart_json.encode("utf-8")).hexdigest()

    store.save_commerce_quote(
        quote_id=quote_id,
        merchant_id=req.merchant_id,
        buyer_agent_id=buyer_principal.buyer_agent_id,
        shopper_session_id=shopper_principal.shopper_session_id,
        catalog_revision=CATALOG_REVISION,
        canonical_cart_json=canonical_cart_json,
        cart_hash=cart_hash,
        quote_hash=quote.quote_hash,
        total_paise=cart.total_paise,
        valid_until=valid_until,
    )

    return QuoteResponse(
        quote_id=quote_id,
        merchant_id=req.merchant_id,
        currency="INR",
        fulfillment_profile_id=req.fulfillment_profile_id,
        cart=cart,
        substitutions=[],
        total_paise=cart.total_paise,
        quote_hash=quote.quote_hash,
        valid_until=valid_until,
    )


@router.post("/attempts", response_model=CommerceAttemptResponse)
def submit_attempt(
    req: CommerceAttemptRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    session_token: str | None = Header(None, alias="X-Shopper-Session"),
) -> CommerceAttemptResponse:
    """Execute an agent purchase attempt through Action Firewall.

    Re-verifies envelope, quote, and inventory atomically before dispatch.
    """
    buyer_principal = verify_buyer_agent(authorization)
    shopper_principal = verify_shopper_session(session_token, expected_session_id=req.shopper_session_id)
    enforce_rate_limit(buyer_principal, shopper_principal.shopper_session_id)

    envelope = store.get_envelope(req.envelope_id)
    if not envelope:
        raise HTTPException(404, "Unknown Purchase Envelope")

    verify_merchant_access(envelope.merchant_id, buyer_principal)

    # Transport identity is authoritative; request body overrides are strictly rejected
    if req.buyer_agent_id and req.buyer_agent_id != buyer_principal.buyer_agent_id:
        raise HTTPException(
            status_code=403,
            detail=f"Identity mismatch: body-supplied buyer_agent_id '{req.buyer_agent_id}' does not match transport principal '{buyer_principal.buyer_agent_id}'. Body overrides are prohibited.",
        )

    cached = check_replay_or_mutation(
        agent_request_id=req.purchase_attempt_id,
        merchant_id=envelope.merchant_id,
        buyer_agent_id=buyer_principal.buyer_agent_id,
        shopper_session_id=shopper_principal.shopper_session_id,
        body_data=req.model_dump(mode="json"),
    )
    if cached:
        return CommerceAttemptResponse(**cached)

    # If unactivated, reject before provider transport
    if envelope.status.value != "active":
        stages = [
            CommerceAttemptStage(stage="understand", name="Draft Intent", status="completed", detail="Envelope created"),
            CommerceAttemptStage(stage="quote", name="Server Quote", status="completed", detail="Catalog verified"),
            CommerceAttemptStage(stage="authorize", name="Authority Gate", status="blocked", detail=f"Envelope is {envelope.status.value}"),
            CommerceAttemptStage(stage="razorpay_action", name="Razorpay Action", status="blocked", detail="Razorpay action not called"),
        ]
        return CommerceAttemptResponse(
            attempt_id=req.purchase_attempt_id,
            envelope_id=req.envelope_id,
            outcome="STOPPED_BEFORE_RAZORPAY",
            stages=stages,
            allowed=False,
            code=f"BLOCK_ENVELOPE_{envelope.status.value.upper()}",
            human_message=f"Purchase Envelope is {envelope.status.value}. Explicit human activation is required before checkout.",
            quote_total_paise=0,
            payment_link=None,
            grant_id=None,
            receipt=None,
            deltas=[],
            recovery_applied=False,
            provider_mode="simulated",
            razorpay_action_called=False,
        )

    if req.quote_id:
        persisted_quote = store.get_commerce_quote(req.quote_id)
        if not persisted_quote or persisted_quote["buyer_agent_id"] != buyer_principal.buyer_agent_id:
            raise HTTPException(404, f"Quote {req.quote_id} not found")
        if time.time() > persisted_quote["valid_until"]:
            raise HTTPException(409, "Quote has expired. Fresh quote required.")
        if persisted_quote["catalog_revision"] != CATALOG_REVISION:
            raise HTTPException(409, "Catalog revision changed. REQUOTE_REQUIRED.")
        if persisted_quote.get("checked_out_at") is not None:
            raise HTTPException(409, "Quote has already been checked out")
        if not store.mark_commerce_quote_checked_out(req.quote_id, req.purchase_attempt_id):
            raise HTTPException(409, "Quote has already been checked out")

    exp_version = req.expected_envelope_version if req.expected_envelope_version is not None else envelope.version
    exp_hash = req.expected_envelope_hash or envelope.envelope_hash

    session_id = req.shopper_session_id if len(req.shopper_session_id) >= 8 else f"session_{req.shopper_session_id}"
    exec_req = AutopilotExecuteRequest(
        envelope_id=req.envelope_id,
        expected_envelope_version=exp_version,
        expected_envelope_hash=exp_hash,
        session_id=session_id,
        purchase_attempt_id=req.purchase_attempt_id,
        scenario=req.scenario,
    )

    try:
        res = autopilot.execute(exec_req)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    # Stages breakdown
    auth_status = "completed" if res.envelope_decision.allowed else "blocked"
    action_status = (
        "completed" if res.action_status == "action_issued"
        else "unknown" if res.action_status == "unknown"
        else "blocked"
    )

    stages = [
        CommerceAttemptStage(
            stage="understand",
            name="Draft Intent",
            status="completed",
            detail="Intent translated to Purchase Envelope",
        ),
        CommerceAttemptStage(
            stage="quote",
            name="Server Quote",
            status="completed",
            detail=f"Quote rehydrated: {res.envelope_decision.quote_total_paise / 100:.2f} INR",
        ),
        CommerceAttemptStage(
            stage="authorize",
            name="Authority Gate",
            status=auth_status,
            detail=res.envelope_decision.code,
        ),
        CommerceAttemptStage(
            stage="razorpay_action",
            name="Razorpay Action",
            status=action_status,
            detail=f"Provider state: {res.action_status or 'none'}",
        ),
    ]

    # Human-readable outcome classification
    if res.action_status == "action_issued":
        outcome = "RECOVERED_INSIDE_ENVELOPE" if res.recovery_applied else "ACTION_ISSUED"
    elif res.action_status == "unknown":
        outcome = "UNKNOWN"
    elif not res.envelope_decision.allowed:
        outcome = "POLICY_DELTA_REQUIRED" if res.envelope_decision.deltas else "STOPPED_BEFORE_RAZORPAY"
    else:
        outcome = "READY_FOR_CHECKOUT"

    razorpay_called = bool(res.payment_link or res.action_status in ("action_issued", "unknown"))

    resp = CommerceAttemptResponse(
        attempt_id=req.purchase_attempt_id,
        envelope_id=req.envelope_id,
        outcome=outcome,
        stages=stages,
        allowed=res.envelope_decision.allowed,
        code=res.envelope_decision.code,
        human_message=res.envelope_decision.human_message,
        quote_total_paise=res.envelope_decision.quote_total_paise,
        payment_link=res.payment_link,
        grant_id=res.grant_id,
        receipt=res.receipt,
        deltas=res.envelope_decision.deltas,
        recovery_applied=res.recovery_applied,
        provider_mode=res.provider_mode,
        razorpay_action_called=razorpay_called,
    )
    order_status = (
        "issued" if res.action_status == "action_issued"
        else "unknown" if res.action_status == "unknown"
        else "blocked"
    )
    record_agent_order(
        purchase_attempt_id=req.purchase_attempt_id,
        merchant_id=envelope.merchant_id,
        buyer_agent_id=buyer_principal.buyer_agent_id,
        shopper_session_id=shopper_principal.shopper_session_id,
        status=order_status,
        outcome=outcome,
        amount_paise=res.envelope_decision.quote_total_paise,
        envelope_id=envelope.id,
        recovery_applied=res.recovery_applied,
        payment_link=res.payment_link,
        grant_id=res.grant_id,
        receipt_id=res.receipt.grant_id if res.receipt else None,
        code=res.envelope_decision.code,
    )
    record_successful_request(
        agent_request_id=req.purchase_attempt_id,
        merchant_id=envelope.merchant_id,
        buyer_agent_id=buyer_principal.buyer_agent_id,
        shopper_session_id=shopper_principal.shopper_session_id,
        body_data=req.model_dump(mode="json"),
        response_data=resp.model_dump(mode="json"),
    )
    return resp


@router.get("/attempts/{attempt_id}", response_model=CommerceAttemptResponse)
def get_attempt_detail(attempt_id: str) -> CommerceAttemptResponse:
    """Fetch stored attempt execution details and four-stage timeline."""
    grant = store.get_action_grant(attempt_id)
    if not grant:
        with store._conn() as cx:
            row = cx.execute(
                "SELECT * FROM spend_ledger WHERE purchase_attempt_id=? OR idempotency_key=? ORDER BY created_at DESC LIMIT 1",
                (attempt_id, attempt_id),
            ).fetchone()
            if row:
                grant = store._row_to_action_grant(row)

    if not grant:
        raise HTTPException(404, f"Attempt {attempt_id} not found")

    envelope = store.get_envelope(grant.envelope_id) if grant.envelope_id else None
    action_status = (
        "completed" if grant.state.value in ("action_issued", "settled")
        else "unknown" if grant.state.value == "unknown"
        else "blocked"
    )

    stages = [
        CommerceAttemptStage(stage="understand", name="Draft Intent", status="completed", detail="Intent bound to envelope"),
        CommerceAttemptStage(stage="quote", name="Server Quote", status="completed", detail=f"{grant.amount_paise / 100:.2f} INR"),
        CommerceAttemptStage(stage="authorize", name="Authority Gate", status="completed", detail="Grant minted"),
        CommerceAttemptStage(stage="razorpay_action", name="Razorpay Action", status=action_status, detail=f"State: {grant.state.value}"),
    ]

    receipt = build_receipt(grant)
    razorpay_called = grant.state.value in ("action_issued", "settled", "unknown")

    payload = unwrap(grant.result) if isinstance(grant.result, dict) else {}
    link = (
        payload.get("short_url") or payload.get("payment_link")
        if isinstance(payload, dict)
        else None
    )
    return CommerceAttemptResponse(
        attempt_id=grant.purchase_attempt_id,
        envelope_id=grant.envelope_id or "",
        outcome="ACTION_ISSUED" if grant.state.value in ("action_issued", "settled") else grant.state.value.upper(),
        stages=stages,
        allowed=True,
        code="ALLOW_ENVELOPE",
        human_message="Action grant recorded.",
        quote_total_paise=grant.amount_paise,
        payment_link=link,
        grant_id=grant.id,
        receipt=receipt,
        deltas=[],
        recovery_applied=False,
        provider_mode="simulated",
        razorpay_action_called=razorpay_called,
    )


@router.get("/orders", response_model=list[AgentOrderSummary])
def list_orders(
    status: str | None = None,
    limit: int = 50,
) -> list[AgentOrderSummary]:
    """Return recent agent orders with optional status filter."""
    return get_agent_orders(merchant_id=DEFAULT_MERCHANT_ID, limit=limit, status_filter=status)


@router.get("/metrics", response_model=AgentCommerceMetricsResponse)
def get_commerce_metrics() -> AgentCommerceMetricsResponse:
    """Return merchant operations dashboard KPIs with explicit evidence modes."""
    m = get_comprehensive_metrics(DEFAULT_MERCHANT_ID)
    return AgentCommerceMetricsResponse(
        agent_gmv_issued_paise=m.agent_gmv_issued_paise,
        settled_agent_gmv_paise=m.settled_agent_gmv_paise,
        agent_orders_count=m.agent_orders_count,
        orders_recovered_count=m.orders_recovered_count,
        unsafe_attempts_blocked_count=m.unsafe_attempts_blocked_count,
        unknown_attempts_count=m.unknown_attempts_count,
        evidence_mode=m.evidence_mode,
        generated_at=m.generated_at,
        store_readiness=m.store_readiness,
        unknown_exposure_paise=m.unknown_exposure_paise,
        funnel=[f.model_dump(mode="json") for f in m.funnel],
        needs_attention=[n.model_dump(mode="json") for n in m.needs_attention],
    )


@router.post("/buyer/plan", response_model=BuyerPlanResponse)
def plan_order_with_buyer(
    req: BuyerPlanRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    session_token: str | None = Header(None, alias="X-Shopper-Session"),
) -> BuyerPlanResponse:
    """Invoke the external AI buyer adapter to plan an order from natural language.

    Uses OpenAI with structured output when configured, or deterministic ReplayBuyer.
    """
    buyer_principal = verify_buyer_agent(authorization)
    shopper_principal = verify_shopper_session(session_token, expected_session_id=req.shopper_session_id)
    enforce_rate_limit(buyer_principal, shopper_principal.shopper_session_id)

    if req.buyer_mode == "replay":
        buyer = ReplayBuyer()
        plan = buyer.plan_order(req.goal, req.budget_paise)
        mode_used = "replay"
        fallback_reason = None
    else:
        buyer = OpenAIBuyer()
        plan = buyer.plan_order(req.goal, req.budget_paise)
        mode_used = plan.mode
        fallback_reason = plan.fallback_reason

    slots = [s.model_dump(mode="json") for s in plan.slots]
    skus = plan.selected_skus

    # Calculate authoritative quote total from server catalog if SKUs were selected
    quote_total = None
    if skus:
        cat_map = {item["sku"]: item for item in catalog.load_catalog()}
        quote_total = sum(cat_map[s]["price_paise"] for s in skus if s in cat_map)

    return BuyerPlanResponse(
        goal=req.goal,
        budget_paise=req.budget_paise,
        understood=plan.understood,
        slots=slots,
        suggested_skus=skus,
        quote_total_paise=quote_total,
        reasoning=plan.reasoning,
        mode_used=mode_used,
        fallback_reason=fallback_reason,
        latency_ms=plan.latency_ms,
    )

