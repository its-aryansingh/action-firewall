# Action Firewall — Five-Minute Demo Script

**Purpose:** hiring-panel demonstration, not a generic product tour  
**Target duration:** 4:45 to 4:55; never exceed 5:00  
**Required build state:** record only after the exact-bound receipt, fail-closed action registry, atomic full-policy reservation, and unknown-outcome state are implemented and tested  
**Default story data:** fixed catalog and policy seed; ₹1,000 rolling headroom; legitimate pasta proposal ₹486; expanded proposal ₹2,034  
**Action language:** payment link issued, action dispatched, payment confirmed, or action denied. Do not say settled unless a trusted test-mode payment state confirms settlement.

## The 30-second value

> “An AI can assemble a useful cart, but it cannot authorize itself. Action Firewall converts one user-confirmed proposal into a one-time receipt for one exact Razorpay action. Change the amount, the tool, the cart, or the policy version and the actuator refuses to call Razorpay.”

The first 30 seconds must show an enforcement result, not a market slide.

## Demo layout

Keep the evidence inside one application. Use six tabs or panels in this order:

1. **Shop** — chat, grounded cart, confirmation.
2. **Policy** — active policy version and limits.
3. **Receipt** — exact action envelope and rule results.
4. **Actuator** — dispatch state, provider/test reference, mismatch denial.
5. **Race Lab** — historical naive run versus protected invariant.
6. **Evidence** — attack-corpus and benign-utility results plus audit verification.

Do not depend on opening Pinecone, Langfuse, a terminal, and Razorpay dashboards during the core story. External dashboards are backup evidence after the five minutes or in the repository.

## Pre-demo state

The reset action must create:

- one authenticated demo shopper;
- one demo merchant;
- one active policy at version 1;
- rolling window cap ₹1,000;
- per-action cap at least ₹1,000;
- grocery category allowed;
- fixed pasta catalog;
- no settled or live-held spend;
- empty action, receipt, and audit tables;
- a unique demo run ID displayed in the UI;
- deterministic planner enabled as failover, with the primary recorded run using a real LLM planner if credentials are present.

Run the reset once. Refresh every screen. Confirm that the run-scoped metrics are zero.

---

## Exact five-minute sequence

### 0:00–0:25 — Open with the boundary

**Screen:** Shop plus a compact four-box boundary at the top:

~~~text
AI proposal → user confirmation → policy receipt → Razorpay actuator
~~~

**Action:** Click a prepared “unsafe direct call” fixture. It attempts to invoke an unregistered state-changing tool with no receipt.

**Expected result:** red actuator event:

~~~text
DENY_UNKNOWN_ACTION
Razorpay calls: 0
~~~

**Say:**

> “This is Action Firewall. The model may propose an action; it cannot authorize itself. Every state-changing Razorpay call must redeem a one-time receipt for one exact action. Unknown actions fail closed.”

**Do not say:**

- “We created a new payment rail.”
- “Razorpay currently has no guardrails.”
- “This is NPCI UAP or a Reserve Pay mandate.”

### 0:25–1:10 — Show why AI is useful

**Screen:** Shop.

**Action:** Enter exactly:

> I need supplies for a simple pasta dinner for two. Keep it economical.

**Expected result:**

- the AI planner returns only known SKUs and quantities;
- the server recomputes the canonical cart and ₹486 total;
- the UI labels this as **Proposal**, not authorized;
- no receipt exists;
- Razorpay calls remain zero.

**Show briefly:**

- “planner: model” or “planner: deterministic fallback”;
- server-owned SKU IDs, quantities, unit prices, categories;
- canonical cart hash;
- explicit **Confirm ₹486 action** button.

**Say:**

> “The model does the probabilistic work: it interprets an ambiguous goal and proposes grounded products. Prices, categories, totals, identity, and policy state are server-owned. This proposal has no authority yet.”

If the deterministic fallback is active, say:

> “The model endpoint is degraded, so planning is using the labelled deterministic fallback. The authorization boundary is unchanged.”

Do not imply an LLM is running if it is not.

### 1:10–1:50 — Authorize one exact action

**Action:** Click **Confirm ₹486 action**.

**Expected sequence on the Receipt and Actuator panels:**

1. policy version 1 is re-read;
2. full policy passes;
3. ₹486 headroom is reserved;
4. one receipt is issued;
5. actuator atomically claims it;
6. Razorpay test-mode create-payment-link is called once;
7. state becomes **ACTION_ISSUED**;
8. provider/test reference is visible.

**Show receipt fields:**

- authenticated actor and merchant;
- policy ID/version/hash;
- action type;
- amount and currency;
- cart hash;
- canonical arguments hash;
- reservation and attempt IDs;
- issued/expiry time;
- single-use state.

