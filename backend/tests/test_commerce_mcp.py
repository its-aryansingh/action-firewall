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

import time
import pytest

from app.approval_tokens import redeem_approval_token
from app.commerce_mcp import _quote_owner
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
    assert res["merchant_id"] in ("merchant_freshbasket", "merchant_demo")
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
        intent_id=draft["intent_id"],
        quote_id="q_test_unact",
        attempt_id="att_mcp_unact",
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

    # 3. Request quote
    quote = request_quote(
        items=[
            {"sku": "SKU-PAS-002", "quantity": 1},
            {"sku": "SKU-SAU-001", "quantity": 1},
        ]
    )

    # 4. Request checkout via MCP (without scenario parameter)
    res = request_checkout(
        intent_id=draft["intent_id"],
        quote_id=quote["quote_id"],
        attempt_id="att_mcp_success_01",
    )
    assert res["allowed"] is True
    assert res["outcome"] == "ACTION_ISSUED"
    assert res["payment_link"] and "/simulated/payment-link/" in res["payment_link"]
    assert res["grant_id"] is not None
    assert res["razorpay_action_called"] is True

    # 5. Polling status returns recorded outcome
    stat = get_checkout_status("att_mcp_success_01")
    assert stat["status"] == "issued"
    assert stat["payment_link"] == res["payment_link"]


def test_request_checkout_rejects_extra_fields():
    """Verify scenario is deleted from MCP tool schema and extra fields fail closed."""
    tool = next(t for t in mcp_server._tool_manager.list_tools() if t.name == "request_checkout")
    props = tool.parameters.get("properties", {})
    assert "scenario" not in props, "scenario must not be an MCP tool parameter!"
    assert set(props.keys()) == {"intent_id", "quote_id", "attempt_id"}

    # Calling with unexpected argument raises TypeError
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        request_checkout(
            intent_id="env_test",
            quote_id="q_test",
            attempt_id="att_test",
            scenario="price_drift",  # type: ignore
        )


def test_demo_scenario_loopback_and_security(monkeypatch):
    """Verify /demo/scenario route is loopback-only and DEMO_MODE=true-only."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app import demo_scenario

    demo_scenario.reset_active_scenario()

    # 1. Loopback caller in DEMO_MODE=true succeeds
    with TestClient(app, base_url="http://localhost") as client:
        r = client.post("/demo/scenario", json={"scenario": "price_drift"})
        assert r.status_code == 200
        assert r.json()["scenario"] == "price_drift"
        assert demo_scenario.get_active_scenario().value == "price_drift"

        # GET confirms active scenario
        r_get = client.get("/demo/scenario")
        assert r_get.status_code == 200
        assert r_get.json()["scenario"] == "price_drift"

        # Invalid scenario returns 422
        r_inv = client.post("/demo/scenario", json={"scenario": "malicious_scenario"})
        assert r_inv.status_code == 422

    # 2. Non-loopback caller without merchant-admin auth returns 403
    with TestClient(app, client=("198.51.100.25", 43210)) as remote_client:
        r_remote = remote_client.post("/demo/scenario", json={"scenario": "normal"})
        assert r_remote.status_code == 403
        assert "restricted to loopback" in r_remote.json()["detail"]

    # 3. DEMO_MODE=false returns 403 even for loopback
    from app.config import get_settings
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "false")
    get_settings.cache_clear()
    try:
        with TestClient(app, base_url="http://localhost") as client:
            r_blocked = client.post("/demo/scenario", json={"scenario": "normal"})
            assert r_blocked.status_code == 403
            assert "only permitted when DEMO_MODE=true" in r_blocked.json()["detail"]
    finally:
        monkeypatch.setenv("DEMO_MODE", "true")
        monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
        get_settings.cache_clear()

    demo_scenario.reset_active_scenario()


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


def test_mcp_tools_route_locked_and_returns_northbound_allowlist():
    """Verify GET /mcp/tools requires merchant-admin and returns northbound allowlist."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.buyer_auth import MERCHANT_ADMIN_KEY

    with TestClient(app, base_url="http://localhost") as client:
        # 1. Unauthenticated returns 401
        r_unauth = client.get("/mcp/tools")
        assert r_unauth.status_code == 401
        assert "Merchant admin authentication required" in r_unauth.json()["detail"]

        # 2. Invalid admin token returns 403
        r_bad = client.get("/mcp/tools", headers={"Authorization": "Bearer invalid_key"})
        assert r_bad.status_code == 403
        assert "Invalid merchant admin credentials" in r_bad.json()["detail"]

        # 3. Authenticated returns northbound allowlist (6 customer tools, 0 raw payment tools)
        r_auth = client.get("/mcp/tools", headers={"Authorization": f"Bearer {MERCHANT_ADMIN_KEY}"})
        assert r_auth.status_code == 200
        data = r_auth.json()
        assert data["surface"] == "northbound_buyer_allowlist"
        assert set(data["tool_names"]) == {
            "discover_storefront",
            "search_catalog",
            "draft_purchase",
            "request_quote",
            "request_checkout",
            "get_checkout_status",
        }
        assert not any(
            bad in data["tool_names"]
            for bad in [
                "create_payment_link",
                "capture_payment",
                "refund_payment",
                "activate_envelope",
                "call_razorpay_tool",
            ]
        )


