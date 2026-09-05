# Action Firewall — Safe Autopilot Checkout

**Razorpay AI Buildathon — Track 01: AI Growth & Agentic Commerce**

> One approval for the job. Zero authority beyond it.

Action Firewall lets an AI buyer recover from ordinary checkout changes without
giving the model reusable payment authority. The shopper approves one structured,
revocable **Purchase Envelope**. AI may draft the envelope, plan the cart, rank
eligible alternatives, and explain the outcome. Only deterministic code can verify
the final quote, derive one exact Action Grant, and dispatch one registered Razorpay
action.

The original exact-cart confirmation flow remains available at `/baseline` as the
measured control. Safe Autopilot is the primary product at `/`.

## Why this is more than a rules engine with AI decoration

The useful job is probabilistic: translate an open-ended request into product
requirements, retrieve catalog candidates, assemble a quote, and recover when the
preferred SKU is unavailable. The dangerous decision is not probabilistic: whether
the final merchant, total, item constraints, destination, time window, currency and
action still match what the shopper approved.

Action Firewall keeps that seam explicit:

| Actor | May do | May not do |
|---|---|---|
| AI planner | Draft, search, assemble, rank alternatives, explain | Activate or widen authority; set trusted price; mint a grant; dispatch |
| Shopper | Review and activate the envelope; revoke while active | Supply server-owned catalog facts or action hashes |
| Deterministic verifier | Rehydrate catalog facts; check every envelope field; emit a field-level delta | Guess intent or waive a failed field |
| Action Firewall | Atomically reserve exposure; mint an exact one-use grant | Call an unregistered action or reuse a spent envelope |
| Razorpay adapter | Redeem one matching grant for `create_payment_link` | Change arguments, reuse a grant, or turn ambiguity into a retry |

Vulcan is product context, not a dependency. This repository does not claim a
Vulcan API, SDK, model endpoint, partnership, or internal Razorpay access. The honest
positioning is: **Vulcan can decide what is likely to work. Action Firewall proves
whether this agent is allowed to do it.**

## Purchase Envelope

One activation binds:

- user and AI buyer identity within the application;
- one approved merchant;
- INR and a maximum total in integer paise;
- required item slots expressed through server-owned catalog tags;
- blocked categories;
- one saved fulfilment profile and a delivery deadline;
- an envelope expiry;
- one purchase only;
- one registered action: `create_payment_link`.

The envelope is an application authorization object. It is **not** an NPCI, UPI,
banking, or regulatory mandate.

## End-to-end workflow

```text
shopper goal
  -> AI or deterministic fallback drafts Purchase Envelope
  -> shopper reviews every field and activates once
  -> planner assembles final merchant quote
  -> deterministic verifier rehydrates catalog facts
       |-- all fields match -> atomic one-use reservation
       |                     -> exact Action Grant
       |                     -> one dispatch owner
       |                     -> Razorpay create_payment_link
       `-- field differs ----> Policy Delta
                               -> repair inside authority, request only the changed
                                  field, or stop
