"""Tests for unified commerce service (commerce_service.py).

Verifies that execute_checkout acts as the single, authoritative money path
across both HTTP and MCP transport principals.
"""
from __future__ import annotations

import time
import pytest
from fastapi import HTTPException

from app import catalog, store
from app.approval_tokens import redeem_approval_token
from app.buyer_auth import AgentPrincipal, ShopperPrincipal
from app.commerce_mcp import _quote_owner, draft_purchase, request_quote
from app.commerce_service import CheckoutPrincipals, execute_checkout
from app.config import get_settings
from app.merchant import CATALOG_REVISION, DEFAULT_MERCHANT_ID


@pytest.fixture(autouse=True)
def init_test_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "commerce_service.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    get_settings.cache_clear()
    store.init_db()


def _make_principals(transport: str = "http", buyer_id: str = "buyer_test_01") -> CheckoutPrincipals:
    return CheckoutPrincipals(
        buyer=AgentPrincipal(buyer_agent_id=buyer_id, merchant_id=DEFAULT_MERCHANT_ID),
        shopper=ShopperPrincipal(user_id="usr_01", shopper_session_id="sess_shopper_01"),
        transport=transport,  # type: ignore
    )


def test_unactivated_envelope_blocked_consistently():
    """Unactivated envelopes fail closed before provider transport on both HTTP and MCP."""
    draft = draft_purchase(
        intent="Buy supplies for a pasta dinner",
        agent_request_id="req_svc_unact",
        budget_paise=60000,
    )
    env_id = draft["intent_id"]

    # HTTP transport
    p_http = _make_principals(transport="http")
    res_http = execute_checkout(p_http, envelope_id=env_id, attempt_id="att_unact_http")
    assert res_http.allowed is False
    assert res_http.outcome == "STOPPED_BEFORE_RAZORPAY"
    assert res_http.code == "BLOCK_ENVELOPE_DRAFT"
    assert res_http.razorpay_action_called is False

    # MCP transport
    p_mcp = _make_principals(transport="mcp")
    res_mcp = execute_checkout(p_mcp, envelope_id=env_id, attempt_id="att_unact_mcp")
    assert res_mcp.allowed is False
    assert res_mcp.outcome == "STOPPED_BEFORE_RAZORPAY"
    assert res_mcp.code == "AWAITING_CUSTOMER_APPROVAL"
    assert res_mcp.razorpay_action_called is False


def test_quote_cross_buyer_isolation():
    """Quotes belong exclusively to the minting buyer agent."""
    draft = draft_purchase(
        intent="Buy supplies for a pasta dinner",
        agent_request_id="req_svc_cross",
        budget_paise=60000,
    )
    token = draft["approval_url"].replace("/approve/", "")
    redeem_approval_token(token)

    quote = request_quote(items=[{"sku": "SKU-PAS-002", "quantity": 1}])
    quote_id = quote["quote_id"]

    # Quote is owned by "buyer_mcp" in request_quote
    # Different buyer agent calling HTTP must get 404
    p_intruder_http = _make_principals(transport="http", buyer_id="buyer_attacker")
    with pytest.raises(HTTPException) as exc_info:
        execute_checkout(
            p_intruder_http,
            envelope_id=draft["intent_id"],
            attempt_id="att_intruder_http",
            quote_id=quote_id,
        )
    assert exc_info.value.status_code == 404

    # Different buyer agent calling MCP must receive structured QUOTE_NOT_FOUND
    p_intruder_mcp = _make_principals(transport="mcp", buyer_id="buyer_attacker")
    res_mcp = execute_checkout(
        p_intruder_mcp,
        envelope_id=draft["intent_id"],
        attempt_id="att_intruder_mcp",
        quote_id=quote_id,
    )
    assert res_mcp.allowed is False
    assert res_mcp.code == "QUOTE_NOT_FOUND"


