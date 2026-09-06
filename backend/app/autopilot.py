"""Safe Autopilot orchestration above the existing exact-action runtime."""
from __future__ import annotations

from . import store
from .actions import canonicalize_action
from .authorization import cart_hash
from .config import get_settings
from .envelope import build_quote, draft_envelope, verify_quote
from .mcp_client import (
    ActionInProgress,
    ActionOutcomeUnknown,
    MandateViolation,
    SimulatedMCPClient,
    get_client,
    unwrap,
)
from .models import (
    ActionContext,
    ActionState,
    AutopilotExecuteRequest,
    AutopilotExecuteResponse,
    AutopilotScenario,
    AuthorizationRequest,
    EnvelopeActivateRequest,
    EnvelopeDecision,
    EnvelopeDraftRequest,
    EnvelopeRevokeRequest,
    PolicyDelta,
    PurchaseEnvelope,
)
from .receipts import build_receipt


def create_draft(req: EnvelopeDraftRequest) -> PurchaseEnvelope:
    return store.save_envelope_draft(draft_envelope(req))


def activate(envelope_id: str, req: EnvelopeActivateRequest) -> PurchaseEnvelope:
    return store.activate_envelope(envelope_id, req.expected_envelope_hash)


def revoke(envelope_id: str, req: EnvelopeRevokeRequest) -> PurchaseEnvelope:
    return store.revoke_envelope(envelope_id, req.expected_version)


def _binding_denial(
    envelope: PurchaseEnvelope,
    req: AutopilotExecuteRequest,
) -> EnvelopeDecision | None:
    deltas: list[PolicyDelta] = []
    if req.expected_envelope_version != envelope.version:
        deltas.append(
            PolicyDelta(
                field="envelope_version",
                expected=str(envelope.version),
                actual=str(req.expected_envelope_version),
                recovery="stop",
            )
        )
    if req.expected_envelope_hash != envelope.envelope_hash:
        deltas.append(
            PolicyDelta(
                field="envelope_hash",
                expected=envelope.envelope_hash,
                actual=req.expected_envelope_hash,
                recovery="stop",
            )
        )
    if not deltas:
        return None
    return EnvelopeDecision(
        allowed=False,
        code="BLOCK_ENVELOPE_BINDING_CHANGED",
        envelope_id=envelope.id,
        envelope_version=envelope.version,
        quote_total_paise=0,
        deltas=deltas,
        human_message="The approved envelope changed. Refresh before any action.",
    )


