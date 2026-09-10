"""Evidence a merchant can put in front of someone who does not trust them.

An agent-initiated charge carries no cardholder-present evidence. When the
customer says "my agent was not authorised to buy that", the merchant carries the
chargeback. A layer that decides with a language model cannot fix this: the
samples are gone, and "the model returned 0.87" is not an artifact anyone checks.

A deterministic layer can do better than keep a record — it can hand over
everything the decision consumed and let a third party RE-EXECUTE it.
`test_altering_the_recorded_outcome_is_caught_by_re_running_it` is where that
claim is actually made good, and the stock test below is where its one honest
limit is pinned down.
"""
import copy
import json
import os
import tempfile

import pytest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "dispute.db")
os.environ["DEMO_MODE"] = "true"
os.environ["ENVELOPE_DRAFTING_MODE"] = "deterministic"
os.environ["PAYMENT_PROVIDER"] = "simulated"
os.environ["FAULT_INJECTION_ENABLED"] = "true"
os.environ["OPENAI_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app import catalog, store  # noqa: E402
from app.buyer_auth import MERCHANT_ADMIN_KEY  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.dispute import DISPUTE_PACK_SCHEMA, build_dispute_pack, verify_dispute_pack  # noqa: E402
from app.main import app  # noqa: E402

ADMIN = {"Authorization": f"Bearer {MERCHANT_ADMIN_KEY}"}


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "dispute.db"))
    monkeypatch.setenv("ENVELOPE_DRAFTING_MODE", "deterministic")
    monkeypatch.setenv("PAYMENT_PROVIDER", "simulated")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    get_settings.cache_clear()
    store.init_db()
    catalog.reset_stock()
    catalog.clear_snapshot()
    yield
    catalog.reset_stock()
    catalog.clear_snapshot()
    get_settings.cache_clear()


def attempt(attempt_id: str, scenario: str = "normal") -> dict:
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
    client.post(
        "/autopilot/execute",
        json={
            "envelope_id": envelope.id,
            "expected_envelope_version": envelope.version,
            "expected_envelope_hash": envelope.envelope_hash,
            "session_id": f"sess_{attempt_id}",
            "purchase_attempt_id": attempt_id,
            "scenario": scenario,
        },
    )
    return build_dispute_pack(attempt_id)


# ---------------------------------------------------------------------------
# The pack itself
# ---------------------------------------------------------------------------
def test_a_clean_pack_verifies():
    result = verify_dispute_pack(attempt("att_clean_00001"))
    assert result["valid"] is True
    assert "THE DECISION ITSELF" in " ".join(result["independently_rederived"])


def test_a_refusal_is_evidenced_too():
    """The case a merchant most needs and an authorisation ledger never keeps,
    because nothing was authorised."""
    pack = attempt("att_refused_0001", scenario="merchant_drift")
    assert pack["outcome"] == "refused"
    assert pack["grant"] is None
    assert pack["decision"]["deltas"], "a refusal must carry its reasons"
    assert verify_dispute_pack(pack)["valid"] is True


def test_the_pack_carries_the_whole_catalog_not_a_slice():
    """catalog_revision digests every row, so a partial snapshot cannot be
    checked against it — and a snapshot nobody can check is not evidence."""
    pack = attempt("att_catalog_0001")
    assert len(pack["catalog_snapshot"]) == len(catalog.load_catalog())


def test_the_pack_carries_no_secrets():
    pack = attempt("att_secret_0001")
    blob = json.dumps(pack)
    for forbidden in ("rzp_test_", "rzp_live_", MERCHANT_ADMIN_KEY, "ACTION_RECEIPT_SECRET"):
        assert forbidden not in blob, f"{forbidden!r} must never appear in an evidence pack"


def test_the_pack_route_is_merchant_only_but_the_verifier_is_public():
    """An integrity check nobody outside can run proves nothing; a customer's
    basket and prices are not public. The two need opposite answers."""
    pack = attempt("att_auth_0001")
    client = TestClient(app)
    assert client.get("/evidence/dispute-pack/att_auth_0001").status_code == 401
    assert client.get("/evidence/dispute-pack/att_auth_0001", headers=ADMIN).status_code == 200
    assert client.post("/evidence/dispute-pack/verify", json=pack).json()["valid"] is True


def test_an_unknown_attempt_is_404_not_an_empty_pack():
    client = TestClient(app)
    assert client.get("/evidence/dispute-pack/att_nope", headers=ADMIN).status_code == 404


def test_the_endpoint_and_the_cli_share_one_implementation():
    """Two verifiers drift, and the drift is found by whoever trusted the wrong
    one. The HTTP route must call the same function the script does."""
    import inspect

    from app import main

    assert "verify_dispute_pack" in inspect.getsource(main.dispute_pack_verify)


# ---------------------------------------------------------------------------
# Every way of doctoring it
# ---------------------------------------------------------------------------
@pytest.fixture
def pack():
    return attempt("att_tamper_0001")


