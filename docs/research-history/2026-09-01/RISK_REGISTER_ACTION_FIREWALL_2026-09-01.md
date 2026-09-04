# Action Firewall — Risk Register

**Review date:** 1 September 2026  
**Decision owner:** project team  
**Primary decision:** continue Action Firewall in Track 01  
**Severity scale:** Critical = invalidates the central claim or can cause an unauthorized/duplicate action; High = likely panel rejection, unreliable demo, or materially misleading evidence; Medium = important limitation with a contained workaround; Low = polish or post-MVP concern.

## Executive view

Action Firewall has a strong direction and real implementation proof, but it is not submission-ready under its current strongest claims. Five critical engineering risks must be closed first:

1. authorization is not bound to the exact action;
2. unknown state-changing tools fail open;
3. full policy/version state is not revalidated atomically;
4. concurrent retries and expired holds can create duplicate or excess exposure;
5. ambiguous provider outcomes are treated as definitive failure.

The top presentation risk is equally clear: the current materials conflate a shopper-defined application policy with UAP/Reserve Pay language and conflate payment-link issuance with settlement.

The mitigation is not a pivot. It is a stricter receipt-and-state-machine implementation plus an evidence and terminology sweep.

## Register

| ID | Risk | Severity | Current evidence/status | Mitigation | Closure evidence | What would change the strategy decision |
|---|---|---:|---|---|---|---|
| R1 | Boolean allow can authorize a different amount, tool, cart, or arguments | **Critical** | Locally reproduced: a small allowed decision could invoke a far larger payment-link amount. Current actuator checks allowed state, not exact action equivalence. | Replace actuator input with a persisted, short-lived, one-use exact-bound receipt; compare authenticated actor, policy version, tool, schema, normalized args, amount, currency, cart, reservation, and attempt. | Direct tamper tests all deny before adapter invocation; forged allow object is unusable. | If this cannot be implemented and proven, narrow the product to a policy preview demo; do not call it a firewall. It still does not justify a speculative Retry Budget. |
| R2 | Unclassified/new MCP side-effect tool bypasses the guard | **Critical** | Locally reproduced with an unknown tool; current short protected-name set omits current official actions such as initiate-payment. | Fail closed. Explicit action registry with reviewed schemas and capability classes. Pin the evaluated MCP snapshot. | Unknown action and schema-drift tests deny; CI detects unclassified configured actions. | If the adapter cannot be made closed-world, the central enforcement claim fails. |
| R3 | Policy can change between verification and reservation/dispatch | **Critical** | Reservation rechecks active state and headroom, but not expected policy version, category, per-action cap, or canonical action. Stale decision remains usable after revocation. | One atomic authorize-and-reserve transaction using immutable policy revision/hash; consume receipt immediately before dispatch; define revocation linearization. | Concurrent edit tests produce the documented result; stale version/category/cap/revocation cases deny. | A first-party Razorpay primitive providing equivalent exact policy enforcement could reduce product novelty, but the developer-side certification harness may remain valuable. |
| R4 | Reservation expiry can reopen the overspend invariant | **Critical** | Locally reproduced: an expired full-cap hold, a new full-cap hold, and late commits can consume twice the cap. | Expiry releases only never-dispatched holds. DISPATCHING/UNKNOWN exposure remains counted until reconciled. Terminal transitions are idempotent. | Late-success-after-TTL and concurrent replacement-hold tests never exceed held + unknown + confirmed cap. | If safe state transitions cannot be completed, disable TTL expiry and narrow the demo rather than claiming crash recovery. |
| R5 | Same purchase attempt can dispatch twice under concurrent retry | **Critical** | A replay of a live reserved idempotency key can continue to the MCP call because it has no stored result yet. | Persist outbox operation; compare-and-set one owner into DISPATCHING; other callers receive IN_PROGRESS/final result. | Barrier test proves exactly one adapter invocation for same attempt; identical new purchase receives a new attempt ID. | If only reservation idempotency is shown, stop claiming external-effect idempotency. |
| R6 | Timeout after external acceptance is treated as “nothing happened” | **Critical** | Current exception path releases the hold and tells the shopper nothing was charged. A lost response cannot prove no effect. | Add UNKNOWN quarantine, retain headroom, stable provider reference, fetch/webhook reconciliation, and no re-dispatch until definitive failure. | Fault injection after provider acceptance yields one external effect and one reconciled terminal state. | If provider reconciliation is unavailable, keep the action simulated/replayed and disclose the limitation; do not perform automatic retries. |
| R7 | Negative or malformed model quantity defeats monetary checks | **Critical** | Locally reproduced: quantity −10 generated a negative cart total and an allow decision. | Strict model-output schema, positive bounded integer quantities, closed operation enum, monetary invariants, malformed-output abstention/fallback. | Boundary/property tests cover negative, zero, huge, Boolean, float, string, malformed, repeated, and unknown operations. | No strategy change; this is a required correctness fix. |
| R8 | Payment-link issuance is presented and accounted as settlement | **Critical presentation and accounting risk** | Current flow commits reservation and increments settled-style metrics after link creation. | Separate action issued, payment pending, confirmed payment/settlement, expired/cancelled, and unknown. Commit settled spend only on trusted confirmation. | UI, API, metrics, script, README, and deck consistently distinguish link issuance; one confirmed test lifecycle if feasible. | If no confirmation path is available, frame the MVP as payment-action issuance control only. |
| R9 | Public naming implies regulated UAP/Reserve Pay/mandate behavior | **High** | README, UI, docs, and deck use UAP Mandate Verification and Reserve Pay-adjacent language. Razorpay already has real Reserve Pay/agentic-payment products. | Public rebrand to “Action Firewall — Policy-bound Agentic Checkout on Razorpay”; use action policy/receipt/reservation; qualify app-layer scope. | Repository-wide claim scan shows no misleading terms except cited background; panel script uses safe language. | A verified first-party program explicitly granting UAP/Reserve Pay integration access could permit a new claim. No such access is currently evidenced. |
| R10 | The product overlaps Razorpay's existing guardrails and looks redundant | **High** | Razorpay publicly describes limits, approval boundaries, platform validation, logs, kill switches, and agent certification. | Do not claim a missing Razorpay layer. Position as an independently testable developer-side reference enforcement/certification implementation over public workflows; differentiate on exact action binding, concurrency, unknown outcomes, and attack corpus. | One-slide overlap/difference table; direct protocol attacks that static controls do not answer; accurate first-party citations. | If Razorpay publishes the same public exact-receipt SDK and certification harness before submission, narrow to an implementation/evaluation extension or reconsider differentiation. |
| R11 | The project looks like a rules engine with AI decoration | **High** | In offline mode the planner, catalog, actuator, and tracing are all deterministic/simulated. | Show one real model-backed ambiguous planning turn; evaluate grounded planning, abstention, prompt injection, and safe repair. Keep authorization deterministic. Visibly label fallback. | Published benign/adversarial planner corpus, model/config/seeds, grounded-cart accuracy, false blocks, and at least one current trace. | If the model adds no measured task utility over deterministic planning, simplify the AI claim and focus on certification; this may lower Track 01 competitiveness but does not make an unmeasured retry model better. |
| R12 | Safety-only metrics reward blocking and hide poor utility | **High** | Breach attempt rate and blocked value can be increased by adversarial prompts; chargeback liability is hard-coded to zero. | Remove hard-coded liability. Report unauthorized calls, duplicate effects, benign completion, false blocks, safe repair, grounding, latency, and exception list. | Generated run-scoped report with actual denominators and no unsupported financial outcome claims. | If benign completion is poor after tuning, narrow supported goals and show honest abstention rather than weakening the gate. |
| R13 | Audit cannot replay historical policy or prove tamper evidence | **High** | Policy row is mutated; append-only behavior is a code convention; SQLite permits direct updates/deletes. | Immutable policy revisions with normalized snapshot/hash; hash-chained events; protected-table triggers; audit verify operation. | Historical receipt replays against exact revision; deliberate event mutation fails verification. | If not completed, call it an application event log, not immutable audit evidence. |
| R14 | Revocation claim is broader than what an app can guarantee | **High** | Re-read on a later turn blocks a new decision, but an already issued link or dispatched action may remain valid. | State the contract: edits block new receipts and cancel undispatched local holds; dispatched actions reconcile/cancel only if supported. Track outstanding artifacts. | Test for edit before reserve, after hold/before dispatch, and after dispatch; UI shows different outcomes. | Access to a first-party cancellation primitive may strengthen the recovery, but absence does not invalidate the app-layer contract. |
| R15 | Demo fails or drifts on the presentation machine | **High** | Default Windows console crashes on the rupee symbol; current docs say ₹2,233 while fixed seed produces ₹2,034; persistent DB contaminates metrics. | Configure cross-platform output in code, add fresh reset/run ID, compute displayed values dynamically, fix startup/reactivation path, run ten consecutive preflights. | Ten clean offline runs; two timed rehearsals; UI and headless fallback both tested on the presentation machine. | Repeated demo instability means record a deterministic video and narrow live interactions; do not change the product direction. |
| R16 | Frontend and clean-clone reproducibility are unproven | **High** | No frontend lockfile/node_modules at audit; production build not verified; no CI workflow found. | Lock dependencies, fresh install, type check, production build, browser smoke, backend/API smoke, CI. | CI link and captured clean-clone preflight; current generated test/build summary. | If UI cannot be stabilized, use a minimal single-screen panel or headless evidence rather than spending P0 time on design. |
| R17 | No public repository remote is configured | **High submission blocker** | git remote produced no configured remote during audit; official form asks for a GitHub URL. | Create or connect the intended public repository, verify history/secrets/license/README, push current branch, replace placeholders. | Public URL opens in a logged-out browser and reproduces the tagged submission. | If repository publication is prohibited, clarify the current form requirement immediately; otherwise submission cannot be completed as requested. |
| R18 | Real integrations are claimed without current proof | **High** | Offline path works; current audit did not verify Razorpay Remote MCP, OpenAI, Pinecone, Langfuse, or completed test payment. | Capture one honest model turn and one Razorpay test-mode action. Label live, replay, and simulated modes. Keep optional services out of the safety path. | Redacted/checksummed provider evidence and visible mode badge; no secrets. | If live provider access remains unavailable, use replay mode and narrow the action claim. |
| R19 | Browser-supplied identity can select another user's policy | **High, production** | User/agent identifiers are currently request fields; no production authentication boundary is evidenced. | For demo, bind a server-side seeded actor/session and label auth as a stub. In production design, derive actor/merchant from authenticated server context and authorize policy ownership. | Cross-user/session replay tests; API refuses client-selected policy authority; limitations doc is explicit. | No track pivot. This determines whether the product is a production architecture or a controlled MVP. |
| R20 | MCP public surface and product language drift before submission | **Medium** | Official repo count and remote restrictions can change; product pages use 35+, 40+, and exact repo inventory differently. | Pin the evaluated commit/date; say “45 in the official repository snapshot on 1 September,” not an eternal count. Recheck before recording. | Dated source ledger and final same-day verification. | A major new first-party enforcement product may affect differentiation; a tool-count change alone does not. |
| R21 | Official deadline and scoring claims are stale | **Medium** | Live official page/form did not show the previously asserted 5 September deadline or a separate four-part rubric on 1 September. | Remove first-party deadline/rubric claim. Treat secondary date as internal urgency only. Use the current official form fields as the submission checklist. | Final docs and pitch have dated, source-labelled wording. | A first-party deadline/rubric publication should replace the current uncertainty immediately. |
| R22 | No authoritative claude/project-brief.md is present | **Medium governance risk** | The requested authority file was not found in this workspace or the implementation repository during the review. | Preserve current direction; avoid silent spec replacement; record refinements as a dated memo. If the file appears, diff it before implementation. | Search result and explicit reconciliation note. | A newly supplied authoritative brief that materially conflicts with the receipt/state design requires a user decision before destructive refactoring. |
| R23 | Retry Budget consumes time without beating the proof bar | **High schedule risk** | Strong concept, but no comparable repository/evaluation evidence; overlaps current Razorpay retry/recovery products. | Freeze it as a secondary memo. No implementation unless it clears all evidence gates with committed results. | Zero P0 Action Firewall time diverted; explicit challenger scorecard. | Pivot only with held-out material recovery uplift, equivalent safety/state proof, honest test actuator, and three reliable rehearsals—and only if Action Firewall cannot establish its boundary. |
| R24 | SQLite/demo architecture is overclaimed as production scale | **Medium** | BEGIN IMMEDIATE is appropriate proof for a local invariant but serializes writes and is not a distributed lock. | State the MVP scope. Document production evolution: transactional database, outbox/queue, authenticated service identity, distributed reconciliation, signed/opaque grants. | Architecture limitations section and measured local latency; no scale claims. | A scale requirement from the official brief would require a different implementation plan, not a thesis pivot. |
| R25 | Greedy cart repair reduces price but not user intent | **Medium** | Current repair removes expensive items; it may destroy the dinner goal while fitting the cap. | Keep it user-confirmed and label it a price-fit suggestion. Add essential/optional constraints and measure safe-repair acceptance. | Evaluation contains intent-preserving repair cases and rejected suggestions. | Poor repair utility means remove automatic repair and ask the user; safety remains intact. |