**Say:**

> “The click creates a new purchase attempt. In one transaction the server revalidates the complete versioned policy, reserves headroom, and mints this short-lived receipt. The actuator verifies an exact match and consumes it once. Razorpay has issued a test-mode payment link; this is not yet a settled payment.”

If no live test-mode credential is available, show a clearly labelled replay fixture and say:

> “This provider response is a deterministic replay of a captured test-mode interaction. The actuator and policy path are live; the provider is simulated for demo reliability.”

Never imply a fixture is a live Razorpay result.

### 1:50–2:30 — Attack the authorization, not just the cap

**Screen:** Receipt attack controls.

**Action:** Select the just-consumed or a prepared unconsumed ₹486 receipt. Click **Tamper action**. The fixture changes:

- tool from create-payment-link to capture-payment; and
- amount from ₹486 to ₹2,034.

**Expected result:**

~~~text
DENY_ACTION_MISMATCH
DENY_AMOUNT_OR_ARGS_HASH_MISMATCH
Razorpay calls added: 0
~~~

Then click **Replay receipt**.

**Expected result:**

~~~text
DENY_RECEIPT_ALREADY_USED
Razorpay calls added: 0
~~~

**Say:**

> “A Boolean allow would be reusable. This receipt is not. It is bound to the tool, normalized arguments, amount, currency, cart, actor, policy version, and reservation. Argument substitution and replay fail at the last trusted boundary.”

This is the central proof. If time is tight, keep this and drop secondary UI explanation.

### 2:30–3:05 — Show a graceful business denial and recovery

**Screen:** Shop.

**Action:** Enter exactly:

> Add the Parmigiano Reggiano and olive oil, then prepare checkout.

**Expected result:**

- proposal becomes ₹2,034;
- user confirmation or authorization attempt returns **DENY_WINDOW_CAP_EXCEEDED**;
- no receipt is issued;
- no actuator call is made;
- UI offers a deterministic catalog-grounded repair, clearly labelled **Suggestion**.

**Action:** Accept the repair that returns the cart to ₹486, then confirm it as a new attempt.

**Expected result:** new policy evaluation, new receipt, and one valid action issued.

**Say:**

> “The denial is typed and recoverable. The model may explain or suggest a smaller known-SKU cart, but it cannot relax the policy. The user accepts the repair, and the whole action is re-authorized from zero.”

Do not say the system “saved ₹1,548,” “prevented a chargeback,” or “recovered revenue.” It denied protected test exposure.

### 3:05–3:45 — Show the concurrency failure and fix

**Screen:** Race Lab.

**Action:** Click **Run historical check-then-act** using the deterministic barrier fixture.

**Expected result:** a stable unsafe result showing multiple workers observed the same headroom and the invariant was exceeded. Display the exact fixture result generated by the test; do not memorize a number that can drift.

**Action:** Click **Run protected authorize-and-reserve** with the same workload.

**Expected result:**

- only requests fitting the remaining headroom receive holds;
- the rest receive typed denials;
- held + unknown + confirmed exposure never exceeds the cap;
- same-attempt concurrent retry dispatches once.

**Say:**

> “Our first implementation checked and acted in separate steps. Under concurrency, every worker could see the same headroom. We reproduced that failure, then moved full-policy validation and reservation into one transaction. We also separated a repeated transport retry from a new purchase attempt, so the same attempt can dispatch only once.”

**Do not say:**

- “This is the largest payment vulnerability.”
- “SQLite proves internet-scale throughput.”
- “The reservation alone solves every distributed-systems problem.”

### 3:45–4:20 — Stale policy and unknown outcome

**Screen:** Policy plus Actuator timeline.

**Stale-policy action:**

1. prepare a receipt under policy version 1 without dispatching;
2. change the cap or revoke the policy, producing version 2;
3. attempt dispatch.

**Expected result:**

~~~text
DENY_STALE_POLICY_VERSION
receipt cancelled before dispatch
Razorpay calls added: 0
~~~

**Unknown-outcome action:** run a prepared timeout-after-send fixture.

**Expected result:**

~~~text
DISPATCHING → UNKNOWN
headroom retained
automatic re-dispatch: suppressed
~~~

Then click **Reconcile captured provider result**.

**Expected result:** exactly one transition to reconciled success or failure.

**Say:**

> “A policy edit blocks every new or undispatched authorization, but it cannot unsend an external action. A lost response is also not proof that nothing happened. We quarantine unknown outcomes, retain headroom, and reconcile before any retry.”

This is the required graceful failure. It is more credible than always returning “nothing was charged.”

### 4:20–4:50 — Show the evidence, including utility

