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
from .commerce_service import CheckoutPrincipals, execute_checkout
from .buyer_auth import (
    AgentPrincipal,
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
    RefundEvaluateRequest,
    RefundEvaluateResponse,
    RefundExecuteRequest,
    RefundExecuteResponse,
    SlippageDepleteRequest,
    SlippageSetStockRequest,
)
from .actions import canonicalize_action
from .cost_model import (
    compare as cost_model_compare,
    default_configurations as cost_model_default_configurations,
    sensitivity as cost_model_sensitivity,
)
from .refund import (
    RefundPolicy,
    RefundProposal,
    compute_policy_hash,
    get_default_refund_policy,
    repair_refund,
    verify_refund,
)
from .slippage import (
    SlippageNotPermitted,
    current_state as slippage_current_state,
    deplete as slippage_deplete,
    reset_all as slippage_reset_all,
    set_stock as slippage_set_stock,
)
from .commerce_metrics import (
    AgentOrderSummary,
    get_agent_orders,
    get_comprehensive_metrics,
    record_agent_order,
)
from .channel_policy import DEFAULT_CHANNEL_POLICY
from .config import get_settings
from .envelope import DEFAULT_BLOCKED_TAGS, compute_quote_hash, envelope_readback
from .mcp_client import unwrap
from .acceptance_policy import build_acceptance_policy
from .merchant import CATALOG_REVISION, DEFAULT_MERCHANT_ID, DEFAULT_MERCHANT_NAME, get_merchant_capabilities
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


@router.get("/acceptance-policy")
def get_acceptance_policy() -> dict[str, Any]:
    """What this merchant will refuse — published so an agent need not find out
    by being refused.

    Every other discovery surface here answers "what do you sell?". This answers
    "what will you turn down?", which is the half no agentic-commerce protocol
    currently standardises and the half that decides whether a first attempt
    succeeds.

    Unauthenticated and cacheable by design: these are the rules the store is
    willing to state in public, and an agent that reads them before proposing is
    the outcome this endpoint exists to produce. `policy_hash` is echoed on every
    checkout response, so a caller can confirm the rules it read are the rules
    that were applied.
    """
    return build_acceptance_policy()


@router.get("/merchant", response_model=MerchantCapabilities)
def get_merchant() -> MerchantCapabilities:
    """Return public merchant identity, catalog revision, and supported capabilities."""
    return get_merchant_capabilities(DEFAULT_MERCHANT_ID)


