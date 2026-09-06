"""End-to-end tests for the Purchase Envelope authorization path."""
from __future__ import annotations

import threading
import uuid

import pytest

from app import autopilot, store
from app.actions import canonicalize_action
from app.authorization import cart_hash
from app.config import get_settings
from app.envelope import build_quote, verify_quote
from app.mcp_client import (
    MandateViolation,
    RazorpayMCPClient,
    SimulatedMCPClient,
    get_client,
    reset_simulated_provider,
)
from app.models import (
    ActionContext,
    ActionState,
    AutopilotExecuteRequest,
    AutopilotScenario,
    AuthorizationRequest,
    EnvelopeActivateRequest,
    EnvelopeDraftRequest,
    EnvelopeRevokeRequest,
    EnvelopeStatus,
)
from app.receipts import verify_receipt


@pytest.fixture(autouse=True)
def clean_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "safe-autopilot.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ACTION_RECEIPT_SECRET", "")
    get_settings.cache_clear()
    reset_simulated_provider()
    store.init_db()
    yield
    get_settings.cache_clear()


def active_envelope(max_total_rupees: int = 600):
    draft = autopilot.create_draft(
        EnvelopeDraftRequest(
            goal="Buy supplies for a pasta dinner",
            max_total_rupees=max_total_rupees,
        )
    )
    return autopilot.activate(
        draft.id, EnvelopeActivateRequest(expected_envelope_hash=draft.envelope_hash)
    )


def execute(envelope, *, scenario=AutopilotScenario.NORMAL, key=None, session=None):
    return autopilot.execute(
        AutopilotExecuteRequest(
            envelope_id=envelope.id,
            expected_envelope_version=envelope.version,
            expected_envelope_hash=envelope.envelope_hash,
            session_id=session or f"session-{uuid.uuid4().hex}",
            purchase_attempt_id=key or f"attempt-{uuid.uuid4().hex}",
            scenario=scenario,
        )
    )


def test_draft_requires_hash_bound_activation_and_creates_spend_fence():
    draft = autopilot.create_draft(
        EnvelopeDraftRequest(goal="Buy supplies for a pasta dinner", max_total_rupees=600)
    )

    with pytest.raises(ValueError, match="ENVELOPE_HASH_CHANGED"):
        autopilot.activate(
            draft.id,
            EnvelopeActivateRequest(expected_envelope_hash="0" * 64),
        )

    active = autopilot.activate(
        draft.id, EnvelopeActivateRequest(expected_envelope_hash=draft.envelope_hash)
    )

    assert draft.status is EnvelopeStatus.DRAFT
    assert active.status is EnvelopeStatus.ACTIVE
    assert active.version == draft.version + 1
    assert active.envelope_hash != draft.envelope_hash
    mandate = store.get_mandate(active.mandate_id)
    assert mandate and mandate.active
    assert mandate.cap_paise == active.max_total_paise
    assert mandate.per_txn_cap_paise == active.max_total_paise


def test_stock_loss_recovers_only_inside_the_same_envelope():
    envelope = active_envelope()

    normal, _ = build_quote(envelope)
    recovered, applied = build_quote(envelope, AutopilotScenario.STOCK_LOSS)

    assert verify_quote(envelope, normal).allowed
    assert verify_quote(envelope, recovered).allowed
    assert applied is True
    assert recovered.substitutions
    assert recovered.cart.lines[0].sku != normal.cart.lines[0].sku
    assert recovered.cart.total_paise <= envelope.max_total_paise


def test_activating_another_job_does_not_revoke_the_first_job():
    first = active_envelope()
    second = active_envelope()

    first_policy = store.get_mandate(first.mandate_id)
    second_policy = store.get_mandate(second.mandate_id)

    assert first.agent_id != second.agent_id
    assert first_policy and first_policy.active
    assert second_policy and second_policy.active


@pytest.mark.parametrize(
    ("scenario", "field"),
    [
        (AutopilotScenario.PRICE_DRIFT, "max_total_paise"),
        (AutopilotScenario.MERCHANT_DRIFT, "merchant_id"),
        (AutopilotScenario.FULFILLMENT_DRIFT, "fulfillment_profile_id"),
    ],
)
def test_out_of_envelope_quote_returns_field_delta_without_action(scenario, field):
    envelope = active_envelope()

    result = execute(envelope, scenario=scenario)

    assert not result.envelope_decision.allowed
    assert any(delta.field == field for delta in result.envelope_decision.deltas)
    assert result.grant_id is None
    assert not [event for event in store.audit_trail() if event["event"] == "ACTION_ISSUED"]


