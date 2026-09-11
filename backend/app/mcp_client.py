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
        try:
            self._post("notifications/initialized")
        except Exception:
            pass
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
        if get_active_provider_mode() == "razorpay_rest":
            rest_client = RazorpayRESTClient()
            return rest_client.call_tool(name, args, grant_id, context, cart_hash)

        if not self.session_id:
            try:
                self.initialize()
            except Exception as exc:
                # If Remote MCP auth fails, rate-limits (429), or is unreachable, fallback to REST
                is_fallback_error = False
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403, 429, 500, 502, 503, 504):
                    is_fallback_error = True
                elif any(phrase in str(exc) for phrase in ("Authentication failed", "401", "403", "429", "Too Many Requests", "ConnectError", "timeout")):
                    is_fallback_error = True

                if is_fallback_error:
                    trigger_provider_fallback(f"Remote MCP unavailable ({exc}); falling back to razorpay_rest")
                    rest_client = RazorpayRESTClient()
                    return rest_client.call_tool(name, args, grant_id, context, cart_hash)

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
        if get_active_provider_mode() == "razorpay_rest":
            return RazorpayRESTClient().fetch_action_status(provider_ref)
        if not self.session_id:
            try:
                self.initialize()
            except Exception as exc:
                trigger_provider_fallback(f"Remote MCP unavailable ({exc}); falling back to razorpay_rest")
                return RazorpayRESTClient().fetch_action_status(provider_ref)
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


#: What each simulated link would have been, so the page this deployment serves
#: for it can show the real figures instead of a placeholder.
_SIMULATED_LINKS: dict[str, dict] = {}


def simulated_link_record(payment_link_id: str) -> dict | None:
    return _SIMULATED_LINKS.get(payment_link_id)


def simulated_payment_link_url(payment_link_id: str) -> str:
    """A link for the simulated provider that this deployment actually serves.

    This used to return `https://rzp.io/i/<8 random hex>`. That is Razorpay's
    real short-link domain, and eight hex characters is a small enough space
    that a fabricated path can collide with a genuine, live payment link
    belonging to someone else — so clicking a "simulated" link could land a
    viewer on a stranger's real payment page and invite them to pay it.

    A simulated provider must never mint URLs on a domain it does not own. This
    one points at this backend, which serves a page saying exactly what would
    have been created and that no provider was called.
    """
    from .config import get_settings

    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/simulated/payment-link/{payment_link_id}"


def reset_simulated_provider() -> None:
    _SIMULATED_PROVIDER.clear()
    _SIMULATED_LINKS.clear()


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
            _SIMULATED_LINKS[payment_link_id] = {
                "id": payment_link_id,
                "amount": canonical.args["amount"],
                "currency": "INR",
                "description": canonical.args["description"],
                "reference_id": canonical.args.get("reference_id"),
                "notes": canonical.args.get("notes", {}),
                "grant_id": grant.id,
                "created_at": time.time(),
            }
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
                                "short_url": simulated_payment_link_url(payment_link_id),
                                "description": canonical.args["description"],
                            }
                        ),
                    }
                ]
            }
            return _persist_issued_or_unknown(grant.id, token, result)
        if name == "refund":
            refund_id = f"rfnd_{uuid.uuid4().hex[:14]}"
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "id": refund_id,
                                "payment_id": canonical.args["payment_id"],
                                "amount": canonical.args["amount"],
                                "currency": "INR",
                                "status": "processed",
                                "speed_processed": canonical.args.get("speed", "normal"),
                                "receipt": canonical.args.get("receipt", ""),
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


