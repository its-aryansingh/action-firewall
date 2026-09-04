# Action Firewall architecture

**Razorpay AI Buildathon 2026 — Track 01: AI Growth & Agentic Commerce**

> An AI agent may propose a cart. Only a deterministic, versioned,
> shopper-defined policy may authorize one exact Razorpay action.

Action Firewall is an application-layer enforcement boundary for an AI-buyer
workflow. It does not create a payment rail, replace Razorpay's own controls, or
claim that a generated payment link is a completed payment.

## Authority boundary

| Component | May do | May not do |
|---|---|---|
| AI planner | Interpret a shopping goal, retrieve products, propose catalog SKUs and quantities, explain a denial, suggest a smaller cart | Set authoritative prices or totals, approve its own proposal, mint a grant, choose an unregistered action, or dispatch to Razorpay |
| Browser | Display the canonical cart and explicitly confirm its current hash | Supply trusted prices, policy state, hashes, or a reusable payment decision |
| Policy service | Load server-owned prices and identity context, evaluate the current policy, reserve headroom, and issue an exact grant | Call Razorpay directly |
| Actuator | Redeem one matching grant for one registered action | Widen an action, use an expired or stale grant, dispatch an unknown tool, or reuse a consumed grant |
| Reconciler | Resolve an ambiguous outcome from authoritative provider evidence | Assume that a timeout means failure or automatically repeat the state-changing call |

Model output, retrieved text, browser fields, and provider connectivity are all
treated as untrusted. Integer paise, catalog identity, policy state, canonical
hashes, and action lifecycle state are owned by the server.

## Minimum viable trust model

The submitted demo is a **single-tenant, localhost prototype**. It trusts the
backend process, its configuration, the server-owned catalog, and the SQLite
database. It does not trust model output, browser-supplied prices or hashes, or
an ambiguous provider response. The simulated actuator proves state transitions;
it is not evidence of a live Razorpay outcome.

The demo does **not** establish who is calling the API. No route authenticates a
shopper or merchant, and `GET /audit` is unscoped. A caller who can reach the API
can read session identifiers, mutate policies, and confirm another session's
cart. Therefore the current service must not be exposed to an untrusted network.
A production boundary requires authenticated tenant and shopper principals,
server-minted opaque session capability, route-level authorization, and a durable
session store before the existing cart and action bindings become meaningful
security controls.

## End-to-end flow

```text
POST /chat
  retrieve_catalog
    -> plan_cart
    -> strict planner-output validation
    -> apply only known catalog SKUs at server-owned prices
    -> compute canonical cart hash
    -> policy preview
    -> return proposal; no state-changing tool is reachable

explicit shopper action
  -> POST /checkout/confirm(session_id, expected_cart_hash, attempt_id)
  -> reject an empty, changed, or stale cart
  -> canonicalize create_payment_link through the closed action registry
  -> atomically evaluate current policy and reserve exposure
  -> mint one exact action grant
  -> recheck binding plus policy version/hash at the dispatch boundary
  -> claim one dispatch token
  -> call Razorpay once
  -> record ACTION_ISSUED, UNKNOWN, or DEFINITIVE_FAILURE
```

Checkout language in chat can request that the review control be shown. It is
not authorization. `POST /chat` returns `tools=[]` even when the shopper types
"checkout", "pay", or "confirm". Only `POST /checkout/confirm` can enter the
authorization and actuator path.

## Proposal path

The proposal trace is named `agentic-cart-proposal` and contains:

| Span | Evidence |
|---|---|
| `retrieve_catalog` | Which merchant SKUs grounded the proposal |
| `plan_cart` | The model or deterministic planner's proposed operations |
| `policy_preview` | A non-authorizing preview of the current policy result |

Planner output is parsed through a strict schema. Operations accept only
`add`, `remove`, or `clear`; quantities must be integers from 1 through 100;
unexpected fields are rejected. Unknown SKUs are never priced. If the model is
unavailable or its output is invalid, the deterministic planner keeps the demo
functional without receiving any additional authority.

The preview is useful feedback, but only explicit confirmation increments the
authorization-attempt metrics.

## Confirmation and exact grant

`POST /checkout/confirm` reloads the server-side session cart and compares it
with the hash the shopper reviewed. A mismatch returns `BLOCK_CART_CHANGED`
before a grant exists.

The server then canonicalizes the payment-link action and calls
`authorize_and_reserve()` inside `BEGIN IMMEDIATE`. The transaction rechecks:

