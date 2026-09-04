# Action Firewall — Submission Strategy Memo

**Decision date:** 1 September 2026  
**Primary build:** Action Firewall — Policy-bound Agentic Checkout on Razorpay  
**Track:** 01 — AI Growth & Agentic Commerce  
**Decision:** Continue Action Firewall. Keep Retry Budget as a documented secondary challenger; do not divert implementation time to it.  
**Authority note:** No claude/project-brief.md was present in either this workspace or the current implementation repository during this review. This memo refines the existing direction; it does not silently replace an authoritative build specification.  
**Evidence labels:** **Primary** = first-party Razorpay material or an official Razorpay repository; **Internal** = locally reproduced repository evidence; **Secondary** = non-first-party reporting; **Inference** = a product or engineering judgment derived from the evidence.

## First action: what is strong, what is missing, and the next move

### Already strong

1. **The architectural judgment is right.** The model interprets a shopping goal and proposes a cart; deterministic code decides whether an action may reach Razorpay. This directly matches Track 01's request that money actions be explainable, bounded, gated, audited, and able to fail gracefully. **Primary:** [Razorpay AI Buildathon](https://razorpay.com/buildathon/)
2. **The repository contains real engineering proof.** The backend currently passes 32 of 32 tests. It includes a barrier-based reproduction of an unsafe check-then-act race and a two-phase headroom reservation. **Internal:** verified locally on 1 September 2026.
3. **The implementation is credible under hackathon constraints.** Integer paise, server-owned catalog prices, deterministic fallbacks, append-before-act event recording, reservation semantics, and session-aware idempotency are sound foundations.
4. **The project does not require imaginary Vulcan access.** Public Vulcan material describes Razorpay's proprietary payment intelligence; no public Buildathon API, SDK, endpoint, or model access is documented. Action Firewall can be accurately described as Vulcan-aligned and complementary, with no runtime dependency. **Primary:** [Vulcan announcement](https://razorpay.com/blog/?p=27542), [Vulcan product page](https://razorpay.com/foundation-model/)
5. **The failure story is stronger than a polished happy path.** The team found a real concurrency defect, made it reproducible, and introduced a transactionally protected hold. That is exactly the kind of engineering judgment a hiring panel can inspect.

### Still missing

The repository proves a cap reservation, but it does not yet prove the stricter claim implied by the name “Action Firewall.”

The enforcement point currently accepts a reusable Boolean allow decision. That decision is not cryptographically or transactionally bound to one actor, one policy version, one cart, one amount, one tool, and one set of normalized arguments. Unknown state-changing tools also fail open if their names are missing from a short protected-tool set. Full policy state is not revalidated atomically when a reservation is created. Network ambiguity is treated as definitive failure, and payment-link issuance is described as settlement.

These are not cosmetic objections. They are direct attacks on the claimed trust boundary.

### Highest-leverage improvement

> Replace the Boolean decision at the actuator boundary with a short-lived, single-use authorization receipt bound to one exact normalized action, and attack that receipt in CI.

This is the next unit of work because it:

- makes the word “firewall” technically defensible;
- converts the concurrency fix into a complete authorization protocol;
- distinguishes the build from a grocery-specific rules engine;
- creates visually compelling attack demonstrations;
- provides a stable evaluation target even when the LLM, Pinecone, Langfuse, or the network is unavailable.

Do not add more agents, more shopping categories, or more AI until this boundary is true.

---

## A. Updated strategy memo

### What we are building

**Action Firewall is an application-layer policy enforcement and certification boundary for AI-buyer checkout workflows using Razorpay's public test-mode and MCP surfaces.**

The AI may:

- interpret a natural-language shopping goal;
- retrieve known catalog items;
- propose a normalized cart;
- explain a typed denial;
- suggest a constrained repair.

The AI may not:

- choose whether its own proposal is authorized;
- supply trusted prices, totals, identity, policy versions, or categories;
- select or change the outgoing Razorpay action;
- mint, modify, reuse, or widen an authorization receipt;
- decide whether a timeout means no external effect occurred;
- bypass an explicit user confirmation.

