"""The single-agent orchestrator.

Razorpay's own FTX26 position is that one well-instrumented agent with full
context beats a multi-agent swarm for commerce: fewer handoff failure modes,
predictable latency, one auditable trace. So this is deliberately ONE agent
with a fixed, inspectable pipeline:

    retrieve_catalog -> plan_cart -> mandate_check -> mcp_tool_call

The LLM only ever produces a *proposal* (which SKUs, what quantity, what to
say). Money is gated by `mandate.verify_for_agent`, which is deterministic
and unit-tested. An LLM that hallucinates cannot spend money here.
"""
from __future__ import annotations
import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from . import catalog, store
from .config import get_settings
from .mandate import rupees, suggest_downgrade, verify_for_agent
from .mcp_client import MandateViolation, get_client, unwrap
from .models import (Cart, CartLine, ChatRequest, ChatResponse, DecisionCode,
                     ToolInvocation)
from .observability import Trace

SYSTEM_PROMPT = """You are a Razorpay agentic-commerce shopping assistant.

You help a human buy groceries and household goods in chat. You may ONLY
choose products from the RETRIEVED CATALOG given to you — never invent a SKU
or a price.

You do not decide whether a payment is permitted. A separate deterministic
Mandate Verification Layer enforces the human's authorised spending ceiling
and will hard-block you. Never claim a payment succeeded unless the tool
result says so.

Reply with JSON only:
{
  "reply": "<what you say to the shopper, warm and brief>",
  "cart_ops": [{"op": "add"|"remove"|"clear", "sku": "...", "qty": 1}],
  "intent": "discover" | "checkout"
}
Set intent to "checkout" only when the shopper clearly asks to pay, order,
buy or confirm. Cross-sell at most one relevant item, naturally, in `reply`.
"""

CHECKOUT_WORDS = ("checkout", "check out", "buy", "pay", "order it", "place the order",
                  "confirm", "purchase", "proceed", "book it", "done")


@dataclass
class Session:
    session_id: str
    user_id: str
    agent_id: str
    cart: Cart = field(default_factory=Cart)
    history: list[dict] = field(default_factory=list)


_SESSIONS: dict[str, Session] = {}


def get_session(req: ChatRequest) -> Session:
    s = _SESSIONS.get(req.session_id)
    if not s:
        s = Session(req.session_id, req.user_id, req.agent_id)
        _SESSIONS[req.session_id] = s
    return s


