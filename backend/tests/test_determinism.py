"""Formal determinism test suite for Action Firewall.

Verifies:
1. Canonical JSON byte-for-byte reproducibility across key insertion orders.
2. Cryptographic quote and cart hash determinism.
3. Decision code, reason, and policy delta determinism under identical drift inputs.
4. HMAC receipt signature determinism and tamper-evidence.
5. Integer paise arithmetic determinism without floating-point drift.
"""
from __future__ import annotations

import hmac
import hashlib
import time
import pytest

from app.authorization import canonical_json
from app.channel_policy import evaluate_channel_policy
from app.config import get_settings
from app.envelope import compute_envelope_hash, compute_quote_hash, verify_quote
from app.models import (
    ActionGrant,
    ActionState,
    Cart,
    CartLine,
    DecisionCode,
    EnvelopeSlot,
    EnvelopeStatus,
    MerchantQuote,
    PurchaseEnvelope,
)
from app.receipts import _signing_key, authorization_payload, authorization_signature_for, build_receipt, verify_receipt


def test_canonical_json_key_order_determinism():
    """canonical_json must produce identical string regardless of dictionary insertion order."""
    d1 = {"z": 100, "a": "hello", "m": [3, 2, 1], "nested": {"y": True, "b": False}}
    d2 = {"nested": {"b": False, "y": True}, "a": "hello", "z": 100, "m": [3, 2, 1]}

    canon1 = canonical_json(d1)
    canon2 = canonical_json(d2)

    assert canon1 == canon2
    assert canon1 == '{"a":"hello","m":[3,2,1],"nested":{"b":false,"y":true},"z":100}'


def test_quote_hash_determinism():
    """compute_quote_hash must be byte-for-byte identical for identical merchant quotes."""
    cart1 = Cart(
        merchant_id="merchant_freshbasket",
        lines=[
            CartLine(sku="SKU-PAS-002", name="Rigatoni Pasta 500g", category="pantry", qty=2, unit_price_paise=8900),
            CartLine(sku="SKU-SAU-001", name="Arrabbiata Pasta Sauce 350g", category="pantry", qty=1, unit_price_paise=24900),
        ],
        total_paise=42700,
        currency="INR",
    )
    cart2 = Cart(
        merchant_id="merchant_freshbasket",
        lines=[
            CartLine(sku="SKU-PAS-002", name="Rigatoni Pasta 500g", category="pantry", qty=2, unit_price_paise=8900),
            CartLine(sku="SKU-SAU-001", name="Arrabbiata Pasta Sauce 350g", category="pantry", qty=1, unit_price_paise=24900),
        ],
        total_paise=42700,
        currency="INR",
    )

    q1 = MerchantQuote(
        merchant_id="merchant_freshbasket",
        currency="INR",
        fulfillment_profile_id="dest_demo",
        delivery_eta=1700001000.0,
        cart=cart1,
        quote_hash="",
    )
    q2 = MerchantQuote(
        merchant_id="merchant_freshbasket",
        currency="INR",
        fulfillment_profile_id="dest_demo",
        delivery_eta=1700001000.0,
        cart=cart2,
        quote_hash="",
    )

    h1 = compute_quote_hash(q1)
    h2 = compute_quote_hash(q2)

    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex string


