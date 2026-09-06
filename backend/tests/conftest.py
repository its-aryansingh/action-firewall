"""Suite-wide isolation from a developer's live service configuration."""
from __future__ import annotations

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def isolated_service_modes(monkeypatch: pytest.MonkeyPatch):
    """Make every test start from the documented offline demo boundary.

    Individual tests may still opt into a live-mode configuration explicitly.
    This prevents an ignored local ``backend/.env`` from changing provider,
    retrieval, or model behavior underneath otherwise deterministic tests.
    """
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("CATALOG_RETRIEVAL_MODE", "keyword")
    monkeypatch.setenv("ENVELOPE_DRAFTING_MODE", "replay")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("RAZORPAY_KEY_ID", "")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "")
    monkeypatch.setenv("RAZORPAY_MCP_TOKEN", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
