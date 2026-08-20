"""FastAPI orchestrator — the only process the frontend talks to."""
from __future__ import annotations
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import agent, catalog, store
from .config import get_settings
from .mcp_client import get_client
from .models import (ChatRequest, ChatResponse, Mandate, MandateCreate,
                     MandateUpdate)

app = FastAPI(title="AI-Native Agentic Checkout with UAP Mandate Verification",
              version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:3000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    store.init_db()
    s = get_settings()
    if not store.get_active_mandate("user_demo", "agent_groceries"):
        store.create_mandate(MandateCreate(cap_rupees=1000))
    print(f"[boot] demo_mode={s.demo_mode} | catalog={len(catalog.load_catalog())} SKUs")


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {"ok": True, "demo_mode": s.demo_mode,
            "catalog_size": len(catalog.load_catalog()),
            "mcp": type(get_client()).__name__}


# ---------------- Chat ----------------
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    return agent.handle_turn(req)


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
