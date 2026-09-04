"""Settlement must be an observation of the provider, never an assertion.

Before this module existed, `settled` was a state nothing could write, so
`confirmed_test_payment_value_paise` was structurally zero and invariant 10 was
satisfied only because settlement was unreachable. These tests close that loop
and pin the property that makes it safe: no caller can declare that money moved.
"""
from __future__ import annotations

import pytest

from app import mcp_client, reconciler, store
from app.config import get_settings
from app.mcp_client import SimulatedMCPClient
from app.models import ActionState, Cart, CartLine, MandateCreate

from tests.test_action_firewall import make_authorization


@pytest.fixture()
def clean_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "reconcile.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    store.init_db()
    mcp_client.reset_simulated_provider()
    yield
    mcp_client.reset_simulated_provider()
    get_settings.cache_clear()


def _issue(amount_paise: int = 48_600):
    """Drive one purchase all the way to an issued payment link."""
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    cart = Cart(lines=[CartLine(sku="SKU-1", name="Test item", category="pantry",
                                unit_price_paise=amount_paise, qty=1)])
    outcome, canonical, context = make_authorization(mandate=mandate, cart=cart)
    assert outcome.authorized, outcome.decision.code

    client = SimulatedMCPClient()
    client.call_tool(canonical.name, canonical.args, outcome.grant.id,
                     context, outcome.grant.cart_hash)
    grant = store.get_action_grant(outcome.grant.id)
    assert grant.state is ActionState.ACTION_ISSUED
    return grant


def test_issued_action_is_not_settled_until_the_provider_says_paid(clean_db):
    grant = _issue()
    result = reconciler.reconcile(grant.id)

    assert result.changed is False
    assert result.after is ActionState.ACTION_ISSUED
    assert result.observation.provider_status == "created"
    assert store.metrics()["confirmed_test_payment_value_paise"] == 0


def test_provider_reporting_paid_settles_the_action(clean_db):
    grant = _issue(amount_paise=48_600)
    # Stands in for the shopper paying the link with the test-mode UPI handle.
    mcp_client.simulate_provider_payment(grant.provider_ref, 48_600)

    result = reconciler.reconcile(grant.id)

    assert result.changed is True
    assert result.after is ActionState.SETTLED
    assert store.get_action_grant(grant.id).state is ActionState.SETTLED
    assert store.metrics()["confirmed_test_payment_value_paise"] == 48_600


def test_settlement_is_recorded_in_the_audit_trail(clean_db):
    grant = _issue()
    mcp_client.simulate_provider_payment(grant.provider_ref, grant.amount_paise)
    reconciler.reconcile(grant.id)

    events = [row["event"] for row in store.audit_trail(limit=50)]
    assert "ACTION_SETTLED" in events


def test_an_unreachable_provider_changes_nothing_and_retains_exposure(clean_db):
    """Invariant 9: not knowing is not the same as not paid."""
    grant = _issue()
    before = store.spent_in_window(grant.mandate_id, store.get_mandate(
        grant.mandate_id).window)

    class Unreachable(SimulatedMCPClient):
        def fetch_action_status(self, provider_ref):
            raise RuntimeError("connection reset")

    import app.reconciler as r
    original = r.get_client
    r.get_client = lambda: Unreachable()
    try:
        result = r.reconcile(grant.id)
    finally:
        r.get_client = original

    assert result.changed is False
    assert result.observation.reachable is False
    assert store.get_action_grant(grant.id).state is ActionState.ACTION_ISSUED
    assert store.spent_in_window(
        grant.mandate_id, store.get_mandate(grant.mandate_id).window) == before


def test_reconciling_twice_is_idempotent(clean_db):
    grant = _issue()
    mcp_client.simulate_provider_payment(grant.provider_ref, grant.amount_paise)
    first = reconciler.reconcile(grant.id)
    second = reconciler.reconcile(grant.id)

    assert first.changed is True
    assert second.changed is False
    assert second.before is ActionState.SETTLED
    assert store.metrics()["confirmed_test_payment_value_paise"] == grant.amount_paise


def test_the_http_route_cannot_be_told_that_money_moved(clean_db):
    """The route accepts a grant id and nothing else, by construction."""
    import inspect
    from app.main import reconcile_action

    params = set(inspect.signature(reconcile_action).parameters)
    assert params == {"grant_id"}, (
        "reconcile must take no status, amount or paid flag from the caller"
    )


def test_sweep_resolves_every_open_action(clean_db):
    grant = _issue()
    mcp_client.simulate_provider_payment(grant.provider_ref, grant.amount_paise)

    results = reconciler.reconcile_open_actions()

    assert any(r.changed and r.after is ActionState.SETTLED for r in results)
    assert store.open_actions_for_reconciliation() == []
