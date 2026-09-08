"""Disposable offline demonstration script for Action Firewall — Agent Commerce Gateway.

Demonstrates the four-stage lifecycle:
1. Discover & Catalog Search
2. Intent Drafting & Server Quote (proposal-only)
3. Explicit Shopper Activation (authority boundary)
4. Razorpay Payment Link Issuance (Action Firewall execution)
Plus graceful degradation: stock substitution and merchant drift policy delta.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_TEMP_DIR = tempfile.TemporaryDirectory(prefix="agent-gateway-demo-")
os.environ["DB_PATH"] = str(Path(_TEMP_DIR.name) / "agent_gateway.db")
os.environ["DEMO_MODE"] = "true"
os.environ["PAYMENT_PROVIDER"] = "simulated"
os.environ["CATALOG_RETRIEVAL_MODE"] = "keyword"
os.environ["ENVELOPE_DRAFTING_MODE"] = "replay"
os.environ["FAULT_INJECTION_ENABLED"] = "true"
for secret_name in (
    "OPENAI_API_KEY",
    "PINECONE_API_KEY",
    "RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_MCP_TOKEN",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "ACTION_RECEIPT_SECRET",
):
    os.environ[secret_name] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.buyer_auth import DEMO_BUYER_KEY  # noqa: E402
from app import store  # noqa: E402


def heading(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> None:
    store.init_db()
    client = TestClient(app, headers={"Authorization": f"Bearer {DEMO_BUYER_KEY}"})

    print("Action Firewall — Agent Commerce Gateway Offline Rehearsal")
    print("Environment: Isolated SQLite; Provider: Simulated Razorpay MCP; Network: Disabled")

    # STAGE 1: DISCOVER
    heading("STAGE 1: Merchant Discovery & Catalog Verification")
    merchant_res = client.get("/agent-commerce/v1/merchant")
    assert merchant_res.status_code == 200
    m_data = merchant_res.json()
    print(f"Merchant: {m_data['display_name']} ({m_data['merchant_id']})")
    print(f"Catalog Revision: {m_data['catalog_revision']}")
    print(f"Supported Actions: {[m_data['action_name']]}")

    cat_res = client.get("/agent-commerce/v1/catalog/search?query=pasta")
    assert cat_res.status_code == 200
    cat_items = cat_res.json()
    print(f"Catalog query 'pasta': Found {len(cat_items)} verified items")
    for item in cat_items:
        print(f"  [{item['sku']}] {item['name']} - Rs {item['price_paise'] / 100:.2f} (in_stock={item['in_stock']})")

    # STAGE 2: UNDERSTAND (Proposal Only)
    heading("STAGE 2: Draft Intent & Server Quote (Proposal-Only)")
    intent_res = client.post(
        "/agent-commerce/v1/intents",
        json={
            "agent_request_id": "req_demo_001",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": "session_demo_replay",
            "natural_language_intent": "Need ingredients for pasta dinner under Rs 600",
            "budget_paise": 60000,
        },
    )
    assert intent_res.status_code == 200
    intent_data = intent_res.json()
    draft = intent_data["draft_envelope"]
    print(f"Draft Envelope: {draft['id']} (Status: {draft['status']})")
    print(f"Envelope Hash: {draft['envelope_hash'][:16]}...")
    print(f"Slots required: {[s['label'] for s in draft['slots']]}")

    # Quote computation strictly server-side
    quote_res = client.post(
        "/agent-commerce/v1/quotes",
        json={
            "merchant_id": "merchant_demo",
            "fulfillment_profile_id": "dest_demo",
            "items": [{"sku": "SKU-PAS-002", "quantity": 1}],
        },
    )
    assert quote_res.status_code == 200
    q_data = quote_res.json()
    print(f"Authoritative Quote: {q_data['quote_id']} Total: Rs {q_data['total_paise'] / 100:.2f}")

    # STAGE 3: AUTHORIZE (Human Authority Boundary)
    heading("STAGE 3: Explicit Human Envelope Activation")
    # Verify unactivated attempt is rejected before Razorpay
    premature_attempt = client.post(
        "/agent-commerce/v1/attempts",
        json={
            "envelope_id": draft["id"],
            "purchase_attempt_id": "att_premature_001",
            "scenario": "normal",
        },
    )
    assert premature_attempt.status_code == 200
    p_res = premature_attempt.json()
    assert p_res["allowed"] is False
    assert p_res["outcome"] == "STOPPED_BEFORE_RAZORPAY"
    assert p_res["razorpay_action_called"] is False
    print(f"Premature execution blocked cleanly: {p_res['code']}")

    # Shopper activates envelope explicitly
    act_res = client.post(
        f"/agent-commerce/v1/envelopes/{draft['id']}/activate",
        json={"expected_envelope_hash": draft["envelope_hash"]},
    )
    assert act_res.status_code == 200
    active_env = act_res.json()
    print(f"Shopper Activated: {active_env['id']} status={active_env['status']} v{active_env['version']}")

    # STAGE 4: RAZORPAY ACTION
    heading("STAGE 4: Atomic Firewall Execution -> Payment Link")
    attempt_res = client.post(
        "/agent-commerce/v1/attempts",
        json={
            "envelope_id": active_env["id"],
            "purchase_attempt_id": "att_demo_success_001",
            "scenario": "normal",
        },
    )
    assert attempt_res.status_code == 200
    res = attempt_res.json()
    assert res["allowed"] is True
    assert res["outcome"] == "ACTION_ISSUED"
    assert res["razorpay_action_called"] is True
    assert res["payment_link"].startswith("https://rzp.io/")
    print(f"Execution Outcome: {res['outcome']}")
    print(f"Payment Link Issued: {res['payment_link']}")
    print(f"Action Grant ID: {res['grant_id']}")
    print(f"Dual-Signature Receipt ID: {res['receipt']['grant_id']}")
    for stage in res["stages"]:
        print(f"  Stage [{stage['stage']}]: {stage['name']} -> {stage['status']} ({stage['detail']})")

    # GRACEFUL RECOVERY: STOCK DRIFT
    heading("DEMO RESILIENCE: In-Envelope Substitution on Stock Loss")
    stock_intent = client.post(
        "/agent-commerce/v1/intents",
        json={
            "agent_request_id": "req_demo_stock",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": "session_stock",
            "natural_language_intent": "Buy supplies for pasta dinner",
            "budget_paise": 60000,
        },
    ).json()["draft_envelope"]
    client.post(
        f"/agent-commerce/v1/envelopes/{stock_intent['id']}/activate",
        json={"expected_envelope_hash": stock_intent["envelope_hash"]},
    )
    stock_res = client.post(
        "/agent-commerce/v1/attempts",
        json={
            "envelope_id": stock_intent["id"],
            "purchase_attempt_id": "att_demo_stock_001",
            "scenario": "stock_loss",
        },
    ).json()
    assert stock_res["allowed"] is True
    assert stock_res["recovery_applied"] is True
    assert stock_res["outcome"] == "RECOVERED_INSIDE_ENVELOPE"
    print(f"Stock loss gracefully handled: outcome={stock_res['outcome']}")
    print(f"Substituted Payment Link: {stock_res['payment_link']}")

    # REFUSAL ON DRIFT: MERCHANT CHANGE
    heading("DEMO BOUNDARY: Block & Policy Delta on Merchant Drift")
    drift_intent = client.post(
        "/agent-commerce/v1/intents",
        json={
            "agent_request_id": "req_demo_drift",
            "buyer_agent_id": "buyer_replay",
            "shopper_session_id": "session_drift",
            "natural_language_intent": "Buy supplies for pasta dinner",
            "budget_paise": 60000,
        },
    ).json()["draft_envelope"]
    client.post(
        f"/agent-commerce/v1/envelopes/{drift_intent['id']}/activate",
        json={"expected_envelope_hash": drift_intent["envelope_hash"]},
    )
    drift_res = client.post(
        "/agent-commerce/v1/attempts",
        json={
            "envelope_id": drift_intent["id"],
            "purchase_attempt_id": "att_demo_drift_001",
            "scenario": "merchant_drift",
        },
    ).json()
    assert drift_res["allowed"] is False
    assert drift_res["outcome"] == "POLICY_DELTA_REQUIRED"
    assert drift_res["razorpay_action_called"] is False
    print(f"Merchant drift blocked before actuator: outcome={drift_res['outcome']}")
    for d in drift_res["deltas"]:
        print(f"  Policy Delta: field={d['field']} expected={d['expected']} actual={d['actual']} recovery={d['recovery']}")

    # METRICS SUMMARY
    heading("MERCHANT DASHBOARD: Live Operational KPIs")
    metrics_res = client.get("/agent-commerce/v1/metrics").json()
    print("Metrics projection:")
    print(json.dumps(metrics_res, indent=2))
    print("\nAGENT COMMERCE GATEWAY DEMO REHEARSAL PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        _TEMP_DIR.cleanup()
