"""Tests for Demo Slippage Controls and Cost Model Endpoints.

Verifies:
1. GET /demo/slippage/state returns current moved SKUs;
2. POST /demo/slippage/deplete takes stock to 0;
3. POST /demo/slippage/reset restores pristine catalog stock;
4. GET /metrics/cost-model exposes comparison and sensitivity sweep.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import catalog, store


@pytest.fixture(autouse=True)
def init_test_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test_slippage_api.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    store.init_db()
    catalog.reset_stock()
    yield
    catalog.reset_stock()


def test_slippage_deplete_and_reset_flow():
    client = TestClient(app)
    sku = "SKU-PAS-001"

    # Deplete stock
    resp = client.post("/agent-commerce/v1/demo/slippage/deplete", json={"sku": sku})
    assert resp.status_code == 200
    data = resp.json()
    assert data["sku"] == sku
    assert data["stock_now"] == 0

    # Verify state reflects change
    state_resp = client.get("/agent-commerce/v1/demo/slippage/state")
    assert state_resp.status_code == 200
    state = state_resp.json()
    assert any(item["sku"] == sku and item["live_stock"] == 0 for item in state)

    # Reset all
    reset_resp = client.post("/agent-commerce/v1/demo/slippage/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["action"] == "reset"

    # State now empty
    state_after = client.get("/agent-commerce/v1/demo/slippage/state").json()
    assert len(state_after) == 0


def test_cost_model_metrics_endpoint():
    client = TestClient(app)
    resp = client.get("/agent-commerce/v1/metrics/cost-model")
    assert resp.status_code == 200
    data = resp.json()
    assert "comparison" in data
    assert "sensitivity" in data
    assert data["comparison"]["lowest_cost"] == "action_firewall"
    assert data["sensitivity"]["ordering_is_robust"] is True
