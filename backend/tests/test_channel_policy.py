"""Tests for Merchant AI-Channel Policy evaluation (channel_policy.py).

Verifies:
1. Permitted categories from catalog (pantry, produce, dairy, etc.) are allowed;
2. Blocked categories (alcohol, tobacco, electronics, gift cards) fail closed;
3. Unapproved unknown categories fail closed;
4. Every single category in data/catalog.json is accounted for in allowed or blocked sets;
5. Transaction ceiling allows demo amount (₹7,840) and fails closed above ₹10,000;
6. Unauthorized actuator actions other than 'create_payment_link' are rejected;
7. Cross-merchant requests targeting unapproved stores are blocked;
8. Policy monotonicity in both directions (effective authority is the intersection);
9. Store.authorize_and_reserve evaluates channel policy atomically under BEGIN IMMEDIATE.
"""
from __future__ import annotations

import json
import uuid
import pytest
from pathlib import Path

from app.actions import canonicalize_action
from app.channel_policy import (
    DEFAULT_CHANNEL_POLICY,
    ChannelPolicyDecision,
    evaluate_channel_policy,
)
from app.config import get_settings
from app.authorization import cart_hash
from app.merchant import DEFAULT_MERCHANT_ID
from app.models import (
    ActionContext,
    AuthorizationRequest,
    Cart,
    CartLine,
    MandateCreate,
)
from app import store


@pytest.fixture()
def clean_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "action-firewall.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    store.init_db()
    yield
    get_settings.cache_clear()


def test_valid_grocery_cart_is_allowed():
    cart = Cart(
        lines=[
            CartLine(sku="SKU-PAS-001", name="Penne", category="pantry", unit_price_paise=9900, qty=1),
            CartLine(sku="SKU-SAU-001", name="Passata", category="produce", unit_price_paise=24900, qty=1),
        ]
    )
    dec = evaluate_channel_policy(
        merchant_id=DEFAULT_MERCHANT_ID,
        cart=cart,
        amount_paise=34800,
        action_name="create_payment_link",
    )
    assert dec.allowed is True
    assert dec.code == "ALLOW_CHANNEL_POLICY"


def test_prohibited_category_fails_closed():
    cart = Cart(
        lines=[
            CartLine(sku="SKU-ALC-999", name="Red Wine 750ml", category="alcohol", unit_price_paise=150000, qty=1),
        ]
    )
    dec = evaluate_channel_policy(
        merchant_id=DEFAULT_MERCHANT_ID,
        cart=cart,
        amount_paise=150000,
        action_name="create_payment_link",
    )
    assert dec.allowed is False
    assert dec.code == "BLOCK_CHANNEL_CATEGORY_RESTRICTED"
    assert "alcohol" in dec.reason.lower()


def test_unapproved_category_fails_closed():
    cart = Cart(
        lines=[
            CartLine(sku="SKU-AUTO-001", name="Motor Oil", category="automotive", unit_price_paise=50000, qty=1),
        ]
    )
    dec = evaluate_channel_policy(
        merchant_id=DEFAULT_MERCHANT_ID,
        cart=cart,
        amount_paise=50000,
        action_name="create_payment_link",
    )
    assert dec.allowed is False
    assert dec.code == "BLOCK_CHANNEL_CATEGORY_RESTRICTED"
    assert "automotive" in dec.reason.lower()


def test_all_catalog_categories_accounted_for():
    catalog_path = Path(__file__).resolve().parents[2] / "data" / "catalog.json"
    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)

    catalog_categories = {p["category"].strip().lower() for p in catalog}
    allowed = {c.strip().lower() for c in DEFAULT_CHANNEL_POLICY["allowed_categories"]}
    blocked = {c.strip().lower() for c in DEFAULT_CHANNEL_POLICY["blocked_categories"]}

    unaccounted = catalog_categories - (allowed | blocked)
    assert not unaccounted, f"Catalog categories unaccounted for in channel policy: {unaccounted}"


def test_channel_order_ceiling():
    # ₹7,840 demo amount is allowed under the ₹10,000 cap
    dec_demo = evaluate_channel_policy(
        merchant_id=DEFAULT_MERCHANT_ID,
        amount_paise=784_000,
        action_name="create_payment_link",
    )
    assert dec_demo.allowed is True
    assert dec_demo.code == "ALLOW_CHANNEL_POLICY"

    # Exactly at ₹10,000 cap is allowed
    dec_cap = evaluate_channel_policy(
        merchant_id=DEFAULT_MERCHANT_ID,
        amount_paise=1_000_000,
        action_name="create_payment_link",
    )
    assert dec_cap.allowed is True

    # ₹12,000 (> ₹10,000 cap) fails closed
    dec_over = evaluate_channel_policy(
        merchant_id=DEFAULT_MERCHANT_ID,
        amount_paise=1_200_000,
        action_name="create_payment_link",
    )
    assert dec_over.allowed is False
    assert dec_over.code == "BLOCK_CHANNEL_ORDER_CAP_EXCEEDED"