```

The final grant binds the envelope ID, version and hash; policy ID, version and
hash; user, agent, session and merchant; quote and cart hashes; action name and
schema; exact canonical arguments; amount; currency; attempt identity; and expiry.
The actuator rechecks the current policy and envelope immediately before dispatch.

## Failure semantics

| Event | Behavior | Recovery |
|---|---|---|
| Preferred SKU unavailable | Pick the next eligible catalog item, then re-verify every field | Continue without a new approval only if the quote remains inside the envelope |
| Price exceeds maximum | No grant; return `max_total_paise` delta | Re-plan below the cap or ask for a cap-only approval |
| Merchant changes | No grant; return `merchant_id` delta | Fresh approval; never silently widen merchant authority |
| Destination changes | No grant; return fulfilment delta | Fresh approval |
| Envelope revoked after authorization | Dispatch fence cancels the undispatched grant | Create a new envelope if the shopper still wants the job |
| Concurrent attempts | `BEGIN IMMEDIATE` plus a unique live-envelope constraint selects one action | Losers receive deterministic denial or the stored state |
| Provider timeout after dispatch | State becomes `UNKNOWN`; exposure and the envelope's one use remain occupied | Reconcile authoritative provider state; never blind-retry |
| Dropped successful response | Same attempt/session/bindings return the stored grant and result | No second provider call |

Creating a payment link records `ACTION_ISSUED`, not payment or settlement. Only a
later provider observation can record `SETTLED`.

## Evidence

### Integration tests

The current suite has **76 passing backend tests**. It includes:

- pure spend-policy boundaries and integer-paise arithmetic;
- proposal-only chat and strict planner schemas;
- exact-cart baseline confirmation;
- envelope draft/activation hash binding;
- safe stock-loss substitution;
- price, merchant, destination, expiry, category and catalog-fact refusals;
- eight concurrent attempts under one envelope producing one issued action;
- policy/envelope revocation between authorization and dispatch;
- exact idempotency replay and binding conflicts;
- timeout-to-`UNKNOWN`, stale-dispatch recovery and reconciliation;
- append-only SQLite audit enforcement;
- application-signed Action Receipt verification.

### Generated authorization corpus

`python scripts/evaluate_autopilot.py` generates **650 deterministic cases** from
50 fixed seeds across 13 families and 10 goal fixtures (104 distinct carts). The verified 5 September 2026 run reported:

- 100/100 in-envelope quotes accepted;
- 550/550 boundary violations blocked;
- 50/50 stock-loss cases recovered inside the same envelope;
- zero unexpected authorizations in that corpus.

These are synthetic authorization-correctness results, not claims of production
conversion, GMV, fraud reduction, or payment success. See
[docs/EVALUATION.md](docs/EVALUATION.md).

### Action Receipt

Each grant can be rendered as an application-signed HMAC-SHA256 receipt containing
the exact policy, envelope, quote, cart, action-argument and lifecycle hashes. The
demo uses an explicit demo key; `ACTION_RECEIPT_SECRET` is required outside demo
mode. This proves what this application recorded. It is not a Razorpay signature,
external timestamp, or tamper-proof ledger.

## Demo

The five-minute path is designed around one useful recovery and one hard refusal:

1. Describe “Buy supplies for a pasta dinner” with a ₹600 maximum.
2. Review and activate the complete envelope once.
3. Simulate stock loss; show a deterministic eligible substitution and one issued
   simulated payment link without another approval.
4. Start a new job; change the merchant; show a field-level refusal before any grant.
5. Show the timeout-to-`UNKNOWN` path and exact retry suppression.
6. Open `/audit` and finish on the 650-case evaluator plus concurrency test.

Full script: [docs/SAFE_AUTOPILOT_DEMO.md](docs/SAFE_AUTOPILOT_DEMO.md).

The original exact-cart demonstration remains documented in
[docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Quick start

The default `DEMO_MODE=true` path requires no credentials and makes no network calls.

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

Open `http://localhost:3000`.

Run all proof paths:

```powershell
cd backend
python -m pytest -q
python scripts/evaluate_autopilot.py
python scripts/demo_autopilot.py
python scripts/demo.py

cd ..\frontend
npm run build
```

## API surface

| Route | Purpose |
|---|---|
| `POST /envelopes/draft` | Turn a goal and maximum into a reviewable draft |
| `POST /envelopes/{id}/activate` | Hash-bound explicit shopper activation |
| `POST /envelopes/{id}/revoke` | Version-bound instant application revocation |
| `POST /autopilot/execute` | Quote, verify, reserve, grant and dispatch—or refuse |
| `GET /receipts/{grant_id}` | Return the application-signed current-state receipt |
| `POST /receipts/{grant_id}/verify` | Verify the submitted receipt against stored grant state |
| `POST /actions/{grant_id}/reconcile` | Read provider state and resolve an open action |
| `GET /audit` | Append-only application event evidence |
| `GET /metrics` | Outcome-aware safety and lifecycle metrics |

The legacy `/chat`, `/checkout/confirm`, and `/mandates` routes remain for the
exact-cart baseline and backward compatibility.

## Repository map

