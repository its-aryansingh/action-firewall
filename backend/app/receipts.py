"""Application-signed evidence for exact Action Firewall decisions."""
from __future__ import annotations

import hashlib
import hmac

from .authorization import canonical_json
from .config import get_settings
from .models import ActionGrant, ActionReceipt


def _signing_key() -> bytes:
    settings = get_settings()
    if settings.action_receipt_secret:
        return settings.action_receipt_secret.encode("utf-8")
    if settings.demo_mode:
        return b"action-firewall-demo-receipt-key-not-for-production"
    raise RuntimeError("ACTION_RECEIPT_SECRET is required outside demo mode")


def receipt_payload(grant: ActionGrant) -> dict[str, object]:
    return {
        "grant_id": grant.id,
        "envelope_id": grant.envelope_id,
        "envelope_version": grant.envelope_version,
        "envelope_hash": grant.envelope_hash,
        "policy_id": grant.mandate_id,
        "policy_version": grant.mandate_version,
        "policy_hash": grant.policy_hash,
        "action_name": grant.action_name,
        "args_hash": grant.args_hash,
        "cart_hash": grant.cart_hash,
        "quote_hash": grant.quote_hash,
        "purchase_attempt_id": grant.purchase_attempt_id,
        "state": grant.state.value,
        "provider_ref": grant.provider_ref,
        "created_at": grant.created_at,
        "updated_at": grant.updated_at,
    }


def signature_for(grant: ActionGrant) -> str:
    return hmac.new(
        _signing_key(),
        canonical_json(receipt_payload(grant)).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_receipt(grant: ActionGrant) -> ActionReceipt:
    return ActionReceipt(**receipt_payload(grant), signature=signature_for(grant))


def verify_receipt(receipt: ActionReceipt, grant: ActionGrant) -> bool:
    expected = build_receipt(grant)
    return hmac.compare_digest(receipt.signature, expected.signature) and (
        receipt.model_dump(mode="json") == expected.model_dump(mode="json")
    )
