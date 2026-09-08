"""Test suite for Phase 3: External Boundary Authentication.

Verifies:
- Buyer agent API key verification;
- Signed, short-lived shopper sessions;
- Cross-merchant request protection;
- Idempotent exact replay;
- Mutated replay conflict (409);
- Write rate limiting (429);
- Demo mode fallback semantics.
"""
from __future__ import annotations

import os
import time
from fastapi.testclient import TestClient
import pytest

from app.buyer_auth import (
    DEMO_BUYER_KEY,
    AgentPrincipal,
    MerchantPrincipal,
    ShopperPrincipal,
    _KNOWN_BUYER_KEYS,
    mint_shopper_session,
    register_buyer_key,
    reset_buyer_keys,
    revoke_buyer_agent,
    revoke_buyer_key,
)
from app.config import get_settings
from app.main import app
from app.rate_limit import get_limiter
from app import store


@pytest.fixture(autouse=True)
def init_test_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_buyer_auth.db")
    monkeypatch.setenv("DB_PATH", db_file)
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()
    store.init_db()
    get_limiter().reset()
    reset_buyer_keys()
    yield
    get_limiter().reset()
    reset_buyer_keys()
    get_settings.cache_clear()


def test_valid_bearer_buyer_key_succeeds():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {DEMO_BUYER_KEY}"}

    resp = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_auth_001",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": "session_auth_01",
            "natural_language_intent": "Buy pasta and sauce",
            "budget_paise": 60000,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["buyer_agent_id"] == "buyer_replay"


def test_invalid_bearer_buyer_key_fails():
    client = TestClient(app)
    headers = {"Authorization": "Bearer invalid_secret_key_12345"}

    resp = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_auth_bad_key",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": "session_auth_01",
            "natural_language_intent": "Buy pasta and sauce",
            "budget_paise": 60000,
        },
    )
    assert resp.status_code == 401
    assert "Invalid buyer agent API key" in resp.json()["detail"]


def test_custom_registered_buyer_key():
    register_buyer_key("test_gemini_key_xyz", "buyer_gemini_flash")
    client = TestClient(app)
    headers = {"Authorization": "Bearer test_gemini_key_xyz"}

    resp = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_auth_custom_key",
            "buyer_agent_id": "buyer_gemini_flash",
            "shopper_session_id": "session_auth_02",
            "natural_language_intent": "Buy pasta and sauce",
            "budget_paise": 60000,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["buyer_agent_id"] == "buyer_gemini_flash"


def test_shopper_session_minting_and_valid_verification():
    client = TestClient(app)

    # 1. Mint session via /sessions endpoint
    mint_resp = client.post(
        "/agent-commerce/v1/sessions",
        json={"user_id": "user_shopper_1", "ttl_seconds": 1800},
    )
    assert mint_resp.status_code == 200
    s_data = mint_resp.json()
    token = s_data["token"]
    session_id = s_data["session_id"]
    assert token.startswith("sess_v1.")

    # 2. Use token in request
    headers = {
        "Authorization": f"Bearer {DEMO_BUYER_KEY}",
        "X-Shopper-Session": token,
    }
    intent_resp = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_session_valid",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": session_id,
            "natural_language_intent": "Buy pasta and sauce",
            "budget_paise": 60000,
        },
    )
    assert intent_resp.status_code == 200
    assert intent_resp.json()["shopper_session_id"] == session_id


def test_tampered_shopper_session_rejected():
    client = TestClient(app)
    _, valid_token = mint_shopper_session(user_id="user_legit")
    tampered_token = valid_token[:-4] + "dead"

    headers = {
        "Authorization": f"Bearer {DEMO_BUYER_KEY}",
        "X-Shopper-Session": tampered_token,
    }
    resp = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_session_tampered",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": "session_any",
            "natural_language_intent": "Buy pasta and sauce",
            "budget_paise": 60000,
        },
    )
    assert resp.status_code == 401
    assert "Invalid shopper session signature" in resp.json()["detail"]


