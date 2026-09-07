"""Tests for Northbound MCP Server (commerce_mcp.py).

Verifies:
1. The tool list contains EXACTLY the six allowed tools;
2. Zero raw Razorpay actuator tools are exposed northbound;
3. Human activation is never an MCP tool;
4. Discovery, search, and proposal-only drafting function properly;
5. Unactivated envelopes fail closed before provider transport;
6. Approval token redemption activates the envelope;
7. Activated envelope checkouts issue payment links;
8. Polling checkout status returns recorded order without re-dispatching.
"""
from __future__ import annotations

import pytest

from app.approval_tokens import redeem_approval_token
from app.commerce_mcp import (
    discover_storefront,
    draft_purchase,
    get_checkout_status,
    mcp_server,
    request_checkout,
    request_quote,
    search_catalog,
)
from app.models import MandateCreate
from app import store


@pytest.fixture(autouse=True)
def clean_database(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_mcp.db")
    monkeypatch.setenv("DB_PATH", db_file)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("ENVELOPE_DRAFTING_MODE", "replay")
    store.init_db()
    store.create_mandate(MandateCreate(cap_rupees=5000))
    yield


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_mcp_exact_tool_allowlist():
    """Verify tool discovery contains EXACTLY the 6 allowed customer-scoped tools."""
    tool_names = sorted([t.name for t in mcp_server._tool_manager.list_tools()])
    expected = sorted([
        "discover_storefront",
        "search_catalog",
        "draft_purchase",
        "request_quote",
        "request_checkout",
        "get_checkout_status",
    ])
    assert tool_names == expected, f"Tool list mismatch: {tool_names} != {expected}"

    # Critical security assertions: Zero raw Razorpay or activation tools
    forbidden = [
        "activate_envelope",
        "create_payment_link",
        "capture_payment",
        "refund_payment",
        "call_razorpay_tool",
    ]
    for bad in forbidden:
        assert bad not in tool_names, f"Forbidden tool {bad} exposed northbound!"


def test_discover_storefront_tool():
    res = discover_storefront()
    assert res["merchant_id"] == "merchant_demo"
    assert res["currency"] == "INR"
    assert res["action_name"] == "create_payment_link"
    assert res["store_readiness"] == "READY_FOR_AI_BUYERS"


def test_search_catalog_tool():
    results = search_catalog(query="pasta", limit=5)
    assert len(results) > 0
    first = results[0]
    assert "sku" in first
    assert "price_paise" in first
    assert isinstance(first["price_paise"], int)


def test_draft_purchase_is_proposal_only():
    res = draft_purchase(
        intent="Buy supplies for a pasta dinner",
        agent_request_id="mcp_req_001",
        budget_paise=60000,
    )
    assert res["status"] == "draft"
    assert res["authority_active"] is False
    assert res["approval_url"].startswith("/approve/appr_")
    assert len(res["required_slots"]) >= 1


def test_request_quote_computes_server_prices():
    items = [
        {"sku": "SKU-PAS-002", "quantity": 2},
        {"sku": "SKU-SAU-001", "quantity": 1},
    ]
    res = request_quote(items=items)
    assert res["currency"] == "INR"
    assert res["total_paise"] == (8900 * 2) + 24900
    assert len(res["quote_hash"]) == 64


def test_unactivated_envelope_fails_closed_in_mcp():
    draft = draft_purchase(
        intent="Buy supplies for a pasta dinner",
        agent_request_id="mcp_req_unact",
        budget_paise=60000,
    )
    res = request_checkout(
        envelope_id=draft["envelope_id"],
        purchase_attempt_id="att_mcp_unact",
        scenario="normal",
    )
    assert res["allowed"] is False
    assert res["outcome"] == "STOPPED_BEFORE_RAZORPAY"
    assert res["code"] == "AWAITING_CUSTOMER_APPROVAL"
    assert res["razorpay_action_called"] is False
    assert res["payment_link"] is None


def test_mcp_full_checkout_lifecycle():
    # 1. Draft purchase
    draft = draft_purchase(
        intent="Buy supplies for a pasta dinner",
        agent_request_id="mcp_req_full",
        budget_paise=60000,
    )
    approval_url = draft["approval_url"]
    raw_token = approval_url.replace("/approve/", "")

    # 2. Human redemption of approval token (via browser path)
    active = redeem_approval_token(raw_token)
    assert active.status.value == "active"

    # 3. Request checkout via MCP
    res = request_checkout(
        envelope_id=draft["envelope_id"],
        purchase_attempt_id="att_mcp_success_01",
        scenario="normal",
    )
    assert res["allowed"] is True
    assert res["outcome"] == "ACTION_ISSUED"
    assert res["payment_link"] and res["payment_link"].startswith("https://rzp.io/")
    assert res["grant_id"] is not None
    assert res["razorpay_action_called"] is True

    # 4. Polling status returns recorded outcome
    stat = get_checkout_status("att_mcp_success_01")
    assert stat["status"] == "issued"
    assert stat["payment_link"] == res["payment_link"]


@pytest.mark.anyio
async def test_mcp_in_memory_client_session_discovery():
    """Verify tool discovery via MCP SDK ClientSession in-memory protocol client."""
    from mcp.shared.memory import create_connected_server_and_client_session

    async with create_connected_server_and_client_session(mcp_server._mcp_server) as session:
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        expected = {
            "discover_storefront",
            "search_catalog",
            "draft_purchase",
            "request_quote",
            "request_checkout",
            "get_checkout_status",
        }
        assert names == expected, f"ClientSession tools mismatch: {names} != {expected}"
        assert not any(
            t.name in {
                "create_payment_link",
                "capture_payment",
                "refund_payment",
                "activate_envelope",
                "call_razorpay_tool",
            }
            for t in tools.tools
        )


def test_mcp_streamable_http_endpoint_mounted():
    """Verify the Streamable HTTP ASGI app is mounted and responds at /agent-commerce/mcp/."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app, base_url="http://localhost") as client:
        resp = client.get("/agent-commerce/mcp/", follow_redirects=True)
        assert resp.status_code in (200, 406)
        assert "mcp-session-id" in resp.headers
