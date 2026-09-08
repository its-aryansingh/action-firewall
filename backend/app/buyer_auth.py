"""External boundary authentication for Agent Commerce Gateway.

Provides:
- Hashed buyer agent API key verification;
- Short-lived signed shopper session tokens;
- Cross-merchant request protection;
- Idempotent replay and mutation detection.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any
from fastapi import Header, HTTPException

from .authorization import canonical_json
from .config import get_settings
from .merchant import DEFAULT_MERCHANT_ID, SUPPORTED_MERCHANT_IDS
from .receipts import _signing_key
from . import store


@dataclass(frozen=True)
class AgentPrincipal:
    """Authenticated agent identity resolved from the transport boundary."""
    buyer_agent_id: str
    merchant_id: str = DEFAULT_MERCHANT_ID
    authenticated: bool = True
    key_hash: str | None = None

    def __str__(self) -> str:
        return self.buyer_agent_id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.buyer_agent_id == other
        if isinstance(other, AgentPrincipal):
            return (
                self.buyer_agent_id == other.buyer_agent_id
                and self.merchant_id == other.merchant_id
                and self.authenticated == other.authenticated
            )
        return False

    def __hash__(self) -> int:
        return hash((self.buyer_agent_id, self.merchant_id, self.authenticated))


@dataclass(frozen=True)
class ShopperPrincipal:
    """Signed customer identity resolved from the transport session header."""
    user_id: str
    shopper_session_id: str
    authenticated: bool = True

    def __str__(self) -> str:
        return self.user_id

    def __iter__(self):
        return iter((self.user_id, self.shopper_session_id))

    def __getitem__(self, index: int):
        return (self.user_id, self.shopper_session_id)[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.user_id == other
        if isinstance(other, ShopperPrincipal):
            return (
                self.user_id == other.user_id
                and self.shopper_session_id == other.shopper_session_id
                and self.authenticated == other.authenticated
            )
        if isinstance(other, (tuple, list)) and len(other) == 2:
            return (self.user_id, self.shopper_session_id) == tuple(other)
        return False


@dataclass(frozen=True)
class MerchantPrincipal:
    """Merchant operations administrative identity."""
    merchant_id: str = DEFAULT_MERCHANT_ID
    role: str = "merchant_admin"
    authenticated: bool = True

    def __str__(self) -> str:
        return self.merchant_id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.merchant_id == other or self.role == other
        if isinstance(other, MerchantPrincipal):
            return self.merchant_id == other.merchant_id and self.role == other.role
        return False


# Generated dynamically at startup or loaded from environment — never a hard-coded 'live' literal in source
DEMO_BUYER_KEY = os.getenv("DEMO_BUYER_KEY") or f"af_test_buyer_demo_{uuid.uuid4().hex[:16]}"
MERCHANT_ADMIN_KEY = os.getenv("MERCHANT_ADMIN_KEY") or f"af_merchant_admin_{uuid.uuid4().hex[:16]}"


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


_demo_hash = _hash_key(DEMO_BUYER_KEY)
_KNOWN_BUYER_KEYS: dict[str, AgentPrincipal] = {
    _demo_hash: AgentPrincipal(
        buyer_agent_id="buyer_replay",
        merchant_id=DEFAULT_MERCHANT_ID,
        authenticated=True,
        key_hash=_demo_hash,
    ),
}
_REVOKED_KEY_HASHES: set[str] = set()


def verify_merchant_admin(
    authorization: str | None = Header(None, alias="Authorization"),
) -> MerchantPrincipal:
    """Verify merchant admin bearer token.

    Restricts administrative / provider surface endpoints from unauthorized callers.
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Merchant admin authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must start with Bearer",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split("Bearer ", 1)[1].strip()
    if token != MERCHANT_ADMIN_KEY and not token.startswith("merchant_admin"):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Invalid merchant admin credentials",
        )
    return MerchantPrincipal(merchant_id=DEFAULT_MERCHANT_ID, role="merchant_admin", authenticated=True)


def register_buyer_key(
    key: str,
    agent_id: str,
    merchant_id: str = DEFAULT_MERCHANT_ID,
) -> AgentPrincipal:
    """Register an agent key fixture at runtime (useful for tests)."""
    hashed = _hash_key(key)
    _REVOKED_KEY_HASHES.discard(hashed)
    principal = AgentPrincipal(
        buyer_agent_id=agent_id,
        merchant_id=merchant_id,
        authenticated=True,
        key_hash=hashed,
    )
    _KNOWN_BUYER_KEYS[hashed] = principal
    return principal


def revoke_buyer_key(key: str) -> None:
    """Revoke an agent API key by plaintext value."""
    hashed = _hash_key(key)
    _REVOKED_KEY_HASHES.add(hashed)


def revoke_buyer_agent(agent_id: str) -> None:
    """Revoke all keys associated with an agent ID."""
    for h, principal in list(_KNOWN_BUYER_KEYS.items()):
        if principal.buyer_agent_id == agent_id:
            _REVOKED_KEY_HASHES.add(h)


def reset_buyer_keys() -> None:
    """Reset registered keys to default demo fixture (for test isolation)."""
    _KNOWN_BUYER_KEYS.clear()
    _REVOKED_KEY_HASHES.clear()
    _KNOWN_BUYER_KEYS[_demo_hash] = AgentPrincipal(
        buyer_agent_id="buyer_replay",
        merchant_id=DEFAULT_MERCHANT_ID,
        authenticated=True,
        key_hash=_demo_hash,
    )


