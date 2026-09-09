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
from . import mcp_client
from . import store
from .approval_tokens import mint_approval_token
from .authorization import canonical_json
from fastapi import HTTPException

from .buyer_auth import AgentPrincipal, ShopperPrincipal, verify_buyer_agent
from .commerce_service import CheckoutPrincipals, execute_checkout
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
    DEFAULT_FULFILLMENT_PROFILE_ID,
    AutopilotExecuteRequest,
    AutopilotScenario,
    Cart,
    CartLine,
    EnvelopeDraftRequest,
    MerchantQuote,
)

def _quote_owner() -> str:
    """The buyer identity this call presents, for rows keyed by owner.

    Falls back to MCP_BUYER_AGENT_ID only when no principal can be resolved at
    all, so a quote is always attributable to someone.
    """
    principals, _refusal = _resolve_mcp_principals()
    if principals is None:
        return MCP_BUYER_AGENT_ID
    return principals.buyer.buyer_agent_id


def _bearer_from_request_context() -> str | None:
    """The Authorization header of the live MCP request, if there is one.

    FastMCP's RequestContext carries the underlying Starlette request on the
    Streamable HTTP transport, so the same header the HTTP surface reads is
    reachable here. Outside a request — a direct call from a test, or a stdio
    transport with no HTTP layer — `get_context()` raises, and that is not an
    error: it means no credential was presented, which is exactly what gets
    passed to verify_buyer_agent to decide.
    """
    try:
        request = mcp_server.get_context().request_context.request
    except Exception:  # noqa: BLE001 — absence of a request is a normal state here
        return None
    headers = getattr(request, "headers", None)
    if headers is None:
        return None
    return headers.get("authorization") or headers.get("Authorization")


def _resolve_mcp_principals() -> tuple[CheckoutPrincipals | None, dict[str, Any] | None]:
    """Resolve who is calling, or say why we will not proceed.

    This exists because the MCP surface is the one we ADVERTISE to AI buyers, and
    until now it built its own principal from constants:

        AgentPrincipal(buyer_agent_id=MCP_BUYER_AGENT_ID, ...)

    `AgentPrincipal.authenticated` defaults to True, so that object asserted an
    authentication that had never happened. The guard sequence downstream then
    trusted it. Identity asserted rather than verified is the same hole the
    field's weakest entries have; routing through verify_buyer_agent — the exact
    function the HTTP twin uses — is what closes it.

    verify_buyer_agent already encodes the three cases correctly: a valid key
    yields an authenticated principal, an invalid or revoked key raises, and no
    key in demo mode yields a principal explicitly marked authenticated=False
    rather than a fabricated one.

    Returns (principals, None) or (None, refusal_dict). MCP tools answer; they do
    not throw, so a rejected credential comes back as a structured refusal.
    """
    try:
        buyer = verify_buyer_agent(_bearer_from_request_context())
    except HTTPException as exc:
        return None, {
            "allowed": False,
            "outcome": "STOPPED_BEFORE_RAZORPAY",
            "code": "UNAUTHENTICATED_BUYER_AGENT",
            "human_message": str(exc.detail),
            "payment_link": None,
            "razorpay_action_called": False,
        }

    return (
        CheckoutPrincipals(
            buyer=buyer,
            shopper=ShopperPrincipal(
                user_id="user_mcp",
                shopper_session_id=MCP_QUOTE_SESSION_ID,
                authenticated=buyer.authenticated,
            ),
            transport="mcp",
        ),
        None,
    )


#: Identity this MCP transport presents to the shared commerce layer.
#: These are constants, not inline literals, for one reason: request_quote WRITES
#: the quote row's owner and request_checkout READS it back to decide ownership.
#: When those were two separate string literals, a typo in either one silently
#: turned every MCP checkout into QUOTE_NOT_FOUND (or, worse, let a quote minted
#: by one identity be spent by another). One definition, both sites.
MCP_BUYER_AGENT_ID = "buyer_mcp"
MCP_QUOTE_SESSION_ID = "session_mcp_quote"

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
        "evidence_mode": mcp_client.get_active_provider_mode(),
    }


@mcp_server.tool()
def search_catalog(query: str = "", limit: int = 10) -> list[dict[str, Any]]:
    """Search merchant catalog by keyword or tags. Returns server-owned verified facts."""
    items = catalog.load_catalog()
    q = query.strip().lower()
    terms = [t for t in q.split() if len(t) > 2 and t not in {"buy", "the", "for", "and", "with", "from"}]
    matches: list[dict[str, Any]] = []

    for item in items:
        name_l = item["name"].lower()
        sku_l = item["sku"].lower()
        cat_l = item["category"].lower()
        tags_l = [tag.lower() for tag in item.get("tags", [])]

        matches_exact = not q or (q in name_l or q in sku_l or q in cat_l or any(q in t for t in tags_l))
        matches_terms = any(t in name_l or t in sku_l or t in cat_l or any(t in tag for tag in tags_l) for t in terms) if terms else False

        if matches_exact or matches_terms:
            matches.append(
                {
                    "sku": item["sku"],
                    "name": item["name"],
                    "category": item["category"],
                    "price_paise": item["price_paise"],
                    # Same expression as the HTTP surface in agent_commerce.py.
                    # These read the SAME catalog rows and previously used two
                    # different keys ("in_stock" here, "stock" there), so the two
                    # surfaces could have disagreed about availability for one SKU.
                    "in_stock": item.get("stock", 1) > 0,
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
    fulfillment_profile_id: str = DEFAULT_FULFILLMENT_PROFILE_ID,
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
        # Resolved, not constant. request_checkout reads this row back to decide
        # ownership, so the writer and the reader must derive identity the same
        # way — otherwise a caller mints a quote it cannot then spend.
        buyer_agent_id=_quote_owner(),
        shopper_session_id=MCP_QUOTE_SESSION_ID,
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
    principals, refusal = _resolve_mcp_principals()
    if refusal is not None:
        return refusal
    result = execute_checkout(
        principals=principals,
        envelope_id=intent_id,
        attempt_id=attempt_id,
        quote_id=quote_id,
    )
    return result.to_mcp_dict()



@mcp_server.tool()
def get_checkout_status(attempt_id: str) -> dict[str, Any]:
    """Query telemetry status of a purchase attempt. Polling never re-dispatches."""
    merchant_id = DEFAULT_MERCHANT_ID
    buyer_agent_id = _quote_owner()
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

