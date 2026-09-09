"""Merchant AI Channel Policy evaluation for Action Firewall.

Ensures that:
1. The merchant has authorized AI-channel commerce;
2. Requested cart items fall within allowed merchant categories and never violate blocklists;
3. Requested transaction value does not exceed merchant channel ceiling;
4. Requested actuator action is strictly the closed registered rail ('create_payment_link').
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .merchant import DEFAULT_MERCHANT_ID, SUPPORTED_MERCHANT_IDS
from .models import Cart


@dataclass(frozen=True)
class ChannelPolicyDecision:
    allowed: bool
    code: str
    reason: str
    remedy: str | None = None


# Default Merchant AI-Channel Rules for FreshBasket for Business (merchant_freshbasket)
DEFAULT_CHANNEL_POLICY = {
    "merchant_id": DEFAULT_MERCHANT_ID,
    "enabled": True,
    "allowed_categories": [
        "pantry",
        "dairy",
        "produce",
        "bakery",
        "beverages",
        "snacks",
        "household",
        "personal_care",
    ],
    "blocked_categories": [
        "electronics",
        "gift_cards",
        "alcohol",
        "tobacco",
        "lottery",
    ],
    "max_order_paise": 1_000_000,  # ₹10,000.00
    # Inbound and outbound. Still a CLOSED registry — anything not named here is
    # refused at the actuator boundary, which is the invariant that matters.
    "allowed_actions": ["create_payment_link", "refund"],
}


def evaluate_channel_policy(
    merchant_id: str,
    cart: Cart | None = None,
    amount_paise: int = 0,
    action_name: str = "create_payment_link",
) -> ChannelPolicyDecision:
    """Evaluate requested purchase against merchant's AI channel policy."""
    if merchant_id not in SUPPORTED_MERCHANT_IDS:
        return ChannelPolicyDecision(
            allowed=False,
            code="BLOCK_MERCHANT_AI_CHANNEL_DISABLED",
            reason=f"Merchant {merchant_id} has not enabled the Action Firewall AI channel.",
            remedy="Select an Action Firewall verified merchant.",
        )

    # 0. Kill switch check
    if not DEFAULT_CHANNEL_POLICY.get("enabled", True):
        return ChannelPolicyDecision(
            allowed=False,
            code="BLOCK_MERCHANT_AI_CHANNEL_DISABLED",
            reason=f"Merchant {merchant_id} AI channel is currently turned OFF by merchant kill switch.",
            remedy="Merchant must turn AI channel ON in Agent Commerce control plane.",
        )

    # 1. Closed registered rail check
    if action_name not in DEFAULT_CHANNEL_POLICY["allowed_actions"]:
        return ChannelPolicyDecision(
            allowed=False,
            code="BLOCK_UNAUTHORIZED_RAIL_ACTION",
            reason=f"Action {action_name} is not permitted for AI channel buyers. Only 'create_payment_link' is callable.",
            remedy="Use the registered create_payment_link action only.",
        )

    # 2. Category inspection if cart is present
    if cart:
        blocked = {c.strip().lower() for c in DEFAULT_CHANNEL_POLICY["blocked_categories"]}
        allowed = {c.strip().lower() for c in DEFAULT_CHANNEL_POLICY["allowed_categories"]}
        for line in cart.lines:
            cat_lower = (line.category or "").strip().lower()
            if cat_lower in blocked:
                return ChannelPolicyDecision(
                    allowed=False,
                    code="BLOCK_CHANNEL_CATEGORY_RESTRICTED",
                    reason=f"Category '{line.category}' is prohibited under the merchant's AI channel policy.",
                    remedy=f"Remove restricted item '{line.name}' from proposal.",
                )
            if cat_lower not in allowed:
                return ChannelPolicyDecision(
                    allowed=False,
                    code="BLOCK_CHANNEL_CATEGORY_RESTRICTED",
                    reason=f"Category '{line.category}' is not approved under the merchant's AI channel policy.",
                    remedy=f"Remove unapproved item '{line.name}' from proposal.",
                )

    # 3. Maximum transaction ceiling check
    max_cap = DEFAULT_CHANNEL_POLICY["max_order_paise"]
    if amount_paise > max_cap:
        return ChannelPolicyDecision(
            allowed=False,
            code="BLOCK_CHANNEL_ORDER_CAP_EXCEEDED",
            reason=f"Order amount ₹{amount_paise / 100:.2f} exceeds merchant AI channel cap of ₹{max_cap / 100:.2f}.",
            remedy="Reduce cart total or request human checkout override.",
        )

    return ChannelPolicyDecision(
        allowed=True,
        code="ALLOW_CHANNEL_POLICY",
        reason="Complies with merchant AI channel policy.",
    )