def test_expired_shopper_session_rejected():
    client = TestClient(app)
    # Mint token with negative TTL (already expired)
    sid, expired_token = mint_shopper_session(user_id="user_expired", ttl_seconds=-10)

    headers = {
        "Authorization": f"Bearer {DEMO_BUYER_KEY}",
        "X-Shopper-Session": expired_token,
    }
    resp = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_session_expired",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": sid,
            "natural_language_intent": "Buy pasta and sauce",
            "budget_paise": 60000,
        },
    )
    assert resp.status_code == 401
    assert "Shopper session expired" in resp.json()["detail"]


def test_cross_merchant_request_blocked_with_403():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {DEMO_BUYER_KEY}"}

    resp = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_cross_merchant",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": "session_demo",
            "merchant_id": "merchant_rogue_unhosted",
            "natural_language_intent": "Buy groceries",
            "budget_paise": 50000,
        },
    )
    assert resp.status_code == 403
    assert "Cross-merchant request blocked" in resp.json()["detail"]


def test_idempotent_exact_replay_returns_cached_response():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {DEMO_BUYER_KEY}"}

    body = {
        "agent_request_id": "req_idem_001",
        "buyer_agent_id": "buyer_replay",
        "shopper_session_id": "session_idem",
        "natural_language_intent": "Buy pasta dinner supplies",
        "budget_paise": 60000,
    }

    # First call
    res1 = client.post("/agent-commerce/v1/intents", headers=headers, json=body)
    assert res1.status_code == 200
    data1 = res1.json()

    # Second call (exact replay)
    res2 = client.post("/agent-commerce/v1/intents", headers=headers, json=body)
    assert res2.status_code == 200
    data2 = res2.json()

    assert data1["intent_id"] == data2["intent_id"]
    assert data1["draft_envelope"]["id"] == data2["draft_envelope"]["id"]


def test_mutated_replay_raises_409_conflict():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {DEMO_BUYER_KEY}"}

    body = {
        "agent_request_id": "req_conflict_001",
        "buyer_agent_id": "buyer_replay",
        "shopper_session_id": "session_conflict",
        "natural_language_intent": "Buy pasta dinner supplies",
        "budget_paise": 60000,
    }

    res1 = client.post("/agent-commerce/v1/intents", headers=headers, json=body)
    assert res1.status_code == 200

    # Mutate payload with the same agent_request_id
    mutated_body = dict(body, budget_paise=99000)
    res2 = client.post("/agent-commerce/v1/intents", headers=headers, json=mutated_body)
    assert res2.status_code == 409
    assert "reused with mutated payload" in res2.json()["detail"]


def test_rate_limiter_blocks_burst():
    from app.buyer_auth import register_buyer_key
    register_buyer_key("key_rate_test", "buyer_rate_test")
    client = TestClient(app)
    headers = {"Authorization": "Bearer key_rate_test"}

    # Run requests up to limit
    for i in range(30):
        resp = client.post(
            "/agent-commerce/v1/intents",
            headers=headers,
            json={
                "agent_request_id": f"req_rate_{i}",
                "buyer_agent_id": "buyer_rate_test",
                "shopper_session_id": "session_rate_test",
                "natural_language_intent": "Buy supplies for pasta dinner",
                "budget_paise": 60000,
            },
        )
        assert resp.status_code == 200

    # 31st request from same session exceeds session limit (30/min)
    resp_blocked = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_rate_overflow",
            "buyer_agent_id": "buyer_rate_test",
            "shopper_session_id": "session_rate_test",
            "natural_language_intent": "Buy supplies for pasta dinner",
            "budget_paise": 60000,
        },
    )
    assert resp_blocked.status_code == 429
    assert "rate limit exceeded" in resp_blocked.json()["detail"].lower()
    assert "Retry-After" in resp_blocked.headers


def test_revoked_key_fails_closed():
    key = "test_key_to_be_revoked_123"
    register_buyer_key(key, "buyer_transient")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {key}"}

    # First verify it succeeds
    resp1 = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_rev_01",
            "shopper_session_id": "session_rev_01",
            "natural_language_intent": "Buy pasta dinner supplies",
            "budget_paise": 60000,
        },
    )
    assert resp1.status_code == 200

    # Revoke key
    revoke_buyer_key(key)

    # Subsequent request fails closed with 401
    resp2 = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_rev_02",
            "shopper_session_id": "session_rev_01",
            "natural_language_intent": "Buy pasta dinner supplies",
            "budget_paise": 60000,
        },
    )
    assert resp2.status_code == 401
    assert "Revoked buyer agent API key" in resp2.json()["detail"]


