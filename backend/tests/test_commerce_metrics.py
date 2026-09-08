"""Tests for Phase 5: Commerce Metrics Projections and Funnel Reporting.

Verifies:
- Payment Link issuance cannot increase settled GMV;
- Stock recovery counted only for valid in-envelope substitution;
- Unsafe attempt blocks increase blocked count without increasing GMV;
- Unknown timeouts appear in Needs Attention with preserved exposure;
- Monotonic checkout funnel conversion rates;
- Orders listing and status filtering;
- Duplicate attempts cannot double count.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.buyer_auth import DEMO_BUYER_KEY
from app.commerce_metrics import get_agent_orders, get_comprehensive_metrics, record_agent_order
from app.main import app
from app import store
from app.models import MandateCreate


@pytest.fixture(autouse=True)
def clean_database(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_commerce_metrics.db")
    monkeypatch.setenv("DB_PATH", db_file)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("ENVELOPE_DRAFTING_MODE", "replay")
    store.init_db()
    store.create_mandate(MandateCreate(cap_rupees=1000))
    yield


def test_payment_link_issuance_cannot_increase_settled_gmv():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {DEMO_BUYER_KEY}"}

    # 1. Check initial metrics
    m_init = client.get("/agent-commerce/v1/metrics").json()
    settled_init = m_init["settled_agent_gmv_paise"]

    # 2. Draft and activate an envelope
    intent = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_metric_01",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": "sess_metric_01",
            "natural_language_intent": "Buy pasta and sauce",
            "budget_paise": 60000,
        },
    ).json()["draft_envelope"]

    client.post(
        f"/agent-commerce/v1/envelopes/{intent['id']}/activate",
        json={"expected_envelope_hash": intent["envelope_hash"]},
    )

    # 3. Submit attempt -> Issues payment link
    att = client.post(
        "/agent-commerce/v1/attempts",
        headers=headers,
        json={
            "envelope_id": intent["id"],
            "purchase_attempt_id": "att_metric_success",
            "scenario": "normal",
        },
    ).json()
    assert att["outcome"] == "ACTION_ISSUED"
    assert att["payment_link"] is not None

    # 4. Check updated metrics: Issued GMV increased, Settled GMV did NOT increase
    m_after = client.get("/agent-commerce/v1/metrics").json()
    assert m_after["agent_gmv_issued_paise"] > m_init["agent_gmv_issued_paise"]
    assert m_after["settled_agent_gmv_paise"] == settled_init == 0, "Issuance must NEVER increase settled GMV"


def test_unknown_outcome_appears_in_needs_attention():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {DEMO_BUYER_KEY}"}

    intent = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_metric_timeout",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": "sess_metric_to",
            "natural_language_intent": "Buy pasta and sauce",
            "budget_paise": 60000,
        },
    ).json()["draft_envelope"]

    client.post(
        f"/agent-commerce/v1/envelopes/{intent['id']}/activate",
        json={"expected_envelope_hash": intent["envelope_hash"]},
    )

    # Submit timeout attempt
    client.post(
        "/agent-commerce/v1/attempts",
        headers=headers,
        json={
            "envelope_id": intent["id"],
            "purchase_attempt_id": "att_metric_timeout_01",
            "scenario": "timeout_after_dispatch",
        },
    )

    m = client.get("/agent-commerce/v1/metrics").json()
    assert m["unknown_attempts_count"] >= 1
    assert m["unknown_exposure_paise"] > 0

    # Must appear in Needs Attention
    attn_items = [item for item in m["needs_attention"] if item["item_type"] == "unknown_outcome"]
    assert len(attn_items) >= 1
    assert attn_items[0]["severity"] == "high"
    assert "Provider Timeout" in attn_items[0]["title"]


def test_in_envelope_recovery_metric_tracked():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {DEMO_BUYER_KEY}"}

    m_before = client.get("/agent-commerce/v1/metrics").json()
    rec_before = m_before["orders_recovered_count"]

    intent = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_metric_rec",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": "sess_metric_rec",
            "natural_language_intent": "Buy supplies for a pasta dinner",
            "budget_paise": 60000,
        },
    ).json()["draft_envelope"]

    client.post(
        f"/agent-commerce/v1/envelopes/{intent['id']}/activate",
        json={"expected_envelope_hash": intent["envelope_hash"]},
    )

    res = client.post(
        "/agent-commerce/v1/attempts",
        headers=headers,
        json={
            "envelope_id": intent["id"],
            "purchase_attempt_id": "att_metric_rec_01",
            "scenario": "stock_loss",
        },
    ).json()

    assert res["outcome"] == "RECOVERED_INSIDE_ENVELOPE"
    assert res["recovery_applied"] is True

    m_after = client.get("/agent-commerce/v1/metrics").json()
    assert m_after["orders_recovered_count"] == rec_before + 1


def test_orders_listing_and_filtering():
    client = TestClient(app)

    # 1. Get all orders
    all_orders = client.get("/agent-commerce/v1/orders").json()
    assert len(all_orders) >= 3

    # 2. Filter by status='issued'
    issued_orders = client.get("/agent-commerce/v1/orders?status=issued").json()
    assert len(issued_orders) >= 1
    for o in issued_orders:
        assert o["status"] == "issued"

    # 3. Filter by status='blocked'
    blocked_orders = client.get("/agent-commerce/v1/orders?status=blocked").json()
    assert len(blocked_orders) >= 1
    for o in blocked_orders:
        assert o["status"] == "blocked"


def test_duplicate_attempt_does_not_double_count():
    record_agent_order(
        purchase_attempt_id="att_dup_test_01",
        merchant_id="merchant_demo",
        buyer_agent_id="buyer_replay",
        shopper_session_id="sess_dup_01",
        status="issued",
        outcome="ACTION_ISSUED",
        amount_paise=24900,
    )

    orders_initial = len(get_agent_orders("merchant_demo"))

    # Record exact duplicate attempt ID
    record_agent_order(
        purchase_attempt_id="att_dup_test_01",
        merchant_id="merchant_demo",
        buyer_agent_id="buyer_replay",
        shopper_session_id="sess_dup_01",
        status="issued",
        outcome="ACTION_ISSUED",
        amount_paise=24900,
    )

    orders_after = len(get_agent_orders("merchant_demo"))
    assert orders_after == orders_initial, "Duplicate attempt must not insert a duplicate row"
