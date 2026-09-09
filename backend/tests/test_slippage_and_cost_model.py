"""Demo controls and the cost model — the two ideas taken from rival repos.

Both are borrowed deliberately: slippage from apex-commerce, the cost model from
viveka. These tests cover the parts that make them safe to borrow, which is not
the same as the parts that make them useful.
"""
from __future__ import annotations

import pytest

from app import catalog, slippage
from app.config import get_settings
from app.cost_model import CostAssumptions, OutcomeMix, compare, cost_of, sensitivity

SKU = "SKU-STA-003"


@pytest.fixture(autouse=True)
def clean_stock():
    catalog.reset_stock()
    yield
    catalog.reset_stock()


# ---------------------------------------------------------------------------
# Slippage: it may move the world, never the policy
# ---------------------------------------------------------------------------

def test_deplete_takes_a_sku_off_the_shelf():
    assert catalog.available_stock(SKU) > 0
    result = slippage.deplete(SKU)
    assert result["stock_now"] == 0
    assert catalog.available_stock(SKU) == 0


def test_reset_restores_the_committed_catalog_not_a_snapshot():
    """Restoring from the committed file is what survives a restart."""
    committed = catalog.by_sku()[SKU]["stock"]
    slippage.deplete(SKU)
    slippage.reset_all()
    assert catalog.available_stock(SKU) == committed


def test_unknown_sku_is_refused():
    with pytest.raises(LookupError):
        slippage.deplete("SKU-DOES-NOT-EXIST")


def test_negative_stock_is_refused():
    with pytest.raises(ValueError):
        slippage.set_stock(SKU, -1)


def test_current_state_reports_only_what_moved():
    assert slippage.current_state() == []
    slippage.set_stock(SKU, 2)
    moved = slippage.current_state()
    assert len(moved) == 1
    assert moved[0]["sku"] == SKU and moved[0]["live_stock"] == 2


def test_demo_controls_fail_closed_without_fault_injection(monkeypatch):
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "false")
    get_settings.cache_clear()
    try:
        for call in (lambda: slippage.deplete(SKU),
                     lambda: slippage.set_stock(SKU, 1),
                     slippage.reset_all):
            with pytest.raises(slippage.SlippageNotPermitted):
                call()
    finally:
        get_settings.cache_clear()


def test_the_dangerous_configuration_cannot_even_be_constructed(monkeypatch):
    """Stronger than the runtime guard, and it is not mine.

    `Settings` refuses to build with fault injection enabled alongside a real
    payment provider (boot-time invariant 17), so the configuration in which a
    demo control could reach live money does not exist rather than being caught.
    The runtime check in slippage.py stays as defence in depth — a guard that is
    only correct because some other module is correct is a guard with a
    dependency nobody wrote down.
    """
    from pydantic import ValidationError

    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "razorpay_mcp")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError, match="fault_injection_enabled"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_slippage_exposes_no_way_to_touch_policy():
    """A demo control that could widen authority is a back door with a nice name."""
    surface = {n for n in dir(slippage) if not n.startswith("_")}
    forbidden = {"set_cap", "set_policy", "activate", "grant", "approve",
                 "set_envelope", "widen", "set_blocked_tags"}
    assert not (surface & forbidden), f"policy-mutating demo control: {surface & forbidden}"


# ---------------------------------------------------------------------------
# Cost model: the ordering must survive disagreement
# ---------------------------------------------------------------------------

def _mixes():
    return {
        "no_layer": OutcomeMix(
            authorised_correctly_paise=100_000, authorised_correctly_count=10,
            violations_authorised_paise=500_000, violations_authorised_count=20),
        "cap_only": OutcomeMix(
            authorised_correctly_paise=100_000, authorised_correctly_count=10,
            violations_authorised_paise=300_000, violations_authorised_count=12),
        "firewall": OutcomeMix(
            authorised_correctly_paise=100_000, authorised_correctly_count=10,
            repaired_paise=80_000, repaired_count=8),
    }


def test_letting_violations_through_costs_more_than_refusing_them():
    priced = compare(_mixes())
    assert priced["lowest_cost"] == "firewall"
    assert priced["highest_cost"] == "no_layer"


def test_repair_is_the_only_outcome_that_reduces_cost():
    without = OutcomeMix(legitimate_refused_paise=80_000, legitimate_refused_count=8)
    with_repair = OutcomeMix(repaired_paise=80_000, repaired_count=8)
    assert cost_of(with_repair)["total_paise"] < cost_of(without)["total_paise"]


def test_the_ordering_survives_every_single_assumption_sweep():
    """The claim is the ordering, not the rupee figure. This is what makes it publishable."""
    result = sensitivity(_mixes())
    assert result["ordering_is_robust"], (
        f"these assumptions flip the answer: {result['assumptions_that_change_the_answer']}"
    )


def test_zeroing_every_soft_assumption_still_prefers_the_firewall():
    """A reader who rejects the relationship penalty and the loss rate outright."""
    hostile = CostAssumptions(remediation_paise=0, relationship_penalty_paise=0,
                              refusal_loss_rate=0.0)
    priced = compare(_mixes(), hostile)
    assert priced["lowest_cost"] == "firewall"


def test_the_output_refuses_to_be_read_as_measurement():
    priced = compare(_mixes())
    caveat = priced["caveat"].lower()
    assert "not observed" in caveat or "not a claim" in caveat
    assert "fraud prevented" in caveat
    assert priced["assumptions"]["refusal_loss_rate_source"]
