"""Unified commerce checkout service for Action Firewall.

Single path to money: both HTTP (agent_commerce.submit_attempt) and MCP
(commerce_mcp.request_checkout) resolve identity at the transport boundary
and delegate to execute_checkout().
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Literal

from fastapi import HTTPException

from . import autopilot, demo_scenario, mcp_client, store
from .acceptance_policy import compute_acceptance_policy_hash
from .buyer_auth import (
    AgentPrincipal,
    ShopperPrincipal,
    check_replay_or_mutation,
    record_successful_request,
    verify_merchant_access,
)
from .buyer_models import CommerceAttemptResponse, CommerceAttemptStage
from .channel_policy import evaluate_channel_policy
from .commerce_metrics import record_agent_order
from .merchant import CATALOG_REVISION
from .models import (
    AutopilotExecuteRequest,
    AutopilotScenario,
    Cart,
    PurchaseEnvelope,
)
from .rate_limit import enforce_rate_limit


@dataclass(frozen=True)
class CheckoutPrincipals:
    """Who is asking. Resolved by the transport, never by the caller's body."""
    buyer: AgentPrincipal
    shopper: ShopperPrincipal
    transport: Literal["http", "mcp"]


@dataclass(frozen=True)
class CheckoutResult:
    """Structured result returned by execute_checkout."""
    attempt_id: str
    envelope_id: str
    outcome: str
    stages: list[CommerceAttemptStage]
    allowed: bool
    code: str
    human_message: str
    quote_total_paise: int
    payment_link: str | None
    grant_id: str | None
    receipt: Any | None
    deltas: list[Any]
    recovery_applied: bool
    provider_mode: str
    razorpay_action_called: bool
    error: str | None = None

    def to_http_response(self) -> CommerceAttemptResponse:
        return CommerceAttemptResponse(
            attempt_id=self.attempt_id,
            envelope_id=self.envelope_id,
            outcome=self.outcome,
            stages=self.stages,
            allowed=self.allowed,
            code=self.code,
            human_message=self.human_message,
            quote_total_paise=self.quote_total_paise,
            payment_link=self.payment_link,
            grant_id=self.grant_id,
            receipt=self.receipt,
            deltas=self.deltas,
            recovery_applied=self.recovery_applied,
            provider_mode=self.provider_mode,
            razorpay_action_called=self.razorpay_action_called,
        )

    def to_mcp_dict(self) -> dict[str, Any]:
        receipt_id = (
            self.receipt.grant_id
            if hasattr(self.receipt, "grant_id")
            else (self.receipt.get("grant_id") if isinstance(self.receipt, dict) else None)
        )
        d: dict[str, Any] = {
            # So a caller can confirm the rules it read at /acceptance-policy are
            # the rules that were applied to this decision. A published policy
            # nobody can tie back to an outcome is a brochure.
            "acceptance_policy_hash": compute_acceptance_policy_hash(),
            "attempt_id": self.attempt_id,
            "intent_id": self.envelope_id,
            "envelope_id": self.envelope_id,
            "outcome": self.outcome,
            "stages": [
                s.model_dump() if hasattr(s, "model_dump") else s for s in self.stages
            ],
            "allowed": self.allowed,
            "code": self.code,
            "human_message": self.human_message,
            "quote_total_paise": self.quote_total_paise,
            "payment_link": self.payment_link,
            "grant_id": self.grant_id,
            "receipt_id": receipt_id,
            "receipt": (
                self.receipt.model_dump()
                if hasattr(self.receipt, "model_dump")
                else self.receipt
            ),
            "deltas": [
                d.model_dump() if hasattr(d, "model_dump") else d for d in self.deltas
            ],
            "recovery_applied": self.recovery_applied,
            "provider_mode": self.provider_mode,
            "razorpay_action_called": self.razorpay_action_called,
        }
        if self.error:
            d["error"] = self.error
        return d



