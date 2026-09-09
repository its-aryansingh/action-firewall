"""FastAPI orchestrator — the only process the frontend talks to."""
from __future__ import annotations
import hashlib
import hmac
import json
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from mcp.server.streamable_http_manager import TransportSecuritySettings

from . import agent, agent_commerce, autopilot, catalog, commerce_mcp, demo_scenario, merchant, reconciler, store, voice
from .buyer_auth import MERCHANT_ADMIN_KEY, verify_merchant_admin
from .config import get_settings
from .merchant import DEFAULT_MERCHANT_ID, DEFAULT_MERCHANT_NAME
from .mcp_client import get_client
from .models import (
    ChatRequest,
    ChatResponse,
    CheckoutConfirmRequest,
    ActionReceipt,
    ActionReceiptVerification,
    AutopilotExecuteRequest,
    AutopilotExecuteResponse,
    EnvelopeActivateRequest,
    EnvelopeDraftRequest,
    EnvelopeRevokeRequest,
    Mandate,
    MandateCreate,
    MandateUpdate,
    PurchaseEnvelope,
    VoiceTranscription,
)
from .receipts import build_receipt, verify_receipt

@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    if s.fault_injection_enabled and (s.payment_provider != "simulated" or not s.demo_mode):
        raise RuntimeError(
            f"Invariant 17 violation: fault_injection_enabled cannot be True when "
            f"payment_provider='{s.payment_provider}' or demo_mode={s.demo_mode}. App refused to start."
        )
    store.init_db()
    recovered = store.recover_stale_dispatches()
    if not store.get_active_mandate("user_demo", "agent_groceries"):
        store.create_mandate(MandateCreate(cap_rupees=1000))
    print(
        f"[boot] payment_provider={s.payment_provider} "
        f"| catalog_retrieval={s.catalog_retrieval_mode} "
        f"| drafting={s.envelope_drafting_mode} "
        f"| db_path={s.db_path} "
        f"| stale_dispatches_to_unknown={recovered}"
    )
    mgr = commerce_mcp.mcp_server.session_manager
    if getattr(mgr, "_has_started", False) and getattr(mgr, "_task_group", None) is None:
        mgr._has_started = False
    async with mgr.run():
        yield


app = FastAPI(
    title="Action Firewall — Agent Commerce Gateway",
    version="3.1.0",
    lifespan=lifespan,
)
_settings = get_settings()
_frontend_origin = _settings.frontend_origin.rstrip("/")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend_origin] if _frontend_origin else [],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def is_isolated_route(path: str, method: str) -> bool:
    """Check if a route path/method is an internal execution/admin route."""
    p = path.rstrip("/")
    m = method.upper()

    if p == "/chat" or p.startswith("/chat/"):
        return True
    if p == "/checkout/confirm":
        return True
    if "/envelopes/" in p and ("/activate" in p or "/revoke" in p):
        return True
    if p == "/autopilot/execute":
        return True
    if p.startswith("/mandates") and m in ("POST", "PATCH", "PUT", "DELETE"):
        return True
    if p == "/mcp/tools" or p.startswith("/mcp/tools") or p == "/mcp/southbound-tools":
        return True
    if p == "/actions/reconcile" or (p.startswith("/actions/") and p.endswith("/reconcile")):
        return True
    if p == "/demo" or p.startswith("/demo/"):
        return True

    return False


@app.middleware("http")
async def enforce_route_isolation(request: Request, call_next):
    s = get_settings()
    if s.gateway_mode == "external":
        path = request.url.path
        method = request.method
        if is_isolated_route(path, method):
            auth = request.headers.get("Authorization", "")
            presented = auth.split("Bearer ", 1)[1].strip() if auth.startswith("Bearer ") else ""
            is_admin = bool(presented) and hmac.compare_digest(presented, MERCHANT_ADMIN_KEY)
            if not is_admin:
                return Response(
                    content=json.dumps({"detail": f"Route '{path}' is isolated from external agents in external gateway mode"}),
                    status_code=403,
                    media_type="application/json",
                )
    return await call_next(request)

# Configure Northbound FastMCP Streamable HTTP Transport
_allowed_origins = [_frontend_origin] if _frontend_origin else []
_allowed_origins.extend(["http://localhost:3000", "http://127.0.0.1:3000"])
commerce_mcp.mcp_server.settings.streamable_http_path = "/"
commerce_mcp.mcp_server.settings.transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["localhost", "127.0.0.1", "localhost:*", "127.0.0.1:*", "testserver"],
    allowed_origins=list(dict.fromkeys(_allowed_origins)),
)
_mcp_asgi = commerce_mcp.mcp_server.streamable_http_app()
app.mount("/agent-commerce/mcp", _mcp_asgi)