def test_southbound_tools_route_requires_merchant_admin():
    """Verify southbound provider route is restricted to merchant-admin."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.buyer_auth import MERCHANT_ADMIN_KEY

    with TestClient(app, base_url="http://localhost") as client:
        # 1. Unauthenticated returns 401
        r_unauth = client.get("/mcp/southbound-tools")
        assert r_unauth.status_code == 401

        # 2. Authenticated returns southbound tools
        r_auth = client.get("/mcp/southbound-tools", headers={"Authorization": f"Bearer {MERCHANT_ADMIN_KEY}"})
        assert r_auth.status_code == 200
        data = r_auth.json()
        assert data["surface"] == "southbound_provider_surface"
        assert "never exposed to AI buyers" in data["notice"]
        assert any(t.get("name") == "create_payment_link" for t in data["tools"])


def test_quote_persisted_in_commerce_quotes():
    """Verify request_quote persists row to commerce_quotes table with canonical JSON and hash."""
    items = [
        {"sku": "SKU-PAS-002", "quantity": 2},
        {"sku": "SKU-SAU-001", "quantity": 1},
    ]
    res = request_quote(items=items)
    quote_id = res["quote_id"]
    row = store.get_commerce_quote(quote_id)
    assert row is not None
    assert row["id"] == quote_id
    assert row["merchant_id"] in ("merchant_freshbasket", "merchant_demo")
    assert row["buyer_agent_id"] == _quote_owner(), (
        "the quote must be attributed to whoever presented the credential, and "
        "request_checkout must read back that same identity"
    )
    assert row["total_paise"] == (8900 * 2) + 24900
    assert row["quote_hash"] == res["quote_hash"]
    assert len(row["cart_hash"]) == 64
    assert row["checked_out_at"] is None
    assert row["checked_out_attempt_id"] is None


def test_quote_rejected_when_expired():
    """Verify expired quote is rejected before checkout dispatch (QUOTE_EXPIRED)."""
    draft = draft_purchase(intent="Buy supplies for a pasta dinner", agent_request_id="req_exp", budget_paise=60000)
    token = draft["approval_url"].replace("/approve/", "")
    redeem_approval_token(token)

    quote = request_quote(items=[{"sku": "SKU-PAS-002", "quantity": 1}])
    quote_id = quote["quote_id"]

    # Manually expire the quote in DB
    with store._conn() as cx:
        cx.execute("UPDATE commerce_quotes SET valid_until = ? WHERE id = ?", (time.time() - 10, quote_id))

    res = request_checkout(intent_id=draft["intent_id"], quote_id=quote_id, attempt_id="att_exp_01")
    assert res["allowed"] is False
    assert res["outcome"] == "STOPPED_BEFORE_RAZORPAY"
    assert res["code"] == "QUOTE_EXPIRED"
    assert res["razorpay_action_called"] is False
    assert res["payment_link"] is None


def test_quote_rejected_for_cross_buyer():
    """Verify quote owned by another buyer is rejected with NOT FOUND (never 403, preventing enumeration)."""
    draft = draft_purchase(intent="Buy supplies for a pasta dinner", agent_request_id="req_cross", budget_paise=60000)
    token = draft["approval_url"].replace("/approve/", "")
    redeem_approval_token(token)

    quote = request_quote(items=[{"sku": "SKU-PAS-002", "quantity": 1}])
    quote_id = quote["quote_id"]

    # Alter buyer_agent_id to another buyer
    with store._conn() as cx:
        cx.execute("UPDATE commerce_quotes SET buyer_agent_id = ? WHERE id = ?", ("buyer_other_agent", quote_id))

    res = request_checkout(intent_id=draft["intent_id"], quote_id=quote_id, attempt_id="att_cross_01")
    assert res["allowed"] is False
    assert res["outcome"] == "STOPPED_BEFORE_RAZORPAY"
    assert res["code"] == "QUOTE_NOT_FOUND"
    assert res["razorpay_action_called"] is False


def test_quote_rejected_on_changed_catalog_revision():
    """Verify changed catalog_revision returns REQUOTE_REQUIRED."""
    draft = draft_purchase(intent="Buy supplies for a pasta dinner", agent_request_id="req_rev", budget_paise=60000)
    token = draft["approval_url"].replace("/approve/", "")
    redeem_approval_token(token)

    quote = request_quote(items=[{"sku": "SKU-PAS-002", "quantity": 1}])
    quote_id = quote["quote_id"]

    # Alter catalog_revision to stale
    with store._conn() as cx:
        cx.execute("UPDATE commerce_quotes SET catalog_revision = ? WHERE id = ?", ("rev_2025_stale", quote_id))

    res = request_checkout(intent_id=draft["intent_id"], quote_id=quote_id, attempt_id="att_rev_01")
    assert res["allowed"] is False
    assert res["outcome"] == "STOPPED_BEFORE_RAZORPAY"
    assert res["code"] == "REQUOTE_REQUIRED"
    assert res["razorpay_action_called"] is False


def test_quote_cannot_be_checked_out_twice():
    """Verify same quote cannot be checked out twice (QUOTE_ALREADY_CHECKED_OUT)."""
    draft1 = draft_purchase(intent="Buy supplies for a pasta dinner 1", agent_request_id="req_double_1", budget_paise=60000)
    token1 = draft1["approval_url"].replace("/approve/", "")
    redeem_approval_token(token1)

    quote = request_quote(items=[{"sku": "SKU-PAS-002", "quantity": 1}])
    quote_id = quote["quote_id"]

    # First checkout succeeds
    res1 = request_checkout(intent_id=draft1["intent_id"], quote_id=quote_id, attempt_id="att_first_01")
    assert res1["allowed"] is True
    assert res1["outcome"] == "ACTION_ISSUED"

    # Second active envelope tries to check out with the already-consumed quote
    draft2 = draft_purchase(intent="Buy supplies for a pasta dinner 2", agent_request_id="req_double_2", budget_paise=60000)
    token2 = draft2["approval_url"].replace("/approve/", "")
    redeem_approval_token(token2)

    res2 = request_checkout(intent_id=draft2["intent_id"], quote_id=quote_id, attempt_id="att_second_01")
    assert res2["allowed"] is False
    assert res2["outcome"] == "STOPPED_BEFORE_RAZORPAY"
    assert res2["code"] == "QUOTE_ALREADY_CHECKED_OUT"
    assert res2["razorpay_action_called"] is False


def test_quote_authoritative_total_paise_used():
    """Verify the quote row total_paise is authoritative and cannot be manipulated by caller."""
    draft = draft_purchase(intent="Buy supplies for a pasta dinner", agent_request_id="req_auth_total", budget_paise=60000)
    token = draft["approval_url"].replace("/approve/", "")
    redeem_approval_token(token)

    quote = request_quote(items=[{"sku": "SKU-PAS-002", "quantity": 1}])
    quote_id = quote["quote_id"]

    row = store.get_commerce_quote(quote_id)
    assert row["total_paise"] == 8900


def test_get_checkout_status_ownership_isolation():
    """Verify buyer B cannot read buyer A's attempt and receives not_found (preventing enumeration)."""
    from app.commerce_metrics import record_agent_order

    # 1. Record an order owned by a different buyer agent
    record_agent_order(
        purchase_attempt_id="att_foreign_buyer_01",
        merchant_id="merchant_demo",
        buyer_agent_id="buyer_other",
        shopper_session_id="sess_foreign",
        status="issued",
        outcome="ACTION_ISSUED",
        amount_paise=12300,
        envelope_id="env_foreign",
    )

    # 2. MCP status check (scoped to the resolved caller) returns not_found
    stat_foreign = get_checkout_status("att_foreign_buyer_01")
    assert stat_foreign["status"] == "not_found"

    # 3. Record an order owned by the resolved caller
    record_agent_order(
        purchase_attempt_id="att_mcp_owned_01",
        merchant_id="merchant_demo",
        buyer_agent_id=_quote_owner(),
        shopper_session_id="sess_mcp",
        status="issued",
        outcome="ACTION_ISSUED",
        amount_paise=45600,
        envelope_id="env_mcp",
        payment_link="https://rzp.io/l/test_owned",
    )

    # 4. MCP status check returns the order
    stat_owned = get_checkout_status("att_mcp_owned_01")
    assert stat_owned["status"] == "issued"
    assert stat_owned["attempt_id"] == "att_mcp_owned_01"
    assert stat_owned["payment_link"] == "https://rzp.io/l/test_owned"