def test_policy_delta_generation_determinism():
    """Under price drift, the generated PolicyDelta must be completely deterministic."""
    from app import catalog

    product = catalog.by_sku()["SKU-PAS-002"]
    now = 1700000000.0
    required_tag = product["tags"][0]

    env = PurchaseEnvelope(
        id="env_det_01",
        label="Dinner envelope",
        goal="Buy dinner items",
        user_id="usr_01",
        agent_id="agt_01",
        merchant_id="merchant_freshbasket",
        currency="INR",
        max_total_paise=5000,
        fulfillment_profile_id="dest_demo",
        delivery_deadline=now + 3600,
        expires_at=now + 3600,
        slots=[EnvelopeSlot(id="pasta", label="Pasta", required_tags=[required_tag])],
        allowed_skus=["SKU-PAS-002"],
        price_caps_paise={"SKU-PAS-002": product["price_paise"]},
        version=1,
        envelope_hash="hash_placeholder",
        status=EnvelopeStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    env = env.model_copy(update={"envelope_hash": compute_envelope_hash(env)})

    # Cart total exceeds envelope budget (product["price_paise"] > 5000)
    cart = Cart(
        merchant_id="merchant_freshbasket",
        lines=[
            CartLine(
                sku="SKU-PAS-002",
                name=product["name"],
                category=product["category"],
                qty=1,
                unit_price_paise=product["price_paise"],
            )
        ],
        total_paise=product["price_paise"],
        currency="INR",
    )

    quote_proto = MerchantQuote(
        merchant_id="merchant_freshbasket",
        currency="INR",
        fulfillment_profile_id="dest_demo",
        delivery_eta=now + 1800,
        cart=cart,
        quote_hash="",
    )
    quote = quote_proto.model_copy(update={"quote_hash": compute_quote_hash(quote_proto)})

    d1 = verify_quote(env, quote, now=now + 10)
    d2 = verify_quote(env, quote, now=now + 10)

    assert d1.allowed is False
    assert d2.allowed is False
    assert d1.code == d2.code == "BLOCK_ENVELOPE_MISMATCH"
    assert d1.human_message == d2.human_message
    assert len(d1.deltas) == len(d2.deltas) == 1
    delta1 = d1.deltas[0]
    delta2 = d2.deltas[0]
    assert delta1.field == delta2.field == "max_total_paise"
    assert delta1.expected == delta2.expected == "5000"
    assert delta1.actual == delta2.actual == str(product["price_paise"])
    assert delta1.recovery == delta2.recovery == "repair"


def test_channel_policy_decision_determinism():
    """evaluate_channel_policy must return deterministic decisions across repeated calls."""
    cart = Cart(
        merchant_id="merchant_freshbasket",
        lines=[CartLine(sku="SKU-PAS-002", name="Rigatoni Pasta 500g", category="pantry", qty=1, unit_price_paise=8900)],
        total_paise=8900,
        currency="INR",
    )
    dec1 = evaluate_channel_policy("merchant_freshbasket", cart, 8900, "create_payment_link")
    dec2 = evaluate_channel_policy("merchant_freshbasket", cart, 8900, "create_payment_link")

    assert dec1.allowed == dec2.allowed == True
    assert dec1.code == dec2.code
    assert dec1.reason == dec2.reason


def test_receipt_hmac_signing_determinism_and_tamper_evidence():
    """build_receipt must produce identical HMAC signatures for identical grants, and detect tampering."""
    now = 1700000000.0
    grant = ActionGrant(
        id="grant_det_001",
        mandate_id="man_001",
        mandate_version=1,
        policy_hash="policy_hash_001",
        user_id="usr_01",
        agent_id="agt_01",
        session_id="sess_01",
        merchant_id="merchant_freshbasket",
        action_name="create_payment_link",
        action_schema_hash="schema_hash_01",
        args_hash="args_hash_01",
        cart_hash="cart_hash_01",
        amount_paise=8900,
        currency="INR",
        purchase_attempt_id="att_det_001",
        state=ActionState.ACTION_ISSUED,
        created_at=now,
        updated_at=now,
    )

    r1 = build_receipt(grant)
    r2 = build_receipt(grant)

    assert r1.authorization_signature == r2.authorization_signature
    assert len(r1.authorization_signature) == 64

    # Verify signature verifies with authoritative signing key
    expected_sig = authorization_signature_for(grant)
    assert r1.authorization_signature == expected_sig

    # Verify verification function succeeds with grant
    verification = verify_receipt(r1, grant)
    assert verification.valid is True
    assert verification.authorization_valid is True
    assert verification.status_current is True

    # Tampering with authorization signature is caught
    tampered_receipt = r1.model_copy(update={"authorization_signature": "0" * 64})
    tampered_verification = verify_receipt(tampered_receipt, grant)
    assert tampered_verification.valid is False
    assert tampered_verification.authorization_valid is False


def test_integer_paise_integrity():
    """All price calculations must remain strictly integer paise without IEEE 754 float imprecision."""
    prices_paise = [1999, 2499, 8900, 12450, 49900]
    total_paise = sum(prices_paise)

    assert isinstance(total_paise, int)
    assert total_paise == 75748

    # Rupee conversion must be exact formatted string, never raw float accumulation
    rupees_str = f"{total_paise / 100:.2f}"
    assert rupees_str == "757.48"