def test_valid_quote_issues_one_action_consumes_envelope_and_signs_receipt():
    envelope = active_envelope()
    session = "safe-session"
    key = "one-approved-job"

    first = execute(envelope, key=key, session=session)
    retry = execute(envelope, key=key, session=session)

    assert first.envelope_decision.allowed
    assert first.action_status is ActionState.ACTION_ISSUED
    assert first.payment_link and first.payment_link.startswith("https://rzp.io/")
    assert first.receipt and first.grant_id
    assert verify_receipt(first.receipt, store.get_action_grant(first.grant_id))
    assert store.get_envelope(envelope.id).status is EnvelopeStatus.CONSUMED
    assert retry.grant_id == first.grant_id
    assert retry.envelope_decision.code == "REPLAYED_RESULT"
    issued = [event for event in store.audit_trail() if event["event"] == "ACTION_ISSUED"]
    assert len(issued) == 1
    replayed = [
        event
        for event in store.audit_trail(session)
        if event["event"] == "ACTION_REPLAY_RETURNED"
    ]
    assert len(replayed) == 1
    assert replayed[0]["code"] == "REPLAYED_RESULT"
    assert replayed[0]["payload"] == {
        "grant_id": first.grant_id,
        "purchase_attempt_id": key,
        "original_state": "action_issued",
        "provider_call_made": False,
        "surface": "autopilot",
    }


def test_receipt_authorization_core_survives_settlement_and_status_is_superseded():
    envelope = active_envelope()
    result = execute(envelope, key="receipt-settle", session="receipt-settle-session")
    assert result.receipt and result.grant_id
    grant = store.get_action_grant(result.grant_id)
    assert grant

    initial_verification = verify_receipt(result.receipt, grant)
    assert initial_verification.authorization_valid is True
    assert initial_verification.status_current is True
    assert initial_verification.valid is True
    assert bool(initial_verification) is True

    # Provider confirms settlement: grant state transitions to SETTLED
    settled_grant = store.settle_issued_action(
        result.grant_id,
        provider_ref="pay_test_settle_123",
        result={"status": "paid"},
    )
    assert settled_grant.state is ActionState.SETTLED

    # The receipt issued at ACTION_ISSUED still has a valid authorization core,
    # but its status block is now superseded.
    post_settle_verification = verify_receipt(result.receipt, settled_grant)
    assert post_settle_verification.authorization_valid is True
    assert post_settle_verification.status_current is False
    assert post_settle_verification.valid is True
    assert bool(post_settle_verification) is True


def test_tampered_action_receipt_does_not_verify():
    envelope = active_envelope()
    result = execute(envelope, key="receipt-tamper", session="receipt-session")
    assert result.receipt and result.grant_id
    grant = store.get_action_grant(result.grant_id)
    assert grant

    # Tampering cart_hash fails authorization core
    tampered_cart = result.receipt.model_copy(update={"cart_hash": "0" * 64})
    v_cart = verify_receipt(tampered_cart, grant)
    assert v_cart.authorization_valid is False
    assert not v_cart

    # Tampering quote_hash fails authorization core
    tampered_quote = result.receipt.model_copy(update={"quote_hash": "f" * 64})
    v_quote = verify_receipt(tampered_quote, grant)
    assert v_quote.authorization_valid is False
    assert not v_quote

    # Tampering created_at fails authorization core
    tampered_time = result.receipt.model_copy(update={"created_at": 1234567.0})
    v_time = verify_receipt(tampered_time, grant)
    assert v_time.authorization_valid is False
    assert not v_time

    # Tampering status signature fails status verification
    tampered_status_sig = result.receipt.model_copy(update={"status_signature": "0" * 64})
    v_stat = verify_receipt(tampered_status_sig, grant)
    assert v_stat.status_current is False


def test_receipt_cross_grant_binding_fails():
    env1 = active_envelope(500)
    env2 = active_envelope(600)

    res1 = execute(env1, key="grant-attempt-a", session="session-a")
    res2 = execute(env2, key="grant-attempt-b", session="session-b")
    assert res1.receipt and res2.receipt
    grant2 = store.get_action_grant(res2.grant_id)

    # Receipt from grant 1 tested against grant 2 must fail
    v = verify_receipt(res1.receipt, grant2)
    assert v.authorization_valid is False
    assert v.valid is False
    assert not v



