"""Evidence a merchant can put in front of someone who does not trust them.

An agent-initiated charge carries no cardholder-present evidence. When the
customer says "my agent was not authorised to buy that", the merchant carries the
chargeback, and until now there was nothing to produce. A layer that decides with
a language model cannot fix this: the samples that produced the decision are
gone, and "the model returned 0.87" is not an artifact anyone can check.

A deterministic layer can do something strictly better than keep a record. It can
hand over everything the decision consumed and let a third party RE-EXECUTE it.
That is the claim this module exists to support, and check 10 in
`verify_dispute_pack` is where it is actually made good.

WHAT A PACK LETS ANYONE RE-DERIVE, from the published source alone:
  - the rule the customer approved, and the words they were shown
  - that the authority minted is bound to that rule and to this exact quote
  - that the recorded decision is the decision this code produces on these inputs

WHAT IT DOES NOT:
  - stock at decision time. Nobody can prove what was on a shelf. The reading is
    the merchant's attestation; the audit chain fixes WHEN it was recorded, not
    what it was. Every honest evidence artifact has an edge like this, and the
    ones worth trusting are the ones that name it.
  - the receipt HMAC, which needs the merchant's signing key.
  - that a human read anything.
"""
from __future__ import annotations

import time

from . import catalog, store
from .actions import canonicalize_action
from .authorization import cart_hash as compute_cart_hash
from .consent import build_consent_record
from .envelope import compute_quote_hash, verify_quote
from .merchant import CATALOG_REVISION, compute_catalog_revision
from .models import MerchantQuote, PurchaseEnvelope
from .receipts import build_receipt

DISPUTE_PACK_SCHEMA = "action-firewall/dispute-pack@1"


def build_dispute_pack(purchase_attempt_id: str) -> dict | None:
    """Everything one authorisation attempt consumed, in one file."""
    record = store.get_decision_record(purchase_attempt_id)
    if record is None:
        return None

    # The envelope AS IT WAS when the decision was taken, not as it is now. A
    # consumed envelope carries a bumped version and a new hash, so building the
    # consent record from today's row produces a pack whose own consent record
    # and grant disagree about which rule the customer approved. The verifier
    # catches that — which is how this was found — but a pack that fails its own
    # verifier is worse than no pack.
    envelope = (
        PurchaseEnvelope.model_validate(record["envelope"])
        if record.get("envelope")
        else store.get_envelope(record["envelope_id"])
    )
    grant = store.get_action_grant(record["grant_id"]) if record["grant_id"] else None

    audit_rows = [
        event
        for event in store.audit_trail(limit=2000)
        if (event.get("payload") or {}).get("envelope_id") == record["envelope_id"]
    ]
    chain = store.verify_audit_chain()

    return {
        "schema": DISPUTE_PACK_SCHEMA,
        "generated_at": time.time(),
        "purchase_attempt_id": purchase_attempt_id,
        "outcome": record["outcome"],
        "merchant_id": envelope.merchant_id if envelope else None,
        "consent": build_consent_record(envelope) if envelope else None,
        "quote": record["quote"],
        "quote_hash": record["quote_hash"],
        "decision": record["decision"],
        "decided_at": record["decided_at"],
        "grant": grant.model_dump(mode="json") if grant else None,
        "receipt": build_receipt(grant).model_dump(mode="json") if grant else None,
        # The WHOLE catalog, not only the SKUs in the cart. catalog_revision is a
        # digest of every row, so a partial snapshot cannot be checked against it
        # — and a snapshot nobody can check is not evidence, it is a claim.
        # 46 rows is ~14 KB; the cost of closing the pack is nothing.
        "catalog_snapshot": catalog.load_catalog(),
        "catalog_revision": record["catalog_revision"],
        "stock_at_decision": record["stock_at_decision"],
        "audit": {
            "entries": audit_rows,
            "head_hash": chain.get("head_hash"),
            "chain_valid_at_export": chain.get("valid"),
        },
        "verify_with": "python scripts/verify_dispute_pack.py <file.json>",
    }


# ---------------------------------------------------------------------------
# Verification — pure. No database, no signing key, no network.
# ---------------------------------------------------------------------------
def _fail(check: str, reason: str, expected: object, actual: object) -> dict:
    return {
        "schema": DISPUTE_PACK_SCHEMA,
        "valid": False,
        "failed_check": check,
        "reason": reason,
        "expected": str(expected)[:400],
        "actual": str(actual)[:400],
    }


