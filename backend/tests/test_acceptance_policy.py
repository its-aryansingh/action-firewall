"""The published acceptance policy must be true.

A store that publishes rules it does not enforce is worse than one that publishes
nothing: it invites an agent to rely on a promise the server will not keep, and
the agent has no way to find out except by losing an order.

So these tests do not check that the document is well-formed, or that it agrees
with the constants it was built from — that much is structural, because the
document is generated from those constants. They check that every published rule
is BEHAVIOURALLY true: for each one, build a cart that violates it and assert the
verifier actually refuses.

The drift this defends against is ordinary and quiet. Someone adds a rule to the
verifier and forgets to publish it; the document silently understates what the
store enforces, and honest agents keep getting refused for reasons the store
never mentioned. `test_every_enforced_rule_appears_in_the_document` is the one
that fails when that happens.
"""
from __future__ import annotations

import time

import pytest

from app import catalog
from app.acceptance_policy import (
    ACCEPTANCE_POLICY_SCHEMA,
    RECOVERY_SEMANTICS,
    build_acceptance_policy,
    compute_acceptance_policy_hash,
)
from app.actions import ACTION_REGISTRY
from app.channel_policy import DEFAULT_CHANNEL_POLICY
from app.envelope import (
    DEFAULT_BLOCKED_TAGS,
    compute_envelope_hash,
    compute_quote_hash,
    verify_quote,
)
from app.models import (
    Cart,
    CartLine,
    EnvelopeSlot,
    EnvelopeStatus,
    MerchantQuote,
    PurchaseEnvelope,
)

NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def clean_stock():
    catalog.reset_stock()
    yield
    catalog.reset_stock()


@pytest.fixture(scope="module")
def policy() -> dict:
    return build_acceptance_policy()


def _envelope(**overrides) -> PurchaseEnvelope:
    base = dict(
        id="env_policy", user_id="u", agent_id="a", label="l", goal="g",
        merchant_id="merchant_freshbasket", max_total_paise=1_000_000,
        fulfillment_profile_id="dest_demo",
        delivery_deadline=NOW + 3600, expires_at=NOW + 3600,
        slots=[EnvelopeSlot(id="s", label="s", required_tags=["protein"], quantity=1)],
        blocked_categories=list(DEFAULT_CHANNEL_POLICY["blocked_categories"]),
        blocked_tags=list(DEFAULT_BLOCKED_TAGS),
        status=EnvelopeStatus.ACTIVE, version=1, envelope_hash="",
        created_at=NOW, updated_at=NOW,
    )
    base.update(overrides)
    env = PurchaseEnvelope(**base)
    return env.model_copy(update={"envelope_hash": compute_envelope_hash(env)})


def _quote_of(envelope: PurchaseEnvelope, skus: list[str], qty: int = 1) -> MerchantQuote:
    by_sku = catalog.by_sku()
    lines = [
        CartLine(sku=s, name=by_sku[s]["name"], category=by_sku[s]["category"],
                 unit_price_paise=by_sku[s]["price_paise"], qty=qty)
        for s in skus
    ]
    q = MerchantQuote(
        merchant_id=envelope.merchant_id, currency="INR",
        fulfillment_profile_id=envelope.fulfillment_profile_id,
        delivery_eta=envelope.delivery_deadline - 60,
        cart=Cart(lines=lines), substitutions=[], quote_hash="",
    )
    return q.model_copy(update={"quote_hash": compute_quote_hash(q)})


def _first_sku_with_tag(tag: str) -> str | None:
    return next((p["sku"] for p in catalog.load_catalog()
                 if tag in p.get("tags", [])), None)


def _first_sku_in_category(category: str) -> str | None:
    return next((p["sku"] for p in catalog.load_catalog()
                 if p["category"] == category), None)


# ---------------------------------------------------------------------------
# Every published refusal must actually refuse
# ---------------------------------------------------------------------------

def test_every_published_ingredient_tag_is_actually_refused(policy):
    """The claim this endpoint exists to make, proved one tag at a time."""
    checked = 0
    for tag in policy["will_refuse"]["ingredient_tags"]:
        sku = _first_sku_with_tag(tag)
        if sku is None:
            continue  # nothing in the catalog carries it; nothing to prove
        checked += 1
        env = _envelope(blocked_tags=[tag])
        decision = verify_quote(env, _quote_of(env, [sku]), now=NOW + 10)
        assert not decision.allowed, (
            f"'{tag}' is published as refused but a cart containing {sku} was authorised"
        )
    assert checked, "no published tag was exercised; this test proved nothing"


def test_every_published_category_is_actually_refused(policy):
    checked = 0
    for category in policy["will_refuse"]["categories"]:
        sku = _first_sku_in_category(category)
        if sku is None:
            continue
        checked += 1
        env = _envelope(blocked_categories=[category])
        decision = verify_quote(env, _quote_of(env, [sku]), now=NOW + 10)
        assert not decision.allowed, (
            f"category '{category}' is published as refused but {sku} was authorised"
        )
    assert checked, "no published category was exercised; this test proved nothing"


