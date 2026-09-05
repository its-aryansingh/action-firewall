"""Application-signed evidence for exact Action Firewall decisions."""
from __future__ import annotations

import hashlib
import hmac

from .authorization import canonical_json
from .config import get_settings
from .models import (
    ActionGrant,
    ActionReceipt,
    ActionReceiptVerification,
)


def _signing_key() -> bytes:
    settings = get_settings()
    if settings.action_receipt_secret:
        return settings.action_receipt_secret.encode("utf-8")
    if settings.demo_mode:
        return b"action-firewall-demo-receipt-key-not-for-production"
    raise RuntimeError("ACTION_RECEIPT_SECRET is required outside demo mode")


def authorization_payload(grant: ActionGrant) -> dict[str, object]:
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
        "created_at": grant.created_at,
    }


def authorization_signature_for(grant: ActionGrant) -> str:
    return hmac.new(
        _signing_key(),
        canonical_json(authorization_payload(grant)).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def status_payload(grant: ActionGrant, auth_sig: str) -> dict[str, object]:
    return {
        "authorization_signature": auth_sig,
        "grant_id": grant.id,
        "state": grant.state.value,
        "provider_ref": grant.provider_ref,
        "updated_at": grant.updated_at,
    }


def status_signature_for(grant: ActionGrant, auth_sig: str) -> str:
    return hmac.new(
        _signing_key(),
        canonical_json(status_payload(grant, auth_sig)).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_receipt(grant: ActionGrant) -> ActionReceipt:
    auth_data = authorization_payload(grant)
    auth_sig = authorization_signature_for(grant)
    stat_sig = status_signature_for(grant, auth_sig)
    return ActionReceipt(
        **auth_data,
        state=grant.state,
        provider_ref=grant.provider_ref,
        updated_at=grant.updated_at,
        authorization_signature=auth_sig,
        status_signature=stat_sig,
        signature=auth_sig,
    )


def verify_receipt(receipt: ActionReceipt, grant: ActionGrant) -> ActionReceiptVerification:
    expected_auth = authorization_payload(grant)
    receipt_auth = receipt.authorization.model_dump(mode="json")
    expected_auth_sig = authorization_signature_for(grant)

    # Core check: does the authorization payload match the grant and does HMAC verify?
    auth_sig_matches = hmac.compare_digest(receipt.authorization_signature, expected_auth_sig)
    auth_fields_match = (receipt_auth == expected_auth)
    authorization_valid = auth_sig_matches and auth_fields_match

    # Status check: is the mutable status block current with respect to the grant row?
    expected_stat_sig = status_signature_for(grant, expected_auth_sig)
    stat_sig_matches = hmac.compare_digest(receipt.status_signature, expected_stat_sig)
    stat_fields_match = (
        receipt.state == grant.state
        and receipt.provider_ref == grant.provider_ref
        and receipt.updated_at == grant.updated_at
    )
    status_current = authorization_valid and stat_sig_matches and stat_fields_match

    return ActionReceiptVerification(
        valid=authorization_valid,
        authorization_valid=authorization_valid,
        status_current=status_current,
        status_as_of=receipt.updated_at,
        grant_id=grant.id,
        application_signed=True,
    )
