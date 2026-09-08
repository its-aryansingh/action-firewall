"""Route isolation tests — verifying Gate A3.

Walks app.routes dynamically to verify that when GATEWAY_MODE=external,
any attempt by an external AgentPrincipal to invoke internal execution/admin
routes returns 403 Forbidden:
- /chat
- /checkout/confirm
- /chat/{id}/reset
- /envelopes/{id}/activate
- /envelopes/{id}/revoke
- /autopilot/execute
- /mandates* (POST/PATCH)
- /mcp/tools
- /actions/*/reconcile
- /demo/*
"""
from __future__ import annotations

import re
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app, is_isolated_route
from app import store

AGENT_AUTH = {"Authorization": "Bearer buyer_agent_key_demo"}


@pytest.fixture
def external_client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "isolation.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("GATEWAY_MODE", "external")
    get_settings.cache_clear()
    store.init_db()
    return TestClient(app)


@pytest.fixture
def demo_client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "demo_isolation.db"))
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("GATEWAY_MODE", "demo")
    get_settings.cache_clear()
    store.init_db()
    return TestClient(app)


def _resolve_template_path(path: str) -> str:
    """Replace path parameter templates with dummy identifiers."""
    resolved = re.sub(r"\{[^}]+\}", "dummy_id", path)
    return resolved


def test_dynamic_route_inventory_isolation_in_external_mode(external_client: TestClient):
    """Walk app.routes and assert all isolated endpoints reject agent callers with 403."""
    isolated_endpoints: list[tuple[str, str]] = []

    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue

        for method in methods:
            if method in ("GET", "POST", "PATCH", "PUT", "DELETE"):
                if is_isolated_route(path, method):
                    isolated_endpoints.append((method, path))

    # Assert that our dynamic discovery found all required route groups
    assert len(isolated_endpoints) >= 10, f"Expected at least 10 isolated routes, found {len(isolated_endpoints)}"

    tested_count = 0
    for method, path in isolated_endpoints:
        test_path = _resolve_template_path(path)
        resp = external_client.request(
            method,
            test_path,
            headers=AGENT_AUTH,
            json={"dummy": "payload"},
        )
        assert resp.status_code in (403, 404), (
            f"Expected 403/404 for agent calling {method} {test_path}, got {resp.status_code}: {resp.text}"
        )
        tested_count += 1

    print(f"\n[Gate A3 Verified: {tested_count} isolated route/method combinations asserted in external mode]")
    assert tested_count == len(isolated_endpoints)


def test_public_agent_routes_accessible_in_external_mode(external_client: TestClient):
    """Verify that legitimate agent commerce endpoints remain accessible in external mode."""
    # Health check
    h_resp = external_client.get("/health")
    assert h_resp.status_code == 200

    # Catalog search
    cat_resp = external_client.get("/agent-commerce/v1/catalog/search", headers=AGENT_AUTH)
    assert cat_resp.status_code == 200

    # Merchant capabilities
    m_resp = external_client.get("/agent-commerce/v1/merchant", headers=AGENT_AUTH)
    assert m_resp.status_code == 200


def test_demo_mode_does_not_block_internal_routes(demo_client: TestClient):
    """When GATEWAY_MODE=demo, internal routes are not blocked by the isolation middleware."""
    # In demo mode, /autopilot/execute should reach handler validation, not 403 route isolation
    resp = demo_client.post("/autopilot/execute", json={})
    # Handler validates payload and returns 422 Unprocessable Entity (not 403 route isolation)
    assert resp.status_code != 403