def test_expired_quote_rejected():
    """Expired quote cannot be redeemed for checkout."""
    draft = draft_purchase(
        intent="Buy supplies for a pasta dinner",
        agent_request_id="req_svc_exp",
        budget_paise=60000,
    )
    token = draft["approval_url"].replace("/approve/", "")
    redeem_approval_token(token)

    quote = request_quote(items=[{"sku": "SKU-PAS-002", "quantity": 1}])
    quote_id = quote["quote_id"]

    # Manually expire quote in database
    with store._conn() as cx:
        cx.execute("UPDATE commerce_quotes SET valid_until = ? WHERE id = ?", (time.time() - 100, quote_id))

    # HTTP transport
    p_http = _make_principals(transport="http", buyer_id=_quote_owner())
    with pytest.raises(HTTPException) as exc_info:
        execute_checkout(p_http, envelope_id=draft["intent_id"], attempt_id="att_exp_http", quote_id=quote_id)
    assert exc_info.value.status_code == 409

    # MCP transport
    p_mcp = _make_principals(transport="mcp", buyer_id=_quote_owner())
    res_mcp = execute_checkout(p_mcp, envelope_id=draft["intent_id"], attempt_id="att_exp_mcp", quote_id=quote_id)
    assert res_mcp.allowed is False
    assert res_mcp.code == "QUOTE_EXPIRED"


def test_quote_catalog_revision_drift_rejected():
    """Quote invalidated by catalog revision change triggers REQUOTE_REQUIRED."""
    draft = draft_purchase(
        intent="Buy supplies for a pasta dinner",
        agent_request_id="req_svc_rev",
        budget_paise=60000,
    )
    token = draft["approval_url"].replace("/approve/", "")
    redeem_approval_token(token)

    quote = request_quote(items=[{"sku": "SKU-PAS-002", "quantity": 1}])
    quote_id = quote["quote_id"]

    with store._conn() as cx:
        cx.execute("UPDATE commerce_quotes SET catalog_revision = ? WHERE id = ?", ("rev_outdated", quote_id))

    p_http = _make_principals(transport="http", buyer_id=_quote_owner())
    with pytest.raises(HTTPException) as exc_info:
        execute_checkout(p_http, envelope_id=draft["intent_id"], attempt_id="att_rev_http", quote_id=quote_id)
    assert exc_info.value.status_code == 409
    assert "REQUOTE_REQUIRED" in exc_info.value.detail


def test_full_successful_checkout_and_replay():
    """End-to-end checkout through execute_checkout issues payment link and caches idempotent replay."""
    draft = draft_purchase(
        intent="Buy supplies for a pasta dinner",
        agent_request_id="req_svc_full",
        budget_paise=60000,
    )
    token = draft["approval_url"].replace("/approve/", "")
    redeem_approval_token(token)

    quote = request_quote(items=[{"sku": "SKU-PAS-002", "quantity": 1}])
    quote_id = quote["quote_id"]

    principals = _make_principals(transport="http", buyer_id=_quote_owner())
    body_data = {
        "envelope_id": draft["intent_id"],
        "purchase_attempt_id": "att_full_svc_01",
        "quote_id": quote_id,
        "shopper_session_id": "sess_shopper_01",
    }

    # First attempt succeeds
    res1 = execute_checkout(
        principals=principals,
        envelope_id=draft["intent_id"],
        attempt_id="att_full_svc_01",
        quote_id=quote_id,
        body_data=body_data,
    )
    assert res1.allowed is True
    assert res1.outcome == "ACTION_ISSUED"
    assert res1.payment_link and "/simulated/payment-link/" in res1.payment_link
    assert res1.razorpay_action_called is True

    # Exact replay with identical body_data returns cached result
    res2 = execute_checkout(
        principals=principals,
        envelope_id=draft["intent_id"],
        attempt_id="att_full_svc_01",
        quote_id=quote_id,
        body_data=body_data,
    )
    assert res2.allowed is True
    assert res2.outcome == "ACTION_ISSUED"
    assert res2.payment_link == res1.payment_link