def reset_session(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------
def _llm_plan(message: str, retrieved: list[dict], cart: Cart,
              history: list[dict]) -> dict | None:
    s = get_settings()
    if not s.openai_api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=s.openai_api_key)
        ctx = {
            "retrieved_catalog": [
                {"sku": p["sku"], "name": p["name"], "category": p["category"],
                 "price_rupees": p["price_paise"] / 100, "tags": p.get("tags", [])}
                for p in retrieved
            ],
            "current_cart": [
                {"sku": l.sku, "name": l.name, "qty": l.qty,
                 "line_total_rupees": l.line_total_paise / 100} for l in cart.lines
            ],
            "cart_total_rupees": cart.total_paise / 100,
        }
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        msgs += history[-6:]
        msgs.append({"role": "user",
                     "content": f"CONTEXT:\n{json.dumps(ctx)}\n\nSHOPPER: {message}"})
        resp = client.chat.completions.create(
            model=s.openai_model, messages=msgs, temperature=0.2,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as exc:  # pragma: no cover - network path
        print(f"[agent] LLM planning failed, using heuristic planner: {exc}")
        return None


@lru_cache
def _name_word_df() -> dict[str, int]:
    """How many catalog products use each word in their name."""
    df: dict[str, int] = {}
    for p in catalog.load_catalog():
        for w in set(re.findall(r"[a-z]+", p["name"].lower())):
            if len(w) > 2:
                df[w] = df.get(w, 0) + 1
    return df


def _mentioned_skus(message: str) -> list[str]:
    """Resolve explicit product mentions ("add the parmigiano") to SKUs.

    A product matches only if the shopper used at least one word UNIQUE to it.
    Matching on shared words alone is what made "the olive oil" also pull in
    Sunflower Oil: both contain "oil", but only one contains "olive". Requiring
    a discriminating word is the difference between an agent that knows what it
    is buying and one that is guessing.
    """
    low = message.lower()
    df = _name_word_df()
    hits: list[str] = []
    for p in sorted(catalog.load_catalog(), key=lambda p: -len(p["name"])):
        words = [w for w in re.findall(r"[a-z]+", p["name"].lower()) if len(w) > 2]
        matched = [w for w in words if w in low]
        if not matched:
            continue
        if min(df[w] for w in matched) > 1:
            continue        # only generic words matched — not a real reference
        if p["sku"] not in hits:
            hits.append(p["sku"])
    return hits


def _heuristic_plan(message: str, retrieved: list[dict], cart: Cart) -> dict:
    """Deterministic fallback so the demo always runs without an LLM key.

    Order matters: explicit mentions are resolved FIRST, independently of
    intent, so "add the parmigiano and check out" both adds and checks out.
    """
    low = message.lower()
    intent = "checkout" if any(w in low for w in CHECKOUT_WORDS) else "discover"
    removing = any(w in low for w in ("remove", "drop", "take out", "without", "delete"))
    ops: list[dict] = []
    in_cart = {l.sku for l in cart.lines}
    mentioned = _mentioned_skus(message)

    if "clear" in low or "empty the cart" in low:
        ops.append({"op": "clear"})
    elif removing:
        for sku in mentioned:
            if sku in in_cart:
                ops.append({"op": "remove", "sku": sku, "qty": 99})
    elif mentioned:
        ops += [{"op": "add", "sku": sku, "qty": 1}
                for sku in mentioned if sku not in in_cart]
    elif intent == "discover":
        ops += [{"op": "add", "sku": p["sku"], "qty": 1} for p in retrieved[:4]]

    added = [o["sku"] for o in ops if o.get("op") == "add"]
    removed = [o["sku"] for o in ops if o.get("op") == "remove"]

    if added:
        names = ", ".join(catalog.by_sku()[s]["name"] for s in added)
        extra = catalog.cross_sell(added + list(in_cart), 1)
        cs = (f" People usually add {extra[0]['name']} "
              f"({rupees(extra[0]['price_paise'])}) with this — want it?") if extra else ""
        reply = f"Added {names} to your cart.{cs}"
    elif removed:
        names = ", ".join(catalog.by_sku()[s]["name"] for s in removed)
        reply = f"Removed {names}."
    elif intent == "checkout":
        reply = "Sending this to checkout now."
    else:
        reply = "Tell me what you'd like to cook or buy and I'll put a cart together."

    if intent == "checkout" and (added or removed):
        reply += " Taking it to checkout."
    return {"reply": reply, "cart_ops": ops, "intent": intent}


def cart_idempotency_key(session_id: str, mandate_id: str, mandate_version: int,
                         cart: Cart) -> str:
    """Stable identity for one logical purchase attempt.

    Scoped to the SESSION as well as the basket. An earlier version keyed on
    (mandate, version, basket) alone, and a concurrency test caught it: two
    different shoppers buying the same item under one mandate produced the same
    key, so the second was silently handed the first one's payment link. Two
    identical baskets in two sessions are two purchases; the same basket
    re-submitted inside one session is a retry.

    Callers who can supply a real client-generated key should do so via
    ChatRequest.idempotency_key — this is only the fallback.
    """
    basket = sorted((l.sku, l.qty, l.unit_price_paise) for l in cart.lines)
    raw = json.dumps([session_id, mandate_id, mandate_version, basket],
                     separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _apply_ops(cart: Cart, ops: list[dict]) -> Cart:
    lines = {l.sku: l for l in cart.lines}
    for op in ops or []:
        kind = op.get("op")
        if kind == "clear":
            lines = {}
            continue
        sku = op.get("sku")
        product = catalog.by_sku().get(sku)
        if not product:
            continue  # hallucinated SKU: silently dropped, never priced
        qty = int(op.get("qty", 1) or 1)
        if kind == "add":
            if sku in lines:
                lines[sku].qty += qty
            else:
                lines[sku] = CartLine(sku=sku, name=product["name"],
                                      category=product["category"],
                                      unit_price_paise=product["price_paise"], qty=qty)
        elif kind == "remove":
            if sku in lines:
                lines[sku].qty -= qty
                if lines[sku].qty <= 0:
                    del lines[sku]
    return Cart(lines=list(lines.values()))


# --------------------------------------------------------------------------
# Turn
# --------------------------------------------------------------------------
def handle_turn(req: ChatRequest) -> ChatResponse:
    sess = get_session(req)
    trace = Trace(name="agentic-checkout-turn", session_id=req.session_id,
                  user_id=req.user_id, input=req.message)
    tools: list[ToolInvocation] = []

    # 1. RETRIEVE -------------------------------------------------------
    with trace.span("retrieve_catalog", input={"query": req.message}) as sp:
        retrieved = catalog.search(req.message, top_k=6)
        sp["output"] = [{"sku": p["sku"], "name": p["name"]} for p in retrieved]

    # 2. PLAN -----------------------------------------------------------
    with trace.span("plan_cart", input={"message": req.message}) as sp:
        plan = _llm_plan(req.message, retrieved, sess.cart, sess.history) \
            or _heuristic_plan(req.message, retrieved, sess.cart)
        sp["output"] = plan
    proposed = _apply_ops(sess.cart, plan.get("cart_ops", []))
    reply = plan.get("reply", "")
    intent = plan.get("intent", "discover")

    # 3. MANDATE CHECK — always, on every turn, before any money tool ----
    with trace.span("mandate_check", input={
            "cart_total_paise": proposed.total_paise,
            "skus": [l.sku for l in proposed.lines]}) as sp:
        decision = verify_for_agent(proposed, req.user_id, req.agent_id, req.session_id)
        sp["output"] = decision.model_dump(mode="json")
        sp["level"] = "DEFAULT" if decision.allowed else "WARNING"
        sp["status_message"] = decision.code.value
    trace.score("mandate_respected", 1.0 if not decision.is_breach else 0.0,
                comment=decision.code.value)

    # 4a. BLOCKED -> graceful failure, no MCP call ------------------------
    if not decision.allowed:
        sess.cart = proposed  # keep the cart visible so the block is legible
        reply = decision.human_message
        if decision.code in (DecisionCode.BLOCK_WINDOW_CAP_EXCEEDED,
                             DecisionCode.BLOCK_PER_TXN_CAP_EXCEEDED):
            fits = suggest_downgrade(proposed, decision)
            if fits and fits.lines and fits.total_paise < proposed.total_paise:
                dropped = [l.name for l in proposed.lines
                           if l.sku not in {k.sku for k in fits.lines}]
                reply += (f" Dropping {', '.join(dropped)} would bring it to "
                          f"{rupees(fits.total_paise)}.")
        tools.append(ToolInvocation(name="create_payment_link",
                                    args={"amount": proposed.total_paise},
                                    blocked=True))
        trace.event(name="mandate_breach_attempt",
                    metadata={"code": decision.code.value,
                              "cart_total_paise": proposed.total_paise,
                              "cap_paise": decision.cap_paise})
        trace.end(output=reply)
        sess.history += [{"role": "user", "content": req.message},
                         {"role": "assistant", "content": reply}]
        return ChatResponse(session_id=req.session_id, reply=reply, cart=sess.cart,
                            decision=decision, tools=tools, trace_url=trace.url)

    # 4b. ALLOWED --------------------------------------------------------
    sess.cart = proposed
    if intent == "checkout" and proposed.lines:
        client = get_client()

        # Phase 1 of two-phase settlement: claim the headroom atomically BEFORE
        # touching Razorpay. `decision` above is advisory — it can go stale in
        # the microseconds before the tool call. This reservation cannot.
        idem = req.idempotency_key or cart_idempotency_key(
            req.session_id, decision.mandate_id or "",
            decision.mandate_version or 0, proposed)
        with trace.span("reserve_headroom", input={"idempotency_key": idem}) as sp:
            reservation = store.reserve_headroom(
                decision.mandate_id, proposed.total_paise, idem)
            sp["output"] = reservation.model_dump(mode="json")
            sp["level"] = "DEFAULT" if reservation.granted else "WARNING"
            sp["status_message"] = reservation.reason

        if not reservation.granted:
            # Lost a race, or the mandate changed under us mid-turn.
            store.log_event(event="RESERVATION_DENIED", session_id=req.session_id,
                            mandate_id=decision.mandate_id,
                            mandate_version=decision.mandate_version,
                            code=reservation.reason,
                            cart_total_paise=proposed.total_paise,
                            payload={"headroom_paise": reservation.headroom_paise})
            tools.append(ToolInvocation(name="create_payment_link",
                                        args={"amount": proposed.total_paise},
                                        blocked=True))
            reply = (f"Another purchase under this mandate settled while I was working, "
                     f"so {rupees(proposed.total_paise)} no longer fits — "
                     f"{rupees(reservation.headroom_paise)} is left. Nothing was charged.")
            trace.end(output=reply)
            sess.history += [{"role": "user", "content": req.message},
                             {"role": "assistant", "content": reply}]
            return ChatResponse(session_id=req.session_id, reply=reply, cart=sess.cart,
                                decision=decision, tools=tools, trace_url=trace.url)

        if reservation.replayed and reservation.razorpay_ref:
            # This exact basket already settled. Do not charge again.
            reply = (f"This order already went through — reusing payment reference "
                     f"{reservation.razorpay_ref} rather than charging you twice.")
            tools.append(ToolInvocation(name="create_payment_link",
                                        args={"idempotency_key": idem},
                                        result={"id": reservation.razorpay_ref,
                                                "replayed": True}))
            trace.event(name="idempotent_replay", metadata={"ref": reservation.razorpay_ref})
            sess.cart = Cart()
            trace.end(output=reply)
            sess.history += [{"role": "user", "content": req.message},
                             {"role": "assistant", "content": reply}]
            return ChatResponse(session_id=req.session_id, reply=reply, cart=sess.cart,
                                decision=decision, tools=tools, trace_url=trace.url)

        with trace.span("mcp_tool_call", input={"tool": "create_payment_link"}) as sp:
            args = {
                "amount": proposed.total_paise,
                "currency": "INR",
                "description": f"Agentic cart ({len(proposed.lines)} items) "
                               f"under mandate {decision.mandate_id}",
                "accept_partial": False,
                "reference_id": idem,
                "notes": {"mandate_id": decision.mandate_id or "",
                          "mandate_version": str(decision.mandate_version),
                          "reservation_id": reservation.id or "",
                          "idempotency_key": idem,
                          "agent_id": req.agent_id, "session_id": req.session_id},
            }
            try:
                raw = client.call_tool("create_payment_link", args, decision)
                payload = unwrap(raw)
                tools.append(ToolInvocation(name="create_payment_link", args=args,
                                            result=payload if isinstance(payload, dict) else
                                            {"text": str(payload)}))
                sp["output"] = payload
                # Phase 2: money moved, so the hold becomes permanent.
                store.commit_reservation(
                    reservation.id,
                    razorpay_ref=(payload or {}).get("id")
                    if isinstance(payload, dict) else None)
                store.log_event(event="MCP_TOOL_CALL", session_id=req.session_id,
                                mandate_id=decision.mandate_id,
                                mandate_version=decision.mandate_version,
                                code="ALLOW", cart_total_paise=proposed.total_paise,
                                payload={"tool": "create_payment_link",
                                         "result": payload if isinstance(payload, dict) else {}})
                link = payload.get("short_url") if isinstance(payload, dict) else None
                reply = (f"Done — {rupees(proposed.total_paise)} is within your "
                         f"{rupees(decision.cap_paise)} mandate, so I raised the payment link"
                         + (f": {link}" if link else "."))
                sess.cart = Cart()
            except MandateViolation as exc:
                store.release_reservation(reservation.id)
                sp["level"] = "ERROR"; sp["status_message"] = str(exc)
                reply = decision.human_message
            except Exception as exc:  # network / Razorpay error
                # Nothing settled, so give the headroom straight back rather
                # than letting a failed call eat the customer's budget.
                store.release_reservation(reservation.id)
                sp["level"] = "ERROR"; sp["status_message"] = str(exc)
                store.log_event(event="MCP_TOOL_ERROR", session_id=req.session_id,
                                mandate_id=decision.mandate_id, payload={"error": str(exc)})
                reply = ("Your mandate allows this purchase, but Razorpay did not return a "
                         "payment link just now. Nothing was charged — shall I retry?")

    trace.end(output=reply)
    sess.history += [{"role": "user", "content": req.message},
                     {"role": "assistant", "content": reply}]
    return ChatResponse(session_id=req.session_id, reply=reply, cart=sess.cart,
                        decision=decision, tools=tools, trace_url=trace.url)
