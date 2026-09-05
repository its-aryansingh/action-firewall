# Action Firewall — winning-product re-ideation

**Decision date:** 5 September 2026  
**Recommended track:** 01 — AI Growth & Agentic Commerce  
**Recommended product:** **Action Firewall — Safe Autopilot Checkout**  
**Customer promise:** **One approval for the job. Zero authority beyond it.**

## Decision

Do not abandon Action Firewall. Upgrade what the customer authorizes.

Today, the project asks the shopper to confirm one exact cart and then proves that
only that exact action can reach Razorpay. That is excellent security engineering,
but the product behaves like a safer confirm button. Razorpay's public direction is
more ambitious: remove repeated checkout interruption while keeping consent,
approved limits, visibility, and revocation.

The stronger product lets the shopper authorize a **bounded shopping job** once:

> “Buy one vegetarian pasta dinner for two from this merchant, under ₹700, using my
> saved office delivery profile, before 7 PM. Brand substitutions are allowed; meat,
> alcohol, subscriptions, address changes, and a higher total are not.”

The AI may search, assemble, re-price, and repair a cart inside those constraints.
It cannot enlarge the constraints, declare a product eligible, set the final price,
mint authority, or call Razorpay. The deterministic firewall proves that the final
merchant quote fits the shopper-approved **Purchase Envelope**, atomically reserves
headroom, and derives an exact, one-use **Action Grant** for that one Razorpay action.

If something changes, the product has three outcomes:

1. **Execute inside authority:** the final cart is a valid member of the envelope;
   derive an exact grant without another shopper interruption.
2. **Repair inside authority:** price or stock changes; AI ranks alternatives, but
   deterministic code filters and approves only a replacement that still satisfies
   the envelope.
3. **Ask for the delta:** merchant, total, item class, quantity, delivery profile,
   expiry, or payment action would change; show the exact difference and require a
   new policy version. No silent widening.

This is a direct evolution of the current repository. It preserves the difficult
parts that already work and adds a clear revenue and user-experience outcome.

## Why this is the best strategic move

### It answers Track 01 in Razorpay's language

