"""The benchmark's claims, guarded by the test suite.

A benchmark that lives only in a script is a number someone once ran. These
tests make its two load-bearing claims — nothing violating gets through, and the
same order always gets the same answer — conditions for the build to be green.

A reduced corpus is used so the suite stays fast; the full run is
`python scripts/benchmark_agent_authorization.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from benchmark_agent_authorization import (  # noqa: E402
    COMPLIANT_FAMILIES,
    DIMENSIONS,
    FAMILIES,
    cap_only_authorises,
    decision_signature,
    run_case,
)

SEEDS = list(range(6))


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return [run_case(seed, family) for seed in SEEDS for family in FAMILIES]


def test_no_constructed_violation_is_ever_authorised(rows):
    """The one number that must be zero."""
    escaped = [(r["family"], r["seed"]) for r in rows if r["violation_escaped"]]
    assert not escaped, f"policy violations reached authorisation: {escaped}"


def test_no_legitimate_order_is_refused(rows):
    """False-positive cost. A layer that blocks everything scores perfectly above."""
    refused = [(r["family"], r["seed"]) for r in rows if r["false_positive"]]
    assert not refused, f"legitimate orders refused: {refused}"


def test_the_corpus_actually_contains_legitimate_boundary_cases(rows):
    """Guard against the false-positive test becoming vacuous.

    Three of the compliant families sit exactly on a boundary — cart total equal
    to the cap, on-hand equal to quantity, an item whose tags neighbour a blocked
    one. If they were dropped, `test_no_legitimate_order_is_refused` would still
    pass while measuring nothing.
    """
    for family in ("near_cap_compliant", "exact_stock_compliant", "lookalike_tag_compliant"):
        assert family in COMPLIANT_FAMILIES
        assert any(r["family"] == family for r in rows)
    assert sum(1 for r in rows if r["compliant"]) >= len(SEEDS) * 5


def test_decisions_are_deterministic(rows):
    """Replay identity. Deliberately NOT reported as pass^k.

    tau-bench's pass^k is an expectation over stochastic trials; on a decision
    path with no model in it, it is arithmetically 1 for every k and claims
    nothing. This asserts the narrower true thing: byte-identical output on
    replay. It is a regression guard.
    """
    for seed in SEEDS:
        for family in FAMILIES:
            sigs = {decision_signature(run_case(seed, family)) for _ in range(3)}
            assert len(sigs) == 1, f"{family}/{seed} gave {len(sigs)} different decisions"


def test_repair_never_widens_authority(rows):
    """A repaired order must cost no more than the envelope allowed.

    Repair is the growth mechanic, and it is also the most dangerous code path
    here: the one place the system changes a cart without asking the customer
    again. It may only ever narrow.
    """
    for r in rows:
        if r["repaired"]:
            assert r["settled_paise"] > 0
            assert not r["violation_escaped"]


def test_stop_deltas_are_never_auto_repaired(rows):
    """`stop` and `fresh_approval` mean a human decides. Never the builder."""
    for r in rows:
        if r["repaired"]:
            assert r["recoveries"] == ["repair"], (
                f"{r['family']}/{r['seed']} was auto-repaired despite {r['recoveries']}"
            )


def test_every_family_is_classified_into_one_policy_dimension():
    seen = [f for fams in DIMENSIONS.values() for f in fams]
    assert sorted(seen) == sorted(set(seen)), "a family appears in two dimensions"
    assert set(seen) == set(FAMILIES)


def test_exhausted_substitution_refuses_rather_than_inventing_a_candidate(rows):
    """Project invariant 13: no eligible candidate means Policy Delta or abort."""
    exhausted = [r for r in rows if r["family"] == "substitution_exhausted"]
    assert exhausted
    assert all(r["outcome"] == "REFUSED" for r in exhausted), (
        "a repair was found for a slot whose only candidate is out of stock"
    )


def test_a_spend_cap_alone_would_not_be_enough(rows):
    """The comparator that makes the whole exercise non-tautological.

    If a plain budget check scored the same as this layer, the layer would not be
    worth building — and a benchmark written by the author of the system under
    test proves nothing without an independent baseline on the same corpus.
    """
    violating = [r for r in rows if not r["compliant"]]
    cap_only_escapes = [
        r for r in violating if cap_only_authorises(r["seed"], r["family"])
    ]
    assert len(cap_only_escapes) > len(violating) * 0.5, (
        "A spend cap alone should authorise most of these violations. If it does "
        "not, the corpus has drifted towards cases a budget check already catches, "
        "and the benchmark is flattering itself."
    )
    assert not [r for r in violating if r["violation_escaped"]]


def test_held_out_seeds_are_actually_held_out():
    from benchmark_agent_authorization import DEV_SEEDS, HELD_OUT_SEEDS
    assert HELD_OUT_SEEDS, "a holdout of zero seeds is not a holdout"
    assert not set(DEV_SEEDS) & set(HELD_OUT_SEEDS)
