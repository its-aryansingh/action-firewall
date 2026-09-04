# Action Firewall

**Agentic checkout authorization for Razorpay — Track 01: AI Growth & Agentic Commerce**

> An AI agent may propose a cart. Only a deterministic, versioned, customer-defined policy may authorize a payment action.

Action Firewall puts a narrow authorization boundary between an AI shopping agent and
Razorpay's payment tooling. The model can search the catalog and assemble a cart, but
it cannot approve spend, mint its own authority, change payment arguments after
approval, or dispatch a payment action from chat. The customer confirms the exact
cart; the backend re-evaluates the current policy and reserves headroom atomically;
only then can one registered action be dispatched once.

## What the product proves

- **Proposal is not authorization.** `POST /chat` can only return a cart proposal and
  policy preview. It never calls a state-changing payment tool.
- **Confirmation is exact.** `POST /checkout/confirm` includes the expected cart hash.
  A changed cart fails closed and must be confirmed again.
- **Authorization uses current state.** The backend re-reads the policy, verifies every
  rule, and reserves cap headroom in one `BEGIN IMMEDIATE` transaction.
- **Authority is one-use and argument-bound.** A grant binds the user, agent, session,
  purchase attempt, policy version and hash, cart hash, action name, canonical
  arguments, amount and currency.
- **The actuator is closed.** The only registered payment action is
  `create_payment_link`; arbitrary tool names are rejected.
- **Dispatch has one owner.** An atomic claim and dispatch token prevent concurrent
  callers from redeeming the same grant twice.
- **Ambiguity does not free exposure.** A timeout or uncertain provider result becomes
  `UNKNOWN`. Headroom remains held and the system will not auto-retry until an
  authoritative provider observation resolves the outcome.
- **Issuance is not settlement.** Creating a payment link records
  `action_issued`. Only separate, verified payment evidence may record `settled`.

## Trust boundary

```text
Untrusted / probabilistic                         Trusted / deterministic

Shopper prompt -> catalog retrieval -> cart  ──> exact-cart confirmation
                       proposal                   current-policy evaluation
                                                  atomic headroom reservation
                                                  exact one-use action grant
                                                  one-owner dispatch claim
                                                  create_payment_link actuator
                                                  append-only event evidence
```

The model may select known catalog SKUs and quantities and explain a proposal. It
may not invent prices, authorize an action, choose an unregistered action, edit a
policy, resolve an unknown provider outcome, or declare a payment settled.

## Checkout lifecycle

```text
POST /chat
  retrieve catalog -> propose cart -> deterministic preview -> confirmation required

POST /checkout/confirm
  verify cart hash
    -> atomically re-read policy + authorize + reserve
    -> mint exact grant
    -> claim grant for one dispatcher
    -> call registered create_payment_link action
       -> accepted response: action_issued, exposure remains accounted
       -> definitive failure: release reservation
       -> ambiguous failure: UNKNOWN, hold exposure, no automatic retry
```

Policy edits are serialized against authorization and dispatch claims. Every edit
increments `mandate.version` (the database and route retain the historical name
`mandate`; the user-facing product term is **policy**). A policy edit or revocation
before dispatch invalidates the older grant.

## Repository map

```text
backend/
  app/agent.py          proposal and explicit-confirmation flows
  app/mandate.py        pure policy evaluator; all money is integer paise
  app/store.py          policies, atomic grants, dispatch state and audit events
  app/mcp_client.py     closed action registry; simulated and Razorpay MCP clients
  app/catalog.py        Pinecone retrieval with deterministic offline fallback
  app/main.py           FastAPI routes
  tests/                policy, boundary, concurrency and recovery proof
  scripts/demo.py       disposable, offline five-minute rehearsal
frontend/
  app/page.tsx          chat, exact-cart confirmation and action status
  app/mandate/page.tsx  policy limits, categories and revocation
  app/audit/page.tsx    lifecycle evidence and safety metrics
data/catalog.json       fixed-price demo catalog
docs/                   architecture, demo script, build plan and submission deck
```

## Quick start

The default `DEMO_MODE=true` path requires no API keys and makes no network calls.

```powershell
# Terminal 1
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend
npm install
Copy-Item .env.local.example .env.local
npm run dev
```

Open `http://localhost:3000`. The backend health check is
`http://localhost:8000/health`.

Run the proof suite and headless rehearsal:

```powershell
cd backend
python -m pytest -q
python scripts/demo.py

cd ..\frontend
npm run build
npm audit
```