app.include_router(agent_commerce.router, prefix="/agent-commerce/v1")
app.include_router(merchant.merchant_router)


@app.get("/.well-known/agent-commerce.json")
def get_agent_commerce_manifest() -> dict[str, Any]:
    """Agent discovery manifest without an SDK (APEX/ACI standard superset)."""
    return {
        "version": "0.1",
        "service": "Action Firewall — Agent Checkout",
        "merchant": {
            "id": DEFAULT_MERCHANT_ID,
            "display_name": DEFAULT_MERCHANT_NAME,
        },
        "currency": "INR",
        "capabilities": [
            "catalog_discovery",
            "purchase_scope_approval",
            "policy_gated_checkout",
        ],
        "endpoints": {
            "catalog": "/agent-commerce/v1/catalog",
            "catalog_jsonld": "/agent-commerce/v1/catalog/jsonld",
            "mcp": "/agent-commerce/mcp",
        },
        "authority_model": "per-purchase customer scope; human activation required; one registered action",
        "notes": "Every purchase passes a deterministic authorization gate before any provider call.",
    }


@app.get("/.well-known/ucp")
@app.get("/.well-known/ucp.json")
def get_ucp_manifest() -> dict[str, Any]:
    """Universal Commerce Protocol (UCP) / AP2 discovery manifest alias."""
    manifest = get_agent_commerce_manifest()
    manifest["protocol"] = "ucp/1.0"
    manifest["spec_alignment"] = {
        "standard": "Universal Commerce Protocol",
        "semantic_authority": "Action Firewall Purchase Envelope",
        "rail": "Razorpay Payments",
        "mandate_profile": "ap2_mandate_compatible",
    }
    return manifest



@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "ok": True,
        "status": "ok",
        "demo_mode": s.demo_mode,
        "catalog_size": len(catalog.load_catalog()),
        "payment_provider": s.payment_provider,
        "catalog_retrieval_mode": s.catalog_retrieval_mode,
        "envelope_drafting_mode": s.envelope_drafting_mode,
        "voice_ai_configured": bool(s.openai_api_key),
        "voice_transcription_model": s.openai_transcription_model,
        "fault_injection_enabled": s.fault_injection_enabled,
        "mcp": type(get_client()).__name__,
        "db_path": s.db_path,
    }


# ---------------- Demo Scenario (Loopback & Admin Only) ----------------
@app.post("/demo/scenario", response_model=demo_scenario.DemoScenarioResponse)
def set_demo_scenario(req: demo_scenario.DemoScenarioRequest, request: Request) -> demo_scenario.DemoScenarioResponse:
    s = get_settings()
    if not s.demo_mode:
        raise HTTPException(
            status_code=403,
            detail="Demo scenario fault injection is only permitted when DEMO_MODE=true",
        )

    client_host = request.client.host if request.client else ""
    is_loopback = client_host in ("127.0.0.1", "::1", "localhost", "testclient")
    auth_header = request.headers.get("Authorization", "")
    # Constant-time compare against the configured key. A prefix match would accept
    # any attacker-chosen token beginning with that literal.
    presented = auth_header.split("Bearer ", 1)[1].strip() if auth_header.startswith("Bearer ") else ""
    is_merchant_admin = bool(presented) and hmac.compare_digest(presented, MERCHANT_ADMIN_KEY)

    if not (is_loopback or is_merchant_admin):
        raise HTTPException(
            status_code=403,
            detail="Demo scenario fault injection is restricted to loopback or merchant-admin callers",
        )

    demo_scenario.set_active_scenario(req.scenario)
    return demo_scenario.DemoScenarioResponse(
        scenario=req.scenario,
        message=f"Active demo scenario updated to '{req.scenario.value}'",
    )


@app.get("/demo/scenario", response_model=demo_scenario.DemoScenarioResponse)
def get_demo_scenario(request: Request) -> demo_scenario.DemoScenarioResponse:
    s = get_settings()
    if not s.demo_mode:
        raise HTTPException(
            status_code=403,
            detail="Demo scenario inspection is only permitted when DEMO_MODE=true",
        )
    return demo_scenario.DemoScenarioResponse(
        scenario=demo_scenario.get_active_scenario(),
        message="Current active demo scenario",
    )


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


