"""Reproducible synthetic evaluation for the deterministic envelope gate.

This evaluates authorization correctness, not payment conversion uplift. It
prints JSON to stdout and never calls a network service.
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.envelope import (  # noqa: E402
    build_quote,
    compute_envelope_hash,
    compute_quote_hash,
    verify_quote,
)
from app.models import (  # noqa: E402
    AutopilotScenario,
    Cart,
    CartLine,
    EnvelopeSlot,
    EnvelopeStatus,
    PurchaseEnvelope,
)

GOAL_FIXTURES: list[tuple[str, list[EnvelopeSlot]]] = [
    (
        "pasta dinner",
        [
            EnvelopeSlot(id="pasta", label="Pasta", required_tags=["pasta", "staple"]),
            EnvelopeSlot(id="sauce", label="Tomato pasta sauce", required_tags=["pasta", "sauce"]),
            EnvelopeSlot(id="herb", label="Fresh Italian herb", required_tags=["italian", "fresh", "herb"]),
        ],
    ),
    (
        "breakfast run",
        [
            EnvelopeSlot(id="bread", label="Bread", required_tags=["bread"]),
            EnvelopeSlot(id="dairy", label="Dairy", required_tags=["dairy"]),
            EnvelopeSlot(id="beverage", label="Beverage", required_tags=["beverage"]),
        ],
    ),
    (
        "office snacks",
        [
            EnvelopeSlot(id="snack", label="Snacks", required_tags=["snack"]),
            EnvelopeSlot(id="beverage", label="Beverage", required_tags=["beverage"]),
        ],
    ),
    (
        "cleaning restock",
        [
            EnvelopeSlot(id="cleaning", label="Cleaning", required_tags=["cleaning"]),
            EnvelopeSlot(id="household", label="Household", required_tags=["household"]),
        ],
    ),
    (
        "bathroom restock",
        [
            EnvelopeSlot(id="bath", label="Bath", required_tags=["bath"]),
            EnvelopeSlot(id="personal", label="Personal care", required_tags=["personal"]),
        ],
    ),
    (
        "indian pantry",
        [
            EnvelopeSlot(id="indian", label="Indian staple", required_tags=["indian"]),
            EnvelopeSlot(id="bulk", label="Bulk grocery", required_tags=["bulk"]),
            EnvelopeSlot(id="oil", label="Cooking oil", required_tags=["oil", "cooking"]),
        ],
    ),
    (
        "fresh produce box",
        [
            EnvelopeSlot(id="produce", label="Fresh vegetables", required_tags=["fresh", "vegetable"]),
            EnvelopeSlot(id="healthy", label="Healthy produce", required_tags=["healthy"]),
        ],
    ),
    (
        "cheese board",
        [
            EnvelopeSlot(id="cheese", label="Cheese", required_tags=["cheese"]),
            EnvelopeSlot(id="bakery", label="Bakery", required_tags=["bakery"]),
        ],
    ),
    (
        "protein top-up",
        [
            EnvelopeSlot(id="protein", label="Protein", required_tags=["protein"]),
            EnvelopeSlot(id="dairy", label="Dairy", required_tags=["dairy"]),
        ],
    ),
    (
        "desk gadgets",
        [
            EnvelopeSlot(id="electronics", label="Electronics", required_tags=["electronics"]),
            EnvelopeSlot(id="gadget", label="Desk gadget", required_tags=["gadget"]),
        ],
    ),
]

SEEDS = list(range(50))
FAMILIES = (
    "normal",
    "stock_loss",
    "price_drift",
    "merchant_drift",
    "fulfillment_drift",
    "extra_blocked_item",
    "catalog_fact_tamper",
    "expired_envelope",
    "slot_unsatisfiable",
    "duplicate_slot_fill",
    "quantity_mismatch",
    "quote_hash_tamper",
    "substitution_exhausted",
)


def active_envelope(seed: int, family: str) -> PurchaseEnvelope:
    rng = random.Random(seed)
    goal_name, slots = GOAL_FIXTURES[seed % len(GOAL_FIXTURES)]
    created = 1_800_000_000.0 + seed

    # Temporary envelope to derive cheapest quote
    temp_env = PurchaseEnvelope(
        id=f"env_{seed}",
        user_id="user_demo",
        agent_id=f"agent_safe_autopilot:{seed}",
        label=goal_name,
        goal=f"Buy supplies for {goal_name}",
        merchant_id="merchant_demo",
        max_total_paise=10_000_000,
        fulfillment_profile_id="profile_home",
        delivery_deadline=created + 2700,
        expires_at=created + 3600,
        slots=slots,
        blocked_categories=["gift_cards"],
        status=EnvelopeStatus.ACTIVE,
        version=2,
        envelope_hash="",
        mandate_id=f"evaluation-policy-{seed}",
        created_at=created,
        updated_at=created,
    )
    quote, _ = build_quote(temp_env, AutopilotScenario.NORMAL, now=created)
    sub_quote, _ = build_quote(temp_env, AutopilotScenario.STOCK_LOSS, now=created)
    cheapest_paise = quote.cart.total_paise
    sub_paise = sub_quote.cart.total_paise
    max_needed = max(cheapest_paise, sub_paise)

    # For roughly a third of seeds under price_drift, set cap below cheapest cart so cap genuinely binds
    if family == "price_drift" and seed % 3 == 0:
        max_total_paise = max(100, cheapest_paise - 100)
    else:
        # Generous headroom for in-bounds and non-budget-binding families
        max_total_paise = max_needed + rng.randint(20_000, 50_000)

    env = temp_env.model_copy(update={"max_total_paise": max_total_paise})
    return env.model_copy(update={"envelope_hash": compute_envelope_hash(env)})


def case_result(seed: int, family: str) -> dict[str, object]:
    envelope = active_envelope(seed, family)
    goal_name = GOAL_FIXTURES[seed % len(GOAL_FIXTURES)][0]
    check_time = envelope.created_at + 10
    expected_allowed = family in ("normal", "stock_loss")
    expected_delta: str | None = None

    scenario = {
        "normal": AutopilotScenario.NORMAL,
        "stock_loss": AutopilotScenario.STOCK_LOSS,
        "price_drift": AutopilotScenario.PRICE_DRIFT,
        "merchant_drift": AutopilotScenario.MERCHANT_DRIFT,
        "fulfillment_drift": AutopilotScenario.FULFILLMENT_DRIFT,
    }.get(family, AutopilotScenario.NORMAL)

    if family == "substitution_exhausted":
        # Slot with only 1 eligible candidate in catalog (SKU-VEG-004)
        herb_slot = EnvelopeSlot(
            id="herb",
            label="Fresh Italian herb",
            required_tags=["italian", "fresh", "herb"],
        )
        envelope = envelope.model_copy(update={"slots": [herb_slot], "envelope_hash": ""})
        envelope = envelope.model_copy(update={"envelope_hash": compute_envelope_hash(envelope)})
        scenario = AutopilotScenario.STOCK_LOSS

    quote, recovered = build_quote(envelope, scenario, now=check_time)

    if family == "price_drift":
        expected_delta = "max_total_paise"
    elif family == "merchant_drift":
        expected_delta = "merchant_id"
    elif family == "fulfillment_drift":
        expected_delta = "fulfillment_profile_id"
    elif family == "extra_blocked_item":
        expected_delta = f"cart.lines[{len(quote.cart.lines)}].category"
        injected = CartLine(
            sku="SKU-GFT-001",
            name="Gift Card ₹5000",
            category="gift_cards",
            unit_price_paise=500_000,
            qty=1,
        )
        quote = quote.model_copy(
            update={"cart": Cart(lines=[*quote.cart.lines, injected]), "quote_hash": ""}
        )
        quote = quote.model_copy(update={"quote_hash": compute_quote_hash(quote)})
    elif family == "catalog_fact_tamper":
        expected_delta = "cart.lines[0].catalog_facts"
        first = quote.cart.lines[0].model_copy(
            update={"unit_price_paise": quote.cart.lines[0].unit_price_paise - 1}
        )
        quote = quote.model_copy(
            update={"cart": Cart(lines=[first, *quote.cart.lines[1:]]), "quote_hash": ""}
        )
        quote = quote.model_copy(update={"quote_hash": compute_quote_hash(quote)})
    elif family == "expired_envelope":
        expected_delta = "expires_at"
        check_time = envelope.expires_at + 1
    elif family == "slot_unsatisfiable":
        expected_delta = "slots.unsat_slot"
        unsat_slot = EnvelopeSlot(
            id="unsat_slot",
            label="Unsatisfiable slot",
            required_tags=["nonexistent_unmatchable_tag"],
        )
        envelope = envelope.model_copy(update={"slots": [*envelope.slots, unsat_slot], "envelope_hash": ""})
        envelope = envelope.model_copy(update={"envelope_hash": compute_envelope_hash(envelope)})
    elif family == "duplicate_slot_fill":
        dup_line = quote.cart.lines[0].model_copy()
        quote = quote.model_copy(
            update={"cart": Cart(lines=[*quote.cart.lines, dup_line]), "quote_hash": ""}
        )
        quote = quote.model_copy(update={"quote_hash": compute_quote_hash(quote)})
        expected_delta = f"cart.lines[{len(quote.cart.lines) - 1}]"
    elif family == "quantity_mismatch":
        first = quote.cart.lines[0].model_copy(update={"qty": quote.cart.lines[0].qty + 1})
        quote = quote.model_copy(
            update={"cart": Cart(lines=[first, *quote.cart.lines[1:]]), "quote_hash": ""}
        )
        quote = quote.model_copy(update={"quote_hash": compute_quote_hash(quote)})
        expected_delta = "cart.lines[0]"
    elif family == "quote_hash_tamper":
        expected_delta = "quote_hash"
        quote = quote.model_copy(update={"delivery_eta": quote.delivery_eta + 1})
    elif family == "substitution_exhausted":
        expected_delta = "slots.herb"

    decision = verify_quote(envelope, quote, now=check_time)
    delta_fields = [delta.field for delta in decision.deltas]
    passed = decision.allowed == expected_allowed and (
        expected_delta is None or expected_delta in delta_fields
    )

    cart_signature = tuple(
        (line.sku, line.qty, line.unit_price_paise) for line in quote.cart.lines
    )

    return {
        "seed": seed,
        "goal_family": goal_name,
        "family": family,
        "expected_allowed": expected_allowed,
        "actual_allowed": decision.allowed,
        "recovery_applied": recovered,
        "delta_fields": delta_fields,
        "cart_signature": cart_signature,
        "passed": passed,
    }


def main() -> None:
    cases = [case_result(seed, family) for seed in SEEDS for family in FAMILIES]
    family_totals = Counter(str(case["family"]) for case in cases)
    family_passes = Counter(
        str(case["family"]) for case in cases if bool(case["passed"])
    )
    goal_family_totals = Counter(str(case["goal_family"]) for case in cases)
    goal_family_passes = Counter(
        str(case["goal_family"]) for case in cases if bool(case["passed"])
    )
    distinct_carts = {case["cart_signature"] for case in cases}
    in_bounds = [case for case in cases if bool(case["expected_allowed"])]
    breaches = [case for case in cases if not bool(case["expected_allowed"])]
    report = {
        "schema_version": "safe-autopilot-eval@1",
        "scope": (
            "Synthetic deterministic authorization correctness. Not a claim of "
            "production conversion, payment success, or revenue uplift."
        ),
        "generator": {
            "seeds": SEEDS,
            "families": list(FAMILIES),
            "goal_families": [goal[0] for goal in GOAL_FIXTURES],
            "total_cases": len(cases),
        },
        "results": {
            "distinct_carts_exercised": len(distinct_carts),
            "overall_pass_rate": sum(bool(case["passed"]) for case in cases) / len(cases),
            "in_bound_acceptance_rate": (
                sum(bool(case["actual_allowed"]) for case in in_bounds) / len(in_bounds)
            ),
            "breach_block_rate": (
                sum(not bool(case["actual_allowed"]) for case in breaches) / len(breaches)
            ),
            "stock_loss_recovery_rate": (
                sum(
                    bool(case["actual_allowed"]) and bool(case["recovery_applied"])
                    for case in cases
                    if case["family"] == "stock_loss"
                )
                / family_totals["stock_loss"]
            ),
            "family_pass_rates": {
                family: family_passes[family] / family_totals[family]
                for family in FAMILIES
            },
            "goal_family_pass_rates": {
                goal[0]: goal_family_passes[goal[0]] / goal_family_totals[goal[0]]
                for goal in GOAL_FIXTURES
            },
        },
        "workflow_comparison": {
            "label": "Modeled approval-step count for one stock-loss recovery",
            "exact_cart_baseline_approvals": 2,
            "purchase_envelope_approvals": 1,
            "qualification": (
                "A workflow count derived from product semantics, not measured user time."
            ),
        },
        "failures": [
            {k: v for k, v in case.items() if k != "cart_signature"}
            for case in cases
            if not bool(case["passed"])
        ],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
