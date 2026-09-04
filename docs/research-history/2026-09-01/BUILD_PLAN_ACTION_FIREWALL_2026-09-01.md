# Action Firewall — Deadline-Prioritized Build Plan

**Baseline verified:** 1 September 2026  
**Implementation repository:** C:\Users\user\projects\razorpay-uap-mandate-agent  
**Current evidence:** clean master at the audit point, 20 commits, 32 of 32 backend tests passing, offline four-act flow runnable only after forcing UTF-8  
**Planning rule:** preserve the existing code and git history. Make additive, reviewable changes. Do not rename every internal “mandate” symbol before the trust boundary is correct.

## Outcome

The next build should make this statement true:

> A user-confirmed canonical proposal can produce one short-lived authorization receipt for one exact registered Razorpay action. The receipt cannot be widened, replayed, used under a stale policy, dispatched twice, or silently retried after an ambiguous provider result.

Everything else is secondary until this passes.

## Work order

### P0.1 — Separate proposal from transaction authority

**Problem:** the model output currently contains checkout intent. That gives an untrusted planner influence over whether a money-adjacent action begins.

**Change:**

- Treat model intent as advisory or remove it from the planner contract.
- Add a server-owned explicit confirmation operation tied to:
  - authenticated actor;
  - session;
  - canonical cart hash;
  - merchant;
  - amount and currency;
  - requested action.
- Create a unique purchase-attempt ID at confirmation time.
- Distinguish policy preview from action authorization.
- Do not count a discovery-time over-cap cart as an attempted money action.

**Likely files:**

- backend/app/models.py
- backend/app/agent.py
- backend/app/main.py
- frontend chat/checkout components

**Acceptance tests:**

- a planner output saying “checkout” cannot dispatch without confirmation;
- confirmation for cart hash A cannot authorize cart hash B;
- modifying the cart invalidates the visible confirmation;
- a browser-supplied actor or total is ignored in favor of server context and canonical data;
- preview decisions are not redeemable.

**Commit boundary:** one commit for the proposal/confirmation contract and tests.

### P0.2 — Introduce the exact-bound authorization receipt

**Problem:** the actuator currently trusts a Boolean allow decision that is reusable and not bound to outgoing arguments.

**Change:**

- Keep the existing deterministic policy result as an explanation object.
- Introduce a new immutable AuthorizationReceipt or ActionGrant for actuator authority.
- Persist it server-side. Return an opaque receipt ID to the workflow.
- Bind the receipt to:
  - receipt ID;
  - authenticated principal, agent, session, and merchant;
  - policy ID, immutable version, and policy hash;
  - exact registered action;
  - action schema hash;
  - canonical arguments hash;
  - canonical cart hash;
  - amount in integer paise and currency;
  - category and quantity digest;
  - reservation ID;
  - purchase-attempt ID and idempotency identity;
  - issuance, expiry, nonce, engine version;
  - one-use state and typed decision code.
- Canonicalize arguments once using a stable serialized representation. Hash that representation.
- Do not accept a receipt or allow object constructed by the browser or model.

**Compatibility choice:**

- Keep MandateDecision as a policy-evaluation/preview type for now.
- Remove it from every actuator method signature.
- Avoid a deadline-risking mass rename of database tables until public terminology and enforcement are stable.

**Acceptance tests:**

- ₹100 receipt rejects ₹101;
- create-payment-link receipt rejects capture-payment;
- currency, merchant, note, destination, SKU, or quantity modification rejects;
- expired receipt rejects;
- consumed receipt rejects;
- cross-user, cross-session, and cross-agent replay reject;
- a forged allowed Boolean cannot reach the actuator;
- canonical equivalent arguments produce the same hash; semantically different arguments do not.

**Commit boundary:** receipt schema/storage and direct unit tests.

### P0.3 — Replace tool-name guarding with a fail-closed capability registry

**Problem:** only names in a short protected set are gated; omitted or newly added side-effect tools pass.

**Change:**

- Create an explicit registry of every supported adapter action.
- Classify actions as:
  - READ_ONLY;
  - LOCAL_ONLY;
  - STATE_CHANGING;
  - CAPTURE_OR_SETTLEMENT;
  - UNKNOWN.
