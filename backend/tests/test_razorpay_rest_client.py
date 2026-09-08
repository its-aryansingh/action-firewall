"""Tests for RazorpayRESTClient, provider fallback, and REST payment link creation."""
from __future__ import annotations

import json
import pytest
import httpx
from unittest.mock import patch, MagicMock

from app import autopilot, mcp_client, store
from app.mcp_client import (
    ActionOutcomeUnknown,
    MandateViolation,
    RazorpayMCPClient,
    RazorpayRESTClient,
    get_client,
    get_active_provider_mode,
    get_provider_fallback_info,
    reset_provider_fallback,
)
from app.models import (
    ActionState,
    AutopilotExecuteRequest,
    AutopilotScenario,
    EnvelopeActivateRequest,
    EnvelopeDraftRequest,
)


@pytest.fixture(autouse=True)
def clean_provider_state():
    reset_provider_fallback()
    yield
    reset_provider_fallback()


def _make_active_env():
    draft = autopilot.create_draft(
        EnvelopeDraftRequest(goal="Buy supplies for a pasta dinner", max_total_rupees=600)
    )
    return autopilot.activate(
        draft.id,
        EnvelopeActivateRequest(expected_envelope_hash=draft.envelope_hash),
    )


def test_rest_client_init_fails_without_credentials(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "")
    with pytest.raises(RuntimeError, match="requires both RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET"):
        RazorpayRESTClient()


def test_rest_client_list_tools(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_sample")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret_sample")
    client = RazorpayRESTClient()
    tools = client.list_tools()
    assert any(t["name"] == "create_payment_link" for t in tools)


def test_rest_client_successful_payment_link_creation(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test_rest.db"))
    monkeypatch.setenv("PAYMENT_PROVIDER", "razorpay_rest")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "false")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_sample")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret_sample")
    store.init_db()

    env = _make_active_env()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "plink_test_12345",
        "amount": 50000,
        "currency": "INR",
        "status": "created",
        "short_url": "https://rzp.io/i/test12345",
        "description": "Test",
    }

    with patch.object(httpx.Client, "post", return_value=mock_resp):
        res = autopilot.execute(
            AutopilotExecuteRequest(
                envelope_id=env.id,
                expected_envelope_version=env.version,
                expected_envelope_hash=env.envelope_hash,
                session_id="session_test_01",
                purchase_attempt_id="attempt_test_01",
                scenario=AutopilotScenario.NORMAL,
            )
        )

    assert res.action_status is ActionState.ACTION_ISSUED
    assert res.payment_link == "https://rzp.io/i/test12345"
    assert res.provider_mode == "RazorpayRESTClient"


def test_rest_client_timeout_marks_action_unknown(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test_rest.db"))
    monkeypatch.setenv("PAYMENT_PROVIDER", "razorpay_rest")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "false")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_sample")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret_sample")
    store.init_db()

    env = _make_active_env()

    def mock_timeout(*a, **kw):
        raise httpx.ReadTimeout("Connection timed out after dispatch")

    with patch.object(httpx.Client, "post", side_effect=mock_timeout):
        res = autopilot.execute(
            AutopilotExecuteRequest(
                envelope_id=env.id,
                expected_envelope_version=env.version,
                expected_envelope_hash=env.envelope_hash,
                session_id="session_test_02",
                purchase_attempt_id="attempt_test_02",
                scenario=AutopilotScenario.NORMAL,
            )
        )

    assert res.action_status is ActionState.UNKNOWN
    grant = store.get_action_grant(res.grant_id)
    assert grant.state is ActionState.UNKNOWN


def test_mcp_auth_failure_triggers_fallback_to_rest(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test_fallback.db"))
    monkeypatch.setenv("PAYMENT_PROVIDER", "razorpay_mcp")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "false")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_sample")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret_sample")
    store.init_db()

    env = _make_active_env()

    req = httpx.Request("POST", "https://mcp.razorpay.com/mcp")
    resp_401 = httpx.Response(
        401,
        request=req,
        text='{"error":{"code":"BAD_REQUEST_ERROR","description":"Authentication failed"}}',
    )
    auth_err = httpx.HTTPStatusError("401 Unauthorized", request=req, response=resp_401)

    mock_rest_resp = MagicMock()
    mock_rest_resp.status_code = 200
    mock_rest_resp.json.return_value = {
        "id": "plink_fallback_999",
        "amount": 50000,
        "currency": "INR",
        "status": "created",
        "short_url": "https://rzp.io/i/fallback999",
        "description": "Test",
    }

    def mock_post(client_self, url, *a, **kw):
        if "mcp.razorpay.com" in str(url):
            raise auth_err
        return mock_rest_resp

    with patch.object(httpx.Client, "post", autospec=True, side_effect=mock_post):
        res = autopilot.execute(
            AutopilotExecuteRequest(
                envelope_id=env.id,
                expected_envelope_version=env.version,
                expected_envelope_hash=env.envelope_hash,
                session_id="session_test_03",
                purchase_attempt_id="attempt_test_03",
                scenario=AutopilotScenario.NORMAL,
            )
        )

    assert res.action_status is ActionState.ACTION_ISSUED
    assert res.payment_link == "https://rzp.io/i/fallback999"
    assert get_active_provider_mode() == "razorpay_rest"
    fb = get_provider_fallback_info()
    assert fb["active_provider"] == "razorpay_rest"
    assert "Remote MCP auth failed" in str(fb["fallback_reason"])
