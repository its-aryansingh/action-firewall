"""End-to-end: the agent must never reach a money tool on a blocked turn."""
import os, tempfile, uuid
import pytest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DEMO_MODE"] = "true"
os.environ["OPENAI_API_KEY"] = ""
os.environ["LANGFUSE_PUBLIC_KEY"] = ""

from app import store                      # noqa: E402
from app.agent import handle_turn, reset_session  # noqa: E402
from app.mcp_client import MandateViolation, SimulatedMCPClient  # noqa: E402
from app.models import (Cart, CartLine, ChatRequest, DecisionCode,  # noqa: E402
                        MandateCreate, MandateDecision, MandateUpdate)


@pytest.fixture(autouse=True)
def db():
    store.init_db()
    yield


def chat(sid, msg):
    return handle_turn(ChatRequest(session_id=sid, message=msg))


def test_discovery_then_blocked_checkout_makes_no_mcp_call():
    store.create_mandate(MandateCreate(cap_rupees=1))       # ₹1 ceiling
    sid = uuid.uuid4().hex
    r = chat(sid, "I need supplies for a pasta dinner")
    assert r.cart.lines, "RAG should have populated a cart"
    assert not r.decision.allowed
    assert r.decision.code is DecisionCode.BLOCK_WINDOW_CAP_EXCEEDED
    assert all(t.blocked for t in r.tools), "no live tool call may be recorded"
    reset_session(sid)


def test_generous_mandate_allows_checkout_and_creates_link():
    store.create_mandate(MandateCreate(cap_rupees=100_000))
    sid = uuid.uuid4().hex
    chat(sid, "I need supplies for a pasta dinner")
    r = chat(sid, "checkout please")
    assert r.decision.allowed
    assert any(t.name == "create_payment_link" and not t.blocked for t in r.tools)
    reset_session(sid)


def test_revocation_binds_on_the_very_next_prompt():
    m = store.create_mandate(MandateCreate(cap_rupees=100_000))
    sid = uuid.uuid4().hex
    r1 = chat(sid, "I need supplies for a pasta dinner")
    assert r1.decision.allowed
    store.update_mandate(m.id, MandateUpdate(active=False))
    r2 = chat(sid, "add some cheese")
    assert not r2.decision.allowed
    assert r2.decision.code is DecisionCode.BLOCK_MANDATE_REVOKED
    assert r2.decision.mandate_version == m.version + 1
    reset_session(sid)


def test_mcp_client_refuses_a_denied_decision_directly():
    """Defence in depth: even a caller that ignores the gate cannot spend."""
    denied = MandateDecision(allowed=False, code=DecisionCode.BLOCK_WINDOW_CAP_EXCEEDED)
    with pytest.raises(MandateViolation):
        SimulatedMCPClient().call_tool("create_payment_link", {"amount": 999}, denied)


def test_metrics_count_breach_attempts():
    store.create_mandate(MandateCreate(cap_rupees=1))
    sid = uuid.uuid4().hex
    chat(sid, "I need supplies for a pasta dinner")
    m = store.metrics()
    assert m["mandate_breach_attempts"] >= 1
    assert 0 < m["mandate_breach_attempt_rate"] <= 1
    reset_session(sid)