- Default to denial.
- Require every state-changing action to name:
  - canonical input schema;
  - schema/version hash;
  - authorization requirements;
  - reconciliation method;
  - idempotency behavior;
  - success, definitive-failure, and unknown classifications.
- Pin and record the official MCP snapshot evaluated for the project.
- Add a CI check that fails if a configured action is missing a classification.

**Immediate registered scope:**

- create-payment-link as the real/test-mode demo action;
- a prepared capture-payment contract fixture only if it can be tested honestly;
- read-only catalog/provider queries as explicit read operations.

Do not add all 45 tools. The point is a closed, reviewable boundary.

**Acceptance tests:**

- unknown future state-changing tool rejects;
- initiate-payment and every other deliberately unsupported mutator reject;
- read-only fixture cannot be used to smuggle state-changing arguments;
- changed schema hash rejects until the registry is updated;
- no adapter can be called outside the registry.

**Commit boundary:** registry, actuator enforcement, and unknown-tool regression tests.

### P0.4 — Replace partial reservation with atomic full-policy authorization

**Problem:** reservation currently rechecks active state and window headroom, but not expected policy version, category, per-transaction cap, action, or complete canonical proposal.

**Change:**

- Introduce one authorize-and-reserve transaction.
- Inputs are authenticated context, expected policy version, canonical action envelope, and purchase-attempt identity.
- Inside one BEGIN IMMEDIATE transaction:
  1. read the current policy and immutable revision;
  2. verify ownership and active state;
  3. reject version/hash mismatch;
  4. verify action scope;
  5. verify amount, category, quantity, per-action cap, rolling window, settled spend, live holds, and unknown exposure;
  6. reuse an existing attempt only if it is the same transport retry;
  7. create the reservation and receipt together;
  8. append the decision event.
- Return a typed denial or the opaque receipt and reservation IDs.
- Remove the standalone verify-then-reserve path from checkout.

**Policy versioning:**

- Add an immutable policy_revisions table containing the complete normalized policy JSON and policy hash.
- Keep a small policy pointer/current-state row if useful.
- Every edit creates a new revision; historical revisions are never updated.
- Store the exact revision on every receipt and event.

**Window semantics:**

- Name a 24-hour duration as a rolling 24-hour window.
- If calendar-day behavior is required, model timezone and anchored boundaries explicitly.
- Inject a clock into tests.

**Acceptance tests:**

- cap, per-action cap, category, quantity, active state, or action scope changes between preview and reserve reject;
- expected version N cannot reserve against N+1;
- concurrent policy edit and checkout have a documented linearization result;
- settled + live-held + unknown exposure never exceeds the window cap;
- two sessions sharing one policy cannot over-reserve;
- a new identical purchase gets a new attempt identity.

**Commit boundary:** additive migration and transaction, followed by agent integration.

### P0.5 — Enforce single-owner dispatch and ambiguous-outcome quarantine

**Problem:** concurrent requests using the same live idempotency key can both call the actuator. A network exception releases the hold even if the provider may have accepted the action. An expired hold can later commit after newer headroom was granted.

**Change:**

- Add an operation/outbox row created with the receipt.
- Use compare-and-set to move one receipt from AUTHORIZED_HELD to DISPATCHING.
- Only the worker that wins DISPATCHING may call the adapter.
- Other callers receive IN_PROGRESS or the stored terminal result.
- Replace the current reservation lifecycle with:
  - RESERVED or AUTHORIZED_HELD;
  - DISPATCHING;
  - ACTION_ISSUED;
  - SETTLED;
  - DEFINITIVE_FAILURE;
  - UNKNOWN;
  - CANCELLED_BEFORE_DISPATCH.
- Treat timeout, connection reset, process crash after send, and malformed provider response as UNKNOWN unless the adapter can prove no request left the process.
- UNKNOWN retains headroom and suppresses re-dispatch.
- Reconcile using a stable provider or local operation reference.
- TTL may expire an undispatched hold. It must not release DISPATCHING or UNKNOWN exposure.
- Late provider success commits once; late definitive failure releases once.

**Acceptance tests:**

