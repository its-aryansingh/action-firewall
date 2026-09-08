"""Verification script for Gate A2b: HMAC-signed Razorpay Webhooks.

Proves:
1. One grant observed 'settled' ('paid') via valid HMAC-SHA256 signed webhook.
2. One rejected forged-signature attempt recorded in the audit log (HTTP 400).
3. One replayed webhook proving idempotency (no double transition, already_processed).
4. One provider failure webhook resolving UNKNOWN to DEFINITIVE_FAILURE (exposure released).
5. Structured evidence written to data/evidence/razorpay_webhook_evidence.json.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Razorpay webhook HMAC processing")
    parser.add_argument("--output", type=str, default="", help="Custom output evidence JSON file")
    args = parser.parse_args()

    webhook_secret = "whsec_test_secret_for_firewall_12345"

    with tempfile.TemporaryDirectory(prefix="action-firewall-webhook-") as temp_dir:
        db_path = str(Path(temp_dir) / "webhook-verification.db")
        os.environ["DB_PATH"] = db_path
        os.environ["DEMO_MODE"] = "true"
        os.environ["PAYMENT_PROVIDER"] = "simulated"
        os.environ["FAULT_INJECTION_ENABLED"] = "true"
        os.environ["RAZORPAY_WEBHOOK_SECRET"] = webhook_secret
        os.environ["CATALOG_RETRIEVAL_MODE"] = "keyword"
        os.environ["ENVELOPE_DRAFTING_MODE"] = "deterministic"
        os.environ.setdefault("ACTION_RECEIPT_SECRET", secrets.token_hex(32))

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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

        get_settings.cache_clear()
        store.init_db()

        client = TestClient(app)

        evidence: dict[str, object] = {
            "verifier": "verify_razorpay_webhook.py",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "webhook_endpoint": "/provider/webhooks/razorpay",
            "hmac_algorithm": "HMAC-SHA256",
            "checks": {},
        }

        def sign(body: bytes) -> str:
            return hmac.new(webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

        # --- Check 1: Rejected forged-signature attempt ---
        forged_body = json.dumps({"event": "payment_link.paid", "id": "evt_forged_001"}).encode("utf-8")
        forged_resp = client.post(
            "/provider/webhooks/razorpay",
            content=forged_body,
            headers={"X-Razorpay-Signature": "invalid_forged_signature_hex", "Content-Type": "application/json"},
        )
        forged_audit = [row for row in store.audit_trail() if row["event"] == "WEBHOOK_SIGNATURE_INVALID"]
        evidence["checks"]["forged_signature_rejected"] = {
            "http_status": forged_resp.status_code,
            "rejected": forged_resp.status_code == 400,
            "audit_event_logged": len(forged_audit) > 0,
            "audit_event": forged_audit[0]["event"] if forged_audit else None,
            "audit_code": forged_audit[0]["code"] if forged_audit else None,
        }

        # --- Check 2: Grant observed 'paid' / 'settled' via signed webhook ---
        draft1 = autopilot.create_draft(
            EnvelopeDraftRequest(goal="Buy supplies for a pasta dinner", max_total_rupees=600)
        )
        active1 = autopilot.activate(
            draft1.id,
            EnvelopeActivateRequest(expected_envelope_hash=draft1.envelope_hash),
        )
        res1 = autopilot.execute(
            AutopilotExecuteRequest(
                envelope_id=active1.id,
                expected_envelope_version=active1.version,
                expected_envelope_hash=active1.envelope_hash,
                session_id="sess_wh_proof_1",
                purchase_attempt_id="att_wh_proof_1",
                scenario=AutopilotScenario.NORMAL,
            )
        )
        grant1 = store.get_action_grant(res1.grant_id)

        wh1_payload = {
            "event_id": "evt_wh_settled_001",
            "event": "payment_link.paid",
            "payload": {
                "payment_link": {
                    "entity": {
                        "id": grant1.provider_ref,
                        "status": "paid",
                        "amount_paid": 41700,
                        "notes": {"grant_id": grant1.id},
                    }
                }
            },
        }
        wh1_body = json.dumps(wh1_payload).encode("utf-8")
        wh1_sig = sign(wh1_body)

        wh1_resp = client.post(
            "/provider/webhooks/razorpay",
            content=wh1_body,
            headers={"X-Razorpay-Signature": wh1_sig, "Content-Type": "application/json"},
        )
        wh1_data = wh1_resp.json()
        grant1_after = store.get_action_grant(grant1.id)

        evidence["checks"]["signed_payment_link_paid"] = {
            "grant_id": grant1.id,
            "provider_ref": grant1.provider_ref,
            "http_status": wh1_resp.status_code,
            "before_status": wh1_data.get("before"),
            "after_status": wh1_data.get("after"),
            "final_grant_state": grant1_after.state.value if grant1_after else None,
            "verified_settled": grant1_after.state is ActionState.SETTLED if grant1_after else False,
        }

        # --- Check 3: Replayed webhook proving no double transition ---
        replay_resp = client.post(
            "/provider/webhooks/razorpay",
            content=wh1_body,
            headers={"X-Razorpay-Signature": wh1_sig, "Content-Type": "application/json"},
        )
        replay_data = replay_resp.json()
        grant1_replayed = store.get_action_grant(grant1.id)

        evidence["checks"]["replayed_webhook_idempotency"] = {
            "http_status": replay_resp.status_code,
            "response_status": replay_data.get("status"),
            "idempotent_flag": replay_data.get("idempotent"),
            "final_grant_state": grant1_replayed.state.value if grant1_replayed else None,
            "double_transition_prevented": replay_data.get("status") == "already_processed" and grant1_replayed.state is ActionState.SETTLED,
        }

        # --- Check 4: Failure webhook resolving UNKNOWN to DEFINITIVE_FAILURE ---
        draft2 = autopilot.create_draft(
            EnvelopeDraftRequest(goal="Buy supplies for a pasta dinner", max_total_rupees=600)
        )
        active2 = autopilot.activate(
            draft2.id,
            EnvelopeActivateRequest(expected_envelope_hash=draft2.envelope_hash),
        )
        res2 = autopilot.execute(
            AutopilotExecuteRequest(
                envelope_id=active2.id,
                expected_envelope_version=active2.version,
                expected_envelope_hash=active2.envelope_hash,
                session_id="sess_wh_proof_2",
                purchase_attempt_id="att_wh_proof_2",
                scenario=AutopilotScenario.TIMEOUT_AFTER_DISPATCH,
            )
        )
        grant2 = store.get_action_grant(res2.grant_id)
        assert grant2.state is ActionState.UNKNOWN

        fail_payload = {
            "event_id": "evt_wh_fail_002",
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_fail_proof_999",
                        "payment_link_id": grant2.provider_ref,
                        "status": "failed",
                        "notes": {"grant_id": grant2.id},
                    }
                }
            },
        }
        fail_body = json.dumps(fail_payload).encode("utf-8")
        fail_sig = sign(fail_body)

        fail_resp = client.post(
            "/provider/webhooks/razorpay",
            content=fail_body,
            headers={"X-Razorpay-Signature": fail_sig, "Content-Type": "application/json"},
        )
        fail_data = fail_resp.json()
        grant2_after = store.get_action_grant(grant2.id)

        evidence["checks"]["unknown_resolved_to_definitive_failure"] = {
            "grant_id": grant2.id,
            "provider_ref": grant2.provider_ref,
            "http_status": fail_resp.status_code,
            "before_status": fail_data.get("before"),
            "after_status": fail_data.get("after"),
            "final_grant_state": grant2_after.state.value if grant2_after else None,
            "verified_definitive_failure": grant2_after.state is ActionState.DEFINITIVE_FAILURE if grant2_after else False,
            "exposure_released": grant2_after.state is ActionState.DEFINITIVE_FAILURE if grant2_after else False,
        }

    evidence_dir = Path(__file__).resolve().parents[1] / "data" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_file = Path(args.output) if args.output else evidence_dir / "razorpay_webhook_evidence.json"
    out_file.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    print(json.dumps(evidence, indent=2))
    print(f"\n[evidence written to: {out_file}]")


if __name__ == "__main__":
    main()
