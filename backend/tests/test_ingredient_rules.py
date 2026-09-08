"""Ingredient-level (tag) prohibitions on a Purchase Envelope.

The rule these tests defend: a category allowlist cannot express a real business
constraint. Free-Range Eggs sit in category `dairy`, which a kitchen allows, and
they are CHEAPER than the compliant alternative — so a spend cap, a merchant
allowlist, a category check and a price-minimising buyer all wave them through.
Only a tag-level rule on the envelope stops them, and only if that rule is bound
into the envelope hash the customer approved.
"""
from __future__ import annotations

import time

import pytest

from app import catalog
from app.envelope import (
    DEFAULT_BLOCKED_TAGS,
    build_quote,
    compute_envelope_hash,
    compute_quote_hash,
    draft_envelope,
    verify_quote,
)
from app.models import (
    AutopilotScenario,
    Cart,
    CartLine,
    EnvelopeDraftRequest,
    EnvelopeSlot,
    EnvelopeStatus,
    MerchantQuote,
    PurchaseEnvelope,
)

FORBIDDEN_SKU = "SKU-DAI-004"   # Free-Range Eggs (12) — category dairy, tag "eggs"
COMPLIANT_SKU = "SKU-STA-003"   # Toor Dal 1kg — category pantry, tag "protein"


def _by_sku(sku: str) -> dict:
    return catalog.by_sku()[sku]


def _envelope(
    blocked_tags: list[str],
    *,
    max_total_paise: int = 100_000,
    now: float | None = None,
) -> PurchaseEnvelope:
    # delivery_deadline and expires_at are inside envelope_payload, so any test
    # comparing two hashes must pin the clock or it compares timestamps instead.
    now = time.time() if now is None else now
    env = PurchaseEnvelope(
        id="env_tag_test",
        user_id="user_kitchen",
        agent_id="agent_kitchen",
        label="Kitchen restock",
        goal="Protein for tomorrow's menu",
        merchant_id="merchant_freshbasket",
        max_total_paise=max_total_paise,
        fulfillment_profile_id="dest_demo",
        delivery_deadline=now + 3600,
        expires_at=now + 3600,
        slots=[EnvelopeSlot(id="protein", label="Protein", required_tags=["protein"])],
        blocked_categories=["gift_cards"],
        blocked_tags=blocked_tags,
        status=EnvelopeStatus.ACTIVE,
        version=1,
        envelope_hash="",
        created_at=now,
        updated_at=now,
    )
    return env.model_copy(update={"envelope_hash": compute_envelope_hash(env)})


def _quote_for(envelope: PurchaseEnvelope, sku: str) -> MerchantQuote:
    product = _by_sku(sku)
    quote = MerchantQuote(
        merchant_id=envelope.merchant_id,
        currency="INR",
        fulfillment_profile_id=envelope.fulfillment_profile_id,
        delivery_eta=envelope.delivery_deadline - 60,
        cart=Cart(
            lines=[
                CartLine(
                    sku=product["sku"],
                    name=product["name"],
                    category=product["category"],
                    unit_price_paise=product["price_paise"],
                    qty=1,
                )
            ]
        ),
        substitutions=[],
        quote_hash="",
    )
    return quote.model_copy(update={"quote_hash": compute_quote_hash(quote)})


def test_the_forbidden_item_is_cheaper_and_in_an_allowed_category():
    """The premise. If this ever stops holding, the demo stops proving anything."""
    forbidden = _by_sku(FORBIDDEN_SKU)
    compliant = _by_sku(COMPLIANT_SKU)

    assert "eggs" in forbidden["tags"]
    assert "protein" in forbidden["tags"] and "protein" in compliant["tags"]
    assert forbidden["category"] == "dairy"
    assert forbidden["category"] not in ("gift_cards", "electronics")
    assert forbidden["price_paise"] < compliant["price_paise"], (
        "The forbidden basket must be the cheaper one — that is the entire point. "
        "A buyer minimising spend picks it, and every monetary guard says yes."
    )


def test_every_other_guard_passes_on_the_forbidden_item():
    """Without the tag rule, nothing else in the envelope catches it."""
    envelope = _envelope(blocked_tags=[])
    decision = verify_quote(envelope, _quote_for(envelope, FORBIDDEN_SKU))

    assert decision.allowed, (
        "With no tag rule the eggs basket is fully authorised: under cap, right "
        f"merchant, allowed category, slot satisfied. Deltas: {decision.deltas}"
    )


