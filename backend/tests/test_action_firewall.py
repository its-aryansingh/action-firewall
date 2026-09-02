"""Adversarial tests for the exact action receipt and dispatch state machine."""
from __future__ import annotations

import threading
import uuid

import pytest
from pydantic import ValidationError

from app import store
from app.actions import canonicalize_action
from app.authorization import cart_hash
from app.config import get_settings
from app.mcp_client import (
    ActionInProgress,
    ActionOutcomeUnknown,
    MandateViolation,
    SimulatedMCPClient,
)
from app.models import (
    ActionContext,
    ActionState,
    AuthorizationRequest,
    Cart,
    CartLine,
    MandateCreate,
    MandateUpdate,
    PlannerOutput,
)


@pytest.fixture()
def clean_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "action-firewall.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    store.init_db()
    yield
    get_settings.cache_clear()


def make_cart(amount_paise: int = 10_000, qty: int = 1) -> Cart:
    return Cart(
        lines=[
            CartLine(
                sku="SKU-1",
                name="Test item",
                category="pantry",
                unit_price_paise=amount_paise,
                qty=qty,
            )
        ]
    )


def make_authorization(
    *,
    mandate,
    cart: Cart | None = None,
    attempt_id: str | None = None,
    session_id: str = "session-1",
    user_id: str = "user_demo",
    agent_id: str = "agent_groceries",
):
    cart = cart or make_cart()
    attempt_id = attempt_id or f"attempt-{uuid.uuid4().hex}"
    context = ActionContext(
        user_id=user_id,
        agent_id=agent_id,
        session_id=session_id,
    )
    raw_args = {
        "amount": cart.total_paise,
        "currency": "INR",
        "description": "Exact-bound test payment link",
        "accept_partial": False,
        "reference_id": attempt_id,
        "notes": {
            "policy_id": mandate.id,
            "agent_id": agent_id,
            "session_id": session_id,
            "purchase_attempt_id": attempt_id,
        },
    }
    canonical = canonicalize_action("create_payment_link", raw_args)
    request = AuthorizationRequest(
        context=context,
        mandate_id=mandate.id,
        expected_mandate_version=mandate.version,
        action_name=canonical.name,
        action_schema_hash=canonical.schema_hash,
        args=canonical.args,
        cart=cart,
        cart_hash=cart_hash(cart),
        purchase_attempt_id=attempt_id,
    )
    return store.authorize_and_reserve(request), canonical, context


def test_amount_tamper_is_rejected_before_transport(clean_db):
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    outcome, canonical, context = make_authorization(mandate=mandate)
    client = SimulatedMCPClient()
    tampered = {**canonical.args, "amount": canonical.args["amount"] + 1}

    with pytest.raises(MandateViolation):
        client.call_tool(
            canonical.name,
            tampered,
            outcome.grant.id,
            context,
            outcome.grant.cart_hash,
        )

    assert client.calls == []
    assert store.get_action_grant(outcome.grant.id).state is ActionState.CANCELLED


def test_unknown_state_changing_tool_fails_closed(clean_db):
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    outcome, canonical, context = make_authorization(mandate=mandate)
    client = SimulatedMCPClient()

    with pytest.raises(MandateViolation):
        client.call_tool(
            "initiate_payment",
            canonical.args,
            outcome.grant.id,
            context,
            outcome.grant.cart_hash,
        )

    assert client.calls == []
    assert store.get_action_grant(outcome.grant.id).state is ActionState.CANCELLED


def test_policy_edit_before_dispatch_invalidates_grant(clean_db):
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    outcome, canonical, context = make_authorization(mandate=mandate)
    store.update_mandate(mandate.id, MandateUpdate(cap_rupees=1))
    client = SimulatedMCPClient()

    with pytest.raises(MandateViolation, match="POLICY_CHANGED_BEFORE_DISPATCH"):
        client.call_tool(
            canonical.name,
            canonical.args,
            outcome.grant.id,
            context,
            outcome.grant.cart_hash,
        )

    assert client.calls == []
    assert store.get_action_grant(outcome.grant.id).state is ActionState.CANCELLED


def test_same_attempt_different_binding_is_conflict(clean_db):
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    attempt_id = "fixed-attempt"
    first, _, _ = make_authorization(
        mandate=mandate,
        cart=make_cart(10_000),
        attempt_id=attempt_id,
    )
    second, _, _ = make_authorization(
        mandate=mandate,
        cart=make_cart(20_000),
        attempt_id=attempt_id,
    )

    assert first.authorized
    assert not second.authorized
    assert second.reason == "IDEMPOTENCY_BINDING_CONFLICT"


