"""Public HTTP contract smoke test for the judge-facing product path."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import store
from app.config import get_settings
from app.main import app


def test_http_draft_activate_execute_and_verify_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "autopilot-http.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    store.init_db()

    with TestClient(app) as client:
        draft_response = client.post(
            "/envelopes/draft",
            json={
                "goal": "Buy supplies for a pasta dinner",
                "max_total_rupees": 600,
            },
        )
        assert draft_response.status_code == 200
        draft = draft_response.json()

        active_response = client.post(
            f"/envelopes/{draft['id']}/activate",
            json={"expected_envelope_hash": draft["envelope_hash"]},
        )
        assert active_response.status_code == 200
        active = active_response.json()
        assert active["status"] == "active"

        execution_response = client.post(
            "/autopilot/execute",
            json={
                "envelope_id": active["id"],
                "expected_envelope_version": active["version"],
                "expected_envelope_hash": active["envelope_hash"],
                "session_id": "http-demo-session",
                "idempotency_key": "http-demo-attempt",
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

    get_settings.cache_clear()
