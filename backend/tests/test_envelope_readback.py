"""A shopper who approves a sentence and receives a rule they never read has
not approved the rule.

The competing design for this problem (IntentGuard) asks a language model, at
purchase time, whether an item is "a reasonable and necessary instance" of the
shopper's sentence. That puts a model on the authorisation path, makes the
decision unrepeatable, and feeds it text the merchant controls.

The alternative here: compile the sentence into an explicit rule once, show the
human what that rule ADMITS — including the most expensive basket it would let
through — and let them tighten it before activating. After activation nothing
needs to judge intent, because the intent is already written down as something a
deterministic checker can evaluate.

`test_a_cheese_slot_admits_parmigiano_and_says_so` is the case their design
exists to catch. It is caught here before any money is authorised, by arithmetic.
"""
import os
import tempfile

import pytest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "readback.db")
os.environ["DEMO_MODE"] = "true"
os.environ["ENVELOPE_DRAFTING_MODE"] = "deterministic"
os.environ["OPENAI_API_KEY"] = ""

from app import catalog, store  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.envelope import (  # noqa: E402
    draft_envelope,
    envelope_readback,
    render_envelope_english,
    slot_admission,
)
from app.models import EnvelopeDraftRequest, EnvelopeSlot  # noqa: E402


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "readback.db"))
    monkeypatch.setenv("ENVELOPE_DRAFTING_MODE", "deterministic")
    get_settings.cache_clear()
    store.init_db()
    catalog.reset_stock()
    yield
    catalog.reset_stock()
    get_settings.cache_clear()


def envelope(**overrides):
    env = draft_envelope(
        EnvelopeDraftRequest(goal="Weeknight pasta dinner for four", max_total_rupees=7840)
    )
    return env.model_copy(update=overrides) if overrides else env


# ---------------------------------------------------------------------------
# The sentence must be a pure function of the rule
# ---------------------------------------------------------------------------
def test_the_english_is_deterministic():
    env = envelope()
    first = render_envelope_english(env)
    assert all(render_envelope_english(env) == first for _ in range(50))


def test_the_english_does_not_move_when_the_catalog_does():
    """The sentence the human approved must not silently change because a shelf
    was restocked. Stock belongs in the readback's worst case, never in the
    rule's own description."""
    env = envelope()
    before = render_envelope_english(env)
    for product in catalog.load_catalog():
        catalog.set_stock(product["sku"], 0)
    assert render_envelope_english(env) == before


def test_the_english_names_every_part_of_the_rule():
    """Anything the engine enforces but the sentence omits is authority the
    human granted without reading."""
    env = envelope(
        blocked_categories=["electronics", "gift_cards"],
        blocked_tags=["eggs", "premium"],
    )
    text = render_envelope_english(env)

    assert "Rs 7,840" in text, "the cap must appear in rupees, grouped Indian-style"
    assert env.merchant_id in text
    for slot in env.slots:
        for tag in slot.required_tags:
            assert tag in text, f"slot tag {tag!r} missing from the readback"
    for blocked in ("electronics", "gift_cards", "eggs", "premium"):
        assert blocked in text
    assert "Nothing else may be added." in text, (
        "this sentence IS the semantic-drift defence; it must be stated, not implied"
    )


def test_quantities_above_one_are_spelled_out():
    env = envelope(slots=[EnvelopeSlot(id="milk", label="Milk", required_tags=["milk"], quantity=3)])
    assert "3 items tagged milk" in render_envelope_english(env)


def test_rupee_grouping_is_indian():
    from app.envelope import _rupees

    assert _rupees(784000) == "Rs 7,840"
    assert _rupees(10000000) == "Rs 1,00,000"
    assert _rupees(100) == "Rs 1"
    assert _rupees(12345) == "Rs 123.45"


# ---------------------------------------------------------------------------
# The worst case is the number that changes a shopper's mind
# ---------------------------------------------------------------------------
def test_a_cheese_slot_admits_parmigiano_and_says_so():
    """IntentGuard's headline scenario, caught by arithmetic before approval.

    "One item tagged cheese" reads as a formality. It admits Parmigiano Reggiano
    at Rs 899 — the exact purchase their design sends to a language model to
    adjudicate after the fact. Here the shopper is told, in rupees, before
    anything is authorised, and can strike the slot or lower the cap."""
    env = envelope(slots=[EnvelopeSlot(id="cheese", label="Cheese", required_tags=["cheese"])])
    readback = envelope_readback(env)

    admission = readback.slots[0]
    assert admission.admissible_count >= 2, "a slot admitting one item proves nothing here"
    assert admission.dearest_name == "Parmigiano Reggiano 200g"
    assert admission.dearest_paise == 89900
    assert admission.cheapest_paise is not None
    assert admission.dearest_paise > admission.cheapest_paise * 2, (
        "the spread is the point: the shopper cannot see it from the tag alone"
    )


