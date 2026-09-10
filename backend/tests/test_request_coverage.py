"""Every item a shopper lists must be accounted for.

The bug this file exists to prevent: a shopper typed "egg,meat,nuts" and got a
one-line cart containing eggs, with no mention of the other two. Two separate
causes, both silent.

1. The deterministic matcher looked at product NAMES only, by strict substring.
   The catalog row is "Free-Range Eggs (12)", so "egg" did not match it. "nuts"
   is a TAG on Roasted Almonds and appears nowhere in its name, so no
   name-based rule could ever have found it.
2. "meat" matched nothing because the merchant genuinely stocked none, and
   nothing in the flow said so. Silence is the worst answer: the shopper cannot
   tell an out-of-stock item from a forgotten one.

The assertions below are about COVERAGE, not about a specific cart. A dropped
item is a correctness failure even when everything that did land is correct.
"""
import os
import tempfile
import uuid

import pytest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "coverage.db")
os.environ["DEMO_MODE"] = "true"
os.environ["OPENAI_API_KEY"] = ""  # deterministic planner only; no model in the loop

from app import catalog, store  # noqa: E402
from app.agent import (  # noqa: E402
    _cart_covers,
    _requested_terms,
    _resolve_term,
    handle_turn,
    reset_session,
)
from app.channel_policy import DEFAULT_CHANNEL_POLICY  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import Cart, CartLine, ChatRequest, MandateCreate  # noqa: E402


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "coverage.db"))
    get_settings.cache_clear()
    store.init_db()
    yield
    get_settings.cache_clear()


def chat(message: str):
    session_id = uuid.uuid4().hex
    store.create_mandate(MandateCreate(cap_rupees=100_000))
    response = handle_turn(ChatRequest(session_id=session_id, message=message))
    reset_session(session_id)
    return response


def categories_in(response) -> set[str]:
    return {line.category for line in response.cart.lines}


# ---------------------------------------------------------------------------
# The reported failure
# ---------------------------------------------------------------------------
def test_three_listed_items_produce_three_covered_items():
    response = chat("egg,meat,nuts")
    names = " ".join(line.name.lower() for line in response.cart.lines)

    assert "egg" in names, "the shopper asked for egg and did not get it"
    assert "meat" in categories_in(response), "the shopper asked for meat and did not get it"
    assert "almond" in names, "'nuts' is a tag on Roasted Almonds; it must resolve"
    assert len(response.cart.lines) == 3


def test_a_term_the_merchant_cannot_serve_is_named_out_loud():
    response = chat("eggs, caviar")
    assert "caviar" in response.reply.lower()
    assert "do not stock" in response.reply.lower()


def test_reply_never_contradicts_itself_when_planner_proposed_nothing():
    """The deterministic planner's empty-handed reply is "tell me what you would
    like to cook or buy". Appending "Also added X" to that is a sentence that
    argues with itself, and on a demo screen that reads as a broken product."""
    response = chat("egg,meat,nuts")
    assert response.cart.lines
    assert "tell me what you would like" not in response.reply.lower()


def test_cross_sell_offer_is_dropped_once_the_item_is_in_the_cart():
    response = chat("milk and bread")
    names = {line.name for line in response.cart.lines}
    if "People usually add" in response.reply:
        offered = response.reply.split("People usually add", 1)[1].split(" (", 1)[0].strip()
        assert offered not in names, (
            f"reply offers {offered!r} as a suggestion while it is already in the cart"
        )


# ---------------------------------------------------------------------------
# The rule that decides what a word means
# ---------------------------------------------------------------------------
def test_a_tag_on_exactly_one_product_resolves():
    sku, alternatives = _resolve_term("nuts")
    assert catalog.by_sku()[sku]["name"] == "Roasted Almonds 500g"
    assert alternatives == ()


def test_plural_and_singular_reach_the_same_product():
    assert _resolve_term("egg")[0] == _resolve_term("eggs")[0]


def test_a_tag_spanning_several_categories_never_becomes_a_cart_line():
    """`dinner` is on 10 products across dairy, pantry and produce; `pasta` on 7
    across three. Those tags describe an occasion or a cuisine, not a kind of
    thing, and the giveaway is that they span categories. Resolving them would
    turn topical relevance into purchase intent, which is the one thing this
    surface must never do."""
    for occasion in ("dinner", "pasta", "premium", "staple", "italian", "breakfast"):
        assert _resolve_term(occasion) == (None, ()), f"{occasion!r} must not resolve"


def test_a_tag_confined_to_one_category_resolves_with_alternatives_named():
    sku, alternatives = _resolve_term("milk")
    assert catalog.by_sku()[sku]["category"] == "dairy"
    assert alternatives, "a kind-term with several options must offer the rest"


