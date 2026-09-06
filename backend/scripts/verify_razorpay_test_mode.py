"""Create exactly one bounded Payment Link through Razorpay Remote MCP test mode.

This is an opt-in integration proof, not part of CI. It refuses non-test keys,
uses a disposable database, disables fault injection, and prints no secrets.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
import uuid
from pathlib import Path


def _require_test_credentials() -> None:
    key_id = os.environ.get("RAZORPAY_KEY_ID", "")
    has_auth = bool(
        os.environ.get("RAZORPAY_MCP_TOKEN")
        or os.environ.get("RAZORPAY_KEY_SECRET")
    )
    if not key_id.startswith("rzp_test_") or not has_auth:
        raise SystemExit(
            "Refusing to run. Set RAZORPAY_KEY_ID to an rzp_test_ key and provide "
            "RAZORPAY_KEY_SECRET or RAZORPAY_MCP_TOKEN. Live keys are not accepted."
        )


def main() -> None:
    _require_test_credentials()
    with tempfile.TemporaryDirectory(prefix="action-firewall-rzp-test-") as temp_dir:
        os.environ["DB_PATH"] = str(Path(temp_dir) / "razorpay-test-mode.db")
        os.environ["DEMO_MODE"] = "false"
        os.environ["PAYMENT_PROVIDER"] = "razorpay_mcp"
        os.environ["CATALOG_RETRIEVAL_MODE"] = "keyword"
        os.environ["ENVELOPE_DRAFTING_MODE"] = "deterministic"
        os.environ["FAULT_INJECTION_ENABLED"] = "false"
        os.environ.setdefault("ACTION_RECEIPT_SECRET", secrets.token_hex(32))

        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app import autopilot, store
        from app.config import get_settings
        from app.models import (
            ActionState,
            AutopilotExecuteRequest,
            AutopilotScenario,
            EnvelopeActivateRequest,
            EnvelopeDraftRequest,
        )

        get_settings.cache_clear()
        store.init_db()
        draft = autopilot.create_draft(
            EnvelopeDraftRequest(
                goal="Buy supplies for a pasta dinner",
                max_total_rupees=600,
            )
        )
        active = autopilot.activate(
            draft.id,
            EnvelopeActivateRequest(expected_envelope_hash=draft.envelope_hash),
        )
        result = autopilot.execute(
            AutopilotExecuteRequest(
                envelope_id=active.id,
                expected_envelope_version=active.version,
                expected_envelope_hash=active.envelope_hash,
                session_id=f"rzp-test-{uuid.uuid4().hex}",
                purchase_attempt_id=f"af-{uuid.uuid4().hex}",
                scenario=AutopilotScenario.NORMAL,
            )
        )

        if result.action_status is not ActionState.ACTION_ISSUED:
            raise SystemExit(
                f"Razorpay test-mode proof failed closed: {result.envelope_decision.code}"
            )
        print(
            json.dumps(
                {
                    "proof": "razorpay_remote_mcp_test_mode",
                    "provider": result.provider_mode,
                    "action_status": result.action_status.value,
                    "grant_id": result.grant_id,
                    "payment_link": result.payment_link,
                    "receipt_verified_locally": result.receipt is not None,
                    "amount_paise": result.quote.cart.total_paise if result.quote else None,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
