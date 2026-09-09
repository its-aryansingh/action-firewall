"""Outbound authorization: money leaving the merchant.

WHY THIS FILE EXISTS
--------------------
Everything else in this codebase governs money coming IN — an AI buyer proposes an
order and the layer decides whether it is inside what the customer approved.

But a merchant's agents also move money OUT. Razorpay's own Agent Studio ships a
Dispute Expert and a Subscription Recovery agent, and its published guardrail is
that "no agent takes an irreversible action without explicit merchant approval" —
a human in the loop for every single action. That is a supervisor, not a control,
and it does not scale past a few dozen a day.

The alternative is the same one this codebase already implements inbound: the
merchant approves a POLICY once, and a deterministic layer decides each action
against it. Only what the policy cannot resolve reaches a person.

Refunds are the right first outbound action because they are the ones that hurt:
daily, high volume, irreversible, and the classic failure — the same payment
refunded twice — is a real incident, not a hypothetical. `benchmark_concurrency.py`
measures exactly that race.

WHAT IS DELIBERATELY REUSED
---------------------------
The decision vocabulary. `EnvelopeDecision` and `PolicyDelta` are the same types
the inbound path returns, so a caller, a screen and an audit row do not have to
learn a second language for the same idea. What differs is only the policy object
and the checks, because a refund has no cart and an order has no reason code.

The registry, the exact one-use grant, atomic authorize-and-reserve, the single
compare-and-set dispatch owner and the UNKNOWN outcome are all action-agnostic
already, and are not duplicated here.
"""
from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .authorization import digest
from .models import EnvelopeDecision, PolicyDelta

#: A refund the layer clamps rather than refuses still needs a floor, or a
#: "repair" could quietly become a ₹0 refund that closes a real complaint.
MIN_REFUND_PAISE = 100


