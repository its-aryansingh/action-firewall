# Action Firewall — Product Definition

**Public name:** Action Firewall — Policy-bound Agentic Checkout on Razorpay  
**Track:** 01 — AI Growth & Agentic Commerce  
**MVP scope:** one merchant, one shopper policy, one catalog, one user-confirmed checkout action, one Razorpay test-mode or clearly labelled replay adapter, deterministic safety, and published evaluation  
**Not in scope:** a payment rail, NPCI mandate, UPI Reserve Pay replacement, production compliance certification, Vulcan runtime integration, or broad orchestration platform

## One-line thesis

> The agent may propose a canonical cart; only a short-lived, versioned, shopper-defined policy receipt may authorize one exact Razorpay action.

## User problem

Agentic checkout combines two fundamentally different jobs:

- understand an ambiguous human goal;
- exercise authority over a payment-adjacent action.

The first benefits from a probabilistic model. The second cannot safely trust the same model. A planner can hallucinate an item, inflate quantity, misread “prepare checkout” as consent, reuse a prior approval, race against shared headroom, act under stale policy, call an unclassified tool, or retry after an ambiguous provider timeout.

Action Firewall lets an agent remain useful without letting it widen its own authority.

## Target user

**Primary:** a merchant or agent developer implementing an AI-buyer flow with Razorpay public test-mode or MCP tools.

**Policy owner:** the authenticated shopper or organization delegating bounded authority.

**Panel-level value:** a testable implementation of the principle that AI proposes while deterministic policy authorizes.

## Product promise

For every supported state-changing action, the system can answer:

1. Who explicitly confirmed it?
2. Which policy revision governed it?
3. What exact action, arguments, cart, amount, and currency were authorized?
4. Which headroom was reserved?
5. Was the receipt consumed once?
6. What was sent to the provider?
7. Was the outcome issued, confirmed, declined, or unknown?
8. How was an unknown outcome reconciled?
9. Can the complete decision and state history be verified?

If any required fact is missing or mismatched, the actuator refuses the action.

## Authority matrix

| Capability | AI planner | Browser/UI | Policy service | Actuator | Reconciler |
|---|:---:|:---:|:---:|:---:|:---:|
| Interpret natural-language goal | Yes | No | No | No | No |
| Retrieve/propose known SKUs | Yes, untrusted proposal | Display only | Validates grounding | No | No |
| Supply trusted price/category/total | No | No | Canonical server data | Verifies receipt | No |
| Confirm a specific cart/action | No | Yes, authenticated explicit action | Records confirmation | No | No |
| Evaluate policy | No | No | Yes | Verifies result binding | No |
| Reserve shared headroom | No | No | Yes, atomically | No | No |
| Mint authorization receipt | No | No | Yes | No | No |
| Select outgoing Razorpay action | No | No | Receipt fixes it | Executes registered exact action | No |
| Redeem receipt | No | No | No | Yes, once | No |
| Decide a timeout means no effect | No | No | No | No | No |
| Reconcile provider state | No | No | No | Supplies reference | Yes |
| Relax policy after a denial | No | Policy owner may edit | Creates new revision | No | No |
| Suggest a lower-cost repair | Yes, advisory | Accept/reject | Re-evaluates from zero | No | No |

## Core workflow

### 1. Propose

The planner receives the shopper goal and returns a strict set of catalog operations. It can reference only known SKU IDs and positive bounded integer quantities. Its output carries no transaction authority.

### 2. Canonicalize

The server resolves:

- merchant and authenticated actor;
- SKU, category, unit price, and quantity;
- amount in integer paise;
- currency;
- intended supported action;
- normalized provider arguments;
- cart and argument hashes.

Client and model totals are ignored.

### 3. Preview

The UI may show a non-authorizing policy preview. It is explanatory only and cannot be sent to the actuator.

### 4. Confirm

The authenticated shopper confirms one displayed cart hash and exact action. The server creates a unique purchase-attempt ID. Editing the cart invalidates confirmation.

### 5. Authorize and reserve

In one transaction, the policy service:

- re-reads the current immutable policy revision;
- verifies expected version, ownership, and active state;
- verifies action scope;
- verifies per-action cap, rolling cap, category, quantity, and any time constraints;
- counts settled, live-held, and unknown exposure;
- checks attempt identity/idempotency;
- creates a hold, outbox operation, audit event, and exact-bound receipt.

A failure returns a typed denial. No receipt exists on denial.

### 6. Dispatch once

The actuator:

- rejects unknown actions by default;
- loads the receipt server-side;
- compares actor, merchant, policy, action, schema, normalized arguments, cart, amount, currency, reservation, expiry, and state;
- atomically moves one operation to dispatching;
- consumes the receipt;
- invokes the registered adapter exactly once.

Concurrent callers for the same attempt receive in-progress or the stored result.

### 7. Classify

Provider success for create-payment-link means action issued, not settled. A trusted capture/payment state may confirm money movement. A definitive pre-effect failure may release headroom. A timeout or lost response becomes unknown.

### 8. Reconcile

Unknown retains headroom and suppresses re-dispatch. The reconciler uses a stable provider/local reference, fetch, or webhook to reach exactly one terminal result.

### 9. Audit

The system records immutable policy revisions and hash-chained events for proposal, confirmation, decision, hold, receipt, dispatch, provider response, unknown state, reconciliation, settlement/expiry, denial, and tamper attempt.

## Authorization receipt

Required bindings:

- receipt ID;
- authenticated principal, agent, session, merchant;
- policy ID, version, and content hash;
- action type and schema hash;
- normalized argument hash;
- cart hash;
- amount paise and currency;
- category/quantity digest;
- reservation and purchase-attempt IDs;
- idempotency identity;
- issue and expiry time;
- nonce and engine version;
- one-use state;
- decision code.