Only the deterministic policy service may atomically revalidate the complete policy, reserve headroom, and issue a one-time receipt. Only the actuator may redeem that receipt for an exact registered action. Only confirmed provider state may move an action from issued or unknown to settled.

This is a deliberately narrow loop:

~~~text
natural-language goal
  → grounded cart proposal
  → explicit user confirmation
  → canonical action envelope
  → atomic policy authorization and reservation
  → exact-bound one-time receipt
  → fail-closed Razorpay actuator
  → reconciliation
  → replayable audit evidence
~~~

### Why this wins

#### 1. It is a literal answer to the Track 01 brief

Razorpay's current Track 01 language asks builders to use test-mode APIs or make a merchant transactable by an AI buyer, while ensuring every money action is explainable, bounded, and gated, with an audit trail and one graceful failure. Action Firewall can demonstrate each property as executable evidence rather than as a slide. **Primary:** [Buildathon](https://razorpay.com/buildathon/)

#### 2. It reflects Razorpay's own guardrail doctrine

Razorpay's public Agent Studio principles emphasize merchant-defined data and action scope, approval boundaries for irreversible actions, instant turn-off, independent platform validation, amount and scope checks, complete action logs, consent, and continuous certification. The project should not claim that Razorpay lacks guardrails. Its defensible differentiation is a working, independently attackable reference enforcement layer for a third-party AI-buyer workflow over public tools. **Primary:** [Agent Studio principles and guardrails](https://razorpay.com/blog/razorpay-agent-studio-principles-guardrails-and-merchant-control/)

#### 3. It solves the developer-side gap without pretending to be a new payment rail

Razorpay's Agentic Payments page already describes UPI Reserve Pay as live and in-app agentic commerce as live in beta, with preset spending limits, delegated payments, and real-time visibility. Action Firewall must therefore avoid positioning itself as a substitute for rail-level consent, a banking mandate, UPI Reserve Pay, or Razorpay's internal platform validation. Its scope is earlier and narrower: protect an agent developer's application boundary before a proposed action reaches a public Razorpay surface. **Primary:** [Razorpay Agentic Payments](https://razorpay.com/agentic-payments/)

#### 4. It turns a real defect into a product proof

The naive check-then-act path allowed concurrent requests to observe the same available headroom. The reservation fix demonstrates that authorization is a concurrency problem, not only a prompt-safety problem. The next receipt/state-machine work extends that proof to stale policy, argument substitution, replay, duplicate dispatch, and ambiguous provider outcomes. **Internal:** locally reproduced test and code audit.

#### 5. It uses AI where probabilistic judgment adds value

The LLM handles ambiguity: mapping “supplies for a pasta dinner” to grounded SKUs and explaining a repair. Deterministic code handles authority. The panel answer to “why not just rules?” is:

> The rules do not understand an open-ended shopping goal, and the model must not authorize money. The product is the controlled composition of the two.

That judgment is stronger than putting an LLM inside the gate.

### Why Retry Budget stays secondary

Retry Budget is an intelligent idea with a direct revenue metric, and Track 03 explicitly values bounded recovery loops. It loses the present decision for four reasons:

