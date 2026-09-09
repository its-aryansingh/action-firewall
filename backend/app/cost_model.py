"""What each kind of wrong decision costs the merchant, in rupees.

WHY THIS EXISTS
---------------
An authorization layer is easy to argue for on safety and hard to argue for on
money, because its output is orders that did NOT go wrong. This turns the
benchmark's counts into a rupee comparison between three ways a merchant could
run their store, so the case can be made in the units a merchant thinks in.

The approach is borrowed openly from a competing entry (`TarunMhanta30/viveka`,
`eval/cost_model.py`), which prices false negatives and false positives and then
reports total cost per configuration. It is a good idea and it deserves to be
copied rather than reinvented. What is different here: their layer scores risk
and hands the decision on, so their false positive is a step-up. This one
authorises or refuses, and it has a third outcome — repair — which is the only
one that puts money back.

WHAT THIS IS NOT
----------------
**Every number below is an assumption, not a measurement.** This module models
consequences; it does not observe them. Nothing here is evidence of fraud
prevented, chargebacks avoided, or revenue recovered, and the output is labelled
so it cannot be quoted as if it were. `sensitivity()` exists so a reader can see
which assumptions actually move the answer, and change the ones they disagree
with.

The one input that is NOT an assumption is the outcome mix — how many proposals
were authorised, refused, repaired or let through. That comes from
`benchmark_agent_authorization.py` running the real verifier.
"""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CostAssumptions:
    """Stated, adjustable, and deliberately conservative where uncertain."""

    #: Handling a wrong order after the fact: the customer contact, the pickup,
    #: the credit note, the staff time. A flat charge on top of the order value.
    remediation_paise: int = 30_000  # ₹300

    #: A refused order is not automatically a lost customer — some buyers retry
    #: or fall back to a human. This is the share that does not come back.
    refusal_loss_rate: float = 0.60

    #: The evidence anchor for the number above, so a reader can check it:
    #: ACI Worldwide / YouGov, N=2,080 UK adults, fieldwork 19-22 June 2026 --
    #: 60% would stop using an AI shopping agent after ONE mistake. That measures
    #: consumers dropping an AGENT, not a merchant, so it is used here as an
    #: order-of-magnitude anchor for abandonment after a bad experience and
    #: nothing more.
    refusal_loss_rate_source: str = "ACI/YouGov Jun 2026, N=2,080 — anchor only"

    #: A wrong order that reaches a customer risks the relationship, not just the
    #: order. Set to zero to see the model with this removed entirely.
    relationship_penalty_paise: int = 100_000  # ₹1,000

    #: A repaired order completes, so the merchant keeps the revenue. It is not
    #: free: the delta round trip costs the agent a call and the customer a wait.
    repair_friction_paise: int = 2_000  # ₹20


@dataclass(frozen=True)
class OutcomeMix:
    """Counts and rupee totals from an actual benchmark run. Not assumptions."""

    authorised_correctly_paise: int = 0
    authorised_correctly_count: int = 0

    #: A policy violation that was authorised. The failure that costs the most.
    violations_authorised_paise: int = 0
    violations_authorised_count: int = 0

    #: A legitimate order that was refused. The cost of being strict.
    legitimate_refused_paise: int = 0
    legitimate_refused_count: int = 0

    #: Refused, corrected, then completed. The only outcome that adds revenue.
    repaired_paise: int = 0
    repaired_count: int = 0

    #: A violation correctly refused. Costs nothing and earns nothing — the order
    #: was never the merchant's to keep.
    violations_refused_count: int = 0


def cost_of(mix: OutcomeMix, a: CostAssumptions | None = None) -> dict[str, int]:
    """Total cost of one configuration, in paise, itemised.

    Sign convention: every figure is a COST. Repair appears as a negative cost,
    because it is revenue the merchant keeps that a refuse-only layer would lose.
    """
    a = a or CostAssumptions()

    # A violation that got through: the order value is at risk, plus the cost of
    # putting it right, plus the relationship.
    violation_cost = mix.violations_authorised_paise + (
        mix.violations_authorised_count * (a.remediation_paise + a.relationship_penalty_paise)
    )

    # A legitimate order refused: only the share that does not come back.
    refusal_cost = int(mix.legitimate_refused_paise * a.refusal_loss_rate)

    # A repaired order is revenue kept, minus the friction of the round trip.
    repair_benefit = mix.repaired_paise - (mix.repaired_count * a.repair_friction_paise)

    total = violation_cost + refusal_cost - repair_benefit
    return {
        "violations_authorised_paise": violation_cost,
        "legitimate_refused_paise": refusal_cost,
        "revenue_kept_by_repair_paise": -repair_benefit,
        "total_paise": total,
    }


def compare(configs: dict[str, OutcomeMix], a: CostAssumptions | None = None) -> dict:
    """Price several configurations against the same assumptions.

    The comparison is the point. An absolute rupee figure from a model is worth
    very little; the ordering between configurations under the same assumptions
    is worth something, and `sensitivity()` says how much.
    """
    a = a or CostAssumptions()
    priced = {name: cost_of(mix, a) for name, mix in configs.items()}
    best = min(priced, key=lambda k: priced[k]["total_paise"])
    baseline = max(priced, key=lambda k: priced[k]["total_paise"])
    return {
        "assumptions": {
            "remediation_paise": a.remediation_paise,
            "refusal_loss_rate": a.refusal_loss_rate,
            "refusal_loss_rate_source": a.refusal_loss_rate_source,
            "relationship_penalty_paise": a.relationship_penalty_paise,
            "repair_friction_paise": a.repair_friction_paise,
        },
        "configurations": priced,
        "lowest_cost": best,
        "highest_cost": baseline,
        "difference_paise": priced[baseline]["total_paise"] - priced[best]["total_paise"],
        "caveat": (
            "Modelled consequences under stated assumptions, not observed outcomes. "
            "Not a claim of fraud prevented, chargebacks avoided, or revenue recovered. "
            "Only the outcome mix is measured; every price attached to an outcome is "
            "an assumption, and sensitivity() shows which ones change the answer."
        ),
    }


def sensitivity(configs: dict[str, OutcomeMix], base: CostAssumptions | None = None) -> dict:
    """Vary each assumption alone and report whether the ordering survives.

    This is the part that makes the model worth publishing. If the answer flips
    when one number is halved, the model is a rhetorical device and should be
    labelled as one; if it survives every single-parameter swing, the ordering is
    load-bearing even for a reader who disagrees with the numbers.
    """
    base = base or CostAssumptions()
    winner = compare(configs, base)["lowest_cost"]

    sweeps: dict[str, list[CostAssumptions]] = {
        "remediation_paise": [replace(base, remediation_paise=v) for v in (0, 10_000, 100_000)],
        "refusal_loss_rate": [replace(base, refusal_loss_rate=v) for v in (0.0, 0.3, 1.0)],
        "relationship_penalty_paise": [
            replace(base, relationship_penalty_paise=v) for v in (0, 50_000, 500_000)
        ],
        "repair_friction_paise": [replace(base, repair_friction_paise=v) for v in (0, 10_000)],
    }

    results: dict[str, dict] = {}
    for name, variants in sweeps.items():
        winners = [compare(configs, v)["lowest_cost"] for v in variants]
        results[name] = {
            "winners_across_sweep": sorted(set(winners)),
            "changes_the_answer": len(set(winners + [winner])) > 1,
        }

    fragile = [k for k, v in results.items() if v["changes_the_answer"]]
    return {
        "baseline_winner": winner,
        "per_assumption": results,
        "assumptions_that_change_the_answer": fragile,
        "ordering_is_robust": not fragile,
    }
