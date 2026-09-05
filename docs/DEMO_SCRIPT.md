# Action Firewall — five-minute demo

> **Baseline script.** This exact-cart flow remains implemented at `/baseline`
> for comparison and regression proof. The primary submission demo is now
> [Safe Autopilot Checkout](SAFE_AUTOPILOT_DEMO.md).

This is the judge-facing path for Track 01. It demonstrates one narrow claim:
chat may propose a cart, but only a current, exact, one-use authorization grant
may reach the registered Razorpay action.

## Before recording or presenting

Open these views before the clock starts:

1. `/mandate` — active application policy, ₹1,000 weekly ceiling, `gift_cards`
   blocked.
2. `/` — empty AI Buyer session and cart.
3. `/audit` — application event log and outcome-aware metrics.
4. A terminal with `python scripts/demo.py` ready from `backend/`.

Use `DEMO_MODE=true` for the reliable stage path. It uses a simulated actuator,
a deterministic catalog fallback, and no network credentials. If a live
test-mode Razorpay call is shown, label it separately and never treat link
creation as payment completion.

Immediately before presenting, run:

```powershell
cd backend
python scripts/demo.py
python -m pytest -q
```

Expected rehearsal totals are derived from the current catalog: ₹2,034 denied,
₹486 payment-link value issued, and a later ₹549 authorization denied after
revocation. The exact grant and policy IDs change every run.

## The five-minute story

### 0:00–0:25 — establish the boundary

**Screen:** `/mandate`.

Point to the ₹1,000 weekly ceiling, active state, policy version, and blocked
category.

**Say:**

> “Razorpay asks Track 01 builders to make every money action explainable,
> bounded, and gated. Here the model can shop, but it cannot authorize itself.
> This shopper-defined application policy is the only source of action
> authority.”

### 0:25–1:05 — prove chat is proposal-only

**Screen:** `/`.

Submit exactly:

```text
I need supplies for a pasta dinner
```

The catalog-backed cart becomes ₹486. Point to `AI Buyer — proposal only`, the
cart hash, and the policy preview.

**Say:**

> “The model interprets an open-ended goal and proposes catalog SKUs. Prices,
> totals, and the canonical cart hash are computed by the server. This green
> result is feedback, not authority. Chat has no state-changing tool path.”

### 1:05–2:00 — the failure proves the gate

Submit exactly:

```text
Add the Parmigiano Reggiano and the olive oil, then check out
```

The proposal becomes ₹2,034 and shows `BLOCK_WINDOW_CAP_EXCEEDED`. Emphasize
that the words “check out” still caused no action. Then click **Authorize payment
link** so the separate confirmation request is also denied.

**Say:**

> “Natural-language checkout is not confirmation. The explicit request re-reads
> the current policy and evaluates the exact ₹2,034 action inside the same write
> transaction that would reserve headroom. It is denied before the actuator:
> zero external calls.”

Point to the deterministic price-fit suggestion of ₹486.

### 2:00–2:55 — recover and issue one action

Submit exactly:

```text
Remove the Parmigiano Reggiano and the olive oil
```

Then submit:

```text
Checkout please
```

The cart is ₹486. Point out that the chat request still did not dispatch. Click
**Authorize payment link** once.

**Say:**

> “The recovery preserves the shopper’s goal while fitting the current
> headroom. Explicit confirmation now creates an exact grant bound to this user,
> agent, session, cart hash, amount, action arguments, policy version, and one
> purchase-attempt ID. One compare-and-set owner dispatches once.”

When the UI shows `ACTION ISSUED`, say:

> “A payment link was issued. That is not a paid transaction and not
> settlement; payment completion needs later verified Razorpay state.”

### 2:55–3:45 — revoke authority and show next-action latency

**Screen:** `/mandate`.

Click **Revoke policy**. Point to version 2 and the `REVOKED` state. Return to
`/`, submit:

```text
Buy me some coffee beans
```

Then click **Authorize payment link**.

**Say:**

> “Revocation binds at the next authorization. The server distinguishes a
> revoked policy from a missing one, re-reads the current version, and denies
> the ₹549 action. An action already issued externally is not magically unsent;
> it must be observed or reconciled.”

### 3:45–4:30 — show evidence, not narration

**Screen:** `/audit`.

Point to:

- 3 explicit authorization attempts;
- 2 denied authorizations;
- ₹2,583 denied requested value;
- ₹486 payment-link value issued;
- ₹0 confirmed test payments;
- ₹0 unknown-outcome exposure in this run;
- 0 actuator binding mismatches in the normal rehearsal.

Find the relevant event rows: `AUTHORIZATION_ATTEMPT`,
`ACTION_DISPATCH_STARTED`, `ACTION_ISSUED`, and the revoked denial. Point to the
policy version and opaque grant ID. If Langfuse is configured, show it only as a
secondary trace; the database evidence remains authoritative.

**Say:**

> “Authorization, dispatch start, and provider outcome are separate facts. The
> application event rows cannot be updated or deleted by SQLite, and the grant
> record carries the exact hashes used at dispatch. This is append-only
> application evidence, not a cryptographically signed ledger.”

### 4:30–5:00 — engineering proof and close

**Screen:** pre-opened terminal output or the proof slide.

Show the full test result and name the concurrency test that drives eight
simultaneous claims to exactly one simulated actuator call.

**Say:**

> “The original check-then-act design overspent ₹2,400 against a ₹1,000 cap
> under eight concurrent workers. The fixed path atomically authorizes and
> reserves, fences the current policy version, and grants one dispatch owner.
> If the provider times out after send, the state becomes UNKNOWN, keeps
> headroom reserved, and never auto-retries. Chat proposes. Policy authorizes.
> One grant dispatches one action.”

Stop there. Do not add a roadmap monologue.

## What not to say

- Do not say “powered by Vulcan” or imply access to a Vulcan API, SDK, model, or
  private Razorpay pilot.
- Do not call the application policy an NPCI, bank, or UPI mandate. Internal
  `Mandate*` names and `/mandates` routes are compatibility debt.
- Do not say the payment link is paid, captured, settled, or recovered revenue.
- Do not say the audit log is cryptographically immutable or independently
  signed.
- Do not claim authentication or tenant isolation. Say plainly that the demo
  routes are unauthenticated and localhost-only; identity binding is required
  before any internet-facing deployment.
- Do not claim zero chargebacks, regulatory compliance, or a production SLA.
- Do not imply that all Razorpay MCP tools are exposed. The application registry
  allows only `create_payment_link`.
- Do not cite an unsourced “single-agent Razorpay doctrine.” Defend one agent on
  the smaller handoff and authority surface.

## Live-failure playbook

### Browser or backend failure

Run `python scripts/demo.py`. State once that it is the disposable offline
rehearsal using the same policy, grant, reservation, dispatch, and audit code
with a simulated actuator. Do not call it a live Razorpay transaction.

### Pinecone or model failure

Continue. The deterministic catalog retriever and planner are deliberate
fallbacks. Say that degraded intelligence must not widen payment authority.

### Langfuse failure

Use `/audit`. Tracing is optional observability; it is not the authorization
source of truth.

### Razorpay timeout after dispatch

Do not click authorize again with a new attempt ID. Preserve the same attempt
identity and show `UNKNOWN` or the corresponding audit/test evidence. Say:

> “We cannot prove whether the provider accepted the request, so we preserve
> exposure and suppress automatic redispatch until authoritative reconciliation.”

### An unexpected UI total

Stop using memorized numbers and read the canonical amount shown by the app.
The server-owned cart is authoritative. If the scripted catalog was changed,
fall back to the headless rehearsal and update the deck before recording.