Current verified baseline: **61 backend tests passing**, a successful production
frontend build, and **0 known npm audit vulnerabilities**. Re-run these commands on
the final commit before recording or submitting.

## Demo proof

The five-minute path shows one narrow loop end to end:

1. The agent proposes a grocery cart; no payment tool is called.
2. A larger natural-language checkout request remains a proposal and exceeds the cap.
3. Explicit confirmation of that exact cart is denied; there is no actuator call.
4. The shopper removes the premium items; one exact grant issues one simulated
   payment link for the smaller cart.
5. The policy is revoked; the next confirmation fails against the new version.
6. The audit view distinguishes denied value, issued-link value, confirmed test
   payment value, unknown exposure and unauthorized actuator calls.
7. The test proof shows atomic headroom accounting and eight concurrent redemptions
   of one grant producing one simulated provider call.

The concurrency regression is the strongest engineering evidence: the intentionally
naive check-then-act path can record ₹2,400 against a ₹1,000 cap. Atomic reservation
caps eight concurrent ₹300 requests at ₹900, while the exact-grant test collapses
eight simultaneous redemptions to one simulated provider call.

## Metrics

`GET /metrics` reports observed system state without relabelling it:

| Metric | Meaning |
|---|---|
| `authorization_denial_rate` | Share of authorization attempts denied by policy |
| `denied_requested_value_paise` | Requested value that never reached the actuator |
| `payment_link_issued_value_paise` | Value for which the system issued links; not settlement |
| `confirmed_test_payment_value_paise` | Value with separate confirmed test evidence |
| `unknown_outcome_value_paise` | Value held because provider outcome is ambiguous |
| `outstanding_authorized_exposure_paise` | Live reserved or unresolved policy headroom |
| `unauthorized_actuator_calls` | Rejected attempts to bypass the action boundary |

## Failure and recovery semantics

| Failure | Safe behavior | Recovery |
|---|---|---|
| Cart changes after preview | Reject confirmation | Show the new cart and request confirmation again |
| Policy edited or revoked | Cancel stale grant | Re-evaluate only after a new explicit confirmation |
| Concurrent confirmations | Atomic cap accounting | Return the winning result or a deterministic denial |
| Definite provider rejection | Record failure and release hold | Customer may start a new purchase attempt |
| Timeout or dropped response | Mark `UNKNOWN`; keep hold | Reconcile against authoritative provider state |
| Process crash during dispatch | Recover stale `dispatching` to `UNKNOWN` | Reconcile; never blind-retry |

## Optional live integrations

The offline path is the submission-safe default. With test credentials,
`DEMO_MODE=false` can use Razorpay Remote MCP for the registered
`create_payment_link` action and Pinecone for retrieval. Langfuse tracing is optional.
Every external dependency has a deterministic fallback so the safety proof does not
depend on network availability.

## Documentation

- [Architecture and failure semantics](docs/ARCHITECTURE.md)
- [Five-minute demo script](docs/DEMO_SCRIPT.md)
- [Adversarial audit findings](docs/AUDIT_FINDINGS.md) — what broke, what is fixed,
  and what is still open

Vulcan is **product context, not a dependency**. This repository does not claim a
Vulcan API, SDK, model endpoint, partnership, or internal Razorpay access. The overlap
is architectural: learned payment intelligence should remain upstream of a bounded,
auditable action boundary.

## Honest limitations

These are stated precisely because the rest of this document makes precise
claims. Each was reproduced against this repository, not inferred.

**There is no authentication on any route.** Not a weak one — none. `POST
/mandates` and `PATCH /mandates/{id}` are unauthenticated, so any caller who can
reach the API can raise, lower or revoke the policy the firewall enforces.
`GET /audit` is unscoped and publishes session identifiers and cart hashes.
Because `cart_hash` is a digest of catalog-derived fields with no session salt,
a caller holding a session id can read the audit trail, recompute the current
hash, and confirm a payment action against someone else's session and policy
headroom. The exact-cart fence works exactly as designed and does not help here:
it proves the confirmer knows the cart, not that they are the shopper. The
authorization boundary in this MVP therefore binds **possession of a session id,
not a person.** Closing it needs an authenticated principal and per-actor
authorization on every route, which is production work this repository has not
done.

