"""HTTP tests for the Agent Commerce Gateway API surface (/agent-commerce/v1)."""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.models import MandateCreate
from app import store


@pytest.fixture(autouse=True)
def clean_database(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_commerce.db")
    monkeypatch.setenv("DB_PATH", db_file)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("ENVELOPE_DRAFTING_MODE", "replay")
    store.init_db()
    store.create_mandate(MandateCreate(cap_rupees=1000))
    yield


def test_merchant_capabilities_endpoint():
    client = TestClient(app)
    resp = client.get("/agent-commerce/v1/merchant")
    assert resp.status_code == 200
    data = resp.json()
    assert data["merchant_id"] == "merchant_freshbasket"
    assert data["display_name"] == "FreshBasket for Business"
    assert data["currency"] == "INR"
    assert "create_payment_link" in data["capabilities"]
    assert data["action_name"] == "create_payment_link"
    assert "api_key" not in data
    assert "secret" not in data


def test_catalog_search_endpoint():
    client = TestClient(app)
    resp = client.get("/agent-commerce/v1/catalog/search?q=pasta&limit=3")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) > 0
    first = items[0]
    assert "sku" in first
    assert "price_paise" in first
    assert isinstance(first["price_paise"], int)
    assert first["price_paise"] > 0
    assert first["in_stock"] is True


