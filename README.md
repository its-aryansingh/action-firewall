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

Current verified baseline: **51 backend tests passing**, a successful production
frontend build, and **0 known npm audit vulnerabilities**. Re-run these commands on
the final commit before recording or submitting.

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

## Submission artifacts

- [Five-minute demo script](docs/DEMO_SCRIPT.md)
- [Architecture and failure semantics](docs/ARCHITECTURE.md)
- [Finish and submit plan](docs/BUILD_PLAN.md)
- [Evidence-led strategy and risk register](docs/SUBMISSION_STRATEGY.md)
- [Browser pitch deck](docs/pitch-deck.html)
- [PowerPoint pitch deck](docs/Razorpay_Buildathon_Action_Firewall_Deck.pptx)
- [Dated market and source context](market-context.md)

Vulcan is **product context, not a dependency**. This repository does not claim a
Vulcan API, SDK, model endpoint, partnership, or internal Razorpay access. The overlap
is architectural: learned payment intelligence should remain upstream of a bounded,
auditable action boundary.

## Honest limitations

- Demo identity is a browser-provided user/agent identifier, not production-grade
  authentication or workload identity.
- Policy records and grants are not cryptographically signed attestations.
- `UNKNOWN` has safe accounting and explicit reconciliation semantics, but the MVP
  does not include a background Razorpay status reconciler.
- Payment-link issuance is observable; customer payment and settlement require
  signed webhook or provider-state verification outside the current demo.
- SQLite `BEGIN IMMEDIATE` proves the concurrency invariant on one service instance.
  Production deployment would use a transactional database, unique constraints and
  an outbox/reconciliation worker.
- Pinecone, Langfuse and Remote MCP are optional integrations, not prerequisites for
  the deterministic authorization proof.

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
