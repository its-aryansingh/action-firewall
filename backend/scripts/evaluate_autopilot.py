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
    draft_envelope,
    verify_quote,
)
from app.models import (  # noqa: E402
    AutopilotScenario,
    Cart,
    CartLine,
    EnvelopeDraftRequest,
    EnvelopeStatus,
)

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
)


def active_envelope(seed: int):
    rng = random.Random(seed)
    created = 1_800_000_000.0 + seed
    draft = draft_envelope(
        EnvelopeDraftRequest(
            goal="Buy supplies for a pasta dinner",
            max_total_rupees=rng.randint(500, 800),
            expires_in_minutes=60,
            delivery_in_minutes=45,
        ),
        now=created,
    )
    active = draft.model_copy(
        update={
            "status": EnvelopeStatus.ACTIVE,
            "version": 2,
            "mandate_id": f"evaluation-policy-{seed}",
            "envelope_hash": "",
        }
    )
    return active.model_copy(
        update={"envelope_hash": compute_envelope_hash(active)}
    )


def case_result(seed: int, family: str) -> dict[str, object]:
    envelope = active_envelope(seed)
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
    quote, recovered = build_quote(envelope, scenario, now=check_time)

    if family == "price_drift":
        expected_delta = "max_total_paise"
    elif family == "merchant_drift":
        expected_delta = "merchant_id"
    elif family == "fulfillment_drift":
        expected_delta = "fulfillment_profile_id"
    elif family == "extra_blocked_item":
        expected_delta = "cart.lines[3].category"
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

    decision = verify_quote(envelope, quote, now=check_time)
    delta_fields = [delta.field for delta in decision.deltas]
    passed = decision.allowed == expected_allowed and (
        expected_delta is None or expected_delta in delta_fields
    )
    return {
        "seed": seed,
        "family": family,
        "expected_allowed": expected_allowed,
        "actual_allowed": decision.allowed,
        "recovery_applied": recovered,
        "delta_fields": delta_fields,
        "passed": passed,
    }


def main() -> None:
    cases = [case_result(seed, family) for seed in SEEDS for family in FAMILIES]
    family_totals = Counter(str(case["family"]) for case in cases)
    family_passes = Counter(
        str(case["family"]) for case in cases if bool(case["passed"])
    )
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
            "total_cases": len(cases),
        },
        "results": {
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
        },
        "workflow_comparison": {
            "label": "Modeled approval-step count for one stock-loss recovery",
            "exact_cart_baseline_approvals": 2,
            "purchase_envelope_approvals": 1,
            "qualification": (
                "A workflow count derived from product semantics, not measured user time."
            ),
        },
        "failures": [case for case in cases if not bool(case["passed"])],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