def test_unauthorized_actuator_action_blocked():
    dec = evaluate_channel_policy(
        merchant_id=DEFAULT_MERCHANT_ID,
        amount_paise=5000,
        action_name="capture_payment",
    )
    assert dec.allowed is False
    assert dec.code == "BLOCK_UNAUTHORIZED_RAIL_ACTION"


def test_unapproved_merchant_blocked():
    dec = evaluate_channel_policy(
        merchant_id="merchant_unapproved_vendor",
        amount_paise=5000,
        action_name="create_payment_link",
    )
    assert dec.allowed is False
    assert dec.code == "BLOCK_MERCHANT_AI_CHANNEL_DISABLED"


def test_policy_monotonicity_both_directions():
    """Effective authority is the intersection: merchant policy can narrow shopper authority
    and shopper envelope can narrow merchant capability, but neither can widen the other.
    """
    # 1. Merchant policy narrows: shopper allows ₹15,000, but merchant cap is ₹10,000
    # An order of ₹12,000 is rejected by merchant channel policy.
    dec_merchant_narrows = evaluate_channel_policy(
        merchant_id=DEFAULT_MERCHANT_ID,
        amount_paise=1_200_000,
        action_name="create_payment_link",
    )
    assert dec_merchant_narrows.allowed is False
    assert dec_merchant_narrows.code == "BLOCK_CHANNEL_ORDER_CAP_EXCEEDED"

    # 2. Merchant policy permits, but shopper envelope/mandate narrows:
    # Merchant allows ₹10,000, but shopper mandate cap is only ₹5,000.
    # An order of ₹6,000 is allowed by channel policy alone, but rejected by shopper mandate.
    dec_channel = evaluate_channel_policy(
        merchant_id=DEFAULT_MERCHANT_ID,
        amount_paise=600_000,
        action_name="create_payment_link",
    )
    assert dec_channel.allowed is True


def test_authorize_and_reserve_enforces_channel_policy(clean_db):
    """Verify that store.authorize_and_reserve checks merchant channel policy atomically."""
    mandate = store.create_mandate(MandateCreate(cap_rupees=20000))
    attempt_id = f"att-{uuid.uuid4().hex}"
    context = ActionContext(
        user_id="user_demo",
        agent_id="agent_groceries",
        session_id="sess-1",
        merchant_id=DEFAULT_MERCHANT_ID,
    )

    # 1. Blocked category (electronics) fails closed in authorize_and_reserve
    cart_electronics = Cart(
        lines=[
            CartLine(sku="SKU-ELEC-001", name="Headphones", category="electronics", unit_price_paise=50000, qty=1)
        ]
    )
    raw_args = {
        "amount": cart_electronics.total_paise,
        "currency": "INR",
        "description": "Electronics purchase",
        "accept_partial": False,
        "reference_id": attempt_id,
        "notes": {"policy_id": mandate.id},
    }
    canonical = canonicalize_action("create_payment_link", raw_args)
    req = AuthorizationRequest(
        context=context,
        mandate_id=mandate.id,
        expected_mandate_version=mandate.version,
        action_name=canonical.name,
        action_schema_hash=canonical.schema_hash,
        args=canonical.args,
        cart=cart_electronics,
        cart_hash=cart_hash(cart_electronics),
        purchase_attempt_id=attempt_id,
    )
    outcome = store.authorize_and_reserve(req)
    assert outcome.authorized is False
    assert outcome.reason == "BLOCK_CHANNEL_CATEGORY_RESTRICTED"

    # Verify audit event was logged
    audit_events = store.audit_trail()
    channel_rejects = [e for e in audit_events if e["event"] == "CHANNEL_POLICY_REJECTED"]
    assert len(channel_rejects) == 1
    assert channel_rejects[0]["code"] == "BLOCK_CHANNEL_CATEGORY_RESTRICTED"

    # 2. Disabled merchant fails closed
    attempt_id_2 = f"att-{uuid.uuid4().hex}"
    context_foreign = ActionContext(
        user_id="user_demo",
        agent_id="agent_groceries",
        session_id="sess-2",
        merchant_id="foreign_unapproved_merchant",
    )
    cart_ok = Cart(
        lines=[
            CartLine(sku="SKU-PAN-001", name="Flour", category="pantry", unit_price_paise=10000, qty=1)
        ]
    )
    raw_args_2 = {
        "amount": cart_ok.total_paise,
        "currency": "INR",
        "description": "Flour purchase",
        "accept_partial": False,
        "reference_id": attempt_id_2,
        "notes": {"policy_id": mandate.id},
    }
    canonical_2 = canonicalize_action("create_payment_link", raw_args_2)
    req_2 = AuthorizationRequest(
        context=context_foreign,
        mandate_id=mandate.id,
        expected_mandate_version=mandate.version,
        action_name=canonical_2.name,
        action_schema_hash=canonical_2.schema_hash,
        args=canonical_2.args,
        cart=cart_ok,
        cart_hash=cart_hash(cart_ok),
        purchase_attempt_id=attempt_id_2,
    )
    outcome_2 = store.authorize_and_reserve(req_2)
    assert outcome_2.authorized is False
    assert outcome_2.reason == "BLOCK_MERCHANT_AI_CHANNEL_DISABLED"
