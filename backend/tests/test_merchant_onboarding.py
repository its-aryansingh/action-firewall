"""Unit tests for Merchant Onboarding, Razorpay connection, and Kill Switch (Gate A4)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
import httpx

from app.channel_policy import DEFAULT_CHANNEL_POLICY, evaluate_channel_policy
from app.config import get_settings
from app.main import app
from app.merchant import (
    DEFAULT_MERCHANT_ID,
    DEFAULT_MERCHANT_NAME,
    get_catalog_categories,
    reset_merchant_state,
)


@pytest.fixture(autouse=True)
def clean_merchant_state(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "merchant.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("GATEWAY_MODE", "demo")
    get_settings.cache_clear()
    reset_merchant_state()
    yield
    reset_merchant_state()


@pytest.fixture
def client():
    return TestClient(app)


def test_refuse_live_razorpay_keys(client: TestClient):
    """Assert live keys are strictly rejected with 400."""
    resp = client.post(
        "/merchant/connect/razorpay",
        json={"key_id": "rzp_live_dummy", "key_secret": "sec_dummy"},
    )
    assert resp.status_code == 400
    assert "Live keys are refused" in resp.json()["detail"]


def test_refuse_empty_secret(client: TestClient):
    """Assert empty secret is rejected."""
    resp = client.post(
        "/merchant/connect/razorpay",
        json={"key_id": "rzp_test_dummy", "key_secret": "   "},
    )
    assert resp.status_code == 400
    assert "Key Secret is required" in resp.json()["detail"]


def test_razorpay_auth_failure_rejected(client: TestClient):
    """Assert 401/403 from Razorpay returns 400 invalid credentials."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 401
    mock_resp.text = '{"error": {"description": "Authentication failed"}}'

    with patch.object(httpx.Client, "get", return_value=mock_resp):
        resp = client.post(
            "/merchant/connect/razorpay",
            json={"key_id": "rzp_test_mock", "key_secret": "invalidsecret"},
        )
        assert resp.status_code == 400
        assert "Razorpay authentication failed" in resp.json()["detail"]


def test_razorpay_test_mode_successful_connection(client: TestClient):
    """Assert valid rzp_test_ key connects, masks secrets, and updates state."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"count": 0, "items": []}

    with patch.object(httpx.Client, "get", return_value=mock_resp):
        resp = client.post(
            "/merchant/connect/razorpay",
            json={"key_id": "rzp_test_validkey", "key_secret": "dummy_secret_val"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["merchant_name"] == DEFAULT_MERCHANT_NAME
        assert data["key_id_masked"].startswith("rzp_test_...")
        assert data["key_id_masked"].endswith("dkey")
        assert "dummy_secret_val" not in data["key_secret_masked"]
        assert data["message"] == "Connected to Razorpay Test Mode"

    # Verify status endpoint reflects connection
    status_resp = client.get("/merchant/onboarding/status")
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["store_readiness"] == "READY_FOR_AI_BUYERS"
    assert status["razorpay_connected"] is True
    assert status["ai_channel_active"] is True


def test_onboarding_status_structure(client: TestClient):
    """Assert onboarding status returns complete merchant information."""
    resp = client.get("/merchant/onboarding/status")
    assert resp.status_code == 200
    data = resp.json()

    assert data["merchant_id"] == DEFAULT_MERCHANT_ID
    assert data["merchant_name"] == DEFAULT_MERCHANT_NAME
    assert "catalog_summary" in data
    assert data["catalog_summary"]["total_products"] > 0
    assert data["catalog_summary"]["in_stock_count"] > 0
    assert len(data["catalog_summary"]["categories"]) > 0

    assert "channel_policy" in data
    assert "allowed_categories" in data["channel_policy"]
    assert "max_order_paise" in data["channel_policy"]


def test_kill_switch_toggle_and_policy_enforcement(client: TestClient):
    """Assert AI channel Kill Switch toggles state and immediately blocks purchases."""
    # 1. Verify channel initially active and policy passes
    init_dec = evaluate_channel_policy(DEFAULT_MERCHANT_ID)
    assert init_dec.allowed is True

    # 2. Toggle AI channel OFF
    toggle_resp = client.post("/merchant/channel-policy/toggle", json={"enabled": False})
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["ai_channel_active"] is False
    assert "OFF" in toggle_resp.json()["message"]

    # 3. Verify evaluate_channel_policy is immediately blocked by kill switch
    blocked_dec = evaluate_channel_policy(DEFAULT_MERCHANT_ID)
    assert blocked_dec.allowed is False
    assert blocked_dec.code == "BLOCK_MERCHANT_AI_CHANNEL_DISABLED"
    assert "kill switch" in blocked_dec.reason.lower()

    # 4. Status reflects inactive channel
    status_resp = client.get("/merchant/onboarding/status")
    assert status_resp.json()["ai_channel_active"] is False
    assert status_resp.json()["store_readiness"] == "CONFIGURING"

    # 5. Toggle AI channel back ON
    toggle_resp2 = client.post("/merchant/channel-policy/toggle", json={"enabled": True})
    assert toggle_resp2.status_code == 200
    assert toggle_resp2.json()["ai_channel_active"] is True
    assert "ON" in toggle_resp2.json()["message"]

    # 6. Channel policy passes again
    restored_dec = evaluate_channel_policy(DEFAULT_MERCHANT_ID)
    assert restored_dec.allowed is True


def test_get_catalog_categories(client: TestClient):
    """Assert dynamic categories match catalog items."""
    resp = client.get("/merchant/catalog/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert data["merchant_id"] == DEFAULT_MERCHANT_ID
    assert data["count"] == len(data["categories"])
    assert "pantry" in data["categories"]
    assert "dairy" in data["categories"]
    assert data["categories"] == get_catalog_categories()


def test_update_channel_policy(client: TestClient):
    """Assert channel policy parameters can be updated."""
    # Snapshot what is actually there. The previous version restored a
    # hardcoded list instead, so once this test had run, every later test in
    # the session saw a stale policy — and any category added to the real
    # policy silently vanished mid-suite. Restoring a literal is not restoring.
    orig_max = DEFAULT_CHANNEL_POLICY["max_order_paise"]
    orig_categories = list(DEFAULT_CHANNEL_POLICY["allowed_categories"])
    orig_substitutions = DEFAULT_CHANNEL_POLICY.get("substitutions_allowed", True)
    try:
        resp = client.post(
            "/merchant/channel-policy",
            json={
                "allowed_categories": ["dairy", "produce"],
                "max_order_rupees": 2500.0,
                "substitutions_allowed": False,
            },
        )
        assert resp.status_code == 200
        policy = resp.json()["policy"]
        assert policy["allowed_categories"] == ["dairy", "produce"]
        assert policy["max_order_paise"] == 250_000
        assert policy["substitutions_allowed"] is False
    finally:
        # Restore
        DEFAULT_CHANNEL_POLICY["max_order_paise"] = orig_max
        DEFAULT_CHANNEL_POLICY["allowed_categories"] = orig_categories
        DEFAULT_CHANNEL_POLICY["substitutions_allowed"] = orig_substitutions
