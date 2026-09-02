"""The tests that matter: the money gate. Run with `pytest -q` from backend/."""
import time
import pytest

from app.mandate import verify, suggest_downgrade
from app.models import Cart, CartLine, DecisionCode, Mandate, Window


def mandate(cap=100_000, window=Window.WEEKLY, **kw) -> Mandate:
    now = time.time()
    base = dict(id="mnd_test", user_id="u", agent_id="a", label="Test",
                cap_paise=cap, window=window, active=True, version=1,
                created_at=now, updated_at=now)
    base.update(kw)
    return Mandate(**base)


def cart(*items) -> Cart:
    return Cart(lines=[CartLine(sku=s, name=s, category=c, unit_price_paise=p, qty=q)
                       for s, c, p, q in items])


def test_under_cap_is_allowed():
    d = verify(cart(("A", "pantry", 30_000, 1)), mandate(cap=100_000))
    assert d.allowed and d.code is DecisionCode.ALLOW
    assert d.headroom_paise == 100_000


def test_exactly_at_cap_is_allowed():
    """Boundary: cap is inclusive. Off-by-one here is a production incident."""
    d = verify(cart(("A", "pantry", 100_000, 1)), mandate(cap=100_000))
    assert d.allowed


def test_one_paisa_over_cap_is_blocked():
    d = verify(cart(("A", "pantry", 100_001, 1)), mandate(cap=100_000))
    assert not d.allowed and d.code is DecisionCode.BLOCK_WINDOW_CAP_EXCEEDED


def test_the_demo_breach_1200_over_1000():
    d = verify(cart(("PASTA", "pantry", 20_000, 1), ("CHEESE", "dairy", 100_000, 1)),
               mandate(cap=100_000))
    assert not d.allowed
    assert "exceeds your authorization policy" in d.human_message
    assert "₹1,200" in d.human_message and "₹1,000" in d.human_message


def test_prior_spend_reduces_headroom():
    d = verify(cart(("A", "pantry", 40_000, 1)), mandate(cap=100_000),
               already_spent_paise=70_000)
    assert not d.allowed and d.headroom_paise == 30_000
    assert "already used" in d.human_message


def test_no_mandate_blocks():
    d = verify(cart(("A", "pantry", 100, 1)), None)
    assert not d.allowed and d.code is DecisionCode.BLOCK_NO_MANDATE


def test_revoked_mandate_blocks_even_when_cheap():
    d = verify(cart(("A", "pantry", 100, 1)), mandate(cap=100_000, active=False))
    assert not d.allowed and d.code is DecisionCode.BLOCK_MANDATE_REVOKED


def test_per_transaction_cap():
    d = verify(cart(("A", "pantry", 60_000, 1)),
               mandate(cap=1_000_000, per_txn_cap_paise=50_000))
    assert not d.allowed and d.code is DecisionCode.BLOCK_PER_TXN_CAP_EXCEEDED


def test_blocked_category_is_refused():
    d = verify(cart(("GIFT", "gift_cards", 10_000, 1)),
               mandate(cap=1_000_000, blocked_categories=["gift_cards"]))
    assert not d.allowed and d.code is DecisionCode.BLOCK_CATEGORY_NOT_ALLOWED
    assert d.offending_skus == ["GIFT"]


def test_allowlist_excludes_everything_else():
    d = verify(cart(("TV", "electronics", 10_000, 1)),
               mandate(cap=1_000_000, allowed_categories=["produce", "pantry"]))
    assert not d.allowed and d.code is DecisionCode.BLOCK_CATEGORY_NOT_ALLOWED


def test_quantity_is_multiplied_not_ignored():
    d = verify(cart(("A", "pantry", 30_000, 4)), mandate(cap=100_000))
    assert not d.allowed and d.cart_total_paise == 120_000


def test_empty_cart_is_allowed_and_free():
    d = verify(Cart(), mandate())
    assert d.allowed and d.cart_total_paise == 0


def test_downgrade_fits_under_headroom():
    c = cart(("CHEAP", "pantry", 20_000, 1), ("MID", "pantry", 30_000, 1),
             ("LUXE", "dairy", 100_000, 1))
    d = verify(c, mandate(cap=100_000))
    fixed = suggest_downgrade(c, d)
    assert fixed is not None
    assert fixed.total_paise <= 100_000
    assert "LUXE" not in {l.sku for l in fixed.lines}
    assert verify(fixed, mandate(cap=100_000)).allowed


@pytest.mark.parametrize("window", list(Window))
def test_every_window_type_evaluates(window):
    assert verify(cart(("A", "pantry", 1, 1)), mandate(window=window)).allowed