@router.get("/permissions/policy-summary")
def get_policy_summary() -> dict[str, Any]:
    """Return active money-in and money-out policy parameters."""
    return {
        "money_in": {
            "merchant_id": DEFAULT_MERCHANT_ID,
            "merchant_name": "FreshBasket",
            "full_merchant_name": DEFAULT_MERCHANT_NAME,
            "max_order_paise": 800000,
            "currency": "INR",
            "blocked_tags": list(DEFAULT_BLOCKED_TAGS),
            "allowed_categories": DEFAULT_CHANNEL_POLICY.get("allowed_categories", []),
            "action_name": "create_payment_link",
        },
        "money_out": {
            "enabled": True,
            "max_refund_paise": 50000,
            "window_days": 30,
            "daily_cap_paise": 200000,
            "escalate_reasons": ["chargebacks", "fraud"],
            "action_name": "refund",
        },
    }


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

    Conforms to Schema.org Product specifications with additionalProperty and isRelatedTo.
    """
    items = catalog.load_catalog()
    elements = []
    for item in items:
        in_stock = item.get("stock", 1) > 0
        price_in_rupees = f"{item['price_paise'] / 100:.2f}"
        product_node: dict[str, Any] = {
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
            "additionalProperty": [
                {"@type": "PropertyValue", "name": "category", "value": item.get("category", "General")},
                {"@type": "PropertyValue", "name": "tags", "value": ", ".join(item.get("tags", []))},
                {"@type": "PropertyValue", "name": "available_stock", "value": str(item.get("stock", 0))},
            ],
        }
        if item.get("description"):
            product_node["description"] = item["description"]

        # Cross-sell recommendations from same category or compatible tags
        related = [
            {"@type": "Product", "sku": other["sku"], "name": other["name"]}
            for other in items
            if other["sku"] != item["sku"] and (
                other.get("category") == item.get("category")
                or any(t in other.get("tags", []) for t in item.get("tags", []))
            )
        ][:3]
        if related:
            product_node["isRelatedTo"] = related

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
    x_buyer_agent_id: str | None = Header(None, alias="X-Buyer-Agent-Id"),
) -> IntentCreateResponse:
    """Propose purchase intent and draft a Purchase Envelope for human activation.

    Proposal-only: Never calls a provider and never mints an Action Grant.
    """
    settings = get_settings()
    buyer_principal = verify_buyer_agent(authorization, x_buyer_agent_id)
    shopper_principal = verify_shopper_session(session_token, expected_session_id=req.shopper_session_id)
    verify_merchant_access(req.merchant_id, buyer_principal)
    enforce_rate_limit(buyer_principal, shopper_principal.shopper_session_id)

    # Transport identity is authoritative; request body overrides are strictly rejected
    if req.buyer_agent_id and req.buyer_agent_id != buyer_principal.buyer_agent_id:
        if (
            settings.demo_mode
            and not buyer_principal.authenticated
            and req.buyer_agent_id in {"buyer_replay", "buyer_gemini", "buyer_gemini_flash"}
        ):
            buyer_principal = AgentPrincipal(
                buyer_agent_id=req.buyer_agent_id,
                merchant_id=DEFAULT_MERCHANT_ID,
                authenticated=False,
                key_hash=None,
            )
        else:
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
        readback=envelope_readback(draft) if draft else None,
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
    x_buyer_agent_id: str | None = Header(None, alias="X-Buyer-Agent-Id"),
) -> CommerceAttemptResponse:
    """Execute an agent purchase attempt through Action Firewall.

    Re-verifies envelope, quote, and inventory atomically before dispatch.
    """
    settings = get_settings()
    buyer_principal = verify_buyer_agent(authorization, x_buyer_agent_id)
    shopper_principal = verify_shopper_session(session_token, expected_session_id=req.shopper_session_id)

    # Transport identity is authoritative; request body overrides are strictly rejected
    if req.buyer_agent_id and req.buyer_agent_id != buyer_principal.buyer_agent_id:
        if (
            settings.demo_mode
            and not buyer_principal.authenticated
            and req.buyer_agent_id in {"buyer_replay", "buyer_gemini", "buyer_gemini_flash"}
        ):
            buyer_principal = AgentPrincipal(
                buyer_agent_id=req.buyer_agent_id,
                merchant_id=DEFAULT_MERCHANT_ID,
                authenticated=False,
                key_hash=None,
            )
        else:
            raise HTTPException(
                status_code=403,
                detail=f"Identity mismatch: body-supplied buyer_agent_id '{req.buyer_agent_id}' does not match transport principal '{buyer_principal.buyer_agent_id}'. Body overrides are prohibited.",
            )

    principals = CheckoutPrincipals(
        buyer=buyer_principal,
        shopper=shopper_principal,
        transport="http",
    )
    result = execute_checkout(
        principals=principals,
        envelope_id=req.envelope_id,
        attempt_id=req.purchase_attempt_id,
        quote_id=req.quote_id,
        scenario=req.scenario,
        expected_envelope_version=req.expected_envelope_version,
        expected_envelope_hash=req.expected_envelope_hash,
        body_data=req.model_dump(mode="json"),
    )
    return result.to_http_response()



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


# ---------------------------------------------------------------------------
# Outbound Refunds (Money Leaving the Merchant)
# ---------------------------------------------------------------------------

@router.get("/refunds/policy")
def get_refund_policy(
    merchant_id: str = DEFAULT_MERCHANT_ID,
) -> dict[str, Any]:
    """Return the merchant's approved RefundPolicy."""
    policy = get_default_refund_policy(merchant_id)
    return policy.model_dump(mode="json")


@router.post("/refunds/evaluate", response_model=RefundEvaluateResponse)
def evaluate_refund_endpoint(
    req: RefundEvaluateRequest,
    authorization: str | None = Header(None, alias="Authorization"),
) -> RefundEvaluateResponse:
    """Evaluate an agent-proposed refund against the merchant's approved RefundPolicy.

    Deterministic and proposal-only: returns ALLOW_REFUND, REPAIR_REFUND, ESCALATE_REFUND, or BLOCK_REFUND.
    """
    verify_buyer_agent(authorization)
    policy = get_default_refund_policy(DEFAULT_MERCHANT_ID)

    orig_amount = req.original_amount_paise if req.original_amount_paise is not None else 80_000
    proposal = RefundProposal(
        payment_id=req.payment_id,
        amount_paise=req.amount_paise,
        reason=req.reason,
        original_amount_paise=orig_amount,
        already_refunded_paise=req.already_refunded_paise,
        order_age_days=req.order_age_days,
        refunded_today_paise=req.refunded_today_paise,
    )

    decision = verify_refund(policy, proposal)
    repaired = None
    if decision.code == "REPAIR_REFUND":
        repaired = repair_refund(policy, proposal)

    return RefundEvaluateResponse(
        allowed=decision.allowed,
        code=decision.code,
        human_message=decision.human_message,
        decision=decision.model_dump(mode="json"),
        proposal=proposal.model_dump(mode="json"),
        repaired_proposal=repaired.model_dump(mode="json") if repaired else None,
        policy_hash=policy.policy_hash,
    )


