# AI-Native Agentic Checkout with UAP Mandate Verification

**Razorpay AI Buildathon 2026 — Track 01: AI Growth & Agentic Commerce**

> Agentic commerce is an **authorization** problem, not a checkout problem.

A merchant becomes transactable by an AI buyer end-to-end — discovery, cart, payment —
with every money action **bounded and gated** by a human-authorised, revocable mandate
that simulates NPCI's Unified Agent Protocol (UAP), built on the UPI Circle delegation
pattern and Razorpay's UPI Reserve Pay.

---

## The thesis in one paragraph

The industry instinct is to make agentic payments a *faster button*. That is the wrong
frame. The moment an autonomous agent holds a payment instrument, the merchant inherits
unbounded chargeback liability and the consumer inherits runaway-spend risk. What is
missing is not a checkout — it is an **authorization layer** that is deterministic,
auditable, and revocable. This project builds that layer, and proves it by trying to
break it on stage.

## Architecture — deliberately a single agent

At FTX26, Razorpay's engineering team argued that for commerce tasks a single
well-instrumented agent with full context hits fewer failure modes and scales more
predictably than a multi-agent swarm. This build takes that position seriously.

```
Shopper (Next.js chat)
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI single-agent orchestrator                           │
│                                                              │
│  1. retrieve_catalog   Pinecone RAG over the merchant SKUs   │
│  2. plan_cart          LLM proposes SKUs + qty (never price) │
│  3. mandate_check  ◀── DETERMINISTIC GATE. Pure. Unit-tested │
│  4. mcp_tool_call      Razorpay Remote MCP — only if ALLOWED │
└──────────────────────────────────────────────────────────────┘
        │                          │
        ▼                          ▼
  SQLite: mandates,          mcp.razorpay.com/mcp
  spend ledger, audit        create_payment_link
        │                    capture_payment
        ▼
  Langfuse trace (one trace per turn, four named spans)
```

The LLM produces a **proposal**. It never decides whether money may move.
`app/mandate.py:verify()` is a pure function with no I/O, and it is the only path to a
money tool — `mcp_client.call_tool()` raises `MandateViolation` if handed a denied
decision, so even a caller that ignores the gate cannot spend. Defence in depth.

## Repository layout

```
backend/
  app/
    mandate.py       ★ the UAP verification layer — pure, deterministic, tested
    agent.py           single-agent pipeline + graceful-failure handling
    mcp_client.py      Razorpay Remote MCP (Streamable HTTP) + simulated client
    catalog.py         Pinecone RAG with a deterministic keyword fallback
    store.py           mandates, spend ledger, append-only audit log
    observability.py   Langfuse spans / scores
    models.py          domain models — all money in integer paise
    main.py            FastAPI routes
  tests/             22 tests, the money-gate boundary cases first
  scripts/demo.py    headless dress rehearsal of the live demo
frontend/
  app/page.tsx           AI buyer chat, with the mandate verdict on every turn
  app/mandate/page.tsx   Mandate Dashboard — set, cap, restrict, revoke
  app/audit/page.tsx     Audit trail + the two judge-facing metrics
data/catalog.json        38-SKU agent-readable merchant catalog
docs/DEMO_SCRIPT.md      the four-act stage script, timed
```

## Quick start

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # DEMO_MODE=true works with no keys
uvicorn app.main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
npm install
cp .env.local.example .env.local
npm run dev                                          # http://localhost:3000

# 3. Rehearse the demo with no browser and no network
cd backend && python scripts/demo.py

# 4. Prove the gate
cd backend && pytest -q                              # 22 passed
```

### Going live

`DEMO_MODE=true` runs the whole system with a simulated MCP client and a keyword
retriever — no keys, no network, nothing to fail on stage. To go live:

```bash
# Razorpay Remote MCP: base64 the test key pair
printf '%s' "$RAZORPAY_KEY_ID:$RAZORPAY_KEY_SECRET" | base64
# put the result in RAZORPAY_MCP_TOKEN, then:
DEMO_MODE=false
```

Seed the vector catalog once: `python -m app.catalog` (creates the Pinecone serverless
index and upserts all 38 SKUs).

For an AI coding assistant to reach the same server, the equivalent config is:

```json
{ "mcpServers": { "razorpay": { "command": "npx", "args": [
    "mcp-remote", "https://mcp.razorpay.com/mcp",
    "--header", "Authorization: Basic <base64 token>" ] } } }
```

## The mandate model

| Control | Field | Enforced in |
|---|---|---|
| Window ceiling (daily / weekly / monthly) | `cap_paise` | `verify()` step 5 |
| Per-transaction ceiling | `per_txn_cap_paise` | `verify()` step 4 |
| Category allow / block list | `allowed_categories`, `blocked_categories` | `verify()` step 3 |
| Instant revocation | `active` | `verify()` step 2 |
| Rolling spend against the window | `spend_ledger` | `spent_in_window()` |

Every edit bumps `mandate.version`. The agent re-reads the mandate row on **every**
turn — there is no cache to invalidate — so a limit change binds on the very next
prompt. That is the *Revocation Latency* metric.

## Metrics the judges care about

Exposed at `GET /metrics` and rendered on `/audit`:

- **Mandate Breach Attempt Rate** — how often the agent tried to exceed authority and
  was stopped at the logic layer.
- **Revocation Latency** — time from dashboard edit to the new ceiling binding
  (one turn, no cache).
- **Value blocked** vs **value settled**.
- **Chargeback liability: ₹0** — no transaction ever left the mandate envelope.

## Engineering notes worth defending in the interview

- **Money is integer paise everywhere.** No float rupees touch the codebase.
- **The cap is inclusive**, and there is a test for cap, cap−1 and cap+1. Off-by-one in
  a limit check is a production incident, not a style nit.
- **A revoked mandate is not the same as no mandate.** Collapsing them tells the shopper
  to create a mandate they already have and loses the revocation audit trail.
- **Hallucinated SKUs are dropped, never priced.** `_apply_ops` only accepts SKUs that
  exist in the catalog.
- **Graceful failure is computed, not improvised.** `suggest_downgrade()` deterministically
  drops the priciest lines until the cart fits the remaining headroom, then re-verifies.
- **The audit log is append-only and written before the tool call**, so a blocked attempt
  is as durable as a successful one.

## Track 01 requirements → where they are met

| Requirement | Implementation |
|---|---|
| Merchant transactable by an AI buyer end-to-end | RAG discovery → cart → Razorpay MCP payment link |
| Money actions bounded and gated | `mandate.verify()` before every money tool; `MandateViolation` as backstop |
| Show the audit trail | Langfuse trace per turn + `/audit` append-only log |
| One failure handled gracefully | Mandate breach → hard block → priced downgrade offer |