```text
backend/
  app/envelope.py       canonical envelope/quote hashing and pure verifier
  app/autopilot.py      draft, activation, recovery and execution workflow
  app/store.py          versioned policies, atomic grants, one-use ledger and audit
  app/mcp_client.py     closed simulated/live Razorpay action adapter
  app/receipts.py       application-signed Action Receipts
  app/agent.py          preserved exact-cart baseline and model/fallback planner
  tests/                boundary, concurrency, lifecycle and regression proof
  scripts/
    demo_autopilot.py   disposable primary five-minute rehearsal
    evaluate_autopilot.py reproducible 400-case authorization corpus
    demo.py             preserved exact-cart baseline rehearsal
frontend/
  app/page.tsx          primary Safe Autopilot product flow
  app/baseline/page.tsx exact-cart control
  app/audit/page.tsx    event evidence and observed metrics
data/catalog.json       fixed-price, server-owned demo catalog
docs/                   architecture, evaluation, demo and research evidence
```

## Optional live services

With test credentials and `DEMO_MODE=false`, the registered
`create_payment_link` action can use Razorpay Remote MCP, catalog retrieval can use
Pinecone plus OpenAI embeddings, the draft/planner can use an OpenAI model, and
tracing can use Langfuse. Every dependency has a deterministic demo fallback. No
fallback receives broader authority than the live component it replaces.

Shipped evidence runs with `envelope_drafting_mode=replay` by default (offline and
deterministic replay of recorded model outputs from `backend/tests/fixtures/llm_envelope_drafts.json`),
exercising the full model-output schema parser and server-side tag vocabulary validation
without requiring an OpenAI API key. Live drafting (`envelope_drafting_mode=llm`) is supported
with `OPENAI_API_KEY`, and `envelope_drafting_mode=deterministic` is available as a fallback.

## Honest limitations

- **No authentication or tenancy.** Demo routes are unauthenticated. Identity binds
  session possession, not a verified person. Do not expose this service publicly.
- **Synthetic merchant environment.** Catalog prices, stock-loss and drift scenarios
  are controlled test fixtures. No live inventory feed is integrated.
- **One merchant, currency, destination profile and action.** This is a narrow proof,
  not a general procurement engine.
- **Application-signed evidence only.** Audit rows reject update/delete and receipts
  are HMAC-signed, but neither is externally anchored or administrator-proof.
- **Pull-based reconciliation.** Open actions require the reconciliation route; a
  signed webhook consumer and scheduler remain production work.
- **SQLite single-instance write serialization.** The transaction proof is real for
  this deployment shape. Production would move the same invariants to a durable
  transactional store and outbox.
- **Model evaluation remains incomplete.** The deterministic authorization gate has a
  generated corpus; arbitrary-language envelope drafting still needs a labeled
  multi-model quality and prompt-injection evaluation.
- **No AP2 compliance claim.** The Purchase Envelope is AP2-shaped in its separation
  of human intent from exact machine action, but no conformance program is claimed.
- **No Vulcan runtime claim.** Alignment is architectural and product-adjacent only.
- **No ceiling spans envelopes.** Each activated Purchase Envelope mints its own
  spend fence, so five approved ₹600 jobs are five independent ₹600 caps and
  nothing aggregates them. This follows from one envelope being one human
  approval, but it means the system cannot yet answer "what is this agent's
  total outstanding authority across all jobs".
- **A receipt attests to a state snapshot, not to the authorization.** `state`
  and `updated_at` are inside the signed body, so a receipt issued at
  `action_issued` stops verifying once the grant legitimately settles.

## Production hardening path

Before an internet-facing pilot: authenticate every principal, add tenant-scoped
authorization, signed webhook verification, a scheduled reconciler, durable quote
and session storage, Postgres row locks plus a transactional outbox, key rotation for
receipts, merchant inventory attestations, idempotency propagation to the provider,
and a red-team corpus for model drafting and catalog prompt injection.

The Buildathon claim is deliberately smaller: **one human-approved job can tolerate a
safe checkout change, but no model output can expand the authority that reaches a
Razorpay action.**
