"""Action Firewall — Northbound MCP Server for AI Buyers.

Exposes a strictly customer-scoped 6-tool surface:
1. discover_storefront
2. search_catalog
3. draft_purchase
4. request_quote
5. request_checkout
6. get_checkout_status

SAFETY INVARIANTS:
- Zero raw Razorpay provider tools exposed northbound;
- Direct payment creation, capture, refund, or payout tools are strictly absent;
- Human activation is never an MCP tool (only the browser path may activate);
- Intent creation and quote requests are proposal-only;
- Headroom is atomically reserved under single CAS dispatch lock.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any
from mcp.server.fastmcp import FastMCP

from . import autopilot
from . import catalog
from . import demo_scenario
from . import store
from .approval_tokens import mint_approval_token
from .authorization import canonical_json
from .envelope import compute_quote_hash
from .buyer_models import (
    CommerceAttemptRequest,
    CommerceAttemptResponse,
    IntentCreateRequest,
    QuoteRequest,
)
from .channel_policy import evaluate_channel_policy
from .commerce_metrics import record_agent_order
from .config import get_settings
from .merchant import CATALOG_REVISION, DEFAULT_MERCHANT_ID, get_merchant_capabilities
from .models import (
    AutopilotExecuteRequest,
    AutopilotScenario,
    Cart,
    CartLine,
    EnvelopeDraftRequest,
    MerchantQuote,
)

mcp_server = FastMCP("Action Firewall — AI Commerce Gateway")


@mcp_server.tool()
def discover_storefront() -> dict[str, Any]:
    """Discover merchant public identity, supported currency, rails, and evidence environment."""
    profile = get_merchant_capabilities(DEFAULT_MERCHANT_ID)
    settings = get_settings()
    return {
        "merchant_id": profile.merchant_id,
        "display_name": profile.display_name,
        "currency": profile.currency,
        "default_fulfillment_profile_id": profile.default_fulfillment_profile_id,
        "supported_currencies": profile.supported_currencies,
        "fulfillment_modes": profile.fulfillment_modes,
        "capabilities": profile.capabilities,
        "action_name": profile.action_name,
        "catalog_revision": profile.catalog_revision,
        "store_readiness": "READY_FOR_AI_BUYERS",
        "evidence_mode": settings.payment_provider,
    }


@mcp_server.tool()
def search_catalog(query: str = "", limit: int = 10) -> list[dict[str, Any]]:
    """Search merchant catalog by keyword or tags. Returns server-owned verified facts."""
    items = catalog.load_catalog()
    q = query.strip().lower()
    matches: list[dict[str, Any]] = []

    for item in items:
        if not q or (
            q in item["name"].lower()
            or q in item["sku"].lower()
            or q in item["category"].lower()
            or any(q in tag.lower() for tag in item.get("tags", []))
        ):
            matches.append(
                {
                    "sku": item["sku"],
                    "name": item["name"],
                    "category": item["category"],
                    "price_paise": item["price_paise"],
                    "in_stock": item.get("in_stock", True),
                    "tags": item.get("tags", []),
                }
            )
            if len(matches) >= limit:
                break

    return matches


@mcp_server.tool()
def draft_purchase(
    intent: str,
    agent_request_id: str,
    budget_paise: int = 60000,
) -> dict[str, Any]:
    """Draft a Purchase Envelope from shopping intent.

    Proposal-only: Mints an opaque expiring approval URL for customer review.
    Does not activate authority or execute any financial transaction.
    """
    goal = intent.strip()
    if not goal:
        return {"error": "Shopping goal intent cannot be empty"}

    max_rupees = max(1, budget_paise // 100)
    draft_req = EnvelopeDraftRequest(
        goal=goal,
        max_total_rupees=max_rupees,
        merchant_id=DEFAULT_MERCHANT_ID,
    )
    draft = autopilot.create_draft(draft_req)

    # Mint opaque, single-use approval URL
    _, approval_url = mint_approval_token(
        envelope_id=draft.id,
        envelope_hash=draft.envelope_hash,
        ttl_seconds=900,
    )

    return {
        "agent_request_id": agent_request_id,
        "intent_id": draft.id,
        "envelope_id": draft.id,
        "status": draft.status.value,
        "max_total_paise": draft.max_total_paise,
        "currency": draft.currency,
        "envelope_hash": draft.envelope_hash,
        "required_slots": [s.label for s in draft.slots],
        "approval_url": approval_url,
        "message": (
          "Draft Purchase Envelope prepared for customer review. "
          "Return approval_url to customer; authority activates only upon explicit customer approval."
        ),
        "authority_active": False,
    }


@mcp_server.tool()
def request_quote(
    items: list[dict[str, Any]],
    fulfillment_profile_id: str = "dest_demo",
) -> dict[str, Any]:
    """Compute an authoritative merchant quote based on current server catalog facts.

    Discards any caller-supplied unit prices or totals.
    """
    catalog_items = {item["sku"]: item for item in catalog.load_catalog()}
    lines: list[CartLine] = []

    for req_item in items:
        sku = req_item.get("sku", "")
        qty = int(req_item.get("quantity", 1))
        product = catalog_items.get(sku)
        if not product:
            return {"error": f"Unknown SKU: {sku}"}

        lines.append(
            CartLine(
                sku=product["sku"],
                name=product["name"],
                category=product["category"],
                unit_price_paise=product["price_paise"],
                qty=qty,
            )
        )

    cart = Cart(lines=lines)
    quote = MerchantQuote(
        merchant_id=DEFAULT_MERCHANT_ID,
        currency="INR",
        fulfillment_profile_id=fulfillment_profile_id,
        delivery_eta=time.time() + 2700,
        cart=cart,
        substitutions=[],
        quote_hash="",
    )
    quote_hash = compute_quote_hash(quote)
    quote = quote.model_copy(update={"quote_hash": quote_hash})

    # Persist the quote row
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
        merchant_id=DEFAULT_MERCHANT_ID,
        buyer_agent_id="buyer_mcp",
        shopper_session_id="session_mcp_quote",
        catalog_revision=CATALOG_REVISION,
        canonical_cart_json=canonical_cart_json,
        cart_hash=cart_hash,
        quote_hash=quote_hash,
        total_paise=cart.total_paise,
        valid_until=valid_until,
    )

    return {
        "quote_id": quote_id,
        "merchant_id": DEFAULT_MERCHANT_ID,
        "currency": "INR",
        "total_paise": cart.total_paise,
        "quote_hash": quote.quote_hash,
        "catalog_revision": CATALOG_REVISION,
        "lines": [
            {
                "sku": line.sku,
                "name": line.name,
                "qty": line.qty,
                "unit_price_paise": line.unit_price_paise,
                "line_total_paise": line.line_total_paise,
            }
            for line in cart.lines
        ],
        "valid_until": valid_until,
    }


@mcp_server.tool()
def request_checkout(
    intent_id: str,
    quote_id: str,
    attempt_id: str,
) -> dict[str, Any]:
    """Execute purchase attempt through Action Firewall.

    Fails closed if the envelope has not been explicitly activated by customer.
    Re-verifies quote and atomic headroom reservation before single CAS dispatch.
    """
    envelope = store.get_envelope(intent_id)
    if not envelope:
        return {"allowed": False, "error": "Unknown Purchase Envelope"}

    # Fails closed if not activated
    if envelope.status.value != "active":
        return {
            "allowed": False,
            "outcome": "STOPPED_BEFORE_RAZORPAY",
            "code": "AWAITING_CUSTOMER_APPROVAL",
            "human_message": "Purchase Envelope is in draft status. Customer approval via approval_url required before checkout.",
            "payment_link": None,
            "razorpay_action_called": False,
        }

    # 1. Reload quote row BY ID
    persisted_quote = store.get_commerce_quote(quote_id)
    if not persisted_quote:
        return {
            "allowed": False,
            "outcome": "STOPPED_BEFORE_RAZORPAY",
            "code": "QUOTE_NOT_FOUND",
            "error": f"Quote {quote_id} not found",
            "payment_link": None,
            "razorpay_action_called": False,
        }

    # 2. Ownership check: quote owned by another buyer is rejected (returns not-found, not forbidden)
    expected_buyer_id = "buyer_mcp"
    if persisted_quote["buyer_agent_id"] != expected_buyer_id:
        return {
            "allowed": False,
            "outcome": "STOPPED_BEFORE_RAZORPAY",
            "code": "QUOTE_NOT_FOUND",
            "error": f"Quote {quote_id} not found",
            "payment_link": None,
            "razorpay_action_called": False,
        }

    # 3. Expiry check: expired quote is rejected
    if time.time() > persisted_quote["valid_until"]:
        return {
            "allowed": False,
            "outcome": "STOPPED_BEFORE_RAZORPAY",
            "code": "QUOTE_EXPIRED",
            "error": "Quote has expired. Fresh quote required.",
            "payment_link": None,
            "razorpay_action_called": False,
        }

    # 4. Catalog revision check: changed catalog_revision returns REQUOTE_REQUIRED
    if persisted_quote["catalog_revision"] != CATALOG_REVISION:
        return {
            "allowed": False,
            "outcome": "STOPPED_BEFORE_RAZORPAY",
            "code": "REQUOTE_REQUIRED",
            "error": "Catalog revision has changed since quote was generated. REQUOTE_REQUIRED.",
            "payment_link": None,
            "razorpay_action_called": False,
        }

    # 5. Check if same quote was already checked out
    if persisted_quote.get("checked_out_at") is not None:
        return {
            "allowed": False,
            "outcome": "STOPPED_BEFORE_RAZORPAY",
            "code": "QUOTE_ALREADY_CHECKED_OUT",
            "error": "Quote has already been checked out. Replay blocked.",
            "payment_link": None,
            "razorpay_action_called": False,
        }

    # Authoritative money value from the persisted quote row (caller-supplied values are ignored)
    authoritative_amount_paise = persisted_quote["total_paise"]

    # Evaluate merchant channel policy using authoritative quote amount
    channel_dec = evaluate_channel_policy(
        merchant_id=envelope.merchant_id,
        amount_paise=authoritative_amount_paise,
        action_name="create_payment_link",
    )
    if not channel_dec.allowed:
        return {
            "allowed": False,
            "outcome": "STOPPED_BEFORE_RAZORPAY",
            "code": channel_dec.code,
            "human_message": channel_dec.reason,
            "payment_link": None,
            "razorpay_action_called": False,
        }

    # Atomic CAS marking quote checked out
    if not store.mark_commerce_quote_checked_out(quote_id, attempt_id):
        return {
            "allowed": False,
            "outcome": "STOPPED_BEFORE_RAZORPAY",
            "code": "QUOTE_ALREADY_CHECKED_OUT",
            "error": "Quote was concurrently checked out. Replay blocked.",
            "payment_link": None,
            "razorpay_action_called": False,
        }

    scen = demo_scenario.get_active_scenario()
    exec_req = AutopilotExecuteRequest(
        envelope_id=envelope.id,
        expected_envelope_version=envelope.version,
        expected_envelope_hash=envelope.envelope_hash,
        session_id=f"sess_mcp_{uuid.uuid4().hex[:8]}",
        purchase_attempt_id=attempt_id,
        scenario=scen,
    )

    res = autopilot.execute(exec_req)
    if res.action_status == "action_issued":
        outcome = "RECOVERED_INSIDE_ENVELOPE" if res.recovery_applied else "ACTION_ISSUED"
    elif res.action_status == "unknown":
        outcome = "UNKNOWN"
    elif not res.envelope_decision.allowed:
        outcome = "POLICY_DELTA_REQUIRED" if res.envelope_decision.deltas else "STOPPED_BEFORE_RAZORPAY"
    order_status = (
        "issued" if res.action_status == "action_issued"
        else "unknown" if res.action_status == "unknown"
        else "blocked"
    )
    record_agent_order(
        purchase_attempt_id=attempt_id,
        merchant_id=envelope.merchant_id,
        buyer_agent_id="buyer_mcp",
        shopper_session_id=exec_req.session_id,
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

    return {
        "attempt_id": attempt_id,
        "intent_id": intent_id,
        "envelope_id": intent_id,
        "allowed": res.envelope_decision.allowed,
        "outcome": outcome,
        "code": res.envelope_decision.code,
        "human_message": res.envelope_decision.human_message,
        "payment_link": res.payment_link,
        "grant_id": res.grant_id,
        "receipt_id": res.receipt.grant_id if res.receipt else None,
        "recovery_applied": res.recovery_applied,
        "provider_mode": res.provider_mode,
        "razorpay_action_called": bool(res.payment_link or res.action_status in ("action_issued", "unknown")),
    }


@mcp_server.tool()
def get_checkout_status(attempt_id: str) -> dict[str, Any]:
    """Query telemetry status of a purchase attempt. Polling never re-dispatches."""
    merchant_id = DEFAULT_MERCHANT_ID
    buyer_agent_id = "buyer_mcp"
    data = store.get_agent_order(
        attempt_id=attempt_id,
        merchant_id=merchant_id,
        buyer_agent_id=buyer_agent_id,
    )
    if not data:
        return {"attempt_id": attempt_id, "status": "not_found"}

    return {
        "attempt_id": data["purchase_attempt_id"],
        "order_id": data["order_id"],
        "status": data["status"],
        "outcome": data["outcome"],
        "amount_paise": data["amount_paise"],
        "recovery_applied": bool(data["recovery_applied"]),
        "payment_link": data["payment_link"],
        "grant_id": data["grant_id"],
        "receipt_id": data["receipt_id"],
        "code": data["code"],
        "updated_at": data["updated_at"],
    }