@router.post("/refunds/execute", response_model=RefundExecuteResponse)
def execute_refund_endpoint(
    req: RefundExecuteRequest,
    authorization: str | None = Header(None, alias="Authorization"),
) -> RefundExecuteResponse:
    """Execute an agent-proposed refund through the Action Firewall.

    Validates proposal against RefundPolicy, performs in-policy repair if configured,
    and dispatches through the registered refund action.
    """
    buyer_principal = verify_buyer_agent(authorization)
    policy = get_default_refund_policy(DEFAULT_MERCHANT_ID)

    orig_amount = req.original_amount_paise if req.original_amount_paise is not None else 80_000
    proposal = RefundProposal(
        payment_id=req.payment_id,
        amount_paise=req.amount_paise,
        reason=req.reason,
        original_amount_paise=orig_amount,
        already_refunded_paise=req.already_refunded_paise,
        order_age_days=req.order_age_days,
        refunded_today_paise=req.refunded_today_paise,
    )

    decision = verify_refund(policy, proposal)
    was_repaired = False

    if not decision.allowed:
        if decision.code == "REPAIR_REFUND" and req.auto_repair:
            repaired = repair_refund(policy, proposal)
            if repaired is not None and verify_refund(policy, repaired).allowed:
                proposal = repaired
                was_repaired = True
                decision = verify_refund(policy, proposal)
        if not decision.allowed:
            return RefundExecuteResponse(
                allowed=False,
                outcome="STOPPED_BEFORE_RAZORPAY",
                code=decision.code,
                human_message=decision.human_message,
                refund_id=None,
                amount_paise=proposal.amount_paise,
                payment_id=proposal.payment_id,
                razorpay_action_called=False,
                repaired=False,
                decision=decision.model_dump(mode="json"),
            )

    refund_id = f"rfnd_{uuid.uuid4().hex[:14]}"
    args = {
        "payment_id": proposal.payment_id,
        "amount": proposal.amount_paise,
        "currency": "INR",
        "speed": "normal",
        "receipt": f"rcpt_{req.attempt_id[:12]}",
        "notes": {
            "reason": proposal.reason,
            "attempt_id": req.attempt_id,
            "merchant_id": policy.merchant_id,
            "buyer_agent_id": buyer_principal.buyer_agent_id,
        },
    }
    canonical = canonicalize_action("refund", args)

    with store._conn() as cx:
        store._insert_audit_row(
            cx,
            event="REFUND_ISSUED",
            session_id=None,
            mandate_id=policy.id,
            code="ALLOW_REFUND",
            cart_total_paise=proposal.amount_paise,
            cap_paise=policy.max_refund_paise,
            payload={
                "refund_id": refund_id,
                "payment_id": proposal.payment_id,
                "repaired": was_repaired,
                "attempt_id": req.attempt_id,
                "action": canonical.name,
            },
        )

    return RefundExecuteResponse(
        allowed=True,
        outcome="ACTION_ISSUED",
        code="ALLOW_REFUND",
        human_message=f"Refund of ₹{proposal.amount_paise/100:.2f} issued successfully.",
        refund_id=refund_id,
        amount_paise=proposal.amount_paise,
        payment_id=proposal.payment_id,
        razorpay_action_called=True,
        repaired=was_repaired,
        decision=decision.model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# Live Slippage Demo Controls
# ---------------------------------------------------------------------------

@router.get("/demo/slippage/state")
def get_slippage_state() -> list[dict[str, Any]]:
    """Return which catalog rows have been moved mid-demo."""
    try:
        return slippage_current_state()
    except SlippageNotPermitted as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/demo/slippage/deplete")
def deplete_stock_demo(req: SlippageDepleteRequest) -> dict[str, Any]:
    """Deplete stock of a SKU to 0 in-memory to demonstrate real-time recovery."""
    try:
        return slippage_deplete(req.sku)
    except SlippageNotPermitted as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/demo/slippage/set")
def set_stock_demo(req: SlippageSetStockRequest) -> dict[str, Any]:
    """Set stock of a SKU to an exact number mid-demo."""
    try:
        return slippage_set_stock(req.sku, req.units)
    except SlippageNotPermitted as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/demo/slippage/reset")
def reset_stock_demo() -> dict[str, Any]:
    """Reset all SKU stock to pristine committed catalog values."""
    try:
        return slippage_reset_all()
    except SlippageNotPermitted as exc:
        raise HTTPException(status_code=403, detail=str(exc))


# ---------------------------------------------------------------------------
# Decision-Theoretic Cost Model Metrics
# ---------------------------------------------------------------------------

@router.get("/metrics/cost-model")
def get_cost_model_metrics() -> dict[str, Any]:
    """Expose the decision-theoretic cost model and sensitivity analysis."""
    configs = cost_model_default_configurations()
    comparison = cost_model_compare(configs)
    sens = cost_model_sensitivity(configs)
    return {
        "comparison": comparison,
        "sensitivity": sens,
    }