**Screen:** Evidence.

**Show only measured, current values:**

- backend tests passed;
- protocol attack cases and successful attacks;
- benign confirmed cases and completion rate;
- false-block rate;
- grounded-cart and hallucinated-SKU metrics;
- duplicate external effects;
- p50/p95 local authorization latency;
- unresolved unknown outcomes;
- audit chain verification;
- current exception list.

**Say:**

> “The safety result is not a cherry-picked prompt. We publish the attack cases, benign cases, repeated model runs, deterministic assertions, and exceptions. The release gate is zero unauthorized actuator calls and zero duplicate effects, while still measuring whether valid shopper goals complete.”

Do not show “chargeback liability ₹0” or describe blocked test-mode value as realized savings.

### 4:50–5:00 — Close

**Screen:** boundary diagram plus one successful receipt and one denied tamper.

**Say:**

> “We did not make the model more trusted. We made its authority smaller, exact, and testable.”

Stop. Do not add a Vulcan detour.

---

## Exact phrases to use

- “application-layer enforcement for an AI-buyer workflow”
- “agent action authorization”
- “shopper-defined action policy”
- “one-time exact-bound authorization receipt”
- “full-policy atomic revalidation and reservation”
- “unknown-outcome quarantine and reconciliation”
- “payment link issued”
- “confirmed test payment,” only with provider confirmation
- “protected test exposure”
- “Vulcan-aligned and complementary; no runtime dependency”
- “reference implementation of Razorpay's published guardrail principles”

## Phrases to remove

- “NPCI UAP mandate verification”
- “we simulate UPI Reserve Pay”
- “new payment rail”
- “zero chargeback liability”
- “money settled” after link creation
- “nothing was charged” after a timeout
- “instant revocation,” without the before-dispatch boundary
- “unhackable,” “production-ready,” or “bank-grade”
- “no second path to money,” until every side-effecting adapter is fail-closed
- “Vulcan-powered” or “integrated with Vulcan”
- “Razorpay does not have this”
- “the application asks what broke first”
- “official 5 September deadline,” unless first-party evidence reappears

---

## Live-failure runbook

| Failure during demo | Immediate action | Exact disclosure |
|---|---|---|
| LLM unavailable | Keep the same prompt; allow labelled deterministic planner fallback; continue to receipt attack. | “Planning is using the deterministic fallback; authorization remains the same.” |
| Pinecone unavailable | Use local deterministic catalog; show retrieval mode badge. | “Catalog retrieval is local for this run; all items remain server-grounded.” |
| Razorpay MCP unavailable before dispatch | Switch to the captured response replay and keep the actuator path live. | “The provider is using a captured test-mode fixture; this is not a live call.” |
| MCP timeout after dispatch | Do not restart. Show the unknown state and reconciliation path. | “The result is ambiguous, so the system will not send a duplicate.” |
| Langfuse unavailable | Show the local run-scoped timeline, receipt, and audit hash verification. | “External tracing is unavailable; local decision evidence is complete.” |
| Frontend fails | Run the UTF-8-safe headless demo and the attack/evaluation report. | “The UI is unavailable; the same server-side protocol is running headlessly.” |
| Seeded amount differs | Read the displayed canonical amount; do not repeat ₹2,034 from memory. | “The server recomputed this amount from the current fixed catalog.” |
| Real test payment remains pending | Leave it at action issued/pending. | “The link was issued; settlement has not been confirmed.” |

## Preflight gate

Do not record or present until all checks pass:

1. fresh reset produces the same run-scoped initial state;
2. Windows default terminal completes the headless script without an encoding environment variable;
3. UI build and type check pass from the locked dependency file;
4. backend tests and protocol attack suite pass;
5. explicit confirmation is required before receipt creation;
6. unknown tool, tool swap, amount swap, args swap, stale version, expiry, replay, and cross-user receipt attacks are denied;
7. same-attempt concurrent calls dispatch exactly once;
8. timeout fixture enters unknown and does not release/re-fire;
9. payment-link issuance is not shown as settlement;
10. metrics are scoped to the current demo run;
11. no UAP, zero-liability, production-ready, or placeholder GitHub text remains;
12. the complete offline path succeeds ten consecutive times;
13. the final spoken run is between 4:45 and 4:55 twice consecutively.

## Backup evidence to prepare

- one 20-second screen recording of a real Razorpay test-mode interaction;
- one captured, redacted provider request/response pair and checksum;
- one screenshot of the model-backed trace with secrets absent;
- one generated attack-corpus report;
- one generated benign-utility report;
- one deterministic concurrency result;
- one audit verification result;
- one current limitations slide.

These are backup evidence. The core five-minute story remains the single-screen action boundary.