def verify_dispute_pack(pack: dict) -> dict:
    """Re-derive every claim in a dispute pack, in dependency order.

    Reports the FIRST check that fails and what it was. A bare "invalid" tells
    the person holding this nothing they can act on, and they are usually the
    person who has to explain it to someone else.
    """
    from .consent import verify_consent_record

    if pack.get("schema") != DISPUTE_PACK_SCHEMA:
        return _fail("schema", "unknown pack schema", DISPUTE_PACK_SCHEMA, pack.get("schema"))

    # 1 — the consent record: the rule and the words the customer was shown
    consent = pack.get("consent")
    if not consent:
        return _fail("consent", "the pack carries no consent record", "a consent record", None)
    consent_result = verify_consent_record(consent)
    if not consent_result["valid"]:
        return _fail(
            "consent",
            f"the consent record does not hold: {consent_result['reason']}",
            consent_result["expected"],
            consent_result["actual"],
        )
    envelope = PurchaseEnvelope.model_validate(consent["envelope"])

    # 2 — the catalog snapshot is the one the decision was taken against
    snapshot = pack.get("catalog_snapshot")
    if not snapshot:
        return _fail("catalog_snapshot", "the pack carries no catalog", "catalog rows", None)
    recomputed_revision = compute_catalog_revision(snapshot)
    if recomputed_revision != pack.get("catalog_revision"):
        return _fail(
            "catalog_revision",
            "the catalog in this pack is not the one the decision saw: a product "
            "fact was changed after the fact",
            recomputed_revision,
            pack.get("catalog_revision"),
        )

    # 3 — the quote
    try:
        quote = MerchantQuote.model_validate(pack["quote"])
    except Exception as exc:
        return _fail("quote", f"the quote does not parse: {exc}", "a valid quote", "malformed")
    recomputed_quote_hash = compute_quote_hash(quote)
    if recomputed_quote_hash != pack.get("quote_hash"):
        return _fail(
            "quote_hash",
            "the quote in this pack does not hash to the recorded value: a price "
            "or a line was changed",
            recomputed_quote_hash,
            pack.get("quote_hash"),
        )

    # 4-7 — the authority is bound to THIS rule and THIS quote
    grant = pack.get("grant")
    if grant:
        if grant.get("envelope_hash") != consent["envelope_hash"]:
            return _fail(
                "grant.envelope_hash",
                "the authority is bound to a different rule from the one the "
                "customer approved",
                consent["envelope_hash"],
                grant.get("envelope_hash"),
            )
        if grant.get("quote_hash") != recomputed_quote_hash:
            return _fail(
                "grant.quote_hash",
                "the authority is bound to a different quote from the one in this pack",
                recomputed_quote_hash,
                grant.get("quote_hash"),
            )
        recomputed_cart_hash = compute_cart_hash(quote.cart)
        if grant.get("cart_hash") != recomputed_cart_hash:
            return _fail(
                "grant.cart_hash",
                "the authority is bound to a different basket",
                recomputed_cart_hash,
                grant.get("cart_hash"),
            )

    # 8 — the receipt describes this grant
    receipt = pack.get("receipt")
    if receipt and grant:
        for field in ("grant_id", "envelope_hash", "args_hash", "cart_hash", "quote_hash"):
            expected = grant.get("id") if field == "grant_id" else grant.get(field)
            if receipt.get(field) != expected:
                return _fail(
                    f"receipt.{field}",
                    "the receipt does not describe the authority in this pack",
                    expected,
                    receipt.get(field),
                )

    # 9 — the audit slice hangs together
    entries = (pack.get("audit") or {}).get("entries") or []
    ordered = sorted((e for e in entries if e.get("seq") is not None), key=lambda e: e["seq"])
    for previous, current in zip(ordered, ordered[1:]):
        if current["seq"] == previous["seq"] + 1 and current["prev_hash"] != previous["entry_hash"]:
            return _fail(
                "audit",
                f"audit entries {previous['seq']} and {current['seq']} are adjacent but "
                "not linked: the trail was cut or reordered",
                previous["entry_hash"],
                current["prev_hash"],
            )

    # 10 — THE DECISION ITSELF RE-DERIVES.
    # Rebuild the exact catalog state the decision saw and run the same verifier.
    # Everything above proves the pack is internally consistent; only this proves
    # the outcome was correct, and it is the check a design that consults a model
    # at authorisation time can never offer, because its inputs no longer exist.
    recorded = pack.get("decision") or {}
    stock = pack.get("stock_at_decision") or {}
    previous_overrides = dict(catalog._STOCK_OVERRIDE)
    try:
        catalog.use_snapshot(snapshot)
        catalog.reset_stock()
        for sku, units in stock.items():
            catalog.set_stock(sku, int(units))
        rederived = verify_quote(envelope, quote, now=pack.get("decided_at"))
    finally:
        catalog.clear_snapshot()
        catalog.reset_stock()
        for sku, units in previous_overrides.items():
            catalog.set_stock(sku, units)

    if bool(rederived.allowed) != bool(recorded.get("allowed")):
        return _fail(
            "decision.allowed",
            "re-running the authorisation on the recorded inputs gives a different "
            "answer: the recorded outcome is not what this rule produces",
            rederived.allowed,
            recorded.get("allowed"),
        )
    rederived_fields = sorted(delta.field for delta in rederived.deltas)
    recorded_fields = sorted(item.get("field", "") for item in recorded.get("deltas", []))
    if rederived_fields != recorded_fields:
        return _fail(
            "decision.deltas",
            "re-running the authorisation produces different reasons from the ones "
            "recorded",
            rederived_fields,
            recorded_fields,
        )

    return {
        "schema": DISPUTE_PACK_SCHEMA,
        "valid": True,
        "purchase_attempt_id": pack.get("purchase_attempt_id"),
        "outcome": pack.get("outcome"),
        "independently_rederived": [
            "the rule the customer approved, and the words they were shown",
            "the catalog facts the decision was taken against",
            "the quote, and that the authority is bound to it",
            "that the authority is bound to the approved rule and basket",
            "that the receipt describes this authority",
            "that the audit entries in this pack are linked",
            "THE DECISION ITSELF — re-running it on these inputs gives this outcome",
        ],
        "attested_by_the_merchant_not_proven": [
            "stock at decision time — nobody can prove what was on a shelf; the "
            "audit chain fixes when the reading was recorded, not what it was",
            "the receipt HMAC — needs the merchant's signing key",
            "that a human read the sentence — unknowable from any artifact",
        ],
    }