def test_revoked_agent_id_fails_closed():
    key = "test_key_agent_rev_456"
    agent_id = "buyer_revocable_agent"
    register_buyer_key(key, agent_id)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {key}"}

    resp1 = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_agent_rev_01",
            "shopper_session_id": "session_rev_02",
            "natural_language_intent": "Buy pasta dinner supplies",
            "budget_paise": 60000,
        },
    )
    assert resp1.status_code == 200

    # Revoke all keys for this agent
    revoke_buyer_agent(agent_id)

    resp2 = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_agent_rev_02",
            "shopper_session_id": "session_rev_02",
            "natural_language_intent": "Buy pasta dinner supplies",
            "budget_paise": 60000,
        },
    )
    assert resp2.status_code == 401
    assert "Revoked buyer agent API key" in resp2.json()["detail"]


def test_cross_merchant_agent_key_fails_with_403():
    foreign_key = "test_foreign_merchant_key_789"
    register_buyer_key(foreign_key, "buyer_foreign", merchant_id="merchant_other_chain")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {foreign_key}"}

    # Request targets this gateway's merchant (merchant_demo), but agent key is scoped to merchant_other_chain
    resp = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_cross_key_01",
            "shopper_session_id": "session_cross_key",
            "natural_language_intent": "Buy pasta dinner supplies",
            "merchant_id": "merchant_demo",
            "budget_paise": 60000,
        },
    )
    assert resp.status_code == 403
    assert "Cross-merchant request blocked" in resp.json()["detail"]
    assert "merchant_other_chain" in resp.json()["detail"]


def test_body_supplied_buyer_agent_id_override_rejected_with_403():
    client = TestClient(app)
    # Bearer key authenticates as buyer_replay
    headers = {"Authorization": f"Bearer {DEMO_BUYER_KEY}"}

    # Body attempts to spoof/override identity to a different agent ID
    resp = client.post(
        "/agent-commerce/v1/intents",
        headers=headers,
        json={
            "agent_request_id": "req_override_spoof_01",
            "buyer_agent_id": "attacker_spoofed_buyer",
            "shopper_session_id": "session_spoof_01",
            "natural_language_intent": "Buy pasta dinner supplies",
            "budget_paise": 60000,
        },
    )
    assert resp.status_code == 403
    assert "Identity mismatch" in resp.json()["detail"]
    assert "Body overrides are prohibited" in resp.json()["detail"]


def test_keys_are_hashed_at_rest():
    test_key = "plain_secret_key_never_stored_in_plaintext_xyz"
    register_buyer_key(test_key, "buyer_hashed_check")

    # The plaintext key must NOT exist as any key or value in the registered keys dictionary
    assert test_key not in _KNOWN_BUYER_KEYS
    for k, principal in _KNOWN_BUYER_KEYS.items():
        assert len(k) == 64  # Hex SHA-256 digest
        assert test_key not in str(principal)
        assert principal.key_hash == k


def test_principal_dataclass_behaviors():
    agent = AgentPrincipal(buyer_agent_id="agent_123", merchant_id="merchant_demo")
    assert str(agent) == "agent_123"
    assert agent == "agent_123"
    assert agent.merchant_id == "merchant_demo"
    assert hash(agent) == hash(("agent_123", "merchant_demo", True))

    shopper = ShopperPrincipal(user_id="user_abc", shopper_session_id="sess_xyz")
    assert str(shopper) == "user_abc"
    u, s = shopper
    assert u == "user_abc"
    assert s == "sess_xyz"
    assert shopper[0] == "user_abc"
    assert shopper[1] == "sess_xyz"

    admin = MerchantPrincipal(merchant_id="merchant_demo", role="merchant_admin")
    assert str(admin) == "merchant_demo"
    assert admin == "merchant_admin"
    assert admin == "merchant_demo"
