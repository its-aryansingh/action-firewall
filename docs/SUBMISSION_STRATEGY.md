# Action Firewall — submission strategy

**Decision date:** 3 September 2026

**Primary:** Track 01 — AI Growth & Agentic Commerce

**Challenger:** Retry Budget — Track 03
**Recommendation:** freeze Action Firewall as the submission and spend the
remaining time on proof, rehearsal, and truthful presentation.

## First action: strong, missing, next

### Already strong

1. **Direct track fit.** **[First-party]** Razorpay asks that every money action
   be explainable, bounded, and gated, with an audit trail and one graceful
   failure. Action Firewall turns each word into a visible system property.
2. **The hard boundary works.** **[Internal proof]** Chat is proposal-only.
   Exact confirmation, policy evaluation, and headroom reservation are separate,
   and the actuator accepts only an exact one-use grant.
3. **There is a real before/after failure.** **[Internal proof]** The repository
   retains the naive check-then-act race, reproduces exposure beyond a ₹1,000
   cap, and tests the atomic reservation and one-owner dispatch fixes.
4. **Provider ambiguity fails safe.** **[Internal proof]** A timeout after send
   becomes UNKNOWN, continues consuming headroom, and cannot trigger a blind
   redispatch.
5. **The payment state is honest.** **[First-party + internal proof]** Razorpay
   distinguishes link creation from payment. The product records ACTION_ISSUED,
   not paid or settled, until separate authoritative evidence exists.
6. **The integration claim is credible.** **[First-party]**
   create_payment_link is a documented Remote MCP action. Vulcan remains
   strategic context; no Vulcan runtime dependency is claimed.

### Still missing

1. **Production identity and tenancy.** Browser identity is an MVP stub. There
   is no authenticated principal, merchant boundary, or workload identity.
2. **Provider reconciliation.** The UNKNOWN transition exists, but there is no
   signed webhook consumer or fetch worker to establish the provider outcome.
3. **Cryptographic evidence.** The audit table rejects updates and deletes, but
   it is not hash-chained, signed, or stored outside the service's administrative
   trust domain.
4. **Broad model evaluation.** Safety-critical policy behavior is deterministic
   and tested, but the repository does not publish a large multi-model
   prompt-injection corpus or catalog-quality score.
5. **Live-provider proof.** The reliable demo is offline. A live test-mode Remote
   MCP run would be additive evidence, not a prerequisite for the safety claim.
6. **Submission logistics.** The official page does not expose a confirmed
   deadline, so the application form and final fields need a same-day check.

### Highest-leverage next move

**Stop feature expansion and record the five-minute proof.** The next major
failure mode is not missing architecture; it is a reviewer failing to understand
the authorization boundary within thirty seconds or seeing inconsistent claims
across the README, video, deck, and UI.

Before recording, run the full proof suite from the final commit, execute the
offline rehearsal three times, capture the concurrency result, and follow
docs/DEMO_SCRIPT.md. Add reconciliation or a larger adversarial corpus only if
the deadline safely permits it.

# A. Updated strategy memo

## What we are building

Action Firewall is an application-layer authorization broker between an AI
shopping agent and Razorpay's payment tools. The AI translates an open-ended
shopping goal into a catalog-grounded cart proposal. It cannot decide that its
own proposal is authorized.

The shopper explicitly confirms one canonical cart. Deterministic code then
re-reads the current policy, checks category and exposure constraints, reserves
headroom atomically, and mints a one-use grant for one exact
create_payment_link action. The actuator revalidates the grant and gives one
dispatcher ownership before network I/O.

## Why this wins

### It answers Razorpay's wording directly

