"""Public HTTP contract smoke and refusal test suite for the judge-facing product path."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import store
from app.config import get_settings
from app.main import app
from app.mcp_client import reset_simulated_provider


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "autopilot-http.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ACTION_RECEIPT_SECRET", "")
    get_settings.cache_clear()
    reset_simulated_provider()
    store.init_db()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def create_draft(client: TestClient, goal: str = "Buy supplies for a pasta dinner", rupees: int = 600) -> dict:
    res = client.post("/envelopes/draft", json={"goal": goal, "max_total_rupees": rupees})
    assert res.status_code == 200
    return res.json()


def activate_envelope(client: TestClient, draft: dict) -> dict:
    res = client.post(f"/envelopes/{draft['id']}/activate", json={"expected_envelope_hash": draft["envelope_hash"]})
    assert res.status_code == 200
    return res.json()


def test_http_draft_activate_execute_and_verify_receipt(client: TestClient):
    draft = create_draft(client, "Buy supplies for a pasta dinner", 600)
    active = activate_envelope(client, draft)
    assert active["status"] == "active"

    execution_response = client.post(
        "/autopilot/execute",
        json={
            "envelope_id": active["id"],
            "expected_envelope_version": active["version"],
            "expected_envelope_hash": active["envelope_hash"],
            "session_id": "http-demo-session",
            "purchase_attempt_id": "http-demo-attempt",
            "scenario": "stock_loss",
        },
    )
    assert execution_response.status_code == 200
    execution = execution_response.json()
    assert execution["recovery_applied"] is True
    assert execution["action_status"] == "action_issued"
    assert execution["payment_link"].startswith("https://rzp.io/")

    receipt_response = client.get(f"/receipts/{execution['grant_id']}")
    assert receipt_response.status_code == 200
    receipt = receipt_response.json()
    verification = client.post(
        f"/receipts/{execution['grant_id']}/verify",
        json=receipt,
    )
    assert verification.status_code == 200
    assert verification.json()["valid"] is True

    metrics = client.get("/metrics").json()
    assert metrics["envelopes_activated"] == 1
    assert metrics["in_envelope_recoveries"] == 1


def test_http_get_unknown_envelope_returns_404(client: TestClient):
    res = client.get("/envelopes/env_unknown12345")
    assert res.status_code == 404
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())


def test_http_activate_unknown_envelope_returns_404(client: TestClient):
    res = client.post(
        "/envelopes/env_unknown12345/activate",
        json={"expected_envelope_hash": "a" * 64},
    )
    assert res.status_code == 404
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())


def test_http_activate_already_active_envelope_returns_409(client: TestClient):
    draft = create_draft(client)
    active = activate_envelope(client, draft)
    res = client.post(
        f"/envelopes/{draft['id']}/activate",
        json={"expected_envelope_hash": active["envelope_hash"]},
    )
    assert res.status_code == 409
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())


def test_http_revoke_wrong_version_returns_409(client: TestClient):
    draft = create_draft(client)
    active = activate_envelope(client, draft)
    res = client.post(
        f"/envelopes/{draft['id']}/revoke",
        json={"expected_version": 999},
    )
    assert res.status_code == 409
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())


def test_http_execute_unknown_envelope_returns_404(client: TestClient):
    res = client.post(
        "/autopilot/execute",
        json={
            "envelope_id": "env_unknown12345",
            "expected_envelope_version": 1,
            "expected_envelope_hash": "a" * 64,
            "session_id": "session-unknown",
            "purchase_attempt_id": "attempt-unknown",
            "scenario": "normal",
        },
    )
    assert res.status_code == 404
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())


@pytest.mark.parametrize(
    "attempt_fields",
    [
        {},
        {"idempotency_key": "legacy-derived-identity"},
        {"purchase_attempt_id": "short"},
    ],
)
def test_http_execute_requires_explicit_purchase_attempt_identity(
    client: TestClient, attempt_fields: dict[str, str]
):
    draft = create_draft(client)
    active = activate_envelope(client, draft)
    res = client.post(
        "/autopilot/execute",
        json={
            "envelope_id": active["id"],
            "expected_envelope_version": active["version"],
            "expected_envelope_hash": active["envelope_hash"],
            "session_id": "session-explicit-attempt",
            "scenario": "normal",
            **attempt_fields,
        },
    )

    assert res.status_code == 422
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())


def test_http_execute_stale_envelope_version_returns_binding_denial(client: TestClient):
    draft = create_draft(client)
    active = activate_envelope(client, draft)
    # expected_envelope_version is stale (1 instead of 2)
    res = client.post(
        "/autopilot/execute",
        json={
            "envelope_id": active["id"],
            "expected_envelope_version": 1,
            "expected_envelope_hash": active["envelope_hash"],
            "session_id": "session-stale",
            "purchase_attempt_id": "attempt-stale",
            "scenario": "normal",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["envelope_decision"]["allowed"] is False
    assert data["envelope_decision"]["code"] == "BLOCK_ENVELOPE_BINDING_CHANGED"
    assert data["grant_id"] is None
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())


def test_http_execute_unactivated_draft_returns_denial(client: TestClient):
    draft = create_draft(client)
    res = client.post(
        "/autopilot/execute",
        json={
            "envelope_id": draft["id"],
            "expected_envelope_version": draft["version"],
            "expected_envelope_hash": draft["envelope_hash"],
            "session_id": "session-draft",
            "purchase_attempt_id": "attempt-draft",
            "scenario": "normal",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["envelope_decision"]["allowed"] is False
    assert data["grant_id"] is None
    deltas = data["envelope_decision"]["deltas"]
    assert any(d["field"] == "status" and d["recovery"] == "stop" for d in deltas)
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())


def test_http_execute_consumed_envelope_with_new_key_returns_denial(client: TestClient):
    draft = create_draft(client)
    active = activate_envelope(client, draft)
    first = client.post(
        "/autopilot/execute",
        json={
            "envelope_id": active["id"],
            "expected_envelope_version": active["version"],
            "expected_envelope_hash": active["envelope_hash"],
            "session_id": "session-consume",
            "purchase_attempt_id": "attempt-1",
            "scenario": "normal",
        },
    )
    assert first.status_code == 200
    assert first.json()["action_status"] == "action_issued"

    # Second execution on now-consumed envelope with a NEW idempotency key
    # If using updated envelope metadata: status is consumed, resulting in verification refusal
    consumed = client.get(f"/envelopes/{active['id']}").json()
    assert consumed["status"] == "consumed"
    second = client.post(
        "/autopilot/execute",
        json={
            "envelope_id": consumed["id"],
            "expected_envelope_version": consumed["version"],
            "expected_envelope_hash": consumed["envelope_hash"],
            "session_id": "session-consume",
            "purchase_attempt_id": "attempt-2",
            "scenario": "normal",
        },
    )
    assert second.status_code == 200
    data = second.json()
    assert data["envelope_decision"]["allowed"] is False
    assert any(d["field"] == "status" and d["recovery"] == "stop" for d in data["envelope_decision"]["deltas"])
    # Exactly one ACTION_ISSUED event, from the first call
    issued = [e for e in store.audit_trail() if e["event"] == "ACTION_ISSUED"]
    assert len(issued) == 1


def test_http_execute_revoked_envelope_returns_denial(client: TestClient):
    draft = create_draft(client)
    active = activate_envelope(client, draft)
    revoke_res = client.post(
        f"/envelopes/{draft['id']}/revoke",
        json={"expected_version": active["version"]},
    )
    assert revoke_res.status_code == 200
    revoked = revoke_res.json()

    res = client.post(
        "/autopilot/execute",
        json={
            "envelope_id": revoked["id"],
            "expected_envelope_version": revoked["version"],
            "expected_envelope_hash": revoked["envelope_hash"],
            "session_id": "session-revoked",
            "purchase_attempt_id": "attempt-revoked",
            "scenario": "normal",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["envelope_decision"]["allowed"] is False
    assert any(d["field"] == "status" and d["recovery"] == "stop" for d in data["envelope_decision"]["deltas"])
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())


def test_http_execute_merchant_drift_returns_field_delta(client: TestClient):
    draft = create_draft(client)
    active = activate_envelope(client, draft)
    res = client.post(
        "/autopilot/execute",
        json={
            "envelope_id": active["id"],
            "expected_envelope_version": active["version"],
            "expected_envelope_hash": active["envelope_hash"],
            "session_id": "session-drift",
            "purchase_attempt_id": "attempt-drift",
            "scenario": "merchant_drift",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["envelope_decision"]["allowed"] is False
    deltas = data["envelope_decision"]["deltas"]
    assert any(
        d["field"] == "merchant_id"
        and d["expected"] == "merchant_demo"
        and d["actual"] == "merchant_unapproved"
        for d in deltas
    )
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())


def test_http_execute_invalid_scenario_enum_returns_422(client: TestClient):
    draft = create_draft(client)
    active = activate_envelope(client, draft)
    res = client.post(
        "/autopilot/execute",
        json={
            "envelope_id": active["id"],
            "expected_envelope_version": active["version"],
            "expected_envelope_hash": active["envelope_hash"],
            "session_id": "session-invalid",
            "purchase_attempt_id": "attempt-invalid",
            "scenario": "unsupported_scenario_injection",
        },
    )
    assert res.status_code == 422
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())


def test_http_draft_refusals_return_422(client: TestClient):
    # Empty goal
    res = client.post("/envelopes/draft", json={"goal": "", "max_total_rupees": 500})
    assert res.status_code == 422

    # Goal too short
    res = client.post("/envelopes/draft", json={"goal": "hi", "max_total_rupees": 500})
    assert res.status_code == 422

    # Zero budget
    res = client.post("/envelopes/draft", json={"goal": "Buy pasta dinner", "max_total_rupees": 0})
    assert res.status_code == 422

    # Negative budget
    res = client.post("/envelopes/draft", json={"goal": "Buy pasta dinner", "max_total_rupees": -50})
    assert res.status_code == 422

    # Unknown merchant
    res = client.post(
        "/envelopes/draft",
        json={"goal": "Buy pasta dinner", "max_total_rupees": 500, "merchant_id": "rogue_merchant"},
    )
    assert res.status_code == 422

    # Unintelligible goal
    res = client.post(
        "/envelopes/draft",
        json={"goal": "xyzzy blorp qwerty nonsense", "max_total_rupees": 500},
    )
    assert res.status_code == 422
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())


def test_http_verify_receipt_unknown_grant_returns_404(client: TestClient):
    get_res = client.get("/receipts/act_unknown999")
    assert get_res.status_code == 404

    dummy_receipt = {
        "grant_id": "act_unknown999",
        "envelope_id": None,
        "envelope_version": None,
        "envelope_hash": None,
        "policy_id": "mnd_test",
        "policy_version": 1,
        "policy_hash": "a" * 64,
        "action_name": "create_payment_link",
        "args_hash": "b" * 64,
        "cart_hash": "c" * 64,
        "quote_hash": None,
        "purchase_attempt_id": "attempt",
        "state": "action_issued",
        "provider_ref": None,
        "created_at": 1000.0,
        "updated_at": 1000.0,
        "signature": "dummy_sig",
    }
    res = client.post("/receipts/act_unknown999/verify", json=dummy_receipt)
    assert res.status_code == 404
    assert not any(e["event"] == "ACTION_ISSUED" for e in store.audit_trail())
