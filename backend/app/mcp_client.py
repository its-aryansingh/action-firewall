"""Fail-closed Razorpay MCP actuator.

Only actions in the local registry are reachable. Every state-changing call
must atomically claim one exact-bound, server-side authorization grant.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx

from . import store
from .actions import (
    ACTION_REGISTRY,
    ActionNotRegistered,
    InvalidActionArguments,
    canonicalize_action,
)
from .config import get_settings
from .models import ActionContext


class MandateViolation(RuntimeError):
    """Raised before dispatch when an exact action grant is invalid."""


class ActionInProgress(MandateViolation):
    """The purchase attempt is dispatching or awaiting reconciliation."""


class ActionOutcomeUnknown(RuntimeError):
    """The provider request may have succeeded, so automatic retry is unsafe."""

    def __init__(self, grant_id: str, message: str) -> None:
        super().__init__(message)
        self.grant_id = grant_id


class RazorpayMCPClient:
    """Minimal MCP Streamable HTTP client with an exact-action boundary."""

    def __init__(self) -> None:
        settings = get_settings()
        self.url = settings.razorpay_mcp_url
        self.headers = {
            "Authorization": settings.mcp_auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self.session_id: str | None = None
        self._id = 0

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _post(self, method: str, params: dict | None = None) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        with httpx.Client(timeout=45.0) as client:
            response = client.post(self.url, json=payload, headers=headers)
            response.raise_for_status()
            if "Mcp-Session-Id" in response.headers:
                self.session_id = response.headers["Mcp-Session-Id"]
            body = _parse_body(response)
        if "error" in body:
            raise RuntimeError(f"MCP error on {method}: {body['error']}")
        return body.get("result", {})

    def initialize(self) -> dict:
        result = self._post(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "action-firewall", "version": "2.0.0"},
            },
        )
        self._post("notifications/initialized")
        return result

    def list_tools(self) -> list[dict]:
        return self._post("tools/list").get("tools", [])

    def _raw_call(self, name: str, args: dict) -> dict:
        return self._post("tools/call", {"name": name, "arguments": args})

    def call_tool(
        self,
        name: str,
        args: dict,
        grant_id: str,
        context: ActionContext,
        cart_hash: str,
    ) -> dict:
        canonical = _canonical_or_block(name, args, grant_id)
        if not self.session_id:
            try:
                self.initialize()
            except Exception:
                store.cancel_action_grant(grant_id, "MCP_INITIALIZATION_FAILED")
                raise
        grant, token = _claim_or_raise(canonical, grant_id, context, cart_hash)
        try:
            result = self._raw_call(name, canonical.args)
        except Exception as exc:
            store.mark_action_unknown(grant.id, token, type(exc).__name__)
            raise ActionOutcomeUnknown(
                grant.id,
                "Razorpay did not return a final result; reconciliation is required.",
            ) from exc
        return _persist_issued_or_unknown(grant.id, token, result)


    def fetch_action_status(self, provider_ref: str) -> dict:
        """Read the provider's own view of an issued action.

        Read-only and not a registered money action, so it does not pass
        through the grant boundary: there is nothing to authorize. It is the
        only source we accept for a settlement claim.
        """
        if not self.session_id:
            self.initialize()
        raw = self._raw_call("fetch_payment_link", {"payment_link_id": provider_ref})
        payload = unwrap(raw)
        return payload if isinstance(payload, dict) else {"status": "unknown"}


#: Simulated provider-side state, keyed by payment link id. Module level
#: because get_client() constructs a fresh client per call. Only the demo
#: script and the tests may write to it - nothing on the HTTP surface can,
#: which is what keeps "settled" an observation rather than an assertion.
_SIMULATED_PROVIDER: dict[str, dict] = {}


def simulate_provider_payment(payment_link_id: str, amount_paise: int) -> None:
    """TEST AND DEMO ONLY. Mark a simulated payment link as paid.

    Stands in for a shopper actually paying the link with the test-mode UPI
    handle. It is deliberately a Python-level helper, not an endpoint.
    """
    _SIMULATED_PROVIDER[payment_link_id] = {
        "id": payment_link_id,
        "status": "paid",
        "amount": amount_paise,
        "amount_paid": amount_paise,
        "currency": "INR",
    }


def reset_simulated_provider() -> None:
    _SIMULATED_PROVIDER.clear()


class SimulatedMCPClient:
    """Offline adapter with the same exact grant boundary as the live client."""

    def __init__(self, failure_mode: str | None = None) -> None:
        self.calls: list[dict] = []
        self.failure_mode = failure_mode

    def initialize(self) -> dict:
        return {"serverInfo": {"name": "razorpay-mcp (simulated)", "version": "2.0"}}

    def list_tools(self) -> list[dict]:
        return [
            {"name": name, "description": f"simulated registered action {name}"}
            for name in sorted(ACTION_REGISTRY)
        ]

    def fetch_action_status(self, provider_ref: str) -> dict:
        """Mirror of the live read. Defaults to an unpaid link."""
        return _SIMULATED_PROVIDER.get(
            provider_ref,
            {"id": provider_ref, "status": "created", "amount_paid": 0},
        )

    def call_tool(
        self,
        name: str,
        args: dict,
        grant_id: str,
        context: ActionContext,
        cart_hash: str,
    ) -> dict:
        canonical = _canonical_or_block(name, args, grant_id)
        grant, token = _claim_or_raise(canonical, grant_id, context, cart_hash)
        self.calls.append({"name": name, "args": canonical.args, "ts": time.time()})
        if self.failure_mode == "timeout_after_dispatch":
            store.mark_action_unknown(grant.id, token, "SIMULATED_TIMEOUT")
            raise ActionOutcomeUnknown(
                grant.id,
                "Simulated provider timeout after dispatch.",
            )
        if name == "create_payment_link":
            payment_link_id = f"plink_{uuid.uuid4().hex[:14]}"
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "id": payment_link_id,
                                "amount": canonical.args["amount"],
                                "currency": "INR",
                                "status": "created",
                                "short_url": f"https://rzp.io/i/{uuid.uuid4().hex[:8]}",
                                "description": canonical.args["description"],
                            }
                        ),
                    }
                ]
            }
            return _persist_issued_or_unknown(grant.id, token, result)
        store.mark_action_unknown(grant.id, token, "SIMULATOR_ACTION_UNHANDLED")
        raise ActionOutcomeUnknown(grant.id, "Simulated action outcome is unknown.")


def _canonical_or_block(name: str, args: dict, grant_id: str):
    try:
        return canonicalize_action(name, args)
    except (ActionNotRegistered, InvalidActionArguments) as exc:
        store.cancel_action_grant(grant_id, type(exc).__name__.upper())
        raise MandateViolation(str(exc)) from exc


def _claim_or_raise(canonical, grant_id: str, context: ActionContext, cart_hash: str):
    grant, token, reason = store.claim_action_grant(
        grant_id,
        context=context,
        action_name=canonical.name,
        action_schema_hash=canonical.schema_hash,
        args=canonical.args,
        cart_hash=cart_hash,
    )
    if not token:
        # ALREADY_ISSUED belongs with the in-progress family, not with binding
        # mismatches. The action succeeded; this is a duplicate dispatch of a
        # spent grant. Reporting it as MandateViolation told the shopper their
        # action "no longer matches its authorization receipt" and wrote a
        # BLOCKED row for a call that had in fact gone through - a false entry
        # in the one record this system exists to keep honest.
        if reason in ("ACTION_IN_PROGRESS", "UNKNOWN_OUTCOME", "ALREADY_ISSUED"):
            raise ActionInProgress(reason)
        raise MandateViolation(reason)
    return grant, token


def _persist_issued_or_unknown(grant_id: str, token: str, result: dict) -> dict:
    try:
        payload = unwrap(result)
        provider_ref = payload.get("id") if isinstance(payload, dict) else None
        store.mark_action_issued(
            grant_id,
            token,
            provider_ref=provider_ref,
            result=result,
        )
        return result
    except Exception as exc:
        current = store.get_action_grant(grant_id)
        if current and current.state.value == "dispatching":
            store.mark_action_unknown(grant_id, token, type(exc).__name__)
        raise ActionOutcomeUnknown(
            grant_id,
            "The provider may have accepted the action, but local confirmation failed.",
        ) from exc


def _parse_body(response: httpx.Response) -> dict:
    """Streamable HTTP may answer with JSON or an SSE frame."""
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        for line in response.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return {}
    return response.json() if response.content else {}


def unwrap(result: dict) -> Any:
    """Return the first decoded text content block from an MCP result."""
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                return json.loads(block["text"])
            except json.JSONDecodeError:
                return block["text"]
    return result


def get_client():
    settings = get_settings()
    if settings.payment_provider == "simulated":
        return SimulatedMCPClient()
    has_token = bool(settings.razorpay_mcp_token)
    has_key_pair = bool(settings.razorpay_key_id and settings.razorpay_key_secret)
    if not (has_token or has_key_pair):
        raise RuntimeError(
            "PAYMENT_PROVIDER=razorpay_mcp requires RAZORPAY_MCP_TOKEN or "
            "both RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET"
        )
    return RazorpayMCPClient()