- server-derived shopper and agent context;
- current policy existence and active state;
- expected policy version and immutable policy hash;
- canonical cart hash, amount, currency, categories, and quantities;
- per-action and rolling exposure ceilings;
- existing authorized, dispatching, issued, settled, and unknown exposure;
- whether the purchase-attempt identity is already bound to another action.

The resulting grant binds all of the following:

- shopper, agent, session, and merchant context;
- policy ID, version, and hash;
- action name and action-schema hash;
- canonical argument hash;
- cart hash;
- amount in paise and currency;
- purchase-attempt identity;
- expiry and lifecycle state.

The grant is one-use authority, not a reusable Boolean approval. A delivery
retry with the same attempt identity and exact binding receives the stored
state or stored result. Reusing the identity for a different amount, cart,
actor, action, or arguments is denied as an idempotency binding conflict.

Policy revisions are stored in `policy_revisions` as immutable version/hash
snapshots. The lifecycle row and reserved exposure share one record in
`spend_ledger`, avoiding disagreement between a receipt and a separate hold.

## Fail-closed action registry

The actuator currently registers exactly one state-changing action:
`create_payment_link`.

Its schema requires a positive integer amount, `INR`, a bounded description,
`accept_partial=false`, a stable reference, and string notes. Extra fields and
coerced values are rejected. The registry has a schema hash, and the same
canonical action is checked at authorization and immediately before dispatch.

An unknown action fails closed before transport. Adding another action requires
an explicit schema, registry entry, canonicalization rules, lifecycle mapping,
and adversarial tests. A newly visible MCP tool does not become reachable by
default.

## Policy fence and single-owner dispatch

Authorization and dispatch are separate linearization points:

1. `authorize_and_reserve()` atomically reserves current headroom and stores an
   `AUTHORIZED` grant.
2. `claim_action_grant()` rechecks the exact binding and the current policy
   version/hash under a SQLite write lock.
3. One compare-and-set changes `AUTHORIZED -> DISPATCHING` and creates an
   internal dispatch token.
4. Only that token may record the first provider result.

If a policy edit commits before step 2, the old grant is cancelled and no call
is made. If the dispatch claim commits first, a later edit cannot unsend the
external request; that action must complete or be reconciled.

Concurrent confirmations of one purchase attempt therefore share one lifecycle
record, but only one worker owns dispatch. Other workers receive `IN_PROGRESS`,
`UNKNOWN`, or the stored issued result without another provider call.

The older `reserve_headroom()` and `record_spend()` helpers remain only for the
historical race-reproduction tests. The active checkout route uses the exact
grant path.

## Lifecycle and ambiguous outcomes

```text
AUTHORIZED
  |-- expiry or policy change before dispatch --> CANCELLED
  `-- one dispatch claim -----------------------> DISPATCHING
                                                   |-- accepted response --> ACTION_ISSUED
                                                   |                         `-- provider confirmation --> SETTLED
                                                   |-- proven no effect --> DEFINITIVE_FAILURE
                                                   `-- timeout, crash, or uncertain result --> UNKNOWN

UNKNOWN
  |-- authoritative acceptance --> ACTION_ISSUED or SETTLED
  |-- authoritative proof of no effect --> DEFINITIVE_FAILURE
  `-- inconclusive evidence --> UNKNOWN
```

Authorization TTL applies only before dispatch. `DISPATCHING`, `UNKNOWN`, and
`ACTION_ISSUED` continue to consume exposure. A process that disappears after
claiming dispatch is recovered to `UNKNOWN` at startup; the hold is not freed
and the effect is not repeated. A late result from the original dispatch owner
may still resolve that record.

Provider transport errors after dispatch and failures while persisting a
successful response are both ambiguous. The user is told that verification is
pending, and automatic retry is suppressed. Only an authoritative observation
may resolve `UNKNOWN` through `reconcile_unknown()`.

Payment-link creation ends at `ACTION_ISSUED`. It becomes `SETTLED` only after a
separate provider confirmation. Issued-link value is outstanding authorized
exposure, not money settled or revenue recovered.

## Persistence, audit, and metrics

SQLite runs in WAL mode. The important tables are:

- `mandates`: current application-policy records; internal legacy naming is
  retained to avoid a deadline-risking database rename;