**[First-party]** The
[Track 01 page](https://razorpay.com/buildathon/) asks for agentic commerce and
requires explainable, bounded, gated money actions, an audit trail, and a
gracefully handled failure.

Action Firewall can show:

- **explainable:** policy version, rule outcome, amount, headroom, hashes, and
  lifecycle event;
- **bounded:** per-action and rolling exposure ceilings with category controls;
- **gated:** the model cannot reach a state-changing action from chat;
- **auditable:** authorization and dispatch-start evidence commits before the
  provider call;
- **graceful failure:** a ₹2,034 proposal is denied and reduced to a valid ₹486
  proposal without weakening the policy.

### The proof is adversarial, not decorative

Most checkout demos prove only a happy path. This one covers:

- stale approval after a cart or policy change;
- concurrent overexposure against shared headroom;
- duplicate dispatch after a retry;
- unknown outcome after a provider timeout;
- action or argument substitution at the tool boundary.

Those failures map to explicit tests and states. The red path is the product
proof, not an exception hidden off-stage.

### It uses AI where uncertainty is useful

The “rules engine with AI decoration” objection is real when the model only
paraphrases a form. Here the model performs open-ended goal interpretation and
cart planning over merchant inventory. That is where probabilistic reasoning
creates utility. Price, identity, authorization, and dispatch remain
deterministic because creativity at that layer would be a defect.

The correct defense is:

> “This is an agentic shopping workflow with a deliberately non-agentic
> authorization boundary.”

### It is narrow enough to be believable

One registered action is an MVP strength. The current
[Razorpay MCP surface](https://github.com/razorpay/razorpay-mcp-server) contains
many consequential actions. A generic pass-through would weaken the safety
claim. Each additional action needs its own schema, lifecycle, policy mapping,
provider semantics, and adversarial tests.

### It remains honest about value

The demo measures denied requested value, issued payment-link value, confirmed
test-payment value, unresolved exposure, and actuator mismatch denials. It does
not invent GMV uplift, prevented chargebacks, or settled revenue.

## Why Retry Budget stays secondary

Retry Budget has a strong Track 03 narrative, but it does not beat this
submission on proof or readiness.

| Criterion | Action Firewall | Retry Budget today |
|---|---|---|
| Published track fit | Directly implements Track 01's stated bar | Track 03 names retry sequencing, but requires measured batch recovery |
| Current repository | Working end-to-end loop with deterministic failures | Material rebuild and a new batch harness required |
| Razorpay overlap | Complements the MCP action surface | Overlaps documented Smart Payment Retries |
| Public action surface | Remote-supported create_payment_link | No dedicated public retry-sequencing tool found |
| Measurement | Safety and execution invariants reproduce locally | Incremental recovery, baselines, and variance not produced |
| Compliance evidence | Does not claim rail compliance | Strongest scheduling claims remain partly unconfirmed |
| Demo reliability | Disposable no-network rehearsal | Recurring setup and reconciliation add failure surface |

Retry Budget should be reopened only when it has verified constraints, an
idempotent execution surface, and measured incremental recovery against both a
fixed schedule and an oracle.

## What changed since the previous pass

| Previous state | Current state | Why it matters |
|---|---|---|
| “UAP Mandate Verification” framing | “Action Firewall” and shopper-defined application policy | Avoids claiming a banking mandate or protocol implementation |
| Chat could appear to initiate checkout | POST /chat is structurally proposal-only | Natural-language “checkout” is not authorization |
| Boolean allow or deny decision | Exact, expiring, one-use action grant | Prevents reuse and action or argument substitution |
| Policy checked before an external call | Policy checked and headroom reserved atomically | Closes check-then-act overexposure |
| Idempotency without full binding | Attempt identity bound to actor, session, cart, action, and arguments | A reused key cannot authorize another purchase |
| Multiple callers could race at dispatch | One compare-and-set dispatch owner and token | Exactly one call can redeem a grant |
| Errors treated as simple failure | DEFINITIVE_FAILURE separated from UNKNOWN | Timeouts do not silently free exposure |
| Link creation described too strongly | ACTION_ISSUED separated from confirmed payment and settlement | Matches Razorpay's lifecycle |
| Append-only by convention | SQLite rejects audit updates and deletes | Makes local evidence enforceable |
| Stale 32 or 49 test references | 51-test baseline after final verification | Keeps proof artifacts synchronized |

# B. Product definition

## One-line thesis

**An AI agent may propose a cart; only a deterministic, versioned,
shopper-defined policy may authorize one exact Razorpay action.**

## User problem

AI shopping collapses discovery, recommendation, and checkout into one
conversation. That creates authority ambiguity: a model can misread intent,
retain a stale cart, cross a cap under concurrency, retry after a timeout, or
substitute tool arguments. A prompt instruction cannot provide a durable
authorization guarantee.

## Target user

The immediate user is a merchant product team adding an AI buyer to a
Razorpay-backed checkout. The protected principal is the shopper who defines and
revokes the application policy. The operational reviewer is the merchant or
payments engineer who needs a replayable explanation for every attempted action.

## Core workflow

~~~text
retrieve catalog
  -> model proposes known SKUs and quantities
  -> server prices and hashes the canonical cart
  -> deterministic policy preview
  -> shopper confirms the exact cart
  -> atomic current-policy check and exposure reservation
  -> exact one-use grant
  -> one-owner dispatch claim
  -> registered Razorpay action
  -> issued / definitive failure / unknown
  -> later provider confirmation or reconciliation
~~~

## Authority matrix

| Capability | AI planner | Browser | Policy service | Actuator | Reconciler |
|---|:---:|:---:|:---:|:---:|:---:|
| Interpret open-ended shopping goal | yes | no | no | no | no |
| Propose known SKUs and quantities | yes | display | validate | no | no |
| Set authoritative price or total | no | no | yes | validate | no |
| Explicitly confirm reviewed cart | no | yes | verify hash | no | no |
| Evaluate and version policy | no | no | yes | recheck | no |
| Mint exact action grant | no | no | yes | no | no |
| Choose an unregistered provider tool | no | no | no | no | no |
| Claim and dispatch one action | no | no | no | yes | no |
| Declare payment completion | no | no | no | no | verified evidence only |
| Resolve an ambiguous outcome | no | no | no | no | verified evidence only |

## Minimum viable trust model

Trusted:

- server-owned catalog identity and integer-paise prices;
- persisted current policy and immutable revision snapshot;
- canonical cart, action-schema, and argument hashing;
- transactional grant and reservation state;
- dispatch compare-and-set token;
- authoritative provider observation for final outcome.

Untrusted:

- prompts and model output;
- retrieved descriptive text;
- browser-provided prices, totals, hashes, or policy claims;
- network timeouts and missing responses;
- tool names or arguments outside the closed registry;
- observability services.

Known MVP exception: user and agent identity are not yet authenticated. The
server keeps session identity stable after creation, but that is not production
identity.

## Safety boundary

Authorization requires all of these to match at dispatch:

- user, agent, session, and merchant context;
- policy ID, current version, and policy hash;
- cart hash, amount, currency, categories, and quantities;
- action name, action-schema hash, canonical arguments, and argument hash;
- unique purchase-attempt identity;
- active, unexpired grant state.

Any mismatch fails closed before provider I/O. An unknown tool is not admitted
because it appears in MCP discovery.

## Failure recovery

| Failure | State | Exposure | Permitted recovery |
|---|---|---:|---|
| Cart changed after review | denied | none | show new cart and ask for confirmation |
| Policy edited before dispatch | cancelled or denied | released | confirm again against current policy |
| Cap or category violation | denied | none | price-fit proposal; policy is not weakened |
| Concurrent redemption | one dispatcher; others wait or reject | counted once | return stored state or result |
| Proven provider rejection | definitive failure | released | begin a new attempt |
| Timeout after send | unknown | retained | authoritative lookup or signed event |
| Process crash after claim | recovered to unknown | retained | reconcile; never blind-retry |
| Payment link issued | action issued | retained | await verified payment evidence |

## Success metrics

Primary reproducible metrics:

- unauthorized actuator calls: target 0;
- concurrent claims to provider calls: 8 → 1 for one grant;
- policy breaches reaching the actuator: target 0;
- stale-policy grants dispatched: target 0;
- ambiguous outcomes automatically redispatched: target 0;
- audit update or delete attempts accepted: target 0;
- deterministic test pass rate: 51/51 on the verified commit.

Operational metrics:

- authorization attempts and denial rate;
- denied requested value;
- payment-link value issued;
- confirmed test-payment value;
- unknown-outcome exposure;
- outstanding authorized exposure;
- time from policy update to the next authorization decision.

These are not production revenue or loss-prevention estimates.

# C. Demo script

The detailed timed script is in docs/DEMO_SCRIPT.md. The five visible beats are:

1. Show a ₹1,000 shopper-defined policy.
2. Let chat propose a ₹486 pasta cart without any payment action.
3. Grow it to ₹2,034, request checkout in language, and explicitly confirm; both
   remain blocked before the actuator.
4. Remove premium items, explicitly authorize the exact ₹486 cart, and show one
   ACTION_ISSUED payment link.
5. Revoke the policy, deny a ₹549 action, then show the event log, metrics,
   51 tests, and 8 → 1 dispatch ownership.

The failure playbook treats a provider timeout as UNKNOWN. It never repeats a
state-changing call merely to keep the demo moving.

# D. Build plan

## P0 — required before submission

1. Run backend tests, Python compilation, frontend build, dependency audit, and
   the offline rehearsal on the final commit.
2. Run the offline rehearsal three consecutive times from disposable databases.
3. Ensure every artifact agrees on 51 tests and the ₹2,034 / ₹486 / ₹549 path.
4. Search public artifacts for stale UAP, UPI Circle, x402, FTX26,
   chargeback-liability, and “link settled” claims.
5. Record a sub-five-minute video from the frozen offline path.
6. Repeat the documented quick start from a clean copy.
7. Confirm the application form, deadline, eligibility, and submission fields on
   the day of submission.

## P1 — only after P0 is frozen

1. Add a deterministic reconciliation adapter and a signed-webhook fixture for
   payment_link.paid.
2. Publish a machine-readable adversarial corpus for cart mutation, prompt
   injection, action substitution, stale policy, idempotency, concurrency, and
   unknown outcome.
3. Demonstrate one Remote MCP test-mode link in a separate recording while
   retaining the offline path as primary evidence.

Do not add a second model, multiple agents, a new payment action, a model router,
or a retry optimizer before submission.

# E. Risk register

| Risk | Severity | Current mitigation | Residual risk | Evidence that changes the decision |
|---|---|---|---|---|
| Looks like rules plus AI decoration | High | AI performs goal-to-cart planning; deterministic code owns authority | Model utility is not benchmarked | A catalog evaluation showing no useful planning value forces a narrower component pitch |
| Too narrow with one action | Medium | One fully specified action is safe and demoable | Other action semantics unproven | A rubric requiring multiple live actions justifies one independently gated addition |
| Identity is spoofable | High in production | Session identity is stable and limitation is disclosed | No authenticated principal | A supported auth flow plus enough test time |
| Provider timeout duplicates action | High | One owner; UNKNOWN holds exposure and blocks retry | Automated lookup missing | Signed webhook or fetch reconciler with idempotent tests |
| SQLite does not prove distributed safety | High in production, low in demo | Transaction and concurrency tests prove one instance | Multi-process behavior unproven | A multi-instance requirement forces PostgreSQL and outbox tests |
| Audit altered by DB administrator | Medium | SQLite rejects row update and delete | Not externally anchored or signed | Small hash-chain or signature change after P0 |
| Link issuance mistaken for revenue | High presentation risk | Separate states and metrics | Reviewers may skim | Any surface saying paid or settled after creation is a release blocker |
| Live integration fails on stage | Medium | No-network demo uses same authorization path | Simulated actuator is weaker evidence | Three stable MCP test runs become optional evidence |
| Public Razorpay facts drift | Medium | Dated source ledger and final-day check | Tool counts and labels can change | Official changes update wording, not thesis |
| Overlap with Razorpay products | Medium | Position as an application control pattern | Internal systems may already solve parts | Equivalent public boundary forces reference-implementation positioning |
| Retry Budget becomes superior | Low before freeze | Keep research, no code pivot | Track 03 names the direction | Pivot only with runnable batch, verified constraints, and measured lift |

## Judge objections

### “Isn't this just a rules engine?”

The authorization boundary is intentionally deterministic. The AI contribution
is open-ended catalog discovery and cart assembly. Replacing policy with an LLM
would make the system less credible, not more intelligent.

### “Why can chat not authorize when the user says checkout?”

Natural-language intent is ambiguous and replayable. Browser confirmation binds
the current canonical cart hash to a distinct authorization request. Chat may
display that control; it cannot invoke the action.

### “Why only create a Payment Link?”

Every state-changing action needs its own schema, lifecycle, and failure
semantics. One action proves the framework end to end. Admitting the full MCP
surface would weaken the claim.

### “What if policy changes between check and call?”

Authorization reserves against current state in one transaction. Dispatch claim
rechecks policy version and hash under the SQLite write boundary used by policy
edits. Whichever commits first defines the safe result.

### “What if Razorpay accepted but the response was lost?”

The state becomes UNKNOWN, keeps headroom reserved, and cannot be blindly
redispatched. Only authoritative provider evidence may resolve it.

### “Where is Vulcan?”

Vulcan is not a public dependency here. Razorpay positions it for routing,
fraud, and checkout intelligence. Action Firewall controls whether the agent is
authorized to invoke the action at all.

### “Where is the business impact?”

The MVP reports what it observes: denied requested exposure, issued link value,
confirmed test-payment value, outstanding exposure, and unauthorized calls. It
does not convert test-mode events into invented GMV or chargeback claims.

## Brutally honest: why this can win

This can win because the repository contains the part most teams will explain
away: the exact moment at which probabilistic intent becomes permission for a
state-changing payment action. It demonstrates a race, idempotency binding,
policy version fencing, single-owner dispatch, ambiguity accounting, and honest
provider state in a system small enough for a panel to inspect.

It will not win on visual spectacle alone. It wins only if the video gets to the
blocked call quickly, shows the separate confirmation boundary, and makes the
8 → 1 proof understandable. If the presentation leads with protocol buzzwords,
a generic chatbot, or fake recovered revenue, the engineering advantage
disappears.

## Do not build

- A generic shop-with-AI chatbot that calls MCP directly.
- A multi-agent planner, reviewer, and payer swarm.
- A fake Vulcan integration, replica model, or benchmark.
- A broad MCP proxy that permits dynamically discovered tools.
- A second payment action before its lifecycle and tests exist.
- A token-economics router unrelated to the judging bar.
- A speculative UAP policy implementation without an operative specification.
- Retry Budget without verified rules and measured incremental recovery.
- A cryptographic audit feature rushed in after demo freeze.
- Production deployment work before the evidence package is consistent.

## Final recommendation

Submit Action Firewall under Track 01. Present it as a Razorpay-native,
application-layer authorization boundary for agentic checkout. Lead with the
failure, prove the exact grant, show one action issued and one revoked attempt
blocked, distinguish issuance from settlement, and close on concurrency and
ambiguity.

**Do not pivot. The evidence strengthens the current direction.**
