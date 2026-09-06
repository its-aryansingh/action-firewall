"""Modeled three-way workflow comparison using the real quote verifier.

This measures workflow semantics over synthetic jobs. It is deliberately not a
claim about conversion, revenue, user time, or production payment success.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.envelope import build_quote, verify_quote  # noqa: E402
from app.models import AutopilotScenario  # noqa: E402
from evaluate_autopilot import SEEDS, active_envelope  # noqa: E402


def main() -> None:
    legitimate_cases = 0
    stock_loss_cases = 0
    unsafe_drift_cases = 0
    exact_cart_no_later_intervention = 0
    envelope_no_later_intervention = 0
    exact_cart_stock_recoveries = 0
    envelope_stock_recoveries = 0
    exact_cart_unsafe_authorizations = 0
    envelope_unsafe_authorizations = 0
    failures: list[dict[str, object]] = []

    for seed in SEEDS:
        normal_envelope = active_envelope(seed, "normal")
        approved_quote, _ = build_quote(
            normal_envelope,
            AutopilotScenario.NORMAL,
            now=normal_envelope.created_at + 10,
        )
        approved_quote_hash = approved_quote.quote_hash

        for scenario_name, scenario in (
            ("normal", AutopilotScenario.NORMAL),
            ("stock_loss", AutopilotScenario.STOCK_LOSS),
        ):
            envelope = active_envelope(seed, scenario_name)
            quote, recovered = build_quote(
                envelope,
                scenario,
                now=envelope.created_at + 10,
            )
            decision = verify_quote(envelope, quote, now=envelope.created_at + 10)
            legitimate_cases += 1
            exact_matches = quote.quote_hash == approved_quote_hash
            exact_cart_no_later_intervention += int(exact_matches)
            envelope_no_later_intervention += int(decision.allowed)
            if scenario is AutopilotScenario.STOCK_LOSS:
                stock_loss_cases += 1
                exact_cart_stock_recoveries += int(exact_matches)
                envelope_stock_recoveries += int(decision.allowed and recovered)
            if not decision.allowed:
                failures.append(
                    {"seed": seed, "scenario": scenario_name, "error": "safe_job_blocked"}
                )

        for scenario_name, scenario in (
            ("price_drift", AutopilotScenario.PRICE_DRIFT),
            ("merchant_drift", AutopilotScenario.MERCHANT_DRIFT),
            ("fulfillment_drift", AutopilotScenario.FULFILLMENT_DRIFT),
        ):
            envelope = active_envelope(seed, scenario_name)
            quote, _ = build_quote(
                envelope,
                scenario,
                now=envelope.created_at + 10,
            )
            decision = verify_quote(envelope, quote, now=envelope.created_at + 10)
            unsafe_drift_cases += 1
            exact_authorized = quote.quote_hash == approved_quote_hash
            exact_cart_unsafe_authorizations += int(exact_authorized)
            envelope_unsafe_authorizations += int(decision.allowed)
            if exact_authorized or decision.allowed:
                failures.append(
                    {
                        "seed": seed,
                        "scenario": scenario_name,
                        "error": "unsafe_drift_authorized",
                        "exact_cart": exact_authorized,
                        "purchase_envelope": decision.allowed,
                    }
                )

    manual_approval_prompts = legitimate_cases
    exact_cart_approval_prompts = (
        legitimate_cases + legitimate_cases - exact_cart_no_later_intervention
    )
    envelope_approval_prompts = legitimate_cases
    report = {
        "schema_version": "action-firewall-workflow-comparison@1",
        "scope": (
            "Modeled workflow counts over synthetic catalog jobs. Not measured user "
            "time, conversion, revenue, or production payment success."
        ),
        "corpus": {
            "seeds": len(SEEDS),
            "legitimate_jobs": legitimate_cases,
            "eligible_stock_loss_jobs": stock_loss_cases,
            "unsafe_drift_attempts": unsafe_drift_cases,
        },
        "results": {
            "manual_checkout": {
                "completed_without_action_time_intervention": 0,
                "eligible_stock_loss_recovered_without_reapproval": 0,
                "approval_prompts_per_legitimate_completion": (
                    manual_approval_prompts / legitimate_cases
                ),
                "unsafe_automatic_authorizations": 0,
            },
            "exact_cart_approval": {
                "completed_without_action_time_intervention": exact_cart_no_later_intervention,
                "eligible_stock_loss_recovered_without_reapproval": exact_cart_stock_recoveries,
                "approval_prompts_per_legitimate_completion": (
                    exact_cart_approval_prompts / legitimate_cases
                ),
                "unsafe_automatic_authorizations": exact_cart_unsafe_authorizations,
            },
            "purchase_envelope": {
                "completed_without_action_time_intervention": envelope_no_later_intervention,
                "eligible_stock_loss_recovered_without_reapproval": envelope_stock_recoveries,
                "approval_prompts_per_legitimate_completion": (
                    envelope_approval_prompts / legitimate_cases
                ),
                "unsafe_automatic_authorizations": envelope_unsafe_authorizations,
            },
        },
        "failures": failures,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
