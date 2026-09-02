"""Concurrency tests for the money gate.

`mandate_check -> mcp_tool_call` is a check-then-act sequence. Two agent turns
running at the same time can both read the same headroom and both spend it.
This is the TOCTOU (time-of-check to time-of-use) class, and it is the single
largest category of vulnerability catalogued in the agentic-commerce literature.

`test_naive_check_then_act_overspends` reproduces the bug against the unguarded
path, so the fix has evidence behind it rather than an assertion of good taste.
Everything below it tests the two-phase reservation that closes the hole.
"""
import os
import tempfile
import threading

import pytest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "concurrency.db")
os.environ["DEMO_MODE"] = "true"

from app import store                                            # noqa: E402
from app.config import get_settings                              # noqa: E402
from app.models import MandateCreate, Window                      # noqa: E402

CAP_RUPEES = 1_000
CAP_PAISE = CAP_RUPEES * 100
LINE_PAISE = 30_000          # ₹300 — four of these breach a ₹1,000 cap
THREADS = 8


@pytest.fixture()
def mandate(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "concurrency.db"))
    get_settings.cache_clear()
    store.init_db()
    created = store.create_mandate(MandateCreate(cap_rupees=CAP_RUPEES))
    yield created
    get_settings.cache_clear()


def _run(fn, n=THREADS):
    """Fire n threads at once through a barrier, so they genuinely collide."""
    barrier = threading.Barrier(n)
    results: list = [None] * n

    def wrapped(i):
        barrier.wait()
        try:
            results[i] = fn(i)
        except Exception as exc:                     # noqa: BLE001
            results[i] = exc

    threads = [threading.Thread(target=wrapped, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


# ---------------------------------------------------------------------------
# The bug, reproduced
# ---------------------------------------------------------------------------
def test_naive_check_then_act_overspends(mandate):
    """Read headroom, then write — with no reservation in between.

    Every thread sees the same headroom because none of them has committed yet,
    so all of them believe they fit. This is what the agent did before the fix.
    """
    def naive(_i):
        spent = store.spent_in_window(mandate.id, mandate.window)
        if spent + LINE_PAISE <= CAP_PAISE:          # the check
            store.record_spend(mandate.id, LINE_PAISE)   # the act
            return True
        return False

    _run(naive)
    committed = store.spent_in_window(mandate.id, mandate.window)
    assert committed > CAP_PAISE, (
        "expected the unguarded path to breach the cap; if this ever stops "
        "failing the race just got harder to hit, not fixed"
    )


# ---------------------------------------------------------------------------
# The fix
# ---------------------------------------------------------------------------
def test_reserve_is_atomic_under_concurrency(mandate):
    """N threads reserve at once; the mandate must never be over-committed."""
    def reserve(i):
        return store.reserve_headroom(mandate.id, LINE_PAISE, f"key-{i}")

    results = _run(reserve)
    granted = [r for r in results if getattr(r, "granted", False)]

    assert len(granted) == CAP_PAISE // LINE_PAISE, "wrong number of winners"
    assert store.spent_in_window(mandate.id, mandate.window) <= CAP_PAISE
    for r in results:
        assert not isinstance(r, Exception), f"thread raised: {r}"


def test_released_reservation_returns_headroom(mandate):
    r = store.reserve_headroom(mandate.id, CAP_PAISE, "key-full")
    assert r.granted
    assert store.reserve_headroom(mandate.id, 100, "key-next").granted is False

    store.release_reservation(r.id)
    assert store.spent_in_window(mandate.id, mandate.window) == 0
    assert store.reserve_headroom(mandate.id, 100, "key-next-2").granted is True


def test_committed_reservation_keeps_consuming_headroom(mandate):
    r = store.reserve_headroom(mandate.id, CAP_PAISE, "key-commit")
    store.commit_reservation(r.id, razorpay_ref="plink_test")
    assert store.spent_in_window(mandate.id, mandate.window) == CAP_PAISE
    assert store.reserve_headroom(mandate.id, 100, "key-after").granted is False


def test_expired_reservation_does_not_strand_headroom(mandate):
    r = store.reserve_headroom(mandate.id, CAP_PAISE, "key-stale", ttl_seconds=0)
    assert r.granted
    # A crashed turn must not hold the mandate hostage forever.
    assert store.reserve_headroom(mandate.id, CAP_PAISE, "key-fresh").granted is True


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
def test_same_idempotency_key_reuses_one_reservation(mandate):
    a = store.reserve_headroom(mandate.id, LINE_PAISE, "same-key")
    b = store.reserve_headroom(mandate.id, LINE_PAISE, "same-key")
    assert a.granted and b.granted
    assert a.id == b.id, "a retry must not consume headroom twice"
    assert store.spent_in_window(mandate.id, mandate.window) == LINE_PAISE


def test_concurrent_retries_of_one_key_reserve_once(mandate):
    """A retry storm on a single logical purchase must debit the cap once."""
    results = _run(lambda _i: store.reserve_headroom(mandate.id, LINE_PAISE, "retry-key"))
    ids = {r.id for r in results if getattr(r, "granted", False)}
    assert len(ids) == 1
    assert store.spent_in_window(mandate.id, mandate.window) == LINE_PAISE


def test_committed_key_replays_stored_result(mandate):
    r = store.reserve_headroom(mandate.id, LINE_PAISE, "replay-key")
    store.commit_reservation(r.id, razorpay_ref="plink_abc123")
    again = store.reserve_headroom(mandate.id, LINE_PAISE, "replay-key")
    assert again.replayed is True
    assert again.razorpay_ref == "plink_abc123"
    assert store.spent_in_window(mandate.id, mandate.window) == LINE_PAISE


# ---------------------------------------------------------------------------
# End-to-end: two agent turns checking out at the same instant
# ---------------------------------------------------------------------------
def test_two_concurrent_confirmations_cannot_both_issue(mandate):
    """The real shape of the attack: one mandate, two sessions, same moment."""
    from app.agent import confirm_checkout, handle_turn, reset_session
    from app.models import ChatRequest, CheckoutConfirmRequest

    # ₹899 parmigiano twice = ₹1,798 against a ₹1,000 cap. Exactly one may win.
    def buy(i):
        sid = f"race_{i}"
        proposal = handle_turn(
            ChatRequest(session_id=sid, message="add the parmigiano reggiano")
        )
        r = confirm_checkout(
            CheckoutConfirmRequest(
                session_id=sid,
                expected_cart_hash=proposal.cart_hash,
                idempotency_key=f"race-attempt-{i}",
            )
        )
        reset_session(sid)
        return r

    results = _run(buy, n=2)
    issued = [
        r
        for r in results
        if not isinstance(r, Exception)
        and any(
            t.name == "create_payment_link" and not t.blocked for t in r.tools
        )
    ]

    assert len(issued) == 1, f"expected exactly one link issuance, got {len(issued)}"
    assert store.spent_in_window(mandate.id, mandate.window) <= CAP_PAISE


def test_same_session_retry_is_idempotent_end_to_end(mandate):
    """A re-sent checkout inside one session must not charge twice."""
    from app.agent import confirm_checkout, handle_turn, reset_session
    from app.models import ChatRequest, CheckoutConfirmRequest

    sid = "retry_session"
    attempt_id = "retry-session-attempt"
    proposal = handle_turn(
        ChatRequest(session_id=sid, message="add the parmigiano reggiano")
    )
    first = confirm_checkout(
        CheckoutConfirmRequest(
            session_id=sid,
            expected_cart_hash=proposal.cart_hash,
            idempotency_key=attempt_id,
        )
    )
    ref = first.tools[0].result.get("id")

    # Client never saw the response and re-sends the same basket + key.
    replay_proposal = handle_turn(
        ChatRequest(session_id=sid, message="add the parmigiano reggiano")
    )
    second = confirm_checkout(
        CheckoutConfirmRequest(
            session_id=sid,
            expected_cart_hash=replay_proposal.cart_hash,
            idempotency_key=attempt_id,
        )
    )
    reset_session(sid)

    assert second.tools[0].result.get("replayed") is True
    assert second.tools[0].result.get("id") == ref
    assert store.spent_in_window(mandate.id, mandate.window) == 89_900