MVP implementation should use an opaque server-resolved receipt. A future cross-service form may be signed, but signature does not replace server-side single-use and reservation state.

## Policy model

Minimum policy controls:

- active/revoked state;
- rolling-window cap;
- per-action cap;
- category allow/block rules;
- per-SKU or total quantity bounds if retained;
- supported action scope;
- immutable revision/version;
- policy owner and merchant binding.

Every edit creates a new revision and invalidates any chosen class of undispatched authorization according to the documented revocation contract.

## Revocation contract

> A policy edit blocks new receipts at the edit transaction's linearization point. It cancels authorized-but-undispatched local receipts and holds. It cannot unsend an action already dispatched to Razorpay; dispatched actions are reconciled and cancelled externally only when the selected API supports cancellation.

Do not call this retroactive or universal instant revocation.

## Failure recovery

### Denied by policy

Return a typed rule code and human-readable explanation. The planner may propose a grounded repair. The user must accept it. The repair creates a new cart hash and must be authorized again.

### Stale policy

Reject the receipt/authorization attempt. Display the current revision and require re-confirmation if the canonical action is still desired.

### Tool or argument tampering

Deny at the actuator. Record the mismatch. Do not call Razorpay.

### Duplicate retry

Return the existing operation. Only the dispatch owner may call the provider.

### Ambiguous provider outcome

Move to unknown, retain headroom, expose pending reconciliation, and suppress re-dispatch. Never tell the user “nothing happened” solely because the response was lost.

### Model/retrieval/trace outage

Use a visibly labelled deterministic planner/retriever/local event trail or abstain. The authorization boundary is unchanged.

## Success metrics

### Safety release gates

- unauthorized actuator calls: zero;
- successful receipt tampering: zero;
- unknown action dispatches: zero;
- policy invariant violations under concurrency: zero;
- duplicate dispatches per purchase attempt: zero;
- dispatches after documented revocation boundary: zero;
- unknown outcomes automatically re-fired: zero;
- audit verification failures: zero.

### Utility

- benign confirmed-action completion;
- false-block rate;
- grounded-cart accuracy;
- hallucinated-SKU rate;
- safe-repair acceptance/completion;
- local authorize/reserve p50 and p95 latency;
- unresolved unknown count and age;
- offline demo preflight pass rate.

### Honest value language

Use:

- protected test exposure;
- calls denied before provider dispatch;
- payment link issued;
- confirmed test payment;
- settled value only with provider confirmation.

Do not use:

- prevented chargebacks;
- recovered revenue;
- savings;
- settled value from link issuance;
- zero liability.

## Evaluation

Publish:

- 40 benign goals;
- 40 adversarial/ambiguous goals;
- at least 20 protocol attacks;
- three seeded model runs when available;
- deterministic fallback results;
- actual denominator, model/configuration, exceptions, and corpus checksum.

Required protocol attacks include amount/tool/currency/cart/actor/merchant/policy/argument substitution, expiry, replay, stale version, unknown tool, concurrent retry, late success after expiry, timeout, duplicate webhook, and audit mutation.

The safety bar is zero successful unauthorized dispatches. Utility must be reported separately so an always-deny system cannot win.

## Razorpay fit

**Primary evidence:** Track 01 asks for test-mode/API or AI-buyer work where money actions are explainable, bounded, gated, audited, and fail gracefully. [Buildathon](https://razorpay.com/buildathon/)

**Primary evidence:** Agent Studio guardrail principles already emphasize scope, approval boundaries, independent validation, logs, consent, kill switches, and certification. Action Firewall implements and attacks those ideas at a developer-side public-tool boundary; it does not claim Razorpay lacks them. [Agent Studio guardrails](https://razorpay.com/blog/razorpay-agent-studio-principles-guardrails-and-merchant-control/)

**Primary evidence:** Agentic Payments already includes Reserve Pay and delegated-limit language. Action Firewall therefore does not claim to invent rail-level consent. [Agentic Payments](https://razorpay.com/agentic-payments/)

**Primary evidence:** the public MCP server is the concrete adapter surface; its inventory can change, which is exactly why an application action registry must fail closed. [Official Razorpay MCP repository](https://github.com/razorpay/razorpay-mcp-server)

**Vulcan statement:** Vulcan may make routing, fraud, or checkout decisions more intelligent, but public materials do not provide this team a runtime integration. Any future score is advisory and cannot bypass policy. [Vulcan](https://razorpay.com/foundation-model/)

## Non-goals

- autonomous policy editing;
- agent-generated user consent;
- multi-agent orchestration;
- all Razorpay tool coverage;
- replacing Razorpay platform validation;
- replacing Reserve Pay, UPI Circle, AutoPay, or a banking mandate;
- provider-independent settlement ledger;
- compliance certification;
- production identity, scale, or HSM claims;
- financial impact claims without observed outcomes;
- Retry Budget.

## Five-minute proof

The panel must see:

1. an unknown action denied before any provider call;
2. an AI-generated, grounded proposal with no authority;
3. explicit user confirmation and one exact receipt;
4. an honest test-mode or labelled replay action issuance;
5. tool/amount substitution and receipt replay denied;
6. a recoverable over-cap cart;
7. the historical concurrency failure and protected invariant;
8. stale-policy denial and unknown-outcome reconciliation;
9. safety plus benign-utility metrics and the exception list.

## Definition of done

The MVP is done when the public claim, executable boundary, tests, metrics, and spoken demo all describe the same system. If any one of them still treats a Boolean as authority, an unknown action as allowed, a timeout as no effect, or a link as settlement, the product definition is not yet implemented.
