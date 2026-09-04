"""FastAPI orchestrator — the only process the frontend talks to."""
from __future__ import annotations
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import agent, catalog, reconciler, store
from .config import get_settings
from .mcp_client import get_client
from .models import (
    ChatRequest,
    ChatResponse,
    CheckoutConfirmRequest,
    Mandate,
    MandateCreate,
    MandateUpdate,
)

app = FastAPI(
    title="Action Firewall — Policy-bound Agentic Checkout",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:3000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    store.init_db()
    recovered = store.recover_stale_dispatches()
    s = get_settings()
    if not store.get_active_mandate("user_demo", "agent_groceries"):
        store.create_mandate(MandateCreate(cap_rupees=1000))
    print(
        f"[boot] demo_mode={s.demo_mode} | catalog={len(catalog.load_catalog())} SKUs "
        f"| stale_dispatches_to_unknown={recovered}"
    )


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"ok": True, "demo_mode": s.demo_mode,
            "catalog_size": len(catalog.load_catalog()),
            "mcp": type(get_client()).__name__}


# ---------------- Chat ----------------
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    try:
        return agent.handle_turn(req)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/checkout/confirm", response_model=ChatResponse)
def confirm_checkout(req: CheckoutConfirmRequest) -> ChatResponse:
    try:
        return agent.confirm_checkout(req)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/chat/{session_id}/reset")
def reset(session_id: str) -> dict:
    agent.reset_session(session_id)
    return {"ok": True}


# ---------------- Mandates ----------------
@app.get("/mandates", response_model=list[Mandate])
def list_mandates(user_id: str = "user_demo") -> list[Mandate]:
    return store.list_mandates(user_id)


@app.get("/mandates/active", response_model=Mandate)
def active_mandate(user_id: str = "user_demo",
                   agent_id: str = "agent_groceries") -> Mandate:
    m = store.get_active_mandate(user_id, agent_id)
    if not m:
        raise HTTPException(404, "No active mandate")
    return m


@app.post("/mandates", response_model=Mandate)
def create_mandate(body: MandateCreate) -> Mandate:
    return store.create_mandate(body)


@app.patch("/mandates/{mandate_id}", response_model=Mandate)
def update_mandate(mandate_id: str, body: MandateUpdate) -> Mandate:
    """Revocation latency starts here: the next agent turn re-reads this row."""
    m = store.update_mandate(mandate_id, body)
    if not m:
        raise HTTPException(404, "Unknown mandate")
    return m


@app.get("/mandates/{mandate_id}/usage")
def mandate_usage(mandate_id: str) -> dict:
    m = store.get_mandate(mandate_id)
    if not m:
        raise HTTPException(404, "Unknown mandate")
    spent = store.spent_in_window(mandate_id, m.window)
    return {"mandate_id": mandate_id, "version": m.version, "window": m.window.value,
            "cap_paise": m.cap_paise, "spent_paise": spent,
            "headroom_paise": max(0, m.cap_paise - spent),
            "utilisation": round(spent / m.cap_paise, 4) if m.cap_paise else 0.0}


# ---------------- Audit & metrics ----------------
@app.get("/audit")
def audit(session_id: str | None = None, limit: int = 100) -> list[dict]:
    return store.audit_trail(session_id, limit)


@app.get("/metrics")
def metrics(user_id: str = "user_demo") -> dict:
    m = store.metrics(user_id)
    m["generated_at"] = time.time()
    return m


# ---------------- Catalog ----------------
@app.get("/catalog")
def get_catalog() -> list[dict]:
    return catalog.load_catalog()


@app.get("/catalog/search")
def search_catalog(q: str, top_k: int = 6) -> list[dict]:
    return catalog.search(q, top_k)


@app.get("/mcp/tools")
def mcp_tools() -> dict:
    client = get_client()
    try:
        return {"client": type(client).__name__, "tools": client.list_tools()}
    except Exception as exc:
        raise HTTPException(502, f"MCP unreachable: {exc}")


# ---------------- Reconciliation ----------------
def _reconciliation_payload(result) -> dict:
    return {
        "grant_id": result.grant_id,
        "before": result.before.value,
        "after": result.after.value,
        "changed": result.changed,
        "note": result.note,
        "provider_reachable": result.observation.reachable,
        "provider_status": result.observation.provider_status,
        "amount_paid_paise": result.observation.amount_paid_paise,
    }


@app.post("/actions/{grant_id}/reconcile")
def reconcile_action(grant_id: str) -> dict:
    """Resolve one action against the provider's own record.

    Takes a grant id and nothing else, deliberately. There is no field on this
    route by which a caller can assert that a payment happened; the server goes
    and reads the provider itself. An unreachable provider changes nothing and
    keeps the exposure held.
    """
    try:
        return _reconciliation_payload(reconciler.reconcile(grant_id))
    except LookupError:
        raise HTTPException(404, "Unknown action grant")


@app.post("/actions/reconcile")
def reconcile_open_actions(limit: int = 50) -> dict:
    """Sweep every action still holding exposure. Idempotent and re-runnable."""
    results = [_reconciliation_payload(r)
               for r in reconciler.reconcile_open_actions(limit=limit)]
    return {
        "reconciled": len(results),
        "changed": sum(1 for r in results if r["changed"]),
        "results": results,
    }