# ---------------- Safe Autopilot ----------------
@app.post("/voice/transcribe", response_model=VoiceTranscription)
async def transcribe_purchase_intent(request: Request) -> VoiceTranscription:
    """Transcribe audio into editable goal text without creating authority."""
    try:
        return await run_in_threadpool(
            voice.transcribe_audio,
            await request.body(),
            request.headers.get("content-type", "application/octet-stream"),
        )
    except voice.VoiceInputError as exc:
        raise HTTPException(422, str(exc)) from exc
    except voice.VoiceServiceUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/envelopes/draft", response_model=PurchaseEnvelope)
def draft_purchase_envelope(body: EnvelopeDraftRequest) -> PurchaseEnvelope:
    try:
        return autopilot.create_draft(body)
    except ValueError as exc:
        if "GOAL_NOT_UNDERSTOOD" in str(exc):
            raise HTTPException(
                422,
                "Goal not understood. Could not derive catalog tags from the request. "
                "Try goals like 'Buy supplies for a pasta dinner', 'Restock office snacks', or 'Breakfast run'.",
            ) from exc
        raise HTTPException(422, str(exc)) from exc


@app.get("/envelopes", response_model=list[PurchaseEnvelope])
def list_purchase_envelopes(user_id: str = "user_demo") -> list[PurchaseEnvelope]:
    return store.list_envelopes(user_id)


@app.get("/envelopes/{envelope_id}", response_model=PurchaseEnvelope)
def get_purchase_envelope(envelope_id: str) -> PurchaseEnvelope:
    envelope = store.get_envelope(envelope_id)
    if not envelope:
        raise HTTPException(404, "Unknown Purchase Envelope")
    return envelope


@app.post("/envelopes/{envelope_id}/activate", response_model=PurchaseEnvelope)
def activate_purchase_envelope(
    envelope_id: str, body: EnvelopeActivateRequest
) -> PurchaseEnvelope:
    try:
        return autopilot.activate(envelope_id, body)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/envelopes/{envelope_id}/revoke", response_model=PurchaseEnvelope)
def revoke_purchase_envelope(
    envelope_id: str, body: EnvelopeRevokeRequest
) -> PurchaseEnvelope:
    try:
        return autopilot.revoke(envelope_id, body)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/autopilot/execute", response_model=AutopilotExecuteResponse)
def execute_autopilot(body: AutopilotExecuteRequest) -> AutopilotExecuteResponse:
    try:
        return autopilot.execute(body)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/receipts/{grant_id}", response_model=ActionReceipt)
def get_receipt(grant_id: str) -> ActionReceipt:
    grant = store.get_action_grant(grant_id)
    if not grant:
        raise HTTPException(404, "Unknown action grant")
    return build_receipt(grant)


@app.post("/receipts/{grant_id}/verify", response_model=ActionReceiptVerification)
def verify_action_receipt(
    grant_id: str, receipt: ActionReceipt
) -> ActionReceiptVerification:
    grant = store.get_action_grant(grant_id)
    if not grant:
        raise HTTPException(404, "Unknown action grant")
    return verify_receipt(receipt, grant)


@app.get("/authority")
def get_authority(user_id: str = "user_demo") -> dict:
    return store.get_authority_view(user_id)


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
def mcp_tools(_: str = Depends(verify_merchant_admin)) -> dict:
    """Return the northbound buyer allowlist to authenticated merchant admins.

    Raw provider tools are never returned here.
    """
    tools = commerce_mcp.mcp_server._tool_manager.list_tools()
    tool_names = [t.name for t in tools]
    return {
        "surface": "northbound_buyer_allowlist",
        "notice": "Strict customer-scoped allowlist exposed to AI buyers",
        "tool_names": tool_names,
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in tools
        ],
    }


@app.get("/mcp/southbound-tools")
@app.get("/mcp/tools/southbound")
def mcp_southbound_tools(_: str = Depends(verify_merchant_admin)) -> dict:
    """Southbound provider surface — never exposed to external buyers.

    Restricted to merchant-admin for audit and evidence verification.
    """
    client = get_client()
    try:
        return {
            "surface": "southbound_provider_surface",
            "notice": "Internal provider adapter surface — never exposed to AI buyers",
            "client": type(client).__name__,
            "tools": client.list_tools(),
        }
    except Exception as exc:
        raise HTTPException(502, f"Provider MCP unreachable: {exc}")


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