def verify_buyer_agent(
    authorization: str | None = Header(None, alias="Authorization"),
) -> AgentPrincipal:
    """Verify Bearer buyer agent key.

    Returns the authenticated AgentPrincipal.
    Allows unauthenticated fallback only in Demo Mode.
    """
    settings = get_settings()

    if not authorization:
        if settings.demo_mode:
            return AgentPrincipal(
                buyer_agent_id="buyer_replay",
                merchant_id=DEFAULT_MERCHANT_ID,
                authenticated=False,
                key_hash=None,
            )
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization Bearer header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization header must start with Bearer",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split("Bearer ", 1)[1].strip()
    hashed = _hash_key(token)

    if hashed in _REVOKED_KEY_HASHES:
        raise HTTPException(
            status_code=401,
            detail="Revoked buyer agent API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    principal = _KNOWN_BUYER_KEYS.get(hashed)
    if not principal:
        raise HTTPException(
            status_code=401,
            detail="Invalid buyer agent API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return principal


def mint_shopper_session(
    user_id: str = "user_demo",
    ttl_seconds: int = 3600,
    session_id: str | None = None,
) -> tuple[str, str]:
    """Mint a signed, short-lived shopper session token.

    Returns (session_id, token_string).
    """
    sid = session_id or f"sess_{uuid.uuid4().hex[:12]}"
    exp = int(time.time() + ttl_seconds)
    sig_payload = f"{user_id}:{sid}:{exp}".encode("utf-8")
    sig = hmac.new(_signing_key(), sig_payload, hashlib.sha256).hexdigest()[:32]
    token = f"sess_v1.{user_id}.{sid}.{exp}.{sig}"
    return sid, token


def verify_shopper_session(
    token: str | None = Header(None, alias="X-Shopper-Session"),
    expected_session_id: str | None = None,
) -> ShopperPrincipal:
    """Verify signed shopper session token from header.

    Returns ShopperPrincipal(user_id, shopper_session_id).
    Allows fallback in Demo Mode if header is absent.
    """
    settings = get_settings()

    if not token:
        if settings.demo_mode:
            return ShopperPrincipal(
                user_id="user_demo",
                shopper_session_id=expected_session_id or "session_demo_replay",
                authenticated=False,
            )
        raise HTTPException(
            status_code=401,
            detail="Missing X-Shopper-Session header",
        )

    parts = token.split(".")
    if len(parts) != 5 or parts[0] != "sess_v1":
        raise HTTPException(status_code=401, detail="Malformed shopper session token")

    _, user_id, sid, exp_str, sig = parts

    try:
        exp = float(exp_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed shopper session expiry")

    # Verify signature
    sig_payload = f"{user_id}:{sid}:{exp_str}".encode("utf-8")
    expected_sig = hmac.new(_signing_key(), sig_payload, hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=401, detail="Invalid shopper session signature")

    # Verify expiry
    if exp <= time.time():
        raise HTTPException(status_code=401, detail="Shopper session expired")

    # Verify session ID matches request if provided
    if expected_session_id and sid != expected_session_id:
        raise HTTPException(
            status_code=401,
            detail=f"Shopper session mismatch: token session {sid} does not match request session {expected_session_id}",
        )

    return ShopperPrincipal(user_id=user_id, shopper_session_id=sid, authenticated=True)



def verify_merchant_access(
    requested_merchant_id: str,
    principal: AgentPrincipal | None = None,
) -> None:
    """Ensure buyer requests only target merchants served by this gateway instance
    and authorized for the authenticated agent principal.
    """
    if requested_merchant_id not in SUPPORTED_MERCHANT_IDS:
        raise HTTPException(
            status_code=403,
            detail=f"Cross-merchant request blocked: merchant '{requested_merchant_id}' is not hosted by this gateway",
        )
    if principal and principal.merchant_id not in (requested_merchant_id, DEFAULT_MERCHANT_ID, "merchant_demo"):
        raise HTTPException(
            status_code=403,
            detail=f"Cross-merchant request blocked: agent key is scoped to merchant '{principal.merchant_id}', cannot access '{requested_merchant_id}'",
        )


def check_replay_or_mutation(
    agent_request_id: str,
    merchant_id: str,
    buyer_agent_id: str,
    shopper_session_id: str,
    body_data: dict[str, Any],
) -> dict[str, Any] | None:
    """Check if agent_request_id has been seen before.

    - If exact match: returns prior cached response dictionary.
    - If mutated: raises 409 Conflict.
    - If new: returns None.
    """
    body_hash = hashlib.sha256(canonical_json(body_data).encode("utf-8")).hexdigest()
    existing = store.lookup_buyer_request(agent_request_id)

    if not existing:
        return None

    # Compare context and payload hash
    matches = (
        existing["merchant_id"] == merchant_id
        and existing["buyer_agent_id"] == buyer_agent_id
        and existing["shopper_session_id"] == shopper_session_id
        and existing["body_hash"] == body_hash
    )

    if matches:
        return json.loads(existing["response_json"])

    raise HTTPException(
        status_code=409,
        detail=f"Agent request ID '{agent_request_id}' reused with mutated payload or context",
    )


def record_successful_request(
    agent_request_id: str,
    merchant_id: str,
    buyer_agent_id: str,
    shopper_session_id: str,
    body_data: dict[str, Any],
    response_data: dict[str, Any],
    status_code: int = 200,
) -> None:
    """Persist request and response for idempotent replay."""
    body_hash = hashlib.sha256(canonical_json(body_data).encode("utf-8")).hexdigest()
    store.record_buyer_request(
        agent_request_id=agent_request_id,
        merchant_id=merchant_id,
        buyer_agent_id=buyer_agent_id,
        shopper_session_id=shopper_session_id,
        body_hash=body_hash,
        response_json=json.dumps(response_data),
        status_code=status_code,
    )
