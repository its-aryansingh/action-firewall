"""Tests for envelope drafting modes (replay, deterministic, llm) and strict slot validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import catalog
from app.config import get_settings
from app.envelope import (
    build_quote,
    compute_envelope_hash,
    draft_envelope,
    validate_slots,
    verify_quote,
)
from app.models import (
    AutopilotScenario,
    Cart,
    CartLine,
    EnvelopeDraftRequest,
    EnvelopeSlot,
    EnvelopeStatus,
    PurchaseEnvelope,
)


def test_replay_mode_reproduces_recorded_slots_byte_for_byte(monkeypatch):
    monkeypatch.setenv("ENVELOPE_DRAFTING_MODE", "replay")
    get_settings.cache_clear()

    goal = "Buy supplies for a pasta dinner"
    draft = draft_envelope(
        EnvelopeDraftRequest(goal=goal, max_total_rupees=600)
    )
    assert len(draft.slots) == 3
    assert draft.slots[0].required_tags == ["pasta", "staple"]
    assert draft.slots[1].required_tags == ["pasta", "sauce"]
    assert draft.slots[2].required_tags == ["italian", "fresh", "herb"]

    get_settings.cache_clear()


def test_slot_validation_rejects_tag_outside_vocabulary():
    bad_slot = EnvelopeSlot(
        id="bad",
        label="Bad slot",
        required_tags=["not_a_real_tag_in_catalog"],
        quantity=1,
    )
    assert validate_slots([bad_slot]) is None


def test_slot_validation_rejects_more_than_four_slots():
    slots = [
        EnvelopeSlot(id=f"s{i}", label=f"Slot {i}", required_tags=["pasta"], quantity=1)
        for i in range(9)
    ]
    assert validate_slots(slots) is None


def test_slot_validation_rejects_empty_slots():
    assert validate_slots([]) is None


def test_slot_validation_rejects_invalid_quantity():
    bad_qty = EnvelopeSlot.model_construct(
        id="s", label="Bad qty", required_tags=["pasta"], quantity=0
    )
    assert validate_slots([bad_qty]) is None

    bad_qty_large = EnvelopeSlot.model_construct(
        id="s", label="Bad qty", required_tags=["pasta"], quantity=101
    )
    assert validate_slots([bad_qty_large]) is None


def test_gift_cards_cannot_survive_verify_quote():
    # Even if an attacker drafted a slot with gift_cards category or tag
    env = PurchaseEnvelope(
        id="env_test_gift_card",
        user_id="user_demo",
        agent_id="agent_safe_autopilot:test",
        label="Gift Card attempt",
        goal="Buy a gift card",
        merchant_id="merchant_demo",
        max_total_paise=100000,
        fulfillment_profile_id="profile_home",
        delivery_deadline=2000000000.0,
        expires_at=2000000000.0,
        slots=[EnvelopeSlot(id="gft", label="Gift card", required_tags=["card"], quantity=1)],
        blocked_categories=["gift_cards"],
        status=EnvelopeStatus.ACTIVE,
        version=2,
        envelope_hash="",
        mandate_id="mandate_test",
        created_at=1800000000.0,
        updated_at=1800000000.0,
    )
    env = env.model_copy(update={"envelope_hash": compute_envelope_hash(env)})

    # Construct a quote that tries to smuggle a gift card
    card_line = CartLine(
        sku="SKU-GFT-001",
        name="Gift Card ₹5000",
        category="gift_cards",
        unit_price_paise=500_000,
        qty=1,
    )
    quote, _ = build_quote(env, AutopilotScenario.NORMAL)
    smuggled_quote = quote.model_copy(
        update={"cart": Cart(lines=[card_line]), "quote_hash": ""}
    )
    from app.envelope import compute_quote_hash
    smuggled_quote = smuggled_quote.model_copy(
        update={"quote_hash": compute_quote_hash(smuggled_quote)}
    )

    decision = verify_quote(env, smuggled_quote)
    assert decision.allowed is False
    delta_fields = [d.field for d in decision.deltas]
    assert any("category" in f for f in delta_fields)


def test_deterministic_mode_still_works_with_no_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("ENVELOPE_DRAFTING_MODE", "deterministic")
    get_settings.cache_clear()

    # Move fixture path to a non-existent file
    import app.envelope as env_mod
    monkeypatch.setattr(env_mod, "FIXTURE_PATH", tmp_path / "nonexistent.json")

    draft = draft_envelope(
        EnvelopeDraftRequest(goal="Buy supplies for a pasta dinner", max_total_rupees=600)
    )
    assert len(draft.slots) == 3
    assert draft.slots[0].id == "pasta"

    get_settings.cache_clear()