The current [Buildathon page](https://razorpay.com/buildathon/) asks builders to
grow merchant revenue or make a merchant transactable by an AI buyer end to end. It
also requires every money action to be explainable, bounded, and gated, with an
audit trail and a graceful failure.

Safe Autopilot Checkout demonstrates all of those requirements in one loop:

- **AI-buyer transacting:** the AI can finish an authorized job, not merely suggest
  products.
- **Revenue:** compliant repair saves carts that a hard-block-only engine abandons.
- **Bounded:** the Purchase Envelope defines the complete authority set.
- **Gated:** deterministic membership validation is the only path to an Action Grant.
- **Explainable:** every allow, repair, block, and delta has field-level reasons.
- **Auditable:** policy version, quote, exact grant, dispatch owner, and provider
  outcome form one traceable receipt.
- **Graceful failure:** a price/stock drift is repaired; an authority drift is blocked
  and escalated as a precise delta.

### It matches Razorpay's direction without claiming private access

Razorpay's [Agentic Payments page](https://razorpay.com/agentic-payments/) emphasizes
pre-authorized limits, delegated payments, visibility, and granular control. Its
[ChatGPT/NPCI announcement](https://razorpay.com/blog/razorpay-unveils-agentic-payments-on-chatgpt-with-npci-indias-first-ai-powered-conversational-payment-experience/)
describes repeated human authentication as the friction preventing autonomous
commerce. Its [UPI Reserve Pay documentation](https://razorpay.com/docs/payments/recurring-payments/upi-reserve-pay/?preferred-country=IN)
describes one authorization followed by exact debits, while also stating that
activation and merchant eligibility are required.

The Buildathon implementation remains an application-layer authorization and
checkout-action gateway. It can use public Razorpay test-mode Payment Links today.
UPI Reserve Pay is an honest future adapter seam—not a dependency, entitlement, or
claim of autonomous settlement.

### It is aligned with the protocol race named by the track

Google's current [AP2 v0.2 specification](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/specification.md)
defines the same fundamental split: in direct mode, a human approves a closed
checkout; in autonomous mode, a human approves open constraints and deterministic
verifiers later check a closed checkout against them. The specification also binds
the closed checkout by hash, versions its schemas, and returns receipts.

Action Firewall should be described as **AP2-shaped** or **compatible in design
principle**, never AP2-compliant. The MVP does not issue AP2 credentials or implement
its full role and signature model. The useful product insight is the open-to-closed
authorization pattern, not a certification claim.

### It turns existing concurrency work into product proof

Recent research supports the exact gap the repository already handles. A 2026
[runtime-verification preprint](https://arxiv.org/abs/2602.06345) argues that replay,
context binding, retries, and concurrency require execution-time state beyond static
authorization. A very recent [formal-analysis preprint](https://arxiv.org/abs/2609.00060)
similarly finds that delegated authority must remain consistent across actors,
states, and protocol stages.

The repository already has a better story than a diagram:

- a naive check-then-act race was reproduced;
- ₹2,400 could be recorded against a ₹1,000 cap;
- atomic reservation bounded eight concurrent ₹300 requests at ₹900;
- eight concurrent claims on one grant produced one simulated provider call;
- timeout after dispatch becomes `UNKNOWN`, retains exposure, and suppresses blind
  retry;
- exact action arguments and policy version are checked again at dispatch.

Safe Autopilot Checkout makes those controls load-bearing. One approved envelope
may produce a later action while the user is absent, so consume-once semantics,
current-state fencing, and conservative reconciliation are not decorative—they are
the trust model.

## What changed from the previous pass

| Previous Action Firewall | Recommended Safe Autopilot Checkout |
|---|---|
| Shopper approves every exact cart | Shopper approves a structured bounded job once |
| Green policy preview still requires a second confirmation | A compliant final quote derives an exact one-use grant automatically |
| Denied cart is primarily blocked | Denied candidate triggers policy-compliant repair before abandonment |
| User re-approves the whole cart after change | User approves only a machine-readable policy delta when authority must expand |
| Primary metric is blocked/issued value | Primary metrics are safe autonomous completion, approval prompts per success, and recovery lift |
| Story leads with rules and concurrency | Story leads with frictionless bounded delegation; runtime proof explains why it is safe |
| Exact cart is the human authorization object | Purchase Envelope is the human authorization object; exact cart remains the machine grant object |

This is not a cosmetic rename. It changes the authorization contract. Therefore,
the current `claude/project-brief.md` and `CLAUDE.md` must not be edited until this
direction is explicitly accepted.

## Candidate ranking

Weighted criteria: Razorpay fit 20%, execution credibility and repository reuse 20%,
measurable impact 15%, demo strength 15%, hackathon feasibility 15%, novelty 10%,
and honest Vulcan alignment 5%. Scores are comparative judgments, not market facts.

| Rank | Candidate | Score / 10 | Decision |
|---:|---|---:|---|
| 1 | Safe Autopilot Checkout: Purchase Envelope + exact grant + repair | **9.05** | Build |
| 2 | Policy-aware checkout repair without delegated execution | **8.55** | Keep as the recovery module |
| 3 | Unknown-outcome reconciler for agent actions | **7.85** | Valuable technical module, weak standalone five-minute story |
| 4 | Agent-readable catalog contract gateway | **7.65** | Useful input layer, increasingly crowded |
| 5 | Payment-link abandonment recovery | **7.55** | Clear revenue story, but more outreach/compliance surface and less reuse |
| 6 | Retry Budget for AutoPay | **7.35** | Secondary challenger only |
| 7 | Agentic-checkout attack/conformance lab | **7.15** | Strong proof artifact, not the main product |
| 8 | Dispute authorization evidence pack | **6.90** | Promising later use of receipts, but Track 02 needs held-out precision/recall |
| 9 | Generic merchant sales assistant | **6.25** | Too easy to copy and too chatbot-like |
| 10 | Vulcan-like route or payment-method advisor | **5.75** | Do not build without proprietary payment data or an exposed model interface |

## Product definition

### One-line thesis

An AI may choose and repair a checkout only inside a shopper-approved Purchase
Envelope; deterministic code alone derives one exact, one-use Razorpay Action Grant.

### Target user

The primary customer is a Razorpay merchant or commerce platform that wants AI buyers
to complete purchases without giving the model unrestricted payment authority or
forcing the shopper to approve every unchanged detail again.

The secondary user is the shopper, who needs one understandable control surface for
scope, budget, expiry, substitutions, delivery, visibility, and revocation.

### User problem

Current choices are unsatisfactory:

- **Unrestricted agent:** low friction, unacceptable authority and retry risk.
- **Manual checkout every time:** familiar safety, but the AI cannot finish the job.
- **Hard-block rules engine:** safe when it blocks, but abandons recoverable carts.

The product creates a fourth option: autonomous completion inside exact delegated
authority, deterministic recovery inside the same authority, and delta-only approval
when the authority must change.

### Product objects

#### 1. Purchase Envelope

The human-approved, versioned definition of permitted outcomes. MVP fields:

- shopper, agent, merchant, and session identifiers;
- allowed action: `create_payment_link` only;
- currency: `INR`;
- maximum total in integer paise;
- required shopping slots, each with allowed server-owned taxonomy IDs and quantity;
- optional exact allowed SKU set;
- blocked categories and item types;
- substitution mode: exact only, within approved slot, or ask;
- maximum purchase count: one for the initial MVP;
- saved fulfilment-profile reference and latest permitted delivery time;
- expiry;
- policy version, canonical hash, and status.

The LLM may draft this object from natural language. It does not activate it. The
trusted review screen renders canonical fields and the shopper explicitly approves
that structured object.

#### 2. Merchant Quote

A server-owned snapshot of merchant, SKUs, quantities, prices, currency, inventory,
fulfilment profile, fees, total, and expiry. Retrieved text and model calculations are
not authoritative.

#### 3. Policy Delta

A deterministic field-by-field difference between the current quote and the active
envelope, for example:

- `total: ₹686 -> ₹742 (+₹56)`;
- `merchant: acme_grocery -> marketplace_seller_18`;
- `delivery_profile: office -> home`;
- `slot: vegetarian_sauce -> unknown_taxonomy`;
- `expiry: quote now lands after 19:00`.

The LLM may explain the delta. It may not choose which fields are material or mark a
delta approved.

#### 4. Action Grant

The current repository's exact one-use authority, derived only after the final quote
is proven to fit the active envelope. It remains bound to actor, agent, merchant,
session, policy version/hash, quote/cart hash, action and schema hash, canonical
arguments, amount, currency, attempt identity, and expiry.

#### 5. Action Receipt

The audit bundle for one attempt: envelope version, quote hash, decision reasons,
repair lineage, delta if any, grant ID, dispatch owner, provider reference/raw state,
and reconciliation state. The current SQLite evidence is append-only at the row level;
adding an application signature and an offline verifier is a recommended upgrade.

### Agent versus policy boundary

| Component | May do | Must never do |
|---|---|---|
| Intent model | Draft envelope fields and identify ambiguity | Activate authority, invent identity, hide a field, or infer approval |
| Shopping/recovery model | Search, rank, assemble, and explain candidates | Set trusted price/taxonomy, declare compliance, widen substitution scope, or call Razorpay |
| Browser/trusted demo surface | Render canonical envelope and collect approval | Supply trusted totals, server time, policy version, or reusable allow decisions |
| Catalog/quote service | Own SKU, taxonomy, inventory, price, total, and quote expiry | Accept model-authored commercial facts as truth |
| Policy runtime | Evaluate envelope membership, produce reasons/delta, reserve exposure, mint exact grant | Search creatively or dispatch to provider |
| Actuator | Redeem one matching grant for one registered action | Accept a Boolean allow, broaden arguments, switch tools, or reuse a grant |
| Reconciler | Resolve outcomes from authenticated provider evidence | Treat timeout as failure, trust browser settlement claims, or auto-redeliver an unknown action |

### Minimum viable trust model

Treat the following as untrusted:

- LLM output and reasoning;
- catalog prose, descriptions, and retrieved text;
- browser-submitted identity, totals, hashes, and status;
- network timeout semantics;
- provider state that is not authenticated or signature-verified.

Trust only:

- server-authenticated principal and merchant context;
- server-owned catalog identity, taxonomy, and integer-paise prices;
- server time;
- canonical serialization and hashes;
- policy/grant state inside the transactional store;
- registered action schemas;
- authenticated Razorpay fetches or verified signed webhook evidence.

The current repository has no production authentication or tenancy. The Buildathon
demo may explicitly use a local single-shopper trusted surface, but it must not claim
person-bound authorization. Production use requires authenticated principals and
per-actor authorization on every policy, session, audit, and action route.

## Core workflow

```text
shopper goal
  -> LLM drafts Purchase Envelope
  -> trusted UI shows canonical fields and ambiguities
  -> shopper approves envelope version N
  -> AI searches merchant catalog and proposes a candidate
  -> server creates fresh Merchant Quote
  -> deterministic membership check
       |-- inside envelope
       |     -> atomic reservation
       |     -> exact one-use Action Grant
       |     -> one-owner Razorpay action dispatch
       |     -> ACTION_ISSUED / DEFINITIVE_FAILURE / UNKNOWN
       |
       `-- outside envelope
             -> deterministic Policy Delta
             -> AI searches only eligible recovery space
                  |-- valid recovery -> re-check -> grant -> dispatch
                  `-- no valid recovery -> shopper approves delta as version N+1 or aborts
  -> receipt and authoritative reconciliation
```

## Failure and recovery contract

| Failure | Required behavior | Recovery |
|---|---|---|
| Intent compiler is uncertain or contradictory | Keep envelope in `DRAFT`; name missing/contradictory fields | Shopper edits or clarifies; no shopping action authority exists |
| Model returns invalid schema or unknown SKU | Reject candidate | Deterministic no-op; retry planning within bounded candidate set |
| Catalog text contains prompt injection | Treat text as data; model output still has no authority | Attack recorded; policy checks server-owned fields only |
| Price or stock changes before dispatch | Re-quote and invalidate stale candidate | Find an in-envelope replacement or return exact delta |
| Repair candidate violates one field | Reject; do not “mostly match” | Try another eligible candidate or ask for delta |
| Policy edited/revoked before dispatch claim | Cancel stale grant | Re-plan only against new version after explicit activation |
| Concurrent agents consume the same one-use envelope | One reservation/dispatch owner wins | Others receive used/in-progress/stored outcome; no second provider call |
| Provider definitively rejects | Release exposure and record reason | A new attempt may be allowed only under the envelope's attempt policy |
| Provider response is ambiguous | Mark `UNKNOWN`, retain exposure, suppress auto-retry | Authenticated provider fetch or signed webhook resolves outcome |
| Audit signature fails | Display evidence as unverified | Hold automation and investigate; never reconstruct facts from model narration |

## Why this is not “a rules engine with AI decoration”

The deterministic layer answers a safety question: **is this exact candidate inside
the authority set?** It cannot solve the utility problem: **which combination of
available products best satisfies an open-ended human goal, and how can that goal be
preserved after price or stock changes?**

AI has three measurable jobs:

1. compile an ambiguous natural-language goal into a structured draft while surfacing
   uncertainty;
2. plan a useful cart from an agent-readable catalog;
3. rank policy-eligible recovery candidates when the environment changes.

The model's value is measured by useful, policy-compliant completion and repair. The
model's mistakes are contained by a different subsystem. That separation is the
product, not an apology for using deterministic code.

## Evaluation plan

### North-star metric

**Safe Autonomous Completion Rate (SACR)**

```text
successful issued actions that satisfy ground-truth envelope
--------------------------------------------------------------
eligible shopping jobs
```

Report `ACTION_ISSUED` and confirmed test payments separately. Do not label issued
Payment Link value as settled revenue.

### Safety invariants

- false allow rate: **0** across the deterministic corpus;
- provider calls from denied candidates: **0**;
- duplicate provider actions under same attempt: **0**;
- automatic redispatch from `UNKNOWN`: **0**;
- stale-policy dispatches: **0**;
- exact grant binding mismatches accepted: **0**.

### Product metrics

- shopper approval prompts per successful action;
- compliant recovery rate after price/stock drift;
- incremental completion versus hard-block baseline;
- task utility score for the recovered cart;
- unnecessary escalation rate;
- time to valid action;
- model cost and latency per completed job;
- `UNKNOWN` exposure and mean time to authoritative resolution.

### Baselines

Run every task against four strategies:

1. **Unrestricted agent:** best apparent completion, expected policy violations.
2. **Exact confirmation every time:** safe baseline, highest shopper interruption.
3. **Hard-block firewall:** safe, but no recovery after drift.
4. **Purchase Envelope + recovery:** target system.

### Corpus

Publish a generator and at least 100 fixed cases with latent ground truth:

- 25 normal shopping jobs;
- 20 price/fee drift cases;
- 15 stock-loss and substitution cases;
- 10 merchant/address/delivery changes requiring delta approval;
- 10 policy revocation/version races;
- 10 replay/concurrency/idempotency cases;
- 10 prompt-injection, malformed output, or unknown-field attacks.

For model-dependent cases, run at least three seeds/temperatures and report both mean
and worst-case `pass^k`. Keep deterministic policy assertions separate from semantic
utility scores. Publish every exception, not only the aggregate.

## Five-minute winning demo

### 0:00–0:20 — outcome first

**Screen:** one clean product screen showing the active envelope and empty action log.

**Say:**

> “Today an AI buyer is either stopped at checkout or given too much authority.
> Action Firewall gives it one precise job—not your wallet. One approval for the
> job; zero authority beyond it.”

Do not begin with architecture, MCP, Langfuse, Pinecone, or Vulcan.

### 0:20–0:55 — approve a bounded job

**Action:** enter:

> “Buy a vegetarian pasta dinner for two from Acme Grocery under ₹700, deliver to my
> saved office profile by 7 PM. Any brand is fine; no meat and no subscription.”

The model drafts a structured envelope. The screen highlights amount, merchant,
required slots, blocked types, substitution policy, fulfilment reference, one-use
limit, and expiry. Approve it once.

**Say:**

> “The model drafted this; it did not authorize it. I approve the canonical fields,
> and version one becomes the only authority source.”

### 0:55–1:35 — complete without a second confirmation

**Action:** let the AI create a ₹486 cart and issue the registered Razorpay test-mode
Payment Link action without another cart-confirmation prompt.

**Screen evidence:** merchant quote hash, envelope version/hash, exact derived grant,
`ACTION_ISSUED`, and one provider call.

**Say:**

> “The final quote is a member of the job I approved. Deterministic code—not the
> model—derived an exact, one-use grant for these SKUs, this amount, this merchant,
> this action, and this policy version. A link was issued; that is not settlement.”

If credentials or network are unreliable, use the clearly labelled simulated
actuator for this main path and show a separately recorded real test-mode receipt.

### 1:35–2:30 — the useful failure: repair, do not abandon

**Action:** deterministically make one SKU unavailable or increase a fee so the first
candidate no longer fits. The agent suggests a premium replacement above ₹700; the
firewall denies it with zero provider calls. The recovery module selects a valid
brand substitute and issues the new ₹6xx action under the same envelope.

**Say:**

> “A hard-block engine would stop here. We preserve the shopper's goal without
> expanding authority. AI ranks the recovery; policy proves it still fits.”

### 2:30–3:10 — authority drift asks for the delta

**Action:** change the merchant or delivery profile. The system refuses to repair and
shows only the material delta.

**Say:**

> “A cheaper cart is not automatically an authorized cart. Merchant and destination
> changed, so the system cannot silently continue. It asks for exactly those fields,
> and any approval creates version two.”

Abort rather than approve, preserving the failure story.

### 3:10–4:00 — prove runtime safety

**Screen:** a purpose-built race visualization or prepared test output.

Trigger eight concurrent redemptions of one grant. Show one dispatch owner and one
provider call. Then show the timeout case: `UNKNOWN`, exposure retained, retry
suppressed.

**Say:**

> “A static signature does not stop two workers from spending the same authority.
> Our original check-then-act path overspent ₹2,400 against ₹1,000. The fixed path
> atomically reserves and gives one worker the dispatch token. If the network goes
> silent after send, not knowing is not failure: we hold exposure and reconcile.”

### 4:00–4:40 — measured product evidence

**Screen:** evaluation dashboard, not a dense terminal.

Show:

- SACR for all four baselines;
- approval prompts per successful action;
- recovery lift over hard-block;
- false allows, denied provider calls, and duplicate dispatches;
- exception count and one inspectable failure.

Do not present synthetic issued-link value as revenue. Call it simulated conversion
or action issuance. Show confirmed test payments separately.

### 4:40–5:00 — close in Razorpay's stack

**Say:**

> “Razorpay already gives builders payment actions and is building intelligent rails.
> Vulcan can decide what is likely to work. Action Firewall proves whether this agent
> is allowed to do it. The model can plan and recover; policy alone authorizes; one
> grant dispatches one action.”

Stop. Do not add a feature roadmap.

## What not to say

- Do not call `PurchaseEnvelope` an NPCI, bank, UPI, or legally binding mandate.
- Do not claim AP2 compliance; say AP2-shaped or standards-aligned architecture.
- Do not claim UPI Reserve Pay access, automatic debit, or autonomous settlement.
- Do not say “powered by Vulcan” or imply a Vulcan API.
- Do not call Payment Link issuance paid, captured, settled, or recovered revenue.
- Do not claim production identity, tenancy, regulatory compliance, immutable audit,
  or zero chargebacks.
- Do not lead with “AI safety platform.” Lead with fewer checkout interruptions and
  more safely completed shopping jobs.
- Do not say the agent has a budget. Say the shopper delegated one bounded job.

## Build plan

### Decision gate — before code

Approve or reject the new authorization invariant. If approved, update
`claude/project-brief.md`, `CLAUDE.md`, architecture, README, and demo contract in one
small documentation commit before implementation. Preserve the current exact-cart
flow on a tag or branch as the baseline; do not erase it.

### P0 — remove current credibility defects

These defects exist today and become more serious if execution becomes less
interactive:

1. Remove the heuristic planner's “add top retrieved items” fallback for ambiguous
   non-shopping prompts. Ambiguity must produce no cart mutation.
2. Frame retrieved catalog fields as untrusted data in the prompt and add injection
   fixtures. Never let product prose define price, taxonomy, tool, or policy.
3. Fix the demo reset/start state so a prior revoked policy or unresolved exposure
   cannot contaminate a live presentation.
4. Show the canonical cart/quote hash in the UI if the script refers to it.
5. Label the actuator truthfully as `SIMULATED` or `RAZORPAY TEST MODE`, never only
   “MCP-compatible.”
6. Support both `localhost` and `127.0.0.1` in the local CORS configuration or pin one
   documented host consistently.

### P1 — Purchase Envelope

1. Introduce `PurchaseEnvelopeDraft` and `PurchaseEnvelope` schemas; do not reuse the
   legacy `Mandate` name at the UI boundary.
2. Canonicalize and version the complete structured object.
3. Add `DRAFT -> ACTIVE -> REVOKED/EXPIRED/CONSUMED` lifecycle.
4. Add a trusted approval screen that renders every authoritative field and rejects
   hidden/extra fields.
5. Limit MVP to one merchant, one action, one purchase, one currency, and a fixed
   server-owned product taxonomy.

### P2 — derived exact grants

1. Implement a pure `quote_fits_envelope(envelope, quote, now)` function.
2. Bind merchant, fulfilment profile, quote expiry, required slots, and substitution
   mode in addition to existing amount/category/quantity checks.
3. Extend `authorize_and_reserve()` to consume one envelope occurrence and derive the
   current exact grant atomically.
4. Preserve dispatch-time policy version/hash checks, one-owner claim, idempotency
   binding, and `UNKNOWN` semantics.
5. Add a feature flag so the old exact-cart confirmation path remains available as a
   measured baseline, not an accidental second money path.

### P3 — policy-aware recovery and delta

1. Compute `PolicyDelta` deterministically for every failed field.
2. Generate eligible replacement sets using server-owned taxonomy, inventory, price,
   and fulfilment data.
3. Let the model rank only the eligible set; re-run the pure verifier on its choice.
4. If the eligible set is empty, require a new shopper-approved envelope version.
5. Store parent candidate, rejected reason, replacement candidate, and final decision
   as one repair lineage.

### P4 — system evaluation

1. Publish the 100-case generator and fixed evaluation manifest.
2. Implement the four baselines with identical inputs.
3. Pin deterministic safety assertions in CI.
4. Add model runs across at least three seeds and report mean, worst case, and
   `pass^k` for semantic tasks.
5. Generate the dashboard from machine-readable results; do not type headline
   numbers into the deck.
6. Publish every exception and a cost/latency summary.

### P5 — receipts and provider evidence

1. Add an application-signed Action Receipt and a standalone verify endpoint or CLI.
2. Add a signed Razorpay webhook fixture and authenticated provider-fetch adapter.
3. Keep `ACTION_ISSUED` separate from confirmed payment.
4. Record one real test-mode Payment Link creation and, if practical, one manually
   completed test payment as separate evidence.
5. Never create more than the documented test-mode limit during automated evaluation;
   keep bulk evaluation on the simulated adapter.

### P6 — presentation

1. Replace the current cap-breach-first demo with the envelope/repair/delta story.
2. Add a race visualization and receipt verifier to the audit page.
3. Regenerate the deck from measured results.
4. Record the five-minute video before adding stretch features.
5. Run the demo from a fresh clone and a disposable database three times.

## Test additions

### Envelope compiler and activation

- malformed/extra fields never activate;
- contradictory goal remains draft;
- hidden UI field cannot be approved;
- shopper edits create a new hash/version;
- expiry and revocation bind on the next action;
- browser cannot set identity, time, price, taxonomy, or status;
- non-shopping prompt produces no cart mutation.

### Membership verifier

- exact cap, cap minus one, cap plus one;
- merchant mismatch;
- currency mismatch;
- fulfilment-profile mismatch;
- late delivery;
- missing required slot;
- duplicate item used to satisfy two slots;
- allowed versus forbidden substitution;
- unknown taxonomy fails closed;
- stale quote and changed price;
- extra line item, fee, discount, tax, or subscription flag;
- zero/negative/fractional/overflow quantity;
- canonicalization equivalence and hash mismatch.

### Recovery

- model's top choice invalid but second choice valid;
- no valid candidate produces delta, not a fabricated repair;
- cheaper wrong merchant still blocked;
- semantic similarity cannot override deterministic eligibility;
- catalog injection cannot change allowed set;
- replacement preserves every required slot and quantity;
- repair lineage is complete and queryable.

### Runtime

- two different carts race on one one-use envelope;
- same cart/same attempt collapses to one dispatch;
- same attempt/different binding conflicts;
- revocation races reservation and dispatch claim;
- process crash after claim recovers to `UNKNOWN`;
- late provider success resolves the original record only;
- `UNKNOWN` cannot consume a second envelope occurrence;
- receipt tampering fails verification.

## Risk register

| Risk | Severity | Why it matters | Mitigation | Evidence that changes the decision |
|---|---|---|---|---|
| Autonomous envelope broadens risk before real authentication exists | Critical | Current identity is session possession, not a person | Keep local trusted surface; block internet deployment; add principal binding before any production claim | Working auth/tenancy tests or inability to isolate local demo |
| Product is mistaken for UPI/AP2 mandate implementation | High | Creates regulatory and technical overclaim | Use Purchase Envelope; state application-layer scope on every artifact | Public Razorpay Buildathon requirement for a specific protocol implementation |
| AI remains decorative | High | Judges may see a rules engine | Measure intent drafting, useful planning, and recovery lift separately from safety | Model contributes no statistically useful recovery over deterministic ranking |
| Broad constraints authorize unwanted but technically eligible products | High | Safe total does not equal correct intent | Fixed taxonomy, required slots, substitution modes, one-use MVP, ambiguity escalation | User tests show unacceptable semantic mismatch even with reviewed fields |
| Payment Link is not autonomous settlement | High | Weakens end-to-end claim | Say action issuance; show real test-mode link/payment separately; Reserve Pay only as seam | Public student-accessible Reserve Pay sandbox or equivalent becomes available |
| Public competitors converge on same pattern | High | Basic policy gate is already crowded | Lead with open-to-closed authority, delta-only approval, measured prompt reduction, runtime/UNKNOWN proof | A stronger public Track 01 entry ships identical loop with better evidence |
| Scope overruns the deadline | High | A half-built v2 is worse than proven baseline | Feature flag, one merchant/action/purchase, P0 first, freeze old flow | Envelope + evaluator + batch harness not working by the time-box gate |
| Synthetic conversion metrics look invented | Medium | Track 01 does not accept fake revenue | Call them simulated completions; publish generator; separate real provider evidence | Access to real anonymized merchant funnel data |
| Signed receipt becomes crypto theatre | Medium | Signatures do not replace correct lifecycle semantics | Sign only canonical facts after state transitions; keep DB and provider truth boundaries | Verification cannot detect meaningful tampering or adds demo instability |
| Retry Budget may have larger topline impact | Medium | Recovery has a clear revenue narrative | Keep it secondary; require compliance proof, control surface, batch baselines, and variance | It passes the original replacement gates with a sharper live demo |
| Vulcan overlap or access assumptions | Medium | Route/personalization is Razorpay's proprietary layer | Treat Vulcan as upstream context only | Razorpay publishes a Buildathon Vulcan API and explicit permitted use |

## Why Retry Budget stays secondary

Retry Budget has a strong Track 03 story, but it does not beat the current path under
deadline pressure:

- Track 03 explicitly requires measured money recovered across a batch, compliant
  escalation, stopping rules, and an audit trail.
- Razorpay's [Sprint 2026 page](https://razorpay.com/sprint/26) already announces a
  Subscription Recovery Agent, increasing overlap.
- The current project lacks a verified programmable retry-control surface and the
  full primary compliance evidence needed for scheduling claims.
- A public competitor, [AgentTrace](https://github.com/ps-aditya/agenttrace), already
  publishes policy-aware recovery, real order IDs, manually completed test
  payments/refunds, and batch evidence.
- Only part of the current authorization runtime transfers; the complete product,
  data generator, and evaluation must still be built.

Retry Budget should replace this decision only if it demonstrates all of the
following before the implementation time-box expires:

1. operative primary retry and notification constraints;
2. a runnable synthetic batch generator;
3. a real idempotent action surface;
4. incremental recovery against fixed schedule and oracle;
5. variance across held-out seeds;
6. a demo more reliable and differentiated than Purchase Envelope recovery.

It does not meet that standard today.

## Brutally honest winning assessment

### Current product, unchanged

The current Action Firewall is technically respectable but not a favorite to win.
It has unusually good concurrency and lifecycle proof, yet the visible product is a
chat cart plus spend-cap rules plus a confirm button. Public competitors already
show similar planner/gate/audit patterns, some with live deployments and real
test-mode order evidence. Its probability improves as an engineering interview
artifact, but the product outcome is not instantly distinctive.

### Recommended product, executed well

Safe Autopilot Checkout can be a finalist-quality submission because it connects
four things most entries show separately:

1. a buyer outcome that is obvious in one sentence;
2. a revenue mechanism—repair instead of safe abandonment;
3. a current standards-shaped authorization model;
4. real runtime proof under concurrency and ambiguous provider outcomes.

It still will not win through the idea alone. It needs three proofs visible in the
video:

- one approval genuinely avoids a second confirmation while remaining exact at the
  machine boundary;
- one broken checkout is recovered without widening authority;
- a public batch shows fewer approval prompts and higher safe completion with zero
  deterministic false allows.

If those are not implemented and measured, the reframe becomes marketing and the
original submission is safer. The winning move is a narrow, functioning v2—not a
larger architecture slide.

## Do not build

- **A generic shopping chatbot.** Razorpay already names conversational checkout;
  retrieval and chat alone have no defensible control or outcome.
- **A plain spend-cap rules engine.** Necessary, crowded, and easy to reproduce.
- **A multi-agent swarm.** It increases the authority and debugging surface without
  improving the five-minute customer loop.
- **A fake Vulcan integration.** No public Buildathon API or model interface was found.
- **A Vulcan clone.** The required payment-scale data is proprietary and inaccessible.
- **An AP2 implementation for its own sake.** Protocol conformance is a large scope and
  not itself merchant revenue. Use the relevant authorization shape.
- **A UPI Reserve Pay simulator presented as live.** A fake debit destroys trust.
- **A broad MCP proxy.** Every newly reachable state-changing tool multiplies the
  action schemas, lifecycle mappings, and adversarial proof burden.
- **A compliance-heavy Retry Budget pivot without primary rules.** It turns evidence
  gaps into product behavior.
- **A prettier deck before the batch harness.** The current competitive field rewards
  inspectable evidence, not polish unsupported by results.

## Final recommendation

Keep **Action Firewall** and Track 01. Change the product from exact-confirmation
middleware to a **delegated purchase-envelope runtime with policy-aware recovery**.

The external pitch is:

> **Action Firewall gives an AI one precise shopping job—not your wallet. The shopper
> approves the boundaries once. The AI can complete or repair the checkout only
> inside them; anything else is blocked or returned as an exact approval delta.**

The engineering close is:

> **The model proposes and repairs. Deterministic policy proves membership. One exact
> grant dispatches one Razorpay action. Ambiguity never becomes permission.**

The product relationship to Razorpay is:

> **Vulcan can decide what is likely to work. Action Firewall proves whether this
> agent is allowed to do it.**

## Evidence note

Claims, evidence classes, search boundaries, candidate scoring inputs, and the full
source-quality ledger are in
[`docs/research/2026-09-05-better-product/report-source.md`](research/2026-09-05-better-product/report-source.md).