**The planner adds items the shopper did not ask for.** When the heuristic
planner cannot parse a message it falls back to adding the top retrieved
catalog items. A message like "what are your delivery hours" puts several
hundred rupees of goods in the cart. Nothing can be dispatched without explicit
confirmation of the exact hash, so this cannot move money on its own — but it is
a real quality defect and it fires with the shipped catalog, no adversary
required.

**Retrieved catalog text is not treated as untrusted.** Product names and tags
are concatenated into the planner prompt without delimiting or data framing, and
a name containing a distinctive common word can cause its SKU to be matched
against an unrelated shopper message. Injection cannot set a price, invent a
SKU, or name an action — those are all server-side — but it can influence which
real SKUs are proposed and can author the shopper-facing reply text. A
multi-model injection corpus is the outstanding proof gap.

**Unresolved exposure never ages out of the window.** Settled spend rolls off a
weekly window; `action_issued`, `dispatching` and `unknown` exposure does not,
by design, because an issued link may still be paid. Combined with the missing
reconciler below, a long-lived policy's usable headroom only decreases. `GET
/mandates/{id}/usage` reports these as window figures; for unresolved exposure
they are lifetime figures.

**Reconciliation is pull-based, not event-driven.** `POST /actions/{id}/reconcile`
and `POST /actions/reconcile` resolve open actions by reading the provider, and
`recover_stale_dispatches` runs once at startup — but nothing runs them on a
schedule and there is no signed webhook consumer. An outcome stays unresolved
until something calls the route.

**Settlement is observed, never asserted.** `action_issued` records that a link
exists. `settled` is written only by `app/reconciler.py` after it reads the
provider's own view of the action, and no field on any route lets a caller
declare that money moved. A provider we cannot reach leaves the state and the
exposure exactly as they were, because not knowing is not the same as not paid.

**Evidence is append-only, not tamper-proof.** The audit table rejects updates
and deletes at the database layer, and `PRAGMA recursive_triggers=ON` closes the
`INSERT OR REPLACE` path that would otherwise rewrite a row in place. It is not
hash-chained, not signed, and lives inside the service's own trust domain, so it
resists accident and casual tampering — not a determined operator.

**`denied_requested_value_paise` counts denial events, not distinct carts.**
Re-submitting one blocked cart five times reports five times the value. It is a
measure of blocked attempts, not of loss prevented, and nothing here should be
read as prevented fraud.

**Policy records and grants are not cryptographically signed attestations.**

**SQLite `BEGIN IMMEDIATE` proves the concurrency invariant on one service
instance.** In-process session state means a second worker cannot serve a
confirmation for a cart the first worker holds. Production deployment would need
a transactional database, unique constraints, and an outbox or reconciliation
worker.

**Pinecone, Langfuse and Remote MCP are optional.** None is required to
reproduce the deterministic authorization proof.

## Continue with Claude Code

The repository includes a committed Claude Code handoff:

- `CLAUDE.md` — project workflow and non-negotiable authorization invariants;
- `claude/project-brief.md` — authoritative product state and next priorities;
- `.claude/rules/` — path-scoped backend, frontend, and evidence rules;
- `.claude/settings.json` — shared safe-command permissions, secret-file denials,
  destructive-Git denials, and disabled AI commit attribution.

Start Claude Code from the repository root:

```powershell
claude
```

On the first interactive launch, review and accept the workspace trust prompt. Then
run `/context` to confirm `CLAUDE.md` is loaded and `/status` to confirm the project
settings source is active. Personal overrides belong in `CLAUDE.local.md` or
`.claude/settings.local.json`; both are intentionally ignored by Git.

No Claude-side Razorpay MCP configuration is committed. Runtime Razorpay access
continues to use the backend adapter and environment variables, so credentials stay
outside source control.

## Strategic scope

Action Firewall remains the primary Track 01 submission because its hardest claims
are demonstrated in the current repository: exact confirmation, current-policy
authorization, concurrency-safe reservation, one-use dispatch and conservative
unknown-outcome handling. **Retry Budget** remains a secondary Track 03 challenger;
it should replace this direction only if it can produce stronger reproducible batch
evidence and compliance-safe execution within the remaining time.

Current public references to verify before submission:

- Buildathon tracks and deliverables: <https://razorpay.com/buildathon/>
- Razorpay MCP tool reference: <https://razorpay.com/docs/mcp-server/tools-reference/>
- Razorpay Remote MCP setup: <https://razorpay.com/docs/mcp-server/remote/>
- Razorpay Payment Links lifecycle: <https://razorpay.com/docs/payments/payment-links/create/>