1. **Proof disadvantage:** Action Firewall already has a working repository, 20 commits, 32 passing tests, and a real concurrency failure/recovery story. Retry Budget does not currently have comparable implementation evidence.
2. **Evaluation dependence:** a timing model needs a versioned generator, held-out outcomes, baselines, variance, and honest assumptions. Without real outcome labels, apparent recovery uplift can be manufactured by the simulator.
3. **Product overlap:** Razorpay already markets Subscription Recovery and Intelligent Revenue-Protect/retry behavior. A synthetic scheduler risks looking like a smaller duplicate unless its scarce-attempt compliance control plane is demonstrably new. **Primary:** [Agent Studio](https://razorpay.com/agent-studio/), [Intelligent Revenue-Protect](https://razorpay.com/blog/upi-autopay-with-intelligent-revenue-protect/)
4. **Demo risk:** retries, notification confirmation, legal windows, delayed outcomes, and reconciliation are harder to show honestly in five minutes than a deterministic action boundary and attack suite.

Retry Budget replaces Action Firewall only if it produces stronger observed evidence, not merely a stronger story: a committed end-to-end compliance refusal, a disclosed generator, a held-out uplift over fixed and random legal baselines, confidence intervals, atomic attempt reservation, unknown-outcome reconciliation, and three consecutive sub-five-minute rehearsals. That bar is not currently met.

### What changed since the previous pass

#### Current-source corrections

- **Official deadline:** the live Buildathon page and linked official application did not display a submission deadline when rechecked on 1 September 2026. Earlier references to an official 5 September close are not currently verifiable from the first-party pages. A 5 September date may remain an internal urgency assumption if sourced to secondary listings, but it must be labelled unconfirmed-current. **Primary:** [Buildathon](https://razorpay.com/buildathon/), [official application](https://docs.google.com/forms/d/e/1FAIpQLScJ9XSqVCB2oaPwEMH0Zk3I1OpILFW1WpWdWweQ2950jdRzlg/viewform)
- **Application rubric:** the current official application asks for project objectives, repository, and a five-minute video. It does not expose a separate four-dimension scoring rubric and does not ask a dedicated “what broke/how recovered” question. The failure story is still strategically important because Track 01 explicitly asks for one graceful failure; it must not be presented as a special form field.
- **MCP tool count:** the official MCP repository listed 45 tools in the 1 September snapshot. Four were marked unsupported remotely. Marketing pages use broader “35+” or “40+” language. Use the dated repository count when precision matters. **Primary:** [Official Razorpay MCP server](https://github.com/razorpay/razorpay-mcp-server#available-tools)

#### Engineering corrections

- A payment link is payment-enabling consent infrastructure, not proof that money settled.
- “Chargeback liability ₹0” is unsupported and must be removed.
- “Instant revocation” must be qualified: a policy change blocks new receipts and can cancel an undispatched local hold; it cannot unsend an external action already dispatched.
- “Append-only audit” currently means application behavior, not tamper evidence. Add an immutable policy revision record and hash-chained events, or call it an application event log.
- The current Windows headless demo is not reliable: it crashes under the default cp1252 console when printing the rupee symbol unless UTF-8 is configured. Its documented breach amount is also stale: the current run produces ₹2,034, not ₹2,233.

#### Product correction

The strongest framing is no longer “customer spending limits for agentic checkout.” Razorpay already publicly discusses limits and revocation. The differentiated claim is:

> Exact action binding, full-policy atomic reservation, fail-closed tool enforcement, ambiguous-outcome reconciliation, and adversarial certification at the agent-to-Razorpay boundary.

---

## B. Product definition

### One-line thesis

> The agent may propose a canonical cart; only a short-lived, versioned, customer-defined policy receipt may authorize one exact Razorpay action.

### Product name

**Action Firewall — Policy-bound Agentic Checkout on Razorpay**

Use “agent action authorization,” “action policy,” “authorization receipt,” and “action reservation.” Avoid “UAP mandate verification,” “NPCI mandate simulation,” and unqualified “payment authorization,” which can be confused with rail- or issuer-level payment authorization.

### Target user

Primary: a merchant or agent developer building an AI-buyer experience on Razorpay public test-mode or MCP tools.

Policy owner: the authenticated shopper or organization delegating a bounded purchase authority.

End beneficiary: the shopper, merchant, and payment platform, each of whom needs evidence that a probabilistic agent could not widen its own authority.

### User problem

An AI can translate an ambiguous goal into a useful purchase proposal, but its output is untrusted:

- it may hallucinate or substitute a SKU;
- inflate quantity or amount;
- misunderstand whether the user asked to check out;
- reuse a prior approval;
- race another request against the same cap;
- act under a stale policy version;
- invoke a new state-changing tool not covered by a handwritten guard;
- retry after a timeout even though the first external action may have succeeded.

Prompt safeguards do not solve these problems. The application needs a deterministic, fail-closed enforcement point with an exact authorization object, concurrency-safe reservation, and provider-state reconciliation.

### Core workflow

1. **Propose.** The AI receives an open-ended goal and returns only catalog operations over known SKU identifiers and bounded positive quantities. Intent to transact is advisory at most.
2. **Canonicalize.** The server resolves canonical product data, prices in integer paise, categories, quantities, currency, merchant, and normalized action arguments. Client- or model-supplied totals are ignored.
3. **Preview.** The policy service may return a non-authorizing preview decision so the UI can explain likely constraints. Preview is never redeemable.
4. **Confirm.** The user explicitly confirms one canonical cart hash and action. The server creates a unique purchase-attempt identity. The LLM cannot simulate this confirmation.
5. **Authorize and reserve.** In one database transaction, the policy service re-reads and validates authenticated ownership, policy active state, expected policy version, action type, transaction cap, category constraints, quantity constraints, time window, prior settled spend, and all live or unknown holds. It either returns a typed denial or creates a hold and exact-bound receipt.
6. **Dispatch once.** The actuator validates the receipt against authenticated context and normalized outgoing arguments, atomically claims the receipt, transitions the attempt to dispatching, and calls only an explicitly registered Razorpay action.
7. **Classify outcome.** A definitive provider success records an issued action. Confirmed capture/webhook/fetch may record settlement. A definitive provider decline may release the hold. A timeout or lost response becomes unknown and retains headroom.
8. **Reconcile.** Unknown and pending actions are resolved using the provider reference, webhook, or fetch. No second action is emitted until reconciliation proves the first had no effect.
9. **Audit.** Every proposal, confirmation, decision, policy revision, reservation, dispatch, response, state transition, reconciliation, denial, and receipt mismatch is recorded with stable identifiers and tamper-evident hashes.

### Safety boundary

#### Trusted for the MVP

- the policy service and its database transaction;
- authenticated principal and merchant context derived by the server;
- canonical catalog pricing and category data;
- the explicit protected-action registry and canonical argument schemas;
- the actuator and reconciler;
- authenticated policy edits.

#### Untrusted

- LLM output;
- retrieval and merchant catalog text;
- browser-supplied user ID, agent ID, price, total, category, currency, policy version, or decision;
- raw MCP arguments originating from the planner;
- a future Vulcan/risk/routing score;
- network failure messages;
- a provider response until persisted and, where needed, reconciled.

#### Authorization receipt

The receipt should be opaque and server-resolved for the MVP. If it crosses a process boundary, sign it. At minimum it binds:

~~~text
receipt_id
authenticated_principal_id
agent_id
session_id
merchant_id
policy_id
policy_version
policy_hash
action_type
action_schema_hash
canonical_args_hash
cart_hash
amount_paise
currency
category_and_quantity_digest
reservation_id
purchase_attempt_id
idempotency_identity
issued_at
expires_at
nonce
engine_version
decision_code
single_use_state
~~~

The actuator rejects the request unless the receipt is live, unused, owned by the authenticated principal, linked to a live reservation, and an exact match for the registered action, canonical arguments, amount, currency, policy, cart, and attempt.

#### Protected action registry

Do not use a small set named “money tools” as the only guard. Maintain a reviewed registry with explicit capability classes:

- read-only;
- local/no external effect;
- state-changing/payment-enabling;
- settlement/capture;
- unknown.

Unknown tools are denied. New tools or changed schemas require an explicit registry update, tests, and a new schema hash. This is more conservative than Razorpay MCP's static READ_ONLY and TOOLSETS configuration because it enforces dynamic, per-attempt policy at the application boundary. **Primary:** [Official MCP repository](https://github.com/razorpay/razorpay-mcp-server)

### Action state model

~~~text
PROPOSED
  ├─→ DENIED
  └─→ AUTHORIZED_HELD
        ├─→ CANCELLED_BEFORE_DISPATCH
        └─→ DISPATCHING
              ├─→ ACTION_ISSUED
              │     ├─→ SETTLED
              │     ├─→ EXPIRED_OR_CANCELLED
              │     └─→ UNKNOWN
              ├─→ DEFINITIVE_FAILURE
              └─→ UNKNOWN
                    ├─→ RECONCILED_SUCCESS
                    └─→ RECONCILED_FAILURE
~~~

Rules:

- only a definitive failure before external effect may release a hold immediately;
- unknown retains the hold and blocks re-dispatch;
- a payment-link response reaches action issued, not settled;
- a confirmed capture or provider settlement event reaches settled;
- a hold that has entered dispatching cannot be released only because its original TTL expired;
- one attempt identity may be reused for transport retries; a new identical purchase receives a new attempt identity;
- one receipt may be redeemed once.

### Failure recovery

| Failure | Required behavior | User-visible explanation |
|---|---|---|
| Model unavailable or invalid output | Use a clearly labelled deterministic planner or ask for clarification; never weaken authorization. | “Planning is using the deterministic fallback; policy enforcement is unchanged.” |
| Hallucinated or unknown SKU | Exclude it from preview, but make checkout fail with a typed grounding error if the confirmed proposal still references it. Audit the attempted identifier. | “One item could not be grounded to the merchant catalog.” |
| Policy changed before authorization | Reject expected-version mismatch and re-evaluate against the current immutable policy revision. | “The policy changed; this action must be reviewed again.” |
| Policy revoked after hold, before dispatch | Cancel undispatched hold and receipt transactionally. | “Authorization was withdrawn before the action was sent.” |
| Policy revoked after dispatch | Do not claim the action was undone. Reconcile or cancel the external resource if the relevant API supports it. | “The action was already sent and is being reconciled.” |
| Tool or argument substitution | Deny at actuator; record mismatch code; do not call MCP. | “The requested action does not match the authorized receipt.” |
| Duplicate concurrent retry | One worker claims dispatch; other workers receive in-progress or the final stored result. | “The original attempt is still in progress.” |
| Timeout after dispatch | Move to unknown, retain headroom, suppress re-dispatch, reconcile by provider reference. | “The provider outcome is not yet confirmed; no duplicate action will be sent.” |
| Provider definitive decline | Record failure, release exactly once, allow a new user-approved attempt. | “The provider declined the action; your reserved headroom was released.” |
| Trace/vector service unavailable | Continue with local event evidence and deterministic retrieval; disclose degradation. | “External observability/retrieval is degraded; the safety gate remains local.” |

### Success metrics

#### Hard safety gates

These are release gates, not aspirational averages:

- unauthorized actuator calls: **0** across the published attack corpus;
- successful receipt-tampering attacks: **0**;
- unknown or unregistered state-changing tools dispatched: **0**;
- cap/category/quantity/version invariant violations under concurrency: **0**;
- duplicate external dispatches per purchase attempt: **0**;
- new dispatches after revocation linearization: **0**;
- unknown outcomes automatically re-fired before reconciliation: **0**;
- audit/policy replay verification failures: **0**.

#### Utility metrics

- authorized benign completion rate;
- false-block rate on policy-compliant, user-confirmed actions;
- grounded-cart accuracy;
- hallucinated-SKU rate;
- safe-repair acceptance and completion rate;
- p50/p95 local authorize-and-reserve latency;
- time and count of unresolved unknown outcomes;
- deterministic demo preflight success rate.

#### Language for value metrics

- call denied before external dispatch;
- protected test exposure;
- payment link issued;
- confirmed test payment or captured value, only when provider evidence exists.

Do not call a created payment link “settled,” blocked test value “savings,” or a prototype's result “zero chargeback liability.”

### Evaluation contract

Publish a versioned dataset and exceptions:

- 40 benign shopping goals;
- 40 adversarial or ambiguous goals;
- at least 20 direct actuator/protocol attacks;
- three seeded runs for model-backed cases;
- deterministic expected policy and protocol outcomes;
- both safety and task-utility results.

The minimum publishable panel view is 100 cases × 3 runs for 300 evaluated turns, with separate protocol tests. Report pass-to-the-power-of-three for repeated safety cases, not only average success. If the full target cannot be completed, publish the actual count and exception list rather than inflating it.

---

## Decision guardrails

### Action Firewall submission kill criteria

Do not record the final pitch with the full “firewall” claim if any of these remain:

- the actuator accepts a Boolean allow instead of an exact-bound receipt;
- an unknown state-changing tool can pass by omission;
- reservation does not revalidate the complete policy and expected version atomically;
- a timeout releases the hold and allows immediate re-fire;
- payment-link issuance is still reported as settlement;
- public artifacts still claim UAP/NPCI mandate simulation, instant external revocation, zero liability, or production readiness;
- no benign plus adversarial evaluation is published;
- the offline core demo does not pass ten consecutive preflights.

Failure to meet these gates means narrow the claims and fix the build. It does not make an unimplemented Retry Budget the better submission.

### Decision-changing evidence

The Track 01 decision should change only if both are true:

1. Action Firewall cannot establish the exact enforcement boundary after the receipt, fail-closed registry, atomic revalidation, and unknown-outcome work; and
2. Retry Budget has a committed, runnable, held-out evaluation with material uplift over fixed and random legal baselines, equivalent concurrency/reconciliation proof, and a more reliable five-minute demonstration.

Neither condition is currently true.

---

## Source ledger

| Source | Class | Current use | Claim boundary |
|---|---|---|---|
| [Razorpay AI Buildathon](https://razorpay.com/buildathon/) | Primary | Track wording; gated/explainable/bounded actions; audit and graceful failure | No currently visible deadline or separate scoring weights |
| [Official Buildathon application](https://docs.google.com/forms/d/e/1FAIpQLScJ9XSqVCB2oaPwEMH0Zk3I1OpILFW1WpWdWweQ2950jdRzlg/viewform) | Primary | Current requested submission fields; five-minute video | No dedicated failure-recovery field observed on 1 September |
| [Razorpay Agentic Payments](https://razorpay.com/agentic-payments/) | Primary | UPI Reserve Pay live; in-app commerce beta; limits/delegation/visibility; 40+ public marketing wording | Does not establish private access for this team |
| [Agent Studio guardrails](https://razorpay.com/blog/razorpay-agent-studio-principles-guardrails-and-merchant-control/) | Primary | Razorpay's bounded-agent doctrine and existing validation/audit claims | Product principles, not Buildathon scoring weights |
| [Official Razorpay MCP server](https://github.com/razorpay/razorpay-mcp-server#available-tools) | Primary | Dated tool inventory; remote/local support; public tool surface | Tool inventory can change; pin the evaluated snapshot |
| [Vulcan announcement](https://razorpay.com/blog/?p=27542) and [product page](https://razorpay.com/foundation-model/) | Primary | Vulcan positioning and public capabilities | No claim of API availability or team access |
| [Agent Studio](https://razorpay.com/agent-studio/) and [Intelligent Revenue-Protect](https://razorpay.com/blog/upi-autopay-with-intelligent-revenue-protect/) | Primary | Retry/recovery product overlap | Marketing outcomes are not independent benchmarks |
| Local repository and test runs | Internal | 32 passing tests, current protocol defects, demo behavior | Evidence is point-in-time and must be rerun after changes |

## Final recommendation

Keep Track 01 and keep Action Firewall. Tighten the claim from a broad “agent spending mandate” to a verifiable application-layer enforcement and certification boundary.

The submission becomes compelling when the panel can watch four things happen:

1. AI makes a useful grounded proposal.
2. A one-time receipt authorizes one exact user-confirmed action.
3. Tampering, stale policy, concurrency, replay, and timeout attacks fail safely.
4. The team publishes both benign utility and adversarial safety evidence, including known limitations.

The closing line should be:

> We did not make the model more trusted. We made its authority smaller, exact, and testable.