def execute_checkout(
    principals: CheckoutPrincipals,
    envelope_id: str,
    attempt_id: str,
    quote_id: str | None = None,
    scenario: AutopilotScenario | str | None = None,
    expected_envelope_version: int | None = None,
    expected_envelope_hash: str | None = None,
    body_data: dict[str, Any] | None = None,
) -> CheckoutResult:
    """The single money path across HTTP and MCP surfaces.

    Enforces:
    1. Rate limiting
    2. Envelope lookup & 404 handling
    3. Merchant access verification
    4. Replay / mutation cache check
    5. Active envelope verification
    6. Authoritative quote validation (ownership, TTL, catalog revision, CAS checked out)
    7. Channel policy pre-flight check
    8. Autopilot execution (atomic reservation + action issuance)
    9. Outcome classification
    10. Audit, order recording, and idempotent replay caching
    """
    is_http = principals.transport == "http"

    # 0. An unverified caller may not reach real money.
    #
    # verify_buyer_agent returns a principal marked authenticated=False when no
    # credential was presented and demo mode allows the fallback. That is a
    # deliberately honest label rather than a refusal, so the offline demo runs
    # without keys — but the label has to be load-bearing somewhere, or it is
    # decoration. This is that place: an unauthenticated principal is confined
    # to the simulated provider, and the moment a real Razorpay client is
    # configured it is refused outright.
    #
    # Without this, the MCP surface — the one advertised to external AI buyers —
    # could construct a principal and reach the money path on its own say-so.
    if not principals.buyer.authenticated:
        provider = mcp_client.get_active_provider_mode()
        if provider not in ("simulated", "SimulatedMCPClient", ""):
            message = (
                "This caller presented no verified buyer-agent credential, so it "
                "may not reach a live payment provider."
            )
            if is_http:
                raise HTTPException(status_code=401, detail=message)
            return CheckoutResult(
                attempt_id=attempt_id,
                envelope_id=envelope_id,
                outcome="STOPPED_BEFORE_RAZORPAY",
                stages=[],
                allowed=False,
                code="UNAUTHENTICATED_BUYER_AGENT",
                human_message=message,
                quote_total_paise=0,
                payment_link=None,
                grant_id=None,
                receipt=None,
                deltas=[],
                recovery_applied=False,
                provider_mode=provider,
                razorpay_action_called=False,
                error=message,
            )

    # 1. Rate limiting
    enforce_rate_limit(principals.buyer, principals.shopper.shopper_session_id)

    # 2. Envelope lookup
    envelope = store.get_envelope(envelope_id)
    if not envelope:
        if is_http:
            raise HTTPException(404, "Unknown Purchase Envelope")
        return CheckoutResult(
            attempt_id=attempt_id,
            envelope_id=envelope_id,
            outcome="STOPPED_BEFORE_RAZORPAY",
            stages=[],
            allowed=False,
            code="ENVELOPE_NOT_FOUND",
            human_message="Unknown Purchase Envelope",
            quote_total_paise=0,
            payment_link=None,
            grant_id=None,
            receipt=None,
            deltas=[],
            recovery_applied=False,
            provider_mode="simulated",
            razorpay_action_called=False,
            error=f"Envelope {envelope_id} not found",
        )

    # 3. Merchant access check
    verify_merchant_access(envelope.merchant_id, principals.buyer)

    # 4. Replay / mutation cache check
    if body_data:
        cached = check_replay_or_mutation(
            agent_request_id=attempt_id,
            merchant_id=envelope.merchant_id,
            buyer_agent_id=principals.buyer.buyer_agent_id,
            shopper_session_id=principals.shopper.shopper_session_id,
            body_data=body_data,
        )
        if cached:
            return CheckoutResult(
                attempt_id=cached["attempt_id"],
                envelope_id=cached["envelope_id"],
                outcome=cached["outcome"],
                stages=[CommerceAttemptStage(**s) for s in cached.get("stages", [])],
                allowed=cached["allowed"],
                code=cached["code"],
                human_message=cached["human_message"],
                quote_total_paise=cached["quote_total_paise"],
                payment_link=cached["payment_link"],
                grant_id=cached["grant_id"],
                receipt=cached["receipt"],
                deltas=cached.get("deltas", []),
                recovery_applied=cached["recovery_applied"],
                provider_mode=cached["provider_mode"],
                razorpay_action_called=cached["razorpay_action_called"],
            )

    # 5. Envelope active check
    if envelope.status.value != "active":
        stages = [
            CommerceAttemptStage(
                stage="understand",
                name="Draft Intent",
                status="completed",
                detail="Envelope created",
            ),
            CommerceAttemptStage(
                stage="quote",
                name="Server Quote",
                status="completed",
                detail="Catalog verified",
            ),
            CommerceAttemptStage(
                stage="authorize",
                name="Authority Gate",
                status="blocked",
                detail=f"Envelope is {envelope.status.value}",
            ),
            CommerceAttemptStage(
                stage="razorpay_action",
                name="Razorpay Action",
                status="blocked",
                detail="Razorpay action not called",
            ),
        ]
        code = (
            "AWAITING_CUSTOMER_APPROVAL"
            if not is_http
            else f"BLOCK_ENVELOPE_{envelope.status.value.upper()}"
        )
        human_msg = (
            "Purchase Envelope is in draft status. Customer approval via approval_url required before checkout."
            if not is_http
            else f"Purchase Envelope is {envelope.status.value}. Explicit human activation is required before checkout."
        )
        return CheckoutResult(
            attempt_id=attempt_id,
            envelope_id=envelope_id,
            outcome="STOPPED_BEFORE_RAZORPAY",
            stages=stages,
            allowed=False,
            code=code,
            human_message=human_msg,
            quote_total_paise=0,
            payment_link=None,
            grant_id=None,
            receipt=None,
            deltas=[],
            recovery_applied=False,
            provider_mode="simulated",
            razorpay_action_called=False,
        )

    # 6. Authoritative quote validation & CAS mark
    if quote_id:
        persisted_quote = store.get_commerce_quote(quote_id)
        if not persisted_quote or persisted_quote["buyer_agent_id"] != principals.buyer.buyer_agent_id:
            if is_http:
                raise HTTPException(404, f"Quote {quote_id} not found")
            return CheckoutResult(
                attempt_id=attempt_id,
                envelope_id=envelope_id,
                outcome="STOPPED_BEFORE_RAZORPAY",
                stages=[],
                allowed=False,
                code="QUOTE_NOT_FOUND",
                human_message="Quote not found or unowned",
                quote_total_paise=0,
                payment_link=None,
                grant_id=None,
                receipt=None,
                deltas=[],
                recovery_applied=False,
                provider_mode="simulated",
                razorpay_action_called=False,
                error=f"Quote {quote_id} not found",
            )
        if time.time() > persisted_quote["valid_until"]:
            if is_http:
                raise HTTPException(409, "Quote has expired. Fresh quote required.")
            return CheckoutResult(
                attempt_id=attempt_id,
                envelope_id=envelope_id,
                outcome="STOPPED_BEFORE_RAZORPAY",
                stages=[],
                allowed=False,
                code="QUOTE_EXPIRED",
                human_message="Quote has expired. Fresh quote required.",
                quote_total_paise=0,
                payment_link=None,
                grant_id=None,
                receipt=None,
                deltas=[],
                recovery_applied=False,
                provider_mode="simulated",
                razorpay_action_called=False,
                error="Quote has expired. Fresh quote required.",
            )
        if persisted_quote["catalog_revision"] != CATALOG_REVISION:
            if is_http:
                raise HTTPException(409, "Catalog revision changed. REQUOTE_REQUIRED.")
            return CheckoutResult(
                attempt_id=attempt_id,
                envelope_id=envelope_id,
                outcome="STOPPED_BEFORE_RAZORPAY",
                stages=[],
                allowed=False,
                code="REQUOTE_REQUIRED",
                human_message="Catalog revision has changed since quote was generated. REQUOTE_REQUIRED.",
                quote_total_paise=0,
                payment_link=None,
                grant_id=None,
                receipt=None,
                deltas=[],
                recovery_applied=False,
                provider_mode="simulated",
                razorpay_action_called=False,
                error="Catalog revision has changed since quote was generated. REQUOTE_REQUIRED.",
            )
        if persisted_quote.get("checked_out_at") is not None:
            if is_http:
                raise HTTPException(409, "Quote has already been checked out")
            return CheckoutResult(
                attempt_id=attempt_id,
                envelope_id=envelope_id,
                outcome="STOPPED_BEFORE_RAZORPAY",
                stages=[],
                allowed=False,
                code="QUOTE_ALREADY_CHECKED_OUT",
                human_message="Quote has already been checked out. Replay blocked.",
                quote_total_paise=0,
                payment_link=None,
                grant_id=None,
                receipt=None,
                deltas=[],
                recovery_applied=False,
                provider_mode="simulated",
                razorpay_action_called=False,
                error="Quote has already been checked out. Replay blocked.",
            )

        # Pre-flight channel policy evaluation on MCP path
        if not is_http:
            authoritative_amount_paise = persisted_quote["total_paise"]
            persisted_cart = (
                Cart.model_validate_json(persisted_quote["cart_json"])
                if persisted_quote.get("cart_json")
                else None
            )
            channel_dec = evaluate_channel_policy(
                merchant_id=envelope.merchant_id,
                cart=persisted_cart,
                amount_paise=authoritative_amount_paise,
                action_name="create_payment_link",
            )
            if not channel_dec.allowed:
                return CheckoutResult(
                    attempt_id=attempt_id,
                    envelope_id=envelope_id,
                    outcome="STOPPED_BEFORE_RAZORPAY",
                    stages=[],
                    allowed=False,
                    code=channel_dec.code,
                    human_message=channel_dec.reason,
                    quote_total_paise=0,
                    payment_link=None,
                    grant_id=None,
                    receipt=None,
                    deltas=[],
                    recovery_applied=False,
                    provider_mode="simulated",
                    razorpay_action_called=False,
                )

        if not store.mark_commerce_quote_checked_out(quote_id, attempt_id):
            if is_http:
                raise HTTPException(409, "Quote has already been checked out")
            return CheckoutResult(
                attempt_id=attempt_id,
                envelope_id=envelope_id,
                outcome="STOPPED_BEFORE_RAZORPAY",
                stages=[],
                allowed=False,
                code="QUOTE_ALREADY_CHECKED_OUT",
                human_message="Quote was concurrently checked out. Replay blocked.",
                quote_total_paise=0,
                payment_link=None,
                grant_id=None,
                receipt=None,
                deltas=[],
                recovery_applied=False,
                provider_mode="simulated",
                razorpay_action_called=False,
                error="Quote was concurrently checked out. Replay blocked.",
            )

    # 7. Autopilot Execution
    exp_version = (
        expected_envelope_version
        if expected_envelope_version is not None
        else envelope.version
    )
    exp_hash = expected_envelope_hash or envelope.envelope_hash

    sess_id = (
        principals.shopper.shopper_session_id
        if len(principals.shopper.shopper_session_id) >= 8
        else f"session_{principals.shopper.shopper_session_id}"
    )

    scen = (
        scenario
        if scenario is not None
        else demo_scenario.get_active_scenario()
    )
    scenario_enum = (
        AutopilotScenario(scen)
        if isinstance(scen, str)
        else (scen or AutopilotScenario.NORMAL)
    )

    exec_req = AutopilotExecuteRequest(
        envelope_id=envelope_id,
        expected_envelope_version=exp_version,
        expected_envelope_hash=exp_hash,
        session_id=sess_id,
        purchase_attempt_id=attempt_id,
        scenario=scenario_enum,
    )

    try:
        res = autopilot.execute(exec_req)
    except ValueError as exc:
        if is_http:
            raise HTTPException(409, str(exc)) from exc
        return CheckoutResult(
            attempt_id=attempt_id,
            envelope_id=envelope_id,
            outcome="STOPPED_BEFORE_RAZORPAY",
            stages=[],
            allowed=False,
            code="EXECUTION_CONFLICT",
            human_message=str(exc),
            quote_total_paise=0,
            payment_link=None,
            grant_id=None,
            receipt=None,
            deltas=[],
            recovery_applied=False,
            provider_mode="simulated",
            razorpay_action_called=False,
            error=str(exc),
        )
    except LookupError as exc:
        if is_http:
            raise HTTPException(404, str(exc)) from exc
        return CheckoutResult(
            attempt_id=attempt_id,
            envelope_id=envelope_id,
            outcome="STOPPED_BEFORE_RAZORPAY",
            stages=[],
            allowed=False,
            code="ENVELOPE_NOT_FOUND",
            human_message=str(exc),
            quote_total_paise=0,
            payment_link=None,
            grant_id=None,
            receipt=None,
            deltas=[],
            recovery_applied=False,
            provider_mode="simulated",
            razorpay_action_called=False,
            error=str(exc),
        )

    # 8. Stages & Outcome Classification
    auth_status = "completed" if res.envelope_decision.allowed else "blocked"
    action_status = (
        "completed"
        if res.action_status == "action_issued"
        else "unknown"
        if res.action_status == "unknown"
        else "blocked"
    )

    quote_total_paise = (
        res.envelope_decision.quote_total_paise
        if hasattr(res.envelope_decision, "quote_total_paise") and res.envelope_decision.quote_total_paise is not None
        else (res.quote.cart.total_paise if res.quote and res.quote.cart else 0)
    )

    stages = [
        CommerceAttemptStage(
            stage="understand",
            name="Draft Intent",
            status="completed",
            detail="Intent translated to Purchase Envelope",
        ),
        CommerceAttemptStage(
            stage="quote",
            name="Server Quote",
            status="completed",
            detail=f"Quote rehydrated: {quote_total_paise / 100:.2f} INR",
        ),
        CommerceAttemptStage(
            stage="authorize",
            name="Authority Gate",
            status=auth_status,
            detail=res.envelope_decision.code,
        ),
        CommerceAttemptStage(
            stage="razorpay_action",
            name="Razorpay Action",
            status=action_status,
            detail=f"Provider state: {res.action_status or 'none'}",
        ),
    ]

    recovery_applied = bool(
        res.recovery_applied
        if hasattr(res, "recovery_applied")
        else (res.quote and len(res.quote.substitutions) > 0)
    )
    razorpay_called = bool(
        res.payment_link or res.action_status in ("action_issued", "unknown")
    )

    if res.action_status == "action_issued":
        outcome = "RECOVERED_INSIDE_ENVELOPE" if recovery_applied else "ACTION_ISSUED"
    elif res.action_status == "unknown":
        outcome = "UNKNOWN"
    elif not res.envelope_decision.allowed:
        outcome = (
            "POLICY_DELTA_REQUIRED"
            if res.envelope_decision.deltas
            else "STOPPED_BEFORE_RAZORPAY"
        )
    else:
        outcome = "READY_FOR_CHECKOUT"

    order_status = (
        "issued"
        if res.action_status == "action_issued"
        else "unknown"
        if res.action_status == "unknown"
        else "blocked"
    )

    # 9. Record Agent Order
    record_agent_order(
        purchase_attempt_id=attempt_id,
        merchant_id=envelope.merchant_id,
        buyer_agent_id=principals.buyer.buyer_agent_id,
        shopper_session_id=principals.shopper.shopper_session_id,
        status=order_status,
        outcome=outcome,
        amount_paise=quote_total_paise,
        envelope_id=envelope.id,
        recovery_applied=recovery_applied,
        payment_link=res.payment_link,
        grant_id=res.grant_id,
        receipt_id=res.receipt.grant_id if res.receipt else None,
        code=res.envelope_decision.code,
    )

    result = CheckoutResult(
        attempt_id=attempt_id,
        envelope_id=envelope_id,
        outcome=outcome,
        stages=stages,
        allowed=res.envelope_decision.allowed,
        code=res.envelope_decision.code,
        human_message=res.envelope_decision.human_message,
        quote_total_paise=quote_total_paise,
        payment_link=res.payment_link,
        grant_id=res.grant_id,
        receipt=res.receipt,
        deltas=res.envelope_decision.deltas,
        recovery_applied=recovery_applied,
        provider_mode=res.provider_mode,
        razorpay_action_called=razorpay_called,
    )

    # 10. Record Successful Request Cache
    if body_data:
        record_successful_request(
            agent_request_id=attempt_id,
            merchant_id=envelope.merchant_id,
            buyer_agent_id=principals.buyer.buyer_agent_id,
            shopper_session_id=principals.shopper.shopper_session_id,
            body_data=body_data,
            response_data=result.to_http_response().model_dump(mode="json"),
        )

    return result
