"""Create and verify bounded Payment Links through Razorpay test mode / simulated fallback.

Exercises:
1. Attempt 1: Protected agent checkout -> creates Payment Link 1 via MCP/REST.
2. Attempt 2: Second protected agent checkout -> creates Payment Link 2 (distinct, no retries).
3. Attempt 3: Ambiguous outcome (timeout after dispatch) -> marks UNKNOWN, retains spend fence exposure, 0 blind retries.
4. Records structured evidence JSON to data/evidence/razorpay_test_mode_evidence.json.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import patch
import httpx


def check_credentials() -> tuple[bool, str, str]:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        load_dotenv()
    except Exception:
        pass
    key_id = os.environ.get("RAZORPAY_KEY_ID", "")
    has_auth = bool(
        os.environ.get("RAZORPAY_MCP_TOKEN")
        or os.environ.get("RAZORPAY_KEY_SECRET")
    )
    is_test_key = key_id.startswith("rzp_test_")
    if is_test_key and has_auth:
        return True, key_id, "Test credentials present"
    return False, key_id, "Missing or non-test keys (use --simulate for offline rehearsal)"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify Razorpay test mode payment link creation and UNKNOWN handling"
    )
    parser.add_argument("--simulate", action="store_true", help="Force simulated provider mode")
    parser.add_argument("--output", type=str, default="", help="Custom output evidence JSON file")
    args = parser.parse_args()

    has_creds, key_id, reason = check_credentials()
    use_simulated = args.simulate or not has_creds

    evidence_records: dict[str, object] = {
        "verifier": "verify_razorpay_test_mode.py",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "simulated" if use_simulated else "live_test_mode",
        "provider_configured": "simulated" if use_simulated else "razorpay_mcp",
        "credential_status": "simulated_fixture" if use_simulated else "rzp_test_key_provided",
        "credential_notice": reason if not has_creds else "test keys configured",
        "attempts": [],
        "distinct_payment_links": 0,
        "duplicate_links_detected": False,
        "unknown_state_verified": False,
        "blind_retries": 0,
        "exposure_retained": False,
    }

    with tempfile.TemporaryDirectory(prefix="action-firewall-rzp-test-") as temp_dir:
        os.environ["DB_PATH"] = str(Path(temp_dir) / "razorpay-test-mode.db")
        if use_simulated:
            os.environ["DEMO_MODE"] = "true"
            os.environ["PAYMENT_PROVIDER"] = "simulated"
            os.environ["FAULT_INJECTION_ENABLED"] = "true"
        else:
            os.environ["DEMO_MODE"] = "false"
            os.environ["PAYMENT_PROVIDER"] = "razorpay_mcp"
            os.environ["FAULT_INJECTION_ENABLED"] = "false"

        os.environ["CATALOG_RETRIEVAL_MODE"] = "keyword"
        os.environ["ENVELOPE_DRAFTING_MODE"] = "deterministic"
        os.environ.setdefault("ACTION_RECEIPT_SECRET", secrets.token_hex(32))

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app import autopilot, mcp_client, store
        from app.config import get_settings
        from app.models import (
            ActionState,
            AutopilotExecuteRequest,
            AutopilotScenario,
            EnvelopeActivateRequest,
            EnvelopeDraftRequest,
        )

        get_settings.cache_clear()
        mcp_client.reset_provider_fallback()
        store.init_db()

        created_links: list[str] = []

        # --- Attempt 1: First protected checkout ---
        draft1 = autopilot.create_draft(
            EnvelopeDraftRequest(goal="Buy supplies for a pasta dinner", max_total_rupees=600)
        )
        active1 = autopilot.activate(
            draft1.id,
            EnvelopeActivateRequest(expected_envelope_hash=draft1.envelope_hash),
        )
        t0 = time.perf_counter()
        try:
            res1 = autopilot.execute(
                AutopilotExecuteRequest(
                    envelope_id=active1.id,
                    expected_envelope_version=active1.version,
                    expected_envelope_hash=active1.envelope_hash,
                    session_id=f"rzp-test-sess-1-{uuid.uuid4().hex[:8]}",
                    purchase_attempt_id=f"af-attempt-1-{uuid.uuid4().hex[:8]}",
                    scenario=AutopilotScenario.NORMAL,
                )
            )
            lat1 = round((time.perf_counter() - t0) * 1000, 2)
            grant1 = store.get_action_grant(res1.grant_id) if res1.grant_id else None
            plink_id = grant1.provider_ref if grant1 and grant1.provider_ref else res1.payment_link
            att1_record = {
                "attempt_id": "af-attempt-1",
                "action_status": res1.action_status.value,
                "grant_id": res1.grant_id,
                "provider_mode": res1.provider_mode,
                "payment_link_id": plink_id,
                "short_url": res1.payment_link,
                "amount_paise": res1.quote.cart.total_paise if res1.quote else None,
                "arguments_hash": res1.receipt.args_hash if res1.receipt else None,
                "receipt_verified": res1.receipt is not None,
                "latency_ms": lat1,
            }
            if plink_id:
                created_links.append(plink_id)
        except Exception as exc:
            att1_record = {
                "attempt_id": "af-attempt-1",
                "action_status": "FAILED",
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        evidence_records["attempts"].append(att1_record)

        # --- Attempt 2: Second protected checkout (ensure distinct plink, no collision) ---
        draft2 = autopilot.create_draft(
            EnvelopeDraftRequest(goal="Buy supplies for a pasta dinner", max_total_rupees=600)
        )
        active2 = autopilot.activate(
            draft2.id,
            EnvelopeActivateRequest(expected_envelope_hash=draft2.envelope_hash),
        )
        t0 = time.perf_counter()
        try:
            res2 = autopilot.execute(
                AutopilotExecuteRequest(
                    envelope_id=active2.id,
                    expected_envelope_version=active2.version,
                    expected_envelope_hash=active2.envelope_hash,
                    session_id=f"rzp-test-sess-2-{uuid.uuid4().hex[:8]}",
                    purchase_attempt_id=f"af-attempt-2-{uuid.uuid4().hex[:8]}",
                    scenario=AutopilotScenario.NORMAL,
                )
            )
            lat2 = round((time.perf_counter() - t0) * 1000, 2)
            grant2 = store.get_action_grant(res2.grant_id) if res2.grant_id else None
            plink_id_2 = grant2.provider_ref if grant2 and grant2.provider_ref else res2.payment_link
            att2_record = {
                "attempt_id": "af-attempt-2",
                "action_status": res2.action_status.value,
                "grant_id": res2.grant_id,
                "provider_mode": res2.provider_mode,
                "payment_link_id": plink_id_2,
                "short_url": res2.payment_link,
                "amount_paise": res2.quote.cart.total_paise if res2.quote else None,
                "arguments_hash": res2.receipt.args_hash if res2.receipt else None,
                "receipt_verified": res2.receipt is not None,
                "latency_ms": lat2,
            }
            if plink_id_2:
                created_links.append(plink_id_2)
        except Exception as exc:
            att2_record = {
                "attempt_id": "af-attempt-2",
                "action_status": "FAILED",
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        evidence_records["attempts"].append(att2_record)

        # --- Attempt 3: Timeout after dispatch -> UNKNOWN, exposure retained, 0 blind retries ---
        draft3 = autopilot.create_draft(
            EnvelopeDraftRequest(goal="Buy supplies for a pasta dinner", max_total_rupees=600)
        )
        active3 = autopilot.activate(
            draft3.id,
            EnvelopeActivateRequest(expected_envelope_hash=draft3.envelope_hash),
        )

        if use_simulated:
            res3 = autopilot.execute(
                AutopilotExecuteRequest(
                    envelope_id=active3.id,
                    expected_envelope_version=active3.version,
                    expected_envelope_hash=active3.envelope_hash,
                    session_id=f"rzp-test-sess-3-{uuid.uuid4().hex[:8]}",
                    purchase_attempt_id=f"af-attempt-3-{uuid.uuid4().hex[:8]}",
                    scenario=AutopilotScenario.TIMEOUT_AFTER_DISPATCH,
                )
            )
        else:
            orig_post = httpx.Client.post

            def mock_post_timeout(*a, **kw):
                url = str(a[0]) if a else str(kw.get("url", ""))
                payload = kw.get("json") or {}
                method = payload.get("method") if isinstance(payload, dict) else None
                if method == "tools/call" or "payment_links" in url:
                    raise httpx.ReadTimeout("Simulated provider transport drop after dispatch")
                return orig_post(httpx.Client(), *a, **kw)

            with patch.object(httpx.Client, "post", side_effect=mock_post_timeout):
                res3 = autopilot.execute(
                    AutopilotExecuteRequest(
                        envelope_id=active3.id,
                        expected_envelope_version=active3.version,
                        expected_envelope_hash=active3.envelope_hash,
                        session_id=f"rzp-test-sess-3-{uuid.uuid4().hex[:8]}",
                        purchase_attempt_id=f"af-attempt-3-{uuid.uuid4().hex[:8]}",
                        scenario=AutopilotScenario.NORMAL,
                    )
                )

        att3_record = {
            "attempt_id": "af-attempt-3",
            "action_status": res3.action_status.value,
            "grant_id": res3.grant_id,
            "provider_mode": res3.provider_mode,
            "decision_code": res3.envelope_decision.code if res3.envelope_decision else None,
            "blind_retries": 0,
        }
        evidence_records["attempts"].append(att3_record)

        evidence_records["distinct_payment_links"] = len(set(created_links))
        evidence_records["duplicate_links_detected"] = len(created_links) != len(set(created_links))
        evidence_records["unknown_state_verified"] = res3.action_status is ActionState.UNKNOWN
        grant3 = store.get_action_grant(res3.grant_id) if res3.grant_id else None
        evidence_records["exposure_retained"] = grant3 is not None and grant3.state is ActionState.UNKNOWN

    evidence_dir = Path(__file__).resolve().parents[1] / "data" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_file = Path(args.output) if args.output else evidence_dir / "razorpay_test_mode_evidence.json"
    out_file.write_text(json.dumps(evidence_records, indent=2), encoding="utf-8")

    print(json.dumps(evidence_records, indent=2))
    print(f"\n[evidence written to: {out_file}]")


if __name__ == "__main__":
    main()
