"""What publishing the acceptance rules is worth, on this repository's own corpus.

WHY THIS SCRIPT EXISTS
----------------------
`app/acceptance_policy.py` makes a claim: an agent that reads what a merchant
will refuse, before it proposes anything, does not propose most of the things
that get refused. A claim like that is only worth making if a reader can rerun
it, so the number quoted in the README comes from here rather than from a
docstring somebody typed once and never checked again.

THE DISTINCTION THAT MATTERS
----------------------------
Two different documents are readable by an agent before it proposes, and
conflating them would inflate the headline:

  * The MERCHANT ACCEPTANCE POLICY at `/agent-commerce/v1/acceptance-policy` —
    merchant-wide rules that apply to every shopper: blocked categories, blocked
    ingredient tags, the order ceiling, the registered actions, server-side
    pricing, availability re-read at authorization.

  * The CUSTOMER'S PURCHASE ENVELOPE — the slots, quantities, deadline and
    fulfilment profile that one shopper approved. The agent already holds it.
    The merchant does not publish it and could not: it is not the merchant's to
    publish.

So every violating family below is labelled with WHICH of the two would have
prevented it, and the two numbers are reported separately. Only the first is
credit the endpoint has earned.

WHAT PUBLICATION CANNOT DO
--------------------------
`catalog_fact_tamper` and `quote_hash_tamper` are callers that forge a price or
a digest. They already know the rules and are choosing to break them. Publication
is a courtesy to honest agents; those families are the reason the firewall still
has to exist, and they get their own column instead of being quietly dropped.

DRIFT GUARD
-----------
If a violating family is added to the benchmark without a disclosure label, this
script exits non-zero rather than silently excluding it from the denominator.

Usage:  python scripts/publication_value.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir / "scripts"))

from benchmark_agent_authorization import (  # noqa: E402
    COMPLIANT_FAMILIES,
    FAMILIES,
    run_case,
)
from evaluate_autopilot import SEEDS  # noqa: E402

DOCUMENT = "acceptance_policy"
ENVELOPE = "purchase_envelope"
NEITHER = "neither"

CHANNEL_MEANING = {
    DOCUMENT: "stated in the merchant acceptance policy an agent can fetch before proposing",
    ENVELOPE: "stated in the customer's Purchase Envelope, which the agent already holds",
    NEITHER: "forged input — the caller knows the rule and breaks it anyway",
}

#: family -> (which document would have prevented the proposal, which clause)
DISCLOSURE: dict[str, tuple[str, str]] = {
    "price_drift": (
        DOCUMENT, "requires.server_priced_quote — line facts must match the catalog revision"),
    "cap_only_breach": (
        DOCUMENT, "will_refuse.orders_above_paise"),
    "category_only_breach": (
        DOCUMENT, "will_refuse.categories"),
    "extra_blocked_item": (
        DOCUMENT, "will_refuse.categories"),
    "forbidden_tag": (
        DOCUMENT, "will_refuse.ingredient_tags"),
    "stock_shortfall": (
        DOCUMENT, "requires.stock_at_dispatch"),
    "substitution_exhausted": (
        DOCUMENT, "requires.stock_at_dispatch"),
    "merchant_drift": (
        DOCUMENT, "merchant_id — the document speaks for exactly one merchant"),

    "expired_envelope": (
        ENVELOPE, "expires_at, on the envelope the agent is already holding"),
    "slot_only_breach": (
        ENVELOPE, "slots are per-customer and not the merchant's to publish"),
    "slot_unsatisfiable": (
        ENVELOPE, "slots are per-customer and not the merchant's to publish"),
    "duplicate_slot_fill": (
        ENVELOPE, "slot quantity is per-customer"),
    "quantity_mismatch": (
        ENVELOPE, "slot quantity is per-customer"),
    "fulfillment_drift": (
        ENVELOPE, "fulfillment_profile_id is chosen by the customer, not published"),

    "catalog_fact_tamper": (
        NEITHER, "forged line facts"),
    "quote_hash_tamper": (
        NEITHER, "forged quote digest"),
}

VIOLATING_FAMILIES = tuple(f for f in FAMILIES if f not in COMPLIANT_FAMILIES)


def _check_coverage() -> list[str]:
    """A family with no label would silently shrink the denominator."""
    return sorted(set(VIOLATING_FAMILIES) - set(DISCLOSURE))


def measure() -> dict:
    unlabelled = _check_coverage()
    rows = [
        run_case(seed, family)
        for seed in SEEDS
        for family in VIOLATING_FAMILIES
    ]

    by_channel: dict[str, dict] = {
        channel: {
            "channel": channel,
            "meaning": CHANNEL_MEANING[channel],
            "violations": 0,
            "hard_refusals": 0,
            "hard_refusal_paise": 0,
        }
        for channel in (DOCUMENT, ENVELOPE, NEITHER)
    }
    by_family: dict[str, dict] = {}

    for row in rows:
        channel, clause = DISCLOSURE.get(row["family"], (NEITHER, "UNLABELLED"))
        # A "hard" refusal is one the repair ladder could not rescue: the order
        # died. Those are the ones worth preventing before they are proposed —
        # a repaired order was never lost in the first place.
        hard = row["outcome"] == "REFUSED"

        bucket = by_channel[channel]
        bucket["violations"] += 1
        family = by_family.setdefault(row["family"], {
            "family": row["family"], "channel": channel, "clause": clause,
            "violations": 0, "hard_refusals": 0, "hard_refusal_paise": 0,
        })
        family["violations"] += 1
        if hard:
            bucket["hard_refusals"] += 1
            bucket["hard_refusal_paise"] += row["proposed_paise"]
            family["hard_refusals"] += 1
            family["hard_refusal_paise"] += row["proposed_paise"]

    total = len(rows)
    hard_total = sum(c["hard_refusals"] for c in by_channel.values())
    hard_value = sum(c["hard_refusal_paise"] for c in by_channel.values())
    doc = by_channel[DOCUMENT]

    def _share(n: int, d: int) -> float:
        return round(n / d, 4) if d else 0.0

    return {
        "schema_version": "publication-value@1",
        "corpus": {
            "violations": total,
            "seeds": len(SEEDS),
            "violating_families": len(VIOLATING_FAMILIES),
        },
        "by_channel": list(by_channel.values()),
        "by_family": sorted(by_family.values(), key=lambda r: (r["channel"], r["family"])),
        "headline": {
            "violations_the_published_document_would_have_prevented": doc["violations"],
            "share_of_all_violations": _share(doc["violations"], total),
            "hard_refusals_total": hard_total,
            "hard_refusals_the_document_would_have_prevented": doc["hard_refusals"],
            "share_of_hard_refusals": _share(doc["hard_refusals"], hard_total),
            "hard_refusal_value_paise_total": hard_value,
            "hard_refusal_value_paise_preventable_by_document": doc["hard_refusal_paise"],
        },
        "caveat": (
            "Counts proposals a well-behaved agent would not have made after reading "
            "the document. It is not a measurement of live agent behaviour, and it "
            "does not apply to forged input: publication prevents mistakes, not attacks."
        ),
        "unlabelled_families": unlabelled,
    }


def _rupees(paise: int) -> str:
    return f"Rs {paise / 100:,.2f}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    report = measure()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        h = report["headline"]
        c = report["corpus"]
        print("What publishing the acceptance rules is worth\n")
        print(f"  corpus  {c['violations']} constructed violations "
              f"({c['seeds']} seeds x {c['violating_families']} violating families)\n")
        print(f"  {'channel':22} {'violations':>11} {'hard refusals':>14} {'value at stake':>18}")
        for bucket in report["by_channel"]:
            print(f"  {bucket['channel']:22} {bucket['violations']:>11} "
                  f"{bucket['hard_refusals']:>14} "
                  f"{_rupees(bucket['hard_refusal_paise']):>18}")
        print()
        print(f"  Of {c['violations']} violations, {h['violations_the_published_document_would_have_prevented']} "
              f"({h['share_of_all_violations']:.1%}) would never have been proposed by an")
        print("  agent that fetched the merchant acceptance policy first.")
        print()
        print(f"  Of {h['hard_refusals_total']} refusals no repair could rescue, "
              f"{h['hard_refusals_the_document_would_have_prevented']} "
              f"({h['share_of_hard_refusals']:.1%}) were preventable that way —")
        print(f"  {_rupees(h['hard_refusal_value_paise_preventable_by_document'])} of "
              f"{_rupees(h['hard_refusal_value_paise_total'])} in orders that died for want of")
        print("  a rule the store already knew and never said.")
        print()
        for bucket in report["by_channel"]:
            print(f"  {bucket['channel']:22} {bucket['meaning']}")
        print(f"\n  {report['caveat']}")

    if report["unlabelled_families"]:
        print(f"\n  UNLABELLED FAMILIES: {report['unlabelled_families']}", file=sys.stderr)
        print("  Every violating family must say which document would have prevented it, "
              "or the denominator is a guess.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