- two simultaneous calls with one attempt invoke the simulated adapter once;
- an in-flight replay receives a stable operation ID;
- timeout after provider acceptance does not issue a second link;
- process crash between send and local persistence enters/reconstructs unknown;
- late success after nominal TTL cannot create overspend;
- duplicate and out-of-order webhook/reconciliation events are idempotent;
- one terminal transition occurs.

**Commit boundary:** state/outbox migration, dispatcher, reconciler, and deterministic fault-injection tests.

### P0.6 — Validate every planner operation before cart mutation

**Problem:** a negative quantity can create a negative total and pass the current policy.

**Change:**

- Parse planner output through a strict schema with extra fields forbidden.
- Closed operation enum.
- Integer quantity only; reject Boolean, float, string, zero, negative, and over-maximum values.
- Set a product and total bound appropriate to the demo.
- Define repeated-operation behavior deterministically.
- Unknown SKU during exploration may be excluded with a warning; an ungrounded SKU on confirmed checkout is a typed deny and audit event.
- Validate non-negative monetary values at every internal boundary, not only in the UI.

**Acceptance tests:**

- quantity −1, 0, huge integer, float, Boolean, numeric string, missing value;
- malformed JSON and unknown operation;
- duplicate SKU operations and remove-more-than-present;
- integer bounds and overflow;
- unknown/confusable SKU;
- negative or zero action amount;
- model outage/malformed result enters fallback or abstention without a 500.

**Commit boundary:** strict planner schema and mutation invariants.

### P0.7 — Correct payment, revocation, metrics, and audit semantics

**Payment state:**

- create-payment-link success becomes ACTION_ISSUED or LINK_CREATED.
- It does not enter the spend ledger as settled without trusted provider confirmation.
- Decide whether issued links reserve headroom until paid, cancelled, or expired; encode that lifecycle.
- A provider webhook/fetch confirms settlement.

**Revocation contract:**

- a policy edit prevents new receipts immediately at its transaction boundary;
- it cancels authorized-but-undispatched receipts/holds if that is the chosen contract;
- dispatched actions reconcile and are never described as retroactively undone;
- external cancellation is attempted only if the selected action/API supports it.

**Metrics:**

- remove hard-coded chargeback liability;
- split preview checks from confirmed authorization attempts;
- rename value_settled to only confirmed test settlement;
- add:
  - unauthorized actuator calls;
  - receipt mismatch denials by code;
  - unknown/unregistered action denials;
  - duplicate dispatch count;
  - confirmed attempts and false blocks;
  - safe-repair completion;
  - link-issued versus payment-confirmed value;
  - protected test exposure;
  - authorize/reserve latency;
  - unknown outcome count and age;
  - revocation-to-new-dispatch invariant.
- Scope metrics by demo run, user, or evaluation version.

**Audit:**

- Add immutable event IDs, prior-event hash, event hash, run ID, actor, receipt, attempt, policy revision, and state transition.
- Add update/delete-denying triggers for protected tables if compatible with the demo.
- Add an audit-verify operation.
- Do not call the log immutable until verification exists.

**Acceptance tests:**

- link issuance does not increment settled value;
- confirmed provider event increments once;
- failed/expired link releases according to policy;
- timeout never produces “nothing was charged”;
- revocation cannot create a new dispatch after its linearization point;
- metrics contain only observed fields;
- event hash chain detects mutation;
- application store cannot update/delete protected events.

**Commit boundary:** truthful states/metrics, then audit integrity.

---

## P1 — Proof and presentation

### P1.1 — Build the adversarial and benign evaluation harness

**Corpus:**

- 40 benign natural-language goals;
- 40 adversarial, ambiguous, or prompt-injected goals;
- 20 or more direct protocol/actuator attacks;
- three seeded model runs where model access is available;
- one deterministic fallback run.

**Planner cases:**

- ambiguous intent;
- quantities and constraints;
- hallucinated SKU;
- prompt injection in user text;
- prompt injection in catalog text;
- price/category manipulation;
- category euphemism;
- multi-turn quantity inflation;
- cart changed after confirmation;
- malformed model output;
- abstention when grounding is impossible.

**Protocol cases:**

- receipt tool, amount, currency, cart, actor, merchant, policy, args, expiry, and replay attacks;
- unknown state-changing tool;
- stale version;
- concurrent policy edit;
- same-attempt concurrency;
- identical new attempt;
- timeout/unknown;
- late success after TTL;
- duplicate/out-of-order webhook;
- audit tampering.

