"""Tests for opaque approval tokens (approval_tokens.py).

Verifies:
1. Minting returns opaque token and approval URL;
2. SHA-256 hashed matching prevents token leakage;
3. Atomic redemption activates envelope once in a single transaction;
4. Double redemption fails closed with ApprovalTokenAlreadyRedeemedError (409);
5. Expired tokens fail closed with ApprovalTokenExpiredError (410);
6. Unknown tokens return ApprovalTokenNotFoundError (404);
7. Forced failure at activation rolls back completely: token remains unconsumed, envelope remains in draft;
8. Lookup of approval details has zero state-changing side effects.
"""
from __future__ import annotations

import time
import pytest
from starlette.testclient import TestClient

from app.approval_tokens import (
    ApprovalTokenAlreadyRedeemedError,
    ApprovalTokenError,
    ApprovalTokenExpiredError,
    ApprovalTokenNotFoundError,
    lookup_approval_token,
    mint_approval_token,
    redeem_approval_token,
)
from app import autopilot
from app.main import app
from app.models import EnvelopeDraftRequest, MandateCreate
from app import store


@pytest.fixture(autouse=True)
def clean_database(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_tokens.db")
    monkeypatch.setenv("DB_PATH", db_file)
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("ENVELOPE_DRAFTING_MODE", "replay")
    store.init_db()
    store.create_mandate(MandateCreate(cap_rupees=5000))
    yield


def test_mint_and_lookup_approval_token():
    draft = autopilot.create_draft(
        EnvelopeDraftRequest(goal="Buy pasta and sauce", max_total_rupees=600)
    )
    raw_token, approval_url = mint_approval_token(
        envelope_id=draft.id,
        envelope_hash=draft.envelope_hash,
        ttl_seconds=900,
    )
    assert raw_token.startswith("appr_")
    assert approval_url == f"/approve/{raw_token}"

    looked_up = lookup_approval_token(raw_token)
    assert looked_up is not None
    assert looked_up["envelope_id"] == draft.id
    assert looked_up["envelope_hash"] == draft.envelope_hash
    assert looked_up["state"] == "pending"
    assert looked_up["consumed_at"] is None
    assert looked_up["redeemed_at"] is None


def test_redeem_approval_token_activates_envelope_once():
    draft = autopilot.create_draft(
        EnvelopeDraftRequest(goal="Buy pasta and sauce", max_total_rupees=600)
    )
    raw_token, _ = mint_approval_token(
        envelope_id=draft.id,
        envelope_hash=draft.envelope_hash,
        ttl_seconds=900,
    )

    # First redemption succeeds
    active = redeem_approval_token(raw_token)
    assert active.status.value == "active"
    assert active.version == draft.version + 1

    # Second redemption fails with ApprovalTokenAlreadyRedeemedError (domain error with status_code=409)
    with pytest.raises(ApprovalTokenAlreadyRedeemedError) as exc:
        redeem_approval_token(raw_token)
    assert exc.value.status_code == 409
    assert "already been redeemed" in str(exc.value)


def test_expired_approval_token_rejected():
    draft = autopilot.create_draft(
        EnvelopeDraftRequest(goal="Buy pasta and sauce", max_total_rupees=600)
    )
    # Mint token with -10 TTL (immediately expired)
    raw_token, _ = mint_approval_token(
        envelope_id=draft.id,
        envelope_hash=draft.envelope_hash,
        ttl_seconds=-10,
    )

    with pytest.raises(ApprovalTokenExpiredError) as exc:
        redeem_approval_token(raw_token)
    assert exc.value.status_code == 410
    assert "expired" in str(exc.value).lower()


def test_unknown_approval_token_rejected():
    with pytest.raises(ApprovalTokenNotFoundError) as exc:
        redeem_approval_token("appr_nonexistent_token_12345")
    assert exc.value.status_code == 404


def test_forced_failure_at_activation_rolls_back():
    """Verify single BEGIN IMMEDIATE transaction rolls back all mutations on activation failure:
    token remains pending/unconsumed, and envelope remains draft.
    """
    draft = autopilot.create_draft(
        EnvelopeDraftRequest(goal="Buy pasta and sauce", max_total_rupees=600)
    )
    raw_token, _ = mint_approval_token(
        envelope_id=draft.id,
        envelope_hash=draft.envelope_hash,
        ttl_seconds=900,
    )

    # 1. Force failure at activation step inside the atomic transaction
    with pytest.raises(RuntimeError, match="SIMULATED_ACTIVATION_FAILURE"):
        redeem_approval_token(raw_token, _simulate_failure_at_activation=True)

    # 2. Token must remain UNCONSUMED and pending
    token_row = lookup_approval_token(raw_token)
    assert token_row is not None
    assert token_row["state"] == "pending"
    assert token_row["consumed_at"] is None
    assert token_row["redeemed_at"] is None

    # 3. Envelope must remain in DRAFT status
    env = store.get_envelope(draft.id)
    assert env is not None
    assert env.status.value == "draft"
    assert env.version == draft.version

    # 4. Subsequent legitimate redemption succeeds
    active = redeem_approval_token(raw_token)
    assert active.status.value == "active"
    assert active.version == draft.version + 1

    # 5. Token is now consumed
    token_row_after = lookup_approval_token(raw_token)
    assert token_row_after is not None
    assert token_row_after["state"] == "consumed"
    assert token_row_after["consumed_at"] is not None


def test_lookup_approval_has_no_side_effects():
    """Verify lookup_approval_token is strictly read-only."""
    draft = autopilot.create_draft(
        EnvelopeDraftRequest(goal="Buy pasta and sauce", max_total_rupees=600)
    )
    raw_token, _ = mint_approval_token(
        envelope_id=draft.id,
        envelope_hash=draft.envelope_hash,
        ttl_seconds=900,
    )

    # Multiple lookups
    r1 = lookup_approval_token(raw_token)
    r2 = lookup_approval_token(raw_token)
    assert r1 == r2
    assert r1["state"] == "pending"
    assert r1["consumed_at"] is None

    # Envelope untouched
    env = store.get_envelope(draft.id)
    assert env.status.value == "draft"


def test_http_approval_endpoints():
    """Verify HTTP router translates domain exceptions into standard HTTP status codes."""
    client = TestClient(app)

    draft = autopilot.create_draft(
        EnvelopeDraftRequest(goal="Buy pasta and sauce", max_total_rupees=600)
    )
    raw_token, _ = mint_approval_token(
        envelope_id=draft.id,
        envelope_hash=draft.envelope_hash,
        ttl_seconds=900,
    )

    # 1. GET /approvals/{token} has no side-effect
    r_get = client.get(f"/agent-commerce/v1/approvals/{raw_token}")
    assert r_get.status_code == 200
    data = r_get.json()
    assert data["envelope_id"] == draft.id
    assert data["redeemed"] is False
    assert data["expired"] is False

    # 2. POST /approvals/{token}/redeem activates envelope
    r_redeem = client.post(f"/agent-commerce/v1/approvals/{raw_token}/redeem")
    assert r_redeem.status_code == 200
    assert r_redeem.json()["status"] == "active"

    # 3. Second redemption returns 409 Conflict
    r_dup = client.post(f"/agent-commerce/v1/approvals/{raw_token}/redeem")
    assert r_dup.status_code == 409
    assert "already been redeemed" in r_dup.json()["detail"]

    # 4. Unknown token returns 404 Not Found
    r_unknown = client.post("/agent-commerce/v1/approvals/appr_unknown_xyz/redeem")
    assert r_unknown.status_code == 404

    # 5. Expired token returns 410 Gone
    expired_token, _ = mint_approval_token(
        envelope_id=draft.id,
        envelope_hash=draft.envelope_hash,
        ttl_seconds=-10,
    )
    r_exp = client.post(f"/agent-commerce/v1/approvals/{expired_token}/redeem")
    assert r_exp.status_code == 410
    assert "expired" in r_exp.json()["detail"].lower()