class RefundPolicy(BaseModel):
    """What the merchant approved, once, for their agents to do with refunds.

    Hash-bound for the same reason the Purchase Envelope is: a policy that can be
    widened after approval is not a policy, and the version fence has to have
    something to fence.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    merchant_id: str
    #: Largest single refund an agent may issue without a human.
    max_refund_paise: StrictInt = Field(..., gt=0)
    #: Share of the original payment an agent may return. 1.0 permits a full
    #: refund; below 1.0 keeps restocking or shipping cost with the merchant.
    max_refund_ratio: float = Field(default=1.0, gt=0.0, le=1.0)
    #: How old an order may be. Past this, a human decides.
    window_days: StrictInt = Field(..., gt=0, le=365)
    #: Total an agent may refund across all orders in a rolling day.
    daily_cap_paise: StrictInt = Field(..., gt=0)
    #: Reasons the merchant will not let an agent settle unattended.
    escalate_reasons: list[str] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)
    policy_hash: str = ""

    def payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "merchant_id": self.merchant_id,
            "max_refund_paise": self.max_refund_paise,
            "max_refund_ratio": self.max_refund_ratio,
            "window_days": self.window_days,
            "daily_cap_paise": self.daily_cap_paise,
            "escalate_reasons": sorted(self.escalate_reasons),
            "version": self.version,
        }


def compute_policy_hash(policy: RefundPolicy) -> str:
    return digest(policy.payload())


class RefundProposal(BaseModel):
    """What an agent is asking to do. Every figure here is server-supplied.

    The agent names a payment and an amount. It does not get to assert what the
    original payment was worth, how much has already been returned, or how old
    the order is — those are read from the merchant's own records, because an
    agent that could assert them could authorise anything.
    """

    model_config = ConfigDict(extra="forbid")

    payment_id: str = Field(..., min_length=4, max_length=64)
    amount_paise: StrictInt = Field(..., gt=0)
    reason: str = Field(..., min_length=1, max_length=120)
    # Server-side facts
    original_amount_paise: StrictInt = Field(..., gt=0)
    already_refunded_paise: StrictInt = Field(default=0, ge=0)
    order_age_days: StrictInt = Field(..., ge=0)
    refunded_today_paise: StrictInt = Field(default=0, ge=0)

    @property
    def refundable_remainder_paise(self) -> int:
        return max(0, self.original_amount_paise - self.already_refunded_paise)


def verify_refund(
    policy: RefundPolicy,
    proposal: RefundProposal,
    now: float | None = None,
) -> EnvelopeDecision:
    """Decide one proposed refund against one merchant-approved policy.

    Deterministic and side-effect free. Returns the same decision shape the
    inbound path returns, so one screen renders both.
    """
    _ = now if now is not None else time.time()
    deltas: list[PolicyDelta] = []

    def delta(field: str, expected: object, actual: object,
              recovery: Literal["repair", "fresh_approval", "stop"]) -> None:
        deltas.append(PolicyDelta(field=field, expected=str(expected),
                                  actual=str(actual), recovery=recovery))

    if policy.policy_hash and policy.policy_hash != compute_policy_hash(policy):
        # A widened policy is the one failure that must never be repairable.
        delta("policy_hash", "canonical policy digest", policy.policy_hash, "stop")

    remainder = proposal.refundable_remainder_paise

    # 1. Nothing left to refund. This is the double-refund case, and it is `stop`
    #    rather than `repair`: there is no smaller amount that would be correct.
    if remainder <= 0:
        delta(
            "already_refunded_paise",
            f"< {proposal.original_amount_paise}",
            f"{proposal.already_refunded_paise} already returned on {proposal.payment_id}",
            "stop",
        )
    # 2. More than is left. Clamping to the remainder is the right answer: the
    #    customer's complaint is real, only the arithmetic is wrong.
    elif proposal.amount_paise > remainder:
        delta(
            "amount_paise",
            f"<= {remainder} refundable",
            f"{proposal.amount_paise} requested",
            "repair",
        )

    # 3. Merchant keeps a share. Same shape: clamp, do not refuse.
    ratio_cap = int(proposal.original_amount_paise * policy.max_refund_ratio)
    if remainder > 0 and proposal.amount_paise > ratio_cap:
        delta(
            "max_refund_ratio",
            f"<= {ratio_cap} ({policy.max_refund_ratio:.0%} of the payment)",
            f"{proposal.amount_paise} requested",
            "repair",
        )

    # 4. Above what an agent may settle alone. A person decides — but the request
    #    survives as one question rather than dying as a refusal.
    if proposal.amount_paise > policy.max_refund_paise:
        delta(
            "max_refund_paise",
            f"<= {policy.max_refund_paise} without a human",
            f"{proposal.amount_paise} requested",
            "fresh_approval",
        )

    # 5. Outside the window the merchant approved.
    if proposal.order_age_days > policy.window_days:
        delta(
            "window_days",
            f"<= {policy.window_days} days old",
            f"{proposal.order_age_days} days old",
            "fresh_approval",
        )

    # 6. The day's total. Deliberately checked here AND re-checked inside the
    #    atomic reservation before dispatch: this read is advisory, and two agents
    #    reading it at once would both believe they fit.
    if proposal.refunded_today_paise + proposal.amount_paise > policy.daily_cap_paise:
        delta(
            "daily_cap_paise",
            f"<= {policy.daily_cap_paise} per day",
            f"{proposal.refunded_today_paise + proposal.amount_paise} would be reached",
            "fresh_approval",
        )

    # 7. Reasons the merchant will not automate.
    reason_key = proposal.reason.strip().lower()
    for blocked in policy.escalate_reasons:
        if blocked.strip().lower() in reason_key:
            delta("reason", f"not '{blocked}'", proposal.reason, "fresh_approval")
            break

    allowed = not deltas
    if allowed:
        code, message = "ALLOW_REFUND", (
            f"Refund of ₹{proposal.amount_paise / 100:,.2f} is inside the policy "
            f"the merchant approved. No human needed."
        )
    elif any(d.recovery == "stop" for d in deltas):
        code, message = "BLOCK_REFUND", (
            "This refund cannot be issued and cannot be corrected automatically."
        )
    elif all(d.recovery == "repair" for d in deltas):
        code, message = "REPAIR_REFUND", (
            "The complaint is valid; the amount is not. A corrected refund is available."
        )
    else:
        code, message = "ESCALATE_REFUND", (
            "This is outside what an agent may settle alone. One question for a person."
        )

    return EnvelopeDecision(
        allowed=allowed,
        code=code,
        envelope_id=policy.id,
        envelope_version=policy.version,
        quote_total_paise=proposal.amount_paise,
        deltas=deltas,
        human_message=message,
    )


def repair_refund(policy: RefundPolicy, proposal: RefundProposal) -> RefundProposal | None:
    """The largest refund that IS inside the policy, or None if none exists.

    This is the outbound half of the repair ladder. Every other refund guardrail
    answers "no"; this one answers "not that much — this much", which is the
    difference between a refused complaint and a settled one.

    It may only ever narrow. A repair that produced a LARGER refund than asked
    would be the layer widening the merchant's authority on its own, which is the
    one thing it must never do.
    """
    remainder = proposal.refundable_remainder_paise
    if remainder <= 0:
        return None

    ceiling = min(
        proposal.amount_paise,
        remainder,
        int(proposal.original_amount_paise * policy.max_refund_ratio),
        policy.max_refund_paise,
        max(0, policy.daily_cap_paise - proposal.refunded_today_paise),
    )
    if ceiling < MIN_REFUND_PAISE:
        return None

    repaired = proposal.model_copy(update={"amount_paise": ceiling})
    if not verify_refund(policy, repaired).allowed:
        # Something outside the amount blocks it — age, reason, a widened policy.
        # Those are not arithmetic and must not be silently repaired away.
        return None
    return repaired
