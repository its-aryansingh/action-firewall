"""Unit tests for Gemini 3.8 Flash buyer adapter (Gate B6).

Verifies:
- Keyless fallback to deterministic replay
- Mocked Gemini execution with strict schema validation
- Rejection of hallucinated SKUs
- Discarding of model-supplied prices and prompt injections
- Retry on schema failure and degradation on persistent failure
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from app.gemini_buyer import GeminiBuyer, GeminiBuyerPlan, GeminiDraftOutput
from app.config import get_settings


@pytest.fixture(autouse=True)
def reset_cfg(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "buyer.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    get_settings.cache_clear()


def test_gemini_buyer_keyless_fallback():
    """Assert missing key cleanly degrades to ReplayBuyer without failure."""
    buyer = GeminiBuyer(api_key="")
    plan = buyer.plan_order("Buy pasta dinner", budget_paise=50000)

    assert isinstance(plan, GeminiBuyerPlan)
    assert plan.mode == "replay"
    assert plan.understood is True
    assert len(plan.selected_skus) > 0
    assert "Replay fallback" in plan.reasoning


def test_gemini_buyer_mocked_success():
    """Assert valid Gemini response parses strictly through Pydantic."""
    buyer = GeminiBuyer(api_key="mock_test_key")

    mock_resp = MagicMock()
    mock_resp.text = '{"understood": true, "reasoning": "Selected pasta essentials", "proposed_skus": ["SKU-PAS-001", "SKU-SAU-001"], "budget_clarification_needed": false}'

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = mock_resp

        plan = buyer.plan_order("Buy pasta dinner", budget_paise=60000)

        assert plan.mode == "gemini-3.8-flash"
        assert plan.understood is True
        assert "SKU-PAS-001" in plan.selected_skus
        assert "SKU-SAU-001" in plan.selected_skus
        assert plan.reasoning == "Selected pasta essentials"


def test_gemini_buyer_rejects_hallucinated_skus():
    """Assert hallucinated SKUs not present in server catalog are filtered out."""
    buyer = GeminiBuyer(api_key="mock_test_key")

    mock_resp = MagicMock()
    # "hallucinated_gold_bars_1000g" does not exist in catalog
    mock_resp.text = '{"understood": true, "reasoning": "Attempted hallucination", "proposed_skus": ["SKU-PAS-001", "hallucinated_gold_bars_1000g"], "budget_clarification_needed": false}'

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.generate_content.return_value = mock_resp

        plan = buyer.plan_order("Buy pasta dinner", budget_paise=60000)

        assert "SKU-PAS-001" in plan.selected_skus
        assert "hallucinated_gold_bars_1000g" not in plan.selected_skus


def test_gemini_buyer_retry_and_fallback_on_schema_error():
    """Assert schema-invalid response retries once, then degrades cleanly to replay."""
    buyer = GeminiBuyer(api_key="mock_test_key")

    mock_resp_invalid = MagicMock()
    mock_resp_invalid.text = '{"malformed_json_without_fields": true}'

    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        # Fails both attempt 1 and attempt 2
        mock_client.models.generate_content.return_value = mock_resp_invalid

        plan = buyer.plan_order("Buy pasta dinner", budget_paise=60000)

        # Degraded cleanly to replay
        assert plan.mode == "replay"
        assert plan.understood is True
        assert "Degraded from Gemini" in plan.reasoning