## Top-five closure sequence

Close risks in this order:

1. **R1 + R2:** exact receipt and fail-closed action registry.
2. **R3:** immutable version plus atomic complete authorize-and-reserve.
3. **R4 + R5 + R6:** state machine, outbox, single-owner dispatch, unknown reconciliation.
4. **R7 + R8:** input invariants and truthful payment lifecycle.
5. **R9 + R12 + R15:** claim sweep, honest metrics, deterministic demo.

The public rebrand should begin early enough to avoid stale assets, but it must not displace the P0 enforcement work.

## Evidence that would make Retry Budget the primary

All conditions are required:

- committed runnable Track 03 repository;
- deterministic notification/compliance gate with a refusal-and-recovery demo;
- versioned synthetic generator with disclosed assumptions;
- held-out comparison against fixed-legal, random-legal, and oracle baselines;
- learned schedule with a material, stable uplift and confidence interval;
- attempts per recovery, duplicate attempt, mandates preserved, and compliance violations reported;
- atomic attempt reservation and unknown-outcome reconciliation;
- honest Razorpay test-mode or simulation boundary;
- sharp non-overlap case against Intelligent Revenue-Protect and Subscription Recovery;
- three consecutive sub-five-minute rehearsals;
- engineering proof at least as strong as Action Firewall's exact receipt and attack corpus.