- `policy_revisions`: immutable version/hash snapshots;
- `spend_ledger`: exact grants, reservations, provider references, and action
  lifecycle state;
- `audit_log`: append-only application events.

Authorization, dispatch, and lifecycle transitions write events carrying the
policy version and opaque grant ID. Principal events include
`CART_POLICY_PREVIEW`, `AUTHORIZATION_ATTEMPT`, `AUTHORIZATION_REJECTED`,
`ACTION_DISPATCH_STARTED`, `ACTION_REJECTED`, `ACTION_ISSUED`,
`ACTION_OUTCOME_UNKNOWN`, and `ACTION_RECONCILED`.

The proposal trace and confirmation trace are separate. The confirmation trace
is named `agentic-checkout-confirmation`; an allowed attempt contains
`authorize_and_reserve` followed by `razorpay_action`. A denied attempt has no
`razorpay_action` span.

`GET /metrics`, rendered on `/audit`, separates:

- explicit authorization attempts and denials;
- denied requested value;
- payment-link value issued;
- confirmed test-payment value;
- unknown-outcome value;
- outstanding authorized exposure;
- actuator binding mismatches denied;
- non-authorizing cart-policy previews.

SQLite triggers reject updates and deletes against `audit_log`, so append-only
behavior is enforced below the application service. It is still not a
tamper-evident hash chain, an independently signed record, or protection against
a database administrator replacing the file.

## Deterministic operation and failure handling

| Failure | Current behavior |
|---|---|
| Model unavailable or malformed output | Strict parser rejects unsafe operations; deterministic planner continues |
| Vector service unavailable | Keyword catalog retrieval continues |
| Unknown SKU | Dropped before pricing |
| Invalid quantity or extra action field | Rejected by strict validation |
| Cart changes after review | Confirmation returns `BLOCK_CART_CHANGED` |
| Policy changes after authorization | Version/hash fence cancels the undispatched grant |
| Concurrent double-click or retry storm | One dispatch token wins; others do not call the provider |
| Unknown state-changing tool | Closed registry rejects it before transport |
| Provider timeout after dispatch | State becomes `UNKNOWN`; exposure remains held; no automatic retry |
| Process stops after dispatch claim | Startup recovery changes stale `DISPATCHING` to `UNKNOWN` |
| Observability unavailable | Local state and audit continue; tracing degrades without affecting authority |

At this revision, 54 backend tests cover policy boundaries, proposal-only chat,
cart-hash confirmation, exact action binding, policy fencing, concurrent dispatch
ownership, ambiguous outcomes, stale-dispatch recovery, strict schemas, legacy
TTL regression, database-enforced audit append-only behavior, and the disposable
demo.

## Disposable offline rehearsal

From `backend`, run:

```powershell
python scripts/demo.py
```

The script forces demo mode, clears external credentials, creates a temporary
SQLite database, uses deterministic local retrieval and the simulated actuator,
and deletes the database afterward. It derives displayed amounts from the
current cart and distinguishes `ACTION_ISSUED` from settlement. It is the stage
fallback, not evidence of a live Razorpay transaction.

## Honest limitations

- No route authenticates or authorizes a shopper or merchant. The first chat
  request supplies user and agent IDs, `GET /audit` exposes session identifiers,
  and the policy routes are open. The demo is safe only as a single-tenant local
  prototype; it is not an internet-facing authorization service.
- Sessions are process-local memory. Multi-process deployment needs a durable,
  authenticated session and confirmation store.
- `reconcile_unknown()` implements the state transition, but no provider lookup,
  webhook ingestion, or signed event verification is wired into the demo.
  Unknown outcomes therefore require an externally supplied authoritative
  observation.
- Only `create_payment_link` is registered. The build does not demonstrate
  capture, refund, subscription, or arbitrary MCP action authorization.
- The primary demo proves payment-link issuance, not payment settlement.
- The audit log rejects row updates and deletes, but is not cryptographically
  tamper-evident or independently anchored.
- The deterministic planner and simulated actuator make the offline demo
  reliable, but they must be labelled as fallbacks rather than live AI or live
  Razorpay evidence.
- Vulcan is contextual alignment only. The project has no public Vulcan API,
  SDK, model weights, privileged endpoint, or runtime dependency.

These limits are deliberate disclosure boundaries, not hidden production
claims. The Buildathon proof is narrower: proposal authority is separated from
action authority, one exact action is gated and dispatched once, and ambiguous
outcomes fail safe.
