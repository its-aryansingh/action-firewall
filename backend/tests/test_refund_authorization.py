"""Outbound authorization — money leaving the merchant.

The inbound path asks "may this cart be bought?". This asks "may this refund be
issued?", against a policy the merchant approved once. Same decision types, same
repair vocabulary, same closed action registry.

The case that matters most here is the double refund: the same payment returned
twice. It is the outbound analogue of a double-spend, it is irreversible, and it
is a real incident rather than a hypothetical.
"""
from __future__ import annotations

import pytest

from app.actions import ACTION_REGISTRY, canonicalize_action
from app.refund import (
    MIN_REFUND_PAISE,
    RefundPolicy,
    RefundProposal,
    compute_policy_hash,
    repair_refund,
    verify_refund,
)

ORDER_PAISE = 80_000  # ₹800 order


def _policy(**overrides) -> RefundPolicy:
    base = dict(
        id="rpol_demo",
        merchant_id="merchant_freshbasket",
        max_refund_paise=50_000,     # ₹500 without a human
        max_refund_ratio=1.0,
        window_days=30,
        daily_cap_paise=200_000,     # ₹2,000/day across all orders
        escalate_reasons=["chargeback", "fraud"],
        version=1,
    )
    base.update(overrides)
    policy = RefundPolicy(**base)
    return policy.model_copy(update={"policy_hash": compute_policy_hash(policy)})


def _proposal(**overrides) -> RefundProposal:
    base = dict(
        payment_id="pay_ABC123",
        amount_paise=20_000,
        reason="item damaged in transit",
        original_amount_paise=ORDER_PAISE,
        already_refunded_paise=0,
        order_age_days=3,
        refunded_today_paise=0,
    )
    base.update(overrides)
    return RefundProposal(**base)


# ---------------------------------------------------------------------------
# The registry actually admitted a second action
# ---------------------------------------------------------------------------

def test_refund_is_a_registered_action():
    assert "refund" in ACTION_REGISTRY
    canonical = canonicalize_action("refund", {
        "payment_id": "pay_ABC123", "amount": 20_000, "currency": "INR",
        "speed": "normal", "receipt": "rf_1", "notes": {},
    })
    assert canonical.amount_paise == 20_000
    assert canonical.name == "refund"


def test_the_registry_is_still_closed():
    from app.actions import ActionNotRegistered
    with pytest.raises(ActionNotRegistered):
        canonicalize_action("payout", {"amount": 1})


def test_an_agent_cannot_choose_the_expensive_refund_speed():
    """`optimum` costs the merchant more. That is a business decision."""
    from app.actions import InvalidActionArguments
    with pytest.raises(InvalidActionArguments):
        canonicalize_action("refund", {
            "payment_id": "pay_ABC123", "amount": 20_000, "currency": "INR",
            "speed": "optimum", "receipt": "rf_1", "notes": {},
        })


# ---------------------------------------------------------------------------
# The ordinary case
# ---------------------------------------------------------------------------

def test_a_refund_inside_the_policy_is_authorised():
    decision = verify_refund(_policy(), _proposal())
    assert decision.allowed
    assert decision.code == "ALLOW_REFUND"
    assert not decision.deltas


# ---------------------------------------------------------------------------
# The double refund — the one that costs real money
# ---------------------------------------------------------------------------

def test_a_fully_refunded_payment_cannot_be_refunded_again():
    decision = verify_refund(
        _policy(),
        _proposal(already_refunded_paise=ORDER_PAISE, amount_paise=20_000),
    )
    assert not decision.allowed
    assert decision.code == "BLOCK_REFUND"
    assert any(d.field == "already_refunded_paise" for d in decision.deltas)


def test_a_double_refund_is_stop_not_repair():
    """There is no smaller amount that would be correct, so it must not clamp."""
    policy, proposal = _policy(), _proposal(already_refunded_paise=ORDER_PAISE)
    decision = verify_refund(policy, proposal)
    assert all(d.recovery == "stop" for d in decision.deltas if
               d.field == "already_refunded_paise")
    assert repair_refund(policy, proposal) is None


def test_a_partial_second_refund_is_clamped_to_what_remains():
    policy = _policy()
    proposal = _proposal(already_refunded_paise=60_000, amount_paise=40_000)
    decision = verify_refund(policy, proposal)

    assert not decision.allowed
    assert decision.code == "REPAIR_REFUND"

    repaired = repair_refund(policy, proposal)
    assert repaired is not None
    assert repaired.amount_paise == 20_000, "only ₹200 of the ₹800 order remains"
    assert verify_refund(policy, repaired).allowed


# ---------------------------------------------------------------------------
# Over-refund, the other way money leaks
# ---------------------------------------------------------------------------

