"""Tests for Outbound Refund Gateway Endpoints (/agent-commerce/v1/refunds/*).

Verifies:
1. GET /refunds/policy returns hash-bound merchant policy;
2. POST /refunds/evaluate returns deterministic decisions and repair proposals;
3. POST /refunds/execute dispatches allowed refunds and auto-repairs bounded complaints;
4. Double-refunds and escalated disputes fail closed before any provider call.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import store


@pytest.fixture(autouse=True)
def init_test_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test_refund_api.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    store.init_db()


def test_get_refund_policy():
    client = TestClient(app)
    resp = client.get("/agent-commerce/v1/refunds/policy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["merchant_id"] == "merchant_freshbasket"
    assert data["max_refund_paise"] == 50_000
    assert data["policy_hash"] != ""


def test_evaluate_refund_allowed():
    client = TestClient(app)
    payload = {
        "payment_id": "pay_test_01",
        "amount_paise": 20_000,
        "reason": "Customer damaged item",
        "original_amount_paise": 80_000,
        "already_refunded_paise": 0,
        "order_age_days": 2,
    }
    resp = client.post("/agent-commerce/v1/refunds/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is True
    assert data["code"] == "ALLOW_REFUND"
    assert data["repaired_proposal"] is None


def test_evaluate_refund_repairable():
    client = TestClient(app)
    # Order of 80,000 paise with 60,000 already refunded. Agent asks for 40,000.
    payload = {
        "payment_id": "pay_test_02",
        "amount_paise": 40_000,
        "reason": "Missing components",
        "original_amount_paise": 80_000,
        "already_refunded_paise": 60_000,
        "order_age_days": 5,
    }
    resp = client.post("/agent-commerce/v1/refunds/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is False
    assert data["code"] == "REPAIR_REFUND"
    assert data["repaired_proposal"] is not None
    assert data["repaired_proposal"]["amount_paise"] == 20_000


def test_evaluate_refund_escalate():
    client = TestClient(app)
    payload = {
        "payment_id": "pay_test_03",
        "amount_paise": 10_000,
        "reason": "Suspected fraud on customer account",
        "original_amount_paise": 80_000,
        "already_refunded_paise": 0,
        "order_age_days": 2,
    }
    resp = client.post("/agent-commerce/v1/refunds/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is False
    assert data["code"] == "ESCALATE_REFUND"


def test_execute_refund_success_and_audit():
    client = TestClient(app)
    payload = {
        "payment_id": "pay_test_exec_01",
        "amount_paise": 15_000,
        "reason": "Minor defect",
        "attempt_id": "att_rfnd_exec_01",
        "original_amount_paise": 80_000,
    }
    resp = client.post("/agent-commerce/v1/refunds/execute", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is True
    assert data["outcome"] == "ACTION_ISSUED"
    assert data["refund_id"].startswith("rfnd_")
    assert data["razorpay_action_called"] is True


def test_execute_refund_auto_repair():
    client = TestClient(app)
    payload = {
        "payment_id": "pay_test_exec_02",
        "amount_paise": 35_000,
        "reason": "Delivery delay compensation",
        "attempt_id": "att_rfnd_exec_02",
        "auto_repair": True,
        "original_amount_paise": 80_000,
        "already_refunded_paise": 60_000,  # only 20,000 left
    }
    resp = client.post("/agent-commerce/v1/refunds/execute", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is True
    assert data["outcome"] == "ACTION_ISSUED"
    assert data["amount_paise"] == 20_000
    assert data["repaired"] is True


def test_execute_refund_double_refund_fails_closed():
    client = TestClient(app)
    payload = {
        "payment_id": "pay_test_exec_03",
        "amount_paise": 10_000,
        "reason": "Duplicate claim",
        "attempt_id": "att_rfnd_exec_03",
        "original_amount_paise": 80_000,
        "already_refunded_paise": 80_000,  # 0 left!
    }
    resp = client.post("/agent-commerce/v1/refunds/execute", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is False
    assert data["outcome"] == "STOPPED_BEFORE_RAZORPAY"
    assert data["code"] == "BLOCK_REFUND"
    assert data["razorpay_action_called"] is False
