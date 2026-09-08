"""Opaque, single-use human approval tokens for Action Firewall.

Provides:
- Short-lived expiring tokens for /approve/{token};
- SHA-256 hashed storage preventing token exposure in logs or leaks;
- Atomic compare-and-set redemption ensuring single-use customer authorization;
- Immediate rejection of expired, revoked, or already-redeemed tokens;
- Single BEGIN IMMEDIATE transaction guaranteeing zero stuck states on activation failure.
"""
from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from typing import Any

from . import store
from .store import UNBOUND_SESSION
from .merchant import DEFAULT_MERCHANT_ID
from .models import PurchaseEnvelope
from .store import (
    ApprovalTokenAlreadyRedeemedError,
    ApprovalTokenConflictError,
    ApprovalTokenError,
    ApprovalTokenExpiredError,
    ApprovalTokenInvalidError,
    ApprovalTokenNotFoundError,
)

__all__ = [
    "ApprovalTokenError",
    "ApprovalTokenNotFoundError",
    "ApprovalTokenExpiredError",
    "ApprovalTokenAlreadyRedeemedError",
    "ApprovalTokenConflictError",
    "ApprovalTokenInvalidError",
    "hash_token",
    "mint_approval_token",
    "redeem_approval_token",
    "lookup_approval_token",
]


def hash_token(raw_token: str) -> str:
    """Hash raw token with SHA-256 for secure storage and comparison."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


_hash_token = hash_token


def mint_approval_token(
    envelope_id: str,
    envelope_hash: str,
    ttl_seconds: int = 900,
    merchant_id: str = DEFAULT_MERCHANT_ID,
    buyer_agent_id: str = "buyer_mcp",
    shopper_session_id: str | None = None,
    intent_id: str | None = None,
    envelope_version: int = 1,
) -> tuple[str, str]:
    """Mint an opaque, single-use approval token.

    Returns (raw_token, approval_url).
    """
    raw_token = f"appr_{secrets.token_urlsafe(24)}"
    token_hash = _hash_token(raw_token)
    token_id = f"tok_{uuid.uuid4().hex[:12]}"
    public_approval_id = f"appr_pub_{uuid.uuid4().hex[:12]}"
    expires_at = time.time() + ttl_seconds

    store.save_approval_token(
        id=token_id,
        public_approval_id=public_approval_id,
        merchant_id=merchant_id,
        buyer_agent_id=buyer_agent_id,
        shopper_session_id=shopper_session_id or UNBOUND_SESSION,
        intent_id=intent_id,
        envelope_id=envelope_id,
        envelope_version=envelope_version,
        envelope_hash=envelope_hash,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    approval_url = f"/approve/{raw_token}"
    return raw_token, approval_url


def lookup_approval_token(raw_token: str) -> dict[str, Any] | None:
    """Lookup an approval token by its hash. Read-only, no side effects."""
    token_hash = _hash_token(raw_token)
    return store.get_approval_token_by_hash(token_hash)


def redeem_approval_token(
    raw_token: str,
    expected_shopper_session_id: str | None = None,
) -> PurchaseEnvelope:
    """Atomically redeem an approval token and activate the bound Purchase Envelope.

    Fails closed if the token is unknown, expired, or already redeemed.
    Single BEGIN IMMEDIATE transaction: token lookup -> expiry/state check ->
    envelope version+hash check -> shopper-session bind check -> CAS token consume ->
    envelope activation -> spend fence -> audit event.

    Any failure rolls back all of it.
    """
    token_hash = _hash_token(raw_token)
    return store.redeem_approval_token_and_activate(
        token_hash=token_hash,
        expected_shopper_session_id=expected_shopper_session_id,
    )