@app.post("/provider/webhooks/razorpay")
async def handle_razorpay_webhook(request: Request) -> dict[str, Any]:
    """Consume HMAC-SHA256 verified Razorpay webhooks.

    Enforces:
    1. Raw body HMAC-SHA256 signature verification (X-Razorpay-Signature) BEFORE parsing.
    2. Rejects with 400 and an audit row on signature mismatch or missing signature.
    3. Idempotent by provider event id; replayed webhooks are immediate no-ops.
    4. Unmatched grants are audited and ignored (never auto-created).
    5. State transition through the exact same reconciler.apply_observation state machine.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature") or request.headers.get("x-razorpay-signature") or ""

    settings = get_settings()
    secret = settings.razorpay_webhook_secret
    if not secret:
        if settings.demo_mode or settings.payment_provider == "simulated":
            secret = settings.action_receipt_secret or "whsec_action_firewall_demo"
        else:
            store.log_event(
                event="WEBHOOK_REJECTED_UNCONFIGURED",
                code="NO_WEBHOOK_SECRET",
                payload={"error": "Webhook secret is not configured on server"},
            )
            raise HTTPException(status_code=500, detail="Webhook secret unconfigured")

    computed_signature = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, computed_signature):
        client_ip = request.client.host if request.client else "unknown"
        store.log_event(
            event="WEBHOOK_SIGNATURE_INVALID",
            code="SIGNATURE_MISMATCH",
            payload={
                "received_signature": signature[:16] + "..." if signature else None,
                "client_ip": client_ip,
                "body_len": len(raw_body),
            },
        )
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        data = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Malformed JSON payload: {exc}")

    event_id = data.get("event_id") or data.get("id") or f"body_{hashlib.sha256(raw_body).hexdigest()[:24]}"
    event_type = data.get("event") or ""
    payload_obj = data.get("payload") or {}

    plink_entity = payload_obj.get("payment_link", {}).get("entity", {})
    payment_entity = payload_obj.get("payment", {}).get("entity", {})

    plink_id = plink_entity.get("id") or payment_entity.get("payment_link_id")
    grant_id = (
        plink_entity.get("notes", {}).get("grant_id")
        or payment_entity.get("notes", {}).get("grant_id")
    )
    provider_ref = plink_id or payment_entity.get("id")

    if not grant_id and plink_id:
        existing_grant = store.get_action_grant_by_provider_ref(plink_id)
        if existing_grant:
            grant_id = existing_grant.id

    # Idempotency check: record event id
    is_new = store.record_webhook_event(
        event_id=event_id,
        event_type=event_type,
        provider_ref=provider_ref,
        payload=data,
    )
    if not is_new:
        return {
            "status": "already_processed",
            "event_id": event_id,
            "idempotent": True,
        }

    # If grant does not exist, audit and ignore
    if not grant_id:
        store.log_event(
            event="WEBHOOK_UNMATCHED_GRANT",
            code="UNKNOWN_GRANT",
            payload={"event_id": event_id, "event_type": event_type, "provider_ref": provider_ref},
        )
        return {
            "status": "unmatched_grant",
            "event_id": event_id,
            "provider_ref": provider_ref,
        }

    grant = store.get_action_grant(grant_id)
    if not grant:
        store.log_event(
            event="WEBHOOK_UNMATCHED_GRANT",
            code="GRANT_NOT_FOUND",
            payload={"event_id": event_id, "grant_id": grant_id},
        )
        return {
            "status": "unmatched_grant",
            "event_id": event_id,
            "grant_id": grant_id,
        }

    status_str = str(plink_entity.get("status") or payment_entity.get("status") or "").lower()
    amount_paid = plink_entity.get("amount_paid") or payment_entity.get("amount") or 0

    if event_type in ("payment_link.paid", "payment.captured") or status_str in ("paid", "captured"):
        obs_status = "paid"
    elif event_type in ("payment_link.cancelled", "payment_link.expired") or status_str in ("cancelled", "expired"):
        obs_status = status_str
    elif event_type == "payment.failed" or status_str == "failed":
        obs_status = "failed"
    else:
        obs_status = status_str or "open"

    obs = reconciler.Observation(
        reachable=True,
        provider_status=obs_status,
        amount_paid_paise=int(amount_paid) if isinstance(amount_paid, int) else 0,
        raw=data,
    )

    reconciliation = reconciler.apply_observation(grant, obs)

    return {
        "status": "processed",
        "event_id": event_id,
        "grant_id": grant.id,
        "before": reconciliation.before.value,
        "after": reconciliation.after.value,
        "changed": reconciliation.changed,
        "note": reconciliation.note,
    }

