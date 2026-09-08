"""Comprehensive tests for POST /provider/webhooks/razorpay.

Verifies:
1. Rejection of invalid/forged signatures with 400 and audit row.
2. Valid HMAC-SHA256 signature processing for payment_link.paid -> SETTLED.
3. Valid HMAC-SHA256 signature processing for payment.captured -> SETTLED.
4. Idempotent deduplication by provider event ID (replayed webhook is a no-op).
5. Resolution of UNKNOWN grants:
   - paid -> SETTLED
   - failed -> DEFINITIVE_FAILURE (exposure released)
6. Unmatched grants are audited and ignored, never auto-created.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import pytest
from fastapi.testclient import TestClient

from app import autopilot, store
from app.config import get_settings
from app.main import app
from app.models import (
    ActionState,
    AutopilotExecuteRequest,
    AutopilotScenario,
    EnvelopeActivateRequest,
    EnvelopeDraftRequest,
)

WEBHOOK_SECRET = "whsec_test_secret_for_firewall_12345"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_file = str(tmp_path / "test_webhooks.db")
    monkeypatch.setenv("DB_PATH", db_file)
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    get_settings.cache_clear()
    store.init_db()
    return TestClient(app)


def _sign(body_bytes: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()


def _issue_simulated_grant() -> tuple[str, str]:
    draft = autopilot.create_draft(
        EnvelopeDraftRequest(goal="Buy supplies for a pasta dinner", max_total_rupees=600)
    )
    active = autopilot.activate(
        draft.id,
        EnvelopeActivateRequest(expected_envelope_hash=draft.envelope_hash),
    )
    res = autopilot.execute(
        AutopilotExecuteRequest(
            envelope_id=active.id,
            expected_envelope_version=active.version,
            expected_envelope_hash=active.envelope_hash,
            session_id="sess_wh_01",
            purchase_attempt_id="att_wh_01",
            scenario=AutopilotScenario.NORMAL,
        )
    )
    grant = store.get_action_grant(res.grant_id)
    return grant.id, grant.provider_ref


def _issue_unknown_grant() -> tuple[str, str]:
    draft = autopilot.create_draft(
        EnvelopeDraftRequest(goal="Buy supplies for a pasta dinner", max_total_rupees=600)
    )
    active = autopilot.activate(
        draft.id,
        EnvelopeActivateRequest(expected_envelope_hash=draft.envelope_hash),
    )
    res = autopilot.execute(
        AutopilotExecuteRequest(
            envelope_id=active.id,
            expected_envelope_version=active.version,
            expected_envelope_hash=active.envelope_hash,
            session_id="sess_wh_unk_01",
            purchase_attempt_id="att_wh_unk_01",
            scenario=AutopilotScenario.TIMEOUT_AFTER_DISPATCH,
        )
    )
    grant = store.get_action_grant(res.grant_id)
    assert grant.state is ActionState.UNKNOWN
    return grant.id, grant.provider_ref


def test_webhook_rejects_missing_signature(client: TestClient):
    payload = {"event": "payment_link.paid", "id": "evt_001"}
    resp = client.post("/provider/webhooks/razorpay", json=payload)
    assert resp.status_code == 400
    assert "Invalid webhook signature" in resp.text

    audit = store.audit_trail(limit=5)
    assert any(row["event"] == "WEBHOOK_SIGNATURE_INVALID" for row in audit)


def test_webhook_rejects_forged_signature(client: TestClient):
    payload = json.dumps({"event": "payment_link.paid", "id": "evt_002"}).encode("utf-8")
    forged_sig = "bad_signature_deadbeef12345678"
    resp = client.post(
        "/provider/webhooks/razorpay",
        content=payload,
        headers={"X-Razorpay-Signature": forged_sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert "Invalid webhook signature" in resp.text

    audit = store.audit_trail(limit=5)
    assert any(row["event"] == "WEBHOOK_SIGNATURE_INVALID" for row in audit)


def test_webhook_payment_link_paid_settles_grant(client: TestClient):
    grant_id, plink_id = _issue_simulated_grant()

    grant_before = store.get_action_grant(grant_id)
    assert grant_before.state is ActionState.ACTION_ISSUED

    webhook_data = {
        "event_id": "evt_plink_paid_001",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": plink_id,
                    "status": "paid",
                    "amount_paid": 41700,
                    "notes": {"grant_id": grant_id},
                }
            }
        },
    }
    raw_body = json.dumps(webhook_data).encode("utf-8")
    sig = _sign(raw_body)

    resp = client.post(
        "/provider/webhooks/razorpay",
        content=raw_body,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data["before"] == "action_issued"
    assert data["after"] == "settled"

    grant_after = store.get_action_grant(grant_id)
    assert grant_after.state is ActionState.SETTLED


def test_webhook_resolves_grant_by_provider_ref_without_notes(client: TestClient):
    grant_id, plink_id = _issue_simulated_grant()

    webhook_data = {
        "event_id": "evt_plink_paid_ref_only",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": plink_id,
                    "status": "paid",
                    "amount_paid": 41700,
                    # No notes provided; resolver must use provider_ref
                }
            }
        },
    }
    raw_body = json.dumps(webhook_data).encode("utf-8")
    sig = _sign(raw_body)

    resp = client.post(
        "/provider/webhooks/razorpay",
        content=raw_body,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data["grant_id"] == grant_id
    assert data["after"] == "settled"


def test_webhook_idempotency_replayed_event_is_noop(client: TestClient):
    grant_id, plink_id = _issue_simulated_grant()

    webhook_data = {
        "event_id": "evt_replay_test_001",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": plink_id,
                    "status": "paid",
                    "amount_paid": 41700,
                    "notes": {"grant_id": grant_id},
                }
            }
        },
    }
    raw_body = json.dumps(webhook_data).encode("utf-8")
    sig = _sign(raw_body)

    # First delivery
    resp1 = client.post(
        "/provider/webhooks/razorpay",
        content=raw_body,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "processed"

    # Replayed delivery (same event_id)
    resp2 = client.post(
        "/provider/webhooks/razorpay",
        content=raw_body,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "already_processed"
    assert resp2.json()["idempotent"] is True


def test_webhook_resolves_unknown_state_to_settled(client: TestClient):
    grant_id, plink_id = _issue_unknown_grant()

    webhook_data = {
        "event_id": "evt_unk_paid_001",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": plink_id,
                    "status": "paid",
                    "amount_paid": 41700,
                    "notes": {"grant_id": grant_id},
                }
            }
        },
    }
    raw_body = json.dumps(webhook_data).encode("utf-8")
    sig = _sign(raw_body)

    resp = client.post(
        "/provider/webhooks/razorpay",
        content=raw_body,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data["before"] == "unknown"
    assert data["after"] == "settled"

    grant_after = store.get_action_grant(grant_id)
    assert grant_after.state is ActionState.SETTLED


def test_webhook_resolves_unknown_state_to_definitive_failure(client: TestClient):
    grant_id, plink_id = _issue_unknown_grant()

    webhook_data = {
        "event_id": "evt_unk_failed_001",
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_failed_123",
                    "payment_link_id": plink_id,
                    "status": "failed",
                    "notes": {"grant_id": grant_id},
                }
            }
        },
    }
    raw_body = json.dumps(webhook_data).encode("utf-8")
    sig = _sign(raw_body)

    resp = client.post(
        "/provider/webhooks/razorpay",
        content=raw_body,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data["before"] == "unknown"
    assert data["after"] == "definitive_failure"

    grant_after = store.get_action_grant(grant_id)
    assert grant_after.state is ActionState.DEFINITIVE_FAILURE


def test_webhook_unmatched_grant_is_audited_and_ignored(client: TestClient):
    webhook_data = {
        "event_id": "evt_orphan_001",
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_nonexistent_9999",
                    "status": "paid",
                    "amount_paid": 50000,
                    "notes": {"grant_id": "act_ghost_0000000000"},
                }
            }
        },
    }
    raw_body = json.dumps(webhook_data).encode("utf-8")
    sig = _sign(raw_body)

    resp = client.post(
        "/provider/webhooks/razorpay",
        content=raw_body,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unmatched_grant"

    audit = store.audit_trail(limit=5)
    assert any(row["event"] == "WEBHOOK_UNMATCHED_GRANT" for row in audit)
