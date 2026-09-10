"""Tests for narrowing-only Purchase Envelope amendments (WO-2).

Enforces Invariant 13: widening authority is a fresh approval by definition.
Amendments may only narrow the envelope (lower cap, shorter expiry, fewer slots,
more blocked tags/categories). Any widening edit is refused with HTTP 409 and
Policy Deltas requiring fresh approval.
"""
from __future__ import annotations

import copy
import time
import pytest
from starlette.testclient import TestClient
from hypothesis import given, settings as hyp_settings, strategies as st

from app.main import app
from app import catalog, store
from app.buyer_models import EnvelopeAmendRequest
from app.envelope import (
    compute_envelope_hash,
    compute_quote_hash,
    draft_envelope,
    envelope_readback,
    verify_quote,
)
from app.models import (
    Cart,
    CartLine,
    EnvelopeActivateRequest,
    EnvelopeDraftRequest,
    EnvelopeStatus,
    MerchantQuote,
    PurchaseEnvelope,
)


@pytest.fixture(autouse=True)
def clean_database(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_amend.db")
    monkeypatch.setenv("DB_PATH", db_file)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("ENVELOPE_DRAFTING_MODE", "deterministic")
    store.init_db()
    catalog.reset_stock()
    yield
    catalog.reset_stock()


def _create_test_intent(client: TestClient, goal: str = "Weeknight pasta dinner for four", budget_paise: int = 60000) -> dict:
    resp = client.post(
        "/agent-commerce/v1/intents",
        json={
            "agent_request_id": f"req_draft_{int(time.time() * 1000)}",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": "sess_demo",
            "natural_language_intent": goal,
            "budget_paise": budget_paise,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# 1. Lowering the cap is accepted; hash & version change; readback worst-case
#    unchanged but cap_binds may flip.
# ---------------------------------------------------------------------------

def test_lowering_cap_accepted():
    client = TestClient(app)
    data = _create_test_intent(client, budget_paise=60000)
    intent_id = data["intent_id"]
    draft = data["draft_envelope"]
    orig_worst_case = data["readback"]["worst_case_total_paise"]

    # Lower cap to 30000 paise (still above 0)
    res = client.post(
        f"/agent-commerce/v1/intents/{intent_id}/amend",
        json={
            "expected_envelope_hash": draft["envelope_hash"],
            "max_total_paise": 30000,
        },
    )
    assert res.status_code == 200, res.text
    amended = res.json()
    amended_env = amended["draft_envelope"]
    assert amended_env["version"] == draft["version"] + 1
    assert amended_env["envelope_hash"] != draft["envelope_hash"]
    assert amended_env["max_total_paise"] == 30000

    # Readback check
    readback = amended["readback"]
    assert readback["max_total_paise"] == 30000
    assert readback["worst_case_total_paise"] == orig_worst_case
    if 30000 < orig_worst_case:
        assert readback["cap_binds"] is True
    else:
        assert readback["cap_binds"] is False


# ---------------------------------------------------------------------------
# 2. Raising the cap refused, recovery="fresh_approval", envelope byte-identical.
# ---------------------------------------------------------------------------

def test_raising_cap_refused():
    client = TestClient(app)
    data = _create_test_intent(client, budget_paise=60000)
    intent_id = data["intent_id"]
    draft = data["draft_envelope"]

    # Attempt to raise cap to 70000 paise
    res = client.post(
        f"/agent-commerce/v1/intents/{intent_id}/amend",
        json={
            "expected_envelope_hash": draft["envelope_hash"],
            "max_total_paise": 70000,
        },
    )
    assert res.status_code == 409
    decision = res.json()
    assert decision["allowed"] is False
    assert decision["code"] == "BLOCK_ENVELOPE_WIDENING_PROHIBITED"
    assert len(decision["deltas"]) == 1
    d = decision["deltas"][0]
    assert d["field"] == "max_total_paise"
    assert d["recovery"] == "fresh_approval"

    # Envelope in DB must be untouched and identical
    env_in_db = store.get_envelope(draft["id"])
    assert env_in_db is not None
    assert env_in_db.max_total_paise == 60000
    assert env_in_db.version == draft["version"]
    assert env_in_db.envelope_hash == draft["envelope_hash"]


# ---------------------------------------------------------------------------
# 3. Dropping a slot accepted; readback.slots shrinks; worst case falls.
# ---------------------------------------------------------------------------

def test_dropping_slot_accepted():
    client = TestClient(app)
    data = _create_test_intent(client, goal="Weeknight pasta dinner for four", budget_paise=60000)
    intent_id = data["intent_id"]
    draft = data["draft_envelope"]
    assert len(draft["slots"]) >= 2, "Test needs multi-slot draft"
    orig_worst_case = data["readback"]["worst_case_total_paise"]
    slot_to_drop = draft["slots"][0]["id"]

    res = client.post(
        f"/agent-commerce/v1/intents/{intent_id}/amend",
        json={
            "expected_envelope_hash": draft["envelope_hash"],
            "drop_slot_ids": [slot_to_drop],
        },
    )
    assert res.status_code == 200, res.text
    amended = res.json()
    amended_env = amended["draft_envelope"]
    assert len(amended_env["slots"]) == len(draft["slots"]) - 1
    assert slot_to_drop not in [s["id"] for s in amended_env["slots"]]

    # Readback shrinks and worst case falls
    readback = amended["readback"]
    assert len(readback["slots"]) == len(draft["slots"]) - 1
    assert readback["worst_case_total_paise"] < orig_worst_case


# ---------------------------------------------------------------------------
# 4. Dropping every slot refused.
# ---------------------------------------------------------------------------

def test_dropping_every_slot_refused():
    client = TestClient(app)
    data = _create_test_intent(client, budget_paise=60000)
    intent_id = data["intent_id"]
    draft = data["draft_envelope"]
    all_slot_ids = [s["id"] for s in draft["slots"]]

    res = client.post(
        f"/agent-commerce/v1/intents/{intent_id}/amend",
        json={
            "expected_envelope_hash": draft["envelope_hash"],
            "drop_slot_ids": all_slot_ids,
        },
    )
    assert res.status_code == 409
    decision = res.json()
    assert decision["allowed"] is False
    assert any(d["field"] == "slots" and d["recovery"] == "fresh_approval" for d in decision["deltas"])

    # DB envelope untouched
    env_in_db = store.get_envelope(draft["id"])
    assert env_in_db is not None
    assert len(env_in_db.slots) == len(draft["slots"])


# ---------------------------------------------------------------------------
# 5. Adding a blocked tag accepted; admissible counts fall or stay same.
# ---------------------------------------------------------------------------

def test_adding_blocked_tag_accepted():
    client = TestClient(app)
    data = _create_test_intent(client, budget_paise=60000)
    intent_id = data["intent_id"]
    draft = data["draft_envelope"]

    res = client.post(
        f"/agent-commerce/v1/intents/{intent_id}/amend",
        json={
            "expected_envelope_hash": draft["envelope_hash"],
            "add_blocked_tags": ["cheese"],
        },
    )
    assert res.status_code == 200, res.text
    amended = res.json()
    amended_env = amended["draft_envelope"]
    assert "cheese" in amended_env["blocked_tags"]


# ---------------------------------------------------------------------------
# 6. Removing a blocked tag refused (assert extra="forbid" rejects it with 422).
# ---------------------------------------------------------------------------

def test_removing_blocked_tag_refused_by_model_schema():
    client = TestClient(app)
    data = _create_test_intent(client, budget_paise=60000)
    intent_id = data["intent_id"]
    draft = data["draft_envelope"]

    # Attempting to supply unapproved extra fields like remove_blocked_tags
    res = client.post(
        f"/agent-commerce/v1/intents/{intent_id}/amend",
        json={
            "expected_envelope_hash": draft["envelope_hash"],
            "remove_blocked_tags": ["eggs"],
        },
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# 7. Shortening expiry accepted, extending refused.
# ---------------------------------------------------------------------------

def test_shortening_expiry_accepted_extending_refused():
    client = TestClient(app)
    data = _create_test_intent(client, budget_paise=60000)
    intent_id = data["intent_id"]
    draft = data["draft_envelope"]
    orig_expiry = draft["expires_at"]

    # Shortening expiry is accepted
    short_expiry = orig_expiry - 300.0
    res_short = client.post(
        f"/agent-commerce/v1/intents/{intent_id}/amend",
        json={
            "expected_envelope_hash": draft["envelope_hash"],
            "expires_at": short_expiry,
        },
    )
    assert res_short.status_code == 200
    amended_draft = res_short.json()["draft_envelope"]
    assert amended_draft["expires_at"] == short_expiry

    # Extending expiry beyond current is refused
    long_expiry = amended_draft["expires_at"] + 600.0
    res_long = client.post(
        f"/agent-commerce/v1/intents/{intent_id}/amend",
        json={
            "expected_envelope_hash": amended_draft["envelope_hash"],
            "expires_at": long_expiry,
        },
    )
    assert res_long.status_code == 409
    decision = res_long.json()
    assert decision["allowed"] is False
    assert any(d["field"] == "expires_at" and d["recovery"] == "fresh_approval" for d in decision["deltas"])


# ---------------------------------------------------------------------------
# 8. Amending an active envelope refused.
# ---------------------------------------------------------------------------

def test_amending_active_envelope_refused():
    client = TestClient(app)
    data = _create_test_intent(client, budget_paise=60000)
    intent_id = data["intent_id"]
    draft = data["draft_envelope"]

    # Activate the envelope
    act_res = client.post(
        f"/agent-commerce/v1/envelopes/{draft['id']}/activate",
        json={"expected_envelope_hash": draft["envelope_hash"]},
    )
    assert act_res.status_code == 200

    # Attempt to amend after activation
    res = client.post(
        f"/agent-commerce/v1/intents/{intent_id}/amend",
        json={
            "expected_envelope_hash": draft["envelope_hash"],
            "max_total_paise": 30000,
        },
    )
    assert res.status_code == 409
    decision = res.json()
    assert decision["allowed"] is False
    assert any(d["field"] == "status" and d["recovery"] == "fresh_approval" for d in decision["deltas"])


# ---------------------------------------------------------------------------
# 9. Stale expected_envelope_hash refused.
# ---------------------------------------------------------------------------

def test_stale_expected_envelope_hash_refused():
    client = TestClient(app)
    data = _create_test_intent(client, budget_paise=60000)
    intent_id = data["intent_id"]

    res = client.post(
        f"/agent-commerce/v1/intents/{intent_id}/amend",
        json={
            "expected_envelope_hash": "sha256_stale_hash_from_earlier_turn",
            "max_total_paise": 30000,
        },
    )
    assert res.status_code == 409
    decision = res.json()
    assert decision["allowed"] is False
    assert any(d["field"] == "envelope_hash" and d["recovery"] == "fresh_approval" for d in decision["deltas"])


# ---------------------------------------------------------------------------
# 10. A request mixing one narrowing and one widening edit applies neither.
# ---------------------------------------------------------------------------

def test_mixed_narrowing_and_widening_applies_neither():
    client = TestClient(app)
    data = _create_test_intent(client, budget_paise=60000)
    intent_id = data["intent_id"]
    draft = data["draft_envelope"]

    # Mix lowering cap (narrowing) with extending expiry (widening)
    res = client.post(
        f"/agent-commerce/v1/intents/{intent_id}/amend",
        json={
            "expected_envelope_hash": draft["envelope_hash"],
            "max_total_paise": 40000,
            "expires_at": draft["expires_at"] + 5000.0,
        },
    )
    assert res.status_code == 409
    decision = res.json()
    assert decision["allowed"] is False
    assert any(d["field"] == "expires_at" and d["recovery"] == "fresh_approval" for d in decision["deltas"])

    # DB envelope must be completely untouched: cap NOT lowered!
    env_in_db = store.get_envelope(draft["id"])
    assert env_in_db is not None
    assert env_in_db.max_total_paise == 60000
    assert env_in_db.version == draft["version"]
    assert env_in_db.envelope_hash == draft["envelope_hash"]


# ---------------------------------------------------------------------------
# 11. Endpoint aliasing: /envelopes/{id}/amend works identically to /intents/{id}/amend
# ---------------------------------------------------------------------------

def test_envelope_id_endpoint_alias():
    client = TestClient(app)
    data = _create_test_intent(client, budget_paise=60000)
    draft = data["draft_envelope"]

    res = client.post(
        f"/agent-commerce/v1/envelopes/{draft['id']}/amend",
        json={
            "expected_envelope_hash": draft["envelope_hash"],
            "max_total_paise": 45000,
        },
    )
    assert res.status_code == 200
    assert res.json()["draft_envelope"]["max_total_paise"] == 45000


# ---------------------------------------------------------------------------
# 12. Hypothesis Property Test:
#     No sequence of narrowing amendments can authorise a quote the original
#     envelope would have refused.
# ---------------------------------------------------------------------------

@hyp_settings(max_examples=100, deadline=None)
@given(
    cap_cut_paise=st.integers(min_value=0, max_value=20000),
    expiry_cut_sec=st.floats(min_value=0.0, max_value=1000.0),
    add_blocked_tag=st.sampled_from(["cheese", "organic", "gluten", "sugar", "dairy"]),
    add_blocked_cat=st.sampled_from(["snacks", "beverages", "dairy", "bakery"]),
    quote_multiplier=st.integers(min_value=1, max_value=3),
)
def test_property_narrowing_amendments_never_authorise_what_original_refuses(
    cap_cut_paise: int,
    expiry_cut_sec: float,
    add_blocked_tag: str,
    add_blocked_cat: str,
    quote_multiplier: int,
):
    """If verify_quote(amended, quote).allowed is True, then verify_quote(original, quote).allowed must be True."""
    # Build baseline envelope
    base_env = draft_envelope(
        EnvelopeDraftRequest(goal="Weeknight pasta dinner for four", max_total_rupees=500)
    )
    # Activate copy so verify_quote does not immediately fail on status != active
    active_original = base_env.model_copy(update={"status": EnvelopeStatus.ACTIVE})

    # Create amended envelope with narrowing edits only
    new_cap = max(1000, base_env.max_total_paise - cap_cut_paise)
    new_expiry = base_env.expires_at - expiry_cut_sec
    new_tags = sorted(set(base_env.blocked_tags) | {add_blocked_tag})
    new_cats = sorted(set(base_env.blocked_categories) | {add_blocked_cat})

    amended_env = base_env.model_copy(
        update={
            "max_total_paise": new_cap,
            "expires_at": new_expiry,
            "blocked_tags": new_tags,
            "blocked_categories": new_cats,
            "version": base_env.version + 1,
            "status": EnvelopeStatus.ACTIVE,
        }
    )
    amended_env = amended_env.model_copy(
        update={"envelope_hash": compute_envelope_hash(amended_env)}
    )

    # Pick products from catalog that might satisfy slots
    cat_items = catalog.load_catalog()
    penne = next((p for p in cat_items if p["sku"] == "SKU-PAS-001"), cat_items[0])
    sauce = next((p for p in cat_items if p["sku"] == "SKU-SAU-001"), cat_items[1])

    # Construct test quote
    lines = [
        CartLine(
            sku=penne["sku"],
            name=penne["name"],
            category=penne["category"],
            unit_price_paise=penne["price_paise"],
            qty=quote_multiplier,
        ),
        CartLine(
            sku=sauce["sku"],
            name=sauce["name"],
            category=sauce["category"],
            unit_price_paise=sauce["price_paise"],
            qty=1,
        ),
    ]
    cart = Cart(lines=lines)
    quote = MerchantQuote(
        merchant_id=base_env.merchant_id,
        fulfillment_profile_id=base_env.fulfillment_profile_id,
        currency="INR",
        delivery_eta=base_env.created_at + 60,
        cart=cart,
        quote_hash="",
    )
    quote = quote.model_copy(update={"quote_hash": compute_quote_hash(quote)})

    eval_time = base_env.created_at + 100.0
    dec_original = verify_quote(active_original, quote, now=eval_time)
    dec_amended = verify_quote(amended_env, quote, now=eval_time)

    # THE CORE INVARIANT:
    # Any quote allowed by the amended envelope MUST have been allowed by the original.
    if dec_amended.allowed:
        assert dec_original.allowed, (
            f"Amended envelope allowed quote but original refused: "
            f"original deltas = {dec_original.deltas}"
        )
