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
from app.mcp_client import MandateViolation, SimulatedMCPClient, reset_simulated_provider
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
            idempotency_key=key,
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


def test_tampered_action_receipt_does_not_verify():
    envelope = active_envelope()
    result = execute(envelope, key="receipt-tamper", session="receipt-session")
    assert result.receipt and result.grant_id
    grant = store.get_action_grant(result.grant_id)
    assert grant

    tampered = result.receipt.model_copy(update={"cart_hash": "0" * 64})

    assert not verify_receipt(tampered, grant)


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

