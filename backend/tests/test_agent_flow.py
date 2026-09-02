"""End-to-end proposal, confirmation, and exact-action boundary tests."""
import os
import tempfile
import uuid

import pytest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DEMO_MODE"] = "true"
os.environ["OPENAI_API_KEY"] = ""
os.environ["LANGFUSE_PUBLIC_KEY"] = ""

from app import store  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.agent import confirm_checkout, handle_turn, reset_session  # noqa: E402
from app.mcp_client import SimulatedMCPClient  # noqa: E402
from app.models import (  # noqa: E402
    ChatRequest,
    CheckoutConfirmRequest,
    DecisionCode,
    MandateCreate,
    MandateUpdate,
)


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "agent-flow.db"))
    get_settings.cache_clear()
    store.init_db()
    yield
    get_settings.cache_clear()


def chat(session_id: str, message: str):
    return handle_turn(ChatRequest(session_id=session_id, message=message))


def confirm(session_id: str, cart_hash: str, key: str | None = None):
    return confirm_checkout(
        CheckoutConfirmRequest(
            session_id=session_id,
            expected_cart_hash=cart_hash,
            idempotency_key=key,
        )
    )


def test_chat_is_proposal_only_even_with_checkout_language():
    store.create_mandate(MandateCreate(cap_rupees=100_000))
    session_id = uuid.uuid4().hex
    proposal = chat(session_id, "I need supplies for a pasta dinner")
    checkout_language = chat(session_id, "checkout please")

    assert proposal.cart.lines
    assert checkout_language.confirmation_required is True
    assert checkout_language.tools == []
    assert store.metrics()["authorization_attempts"] == 0
    reset_session(session_id)


def test_blocked_confirmation_makes_no_mcp_call():
    store.create_mandate(MandateCreate(cap_rupees=1))
    session_id = uuid.uuid4().hex
    proposal = chat(session_id, "I need supplies for a pasta dinner")
    response = confirm(session_id, proposal.cart_hash, f"attempt-{uuid.uuid4().hex}")

    assert not response.decision.allowed
    assert response.decision.code is DecisionCode.BLOCK_WINDOW_CAP_EXCEEDED
    assert all(tool.blocked for tool in response.tools)
    assert response.grant_id is None
    reset_session(session_id)


def test_confirmation_issues_payment_link_but_not_settlement():
    store.create_mandate(MandateCreate(cap_rupees=100_000))
    session_id = uuid.uuid4().hex
    proposal = chat(session_id, "I need supplies for a pasta dinner")
    response = confirm(session_id, proposal.cart_hash, f"attempt-{uuid.uuid4().hex}")

    assert response.decision.allowed
    assert response.action_status.value == "action_issued"
    assert any(
        tool.name == "create_payment_link" and not tool.blocked
        for tool in response.tools
    )
    metrics = store.metrics()
    assert metrics["payment_link_issued_value_paise"] > 0
    assert metrics["confirmed_test_payment_value_paise"] == 0
    reset_session(session_id)


def test_wrong_cart_hash_is_denied_before_authorization():
    store.create_mandate(MandateCreate(cap_rupees=100_000))
    session_id = uuid.uuid4().hex
    chat(session_id, "I need supplies for a pasta dinner")
    response = confirm(session_id, "not-the-current-cart")

    assert response.decision.code is DecisionCode.BLOCK_CART_CHANGED
    assert response.grant_id is None
    reset_session(session_id)


def test_revocation_binds_before_confirmation():
    mandate = store.create_mandate(MandateCreate(cap_rupees=100_000))
    session_id = uuid.uuid4().hex
    proposal = chat(session_id, "I need supplies for a pasta dinner")
    store.update_mandate(mandate.id, MandateUpdate(active=False))
    response = confirm(session_id, proposal.cart_hash)

    assert not response.decision.allowed
    assert response.decision.code is DecisionCode.BLOCK_MANDATE_REVOKED
    reset_session(session_id)


def test_metrics_count_only_explicit_authorization_attempts():
    store.create_mandate(MandateCreate(cap_rupees=1))
    session_id = uuid.uuid4().hex
    proposal = chat(session_id, "I need supplies for a pasta dinner")
    before = store.metrics()
    confirm(session_id, proposal.cart_hash, f"attempt-{uuid.uuid4().hex}")
    after = store.metrics()

    assert before["authorization_attempts"] == 0
    assert before["cart_policy_previews"] >= 1
    assert after["authorization_attempts"] == 1
    assert after["denied_authorizations"] == 1
    reset_session(session_id)


def test_same_session_identity_cannot_be_changed():
    store.create_mandate(MandateCreate(cap_rupees=100_000))
    session_id = uuid.uuid4().hex
    chat(session_id, "pasta dinner")
    with pytest.raises(ValueError):
        handle_turn(
            ChatRequest(
                session_id=session_id,
                user_id="different-user",
                message="show cart",
            )
        )
    reset_session(session_id)