class RazorpayRESTClient:
    """Direct Razorpay REST client using official Test Mode API keys.

    Targets:
      - POST https://api.razorpay.com/v1/payment_links
      - GET  https://api.razorpay.com/v1/payment_links/{id}

    Enforces the identical atomic authorization, exact-bound Action Grant claiming,
    and unknown-outcome boundary as RazorpayMCPClient.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.key_id = settings.razorpay_key_id
        self.key_secret = settings.razorpay_key_secret
        if not (self.key_id and self.key_secret):
            raise RuntimeError(
                "PAYMENT_PROVIDER=razorpay_rest requires both RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET"
            )
        self.base_url = "https://api.razorpay.com/v1"

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "create_payment_link",
                "description": "Issue a Razorpay Standard Payment Link via REST API",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "amount": {"type": "integer"},
                        "currency": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["amount", "currency", "description"],
                },
            },
            {
                "name": "refund",
                "description": "Issue a refund against a payment via REST API",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "payment_id": {"type": "string"},
                        "amount": {"type": "integer"},
                        "currency": {"type": "string"},
                    },
                    "required": ["payment_id", "amount", "currency"],
                },
            },
        ]

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

        if name == "create_payment_link":
            payload = {
                "amount": canonical.args["amount"],
                "currency": canonical.args.get("currency", "INR"),
                "description": canonical.args.get("description", "Agent Purchase"),
                "notes": {
                    "grant_id": grant.id,
                    "merchant_id": getattr(context, "merchant_id", "merchant_freshbasket"),
                    "agent_id": getattr(context, "agent_id", "buyer_agent"),
                    "session_id": getattr(context, "session_id", ""),
                },
            }
            endpoint_url = f"{self.base_url}/payment_links"
        elif name == "refund":
            payment_id = canonical.args["payment_id"]
            payload = {
                "amount": canonical.args["amount"],
                "speed": canonical.args.get("speed", "normal"),
                "receipt": canonical.args.get("receipt", f"rcpt_{grant.id[:12]}"),
                "notes": {
                    "grant_id": grant.id,
                    "merchant_id": getattr(context, "merchant_id", "merchant_freshbasket"),
                    "agent_id": getattr(context, "agent_id", "buyer_agent"),
                    "session_id": getattr(context, "session_id", ""),
                },
            }
            endpoint_url = f"{self.base_url}/payments/{payment_id}/refund"
        else:
            store.cancel_action_grant(grant_id, "UNSUPPORTED_REST_ACTION")
            raise MandateViolation(f"Action '{name}' is not supported via REST client")

        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(
                    endpoint_url,
                    json=payload,
                    auth=(self.key_id, self.key_secret),
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 401, 403, 422, 429):
                is_quota = (
                    exc.response.status_code == 429
                    or "limit of 30" in exc.response.text.lower()
                    or "quota" in exc.response.text.lower()
                )
                if is_quota and settings.demo_mode:
                    trigger_provider_fallback(
                        "Razorpay Test Mode 30-link quota exceeded; falling back to simulated provider",
                        target="simulated",
                    )
                    if name == "create_payment_link":
                        payment_link_id = f"plink_sim_{uuid.uuid4().hex[:12]}"
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
                                            "short_url": simulated_payment_link_url(payment_link_id),
                                            "description": canonical.args.get("description", "Agent Purchase"),
                                        }
                                    ),
                                }
                            ]
                        }
                        return _persist_issued_or_unknown(grant.id, token, result)
                    elif name == "refund":
                        refund_id = f"rfnd_{uuid.uuid4().hex[:14]}"
                        result = {
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(
                                        {
                                            "id": refund_id,
                                            "payment_id": canonical.args["payment_id"],
                                            "amount": canonical.args["amount"],
                                            "currency": "INR",
                                            "status": "processed",
                                            "speed_processed": canonical.args.get("speed", "normal"),
                                            "receipt": canonical.args.get("receipt", ""),
                                        }
                                    ),
                                }
                            ]
                        }
                        return _persist_issued_or_unknown(grant.id, token, result)

                store.cancel_action_grant(grant.id, f"PROVIDER_HTTP_{exc.response.status_code}")
                try:
                    err_desc = exc.response.json().get("error", {}).get("description", exc.response.text)
                except Exception:
                    err_desc = exc.response.text
                raise MandateViolation(
                    f"Razorpay rejected request ({exc.response.status_code}): {err_desc}"
                ) from exc
            store.mark_action_unknown(grant.id, token, type(exc).__name__)
            raise ActionOutcomeUnknown(
                grant.id,
                "Razorpay REST returned an ambiguous status; reconciliation required.",
            ) from exc
        except Exception as exc:
            store.mark_action_unknown(grant.id, token, type(exc).__name__)
            raise ActionOutcomeUnknown(
                grant.id,
                "Razorpay REST did not return a final result; reconciliation is required.",
            ) from exc

        if name == "refund":
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "id": data.get("id", f"rfnd_{uuid.uuid4().hex[:12]}"),
                                "payment_id": canonical.args["payment_id"],
                                "amount": data.get("amount", canonical.args["amount"]),
                                "currency": data.get("currency", "INR"),
                                "status": data.get("status", "processed"),
                                "speed_processed": data.get("speed_processed", "normal"),
                                "receipt": canonical.args.get("receipt", ""),
                            }
                        ),
                    }
                ]
            }
        else:
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "id": data.get("id"),
                                "amount": data.get("amount"),
                                "currency": data.get("currency", "INR"),
                                "status": data.get("status", "created"),
                                "short_url": data.get("short_url"),
                                "description": data.get("description"),
                            }
                        ),
                    }
                ]
            }
        return _persist_issued_or_unknown(grant.id, token, result)

    def fetch_action_status(self, provider_ref: str) -> dict:
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(
                    f"{self.base_url}/payment_links/{provider_ref}",
                    auth=(self.key_id, self.key_secret),
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            pass
        return {"id": provider_ref, "status": "unknown"}


_ACTIVE_PROVIDER: str | None = None
_FALLBACK_REASON: str | None = None


def get_active_provider_mode() -> str:
    global _ACTIVE_PROVIDER
    if _ACTIVE_PROVIDER:
        return _ACTIVE_PROVIDER
    return get_settings().payment_provider


def get_provider_fallback_info() -> dict[str, str | None]:
    return {
        "active_provider": get_active_provider_mode(),
        "configured_provider": get_settings().payment_provider,
        "fallback_reason": _FALLBACK_REASON,
    }


def trigger_provider_fallback(reason: str, target: str = "razorpay_rest") -> None:
    global _ACTIVE_PROVIDER, _FALLBACK_REASON
    if _ACTIVE_PROVIDER != target:
        _ACTIVE_PROVIDER = target
        _FALLBACK_REASON = reason
        print(f"[provider-fallback] Switched payment provider to {target}: {reason}")


def reset_provider_fallback() -> None:
    global _ACTIVE_PROVIDER, _FALLBACK_REASON
    _ACTIVE_PROVIDER = None
    _FALLBACK_REASON = None


def get_client():
    settings = get_settings()
    provider = get_active_provider_mode()

    if provider == "simulated":
        return SimulatedMCPClient()

    if provider == "razorpay_rest":
        has_key_pair = bool(settings.razorpay_key_id and settings.razorpay_key_secret)
        if not has_key_pair:
            raise RuntimeError(
                "PAYMENT_PROVIDER=razorpay_rest requires both RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET"
            )
        return RazorpayRESTClient()

    if provider == "razorpay_mcp":
        has_token = bool(settings.razorpay_mcp_token)
        has_key_pair = bool(settings.razorpay_key_id and settings.razorpay_key_secret)
        if not (has_token or has_key_pair):
            raise RuntimeError(
                "PAYMENT_PROVIDER=razorpay_mcp requires RAZORPAY_MCP_TOKEN or "
                "both RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET"
            )
        return RazorpayMCPClient()

    raise ValueError(f"Unknown payment provider: {provider}")

