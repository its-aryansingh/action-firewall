"""What the customer was shown when they approved — provable after the fact.

Every consent system records THAT a human clicked. Almost none record WHAT WAS
ON THE SCREEN when they did, and that is the thing every consent dispute is
actually about. "The customer approved envelope env_9f3a" is a database row; it
persuades nobody who does not already trust the database.

This module exists because `render_envelope_english` is a pure function of the
envelope. That was a design decision made for a different reason — so the
sentence a shopper approves cannot drift when a shelf is restocked — and this
falls out of it for free: given the envelope, ANYONE can recompute, verbatim,
the sentence that was displayed. Not "we logged that we showed them something",
but "here is the text, and it is derivable from the hash, so it cannot have been
written afterwards to suit us".

A competing design that re-interprets the customer's intent with a language
model at each transaction has no such artifact. There is no stable sentence to
recompute, because the rule was never written down — only a sentence and a model
that read it differently each time.

WHAT A CONSENT RECORD PROVES
  - the envelope in the record hashes to the hash the record claims
  - the sentence in the record is what this codebase renders for that envelope
  - therefore the displayed text and the enforced rule are the same object

WHAT IT DOES NOT PROVE
  - that a human read the sentence. It proves what was rendered, not what was
    understood. Nothing here is a legal instrument or a substitute for one.
  - anything about the receipt's HMAC. That needs the merchant's signing key and
    is verified separately, by whoever holds it.

The verifier needs the published source and nothing else — no database, no
secret, no network. That is the entire point: evidence a third party can check
is evidence; evidence only the record-keeper can check is an assertion.
"""
from __future__ import annotations

import hashlib

from .authorization import canonical_json
from .envelope import compute_envelope_hash, render_envelope_english
from .models import PurchaseEnvelope

CONSENT_RECORD_SCHEMA = "action-firewall/consent-record@1"


def consent_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_consent_record(
    envelope: PurchaseEnvelope,
    *,
    activated_at: float | None = None,
) -> dict:
    """The rule, the sentence rendered from it, and the bindings between them."""
    english = render_envelope_english(envelope)
    return {
        "schema": CONSENT_RECORD_SCHEMA,
        "envelope_id": envelope.id,
        "envelope_version": envelope.version,
        "envelope_hash": envelope.envelope_hash,
        "envelope": envelope.model_dump(mode="json"),
        "displayed_text": english,
        "displayed_text_hash": consent_text_hash(english),
        "status": envelope.status.value,
        "activated_at": activated_at,
        "proves": (
            "The rule shown to the customer and the rule enforced at dispatch are "
            "the same object: the sentence is a pure function of the envelope, and "
            "the envelope hashes to the value recorded here."
        ),
        "does_not_prove": (
            "That a human read or understood the sentence. This records what was "
            "rendered, not what was comprehended, and it is not a legal instrument."
        ),
        "verify_with": "python scripts/verify_consent_record.py <file.json>",
    }


def verify_consent_record(record: dict) -> dict:
    """Re-derive every claim in a consent record. Pure: no database, no secret.

    Reports the FIRST failing binding by name. "invalid" alone is useless to
    anyone trying to act on it.
    """
    def bad(field: str, reason: str, expected: object, actual: object) -> dict:
        return {
            "schema": CONSENT_RECORD_SCHEMA,
            "valid": False,
            "failed_field": field,
            "reason": reason,
            "expected": str(expected),
            "actual": str(actual),
        }

    if record.get("schema") != CONSENT_RECORD_SCHEMA:
        return bad("schema", "unknown record schema", CONSENT_RECORD_SCHEMA, record.get("schema"))

    try:
        envelope = PurchaseEnvelope.model_validate(record["envelope"])
    except Exception as exc:
        return bad("envelope", f"envelope does not parse: {exc}", "a valid envelope", "malformed")

    # 1. Does the embedded envelope hash to the value the record claims?
    recomputed_hash = compute_envelope_hash(envelope)
    if recomputed_hash != record.get("envelope_hash"):
        return bad(
            "envelope_hash",
            "the envelope in this record does not hash to the recorded value: a "
            "field of the approved rule was changed after the fact",
            recomputed_hash,
            record.get("envelope_hash"),
        )
    if envelope.envelope_hash != recomputed_hash:
        return bad(
            "envelope.envelope_hash",
            "the envelope's own stored hash disagrees with its contents",
            recomputed_hash,
            envelope.envelope_hash,
        )

    # 2. Is the recorded sentence what this codebase renders for that envelope?
    recomputed_text = render_envelope_english(envelope)
    if recomputed_text != record.get("displayed_text"):
        return bad(
            "displayed_text",
            "the recorded sentence is not what this rule renders: the customer was "
            "shown different words from the rule that was enforced",
            recomputed_text,
            record.get("displayed_text"),
        )
    recomputed_text_hash = consent_text_hash(recomputed_text)
    if recomputed_text_hash != record.get("displayed_text_hash"):
        return bad(
            "displayed_text_hash",
            "the sentence does not hash to the recorded value",
            recomputed_text_hash,
            record.get("displayed_text_hash"),
        )

    return {
        "schema": CONSENT_RECORD_SCHEMA,
        "valid": True,
        "envelope_id": record.get("envelope_id"),
        "envelope_hash": recomputed_hash,
        "displayed_text_hash": recomputed_text_hash,
        "checked": [
            "envelope hashes to the recorded value",
            "the envelope's own stored hash agrees with its contents",
            "the recorded sentence is exactly what this rule renders",
            "the sentence hashes to the recorded value",
        ],
        "not_checked": [
            "the receipt's HMAC signature — needs the merchant's signing key",
            "that a human read the sentence — unknowable from any artifact",
        ],
    }
