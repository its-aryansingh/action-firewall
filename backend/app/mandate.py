"""The UAP Mandate Verification Layer.

Design rule: this module is PURE and DETERMINISTIC. The LLM never decides
whether a payment is allowed — it only proposes a cart. `verify()` is the
only gate, it runs before any Razorpay MCP tool is reachable, and it is
unit-tested. That separation is the whole thesis of the project:
agentic commerce is an authorization problem, not a checkout problem.
"""
from __future__ import annotations

from .models import (Cart, DecisionCode, Mandate, MandateDecision, Window)
from . import store


def rupees(paise: int) -> str:
    return f"₹{paise / 100:,.2f}".replace(".00", "")


def verify(cart: Cart, mandate: Mandate | None, already_spent_paise: int = 0) -> MandateDecision:
    """Evaluate a proposed cart against a human-authorised mandate.

    Checks run cheapest-and-most-fatal first:
      1. mandate exists          4. per-transaction cap
      2. mandate is active       5. window cap (cap - spent = headroom)
      3. category policy
    """
    total = cart.total_paise

    if mandate is None:
        return MandateDecision(
            allowed=False, code=DecisionCode.BLOCK_NO_MANDATE, cart_total_paise=total,
            human_message=("No spending mandate is authorised for this agent yet. "
                           "Please create one in the Mandate Dashboard before I can pay."),
        )

    base = dict(mandate_id=mandate.id, mandate_version=mandate.version,
                cart_total_paise=total, cap_paise=mandate.cap_paise,
                already_spent_paise=already_spent_paise,
                headroom_paise=max(0, mandate.cap_paise - already_spent_paise))

    if not mandate.active:
        return MandateDecision(
            allowed=False, code=DecisionCode.BLOCK_MANDATE_REVOKED, **base,
            human_message=("Your mandate for this agent has been revoked, so I cannot "
                           "move any money. Re-activate it in the dashboard to continue."),
        )

    # 3. Category policy
    offending = [
        l.sku for l in cart.lines
        if l.category in mandate.blocked_categories
        or (mandate.allowed_categories and l.category not in mandate.allowed_categories)
    ]
    if offending:
        names = ", ".join(l.name for l in cart.lines if l.sku in offending)
        return MandateDecision(
            allowed=False, code=DecisionCode.BLOCK_CATEGORY_NOT_ALLOWED,
            offending_skus=offending, **base,
            human_message=(f"Your mandate does not cover these items: {names}. "
                           "I have left them out rather than charging you for them."),
        )

    # 4. Per-transaction cap
    if mandate.per_txn_cap_paise is not None and total > mandate.per_txn_cap_paise:
        return MandateDecision(
            allowed=False, code=DecisionCode.BLOCK_PER_TXN_CAP_EXCEEDED, **base,
            human_message=(f"This cart of {rupees(total)} is over your per-transaction "
                           f"limit of {rupees(mandate.per_txn_cap_paise)}. "
                           "Shall I split it into two smaller orders?"),
        )

    # 5. Window cap
    headroom = mandate.cap_paise - already_spent_paise
    if total > headroom:
        window_label = {Window.PER_TXN: "per transaction", Window.DAILY: "daily",
                        Window.WEEKLY: "weekly", Window.MONTHLY: "monthly"}[mandate.window]
        spent_note = (f" You have already used {rupees(already_spent_paise)} of it this period."
                      if already_spent_paise else "")
        return MandateDecision(
            allowed=False, code=DecisionCode.BLOCK_WINDOW_CAP_EXCEEDED, **base,
            human_message=(
                f"I cannot complete this transaction — the {rupees(total)} total exceeds your "
                f"authorised UPI Reserve Pay mandate of {rupees(mandate.cap_paise)} "
                f"({window_label}).{spent_note} "
                f"You have {rupees(max(0, headroom))} of headroom left. "
                "Would you like me to drop the most expensive item to bring it under the limit?"),
        )

    return MandateDecision(
        allowed=True, code=DecisionCode.ALLOW, **base,
        human_message=(f"{rupees(total)} is within your authorised mandate of "
                       f"{rupees(mandate.cap_paise)}. Proceeding to checkout."),
    )


def verify_for_agent(cart: Cart, user_id: str, agent_id: str,
                     session_id: str | None = None) -> MandateDecision:
    """Live variant: loads the CURRENT mandate + spend, verifies, and writes the
    audit row. Reloading on every call is what makes revocation take effect on
    the very next prompt with no cache to invalidate."""
    mandate = store.get_active_mandate(user_id, agent_id)
    spent = store.spent_in_window(mandate.id, mandate.window) if mandate else 0
    decision = verify(cart, mandate, spent)
    store.log_event(
        event="MANDATE_CHECK", session_id=session_id,
        mandate_id=decision.mandate_id, mandate_version=decision.mandate_version,
        code=decision.code.value, cart_total_paise=decision.cart_total_paise,
        cap_paise=decision.cap_paise,
        payload={"already_spent_paise": decision.already_spent_paise,
                 "headroom_paise": decision.headroom_paise,
                 "skus": [l.sku for l in cart.lines],
                 "offending_skus": decision.offending_skus},
    )
    return decision


def suggest_downgrade(cart: Cart, decision: MandateDecision) -> Cart | None:
    """Graceful failure: drop the priciest lines until the cart fits the headroom.
    Returns None if nothing survives."""
    if decision.allowed:
        return cart
    budget = decision.headroom_paise if decision.code == DecisionCode.BLOCK_WINDOW_CAP_EXCEEDED \
        else decision.cap_paise
    kept, running = [], 0
    for line in sorted(cart.lines, key=lambda l: l.line_total_paise):
        if running + line.line_total_paise <= budget:
            kept.append(line)
            running += line.line_total_paise
    return Cart(lines=kept) if kept else None