def test_tag_rule_blocks_the_forbidden_item():
    envelope = _envelope(blocked_tags=["eggs"])
    decision = verify_quote(envelope, _quote_for(envelope, FORBIDDEN_SKU))

    assert not decision.allowed
    assert decision.code == "BLOCK_ENVELOPE_MISMATCH"
    tag_deltas = [d for d in decision.deltas if d.field.endswith(".tags")]
    assert len(tag_deltas) == 1
    assert FORBIDDEN_SKU in tag_deltas[0].actual
    assert "eggs" in tag_deltas[0].actual
    assert tag_deltas[0].recovery == "repair"


def test_tag_rule_allows_the_compliant_item():
    envelope = _envelope(blocked_tags=["eggs"])
    decision = verify_quote(envelope, _quote_for(envelope, COMPLIANT_SKU))

    assert decision.allowed, f"Compliant basket must pass. Deltas: {decision.deltas}"


def test_tags_are_read_from_the_server_catalog_not_the_proposed_line():
    """A buyer cannot clear the rule by describing the item differently."""
    envelope = _envelope(blocked_tags=["eggs"])
    product = _by_sku(FORBIDDEN_SKU)
    lying = MerchantQuote(
        merchant_id=envelope.merchant_id,
        currency="INR",
        fulfillment_profile_id=envelope.fulfillment_profile_id,
        delivery_eta=envelope.delivery_deadline - 60,
        cart=Cart(
            lines=[
                CartLine(
                    sku=product["sku"],
                    name=product["name"],
                    category=product["category"],
                    unit_price_paise=product["price_paise"],
                    qty=1,
                )
            ]
        ),
        substitutions=[],
        quote_hash="",
    )
    lying = lying.model_copy(update={"quote_hash": compute_quote_hash(lying)})
    decision = verify_quote(envelope, lying)

    assert not decision.allowed
    assert any(d.field.endswith(".tags") for d in decision.deltas)


def test_blocked_tags_are_bound_to_the_envelope_hash():
    """Widening the rule after approval must invalidate the approved hash."""
    strict = _envelope(blocked_tags=["eggs"])
    widened = strict.model_copy(update={"blocked_tags": []})

    assert compute_envelope_hash(widened) != strict.envelope_hash, (
        "blocked_tags must be inside envelope_payload, or the rule the customer "
        "approved is not the rule enforced at dispatch."
    )
    assert compute_envelope_hash(strict) == strict.envelope_hash


def test_blocked_tags_order_does_not_change_the_hash():
    pinned = 1_757_000_000.0
    a = _envelope(blocked_tags=["eggs", "meat"], now=pinned)
    b = _envelope(blocked_tags=["meat", "eggs"], now=pinned)
    assert a.envelope_hash == b.envelope_hash


def test_deterministic_repair_never_offers_a_forbidden_item():
    """The builder must respect the rule too, or every repair blocks itself."""
    envelope = _envelope(blocked_tags=["eggs"])
    quote, _ = build_quote(envelope, AutopilotScenario.NORMAL)

    assert quote.cart.lines, "Builder must still find a compliant protein"
    for line in quote.cart.lines:
        assert "eggs" not in _by_sku(line.sku)["tags"]
    assert verify_quote(envelope, quote).allowed


def test_forbidden_tag_scenario_reproduces_the_agent_mistake():
    """FORBIDDEN_TAG models the buyer, so the built quote must be the blocked one."""
    envelope = _envelope(blocked_tags=["eggs"])
    quote, _ = build_quote(envelope, AutopilotScenario.FORBIDDEN_TAG)

    assert any(FORBIDDEN_SKU == line.sku for line in quote.cart.lines)
    decision = verify_quote(envelope, quote)
    assert not decision.allowed
    assert any(d.field.endswith(".tags") for d in decision.deltas)

    compliant_quote, _ = build_quote(envelope, AutopilotScenario.NORMAL)
    assert quote.cart.total_paise < compliant_quote.cart.total_paise, (
        "The mistake must cost LESS than the correct basket, or a judge will "
        "assume a spend cap would have caught it."
    )


def test_drafted_envelopes_carry_the_kitchen_rules():
    draft = draft_envelope(EnvelopeDraftRequest(goal="Buy protein for the kitchen", max_total_rupees=600))
    assert set(DEFAULT_BLOCKED_TAGS).issubset(set(draft.blocked_tags))
    assert draft.envelope_hash == compute_envelope_hash(draft)


def test_envelope_without_tag_rules_still_hashes_and_verifies():
    """Backward compatibility: an empty rule list must not change behaviour."""
    envelope = _envelope(blocked_tags=[])
    quote, _ = build_quote(envelope, AutopilotScenario.NORMAL)
    assert verify_quote(envelope, quote).allowed