def test_raising_the_cap_in_the_embedded_rule_is_caught(pack):
    bad = copy.deepcopy(pack)
    bad["consent"]["envelope"]["max_total_paise"] = 9_000_000
    assert verify_dispute_pack(bad)["failed_check"] == "consent"


def test_changing_a_price_in_the_quote_is_caught(pack):
    bad = copy.deepcopy(pack)
    bad["quote"]["cart"]["lines"][0]["unit_price_paise"] = 1
    assert verify_dispute_pack(bad)["failed_check"] == "quote_hash"


def test_changing_a_price_in_the_catalog_snapshot_is_caught(pack):
    """The snapshot is an input to the re-derivation, so it has to be bound too.
    An unbound snapshot would let anyone justify any decision after the fact."""
    bad = copy.deepcopy(pack)
    bad["catalog_snapshot"][0]["price_paise"] = 1
    assert verify_dispute_pack(bad)["failed_check"] == "catalog_revision"


def test_binding_the_grant_to_a_different_rule_is_caught(pack):
    bad = copy.deepcopy(pack)
    bad["grant"]["envelope_hash"] = "0" * 64
    assert verify_dispute_pack(bad)["failed_check"] == "grant.envelope_hash"


def test_binding_the_grant_to_a_different_basket_is_caught(pack):
    bad = copy.deepcopy(pack)
    bad["grant"]["cart_hash"] = "0" * 64
    assert verify_dispute_pack(bad)["failed_check"] == "grant.cart_hash"


def test_a_receipt_for_a_different_authority_is_caught(pack):
    bad = copy.deepcopy(pack)
    bad["receipt"]["grant_id"] = "act_somebody_elses"
    assert verify_dispute_pack(bad)["failed_check"] == "receipt.grant_id"


def test_altering_the_recorded_outcome_is_caught_by_re_running_it():
    """THE claim. Flip a refusal to an allow and the verifier re-executes the
    authorisation on the recorded inputs and disagrees. Nothing in the pack has
    to be trusted for this to work — only the published code."""
    pack = attempt("att_flip_0001", scenario="merchant_drift")
    assert pack["decision"]["allowed"] is False
    bad = copy.deepcopy(pack)
    bad["decision"]["allowed"] = True
    bad["decision"]["deltas"] = []
    result = verify_dispute_pack(bad)
    assert result["valid"] is False
    assert result["failed_check"] == "decision.allowed"
    assert "different answer" in result["reason"]


def test_deleting_one_reason_from_a_refusal_is_caught(pack):
    bad = copy.deepcopy(attempt("att_delta_0001", scenario="merchant_drift"))
    assert len(bad["decision"]["deltas"]) >= 1
    bad["decision"]["deltas"] = bad["decision"]["deltas"][1:]
    result = verify_dispute_pack(bad)
    assert result["valid"] is False
    assert result["failed_check"] == "decision.deltas"


def test_inflating_the_attested_stock_cannot_launder_a_refusal():
    """The sharpest test here. Stock is the ONE input a third party cannot
    independently prove, so the obvious attack is to overstate it and claim the
    order should have gone through. It does not work: the decision is re-derived
    FROM the attested figure, so raising it changes the re-derived outcome and
    the mismatch surfaces. The attested input cannot be doctored to justify a
    derived one."""
    pack = attempt("att_stock_0001")
    bad = copy.deepcopy(pack)
    for sku in bad["stock_at_decision"]:
        bad["stock_at_decision"][sku] = 0
    result = verify_dispute_pack(bad)
    assert result["valid"] is False
    assert result["failed_check"].startswith("decision")


def test_cutting_the_audit_trail_is_caught(pack):
    bad = copy.deepcopy(pack)
    entries = [e for e in bad["audit"]["entries"] if e.get("seq") is not None]
    if len(entries) >= 2:
        ordered = sorted(entries, key=lambda e: e["seq"])
        ordered[1]["prev_hash"] = "0" * 64
        bad["audit"]["entries"] = ordered
        assert verify_dispute_pack(bad)["failed_check"] == "audit"


def test_an_unknown_schema_is_refused(pack):
    bad = copy.deepcopy(pack)
    bad["schema"] = "something-else@1"
    assert verify_dispute_pack(bad)["failed_check"] == "schema"


# ---------------------------------------------------------------------------
# The verifier must not quietly depend on the machine it runs on
# ---------------------------------------------------------------------------
def test_verification_does_not_depend_on_local_catalog_state(pack):
    """A verifier that read today's catalog would pass or fail depending on the
    machine it ran on, which is the opposite of evidence."""
    catalog.set_stock(pack["catalog_snapshot"][0]["sku"], 0)
    assert verify_dispute_pack(pack)["valid"] is True


def test_verification_restores_whatever_catalog_state_it_found(pack):
    """It reaches into a shared module to re-derive. Leaving that module changed
    would silently corrupt the next request in the same process."""
    catalog.set_stock("SKU-DAI-004", 3)
    verify_dispute_pack(pack)
    assert catalog.available_stock("SKU-DAI-004") == 3
    assert catalog._CATALOG_OVERRIDE is None