def test_concurrent_distinct_attempts_under_one_envelope_issue_once():
    envelope = active_envelope()
    barrier = threading.Barrier(8)
    results: list[object] = [None] * 8

    def invoke(index: int) -> None:
        barrier.wait()
        results[index] = execute(
            envelope,
            key=f"attempt-{index}",
            session=f"session-{index}",
        )

    threads = [threading.Thread(target=invoke, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(
        result.action_status is ActionState.ACTION_ISSUED
        for result in results
        if not isinstance(result, Exception)
    ) == 1
    issued = [event for event in store.audit_trail() if event["event"] == "ACTION_ISSUED"]
    assert len(issued) == 1


def test_revocation_after_authorization_blocks_dispatch():
    envelope = active_envelope()
    quote, _ = build_quote(envelope)
    mandate = store.get_mandate(envelope.mandate_id)
    assert mandate
    context = ActionContext(
        user_id=envelope.user_id,
        agent_id=envelope.agent_id,
        session_id="revocation-race",
        merchant_id=envelope.merchant_id,
    )
    canonical = canonicalize_action(
        "create_payment_link",
        {
            "amount": quote.cart.total_paise,
            "currency": "INR",
            "description": "Revocation race test",
            "accept_partial": False,
            "reference_id": "revocation-race",
            "notes": {"envelope_id": envelope.id},
        },
    )
    outcome = store.authorize_and_reserve(
        AuthorizationRequest(
            context=context,
            mandate_id=mandate.id,
            expected_mandate_version=mandate.version,
            action_name=canonical.name,
            action_schema_hash=canonical.schema_hash,
            args=canonical.args,
            cart=quote.cart,
            cart_hash=cart_hash(quote.cart),
            purchase_attempt_id="revocation-race",
            envelope_id=envelope.id,
            expected_envelope_version=envelope.version,
            expected_envelope_hash=envelope.envelope_hash,
            quote=quote,
        )
    )
    assert outcome.authorized and outcome.grant

    autopilot.revoke(
        envelope.id, EnvelopeRevokeRequest(expected_version=envelope.version)
    )
    client = SimulatedMCPClient()
    with pytest.raises(MandateViolation, match="POLICY_CHANGED_BEFORE_DISPATCH"):
        client.call_tool(
            canonical.name,
            canonical.args,
            outcome.grant.id,
            context,
            cart_hash(quote.cart),
        )

    assert client.calls == []
    assert store.get_action_grant(outcome.grant.id).state is ActionState.CANCELLED


def test_unknown_provider_outcome_holds_one_use_and_does_not_redispatch():
    envelope = active_envelope()
    key = "timeout-attempt"
    session = "timeout-session"

    first = execute(
        envelope,
        scenario=AutopilotScenario.TIMEOUT_AFTER_DISPATCH,
        key=key,
        session=session,
    )
    retry = execute(
        envelope,
        scenario=AutopilotScenario.TIMEOUT_AFTER_DISPATCH,
        key=key,
        session=session,
    )

    assert first.action_status is ActionState.UNKNOWN
    assert retry.grant_id == first.grant_id
    assert retry.action_status is ActionState.UNKNOWN
    assert retry.envelope_decision.code == "ACTION_ALREADY_IN_PROGRESS"
    started = [
        event for event in store.audit_trail() if event["event"] == "ACTION_DISPATCH_STARTED"
    ]
    assert len(started) == 1
    replayed = [
        event
        for event in store.audit_trail(session)
        if event["event"] == "ACTION_REPLAY_RETURNED"
    ]
    assert len(replayed) == 1
    assert replayed[0]["code"] == "ACTION_ALREADY_IN_PROGRESS"
    assert replayed[0]["payload"]["original_state"] == "unknown"
    assert replayed[0]["payload"]["provider_call_made"] is False


def test_unintelligible_goal_produces_no_draft():
    gibberish = "xyzzy blorp qwerty 123456789 non-existent nonsense"
    with pytest.raises(ValueError, match="GOAL_NOT_UNDERSTOOD"):
        autopilot.create_draft(
            EnvelopeDraftRequest(
                goal=gibberish,
                max_total_rupees=500,
            )
        )
    assert store.list_envelopes("user_demo") == []
    drafted_events = [
        event for event in store.audit_trail() if event["event"] == "ENVELOPE_DRAFTED"
    ]
    assert len(drafted_events) == 0


def test_fault_injection_switch_is_independent_of_demo_mode(monkeypatch):
    envelope = active_envelope()
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "false")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="Fault injection is disabled"):
        autopilot.execute(
            AutopilotExecuteRequest(
                envelope_id=envelope.id,
                expected_envelope_version=envelope.version,
                expected_envelope_hash=envelope.envelope_hash,
                session_id="session-non-demo",
                purchase_attempt_id="key-non-demo",
                scenario=AutopilotScenario.STOCK_LOSS,
            )
        )


def test_fault_injection_can_never_target_live_provider(monkeypatch):
    envelope = active_envelope()
    monkeypatch.setenv("PAYMENT_PROVIDER", "razorpay_mcp")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_config_only")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "not-a-real-secret")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="cannot target a live payment provider"):
        execute(envelope, scenario=AutopilotScenario.STOCK_LOSS)


def test_payment_provider_selection_is_not_derived_from_demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    get_settings.cache_clear()
    assert isinstance(get_client(), SimulatedMCPClient)

    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "razorpay_mcp")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_config_only")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "not-a-real-secret")
    get_settings.cache_clear()
    assert isinstance(get_client(), RazorpayMCPClient)


def test_live_provider_selection_fails_closed_without_credentials(monkeypatch):
    monkeypatch.setenv("PAYMENT_PROVIDER", "razorpay_mcp")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "")
    monkeypatch.setenv("RAZORPAY_MCP_TOKEN", "")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="requires RAZORPAY_MCP_TOKEN"):
        get_client()


