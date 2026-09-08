"""Tests for configuration safety, Invariant 17 enforcement, and DB path anchoring."""
from __future__ import annotations

from pathlib import Path
import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from app.config import BACKEND_DIR, Settings, get_settings
from app.main import app


def test_default_config_values():
    """Verify default security settings."""
    s = Settings(
        demo_mode=True,
        payment_provider="simulated",
        fault_injection_enabled=False,
    )
    assert s.fault_injection_enabled is False
    assert Path(s.db_path).is_absolute()
    assert s.payment_provider == "simulated"


def test_db_path_always_resolves_to_absolute():
    """Relative paths must be resolved relative to BACKEND_DIR."""
    s = Settings(db_path="custom_relative.db", fault_injection_enabled=False)
    p = Path(s.db_path)
    assert p.is_absolute()
    assert p == (BACKEND_DIR / "custom_relative.db").resolve()

    # Pre-existing absolute path stays absolute
    abs_path = str(BACKEND_DIR / "another.db")
    s2 = Settings(db_path=abs_path, fault_injection_enabled=False)
    assert s2.db_path == abs_path


def test_fault_injection_invariant_17_rejected_when_not_simulated():
    """Fault injection cannot be enabled when payment_provider is not simulated."""
    with pytest.raises((ValidationError, ValueError), match="Invariant 17"):
        Settings(
            demo_mode=True,
            payment_provider="razorpay_mcp",
            fault_injection_enabled=True,
        )

    with pytest.raises((ValidationError, ValueError), match="Invariant 17"):
        Settings(
            demo_mode=True,
            payment_provider="razorpay_rest",
            fault_injection_enabled=True,
        )


def test_fault_injection_invariant_17_rejected_when_not_demo_mode():
    """Fault injection cannot be enabled when demo_mode is False."""
    with pytest.raises((ValidationError, ValueError), match="Invariant 17"):
        Settings(
            demo_mode=False,
            payment_provider="simulated",
            fault_injection_enabled=True,
        )


def test_fault_injection_permitted_in_offline_simulated_demo():
    """Fault injection is only valid when demo_mode is True and provider is simulated."""
    s = Settings(
        demo_mode=True,
        payment_provider="simulated",
        fault_injection_enabled=True,
    )
    assert s.fault_injection_enabled is True


def test_live_provider_permitted_when_fault_injection_disabled():
    """Live or non-simulated providers are valid when fault injection is False."""
    s = Settings(
        demo_mode=False,
        payment_provider="razorpay_rest",
        fault_injection_enabled=False,
    )
    assert s.fault_injection_enabled is False
    assert s.payment_provider == "razorpay_rest"


def test_health_endpoint_reports_absolute_db_path_and_status():
    """GET /health must report ok status, absolute db_path, and configuration."""
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "ok"
    assert "db_path" in data
    assert Path(data["db_path"]).is_absolute()
    assert data["payment_provider"] in ("simulated", "razorpay_mcp", "razorpay_rest")


def test_lifespan_refuses_boot_on_invariant_17_violation(monkeypatch: pytest.MonkeyPatch):
    """Lifespan context manager must refuse boot if invariant 17 is breached."""
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("PAYMENT_PROVIDER", "razorpay_mcp")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    get_settings.cache_clear()

    with pytest.raises((RuntimeError, ValidationError, ValueError)):
        with TestClient(app):
            pass