def test_refunding_more_than_the_order_is_clamped_not_refused():
    policy = _policy()
    proposal = _proposal(amount_paise=ORDER_PAISE + 50_000)
    decision = verify_refund(policy, proposal)
    assert not decision.allowed

    repaired = repair_refund(policy, proposal)
    assert repaired is not None
    assert repaired.amount_paise <= ORDER_PAISE
    assert repaired.amount_paise <= policy.max_refund_paise


def test_the_merchant_can_keep_a_share():
    # max_refund_paise is raised so the RATIO is the binding constraint and this
    # test measures the thing it is named for. With the default ₹500 cap the
    # repair clamps to ₹500, which is correct but tests a different rule.
    policy = _policy(max_refund_ratio=0.8, max_refund_paise=100_000)
    decision = verify_refund(policy, _proposal(amount_paise=ORDER_PAISE))
    assert not decision.allowed
    assert any(d.field == "max_refund_ratio" for d in decision.deltas)

    repaired = repair_refund(policy, _proposal(amount_paise=ORDER_PAISE))
    assert repaired is not None
    assert repaired.amount_paise == 64_000  # 80% of ₹800


def test_repair_clamps_to_the_tightest_limit_not_the_first_one():
    """Four ceilings apply at once; the repair must respect all of them."""
    policy = _policy(max_refund_paise=50_000, max_refund_ratio=0.8)
    repaired = repair_refund(policy, _proposal(amount_paise=ORDER_PAISE))
    assert repaired is not None
    assert repaired.amount_paise == 50_000, (
        "₹500 per-refund cap is tighter than 80% of ₹800 (₹640) and must win"
    )


# ---------------------------------------------------------------------------
# Escalation — stolen, deliberately, from the field
# ---------------------------------------------------------------------------

def test_a_large_refund_escalates_rather_than_blocking():
    """Not every refusal is a dead end. Some are one question for a person."""
    decision = verify_refund(_policy(max_refund_paise=10_000),
                             _proposal(amount_paise=20_000))
    assert not decision.allowed
    assert decision.code == "ESCALATE_REFUND"
    assert any(d.recovery == "fresh_approval" for d in decision.deltas)


def test_a_stale_order_escalates():
    decision = verify_refund(_policy(window_days=30), _proposal(order_age_days=90))
    assert decision.code == "ESCALATE_REFUND"
    assert any(d.field == "window_days" for d in decision.deltas)


def test_the_daily_cap_escalates():
    decision = verify_refund(
        _policy(daily_cap_paise=200_000),
        _proposal(refunded_today_paise=195_000, amount_paise=20_000),
    )
    assert decision.code == "ESCALATE_REFUND"
    assert any(d.field == "daily_cap_paise" for d in decision.deltas)


def test_reasons_the_merchant_will_not_automate():
    decision = verify_refund(_policy(), _proposal(reason="Customer filed a chargeback"))
    assert not decision.allowed
    assert any(d.field == "reason" for d in decision.deltas)


# ---------------------------------------------------------------------------
# The policy itself
# ---------------------------------------------------------------------------

def test_a_widened_policy_is_never_repairable():
    """The hash fences the policy exactly as the envelope hash fences a purchase."""
    policy = _policy()
    widened = policy.model_copy(update={"max_refund_paise": 10_000_000})
    decision = verify_refund(widened, _proposal())

    assert not decision.allowed
    assert decision.code == "BLOCK_REFUND"
    assert any(d.field == "policy_hash" and d.recovery == "stop" for d in decision.deltas)
    assert repair_refund(widened, _proposal()) is None


def test_repair_only_ever_narrows():
    policy = _policy()
    for requested in (5_000, 20_000, 50_000, ORDER_PAISE, ORDER_PAISE * 3):
        proposal = _proposal(amount_paise=requested)
        repaired = repair_refund(policy, proposal)
        if repaired is not None:
            assert repaired.amount_paise <= requested, "repair widened the refund"
            assert verify_refund(policy, repaired).allowed


def test_repair_refuses_rather_than_issuing_a_token_amount():
    """A clamp that reaches near-zero is not a settlement, it is an insult."""
    policy = _policy(daily_cap_paise=200_000)
    proposal = _proposal(refunded_today_paise=199_950, amount_paise=20_000)
    repaired = repair_refund(policy, proposal)
    assert repaired is None or repaired.amount_paise >= MIN_REFUND_PAISE


def test_escalation_is_never_silently_repaired():
    """Age and reason are not arithmetic; no amount fixes them."""
    policy = _policy(window_days=30)
    assert repair_refund(policy, _proposal(order_age_days=90)) is None
    assert repair_refund(policy, _proposal(reason="suspected fraud")) is None


def test_the_decision_shape_matches_the_inbound_path():
    """One vocabulary. A screen that renders an order decision renders this one."""
    decision = verify_refund(_policy(), _proposal(amount_paise=ORDER_PAISE * 2))
    assert hasattr(decision, "allowed") and hasattr(decision, "deltas")
    for d in decision.deltas:
        assert d.recovery in ("repair", "fresh_approval", "stop")
        assert d.field and d.expected and d.actual
