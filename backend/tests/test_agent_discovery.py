"""Tests for Gate A4b: SDK-less agent discovery manifest and Schema.org JSON-LD catalog."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import catalog
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
    # Derived from the catalog rather than pinned to a literal. A hardcoded 43
    # asserts only that nobody has edited data/catalog.json, which is not a
    # property worth defending — and it fails for the wrong reason (a stale
    # number) the moment the merchant adds a product.
    expected = len(catalog.load_catalog())
    assert data["total_products"] == expected
    assert len(data["products"]) == expected

    for p in data["products"]:
        assert "sku" in p
        assert "name" in p
        assert "category" in p
        assert isinstance(p["price_paise"], int) and p["price_paise"] > 0
        assert p["currency"] == "INR"
        # Assert the endpoint AGREES with the catalog, not that everything is
        # always available. The previous form ("in_stock is True" for every row)
        # only passed while availability was hard-coded; it would have gone on
        # passing with a row the merchant genuinely cannot ship.
        assert p["in_stock"] is (catalog.available_stock(p["sku"]) > 0)
    assert any(p["in_stock"] for p in data["products"]), "catalog cannot be entirely empty"


def test_public_agent_catalog_jsonld_endpoint(client: TestClient):
    resp = client.get("/agent-commerce/v1/catalog/jsonld")
    assert resp.status_code == 200
    data = resp.json()

    assert data["@context"] == "https://schema.org/"
    assert data["@type"] == "ItemList"
    assert data["numberOfItems"] == len(catalog.load_catalog())

    items = data["itemListElement"]
    assert len(items) == len(catalog.load_catalog())

    for item in items:
        assert item["@type"] == "Product"
        assert item["sku"].startswith("SKU-")
        assert len(item["name"]) > 0

        # Verify Offer conforms to Schema.org without margin/cost fields
        offer = item["offers"]
        assert offer["@type"] == "Offer"
        assert float(offer["price"]) > 0
        assert offer["priceCurrency"] == "INR"
        expected_availability = (
            "https://schema.org/InStock"
            if catalog.available_stock(item["sku"]) > 0
            else "https://schema.org/OutOfStock"
        )
        assert offer["availability"] == expected_availability

        # Explicitly assert no cost or margin fields
        assert "cost" not in item
        assert "margin" not in item
        assert "profit" not in item
        assert "cost" not in offer
        assert "margin" not in offer

        # Verify Schema.org additionalProperty and isRelatedTo (WO-5)
        assert "additionalProperty" in item
        prop_names = {p["name"] for p in item["additionalProperty"]}
        assert "category" in prop_names
        assert "tags" in prop_names
        assert "available_stock" in prop_names
        for prop in item["additionalProperty"]:
            assert prop["@type"] == "PropertyValue"

    # Verify at least one item has related product recommendations
    has_related = any("isRelatedTo" in item for item in items)
    assert has_related, "At least one product must have isRelatedTo recommendations"
    for item in items:
        if "isRelatedTo" in item:
            for rel in item["isRelatedTo"]:
                assert rel["@type"] == "Product"
                assert rel["sku"].startswith("SKU-")
                assert len(rel["name"]) > 0


def test_ucp_manifest_endpoint(client: TestClient):
    for path in ("/.well-known/ucp", "/.well-known/ucp.json"):
        resp = client.get(path)
        assert resp.status_code == 200
        data = resp.json()
        assert data["protocol"] == "ucp/1.0"
        assert data["spec_alignment"]["standard"] == "Universal Commerce Protocol"
        assert data["spec_alignment"]["mandate_profile"] == "ap2_mandate_compatible"
        assert data["merchant"]["id"] == "merchant_freshbasket"
        assert data["endpoints"]["mcp"] == "/agent-commerce/mcp"


def test_permissions_policy_summary_endpoint(client: TestClient):
    resp = client.get("/agent-commerce/v1/permissions/policy-summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "money_in" in data
    assert "money_out" in data

    money_in = data["money_in"]
    assert money_in["merchant_id"] == "merchant_freshbasket"
    assert money_in["max_order_paise"] == 800000
    assert money_in["currency"] == "INR"
    assert "eggs" in money_in["blocked_tags"] or "egg" in money_in["blocked_tags"]
    assert money_in["action_name"] == "create_payment_link"

    money_out = data["money_out"]
    assert money_out["enabled"] is True
    assert money_out["max_refund_paise"] == 50000
    assert money_out["window_days"] == 30
    assert money_out["daily_cap_paise"] == 200000
    assert "fraud" in money_out["escalate_reasons"]
    assert money_out["action_name"] == "refund"


def test_gateway_root_endpoint_html_and_json(client: TestClient):
    # HTML request from a browser
    resp_html = client.get("/", headers={"accept": "text/html"})
    assert resp_html.status_code == 200
    assert "Action Firewall" in resp_html.text
    assert "Razorpay AI Buildathon" in resp_html.text
    assert "/docs" in resp_html.text
    assert "/health" in resp_html.text

    # JSON request from an API caller
    resp_json = client.get("/", headers={"accept": "application/json"})
    assert resp_json.status_code == 200
    data = resp_json.json()
    assert data["status"] == "ok"
    assert "Action Firewall" in data["service"]
    assert data["endpoints"]["health"] == "/health"
    assert data["endpoints"]["docs"] == "/docs"
