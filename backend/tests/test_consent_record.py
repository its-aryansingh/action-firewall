"""Proving what the customer was shown, not merely that they clicked.

Every consent system records THAT a human approved. Almost none record WHAT WAS
ON THE SCREEN when they did — which is what every consent dispute is actually
about. "The customer approved envelope env_9f3a" is a database row; it persuades
nobody who does not already trust the database.

This works only because `render_envelope_english` is a pure function of the
envelope. That decision was made for a different reason — so the sentence a
shopper approves cannot drift when a shelf is restocked — and provability falls
out of it: given the envelope, anyone can recompute the exact sentence displayed.

The attacks below are the point. Note especially
`test_rewriting_the_sentence_and_its_hash_together_is_still_caught`: hash-only
verification would pass it. Recomputing the sentence from the rule does not,
because the sentence was never independent evidence — it is derived.
"""
import copy
import hashlib
import os
import tempfile

import pytest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "consent.db")
os.environ["DEMO_MODE"] = "true"
os.environ["ENVELOPE_DRAFTING_MODE"] = "deterministic"
os.environ["OPENAI_API_KEY"] = ""

from app import store  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.consent import (  # noqa: E402
    CONSENT_RECORD_SCHEMA,
    build_consent_record,
    verify_consent_record,
)
from app.envelope import draft_envelope, render_envelope_english  # noqa: E402
from app.models import EnvelopeDraftRequest  # noqa: E402


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "consent.db"))
    monkeypatch.setenv("ENVELOPE_DRAFTING_MODE", "deterministic")
    get_settings.cache_clear()
    store.init_db()
    yield
    get_settings.cache_clear()


def activated_envelope():
    draft = draft_envelope(
        EnvelopeDraftRequest(goal="Weeknight pasta dinner for four", max_total_rupees=7840)
    )
    store.save_envelope_draft(draft)
    return store.activate_envelope(draft.id, draft.envelope_hash)


def record():
    return build_consent_record(activated_envelope())


# ---------------------------------------------------------------------------
# It holds when nothing has been touched
# ---------------------------------------------------------------------------
def test_an_untouched_record_verifies():
    result = verify_consent_record(record())
    assert result["valid"] is True
    assert result["schema"] == CONSENT_RECORD_SCHEMA


def test_the_record_carries_the_sentence_the_rule_renders():
    env = activated_envelope()
    rec = build_consent_record(env)
    assert rec["displayed_text"] == render_envelope_english(env)
    assert rec["displayed_text_hash"] == hashlib.sha256(
        rec["displayed_text"].encode("utf-8")
    ).hexdigest()


def test_verification_needs_no_database_and_no_secret():
    """The record must verify from its own contents. If verification reached for
    the database, only the party holding the database could verify — which is
    the difference between evidence and an assertion."""
    rec = record()
    get_settings.cache_clear()
    os.environ["DB_PATH"] = "/nonexistent/path/should-never-be-opened.db"
    try:
        assert verify_consent_record(rec)["valid"] is True
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Every way of doctoring it afterwards
# ---------------------------------------------------------------------------
def tampered(**changes):
    rec = copy.deepcopy(record())
    for path, value in changes.items():
        if path.startswith("envelope."):
            rec["envelope"][path.split(".", 1)[1]] = value
        else:
            rec[path] = value
    return verify_consent_record(rec)


def test_raising_the_cap_afterwards_is_caught():
    result = tampered(**{"envelope.max_total_paise": 5_000_000})
    assert result["valid"] is False
    assert result["failed_field"] == "envelope_hash"
    assert "changed after the fact" in result["reason"]


def test_deleting_a_blocked_tag_afterwards_is_caught():
    """Quietly widening a rule is the interesting attack: the envelope still
    looks reasonable, and the customer's approval appears to cover it."""
    result = tampered(**{"envelope.blocked_tags": []})
    assert result["valid"] is False
    assert result["failed_field"] == "envelope_hash"


def test_adding_a_slot_afterwards_is_caught():
    rec = copy.deepcopy(record())
    rec["envelope"]["slots"].append(
        {"id": "extra", "label": "Extra", "required_tags": ["premium"], "quantity": 1}
    )
    assert verify_consent_record(rec)["valid"] is False


def test_rewriting_the_sentence_is_caught():
    rec = copy.deepcopy(record())
    rec["displayed_text"] = rec["displayed_text"].replace("Rs 7,840", "Rs 70,000")
    result = verify_consent_record(rec)
    assert result["valid"] is False
    assert result["failed_field"] == "displayed_text"


def test_rewriting_the_sentence_and_its_hash_together_is_still_caught():
    """A verifier that only checked text against its own hash would pass this.
    The sentence is not independent evidence — it is derived from the rule — so
    it is recomputed rather than merely checked."""
    rec = copy.deepcopy(record())
    forged = "Spend anything you like."
    rec["displayed_text"] = forged
    rec["displayed_text_hash"] = hashlib.sha256(forged.encode("utf-8")).hexdigest()
    result = verify_consent_record(rec)
    assert result["valid"] is False
    assert result["failed_field"] == "displayed_text"


def test_a_record_from_an_unknown_schema_is_refused():
    rec = copy.deepcopy(record())
    rec["schema"] = "some-other-thing@9"
    assert verify_consent_record(rec)["failed_field"] == "schema"


def test_a_malformed_envelope_is_refused_rather_than_crashing():
    rec = copy.deepcopy(record())
    rec["envelope"] = {"not": "an envelope"}
    result = verify_consent_record(rec)
    assert result["valid"] is False
    assert result["failed_field"] == "envelope"


# ---------------------------------------------------------------------------
# The record has to be created on every activation path, not just the easy one
# ---------------------------------------------------------------------------
def test_direct_activation_records_what_was_displayed():
    env = activated_envelope()
    events = [
        e for e in store.audit_trail(limit=100)
        if e["event"] == "ENVELOPE_ACTIVATED" and e["payload"].get("envelope_id") == env.id
    ]
    assert events, "activation must be audited"
    payload = events[0]["payload"]
    assert payload["displayed_text"] == render_envelope_english(env)
    assert payload["displayed_text_hash"] == hashlib.sha256(
        payload["displayed_text"].encode("utf-8")
    ).hexdigest()


def test_the_recorded_sentence_describes_the_activated_envelope_not_the_draft():
    """Activation re-hashes the envelope and bumps its version. Rendering the
    draft would record a sentence describing a rule that no longer exists."""
    draft = draft_envelope(
        EnvelopeDraftRequest(goal="Weeknight pasta dinner for four", max_total_rupees=7840)
    )
    store.save_envelope_draft(draft)
    activated = store.activate_envelope(draft.id, draft.envelope_hash)
    assert activated.envelope_hash != draft.envelope_hash

    payload = [
        e for e in store.audit_trail(limit=100)
        if e["event"] == "ENVELOPE_ACTIVATED" and e["payload"].get("envelope_id") == draft.id
    ][0]["payload"]
    assert payload["envelope_hash"] == activated.envelope_hash
    assert payload["displayed_text"] == render_envelope_english(activated)


def test_the_record_states_what_it_cannot_prove():
    """An evidence artifact that does not name its own limits invites being read
    as proving more than it does."""
    rec = record()
    assert "not" in rec["does_not_prove"].lower()
    assert "legal instrument" in rec["does_not_prove"]
    result = verify_consent_record(rec)
    assert any("HMAC" in line for line in result["not_checked"])
    assert any("read" in line for line in result["not_checked"])