The current evidence does not meet these conditions.

## Honest limitations to put in the submission

- The MVP is an application-layer reference implementation, not a payment rail or compliance certification.
- The current SQLite transaction demonstrates the invariant locally; production requires a durable transactional store, outbox, reconciler, and authenticated service identity.
- A payment link is not settlement.
- Revocation cannot unsend an already dispatched action.
- Vulcan is not a runtime dependency and no access is claimed.
- Offline mode is deterministic and simulated; it is labelled.
- Financial savings, recovery uplift, chargeback reduction, and production scale are not claimed without observed data.

These limitations increase credibility because they define exactly what the team proved.

## Residual-risk acceptance

The following may remain after submission if explicitly documented:

- SQLite instead of a distributed production datastore;
- server-side opaque receipts instead of HSM-signed cross-service tokens;
- one real state-changing action rather than broad MCP coverage;
- replay fixtures for optional external integrations;
- internal legacy “mandate” names;
- a small catalog and synthetic shoppers;
- manual rather than continuous external reconciliation.

The following may not remain under the full Action Firewall claim:

- Boolean-only actuator authority;
- default-open unknown tools;
- stale-policy authorization;
- duplicate same-attempt dispatch;
- blind release after ambiguous outcome;
- negative monetary proposals;
- link-as-settlement accounting;
- hard-coded liability;
- misleading UAP/Vulcan/product access claims.
