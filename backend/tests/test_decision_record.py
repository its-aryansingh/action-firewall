"""Every attempt must leave behind why it ended the way it did.

`spend_ledger` records what was AUTHORISED — hashes, amounts, the action. It
never recorded WHY. Without the decision, the quote it was taken against, and
the stock reading it saw, an evidence pack can show a charge is bound to an
approved rule but not that allowing it was correct — and a refusal leaves
nothing behind at all, because nothing was authorised to leave a row.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "decision.db")
os.environ["DEMO_MODE"] = "true"
os.environ["ENVELOPE_DRAFTING_MODE"] = "deterministic"
os.environ["PAYMENT_PROVIDER"] = "simulated"
os.environ["FAULT_INJECTION_ENABLED"] = "true"
os.environ["OPENAI_API_KEY"] = ""

from app import catalog, store  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "decision.db"))
    monkeypatch.setenv("ENVELOPE_DRAFTING_MODE", "deterministic")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    get_settings.cache_clear()
    store.init_db()
    catalog.reset_stock()
    yield
    catalog.reset_stock()
    get_settings.cache_clear()


def run(attempt_id: str, scenario: str = "normal"):
    client = TestClient(app)
    drafted = client.post(
        "/agent-commerce/v1/intents",
        json={
            "agent_request_id": f"req_{attempt_id}",
            "natural_language_intent": "Weeknight pasta dinner for four",
            "budget_paise": 784000,
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": f"sess_{attempt_id}",
        },
    ).json()["draft_envelope"]
    client.post(
        f"/agent-commerce/v1/envelopes/{drafted['id']}/activate",
        json={"expected_envelope_hash": drafted["envelope_hash"]},
    )
    envelope = store.get_envelope(drafted["id"])
    body = {
        "envelope_id": envelope.id,
        "expected_envelope_version": envelope.version,
        "expected_envelope_hash": envelope.envelope_hash,
        "session_id": f"sess_{attempt_id}",
        "purchase_attempt_id": attempt_id,
        "scenario": scenario,
    }
    response = client.post("/autopilot/execute", json=body)
    return envelope, body, response, store.get_decision_record(attempt_id)


def test_an_issued_attempt_is_recorded():
    _, _, _, record = run("att_rec_issued_01")
    assert record["outcome"] == "issued"
    assert record["grant_id"]
    assert record["decision"]["allowed"] is True


def test_a_refusal_is_recorded_with_its_reasons():
    _, _, _, record = run("att_rec_refused_1", scenario="merchant_drift")
    assert record["outcome"] == "refused"
    assert record["grant_id"] is None
    assert record["decision"]["allowed"] is False
    assert record["decision"]["deltas"], "a refusal without its reasons evidences nothing"


def test_an_unknown_provider_outcome_keeps_its_grant():
    """Exposure stays held on UNKNOWN, so the evidence must point at the grant
    that is holding it."""
    _, _, _, record = run("att_rec_unknown_1", scenario="timeout_after_dispatch")
    assert record["outcome"] == "unknown"
    assert record["grant_id"]


def test_the_stock_reading_covers_the_cart_and_nothing_else():
    _, _, _, record = run("att_rec_stock_01")
    cart_skus = {line["sku"] for line in record["quote"]["cart"]["lines"]}
    assert set(record["stock_at_decision"]) == cart_skus
    assert all(isinstance(v, int) for v in record["stock_at_decision"].values())


def test_the_recorded_envelope_is_the_one_the_decision_saw():
    """A consumed envelope carries a bumped version and a new hash. Recording
    only the id would mean evidence built later described a different rule from
    the one the grant is bound to — which is exactly the bug the dispute-pack
    verifier caught on a clean pack."""
    envelope, _, _, record = run("att_rec_env_0001")
    assert record["envelope"]["envelope_hash"] == envelope.envelope_hash
    assert record["envelope"]["version"] == envelope.version

    current = store.get_envelope(envelope.id)
    assert current.envelope_hash != record["envelope"]["envelope_hash"], (
        "this test is meaningless unless the envelope really does move after dispatch"
    )


def test_a_replayed_attempt_does_not_write_a_second_record():
    """One purchase attempt is one decision. A replay returns the first grant;
    it must not leave a second, subtly different account of the same event."""
    _, body, _, first = run("att_rec_replay_01")
    TestClient(app).post("/autopilot/execute", json=body)
    second = store.get_decision_record("att_rec_replay_01")
    assert second["id"] == first["id"]
    assert second["decided_at"] == first["decided_at"]


def test_the_record_is_written_after_the_grant_exists():
    """Written after the grant commits, deliberately: the worst failure is then
    a grant with no decision record — missing evidence — rather than a record
    describing an authorisation that was rolled back."""
    _, _, _, record = run("att_rec_order_001")
    assert store.get_action_grant(record["grant_id"]) is not None
