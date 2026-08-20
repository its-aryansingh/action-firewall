"""Razorpay Remote MCP client (Module 3).

We do NOT hand-roll Razorpay REST calls. The agent talks to
https://mcp.razorpay.com/mcp over MCP Streamable HTTP with a
`Authorization: Basic base64(key_id:key_secret)` header, exactly as the
`npx mcp-remote` bridge does, and calls the published tools
(create_payment_link, capture_payment, fetch_payment, ...).

Every call funnels through `call_tool`, which refuses to run unless it is
handed an ALLOWED MandateDecision. There is no second code path to money.
"""
from __future__ import annotations
import json, time, uuid
from typing import Any

import httpx

from .config import get_settings
from .models import MandateDecision


class MandateViolation(RuntimeError):
    """Raised if anything tries to reach a money tool without a passing decision."""


MONEY_TOOLS = {"create_payment_link", "capture_payment", "create_order",
               "create_refund", "create_payment_link_upi"}


class RazorpayMCPClient:
    """Minimal MCP Streamable HTTP client — initialize -> tools/list -> tools/call."""

    def __init__(self) -> None:
        s = get_settings()
        self.url = s.razorpay_mcp_url
        self.headers = {
            "Authorization": s.mcp_auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self.session_id: str | None = None
        self._id = 0

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _post(self, method: str, params: dict | None = None) -> dict:
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method,
                   "params": params or {}}
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        with httpx.Client(timeout=45.0) as client:
            r = client.post(self.url, json=payload, headers=headers)
            r.raise_for_status()
            if "Mcp-Session-Id" in r.headers:
                self.session_id = r.headers["Mcp-Session-Id"]
            body = _parse_body(r)
        if "error" in body:
            raise RuntimeError(f"MCP error on {method}: {body['error']}")
        return body.get("result", {})

    def initialize(self) -> dict:
        res = self._post("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "uap-mandate-agent", "version": "1.0.0"},
        })
        self._post("notifications/initialized")
        return res

    def list_tools(self) -> list[dict]:
        return self._post("tools/list").get("tools", [])

    def _raw_call(self, name: str, args: dict) -> dict:
        return self._post("tools/call", {"name": name, "arguments": args})

    def call_tool(self, name: str, args: dict, decision: MandateDecision) -> dict:
        """The ONLY entry point to a Razorpay tool."""
        if name in MONEY_TOOLS and not decision.allowed:
            raise MandateViolation(
                f"Blocked '{name}': mandate decision {decision.code.value}")
        if not self.session_id:
            self.initialize()
        return self._raw_call(name, args)


class SimulatedMCPClient:
    """DEMO_MODE stand-in. Same signature, same mandate gate, no live money.
    Lets you rehearse the demo on a plane and lets CI run without secrets."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def initialize(self) -> dict:
        return {"serverInfo": {"name": "razorpay-mcp (simulated)", "version": "2.0"}}

    def list_tools(self) -> list[dict]:
        return [{"name": n, "description": f"simulated {n}"} for n in sorted(MONEY_TOOLS)]

    def call_tool(self, name: str, args: dict, decision: MandateDecision) -> dict:
        if name in MONEY_TOOLS and not decision.allowed:
            raise MandateViolation(
                f"Blocked '{name}': mandate decision {decision.code.value}")
        self.calls.append({"name": name, "args": args, "ts": time.time()})
        if name == "create_payment_link":
            pid = f"plink_{uuid.uuid4().hex[:14]}"
            return {"content": [{"type": "text", "text": json.dumps({
                "id": pid, "amount": args.get("amount"), "currency": "INR",
                "status": "created",
                "short_url": f"https://rzp.io/i/{uuid.uuid4().hex[:8]}",
                "description": args.get("description", ""),
            })}]}
        if name == "capture_payment":
            return {"content": [{"type": "text", "text": json.dumps({
                "id": args.get("payment_id", f"pay_{uuid.uuid4().hex[:14]}"),
                "amount": args.get("amount"), "currency": "INR", "status": "captured",
            })}]}
        return {"content": [{"type": "text", "text": json.dumps({"ok": True, "tool": name})}]}


def _parse_body(r: httpx.Response) -> dict:
    """Streamable HTTP may answer with JSON or with an SSE frame."""
    ctype = r.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        for line in r.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return {}
    return r.json() if r.content else {}


def unwrap(result: dict) -> Any:
    """MCP tool results arrive as content blocks; give callers the payload."""
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                return json.loads(block["text"])
            except json.JSONDecodeError:
                return block["text"]
    return result


def get_client():
    s = get_settings()
    if s.demo_mode or not (s.razorpay_mcp_token or s.razorpay_key_secret):
        return SimulatedMCPClient()
    return RazorpayMCPClient()
