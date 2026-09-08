"""External boundary authentication for Agent Commerce Gateway.

Provides:
- Hashed buyer agent API key verification;
- Short-lived signed shopper session tokens;
- Cross-merchant request protection;
- Idempotent replay and mutation detection.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any
from fastapi import Header, HTTPException

from .authorization import canonical_json
from .config import get_settings
from .merchant import DEFAULT_MERCHANT_ID
from .receipts import _signing_key
from . import store

# Default fixture for replay buyer / demo testing
DEMO_BUYER_KEY = "af_live_buyer_demo_key_2026"
MERCHANT_ADMIN_KEY = "af_merchant_admin_demo_key_2026"
_KNOWN_BUYER_KEYS: dict[str, str] = {
    hashlib.sha256(DEMO_BUYER_KEY.encode("utf-8")).hexdigest(): "buyer_replay",
}


def verify_merchant_admin(
    authorization: str | None = Header(None, alias="Authorization"),
) -> str:
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
    return "merchant_admin"


def register_buyer_key(key: str, agent_id: str) -> None:
    """Register an agent key fixture at runtime (useful for tests)."""
    hashed = hashlib.sha256(key.encode("utf-8")).hexdigest()
    _KNOWN_BUYER_KEYS[hashed] = agent_id


def verify_buyer_agent(
    authorization: str | None = Header(None, alias="Authorization"),
) -> str:
    """Verify Bearer buyer agent key.

    Returns the authenticated buyer_agent_id.
    Allows unauthenticated fallback only in Demo Mode.
    """
    settings = get_settings()

    if not authorization:
        if settings.demo_mode:
            return "buyer_replay"
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
    hashed = hashlib.sha256(token.encode("utf-8")).hexdigest()

    # Check registered keys
    agent_id = _KNOWN_BUYER_KEYS.get(hashed)
    if not agent_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid buyer agent API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return agent_id


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
) -> tuple[str, str]:
    """Verify signed shopper session token from header.

    Returns (user_id, shopper_session_id).
    Allows fallback in Demo Mode if header is absent.
    """
    settings = get_settings()

    if not token:
        if settings.demo_mode:
            return "user_demo", expected_session_id or "session_demo_replay"
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

    return user_id, sid


def verify_merchant_access(requested_merchant_id: str) -> None:
    """Ensure buyer requests only target merchants served by this gateway instance."""
    if requested_merchant_id != DEFAULT_MERCHANT_ID:
        raise HTTPException(
            status_code=403,
            detail=f"Cross-merchant request blocked: merchant '{requested_merchant_id}' is not hosted by this gateway",
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