**Report:**

- version and checksum of the corpus;
- model/config/seed or fallback mode;
- actual evaluated case count;
- all-run safety rate or pass-to-the-power-of-k;
- grounded-cart accuracy;
- benign completion and false blocks;
- safe-repair completion;
- unauthorized calls and duplicate effects;
- authorization latency;
- exception list.

**CI gate:**

- deterministic protocol safety must pass 100%;
- model utility thresholds may warn or gate only after a stable baseline is measured;
- never report only the best seed or model.

### P1.2 — Make the demo deterministic and cross-platform

**Fixes:**

- configure stdout safely in the script or avoid encoding-dependent output;
- stop depending on a remembered PYTHONUTF8 environment variable;
- use a fresh temporary or explicitly reset demo database;
- compute displayed totals from seeded catalog state;
- fix startup seeding after a revoked policy;
- allow the UI to create/reactivate the intended current policy safely;
- add one reset/preflight command;
- scope audit and metrics to a displayed run ID;
- run ten consecutive offline rehearsals;
- time two consecutive spoken rehearsals under five minutes.

**Required modes:**

- LIVE_TEST_MODE: real LLM planner plus Razorpay test-mode action when credentials work;
- REPLAY_MODE: live local policy/actuator path plus checksummed captured provider response;
- OFFLINE_MODE: deterministic planner, retrieval, adapter, and tracing fallback.

Every screen must show the active mode. Never silently downgrade.

### P1.3 — Produce reproducible build evidence

**Backend:**

- pin Python dependencies;
- test from a clean environment;
- run unit, concurrency, state-machine, API, and demo smoke tests;
- add CI.

**Frontend:**

- add the dependency lockfile;
- run type check and production build;
- run the app from a fresh install;
- add a browser smoke covering proposal, confirmation, denial, receipt, and audit.

**Repository:**

- configure a public remote before submission;
- verify no secrets or .env files are tracked;
- replace the GitHub placeholder;
- verify commit identity;
- retain small logical commits;
- include a one-command preflight;
- include generated current test/evaluation evidence without secrets.

**Current blockers discovered:**

- no package-lock or installed frontend dependencies were present during the audit;
- no CI workflow was found;
- no git remote was configured;
- current real Razorpay, OpenAI, Pinecone, and Langfuse integrations were not verified in this review.

### P1.4 — Rebrand public artifacts without destabilizing internals

**Public title:**

> Action Firewall — Policy-bound Agentic Checkout on Razorpay

**Claim sweep across README, UI, deck, architecture, and demo:**

- remove UAP Mandate Verification;
- remove NPCI UAP simulation and Reserve Pay mandate language;
- remove zero chargeback liability;
- replace settlement claims for payment-link creation;
- qualify revocation;
- remove production-ready, underwritable, and x402 claims;
- remove stale ₹2,233 amount;
- replace “22 pure-gate tests” with generated current counts;
- update architecture so reservation is current, not future;
- update actual tracing span count;
- replace all placeholders.

Internal table/module names may remain for this submission if a broad rename would create migration risk. Document them as legacy implementation names.

### P1.5 — Capture honest integration proof

Obtain before final recording:

- one real model-backed planning trace;
- one real Razorpay test-mode create-payment-link interaction;
- if feasible, one confirmed test-mode payment lifecycle;
- redacted request/response or provider reference;
- one captured Langfuse trace, if available.

If an integration cannot be verified, use the clearly labelled replay/offline mode and state the limitation. Do not delay the deterministic safety proof to chase optional services.

---

## Suggested logical commit sequence

1. test: add failing action-substitution and unknown-tool cases
2. feat: add exact-bound authorization receipt
3. feat: default-deny action registry
4. test: add stale-policy and negative-quantity cases
5. feat: atomic full-policy authorize-and-reserve
6. feat: strict planner operation validation
7. test: add duplicate-dispatch, timeout, TTL, and late-success cases
8. feat: add outbox, single-owner dispatch, unknown, and reconciliation
9. fix: separate action issued from settlement and replace metrics
10. feat: immutable policy revisions and tamper-evident events
11. fix: explicit checkout confirmation and run-scoped demo
12. fix: Windows-safe demo and deterministic reset
13. test: add adversarial/benign evaluation harness and CI gate
14. chore: lock frontend dependencies and add build/smoke CI
15. docs: Action Firewall terminology and claim sweep
16. docs: current evidence, limitations, five-minute demo, and public repository link

