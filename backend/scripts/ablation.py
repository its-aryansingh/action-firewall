"""Ablation: does every rule in the envelope earn its place?

WHY
---
A benchmark that only ever reports "zero violations authorised" tells you the
layer works. It does not tell you which PART of the layer is doing the work, and
it cannot distinguish a rule that is load-bearing from one that has never once
changed an outcome. A rule that never changes an outcome is not a safety control,
it is a comment with a runtime cost.

So this removes one rule at a time from the same 1,050-case corpus and reports what
escapes. The number that matters per row is `violations_authorised`: how many
constructed policy violations the layer would wave through with that single rule
switched off.

HOW A RULE IS "REMOVED"
-----------------------
By neutralising the input that triggers it, never by editing the verifier. That
matters: an ablation that patches the code under test measures a different
program than the one that ships. Emptying `blocked_tags` is a configuration a
real merchant could actually choose, so each row below is also an answer to
"what happens if a merchant does not set this?"

The hash-binding row is the exception and is marked as such — it re-hashes a
widened envelope, which is what an attacker with write access would do, not a
configuration.

Usage:  python scripts/ablation.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir / "scripts"))

from app import catalog  # noqa: E402
from app.envelope import compute_envelope_hash, verify_quote  # noqa: E402
from app.models import EnvelopeSlot  # noqa: E402

from benchmark_agent_authorization import (  # noqa: E402
    COMPLIANT_FAMILIES,
    FAMILIES,
    build_case,
)
from evaluate_autopilot import SEEDS  # noqa: E402

FAR_FUTURE = 4_102_444_800.0  # 2100-01-01
HUGE_CAP = 10_000_000_000


def _rehash(envelope, **updates):
    env = envelope.model_copy(update={**updates, "envelope_hash": ""})
    return env.model_copy(update={"envelope_hash": compute_envelope_hash(env)})


# Each ablation returns (envelope, check_time) with exactly one rule neutralised.
def _full(env, quote, at):
    return env, at


def _no_tag_rule(env, quote, at):
    return _rehash(env, blocked_tags=[]), at


def _no_category_rule(env, quote, at):
    return _rehash(env, blocked_categories=[]), at


def _no_cap(env, quote, at):
    return _rehash(env, max_total_paise=HUGE_CAP), at


def _no_expiry(env, quote, at):
    return _rehash(env, expires_at=FAR_FUTURE, delivery_deadline=FAR_FUTURE), at


def _no_slot_requirements(env, quote, at):
    """Slots stop an agent buying something adjacent to what was asked for.

    Widening `required_tags` alone does NOT neutralise them: the unmatched-line
    check is separate, so an extra line still fails. Genuinely removing slot
    enforcement means giving the envelope one slot per proposed line, shaped to
    accept exactly that line — which is the configuration equivalent of "any
    basket satisfies this envelope".
    """
    by_sku = catalog.by_sku()
    permissive = []
    for i, line in enumerate(quote.cart.lines):
        tags = by_sku.get(line.sku, {}).get("tags", [])
        if not tags:
            continue
        permissive.append(EnvelopeSlot(
            id=f"any{i}", label="any", required_tags=[tags[0]], quantity=line.qty))
    if not permissive:
        return env, at
    return _rehash(env, slots=permissive), at


ABLATIONS = {
    "full_layer": (_full, "every rule active — the shipped configuration"),
    "no_ingredient_tag_rule": (_no_tag_rule, "merchant sets no blocked_tags"),
    "no_category_rule": (_no_category_rule, "merchant sets no blocked_categories"),
    "no_spend_cap": (_no_cap, "cap raised beyond any cart in the corpus"),
    "no_expiry": (_no_expiry, "envelope never expires"),
    "no_slot_requirements": (_no_slot_requirements, "slots accept almost anything"),
}


def _stock_ablation_row() -> dict:
    """Stock cannot be neutralised on the envelope, so it gets its own pass."""
    escaped = 0
    checked = 0
    for seed in SEEDS:
        for family in FAMILIES:
            if family in COMPLIANT_FAMILIES:
                continue
            case = build_case(seed, family)
            checked += 1
            # Refill every shelf, then re-verify: the stock rule is now inert.
            for line in case["quote"].cart.lines:
                catalog.set_stock(line.sku, 9_999)
            if verify_quote(case["envelope"], case["quote"], now=case["check_time"]).allowed:
                escaped += 1
            catalog.reset_stock()
    return {
        "ablation": "no_stock_check",
        "description": "every shelf refilled, so availability never binds",
        "violations_checked": checked,
        "violations_authorised": escaped,
        "escape_rate": round(escaped / checked, 4) if checked else 0.0,
    }


def _hash_binding_row() -> dict:
    """Not a configuration — an attacker who can widen AND re-hash."""
    escaped = 0
    checked = 0
    for seed in SEEDS:
        for family in FAMILIES:
            if family in COMPLIANT_FAMILIES:
                continue
            case = build_case(seed, family)
            checked += 1
            wide = _rehash(
                case["envelope"],
                blocked_tags=[], blocked_categories=[],
                max_total_paise=HUGE_CAP,
                expires_at=FAR_FUTURE, delivery_deadline=FAR_FUTURE,
            )
            if verify_quote(wide, case["quote"], now=case["check_time"]).allowed:
                escaped += 1
            catalog.reset_stock()
    return {
        "ablation": "envelope_widened_and_rehashed",
        "description": "ATTACK, not a setting: every rule removed and the digest recomputed",
        "violations_checked": checked,
        "violations_authorised": escaped,
        "escape_rate": round(escaped / checked, 4) if checked else 0.0,
    }


def run(name: str) -> dict:
    mutate, description = ABLATIONS[name]
    escaped = 0
    checked = 0
    false_positives = 0
    compliant = 0
    for seed in SEEDS:
        for family in FAMILIES:
            case = build_case(seed, family)
            env, at = mutate(case["envelope"], case["quote"], case["check_time"])
            allowed = verify_quote(env, case["quote"], now=at).allowed
            if family in COMPLIANT_FAMILIES:
                compliant += 1
                if not allowed:
                    false_positives += 1
            else:
                checked += 1
                if allowed:
                    escaped += 1
            catalog.reset_stock()
    return {
        "ablation": name,
        "description": description,
        "violations_checked": checked,
        "violations_authorised": escaped,
        "escape_rate": round(escaped / checked, 4) if checked else 0.0,
        "legitimate_orders_refused": false_positives,
        "legitimate_checked": compliant,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = [run(name) for name in ABLATIONS]
    rows.append(_stock_ablation_row())
    rows.append(_hash_binding_row())

    baseline = rows[0]["violations_authorised"]
    inert = [
        r["ablation"] for r in rows[1:]
        if r["ablation"] != "envelope_widened_and_rehashed"
        and r["violations_authorised"] == baseline
    ]

    report = {
        "schema_version": "ablation@1",
        "scope": (
            "One rule neutralised at a time on the same corpus, by changing the "
            "envelope rather than the verifier. Each row except the last is a "
            "configuration a merchant could actually choose."
        ),
        "rows": rows,
        "rules_that_never_changed_an_outcome": inert,
        "every_rule_is_load_bearing": not inert,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Ablation — what escapes when one rule is switched off\n")
        print(f"  {'ablation':34} {'escaped':>8} {'of':>6} {'rate':>8}  note")
        for r in rows:
            print(f"  {r['ablation']:34} {r['violations_authorised']:>8} "
                  f"{r['violations_checked']:>6} {r['escape_rate']:>8.1%}  "
                  f"{r['description']}")
        print()
        if inert:
            print(f"  RULES THAT NEVER CHANGED AN OUTCOME: {inert}")
            print("  A rule that never changes an outcome is not a control. Either the "
                  "corpus does not exercise it, or it is dead weight — find out which.")
        else:
            print("  Every rule changed an outcome on at least one case: none is dead weight.")
        print(f"\n  {report['scope']}")

    # A rule that never fires is a finding, not a pass.
    sys.exit(1 if inert else 0)


if __name__ == "__main__":
    main()