def test_the_representative_pick_is_stable():
    """Lowest price, then SKU. A demo that picks a different item on the second
    run is not a demo."""
    assert _resolve_term("meat")[0] == _resolve_term("meat")[0]
    sku, alternatives = _resolve_term("meat")
    by = catalog.by_sku()
    assert all(by[sku]["price_paise"] <= by[alt]["price_paise"] for alt in alternatives)


def test_a_term_the_catalog_has_no_answer_for_resolves_to_nothing():
    assert _resolve_term("caviar") == (None, ())
    assert _resolve_term("paneer") == (None, ())


# ---------------------------------------------------------------------------
# Scope: the coverage pass must not fire on prose or on subtraction
# ---------------------------------------------------------------------------
def test_prose_is_not_treated_as_a_shopping_list():
    """Splitting prose into words would let the coverage pass announce that the
    shop does not stock `tell` or `something`."""
    assert _requested_terms("Tell me something interesting about dinner") == []
    assert _requested_terms("I need supplies for a pasta dinner") == []


def test_a_delimited_list_is_treated_as_a_shopping_list():
    assert _requested_terms("egg,meat,nuts") == ["egg", "meat", "nuts"]
    assert len(_requested_terms("milk and bread and caviar")) == 3


def test_ambiguous_prose_still_creates_no_purchase_intent():
    response = chat("Tell me something interesting about dinner")
    assert response.cart.lines == []
    assert response.confirmation_required is False
    assert store.metrics()["authorization_attempts"] == 0


def test_subtraction_suppresses_coverage_repair():
    """"eggs, but no nuts" lists nuts. Adding them would be the exact opposite
    of what was asked."""
    response = chat("eggs, but no nuts")
    assert not any("Almond" in line.name for line in response.cart.lines)


def test_an_item_already_in_the_cart_is_not_reported_as_unstocked():
    """The name pass adds Multigrain Bread; the coverage pass must recognise
    that `bread` is answered rather than announcing the shop has no bread."""
    response = chat("milk and bread")
    assert "do not stock" not in response.reply.lower()


def test_cart_coverage_reads_names_tags_and_category():
    line = CartLine(
        sku="SKU-DAI-004",
        name="Free-Range Eggs (12)",
        category="dairy",
        unit_price_paise=13900,
        qty=1,
    )
    cart = Cart(lines=[line])
    assert _cart_covers("egg", cart)          # name word, singularised
    assert _cart_covers("breakfast", cart)    # tag
    assert _cart_covers("dairy", cart)        # category
    assert not _cart_covers("caviar", cart)


# ---------------------------------------------------------------------------
# The catalog change that made "meat" answerable
# ---------------------------------------------------------------------------
def test_meat_is_stocked_and_permitted_on_the_ai_channel():
    """Shipping a product the firewall then refuses is worse than not stocking
    it: the shopper sees an item accepted into the cart and rejected at the
    boundary, for no reason they can act on."""
    meat = [p for p in catalog.load_catalog() if p["category"] == "meat"]
    assert meat, "catalog must stock meat for 'meat' to be answerable"
    assert "meat" in DEFAULT_CHANNEL_POLICY["allowed_categories"]
    assert all(product["stock"] > 0 for product in meat)


def test_meat_tags_did_not_disturb_an_existing_singleton_tag():
    """`eggs` and `nuts` each identify exactly one product, and the resolution
    rule depends on that. A convenience tag on the new rows — `protein`, say —
    would have quietly changed what an existing word means."""
    for tag in ("eggs", "nuts"):
        owners = [p for p in catalog.load_catalog() if tag in p.get("tags", [])]
        assert len(owners) == 1, f"tag {tag!r} is no longer unique: {owners}"


# ---------------------------------------------------------------------------
# The header badge must not misreport which payment rail is live
# ---------------------------------------------------------------------------
def test_evidence_mode_reports_the_provider_not_the_demo_flag(monkeypatch):
    """DEMO_MODE and PAYMENT_PROVIDER are unrelated settings, and running
    DEMO_MODE=true with PAYMENT_PROVIDER=razorpay_rest is ordinary. The metrics
    layer used to derive evidence_mode from demo_mode, so in that configuration
    the header badge read "Simulated Razorpay MCP" while the backend was
    creating real Razorpay payment links. A surface that misreports its own rail
    is worse than one that stays silent, because a viewer believes it."""
    from app import commerce_metrics, mcp_client

    for provider in ("simulated", "razorpay_mcp", "razorpay_rest"):
        monkeypatch.setattr(mcp_client, "get_active_provider_mode", lambda p=provider: p)
        metrics = commerce_metrics.get_comprehensive_metrics()
        assert metrics.evidence_mode == provider, (
            f"evidence_mode reported {metrics.evidence_mode!r} while {provider!r} was dispatching"
        )
