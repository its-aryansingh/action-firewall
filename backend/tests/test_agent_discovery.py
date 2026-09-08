"""Tests for Gate A4b: SDK-less agent discovery manifest and Schema.org JSON-LD catalog."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app import store


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "discovery.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    get_settings.cache_clear()
    store.init_db()
    return TestClient(app)


def test_agent_commerce_well_known_manifest(client: TestClient):
    resp = client.get("/.well-known/agent-commerce.json")
    assert resp.status_code == 200
    data = resp.json()

    assert data["version"] == "0.1"
    assert "Action Firewall" in data["service"]
    assert data["merchant"]["id"] == "merchant_freshbasket"
    assert data["merchant"]["display_name"] == "FreshBasket for Business"
    assert data["currency"] == "INR"

    endpoints = data["endpoints"]
    assert endpoints["catalog"] == "/agent-commerce/v1/catalog"
    assert endpoints["catalog_jsonld"] == "/agent-commerce/v1/catalog/jsonld"
    assert endpoints["mcp"] == "/agent-commerce/mcp"

    capabilities = data["capabilities"]
    assert "catalog_discovery" in capabilities
    assert "purchase_scope_approval" in capabilities
    assert "policy_gated_checkout" in capabilities

    assert "deterministic authorization gate" in data["notes"]


def test_public_agent_catalog_endpoint(client: TestClient):
    resp = client.get("/agent-commerce/v1/catalog")
    assert resp.status_code == 200
    data = resp.json()

    assert data["merchant_id"] == "merchant_freshbasket"
    assert data["total_products"] == 43
    assert len(data["products"]) == 43

    for p in data["products"]:
        assert "sku" in p
        assert "name" in p
        assert "category" in p
        assert isinstance(p["price_paise"], int) and p["price_paise"] > 0
        assert p["currency"] == "INR"
        assert p["in_stock"] is True


def test_public_agent_catalog_jsonld_endpoint(client: TestClient):
    resp = client.get("/agent-commerce/v1/catalog/jsonld")
    assert resp.status_code == 200
    data = resp.json()

    assert data["@context"] == "https://schema.org/"
    assert data["@type"] == "ItemList"
    assert data["numberOfItems"] == 43

    items = data["itemListElement"]
    assert len(items) == 43

    for item in items:
        assert item["@type"] == "Product"
        assert item["sku"].startswith("SKU-")
        assert len(item["name"]) > 0

        # Verify Offer conforms to Schema.org without margin/cost fields
        offer = item["offers"]
        assert offer["@type"] == "Offer"
        assert float(offer["price"]) > 0
        assert offer["priceCurrency"] == "INR"
        assert offer["availability"] == "https://schema.org/InStock"

        # Explicitly assert no cost or margin fields
        assert "cost" not in item
        assert "margin" not in item
        assert "profit" not in item
        assert "cost" not in offer
        assert "margin" not in offer
