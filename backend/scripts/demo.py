"""Disposable, offline dress rehearsal for the five-minute judge demo.

Run from ``backend`` with ``python scripts/demo.py``. The script forces demo
mode, uses a temporary SQLite database, and never needs network credentials.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    # The default Windows code page cannot represent the rupee sign or the
    # punctuation used by the scripted responses. Force a deterministic stream
    # encoding so the fallback demo remains readable on the presentation host.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_TEMP_DIR = tempfile.TemporaryDirectory(prefix="action-firewall-demo-")
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
):
    os.environ[secret_name] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import reconciler, store  # noqa: E402
from app.agent import confirm_checkout, handle_turn, reset_session  # noqa: E402
from app.mandate import rupees  # noqa: E402
from app.mcp_client import simulate_provider_payment  # noqa: E402
from app.models import (  # noqa: E402
    ActionState,
    ChatRequest,
    ChatResponse,
    CheckoutConfirmRequest,
    MandateCreate,
    MandateUpdate,
)


USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
GREEN = "\033[92m" if USE_COLOR else ""
RED = "\033[91m" if USE_COLOR else ""
BLUE = "\033[94m" if USE_COLOR else ""
RESET = "\033[0m" if USE_COLOR else ""
SESSION_ID = f"judge_demo_{uuid.uuid4().hex[:8]}"


def heading(title: str) -> None:
    print(f"\n--- {title} ---")


def show_response(response: ChatResponse) -> None:
    print(f"{BLUE}ASSISTANT:{RESET} {response.reply}")
    print(
        "  cart="
        f"{rupees(response.cart.total_paise)} "
        f"hash={response.cart_hash[:12] or '-'} "
        f"confirmation_required={response.confirmation_required}"
    )
    if response.decision:
        color = GREEN if response.decision.allowed else RED
        print(
            f"  {color}[{response.decision.code.value}]{RESET} "
            f"headroom={rupees(response.decision.headroom_paise)}"
        )
    for invocation in response.tools:
        status = (
            f"{RED}BLOCKED{RESET}"
            if invocation.blocked
            else f"{GREEN}ISSUED{RESET}"
        )
        print(f"  {status} action:{invocation.name}")
    if response.action_status:
        print(
            f"  state={response.action_status.value} "
            f"grant={response.grant_id or '-'}"
        )


def propose(message: str) -> ChatResponse:
    print(f"\n{BLUE}SHOPPER:{RESET} {message}")
    response = handle_turn(ChatRequest(session_id=SESSION_ID, message=message))
    show_response(response)
    if response.tools:
        raise AssertionError("Proposal-only chat unexpectedly reached an action")
    return response


def authorize(proposal: ChatResponse, purchase_attempt_id: str) -> ChatResponse:
    print(
        f"\n{BLUE}SHOPPER ACTION:{RESET} Authorize exact cart "
        f"{proposal.cart_hash[:12]} for create_payment_link"
    )
    response = confirm_checkout(
        CheckoutConfirmRequest(
            session_id=SESSION_ID,
            expected_cart_hash=proposal.cart_hash,
            idempotency_key=purchase_attempt_id,
        )
    )
    show_response(response)
    return response


def main() -> None:
    store.init_db()
    policy = store.create_mandate(
        MandateCreate(
            label="Grocery action policy",
            cap_rupees=1000,
            blocked_categories=["gift_cards"],
        )
    )
    print("Action Firewall offline rehearsal")
    print("State: disposable temporary SQLite database; network: disabled")
    print(
        f"{GREEN}Policy active:{RESET} {policy.id} v{policy.version} — "
        f"{rupees(policy.cap_paise)} / {policy.window.value}"
    )

    try:
        heading("ACT 1 — the agent proposes; it cannot pay")
        propose("I need supplies for a pasta dinner")

        heading("ACT 2 — an over-cap exact action is denied")
        oversized = propose(
            "Add the Parmigiano Reggiano and the olive oil, then check out"
        )
        denied = authorize(oversized, "demo_attempt_over_cap")
        assert denied.decision and not denied.decision.allowed
        assert all(invocation.blocked for invocation in denied.tools)

        heading("ACT 3 — recovery creates one payment link, not a settlement")
        propose("Remove the Parmigiano Reggiano and the olive oil")
        recovered = propose("Checkout please")
        issued = authorize(recovered, "demo_attempt_recovered")
        assert issued.action_status and issued.action_status.value == "action_issued"
        assert any(not invocation.blocked for invocation in issued.tools)

        heading("ACT 4 — revocation binds at the next authorization")
        revoked = store.update_mandate(policy.id, MandateUpdate(active=False))
        assert revoked and not revoked.active
        print(
            f"{RED}Policy revoked:{RESET} {revoked.id} v{revoked.version}; "
            "new action receipts are disabled"
        )
        coffee = propose("Buy me some coffee beans")
        blocked_after_revocation = authorize(coffee, "demo_attempt_revoked")
        assert blocked_after_revocation.decision
        assert not blocked_after_revocation.decision.allowed

        heading("ACT 5 — settlement is observed, never asserted")
        issued = [
            g for g in store.open_actions_for_reconciliation()
            if g.state is ActionState.ACTION_ISSUED
        ]
        assert issued, "act 3 should have left one issued payment link"
        target = issued[0]

        # Reconciling an unpaid link must change nothing. Issuing is not paying.
        unpaid = reconciler.reconcile(target.id)
        print(
            f"Reconcile before payment: provider says "
            f"{unpaid.observation.provider_status!r} -> changed={unpaid.changed}"
        )
        assert not unpaid.changed
        assert store.metrics()["confirmed_test_payment_value_paise"] == 0

        # Stand in for the shopper paying the link. In live mode this is a real
        # test-mode UPI payment; the reconciler cannot tell the difference,
        # because it only ever reads the provider's own view.
        simulate_provider_payment(target.provider_ref, target.amount_paise)
        settled = reconciler.reconcile(target.id)
        print(
            f"Reconcile after payment:  provider says "
            f"{settled.observation.provider_status!r} -> "
            f"{settled.before.value} -> {settled.after.value}"
        )
        assert settled.changed and settled.after is ActionState.SETTLED
        assert store.metrics()["confirmed_test_payment_value_paise"] == target.amount_paise
        print(
            f"{GREEN}Settled{RESET} {rupees(target.amount_paise)} — recorded only "
            "because the provider said so."
        )

        heading("EVIDENCE — truthful outcome metrics")
        print(json.dumps(store.metrics(), indent=2, sort_keys=True))
        print(f"\n{GREEN}REHEARSAL PASSED{RESET}")
    finally:
        reset_session(SESSION_ID)


if __name__ == "__main__":
    try:
        main()
    finally:
        _TEMP_DIR.cleanup()
