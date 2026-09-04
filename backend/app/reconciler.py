"""Provider reconciliation — the only path that can close a money action.

Until this module existed, `settled` was a state the schema knew about and
nothing could ever write, so `confirmed_test_payment_value_paise` was
structurally zero. That made invariant 10 ("ACTION_ISSUED is not payment,
capture, settlement, or recovered revenue") true only because settlement was
unreachable. Respecting a distinction you cannot exercise is weaker than
respecting one you can.

The rule this module enforces is that a settlement claim is an **observation,
not an assertion**. Callers pass a grant id and nothing else. This module asks
the provider what it thinks happened and applies the answer. There is no code
path — HTTP or otherwise — by which a caller can declare that money moved.

State transitions, and the evidence each requires:

    action_issued --provider says paid------------> settled
    action_issued --provider says anything else---> action_issued (unchanged)
    unknown       --provider knows the action-----> action_issued / settled
    unknown       --provider has no such action---> definitive_failure
    unknown       --provider unreachable / vague--> unknown (exposure retained)

The last line is invariant 9 and is the reason this is a reconciler rather than
a retry loop: an ambiguous answer must leave the exposure exactly where it was.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import store
from .mcp_client import get_client
from .models import ActionGrant, ActionState

#: Razorpay payment-link states that mean money has actually been collected.
#: `partially_paid` is deliberately excluded: this MVP registers only
#: `accept_partial: False` actions, so a partial payment is an anomaly to
#: surface rather than a settlement to record.
PAID_STATES = {"paid"}

#: States that mean the link exists and is simply not paid yet.
OPEN_STATES = {"created", "issued", "partially_paid"}

#: States that mean this action will never collect.
DEAD_STATES = {"cancelled", "expired"}


@dataclass(frozen=True)
class Observation:
    """What the provider said, normalised. Never constructed from user input."""
    reachable: bool
    provider_status: str | None
    amount_paid_paise: int
    raw: dict[str, Any]
    error: str | None = None

    @property
    def is_paid(self) -> bool:
        return self.reachable and (self.provider_status or "").lower() in PAID_STATES

    @property
    def is_dead(self) -> bool:
        return self.reachable and (self.provider_status or "").lower() in DEAD_STATES

    @property
    def is_open(self) -> bool:
        return self.reachable and (self.provider_status or "").lower() in OPEN_STATES


@dataclass(frozen=True)
class Reconciliation:
    grant_id: str
    before: ActionState
    after: ActionState
    changed: bool
    observation: Observation
    note: str


def observe(provider_ref: str | None) -> Observation:
    """Ask the provider for its own view. The only accepted source of truth."""
    if not provider_ref:
        return Observation(False, None, 0, {}, error="NO_PROVIDER_REFERENCE")
    client = get_client()
    try:
        payload = client.fetch_action_status(provider_ref)
    except Exception as exc:                      # network, auth, provider down
        # Unreachable is not the same as unpaid. Say so, and change nothing.
        return Observation(False, None, 0, {}, error=str(exc)[:200])

    status = str(payload.get("status") or "").lower() or None
    amount_paid = payload.get("amount_paid")
    return Observation(
        reachable=True,
        provider_status=status,
        amount_paid_paise=int(amount_paid) if isinstance(amount_paid, int) else 0,
        raw=payload,
    )


def reconcile(grant_id: str) -> Reconciliation:
    """Resolve one action against the provider's own record.

    Takes a grant id and nothing else. Whatever the caller believes about the
    payment is irrelevant; only `observe()` decides.
    """
    grant = store.get_action_grant(grant_id)
    if grant is None:
        raise LookupError("UNKNOWN_GRANT")

    before = grant.state
    if before not in (ActionState.ACTION_ISSUED, ActionState.UNKNOWN):
        return Reconciliation(
            grant_id, before, before, False,
            Observation(False, None, 0, {}, error="NOT_RECONCILABLE"),
            f"{before.value} is already terminal; nothing to reconcile.",
        )

    obs = observe(grant.provider_ref)

    if not obs.reachable:
        # Invariant 9. We learned nothing, so we change nothing — including
        # not freeing the headroom this action is holding.
        return Reconciliation(
            grant_id, before, before, False, obs,
            "Provider could not be read. Exposure retained and no redispatch.",
        )

    if obs.is_paid:
        if before is ActionState.ACTION_ISSUED:
            store.settle_issued_action(
                grant_id, provider_ref=grant.provider_ref, result=obs.raw)
        else:
            store.reconcile_unknown(
                grant_id, accepted=True, provider_ref=grant.provider_ref,
                result=obs.raw, settled=True)
        return Reconciliation(
            grant_id, before, ActionState.SETTLED, True, obs,
            f"Provider reports paid; {obs.amount_paid_paise} paise collected.",
        )

    if obs.is_dead:
        if before is ActionState.UNKNOWN:
            store.reconcile_unknown(
                grant_id, accepted=False, provider_ref=grant.provider_ref,
                result=obs.raw)
            return Reconciliation(
                grant_id, before, ActionState.DEFINITIVE_FAILURE, True, obs,
                f"Provider reports {obs.provider_status}; exposure released.",
            )
        # An issued link that expired is a definite non-collection, but this MVP
        # has no issued -> definitive_failure transition and inventing one here
        # would be a second logical change. Reported, not acted on.
        return Reconciliation(
            grant_id, before, before, False, obs,
            f"Provider reports {obs.provider_status}. Issued actions are not "
            f"auto-failed in this MVP; surfaced for an operator.",
        )

    if before is ActionState.UNKNOWN and obs.is_open:
        # We now know the action reached the provider and is live. That is a
        # real resolution of the ambiguity even though no money has moved.
        store.reconcile_unknown(
            grant_id, accepted=True, provider_ref=grant.provider_ref,
            result=obs.raw, settled=False)
        return Reconciliation(
            grant_id, before, ActionState.ACTION_ISSUED, True, obs,
            "Provider confirms the action exists and is unpaid; no longer ambiguous.",
        )

    return Reconciliation(
        grant_id, before, before, False, obs,
        f"Provider reports {obs.provider_status}; not yet collected.",
    )


def reconcile_open_actions(limit: int = 50) -> list[Reconciliation]:
    """Sweep everything still holding exposure. Safe to run repeatedly."""
    out: list[Reconciliation] = []
    for grant in store.open_actions_for_reconciliation(limit=limit):
        try:
            out.append(reconcile(grant.id))
        except Exception as exc:                  # one bad row must not stop the sweep
            store.log_event(
                event="RECONCILIATION_ERROR", mandate_id=grant.mandate_id,
                payload={"grant_id": grant.id, "error": str(exc)[:200]})
    return out