def test_get_checkout_status_polling_never_redispatches():
    """Verify polling get_checkout_status multiple times is purely read-only and never re-dispatches."""
    from app.commerce_metrics import record_agent_order

    record_agent_order(
        purchase_attempt_id="att_poll_01",
        merchant_id="merchant_demo",
        buyer_agent_id=_quote_owner(),
        shopper_session_id="sess_poll",
        status="issued",
        outcome="ACTION_ISSUED",
        amount_paise=8900,
        envelope_id="env_poll",
        grant_id="grant_poll_01",
    )

    # Poll twice
    r1 = get_checkout_status("att_poll_01")
    r2 = get_checkout_status("att_poll_01")

    assert r1 == r2
    assert r1["status"] == "issued"
    assert r1["grant_id"] == "grant_poll_01"


def test_mcp_concurrent_checkout_returns_structured_conflict():
    """Verify concurrent checkout attempts on the same quote/envelope safely serialize or return structured conflict."""
    import concurrent.futures

    draft = draft_purchase(
        intent="Buy supplies for a pasta dinner concurrent",
        agent_request_id="req_mcp_conc",
        budget_paise=60000,
    )
    token = draft["approval_url"].replace("/approve/", "")
    redeem_approval_token(token)

    quote = request_quote(items=[{"sku": "SKU-PAS-002", "quantity": 1}])
    quote_id = quote["quote_id"]

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(
            request_checkout,
            intent_id=draft["intent_id"],
            quote_id=quote_id,
            attempt_id="att_mcp_conc_01",
        )
        f2 = executor.submit(
            request_checkout,
            intent_id=draft["intent_id"],
            quote_id=quote_id,
            attempt_id="att_mcp_conc_02",
        )
        for f in concurrent.futures.as_completed([f1, f2]):
            results.append(f.result())

    # Exactly one must succeed with ACTION_ISSUED; the other must fail closed
    outcomes = [r["outcome"] for r in results]
    assert "ACTION_ISSUED" in outcomes
    success_count = sum(1 for r in results if r.get("allowed") is True)
    assert success_count == 1, f"Expected exactly 1 successful checkout, got: {results}"
    failed = next(r for r in results if not r.get("allowed"))
    assert failed["outcome"] in ("STOPPED_BEFORE_RAZORPAY", "READY_FOR_CHECKOUT")
    assert failed["razorpay_action_called"] is False


def test_request_checkout_with_revoked_key_fails_closed(monkeypatch):
    """Verify an invalid or revoked bearer token calling request_checkout fails closed with structured refusal."""
    from app import buyer_auth
    import app.commerce_mcp as cmcp

    revoked_key = "af_test_revoked_key_mcp"
    buyer_auth.register_buyer_key(revoked_key, "buyer_agent_revoked")
    buyer_auth.revoke_buyer_key(revoked_key)

    monkeypatch.setattr(
        cmcp,
        "_bearer_from_request_context",
        lambda: f"Bearer {revoked_key}",
    )
    try:
        res = request_checkout(
            intent_id="env_test_revoked",
            quote_id="q_test_revoked",
            attempt_id="att_test_revoked",
        )
        assert res["allowed"] is False
        assert res["outcome"] == "STOPPED_BEFORE_RAZORPAY"
        assert res["code"] == "UNAUTHENTICATED_BUYER_AGENT"
        assert res["razorpay_action_called"] is False
        assert res["payment_link"] is None
    finally:
        buyer_auth.reset_buyer_keys()