def test_intent_creation_is_proposal_only():
    client = TestClient(app)
    payload = {
        "agent_request_id": "req_test_001",
        "buyer_agent_id": "buyer_replay",
        "shopper_session_id": "sess_test",
        "natural_language_intent": "Buy supplies for a pasta dinner",
        "budget_paise": 60000,
        "merchant_id": "merchant_demo",
    }
    resp = client.post("/agent-commerce/v1/intents", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_request_id"] == "req_test_001"
    assert data["provider_action_called"] is False
    assert data["draft_envelope"] is not None
    assert data["draft_envelope"]["status"] == "draft"
    assert data["draft_envelope"]["max_total_paise"] == 60000
    assert len(data["draft_envelope"]["slots"]) >= 1


def test_quote_endpoint_computes_server_prices():
    client = TestClient(app)
    payload = {
        "merchant_id": "merchant_demo",
        "fulfillment_profile_id": "dest_demo",
        "items": [
            {"sku": "SKU-PAS-002", "quantity": 2},
            {"sku": "SKU-SAU-001", "quantity": 1},
        ],
    }
    resp = client.post("/agent-commerce/v1/quotes", json=payload)
    assert resp.status_code == 200
    quote = resp.json()
    assert quote["merchant_id"] == "merchant_demo"
    assert quote["currency"] == "INR"
    assert quote["total_paise"] == (8900 * 2) + 24900
    assert len(quote["quote_hash"]) == 64


def test_unactivated_envelope_cannot_transact():
    client = TestClient(app)
    # 1. Draft intent
    intent_resp = client.post(
        "/agent-commerce/v1/intents",
        json={
            "agent_request_id": "req_unactivated",
            "natural_language_intent": "Buy supplies for a pasta dinner",
            "budget_paise": 60000,
        },
    )
    envelope = intent_resp.json()["draft_envelope"]
    assert envelope["status"] == "draft"

    # 2. Propose attempt directly on unactivated envelope
    attempt_resp = client.post(
        "/agent-commerce/v1/attempts",
        json={
            "envelope_id": envelope["id"],
            "purchase_attempt_id": "att_premature_001",
            "scenario": "normal",
        },
    )
    assert attempt_resp.status_code == 200
    data = attempt_resp.json()
    assert data["allowed"] is False
    assert data["outcome"] == "STOPPED_BEFORE_RAZORPAY"
    assert data["razorpay_action_called"] is False
    assert data["payment_link"] is None
    assert data["code"] == "BLOCK_ENVELOPE_DRAFT"


def test_full_replay_buyer_loop_issues_payment_link():
    client = TestClient(app)

    # 1. Understand / Draft Intent
    intent_resp = client.post(
        "/agent-commerce/v1/intents",
        json={
            "agent_request_id": "req_full_001",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": "sess_full",
            "natural_language_intent": "Buy supplies for a pasta dinner",
            "budget_paise": 60000,
        },
    )
    assert intent_resp.status_code == 200
    draft = intent_resp.json()["draft_envelope"]

    # 2. Authorize: Explicit human activation
    act_resp = client.post(
        f"/agent-commerce/v1/envelopes/{draft['id']}/activate",
        json={"expected_envelope_hash": draft["envelope_hash"]},
    )
    assert act_resp.status_code == 200
    active_env = act_resp.json()
    assert active_env["status"] == "active"

    # 3. Execute Attempt through Gateway
    attempt_resp = client.post(
        "/agent-commerce/v1/attempts",
        json={
            "envelope_id": active_env["id"],
            "purchase_attempt_id": "att_full_success_001",
            "scenario": "normal",
        },
    )
    assert attempt_resp.status_code == 200
    res = attempt_resp.json()

    assert res["allowed"] is True
    assert res["outcome"] == "ACTION_ISSUED"
    assert res["razorpay_action_called"] is True
    assert res["payment_link"] and res["payment_link"].startswith("https://rzp.io/")
    assert res["grant_id"] is not None
    assert res["receipt"] is not None
    assert len(res["stages"]) == 4
    for stage in res["stages"]:
        assert stage["status"] == "completed"

    # 4. Query attempt by ID
    get_resp = client.get(f"/agent-commerce/v1/attempts/{res['attempt_id']}")
    assert get_resp.status_code == 200
    saved = get_resp.json()
    assert saved["attempt_id"] == "att_full_success_001"
    assert saved["payment_link"] == res["payment_link"]


def test_stock_loss_recovery_inside_envelope():
    client = TestClient(app)

    # 1. Draft
    draft = client.post(
        "/agent-commerce/v1/intents",
        json={
            "agent_request_id": "req_stock_001",
            "natural_language_intent": "Buy supplies for a pasta dinner",
            "budget_paise": 60000,
        },
    ).json()["draft_envelope"]

    # 2. Activate
    active_env = client.post(
        f"/agent-commerce/v1/envelopes/{draft['id']}/activate",
        json={"expected_envelope_hash": draft["envelope_hash"]},
    ).json()

    # 3. Execute with stock_loss scenario
    attempt = client.post(
        "/agent-commerce/v1/attempts",
        json={
            "envelope_id": active_env["id"],
            "purchase_attempt_id": "att_recovery_001",
            "scenario": "stock_loss",
        },
    ).json()

    assert attempt["allowed"] is True
    assert attempt["outcome"] == "RECOVERED_INSIDE_ENVELOPE"
    assert attempt["recovery_applied"] is True
    assert attempt["razorpay_action_called"] is True
    assert attempt["payment_link"].startswith("https://rzp.io/")


def test_merchant_drift_refused_with_policy_delta():
    client = TestClient(app)

    # 1. Draft
    draft = client.post(
        "/agent-commerce/v1/intents",
        json={
            "agent_request_id": "req_drift_001",
            "natural_language_intent": "Buy supplies for a pasta dinner",
            "budget_paise": 60000,
        },
    ).json()["draft_envelope"]

    # 2. Activate
    active_env = client.post(
        f"/agent-commerce/v1/envelopes/{draft['id']}/activate",
        json={"expected_envelope_hash": draft["envelope_hash"]},
    ).json()

    # 3. Execute with merchant_drift
    attempt = client.post(
        "/agent-commerce/v1/attempts",
        json={
            "envelope_id": active_env["id"],
            "purchase_attempt_id": "att_drift_001",
            "scenario": "merchant_drift",
        },
    ).json()

    assert attempt["allowed"] is False
    assert attempt["outcome"] == "POLICY_DELTA_REQUIRED"
    assert attempt["razorpay_action_called"] is False
    assert attempt["payment_link"] is None
    assert len(attempt["deltas"]) > 0
    delta = attempt["deltas"][0]
    assert delta["field"] == "merchant_id"
    assert delta["recovery"] == "fresh_approval"


def test_commerce_metrics_endpoint():
    client = TestClient(app)
    resp = client.get("/agent-commerce/v1/metrics")
    assert resp.status_code == 200
    metrics = resp.json()
    assert "agent_gmv_issued_paise" in metrics
    assert "settled_agent_gmv_paise" in metrics
    assert "evidence_mode" in metrics
    assert metrics["evidence_mode"] in ("simulated", "razorpay_test")


def test_http_attempt_with_quote_binding():
    import time
    client = TestClient(app)

    # 1. Draft
    draft = client.post(
        "/agent-commerce/v1/intents",
        json={
            "agent_request_id": "req_quote_http_01",
            "natural_language_intent": "Buy supplies for a pasta dinner",
            "budget_paise": 60000,
        },
    ).json()["draft_envelope"]

    # 2. Activate
    active_env = client.post(
        f"/agent-commerce/v1/envelopes/{draft['id']}/activate",
        json={"expected_envelope_hash": draft["envelope_hash"]},
    ).json()

    # 3. Request Quote
    quote_resp = client.post(
        "/agent-commerce/v1/quotes",
        json={
            "merchant_id": "merchant_demo",
            "fulfillment_profile_id": "dest_demo",
            "items": [{"sku": "SKU-PAS-002", "quantity": 1}],
        },
    )
    assert quote_resp.status_code == 200
    quote_id = quote_resp.json()["quote_id"]

    # 4. Attempt with valid quote succeeds
    att_resp = client.post(
        "/agent-commerce/v1/attempts",
        json={
            "envelope_id": active_env["id"],
            "quote_id": quote_id,
            "purchase_attempt_id": "att_quote_success_01",
        },
    )
    assert att_resp.status_code == 200
    assert att_resp.json()["allowed"] is True

    # 5. Draft and activate a second envelope to attempt replay with same quote
    draft2 = client.post(
        "/agent-commerce/v1/intents",
        json={
            "agent_request_id": "req_quote_http_02",
            "natural_language_intent": "Buy supplies for a pasta dinner 2",
            "budget_paise": 60000,
        },
    ).json()["draft_envelope"]
    active_env2 = client.post(
        f"/agent-commerce/v1/envelopes/{draft2['id']}/activate",
        json={"expected_envelope_hash": draft2["envelope_hash"]},
    ).json()

    # Attempt with already checked-out quote fails with 409
    att_dup = client.post(
        "/agent-commerce/v1/attempts",
        json={
            "envelope_id": active_env2["id"],
            "quote_id": quote_id,
            "purchase_attempt_id": "att_quote_dup_01",
        },
    )
    assert att_dup.status_code == 409
    assert "already been checked out" in att_dup.json()["detail"]