def execute(req: AutopilotExecuteRequest) -> AutopilotExecuteResponse:
    settings = get_settings()
    if req.scenario is not AutopilotScenario.NORMAL:
        if not settings.fault_injection_enabled:
            raise ValueError("Fault injection is disabled")
        if settings.payment_provider != "simulated":
            raise ValueError("Fault injection cannot target a live payment provider")
    envelope = store.get_envelope(req.envelope_id)
    if not envelope:
        raise LookupError("UNKNOWN_ENVELOPE")

    provider = get_client()
    provider_mode = type(provider).__name__
    quote, recovered = build_quote(envelope, req.scenario)
    attempt_id = req.purchase_attempt_id
    prior = (
        store.get_action_grant_for_attempt(envelope.mandate_id, attempt_id)
        if envelope.mandate_id
        else None
    )
    if prior and (
        prior.envelope_id == envelope.id
        and prior.envelope_version == req.expected_envelope_version
        and prior.envelope_hash == req.expected_envelope_hash
        and prior.quote_hash == quote.quote_hash
        and prior.cart_hash == cart_hash(quote.cart)
        and prior.session_id == req.session_id
        and prior.purchase_attempt_id == attempt_id
    ):
        payload = unwrap(prior.result or {})
        link = payload.get("short_url") if isinstance(payload, dict) else None
        replay_decision = EnvelopeDecision(
            allowed=prior.state in (ActionState.ACTION_ISSUED, ActionState.SETTLED),
            code=(
                "REPLAYED_RESULT"
                if prior.state in (ActionState.ACTION_ISSUED, ActionState.SETTLED)
                else "ACTION_ALREADY_IN_PROGRESS"
            ),
            envelope_id=envelope.id,
            envelope_version=prior.envelope_version or envelope.version,
            quote_total_paise=quote.cart.total_paise,
            human_message=(
                "Returned the stored result without another provider call."
                if prior.state in (ActionState.ACTION_ISSUED, ActionState.SETTLED)
                else "The exact action is already in flight; it was not dispatched again."
            ),
        )
        store.log_event(
            "ACTION_REPLAY_RETURNED",
            session_id=req.session_id,
            mandate_id=envelope.mandate_id,
            mandate_version=prior.mandate_version,
            code=replay_decision.code,
            cart_total_paise=quote.cart.total_paise,
            cap_paise=envelope.max_total_paise,
            payload={
                "grant_id": prior.id,
                "purchase_attempt_id": attempt_id,
                "original_state": prior.state.value,
                "provider_call_made": False,
                "surface": "autopilot",
            },
        )
        return AutopilotExecuteResponse(
            envelope=envelope,
            quote=quote,
            envelope_decision=replay_decision,
            action_status=prior.state,
            grant_id=prior.id,
            payment_link=link,
            receipt=build_receipt(prior),
            recovery_applied=recovered,
            provider_mode=provider_mode,
        )

    binding_denial = _binding_denial(envelope, req)
    if binding_denial:
        store.log_event(
            "ENVELOPE_QUOTE_BLOCKED",
            session_id=req.session_id,
            mandate_id=envelope.mandate_id,
            code=binding_denial.code,
            payload={"envelope_id": envelope.id},
        )
        return AutopilotExecuteResponse(
            envelope=envelope,
            quote=quote,
            envelope_decision=binding_denial,
            provider_mode=provider_mode,
        )

    envelope_decision = verify_quote(envelope, quote)
    if not envelope_decision.allowed:
        store.log_event(
            "ENVELOPE_QUOTE_BLOCKED",
            session_id=req.session_id,
            mandate_id=envelope.mandate_id,
            code=envelope_decision.code,
            cart_total_paise=quote.cart.total_paise,
            cap_paise=envelope.max_total_paise,
            payload={
                "envelope_id": envelope.id,
                "quote_hash": quote.quote_hash,
                "deltas": [delta.model_dump(mode="json") for delta in envelope_decision.deltas],
            },
        )
        return AutopilotExecuteResponse(
            envelope=envelope,
            quote=quote,
            envelope_decision=envelope_decision,
            recovery_applied=recovered,
            provider_mode=provider_mode,
        )

    store.log_event(
        "ENVELOPE_QUOTE_ALLOWED",
        session_id=req.session_id,
        mandate_id=envelope.mandate_id,
        code="ALLOW_ENVELOPE",
        cart_total_paise=quote.cart.total_paise,
        cap_paise=envelope.max_total_paise,
        payload={
            "envelope_id": envelope.id,
            "quote_hash": quote.quote_hash,
            "recovery_applied": recovered,
        },
    )
    if recovered:
        store.log_event(
            "ENVELOPE_RECOVERY_APPLIED",
            session_id=req.session_id,
            mandate_id=envelope.mandate_id,
            code="IN_ENVELOPE_SUBSTITUTION",
            cart_total_paise=quote.cart.total_paise,
            cap_paise=envelope.max_total_paise,
            payload={
                "envelope_id": envelope.id,
                "substitutions": [
                    item.model_dump(mode="json") for item in quote.substitutions
                ],
            },
        )

    if not envelope.mandate_id:
        raise ValueError("ACTIVE_ENVELOPE_WITHOUT_POLICY")
    mandate = store.get_mandate(envelope.mandate_id)
    if not mandate:
        raise ValueError("ENVELOPE_POLICY_MISSING")

    context = ActionContext(
        user_id=envelope.user_id,
        agent_id=envelope.agent_id,
        session_id=req.session_id,
        merchant_id=envelope.merchant_id,
    )
    canonical = canonicalize_action(
        envelope.action_name,
        {
            "amount": quote.cart.total_paise,
            "currency": envelope.currency,
            "description": f"Safe Autopilot purchase under envelope {envelope.id}",
            "accept_partial": False,
            "reference_id": attempt_id,
            "notes": {
                "policy_id": mandate.id,
                "envelope_id": envelope.id,
                "envelope_version": str(envelope.version),
                "session_id": req.session_id,
                "purchase_attempt_id": attempt_id,
            },
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
            purchase_attempt_id=attempt_id,
            envelope_id=envelope.id,
            expected_envelope_version=envelope.version,
            expected_envelope_hash=envelope.envelope_hash,
            quote=quote,
        )
    )
    if not outcome.authorized or not outcome.grant:
        denied = envelope_decision.model_copy(
            update={
                "allowed": False,
                "code": outcome.reason,
                "human_message": outcome.decision.human_message,
            }
        )
        return AutopilotExecuteResponse(
            envelope=store.get_envelope(envelope.id) or envelope,
            quote=quote,
            envelope_decision=denied,
            action_status=outcome.grant.state if outcome.grant else None,
            grant_id=outcome.grant.id if outcome.grant else None,
            receipt=build_receipt(outcome.grant) if outcome.grant else None,
            recovery_applied=recovered,
            provider_mode=provider_mode,
        )

    if outcome.replayed:
        payload = unwrap(outcome.grant.result or {})
        link = payload.get("short_url") if isinstance(payload, dict) else None
        return AutopilotExecuteResponse(
            envelope=store.get_envelope(envelope.id) or envelope,
            quote=quote,
            envelope_decision=envelope_decision,
            action_status=outcome.grant.state,
            grant_id=outcome.grant.id,
            payment_link=link,
            receipt=build_receipt(outcome.grant),
            recovery_applied=recovered,
            provider_mode=provider_mode,
        )

    if req.scenario is AutopilotScenario.TIMEOUT_AFTER_DISPATCH:
        provider = SimulatedMCPClient(failure_mode="timeout_after_dispatch")
        provider_mode = "SimulatedMCPClient(timeout_after_dispatch)"

    try:
        raw_result = provider.call_tool(
            canonical.name,
            canonical.args,
            outcome.grant.id,
            context,
            cart_hash(quote.cart),
        )
        payload = unwrap(raw_result)
        link = payload.get("short_url") if isinstance(payload, dict) else None
        current = store.get_action_grant(outcome.grant.id)
        return AutopilotExecuteResponse(
            envelope=store.get_envelope(envelope.id) or envelope,
            quote=quote,
            envelope_decision=envelope_decision,
            action_status=current.state if current else ActionState.ACTION_ISSUED,
            grant_id=outcome.grant.id,
            payment_link=link,
            receipt=build_receipt(current) if current else None,
            recovery_applied=recovered,
            provider_mode=provider_mode,
        )
    except ActionOutcomeUnknown as exc:
        current = store.get_action_grant(exc.grant_id)
        return AutopilotExecuteResponse(
            envelope=store.get_envelope(envelope.id) or envelope,
            quote=quote,
            envelope_decision=envelope_decision.model_copy(
                update={
                    "code": "ALLOW_BUT_PROVIDER_OUTCOME_UNKNOWN",
                    "human_message": (
                        "The provider outcome is unknown. Exposure remains held and "
                        "the action will not be retried before reconciliation."
                    ),
                }
            ),
            action_status=ActionState.UNKNOWN,
            grant_id=exc.grant_id,
            receipt=build_receipt(current) if current else None,
            recovery_applied=recovered,
            provider_mode=provider_mode,
        )
    except ActionInProgress:
        current = store.get_action_grant(outcome.grant.id)
        return AutopilotExecuteResponse(
            envelope=store.get_envelope(envelope.id) or envelope,
            quote=quote,
            envelope_decision=envelope_decision.model_copy(
                update={"code": "ACTION_ALREADY_IN_PROGRESS"}
            ),
            action_status=current.state if current else None,
            grant_id=outcome.grant.id,
            receipt=build_receipt(current) if current else None,
            recovery_applied=recovered,
            provider_mode=provider_mode,
        )
    except MandateViolation as exc:
        current = store.get_action_grant(outcome.grant.id)
        denied = envelope_decision.model_copy(
            update={
                "allowed": False,
                "code": str(exc),
                "human_message": "The exact grant changed before dispatch; no action was sent.",
            }
        )
        return AutopilotExecuteResponse(
            envelope=store.get_envelope(envelope.id) or envelope,
            quote=quote,
            envelope_decision=denied,
            action_status=current.state if current else ActionState.CANCELLED,
            grant_id=outcome.grant.id,
            receipt=build_receipt(current) if current else None,
            recovery_applied=recovered,
            provider_mode=provider_mode,
        )