def test_one_grant_is_consumed_once(clean_db):
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    outcome, canonical, context = make_authorization(mandate=mandate)
    client = SimulatedMCPClient()

    first = client.call_tool(
        canonical.name,
        canonical.args,
        outcome.grant.id,
        context,
        outcome.grant.cart_hash,
    )
    with pytest.raises(MandateViolation):
        client.call_tool(
            canonical.name,
            canonical.args,
            outcome.grant.id,
            context,
            outcome.grant.cart_hash,
        )

    assert first
    assert len(client.calls) == 1
    assert store.get_action_grant(outcome.grant.id).state is ActionState.ACTION_ISSUED


def test_concurrent_claims_have_one_dispatch_owner(clean_db):
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    outcome, canonical, context = make_authorization(mandate=mandate)
    client = SimulatedMCPClient()
    barrier = threading.Barrier(8)
    results: list[object] = [None] * 8

    def invoke(index: int) -> None:
        barrier.wait()
        try:
            results[index] = client.call_tool(
                canonical.name,
                canonical.args,
                outcome.grant.id,
                context,
                outcome.grant.cart_hash,
            )
        except Exception as exc:  # noqa: BLE001
            results[index] = exc

    threads = [threading.Thread(target=invoke, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(client.calls) == 1
    assert sum(isinstance(result, dict) for result in results) == 1
    assert all(
        isinstance(result, (dict, MandateViolation, ActionInProgress))
        for result in results
    )


def test_timeout_after_dispatch_becomes_unknown_and_blocks_retry(clean_db):
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    outcome, canonical, context = make_authorization(mandate=mandate)
    client = SimulatedMCPClient(failure_mode="timeout_after_dispatch")

    with pytest.raises(ActionOutcomeUnknown):
        client.call_tool(
            canonical.name,
            canonical.args,
            outcome.grant.id,
            context,
            outcome.grant.cart_hash,
        )
    assert store.get_action_grant(outcome.grant.id).state is ActionState.UNKNOWN
    assert store.spent_in_window(mandate.id, mandate.window) == canonical.amount_paise

    with pytest.raises(ActionInProgress):
        SimulatedMCPClient().call_tool(
            canonical.name,
            canonical.args,
            outcome.grant.id,
            context,
            outcome.grant.cart_hash,
        )


def test_unknown_can_be_reconciled_without_redispatch(clean_db):
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    outcome, canonical, context = make_authorization(mandate=mandate)
    client = SimulatedMCPClient(failure_mode="timeout_after_dispatch")
    with pytest.raises(ActionOutcomeUnknown):
        client.call_tool(
            canonical.name,
            canonical.args,
            outcome.grant.id,
            context,
            outcome.grant.cart_hash,
        )

    resolved = store.reconcile_unknown(
        outcome.grant.id,
        accepted=True,
        provider_ref="plink_reconciled",
        result={"id": "plink_reconciled", "status": "created"},
    )
    assert resolved.state is ActionState.ACTION_ISSUED
    assert resolved.provider_ref == "plink_reconciled"


def test_strict_planner_quantities_reject_negative_and_boolean():
    with pytest.raises(ValidationError):
        PlannerOutput.model_validate(
            {
                "reply": "bad",
                "intent": "discover",
                "cart_ops": [{"op": "add", "sku": "SKU-1", "qty": -10}],
            }
        )
    with pytest.raises(ValidationError):
        PlannerOutput.model_validate(
            {
                "reply": "bad",
                "intent": "discover",
                "cart_ops": [{"op": "add", "sku": "SKU-1", "qty": True}],
            }
        )


def test_action_schema_rejects_extra_or_coerced_arguments():
    with pytest.raises(Exception):
        canonicalize_action(
            "create_payment_link",
            {
                "amount": "100",
                "currency": "INR",
                "description": "bad",
                "accept_partial": False,
                "reference_id": "attempt",
                "notes": {},
            },
        )
    with pytest.raises(Exception):
        canonicalize_action(
            "create_payment_link",
            {
                "amount": 100,
                "currency": "INR",
                "description": "bad",
                "accept_partial": False,
                "reference_id": "attempt",
                "notes": {},
                "unexpected": "field",
            },
        )


def test_expired_legacy_reservation_cannot_commit_late(clean_db):
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    expired = store.reserve_headroom(
        mandate.id, 100_000, "expired", ttl_seconds=0
    )
    fresh = store.reserve_headroom(mandate.id, 100_000, "fresh")

    assert fresh.granted
    assert store.commit_reservation(expired.id, "plink_late") is False
    assert store.commit_reservation(fresh.id, "plink_fresh") is True
    assert store.spent_in_window(mandate.id, mandate.window) == 100_000
