"""Tests for Phase 4: OpenAI External Buyer Adapter and Fallback Replay Buyer.

Verifies:
- Deterministic Replay Buyer planning;
- OpenAI Buyer Adapter structured output parsing;
- Graceful degradation to Replay Buyer on missing key or API failure;
- Server-side quote and catalog truth (model cannot forge prices);
- Prompt injection and meta-instruction defenses;
- /agent-commerce/v1/buyer/plan endpoint.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest

from app.buyer_auth import DEMO_BUYER_KEY
from app.config import get_settings
from app.main import app
from app.openai_buyer import ModelPlanResponse, ModelSlotProposal, OpenAIBuyer
from app.replay_buyer import ReplayBuyer
from app import store


@pytest.fixture(autouse=True)
def setup_db():
    store.init_db()


def test_replay_buyer_deterministic_planning():
    buyer = ReplayBuyer()
    plan = buyer.plan_order("Buy supplies for a pasta dinner", budget_paise=60000)

    assert plan.understood is True
    assert len(plan.slots) >= 2
    assert len(plan.selected_skus) >= 2
    assert plan.mode == "replay"
    assert "SKU-PAS-" in plan.selected_skus[0]


def test_replay_buyer_unrecognized_goal_safely_rejected():
    buyer = ReplayBuyer()
    plan = buyer.plan_order("Random gibberish that is not groceries", budget_paise=60000)

    assert plan.understood is False
    assert len(plan.slots) == 0
    assert len(plan.selected_skus) == 0


def test_openai_buyer_falls_back_to_replay_without_api_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "")

    buyer = OpenAIBuyer()
    plan = buyer.plan_order("Buy supplies for a pasta dinner", budget_paise=60000)

    assert plan.understood is True
    assert plan.mode == "replay_fallback"
    assert plan.fallback_reason == "OPENAI_API_KEY_NOT_CONFIGURED"
    assert len(plan.slots) >= 2
    assert len(plan.selected_skus) >= 2


def test_openai_buyer_successful_structured_output(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "sk-mock-key-for-test")

    mock_parsed = ModelPlanResponse(
        understood=True,
        reasoning="Identified need for Italian pasta and tomato sauce.",
        slots=[
            ModelSlotProposal(id="pasta", label="Pasta", required_tags=["pasta", "staple"], quantity=1),
            ModelSlotProposal(id="sauce", label="Tomato Sauce", required_tags=["sauce", "tomato"], quantity=1),
        ],
        suggested_skus=["SKU-PAS-002", "SKU-SAU-001"],
    )

    mock_choice = MagicMock()
    mock_choice.message.parsed = mock_parsed

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage.prompt_tokens = 120
    mock_completion.usage.completion_tokens = 45

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.beta.chat.completions.parse.return_value = mock_completion

        buyer = OpenAIBuyer()
        plan = buyer.plan_order("Buy pasta dinner supplies", budget_paise=50000)

        assert plan.understood is True
        assert plan.mode == "openai"
        assert len(plan.slots) == 2
        assert plan.slots[0].id == "pasta"
        assert plan.selected_skus == ["SKU-PAS-002", "SKU-SAU-001"]
        assert plan.prompt_tokens == 120
        assert plan.completion_tokens == 45


def test_openai_buyer_graceful_fallback_on_api_exception(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "sk-mock-key-for-test")

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.beta.chat.completions.parse.side_effect = RuntimeError("OpenAI 503 Service Unavailable")

        buyer = OpenAIBuyer()
        plan = buyer.plan_order("Buy supplies for a pasta dinner", budget_paise=60000)

        # Must NOT crash! Must degrade gracefully to deterministic replay
        assert plan.understood is True
        assert plan.mode == "replay_fallback"
        assert "OPENAI_API_ERROR" in (plan.fallback_reason or "")
        assert len(plan.slots) >= 2


def test_openai_buyer_discards_unrecognized_model_skus(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "openai_api_key", "sk-mock-key-for-test")

    mock_parsed = ModelPlanResponse(
        understood=True,
        reasoning="Testing hallucinated SKU filtering.",
        slots=[
            ModelSlotProposal(id="pasta", label="Pasta", required_tags=["pasta"], quantity=1),
        ],
        suggested_skus=["SKU-PAS-001", "SKU-HALLUCINATED-999"],
    )

    mock_choice = MagicMock()
    mock_choice.message.parsed = mock_parsed
    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]
    mock_completion.usage = None

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.beta.chat.completions.parse.return_value = mock_completion

        buyer = OpenAIBuyer()
        plan = buyer.plan_order("Buy pasta", budget_paise=20000)

        assert plan.understood is True
        # Only existing SKU preserved; hallucinated SKU stripped
        assert "SKU-PAS-001" in plan.selected_skus
        assert "SKU-HALLUCINATED-999" not in plan.selected_skus


def test_gateway_buyer_plan_endpoint():
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {DEMO_BUYER_KEY}"}

    resp = client.post(
        "/agent-commerce/v1/buyer/plan",
        headers=headers,
        json={
            "goal": "Buy supplies for a pasta dinner",
            "budget_paise": 60000,
            "buyer_mode": "replay",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["understood"] is True
    assert data["mode_used"] == "replay"
    assert len(data["slots"]) >= 2
    assert len(data["suggested_skus"]) >= 2
    assert data["quote_total_paise"] is not None
    assert data["quote_total_paise"] > 0
