"""The MCP surface must verify identity, not assert it.

Why this file exists. The six MCP tools are the surface this project ADVERTISES
to external AI buyers. Until now `request_checkout` built its own principal:

    AgentPrincipal(buyer_agent_id=MCP_BUYER_AGENT_ID, merchant_id=...)

`AgentPrincipal.authenticated` defaults to True, so that object asserted an
authentication that had never happened, and every guard downstream trusted it.
The HTTP twin had verify_buyer_agent, a rate limit and replay protection; the
advertised surface had none of them.

Identity asserted rather than verified is the weakest pattern in this
buildathon's field — one rival ships `allow_origins=["*"]` with an agent id read
straight from the request body. These tests exist so this repository cannot drift
back into it.
"""
from __future__ import annotations

import pytest

from app import buyer_auth, commerce_mcp
from app.buyer_auth import AgentPrincipal, ShopperPrincipal
from app.commerce_service import CheckoutPrincipals, execute_checkout
from app.config import get_settings


def test_mcp_resolves_a_principal_instead_of_constructing_one():
    """The tell: no credential must not yield authenticated=True."""
    principals, refusal = commerce_mcp._resolve_mcp_principals()
    assert refusal is None, "demo mode should resolve, not refuse"
    assert principals is not None
    assert principals.buyer.authenticated is False, (
        "a caller that presented no credential must be labelled unauthenticated. "
        "If this ever reads True again, the surface is asserting identity."
    )
    assert principals.transport == "mcp"


def test_a_valid_key_yields_an_authenticated_principal(monkeypatch):
    monkeypatch.setattr(
        commerce_mcp, "_bearer_from_request_context",
        lambda: f"Bearer {buyer_auth.DEMO_BUYER_KEY}",
    )
    principals, refusal = commerce_mcp._resolve_mcp_principals()
    assert refusal is None
    assert principals.buyer.authenticated is True
    assert principals.buyer.key_hash is not None


def test_an_invalid_key_is_refused_as_a_structured_answer(monkeypatch):
    """MCP tools answer; they do not throw. A bad key is a refusal, not a 500."""
    monkeypatch.setattr(
        commerce_mcp, "_bearer_from_request_context",
        lambda: "Bearer af_test_not_a_real_key_at_all",
    )
    principals, refusal = commerce_mcp._resolve_mcp_principals()
    assert principals is None
    assert refusal["allowed"] is False
    assert refusal["code"] == "UNAUTHENTICATED_BUYER_AGENT"
    assert refusal["razorpay_action_called"] is False


def test_a_revoked_key_stops_working_on_the_mcp_surface(monkeypatch):
    """Revocation has to cover the advertised surface, or it covers nothing."""
    key = "af_test_revocable_key_for_mcp"
    buyer_auth.register_buyer_key(key, "buyer_revocable")
    monkeypatch.setattr(
        commerce_mcp, "_bearer_from_request_context", lambda: f"Bearer {key}")
    try:
        principals, refusal = commerce_mcp._resolve_mcp_principals()
        assert refusal is None and principals.buyer.authenticated is True

        buyer_auth.revoke_buyer_key(key)
        principals, refusal = commerce_mcp._resolve_mcp_principals()
        assert principals is None
        assert refusal["code"] == "UNAUTHENTICATED_BUYER_AGENT"
    finally:
        buyer_auth.reset_buyer_keys()


def test_the_quote_writer_and_the_checkout_reader_agree(monkeypatch):
    """One resolver, both sites.

    request_quote writes the quote row's owner and request_checkout reads it back
    to decide ownership. If those two derive identity differently, a caller mints
    a quote it cannot spend, and every MCP checkout becomes QUOTE_NOT_FOUND.
    """
    monkeypatch.setattr(
        commerce_mcp, "_bearer_from_request_context",
        lambda: f"Bearer {buyer_auth.DEMO_BUYER_KEY}",
    )
    owner = commerce_mcp._quote_owner()
    principals, _ = commerce_mcp._resolve_mcp_principals()
    assert owner == principals.buyer.buyer_agent_id


def test_no_request_context_is_a_normal_state_not_a_crash():
    """Direct calls and stdio transports have no HTTP request. That is fine."""
    assert commerce_mcp._bearer_from_request_context() is None


# ---------------------------------------------------------------------------
# The label has to be load-bearing
# ---------------------------------------------------------------------------

def _unauthenticated_principals() -> CheckoutPrincipals:
    return CheckoutPrincipals(
        buyer=AgentPrincipal(buyer_agent_id="buyer_unverified", authenticated=False),
        shopper=ShopperPrincipal(user_id="u", shopper_session_id="s_unverified",
                                 authenticated=False),
        transport="mcp",
    )


def test_an_unverified_caller_cannot_reach_a_live_provider(monkeypatch, tmp_path):
    """`authenticated=False` must change an outcome somewhere, or it is decoration."""
    from app import mcp_client

    monkeypatch.setattr(mcp_client, "get_active_provider_mode", lambda: "RazorpayRESTClient")
    result = execute_checkout(
        principals=_unauthenticated_principals(),
        envelope_id="env_does_not_matter",
        attempt_id="att_unverified_01",
    )
    assert result.allowed is False
    assert result.code == "UNAUTHENTICATED_BUYER_AGENT"
    assert result.razorpay_action_called is False
    assert result.payment_link is None


def test_the_same_caller_is_allowed_against_the_simulated_provider(monkeypatch, tmp_path):
    """The offline demo must keep working without keys — that is the whole point
    of labelling rather than refusing outright."""
    from app import mcp_client, store

    monkeypatch.setenv("DB_PATH", str(tmp_path / "mcp_auth.db"))
    get_settings.cache_clear()
    store.init_db()
    monkeypatch.setattr(mcp_client, "get_active_provider_mode", lambda: "simulated")
    result = execute_checkout(
        principals=_unauthenticated_principals(),
        envelope_id="env_definitely_missing",
        attempt_id="att_unverified_02",
    )
    # It gets past the auth gate and fails on the envelope instead.
    assert result.code != "UNAUTHENTICATED_BUYER_AGENT"


def test_outside_demo_mode_no_credential_is_refused_outright(monkeypatch):
    # Fault injection must go off with demo mode, or boot-time invariant 17
    # refuses to build Settings at all — the two are deliberately coupled.
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "false")
    get_settings.cache_clear()
    try:
        monkeypatch.setattr(commerce_mcp, "_bearer_from_request_context", lambda: None)
        principals, refusal = commerce_mcp._resolve_mcp_principals()
        assert principals is None
        assert refusal["code"] == "UNAUTHENTICATED_BUYER_AGENT"
    finally:
        get_settings.cache_clear()