Before every commit, rebase from the configured branch once a remote exists. Never stage credentials or local environment files.

## Required test additions

### Protocol and authorization

- [ ] amount substitution
- [ ] tool substitution
- [ ] currency substitution
- [ ] canonical-argument substitution
- [ ] cart/SKU/quantity substitution
- [ ] cross-actor/merchant/session replay
- [ ] expired and consumed receipt
- [ ] forged decision
- [ ] unknown action default denial
- [ ] action schema drift

### Policy and concurrency

- [ ] stale policy version
- [ ] category/per-action/window change before reserve
- [ ] revoke before reserve
- [ ] revoke after hold/before dispatch
- [ ] concurrent edit and dispatch
- [ ] distinct sessions sharing a policy
- [ ] same attempt dispatch exactly once
- [ ] identical new purchase remains possible
- [ ] late success after TTL
- [ ] held + unknown + confirmed invariant

### External outcome

- [ ] definitive pre-send failure releases once
- [ ] timeout after send enters unknown
- [ ] unknown suppresses re-dispatch
- [ ] reconciliation success commits once
- [ ] reconciliation failure releases once
- [ ] duplicate webhook
- [ ] out-of-order webhook
- [ ] crash between send and persistence

### Input and AI

- [ ] negative/zero/huge/non-integer quantity
- [ ] malformed JSON and unknown operation
- [ ] unknown and confusable SKU
- [ ] prompt injection in user and catalog text
- [ ] hallucinated item and stale price
- [ ] model outage and deterministic fallback
- [ ] explicit confirmation cannot be forged by model
- [ ] benign completion/false-block corpus

### Semantics and evidence

- [ ] link issuance is not settlement
- [ ] confirmed payment counts once
- [ ] metrics are run/user scoped
- [ ] no hard-coded liability
- [ ] policy revision replay
- [ ] audit mutation detection
- [ ] Windows console demo
- [ ] clean reset and ten-run preflight
- [ ] fresh frontend install/type/build/smoke

## Missing artifacts

- exact action-envelope schema;
- receipt schema and verification contract;
- action capability registry;
- state-transition table and invariant document;
- immutable policy revision schema;
- reconciliation contract and fault-injection fixtures;
- published adversarial/benign corpus;
- generated evaluation report with exceptions;
- run-scoped metrics/evidence screen;
- captured/redacted real test-mode interaction;
- current architecture diagram;
- updated README and deck;
- dependency lockfile;
- CI workflow;
- public repository remote;
- final five-minute recording;
- submission checklist with current official form fields.

## Defer until after submission

- broad internal rename from mandate to policy;
- multiple merchants and complex organization RBAC;
- distributed database or queue migration;
- full webhook infrastructure for every Razorpay product;
- all 45 MCP tools;
- signed cross-service receipts with HSM-backed keys;
- production compliance attestation;
- Vulcan integration;
- Retry Budget implementation;
- multi-agent orchestration.

These are legitimate production topics, but they do not improve the immediate proof as much as the exact receipt and state machine.

## Final acceptance gate

The build is submission-ready only when:

1. the model cannot create transaction authority;
2. an exact receipt is required for every supported state-changing action;
3. unknown actions fail closed;
4. complete policy and expected version are revalidated atomically;
5. one purchase attempt dispatches at most once;
6. ambiguous outcomes quarantine and reconcile;
7. link issuance and settlement are distinct;
8. unsafe input cannot create negative or inflated totals;
9. public terminology matches the real product boundary;
10. deterministic safety and benign utility results are published;
11. fresh backend and frontend checks pass;
12. the offline five-minute path succeeds ten consecutive times;
13. real, replayed, and simulated evidence are visibly labelled.

If time runs short, cut visual polish and optional integrations. Do not cut the actuator boundary, unknown-outcome handling, truthfulness of claims, or the attack suite.