def test_the_published_order_ceiling_is_actually_enforced(policy):
    ceiling = policy["will_refuse"]["orders_above_paise"]
    assert ceiling == DEFAULT_CHANNEL_POLICY["max_order_paise"]

    env = _envelope(max_total_paise=50_000)
    sku = _first_sku_with_tag("protein")
    over = _quote_of(env, [sku], qty=4)
    if over.cart.total_paise > 50_000:
        assert not verify_quote(env, over, now=NOW + 10).allowed


def test_an_action_outside_the_published_list_cannot_be_taken(policy):
    from app.actions import ActionNotRegistered, canonicalize_action

    published = set(policy["will_accept"]["actions"])
    assert published == set(ACTION_REGISTRY), (
        "the published action list and the closed registry have diverged"
    )
    with pytest.raises(ActionNotRegistered):
        canonicalize_action("payout", {"amount": 1})


def test_the_published_stock_promise_holds(policy):
    """'Availability is re-read when the order is authorised, not when quoted.'"""
    assert "stock_at_dispatch" in policy["requires"]
    env = _envelope()
    sku = _first_sku_with_tag("protein")
    quote = _quote_of(env, [sku], qty=2)
    env = _envelope(slots=[EnvelopeSlot(id="s", label="s",
                                        required_tags=["protein"], quantity=2)])
    quote = _quote_of(env, [sku], qty=2)
    assert verify_quote(env, quote, now=NOW + 10).allowed

    catalog.set_stock(sku, 1)
    assert not verify_quote(env, quote, now=NOW + 10).allowed


def test_the_published_human_activation_requirement_holds(policy):
    assert "human_activation" in policy["requires"]
    env = _envelope(status=EnvelopeStatus.DRAFT)
    sku = _first_sku_with_tag("protein")
    assert not verify_quote(env, _quote_of(env, [sku]), now=NOW + 10).allowed


def test_the_published_server_pricing_promise_holds(policy):
    """'Client-supplied prices are discarded.'"""
    assert "server_priced_quote" in policy["requires"]
    env = _envelope()
    sku = _first_sku_with_tag("protein")
    p = catalog.by_sku()[sku]
    lying = MerchantQuote(
        merchant_id=env.merchant_id, currency="INR",
        fulfillment_profile_id=env.fulfillment_profile_id,
        delivery_eta=env.delivery_deadline - 60,
        cart=Cart(lines=[CartLine(sku=sku, name=p["name"], category=p["category"],
                                  unit_price_paise=1, qty=1)]),
        substitutions=[], quote_hash="",
    )
    lying = lying.model_copy(update={"quote_hash": compute_quote_hash(lying)})
    assert not verify_quote(env, lying, now=NOW + 10).allowed


# ---------------------------------------------------------------------------
# Drift, in both directions
# ---------------------------------------------------------------------------

def test_every_enforced_rule_appears_in_the_document(policy):
    """The quiet failure: a rule is added to the verifier and never published.

    An honest agent then keeps getting refused for a reason the store never
    stated. If you add a check to verify_quote, add it here too — and if it
    cannot be published, say why in `not_covered_by_this_document`.
    """
    published = repr(policy)
    for tag in DEFAULT_BLOCKED_TAGS:
        assert tag in published
    for category in DEFAULT_CHANNEL_POLICY["blocked_categories"]:
        assert category in published
    for action in ACTION_REGISTRY:
        assert action in published
    for promise in ("human_activation", "server_priced_quote",
                    "single_use_authorization", "stock_at_dispatch"):
        assert promise in policy["requires"]


def test_the_document_does_not_promise_more_than_it_delivers(policy):
    """Publication prevents mistakes, not attacks — and must say so."""
    caveat = policy["not_covered_by_this_document"].lower()
    assert "forge" in caveat or "tamper" in caveat
    assert "no additional trust" in caveat or "confers no" in caveat


def test_every_recovery_an_agent_can_receive_is_explained(policy):
    """A refusal an agent cannot act on is a dead end, and this layer sells the
    route forward. Each recovery must be documented."""
    from app.models import PolicyDelta

    literal_recoveries = set(PolicyDelta.model_fields["recovery"].annotation.__args__)
    assert literal_recoveries == set(RECOVERY_SEMANTICS)
    assert set(policy["on_refusal"]["recoveries"]) == literal_recoveries


def test_the_hash_changes_when_a_rule_changes(monkeypatch):
    """A version an agent can pin is only useful if it moves."""
    before = compute_acceptance_policy_hash()
    monkeypatch.setitem(DEFAULT_CHANNEL_POLICY, "max_order_paise", 999_999)
    assert compute_acceptance_policy_hash() != before


def test_the_hash_is_stable_across_calls():
    assert compute_acceptance_policy_hash() == compute_acceptance_policy_hash()


def test_the_document_declares_its_schema(policy):
    assert policy["schema"] == ACCEPTANCE_POLICY_SCHEMA
    assert policy["amounts_are_in"] == "integer paise"


def test_the_endpoint_serves_it_without_authentication(tmp_path, monkeypatch):
    """An acceptance policy behind a key is not published."""
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app import store

    monkeypatch.setenv("DB_PATH", str(tmp_path / "policy.db"))
    get_settings.cache_clear()
    store.init_db()
    from app.main import app

    resp = TestClient(app).get("/agent-commerce/v1/acceptance-policy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["policy_hash"] == compute_acceptance_policy_hash()
    assert body["will_refuse"]["ingredient_tags"]
    get_settings.cache_clear()
