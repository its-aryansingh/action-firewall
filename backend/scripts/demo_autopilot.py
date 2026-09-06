"""Disposable offline rehearsal for Safe Autopilot Checkout."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_TEMP_DIR = tempfile.TemporaryDirectory(prefix="safe-autopilot-demo-")
os.environ["DB_PATH"] = str(Path(_TEMP_DIR.name) / "demo.db")
os.environ["DEMO_MODE"] = "true"
os.environ["PAYMENT_PROVIDER"] = "simulated"
os.environ["CATALOG_RETRIEVAL_MODE"] = "keyword"
os.environ["ENVELOPE_DRAFTING_MODE"] = "replay"
os.environ["FAULT_INJECTION_ENABLED"] = "true"
for secret_name in (
    "OPENAI_API_KEY",
    "PINECONE_API_KEY",
    "RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_MCP_TOKEN",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "ACTION_RECEIPT_SECRET",
):
    os.environ[secret_name] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import autopilot, store  # noqa: E402
from app.models import (  # noqa: E402
    ActionState,
    AutopilotExecuteRequest,
    AutopilotScenario,
    EnvelopeActivateRequest,
    EnvelopeDraftRequest,
)


def heading(title: str) -> None:
    print(f"\n--- {title} ---")


def create_active_envelope(label: str):
    draft = autopilot.create_draft(
        EnvelopeDraftRequest(
            goal="Buy supplies for a pasta dinner",
            max_total_rupees=600,
        )
    )
    print(
        f"DRAFT {label}: {draft.id} v{draft.version} "
        f"hash={draft.envelope_hash[:12]} slots={len(draft.slots)}"
    )
    active = autopilot.activate(
        draft.id,
        EnvelopeActivateRequest(expected_envelope_hash=draft.envelope_hash),
    )
    print(
        f"APPROVED ONCE: v{active.version} max=Rs {active.max_total_paise / 100:.0f} "
        f"merchant={active.merchant_id} action={active.action_name}"
    )
    return active


def execute(envelope, scenario: AutopilotScenario, key: str, session: str):
    result = autopilot.execute(
        AutopilotExecuteRequest(
            envelope_id=envelope.id,
            expected_envelope_version=envelope.version,
            expected_envelope_hash=envelope.envelope_hash,
            session_id=session,
            purchase_attempt_id=key,
            scenario=scenario,
        )
    )
    print(
        f"DECISION {result.envelope_decision.code}: "
        f"allowed={result.envelope_decision.allowed} "
        f"state={result.action_status.value if result.action_status else 'no_action'}"
    )
    for delta in result.envelope_decision.deltas:
        print(
            f"  DELTA {delta.field}: expected={delta.expected} "
            f"actual={delta.actual} next={delta.recovery}"
        )
    if result.recovery_applied:
        print("  RECOVERY: deterministic in-envelope substitution")
    if result.receipt:
        print(
            f"  RECEIPT grant={result.receipt.grant_id[:16]} "
            f"signature={result.receipt.signature[:16]}..."
        )
    return result


def main() -> None:
    store.init_db()
    print("Action Firewall - Safe Autopilot offline rehearsal")
    print("State: disposable SQLite; provider: simulated; network: disabled")

    heading("ACT 1 - shopper approves the job, not a frozen cart")
    recovery_envelope = create_active_envelope("pasta-job")

    heading("ACT 2 - stock changes; the system recovers inside authority")
    recovered = execute(
        recovery_envelope,
        AutopilotScenario.STOCK_LOSS,
        "demo-safe-recovery",
        "session-safe-recovery",
    )
    assert recovered.recovery_applied
    assert recovered.action_status is ActionState.ACTION_ISSUED
    assert recovered.receipt

    heading("ACT 3 - merchant changes; the system refuses before the actuator")
    blocked_envelope = create_active_envelope("merchant-drift-job")
    blocked = execute(
        blocked_envelope,
        AutopilotScenario.MERCHANT_DRIFT,
        "demo-merchant-drift",
        "session-merchant-drift",
    )
    assert not blocked.envelope_decision.allowed
    assert blocked.grant_id is None
    assert any(delta.field == "merchant_id" for delta in blocked.envelope_decision.deltas)

    heading("ACT 4 - provider times out; UNKNOWN is held, never blind-retried")
    timeout_envelope = create_active_envelope("timeout-job")
    unknown = execute(
        timeout_envelope,
        AutopilotScenario.TIMEOUT_AFTER_DISPATCH,
        "demo-timeout",
        "session-timeout",
    )
    retry = execute(
        timeout_envelope,
        AutopilotScenario.TIMEOUT_AFTER_DISPATCH,
        "demo-timeout",
        "session-timeout",
    )
    assert unknown.action_status is ActionState.UNKNOWN
    assert retry.grant_id == unknown.grant_id
    print("  RETRY: same grant returned; provider dispatch count remains one")

    heading("EVIDENCE - observed outcomes, not marketing claims")
    print(json.dumps(store.metrics(), indent=2, sort_keys=True))
    events = store.audit_trail(limit=500)
    print(
        "event_counts="
        + json.dumps(
            {
                name: sum(event["event"] == name for event in events)
                for name in (
                    "ENVELOPE_ACTIVATED",
                    "ENVELOPE_RECOVERY_APPLIED",
                    "ENVELOPE_QUOTE_BLOCKED",
                    "ACTION_ISSUED",
                    "ACTION_OUTCOME_UNKNOWN",
                )
            },
            sort_keys=True,
        )
    )
    print("\nSAFE AUTOPILOT REHEARSAL PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        _TEMP_DIR.cleanup()