def test_the_worst_case_is_the_sum_of_each_slot_s_dearest_admissible_item():
    env = envelope()
    readback = envelope_readback(env)
    assert readback.worst_case_total_paise == sum(s.dearest_paise or 0 for s in readback.slots)
    assert readback.worst_case_total_paise >= sum(s.cheapest_paise or 0 for s in readback.slots)


def test_quantity_multiplies_the_worst_case():
    one = envelope(slots=[EnvelopeSlot(id="c", label="C", required_tags=["cheese"])])
    three = envelope(
        slots=[EnvelopeSlot(id="c", label="C", required_tags=["cheese"], quantity=3)]
    )
    assert envelope_readback(three).worst_case_total_paise == (
        envelope_readback(one).worst_case_total_paise * 3
    )


def test_a_cap_that_does_no_work_is_reported_as_doing_no_work():
    """A shopper who believes a Rs 7,840 cap is protecting them has misread which
    control is load-bearing. On the demo envelope the dearest admissible basket
    is a small fraction of the cap: the RULE is the protection, not the number."""
    readback = envelope_readback(envelope())
    assert readback.cap_binds is False
    assert readback.worst_case_total_paise < readback.max_total_paise


def test_a_cap_below_the_worst_case_is_reported_as_binding():
    env = envelope(
        slots=[EnvelopeSlot(id="cheese", label="Cheese", required_tags=["cheese"])],
        max_total_paise=50000,  # Rs 500, below Parmigiano at Rs 899
    )
    readback = envelope_readback(env)
    assert readback.cap_binds is True


def test_a_worst_case_exactly_equal_to_the_cap_does_not_bind():
    """Off-by-one on a spend limit is a refusal the shopper cannot explain."""
    env = envelope(slots=[EnvelopeSlot(id="cheese", label="Cheese", required_tags=["cheese"])])
    at_cap = env.model_copy(update={"max_total_paise": envelope_readback(env).worst_case_total_paise})
    assert envelope_readback(at_cap).cap_binds is False


# ---------------------------------------------------------------------------
# It has to track the catalog, or it is decoration
# ---------------------------------------------------------------------------
def test_the_worst_case_follows_stock():
    """Selling out the dearest item lowers the worst case. If it did not, the
    readback would be a static description wearing the costume of a measurement."""
    env = envelope(slots=[EnvelopeSlot(id="cheese", label="Cheese", required_tags=["cheese"])])
    before = envelope_readback(env)
    catalog.set_stock(before.slots[0].dearest_sku, 0)
    after = envelope_readback(env)

    assert after.worst_case_total_paise < before.worst_case_total_paise
    assert after.slots[0].dearest_sku != before.slots[0].dearest_sku
    assert after.slots[0].admissible_count == before.slots[0].admissible_count - 1


def test_a_blocked_tag_removes_items_from_the_admissible_set():
    env = envelope(slots=[EnvelopeSlot(id="cheese", label="Cheese", required_tags=["cheese"])])
    before = envelope_readback(env)
    tightened = env.model_copy(update={"blocked_tags": [*env.blocked_tags, "premium"]})
    after = envelope_readback(tightened)

    assert after.slots[0].admissible_count < before.slots[0].admissible_count
    assert after.worst_case_total_paise < before.worst_case_total_paise


def test_a_slot_nothing_can_satisfy_is_named_before_activation():
    """An envelope carrying an unsatisfiable slot can never be fulfilled. The
    shopper should learn that while deciding, not at dispatch."""
    env = envelope(
        slots=[EnvelopeSlot(id="impossible", label="Impossible", required_tags=["no_such_tag"])]
    )
    readback = envelope_readback(env)
    assert readback.unsatisfiable_slot_ids == ["impossible"]
    assert readback.slots[0].admissible_count == 0
    assert readback.slots[0].dearest_paise is None
    assert readback.worst_case_total_paise == 0


def test_the_readback_is_stamped_with_the_catalog_it_was_computed_against():
    """Stock and prices move, so the worst case is a snapshot. Saying which
    catalog produced it is the difference between a snapshot and a promise."""
    from app.merchant import CATALOG_REVISION

    assert envelope_readback(envelope()).catalog_revision == CATALOG_REVISION


# ---------------------------------------------------------------------------
# It must agree with the thing that actually enforces
# ---------------------------------------------------------------------------
def test_every_admitted_item_really_satisfies_the_slot():
    """The readback and the verifier must not disagree about what a slot means.
    If they did, the shopper would be approving one rule while another was
    enforced — which is the exact failure this surface exists to prevent."""
    env = envelope()
    for slot in env.slots:
        admission = slot_admission(env, slot)
        if admission.admissible_count == 0:
            continue
        dearest = catalog.by_sku()[admission.dearest_sku]
        tags = set(dearest.get("tags", []))
        assert set(slot.required_tags).issubset(tags)
        assert not tags & set(env.blocked_tags)
        assert dearest["category"] not in env.blocked_categories
        assert catalog.available_stock(dearest["sku"]) >= slot.quantity
