"""Adversarial tests for the exact action receipt and dispatch state machine."""
from __future__ import annotations

import sqlite3
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


def test_audit_rows_cannot_be_updated(clean_db):
    store.log_event("TEST_EVENT", session_id="audit-session", code="ORIGINAL")
    audit_id = store.audit_trail("audit-session")[0]["id"]

    with sqlite3.connect(get_settings().db_path) as cx:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            cx.execute(
                "UPDATE audit_log SET code='TAMPERED' WHERE id=?",
                (audit_id,),
            )

    assert store.audit_trail("audit-session")[0]["code"] == "ORIGINAL"


def test_audit_rows_cannot_be_deleted(clean_db):
    store.log_event("TEST_EVENT", session_id="audit-session", code="ORIGINAL")
    audit_id = store.audit_trail("audit-session")[0]["id"]

    with sqlite3.connect(get_settings().db_path) as cx:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            cx.execute("DELETE FROM audit_log WHERE id=?", (audit_id,))

    assert store.audit_trail("audit-session")[0]["id"] == audit_id


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


def test_stale_dispatching_recovers_to_unknown_without_releasing_headroom(clean_db):
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    outcome, canonical, context = make_authorization(mandate=mandate)
    grant, token, reason = store.claim_action_grant(
        outcome.grant.id,
        context=context,
        action_name=canonical.name,
        action_schema_hash=canonical.schema_hash,
        args=canonical.args,
        cart_hash=outcome.grant.cart_hash,
    )

    assert grant and token and reason == "DISPATCH_CLAIMED"
    assert store.recover_stale_dispatches(cutoff_seconds=0) == 1
    recovered = store.get_action_grant(outcome.grant.id)
    assert recovered and recovered.state is ActionState.UNKNOWN
    assert store.spent_in_window(mandate.id, mandate.window) == canonical.amount_paise

    with pytest.raises(ActionInProgress):
        SimulatedMCPClient().call_tool(
            canonical.name,
            canonical.args,
            outcome.grant.id,
            context,
            outcome.grant.cart_hash,
        )


def test_late_result_from_original_dispatch_owner_can_resolve_recovered_unknown(clean_db):
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    outcome, canonical, context = make_authorization(mandate=mandate)
    _, token, _ = store.claim_action_grant(
        outcome.grant.id,
        context=context,
        action_name=canonical.name,
        action_schema_hash=canonical.schema_hash,
        args=canonical.args,
        cart_hash=outcome.grant.cart_hash,
    )
    assert token
    assert store.recover_stale_dispatches(cutoff_seconds=0) == 1

    issued = store.mark_action_issued(
        outcome.grant.id,
        token,
        provider_ref="plink_late_result",
        result={"id": "plink_late_result", "status": "created"},
    )

    assert issued.state is ActionState.ACTION_ISSUED
    assert issued.provider_ref == "plink_late_result"


def test_fresh_dispatch_is_not_recovered_early(clean_db):
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    outcome, canonical, context = make_authorization(mandate=mandate)
    store.claim_action_grant(
        outcome.grant.id,
        context=context,
        action_name=canonical.name,
        action_schema_hash=canonical.schema_hash,
        args=canonical.args,
        cart_hash=outcome.grant.cart_hash,
    )

    assert store.recover_stale_dispatches(cutoff_seconds=60) == 0
    current = store.get_action_grant(outcome.grant.id)
    assert current and current.state is ActionState.DISPATCHING


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


# ---------------------------------------------------------------------------
# Regressions found in the pre-submission adversarial audit
# ---------------------------------------------------------------------------
def test_zero_per_transaction_cap_is_a_cap_not_an_absence(clean_db):
    """A per-transaction cap of 0 must block, not disable the cap.

    create_mandate coerced the value with truthiness, so the most restrictive
    limit a shopper can express (0) stored NULL and removed the cap entirely.
    update_mandate had always been correct, so the same input produced opposite
    policies depending on which route set it.
    """
    created = store.create_mandate(MandateCreate(cap_rupees=1_000, per_txn_cap_rupees=0))
    assert created.per_txn_cap_paise == 0, "0 must persist as a zero cap, not NULL"

    updated = store.update_mandate(created.id, MandateUpdate(per_txn_cap_rupees=0))
    assert updated is not None
    assert updated.per_txn_cap_paise == created.per_txn_cap_paise, (
        "create and update must agree on what a zero per-transaction cap means"
    )


def test_audit_rows_cannot_be_rewritten_by_insert_or_replace(clean_db):
    """INSERT OR REPLACE must not be able to overwrite an audit row in place.

    SQLite leaves recursive_triggers OFF by default, and with it off the
    implicit DELETE inside a REPLACE conflict does not fire the BEFORE DELETE
    guard. A breach record could be rewritten to ALLOW with the row count
    unchanged and no error raised.
    """
    store.log_event(event="AUTHORIZATION_ATTEMPT", code="BLOCK_WINDOW_CAP_EXCEEDED",
                    cart_total_paise=500_000, payload={"truth": "the agent overspent"})
    with store._conn() as cx:
        # Worst case on purpose: whether the implicit DELETE inside a REPLACE
        # fires the delete guard varies by SQLite build, so turn the pragma off
        # and prove the BEFORE INSERT guard holds without it.
        cx.execute("PRAGMA recursive_triggers=OFF")
        row = cx.execute(
            "SELECT id FROM audit_log WHERE code='BLOCK_WINDOW_CAP_EXCEEDED'"
        ).fetchone()
        assert row is not None
        with pytest.raises(sqlite3.IntegrityError):
            cx.execute(
                "INSERT OR REPLACE INTO audit_log "
                "(id,session_id,mandate_id,mandate_version,event,code,"
                " cart_total_paise,cap_paise,payload,created_at) "
                "VALUES (?,NULL,NULL,NULL,'AUTHORIZATION_ATTEMPT','ALLOW',0,0,'{}',0)",
                (row["id"],),
            )

    with store._conn() as cx:
        after = cx.execute(
            "SELECT code, cart_total_paise FROM audit_log WHERE id=?", (row["id"],)
        ).fetchone()
    assert after["code"] == "BLOCK_WINDOW_CAP_EXCEEDED"
    assert after["cart_total_paise"] == 500_000


def test_duplicate_dispatch_of_issued_grant_is_in_progress_not_a_violation(clean_db):
    """A second dispatch of a spent grant must not read as a binding mismatch.

    ALREADY_ISSUED means the action succeeded and this caller lost the race.
    It was raised as a bare MandateViolation, which the agent renders as "the
    exact action no longer matches its authorization receipt" and records as a
    BLOCKED tool call - a false entry for a call that had in fact gone through.
    ActionInProgress is the correct family, and it is a MandateViolation
    subclass, so fail-closed behaviour is unchanged.
    """
    mandate = store.create_mandate(MandateCreate(cap_rupees=1_000))
    outcome, canonical, context = make_authorization(mandate=mandate)
    client = SimulatedMCPClient()

    client.call_tool(canonical.name, canonical.args, outcome.grant.id,
                     context, outcome.grant.cart_hash)

    with pytest.raises(ActionInProgress) as excinfo:
        client.call_tool(canonical.name, canonical.args, outcome.grant.id,
                         context, outcome.grant.cart_hash)

    assert "ALREADY_ISSUED" in str(excinfo.value)
    assert len(client.calls) == 1, "the provider must still be called exactly once"
    assert store.get_action_grant(outcome.grant.id).state is ActionState.ACTION_ISSUED
