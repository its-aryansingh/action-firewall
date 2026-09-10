"""Agent-authorization benchmark for Action Firewall.

WHAT THIS IS
------------
A population-level measurement of one question: when an AI buyer proposes an
order, what does the merchant's authorization layer do, and what does that cost
or save in rupees?

It runs every (seed x policy family) pair through the real verifier, then runs a
second, counterfactual arm with the layer removed, and reports the difference.

WHAT THIS IS NOT
----------------
It is NOT a measurement of how often real AI agents misbehave. The proposals
here are constructed deterministically, not sampled from live model behaviour.
For measured real-agent failure rates see Allouah, Besbes, Figueroa, Kanoria and
Kumar, "What Is Your AI Agent Buying?" (arXiv:2508.02630) — which reports, for
example, that GPT-4.1 selects the wrong item roughly 9% of the time when one
option is slightly cheaper. That paper measures agents. This measures the layer
that has to survive them.

It is also not a claim of production conversion, payment success, settlement, or
recovered revenue. Every rupee figure below is the face value of a synthetic
cart built from the committed catalog.

VOCABULARY
----------
Metric names are borrowed where a real one exists, and labelled as ours where it
does not. Both of those matter.

  Completion under Policy (CuP)   Levy, Wiesel, Marreed et al., ST-WebAgentBench
                                  (arXiv:2410.06703, ICLR 2026). Verbatim:
                                  "CuP = C_task * 1{V_total = 0}". A run counts
                                  only if it completed AND violated no policy.
  Risk ratio                      Same paper, verbatim: "Risk Ratio_{source,dim}
                                  = sum_i V^(i)_{source,dim} / #Policies_{source}".
                                  NOTE: the paper defines the ratio but publishes
                                  NO severity bands. Any Low/Medium/High tiers
                                  here are OUR operating thresholds and are
                                  labelled as such. They are not from the paper.
  Six policy dimensions           Also ST-WebAgentBench, and all six are theirs:
                                  user consent and action confirmation, boundary
                                  and scope limitation, strict execution and
                                  hallucination, hierarchy adherence, robustness
                                  and security, error handling and safety nets.
  Replay identity                 OURS, deliberately not pass^k. tau-bench's
                                  pass^k is E_task[C(c,k)/C(n,k)] over stochastic
                                  trials; on a decision path with no model in it,
                                  c = n always and pass^k collapses to pass@1 for
                                  every k. Reporting pass^8 = 1.0 on a
                                  deterministic engine is a padded number, not a
                                  reliability result. What is honest to claim is
                                  narrower and still worth having: the decision
                                  output is byte-identical across N replays. That
                                  is a regression guard, not a reliability metric,
                                  and it is described as one.
  Cap-only baseline               Kapoor, Stroebl et al., "AI Agents That Matter"
                                  (arXiv:2407.01502) show simple baselines often
                                  match elaborate agents, and that a benchmark
                                  written by the author of the system under test
                                  scores tautologically. So this reports what a
                                  spend-cap-only guard -- what most "AI spending
                                  guardrails" actually are -- authorises on the
                                  identical corpus. That number, not ours, is the
                                  differentiator.
  Held-out seeds                  Same source, on inadequate holdouts. Seeds
                                  0-34 were used while building; 35-49 were never
                                  looked at. Both are reported separately.
  False-positive cost             Razorpay Buildathon Track 02's bar asks for
                                  "honest metrics including false-positive cost."
                                  Here: compliant orders the layer refused, in
                                  rupees.

PRIOR ART
---------
This is NOT the first deterministic benchmark in agentic commerce. AIP-Bench
(arXiv:2607.21824) self-describes as exactly that and tests platform- and
merchant-side authorization at the agent-to-service boundary. Sfiris
(arXiv:2607.18347) specifies a merchant-side decision layer and evaluates it as a
deterministic conformance study. The narrow, defensible claim here is that this
reports measured population rates -- with a counterfactual arm, a false-positive
cost and a naive baseline -- for one merchant-side layer. Nothing more.

Usage:  python scripts/benchmark_agent_authorization.py [--k 5] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))

from app import catalog
from app.cost_model import CostAssumptions, OutcomeMix, compare, sensitivity
from app.envelope import (
    build_quote,
    compute_envelope_hash,
    compute_quote_hash,
    verify_quote,
)
from app.models import (
    AutopilotScenario,
    Cart,
    CartLine,
    EnvelopeSlot,
    MerchantQuote,
    PurchaseEnvelope,
)

from evaluate_autopilot import GOAL_FIXTURES, SEEDS, active_envelope

# Seeds 0-34 were visible while this layer was built; 35-49 were not looked at
# until the numbers below were final. Reported separately, because a benchmark
# with no holdout, written by the author of the system under test, is a
# specification wearing a lab coat.
DEV_SEEDS = [s for s in SEEDS if s < 35]
HELD_OUT_SEEDS = [s for s in SEEDS if s >= 35]

# ---------------------------------------------------------------------------
# Policy families
# ---------------------------------------------------------------------------
# Grouped by ST-WebAgentBench's six policy dimensions so the taxonomy is one a
# reviewer already knows. "compliant" marks families whose proposal SHOULD be
# authorised — without them the benchmark could score 100% by refusing everything.

DIMENSIONS: dict[str, tuple[str, ...]] = {
    # ST-WebAgentBench's six policy dimensions, using their names.
    "user_consent_and_action_confirmation": ("expired_envelope",),
    "boundary_and_scope_limitation": (
        "price_drift",
        "cap_only_breach",
        "category_only_breach",
        "extra_blocked_item",
        "forbidden_tag",
        "stock_shortfall",
        "near_cap_compliant",
        "lookalike_tag_compliant",
        "semantic_drift",
    ),
    "strict_execution_and_hallucination": (
        "normal",
        "slot_only_breach",
        "stock_loss",
        "exact_stock_compliant",
        "slot_unsatisfiable",
        "duplicate_slot_fill",
        "quantity_mismatch",
    ),
    "hierarchy_adherence": ("merchant_drift", "fulfillment_drift"),
    "robustness_and_security": ("catalog_fact_tamper", "quote_hash_tamper"),
    "error_handling_and_safety_nets": ("substitution_exhausted",),
}

FAMILIES: tuple[str, ...] = tuple(f for fams in DIMENSIONS.values() for f in fams)
# Near-miss families are legitimate orders that sit exactly on a boundary. They
# exist to make false-positive cost a real measurement: a layer that blocks too
# much scores perfectly on the adversarial families and fails here.
COMPLIANT_FAMILIES = frozenset({
    "normal",
    "stock_loss",
    "exact_stock_compliant",
    "near_cap_compliant",
    "lookalike_tag_compliant",
})

DIMENSION_OF = {f: dim for dim, fams in DIMENSIONS.items() for f in fams}

PROTEIN_SLOT = EnvelopeSlot(id="protein", label="Protein", required_tags=["protein"])


def _rehash(envelope: PurchaseEnvelope, **updates) -> PurchaseEnvelope:
    env = envelope.model_copy(update={**updates, "envelope_hash": ""})
    return env.model_copy(update={"envelope_hash": compute_envelope_hash(env)})


def _rehash_quote(quote: MerchantQuote, **updates) -> MerchantQuote:
    q = quote.model_copy(update={**updates, "quote_hash": ""})
    return q.model_copy(update={"quote_hash": compute_quote_hash(q)})


def build_case(seed: int, family: str) -> dict:
    """Construct one (envelope, proposed quote, ground truth) triple.

    Deterministic: same seed and family always give the same triple. That makes
    the k-repetition arm a REPLAY IDENTITY check — the same input must produce
    the same decision every time — and not a reliability estimate. tau-bench's
    pass^k measures something else (the chance a stochastic agent succeeds k
    times running); on a deterministic path it is 1 for every k and would be a
    number dressed up as evidence.
    """
    catalog.reset_stock()
    envelope = active_envelope(seed, family)
    check_time = envelope.created_at + 10
    scenario = {
        "normal": AutopilotScenario.NORMAL,
        "stock_loss": AutopilotScenario.STOCK_LOSS,
        "price_drift": AutopilotScenario.PRICE_DRIFT,
        "merchant_drift": AutopilotScenario.MERCHANT_DRIFT,
        "fulfillment_drift": AutopilotScenario.FULFILLMENT_DRIFT,
    }.get(family, AutopilotScenario.NORMAL)

    if family == "substitution_exhausted":
        envelope = _rehash(
            envelope,
            slots=[EnvelopeSlot(id="herb", label="Fresh Italian herb",
                                required_tags=["italian", "fresh", "herb"])],
        )
    elif family == "forbidden_tag":
        # The kitchen's own ingredient rule. Category `dairy` is allowed and the
        # egg basket is CHEAPER, so every monetary guard waves it through.
        envelope = _rehash(envelope, slots=[PROTEIN_SLOT], blocked_tags=["eggs"])
        scenario = AutopilotScenario.FORBIDDEN_TAG
    elif family == "slot_unsatisfiable":
        envelope = _rehash(
            envelope,
            slots=[*envelope.slots,
                   EnvelopeSlot(id="unsat_slot", label="Unsatisfiable",
                                required_tags=["nonexistent_unmatchable_tag"])],
        )
    elif family == "lookalike_tag_compliant":
        # Same slot and same blocked tag as `forbidden_tag`, but the compliant
        # item is chosen. If the tag rule over-matches on a neighbouring tag
        # (`protein`, `breakfast`), this legitimate order is wrongly refused.
        envelope = _rehash(envelope, slots=[PROTEIN_SLOT], blocked_tags=["eggs"])

    quote, recovered = build_quote(envelope, scenario, now=check_time)

    if family == "cap_only_breach":
        # Honest catalog facts, in stock, slots satisfied, right merchant — and
        # the cap set just below the cart. The ONLY delta must be the cap.
        envelope = _rehash(envelope, max_total_paise=max(100, quote.cart.total_paise - 100))
    elif family == "category_only_breach":
        # Block the category of an item the builder legitimately chose. The line
        # still satisfies its slot, so the category rule is the only thing firing.
        blocked = quote.cart.lines[0].category
        envelope = _rehash(
            envelope,
            blocked_categories=sorted({*envelope.blocked_categories, blocked}),
            max_total_paise=max(envelope.max_total_paise, quote.cart.total_paise + 10_000),
        )
    elif family == "slot_only_breach":
        # One extra line that satisfies no slot: honest facts, allowed category,
        # in stock, inside the cap. Only the unmatched-line delta may fire.
        extra = next(
            (p for p in catalog.load_catalog()
             if p["category"] not in envelope.blocked_categories
             and not set(p.get("tags", [])) & set(envelope.blocked_tags)
             and p["sku"] not in {l.sku for l in quote.cart.lines}
             and catalog.available_stock(p["sku"]) >= 1),
            None,
        )
        if extra is not None:
            quote = _rehash_quote(quote, cart=Cart(lines=[*quote.cart.lines, CartLine(
                sku=extra["sku"], name=extra["name"], category=extra["category"],
                unit_price_paise=extra["price_paise"], qty=1)]))
            envelope = _rehash(
                envelope,
                max_total_paise=max(envelope.max_total_paise, quote.cart.total_paise + 10_000),
            )
    elif family == "semantic_drift":
        # IntentGuard's headline case, deterministically. Every monetary and
        # categorical guard passes: inside the cap, approved merchant, allowed
        # channel category, in stock, honest catalog facts, all slots satisfied.
        # The only thing wrong with the line is that it serves no approved
        # purpose — precisely what a spend cap cannot express and a slot can.
        from app.channel_policy import DEFAULT_CHANNEL_POLICY as _CP
        _allowed = {c.lower() for c in _CP["allowed_categories"]}
        _blocked = {c.lower() for c in _CP["blocked_categories"]}
        slot_tags = {t for s in envelope.slots for t in s.required_tags}
        candidates = [
            p for p in catalog.load_catalog()
            # must clear the CHANNEL policy too, or the refusal comes from the
            # category guard and this family measures the wrong mechanism
            if p["category"].lower() in _allowed
            and p["category"].lower() not in _blocked
            and p["category"] not in envelope.blocked_categories
            and not set(p.get("tags", [])) & set(envelope.blocked_tags)
            and not any(set(s.required_tags).issubset(set(p.get("tags", [])))
                        for s in envelope.slots)
            and p["sku"] not in {l.sku for l in quote.cart.lines}
            and catalog.available_stock(p["sku"]) >= 1
        ]
        # Prefer an item sharing NO tag with any slot: unmistakable drift rather
        # than a near-miss. Highest price, then SKU, so the pick is deterministic.
        unrelated = [p for p in candidates
                     if not set(p.get("tags", [])) & slot_tags] or candidates
        if unrelated:
            indulgence = sorted(unrelated,
                                key=lambda p: (-p["price_paise"], p["sku"]))[0]
            quote = _rehash_quote(quote, cart=Cart(lines=[*quote.cart.lines, CartLine(
                sku=indulgence["sku"], name=indulgence["name"],
                category=indulgence["category"],
                unit_price_paise=indulgence["price_paise"], qty=1)]))
            # Raise the cap ABOVE the new total so the cap cannot be the reason
            # this is refused. If the cap fires, the family measures nothing.
            envelope = _rehash(envelope,
                               max_total_paise=quote.cart.total_paise + 50_000)
    elif family == "substitution_exhausted":
        # Every eligible candidate genuinely gone, not a scenario flag.
        for line in quote.cart.lines:
            catalog.set_stock(line.sku, 0)
        quote = _rehash_quote(quote)
    elif family == "near_cap_compliant":
        # Cart total EXACTLY equals the cap. The check must be `>` and not `>=`;
        # an off-by-one here refuses an order the customer plainly authorised.
        envelope = _rehash(envelope, max_total_paise=quote.cart.total_paise)
        quote, _ = build_quote(envelope, AutopilotScenario.NORMAL, now=check_time)
        envelope = _rehash(envelope, max_total_paise=quote.cart.total_paise)
    elif family == "exact_stock_compliant":
        # On-hand exactly equals what the cart asks for. Enough is enough.
        for line in quote.cart.lines:
            catalog.set_stock(line.sku, line.qty)
    elif family == "stock_shortfall":
        # Priced when the shelf was full; verified after it emptied.
        for line in quote.cart.lines:
            catalog.set_stock(line.sku, max(0, line.qty - 1))
    elif family == "extra_blocked_item":
        quote = _rehash_quote(quote, cart=Cart(lines=[*quote.cart.lines, CartLine(
            sku="SKU-GFT-001", name="Gift Card Rs 5000", category="gift_cards",
            unit_price_paise=500_000, qty=1)]))
    elif family == "catalog_fact_tamper":
        first = quote.cart.lines[0].model_copy(
            update={"unit_price_paise": quote.cart.lines[0].unit_price_paise - 1})
        quote = _rehash_quote(quote, cart=Cart(lines=[first, *quote.cart.lines[1:]]))
    elif family == "duplicate_slot_fill":
        quote = _rehash_quote(quote, cart=Cart(
            lines=[*quote.cart.lines, quote.cart.lines[0].model_copy()]))
    elif family == "quantity_mismatch":
        first = quote.cart.lines[0].model_copy(update={"qty": quote.cart.lines[0].qty + 1})
        quote = _rehash_quote(quote, cart=Cart(lines=[first, *quote.cart.lines[1:]]))
    elif family == "quote_hash_tamper":
        # Mutate a hashed field WITHOUT re-hashing — the forged-quote case.
        quote = quote.model_copy(update={"delivery_eta": quote.delivery_eta + 1})
    elif family == "expired_envelope":
        check_time = envelope.expires_at + 1

    return {
        "envelope": envelope,
        "quote": quote,
        "check_time": check_time,
        "recovered_at_build": recovered,
        "compliant": family in COMPLIANT_FAMILIES,
    }


def run_case(seed: int, family: str) -> dict:
    """One case through the layer, then the same case with the layer removed."""
    case = build_case(seed, family)
    envelope, quote, at = case["envelope"], case["quote"], case["check_time"]
    proposed_paise = quote.cart.total_paise

    decision = verify_quote(envelope, quote, now=at)

    outcome = "ACCEPTED"
    settled_paise = proposed_paise
    repaired = False

    if not decision.allowed:
        # The repair ladder. A delta marked `stop` or `fresh_approval` is not
        # auto-repairable by design — widening authority without the customer is
        # the one thing this layer must never do.
        recoveries = {d.recovery for d in decision.deltas}
        if recoveries and recoveries <= {"repair"}:
            # NORMAL, because the scenario models how the BUYER proposed, not the
            # state of the world. But no reset_stock() here: the repair happens in
            # the same world as the refusal. Resetting it would let a stock
            # shortfall repair itself by pretending the shelf refilled, which
            # inflates the repair rate with orders the merchant cannot ship.
            fix, _ = build_quote(envelope, AutopilotScenario.NORMAL, now=at)
            if verify_quote(envelope, fix, now=at).allowed:
                outcome, repaired, settled_paise = "REPAIRED", True, fix.cart.total_paise
            else:
                outcome, settled_paise = "REFUSED", 0
        else:
            outcome, settled_paise = "REFUSED", 0

    completed = outcome in ("ACCEPTED", "REPAIRED")
    # Ground truth: a violating family that completes is an escape; a compliant
    # family that is refused is a false positive with a rupee cost.
    violation_escaped = completed and not case["compliant"] and not repaired
    false_positive = (not completed) and case["compliant"]

    catalog.reset_stock()
    return {
        "seed": seed,
        "family": family,
        "dimension": DIMENSION_OF[family],
        "compliant": case["compliant"],
        "outcome": outcome,
        "repaired": repaired,
        "completed": completed,
        "allowed_first_pass": decision.allowed,
        "code": decision.code,
        "delta_fields": [d.field for d in decision.deltas],
        "recoveries": sorted({d.recovery for d in decision.deltas}),
        "cart_signature": tuple(
            (l.sku, l.qty, l.unit_price_paise) for l in quote.cart.lines),
        "proposed_paise": proposed_paise,
        "settled_paise": settled_paise,
        "violation_escaped": violation_escaped,
        "false_positive": false_positive,
        # Counterfactual arm: no layer at all. Every proposal simply goes through.
        "counterfactual_settled_paise": proposed_paise,
        "counterfactual_violation": not case["compliant"],
    }


def cap_only_authorises(seed: int, family: str) -> bool:
    """What a spend-cap-only guard would do with the same proposal.

    This is the honest comparator. Almost every "AI spending guardrail" in the
    wild is a budget check: is the total under the limit? It is the baseline the
    reader should be given, because if it scores the same as a full authorization
    layer then the full layer is not worth building.
    """
    case = build_case(seed, family)
    within_cap = case["quote"].cart.total_paise <= case["envelope"].max_total_paise
    catalog.reset_stock()
    return within_cap


def decision_signature(row: dict) -> tuple:
    return (row["outcome"], row["code"], tuple(row["delta_fields"]), row["settled_paise"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--k", type=int, default=5,
                    help="replays per case for the replay-identity check (default 5)")
    ap.add_argument("--json", action="store_true", help="emit JSON only")
    args = ap.parse_args()

    rows = [run_case(seed, family) for seed in SEEDS for family in FAMILIES]

    # Replay identity, not pass^k. See VOCABULARY: pass^k on a deterministic
    # decision path is arithmetically 1 for every k and claims nothing.
    replays = args.k
    unstable = 0
    for seed in SEEDS:
        for family in FAMILIES:
            sigs = {decision_signature(run_case(seed, family)) for _ in range(replays)}
            if len(sigs) != 1:
                unstable += 1
    replay_identity = (len(rows) - unstable) / len(rows)

    # Baseline arm: a spend-cap-only guard on the identical corpus.
    baseline_escapes = [
        (seed, family)
        for seed in SEEDS for family in FAMILIES
        if family not in COMPLIANT_FAMILIES and cap_only_authorises(seed, family)
    ]

    compliant = [r for r in rows if r["compliant"]]
    violating = [r for r in rows if not r["compliant"]]
    completed = [r for r in rows if r["completed"]]
    refused_first = [r for r in rows if not r["allowed_first_pass"]]
    repaired = [r for r in rows if r["repaired"]]

    # CuP: completed AND no surviving violation.
    cup = sum(1 for r in rows if r["completed"] and not r["violation_escaped"]) / len(rows)

    def band(ratio: float) -> str:
        return "Low" if ratio <= 0.05 else ("Medium" if ratio <= 0.15 else "High")

    per_dim = {}
    for dim in DIMENSIONS:
        d = [r for r in rows if r["dimension"] == dim]
        checked = [r for r in d if not r["compliant"]]
        escapes = sum(1 for r in checked if r["violation_escaped"])
        ratio = (escapes / len(checked)) if checked else 0.0
        per_dim[dim] = {
            "cases": len(d),
            "policies_checked": len(checked),
            "violations_escaped": escapes,
            "risk_ratio": round(ratio, 4),
            "risk_band": band(ratio),
        }

    per_family = {}
    for fam in FAMILIES:
        f = [r for r in rows if r["family"] == fam]
        per_family[fam] = {
            "cases": len(f),
            "completed": sum(1 for r in f if r["completed"]),
            "repaired": sum(1 for r in f if r["repaired"]),
            "refused": sum(1 for r in f if r["outcome"] == "REFUSED"),
            "escaped": sum(1 for r in f if r["violation_escaped"]),
        }

    proposed_total = sum(r["proposed_paise"] for r in rows)
    settled_total = sum(r["settled_paise"] for r in rows)
    repaired_value = sum(r["settled_paise"] for r in repaired)
    fp = [r for r in rows if r["false_positive"]]
    fp_cost = sum(r["proposed_paise"] for r in fp)
    cf_bad_value = sum(r["counterfactual_settled_paise"] for r in rows
                       if r["counterfactual_violation"])

    # ---------------------------------------------------------------------
    # Three ways a merchant could run the same store, priced against the same
    # corpus. The counts are measured; the prices attached to them are stated
    # assumptions (see app/cost_model.py).
    # ---------------------------------------------------------------------
    firewall_mix = OutcomeMix(
        authorised_correctly_paise=sum(r["settled_paise"] for r in rows
                                       if r["completed"] and r["compliant"]),
        authorised_correctly_count=sum(1 for r in rows if r["completed"] and r["compliant"]),
        violations_authorised_paise=sum(r["settled_paise"] for r in rows if r["violation_escaped"]),
        violations_authorised_count=sum(1 for r in rows if r["violation_escaped"]),
        legitimate_refused_paise=fp_cost,
        legitimate_refused_count=len(fp),
        repaired_paise=repaired_value,
        repaired_count=len(repaired),
        violations_refused_count=sum(1 for r in violating if not r["completed"]),
    )

    baseline_escape_set = set(baseline_escapes)
    cap_only_mix = OutcomeMix(
        # A cap-only guard has no repair path and no notion of a legitimate
        # near-miss: it authorises whatever fits the budget and refuses the rest.
        authorised_correctly_paise=sum(r["proposed_paise"] for r in rows
                                       if r["compliant"] and cap_only_authorises(r["seed"], r["family"])),
        authorised_correctly_count=sum(1 for r in rows if r["compliant"]
                                       and cap_only_authorises(r["seed"], r["family"])),
        violations_authorised_paise=sum(r["proposed_paise"] for r in rows
                                        if not r["compliant"]
                                        and (r["seed"], r["family"]) in baseline_escape_set),
        violations_authorised_count=len(baseline_escapes),
        legitimate_refused_paise=sum(r["proposed_paise"] for r in rows if r["compliant"]
                                     and not cap_only_authorises(r["seed"], r["family"])),
        legitimate_refused_count=sum(1 for r in rows if r["compliant"]
                                     and not cap_only_authorises(r["seed"], r["family"])),
    )

    no_layer_mix = OutcomeMix(
        authorised_correctly_paise=sum(r["proposed_paise"] for r in compliant),
        authorised_correctly_count=len(compliant),
        violations_authorised_paise=sum(r["proposed_paise"] for r in violating),
        violations_authorised_count=len(violating),
    )

    configs = {
        "no_layer": no_layer_mix,
        "cap_only_guard": cap_only_mix,
        "action_firewall": firewall_mix,
    }
    cost = compare(configs, CostAssumptions())
    cost["sensitivity"] = sensitivity(configs, CostAssumptions())

    report = {
        "schema_version": "agent-authorization-benchmark@2",
        "scope": (
            "Synthetic, deterministic policy-compliance measurement of the merchant "
            "authorization layer. Constructed proposals, not sampled live agent "
            "behaviour. No claim of production conversion, settlement, or recovered "
            "revenue. Rupee figures are face value of synthetic carts."
        ),
        "corpus": {
            "seeds": len(SEEDS),
            "families": len(FAMILIES),
            "cases": len(rows),
            "goal_fixtures": [g[0] for g in GOAL_FIXTURES],
            "distinct_carts": len({r["cart_signature"] for r in rows}),
            "compliant_cases": len(compliant),
            "violating_cases": len(violating),
            "k": args.k,
        },
        "headline": {
            "completion_under_policy": round(cup, 4),
            "cup_compliant_only": round(
                sum(1 for r in compliant if r["completed"] and not r["violation_escaped"])
                / len(compliant), 4) if compliant else 0.0,
            "replay_identity": round(replay_identity, 4),
            "violation_escape_rate": round(
                sum(1 for r in violating if r["violation_escaped"]) / len(violating), 4),
            "acceptance_rate_compliant": round(
                sum(1 for r in compliant if r["completed"]) / len(compliant), 4),
            "repair_rate": round(len(repaired) / len(refused_first), 4) if refused_first else 0.0,
            "false_positive_rate": round(len(fp) / len(compliant), 4) if compliant else 0.0,
        },
        "money_paise": {
            "proposed": proposed_total,
            "settled_with_layer": settled_total,
            "recovered_by_repair": repaired_value,
            "false_positive_cost": fp_cost,
            "counterfactual_settled_without_layer": proposed_total,
            "counterfactual_violating_value_that_would_have_completed": cf_bad_value,
        },
        "cap_only_baseline": {
            "what_it_checks": "cart total <= envelope cap, and nothing else",
            "violations_it_would_authorise": len(baseline_escapes),
            "of_violating_cases": len(violating),
            "escape_rate": round(len(baseline_escapes) / len(violating), 4) if violating else 0.0,
        },
        "holdout": {
            "dev_seeds": len(DEV_SEEDS),
            "held_out_seeds": len(HELD_OUT_SEEDS),
            "held_out_violation_escape_rate": round(
                sum(1 for r in rows if r["seed"] in HELD_OUT_SEEDS
                    and not r["compliant"] and r["violation_escaped"])
                / max(1, sum(1 for r in rows if r["seed"] in HELD_OUT_SEEDS and not r["compliant"])),
                4),
            "held_out_false_positive_rate": round(
                sum(1 for r in rows if r["seed"] in HELD_OUT_SEEDS and r["false_positive"])
                / max(1, sum(1 for r in rows if r["seed"] in HELD_OUT_SEEDS and r["compliant"])),
                4),
        },
        "cost_model": cost,
        "risk_by_dimension": per_dim,
        "by_family": per_family,
        "citations": {
            "cup_and_risk_ratio": "Levy, Wiesel, Marreed et al., ST-WebAgentBench, arXiv:2410.06703, ICLR 2026",
            "severity_bands": "OURS, not from any paper. ST-WebAgentBench defines the ratio and publishes no bands.",
            "baseline_and_holdout_practice": "Kapoor, Stroebl et al., arXiv:2407.01502",
            "prior_deterministic_commerce_benchmark": "AIP-Bench, arXiv:2607.21824",
            "prior_merchant_side_architecture": "Sfiris, arXiv:2607.18347",
            "real_agent_failure_rates": "Allouah et al., arXiv:2508.02630",
            "reporting_checklist": "Agentic Benchmark Checklist, arXiv:2507.02825",
        },
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        h, m = report["headline"], report["money_paise"]
        print("Agent-authorization benchmark")
        print(f"  corpus                      {len(rows)} cases "
              f"({len(SEEDS)} seeds x {len(FAMILIES)} families), k={args.k}")
        comp = report["corpus"]
        print(f"  composition                 {comp['compliant_cases']} legitimate / "
              f"{comp['violating_cases']} constructed policy violations")
        print(f"  Completion under Policy     {h['completion_under_policy']:.1%}   "
              f"(share of ALL proposals ending in a clean completed order)")
        print(f"    of legitimate proposals   {h['cup_compliant_only']:.1%}")
        print(f"  replay identity ({replays}x)      {h['replay_identity']:.1%}   "
              f"(regression guard, not a reliability metric)")
        print(f"  violation escape rate       {h['violation_escape_rate']:.2%}")
        print(f"  acceptance (compliant)      {h['acceptance_rate_compliant']:.1%}")
        print(f"  repair rate (of refused)    {h['repair_rate']:.1%}")
        print(f"  false-positive rate         {h['false_positive_rate']:.2%}")
        print(f"  false-positive cost         Rs {m['false_positive_cost']/100:,.2f}")
        print(f"  value recovered by repair   Rs {m['recovered_by_repair']/100:,.2f}")
        print(f"  value that would have completed without the layer, "
              f"in violation  Rs {m['counterfactual_violating_value_that_would_have_completed']/100:,.2f}")
        b, ho = report["cap_only_baseline"], report["holdout"]
        print(f"  cap-only guard would let through  {b['violations_it_would_authorise']} "
              f"of {b['of_violating_cases']} violations ({b['escape_rate']:.1%})")
        print(f"  held out ({ho['held_out_seeds']} unseen seeds)   escape "
              f"{ho['held_out_violation_escape_rate']:.2%}, false-positive "
              f"{ho['held_out_false_positive_rate']:.2%}")
        print("\n  modelled cost of each configuration (assumptions, not measurements):")
        for name, c in cost["configurations"].items():
            print(f"    {name:20} Rs {c['total_paise']/100:>12,.0f}")
        sens = cost["sensitivity"]
        print(f"    lowest cost: {cost['lowest_cost']}  ·  ordering robust to every "
              f"single-assumption sweep: {sens['ordering_is_robust']}")
        if sens["assumptions_that_change_the_answer"]:
            print(f"    assumptions that flip it: {sens['assumptions_that_change_the_answer']}")
        print("\n  risk by policy dimension (bands are ours, not ST-WebAgentBench's):")
        for dim, d in per_dim.items():
            print(f"    {dim:26} {d['risk_ratio']:.2%}  {d['risk_band']}")
        print(f"\n  {report['scope']}")

    failed = (
        report["headline"]["violation_escape_rate"] > 0
        or report["headline"]["replay_identity"] < 1.0
    )
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
