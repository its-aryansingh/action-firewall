# Deep-research source report — Action Firewall product re-ideation

**Research cut-off:** 5 September 2026, Asia/Calcutta  
**Decision scope:** improve the existing Razorpay Buildathon submission without
discarding its working authorization runtime  
**Authoritative implementation brief:** `claude/project-brief.md` remains unchanged
pending an explicit product decision

## Executive finding

The current project has a credible authorization runtime but an incomplete product
story. Its exact-cart confirmation flow proves safety, yet reproduces the repeated
human interruption that Razorpay says agentic payments are intended to remove. The
strongest evolution is not a new project and not Retry Budget. It is:

> **Action Firewall — Safe Autopilot Checkout**  
> One approval for the job. Zero authority beyond it.

The shopper approves a structured, revocable **Purchase Envelope** before execution.
The AI may discover, plan, and repair a cart inside that envelope. Deterministic code
alone evaluates the final merchant quote, atomically reserves headroom, and derives
an exact, one-use **Action Grant** bound to the final Razorpay action. A mismatch
produces a structured **Policy Delta**; the system either finds a policy-compliant
recovery or asks the shopper to approve only the delta.

This product retains the repository's strongest proof—version fencing, exact action
binding, atomic reservation, one-owner dispatch, conservative `UNKNOWN` handling,
and append-only application evidence—while adding the missing outcome: fewer buyer
interruptions and more policy-compliant completed checkouts.

## Research question and boundaries

### Question

What product can a student team ship from the current repository that has a stronger
chance of winning Track 01 than the existing exact-confirmation demo or the Retry
Budget challenger?

### Constraints

- India and Razorpay's public 2026 product surface.
- Public APIs and test mode only; no implied private beta, internal data, Vulcan API,
  UPI Reserve Pay entitlement, or NPCI integration.
- Five-minute judge demo and a public, reproducible repository.
- Existing 61-test authorization runtime must be reused.
- A pivot must beat the incumbent on strategic fit, proof, measurable impact,
  novelty, demo clarity, and delivery risk.

## Evidence-gap plan

| Question | Evidence sought | Result |
|---|---|---|
| What does Track 01 reward? | Current first-party Buildathon page | End-to-end AI-buyer transacting; revenue; every money action explainable, bounded, gated; audit and graceful failure. |
| What friction is Razorpay trying to remove? | Current Agentic Payments pages and launch posts | Repeated PIN/OTP/manual checkout interruption; Razorpay emphasizes one consent event, approved limits, visibility, and revocation. |
| Is pre-authorized constrained delegation a real protocol shape? | Current AP2 specification and official launch | Yes. AP2 v0.2 distinguishes direct approval from autonomous open constraints and requires deterministic verification of a closed checkout. |
| Does runtime enforcement remain necessary after signed intent? | Current research and repository proof | Yes. Recent preprints identify replay, context-binding, retry, concurrency, and cross-stage consistency gaps. The repository already demonstrates several of these controls. |
| Is a plain policy gate differentiated? | Public Buildathon repositories; non-exhaustive | No. Several public entries already combine an LLM planner, deterministic spend rules, idempotency, audit, and Razorpay test-mode orders. |
| Does Retry Budget now dominate? | Track language, Razorpay product announcements, public submissions | No. Track 03 has a higher batch-recovery burden, Razorpay already announces Subscription Recovery, and a public competitor shows real order/payment/refund evidence and batch recovery. |
| Can the recommended product use public Razorpay infrastructure? | MCP and Payment Link documentation | Yes for action issuance in test mode. Payment Link creation is not autonomous settlement and must remain labelled `ACTION_ISSUED`. UPI Reserve Pay requires activation/eligibility and is an integration seam, not an MVP dependency. |

## Evidence synthesis

### [First-party] Buildathon bar

The [Razorpay AI Buildathon page](https://razorpay.com/buildathon/) says Track 01
should grow merchant revenue or make a merchant transactable by an AI buyer using
test-mode APIs. It explicitly requires money actions to be explainable, bounded,
and gated, with an audit trail and one graceful failure. It also requires a public
repo, architecture, and five-minute video. The page shows an internship starting
“from September” but no application deadline.

**Implication:** a security control alone is insufficient. The entry should show a
merchant outcome and an end-to-end AI-buyer flow while preserving the gate.

### [First-party] Razorpay's product signal

The [Agentic Payments product page](https://razorpay.com/agentic-payments/) emphasizes
consent-based pre-authorization, approved spending limits, delegated payments,
real-time visibility, and granular control. It labels UPI Reserve Pay live and UPI
Circle coming soon. Razorpay's [ChatGPT/NPCI launch post](https://razorpay.com/blog/razorpay-unveils-agentic-payments-on-chatgpt-with-npci-indias-first-ai-powered-conversational-payment-experience/)
explicitly describes repeated human authentication as the friction that prevents
autonomous commerce and describes pre-authorizing a trusted agent within user-defined
limits. The [Claude launch post](https://razorpay.com/blog/?p=26080) repeats the
one-time, merchant-scoped spending-limit model and instant revocation.

**Implication:** the current exact-cart confirmation path is safe but strategically
under-claims the agentic outcome. The better authorization event is approval of a
bounded job, followed by exact machine authorization of the final compliant action.

### [First-party] Open protocol direction

Google's [AP2 v0.2 specification](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/specification.md)
requires deterministic validation even when a role is agentic. It distinguishes:

- a direct mode in which the user approves a closed checkout; and
- an autonomous mode in which the user approves open constraints and the agent later
  creates a closed checkout that verifiers deterministically check against them.

AP2 also version-tags mandate schemas, binds a closed checkout by hash, uses expiry,
and returns receipts. Its [Checkout Mandate specification](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/checkout_mandate.md)
defines allowed-merchant and line-item constraints. Google's
[official AP2 launch](https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol)
frames the protocol as payment-agnostic infrastructure that works with A2A and MCP.

**Boundary:** Action Firewall should describe this as standards alignment, not AP2
conformance. The MVP does not issue AP2 SD-JWTs, operate a credential provider, or
implement an AP2 trusted surface.

### [Research, preprint] Why runtime proof matters

A February 2026 [runtime-verification preprint](https://arxiv.org/abs/2602.06345)
argues that signatures and expiration do not by themselves solve retries,
concurrency, replay, and context redirection; it proposes execution-time context
binding and consume-once semantics. A September 2026
[formal-analysis preprint](https://arxiv.org/abs/2609.00060) reports cross-stage
consistency findings across ACP, AP2, MPP, and x402. An August 2026
[AP2 threat-analysis preprint](https://arxiv.org/abs/2608.23858) notes that signed
mandates protect transaction data after signing while pre-authorization agent and
tool interactions remain a separate attack surface.

These are current preprints, not settled standards. They nevertheless support a
precise product claim: protocol-shaped intent still needs a stateful runtime that
binds, consumes, dispatches, and reconciles authority safely.

### [First-party] Razorpay tooling and product boundaries

Razorpay's [MCP tools reference](https://razorpay.com/docs/mcp-server/tools-reference/)
documents 35+ tools across payments, links, orders, refunds, QR codes, settlements,
and payouts. The [Remote MCP documentation](https://razorpay.com/docs/mcp-server/remote/)
documents the Streamable HTTP endpoint and merchant-key or OAuth authentication.
Razorpay's [Payment Link API](https://razorpay.com/docs/api/payments/payment-links/create-standard/)
supports public test-mode creation and unique references, but link creation is not
payment completion. The [UPI Reserve Pay guide](https://razorpay.com/docs/payments/recurring-payments/upi-reserve-pay/?preferred-country=IN)
describes one authorization followed by exact debits, but tells merchants to request
activation and check eligibility.

**Implication:** the MVP can prove a real Razorpay test-mode action and expose an
adapter seam for Reserve Pay. It must not present a Payment Link as an autonomous
debit or claim Reserve Pay access.

### [First-party] Vulcan boundary

Razorpay's [Vulcan announcement](https://razorpay.com/blog/?p=27542) discloses a
proprietary foundation model used for route scoring, network fraud, payment-method
recommendation, and checkout/offer personalization. It does not publish a customer
policy API or authorize Buildathon access.

**Allowed positioning:** “Vulcan can decide what is likely to work. Action Firewall
proves whether this agent is allowed to do it.”

### [First-party] Evaluation signal

Razorpay's [evaluation article](https://razorpay.com/blog/?p=27428) says generic
benchmarks do not measure the whole agentic system and argues for task-specific
evaluations that include the harness, tools, context, latency, cost, and security.

**Implication:** publish a task-level commerce corpus and measure the entire path,
not just LLM extraction accuracy or the deterministic unit suite.

### [Competitive observation] Public field

This search is non-exhaustive and public repositories can change. It found:

- [RazorAgent](https://github.com/Piyush-Thakur7/razoragent), a live bounded MCP
  commerce gateway with catalog adapters, policy checks, idempotency, Razorpay order
  creation, and six verification tests.
- [A Track 01 zero-trust commerce engine](https://github.com/Antariksh62/razorpay-AI-buildathon-track-01-AI-growth-Agentic-commerce)
  with an LLM buyer, deterministic policy, spend limits, expiry, audit streaming,
  and real test-mode order IDs.
- [AgentTrace](https://github.com/ps-aditya/agenttrace), now positioned for Track 03,
  with policy-aware checkout drift recovery, real test-mode order IDs, manually
  completed payments/refunds, and published batch evidence.
- [ATTEST](https://github.com/kunalKumar-13/attest), a Track 04-style finance control
  project with held-out batch metrics, explicit exceptions, and a large proof corpus.

**Implication:** “the model proposes; deterministic rules decide” is necessary but
not unique. Action Firewall must lead with a differentiated customer loop and use its
runtime semantics as proof underneath that loop.

## Candidate scorecard

Scoring is 1–10. Weighted total uses Razorpay fit 20%, execution credibility/reuse
20%, measurable impact 15%, demo 15%, feasibility 15%, novelty 10%, and honest Vulcan
alignment 5%.

| Candidate | Fit | Proof | Impact | Demo | Feasible | Novel | Vulcan | Weighted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Safe Autopilot Checkout: Purchase Envelope + exact grant + recovery | 10 | 10 | 9 | 9 | 8 | 8 | 7 | **9.05** |
| Policy-aware checkout repair only | 9 | 9 | 9 | 9 | 9 | 7 | 6 | **8.55** |
| Unknown-outcome reconciler for agent actions | 8 | 9 | 7 | 8 | 8 | 8 | 5 | **7.85** |
| Agent-readable catalog contract gateway | 9 | 7 | 8 | 7 | 8 | 6 | 6 | **7.65** |
| Payment-link abandonment recovery | 8 | 7 | 9 | 8 | 7 | 6 | 6 | **7.55** |
| Retry Budget for AutoPay | 9 | 5 | 9 | 8 | 5 | 8 | 7 | **7.35** |
| Agentic checkout attack/conformance lab | 8 | 8 | 6 | 8 | 7 | 8 | 4 | **7.15** |
| Dispute authorization evidence pack | 8 | 6 | 8 | 7 | 6 | 7 | 4 | **6.90** |
| Generic merchant sales assistant | 6 | 7 | 6 | 6 | 9 | 3 | 4 | **6.25** |
| Vulcan-like route or payment-method advisor | 7 | 3 | 8 | 7 | 4 | 5 | 10 | **5.75** |

## Decision

Adopt Safe Autopilot Checkout as the proposed product evolution. Keep Track 01.
Keep `Action Firewall` as the trust-bearing product name and use the new customer
subtitle. Keep Retry Budget as research only.

Do not modify the authoritative brief or code until the product decision is accepted.
The proposed autonomous-envelope path deliberately changes the current invariant
that every final cart requires a fresh human confirmation. The replacement invariant
is stricter in a different place:

> A human must approve the canonical Purchase Envelope on a trusted surface. Every
> later cart must be deterministically proven to be a member of that envelope before
> an exact, one-use Action Grant can be derived.

## Research stop condition

Research stopped after current first-party sources established the Track 01 bar,
Razorpay's delegated-payment direction, public tooling limits, Vulcan boundary, and
evaluation philosophy; a current open protocol established the open-to-closed
authorization shape; recent research supported the runtime gap; and a non-exhaustive
competitive scan showed why a plain rules gate is insufficient. Further generic
market-size or agentic-commerce forecasts would not alter the product decision.

## Source-quality ledger

| Source | Class | Visible date/status | Used for | Limitation |
|---|---|---|---|---|
| [Razorpay Buildathon](https://razorpay.com/buildathon/) | First-party | live, checked 5 Sep 2026 | tracks, deliverables, judging bar | no deadline shown |
| [Razorpay Agentic Payments](https://razorpay.com/agentic-payments/) | First-party | live, checked 5 Sep 2026 | product language and status labels | marketing surface, not an API contract |
| [Agentic Payments with NPCI/OpenAI](https://razorpay.com/blog/razorpay-unveils-agentic-payments-on-chatgpt-with-npci-indias-first-ai-powered-conversational-payment-experience/) | First-party | 9 Oct 2025 | repeated-authentication problem and delegated limits | private beta; no project access |
| [Agentic Payments on Claude](https://razorpay.com/blog/?p=26080) | First-party | 2026 page | merchant-scoped one-time authorization | early access; no project access |
| [Sprint 2026](https://razorpay.com/sprint/26) | First-party | live 2026 | product overlap and direction | launch page summaries, some copy inconsistencies |
| [Vulcan](https://razorpay.com/blog/?p=27542) | First-party | 18 Aug 2026 | public production functions and boundary | proprietary; no public Buildathon interface found |
| [Razorpay evals](https://razorpay.com/blog/?p=27428) | First-party | 4 Aug 2026 | system-level bespoke evaluation philosophy | software-agent case, applied by inference to commerce |
| [MCP tools](https://razorpay.com/docs/mcp-server/tools-reference/) | First-party docs | live | public action surface | count and support can change |
| [Remote MCP](https://razorpay.com/docs/mcp-server/remote/) | First-party docs | live | transport and authentication | does not authorize arbitrary tool exposure |
| [Payment Link API](https://razorpay.com/docs/api/payments/payment-links/create-standard/) | First-party docs | live | test-mode action and state boundary | link issuance is not payment |
| [UPI Reserve Pay](https://razorpay.com/docs/payments/recurring-payments/upi-reserve-pay/?preferred-country=IN) | First-party docs | live | future adapter seam | activation and eligibility required |
| [AP2 v0.2](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/specification.md) | Primary open specification | v0.2, live | autonomous open constraints and deterministic verification | not implemented by this repo |
| [AP2 checkout constraints](https://github.com/google-agentic-commerce/AP2/blob/main/docs/ap2/checkout_mandate.md) | Primary open specification | live | merchant and line-item constraint shape | does not define this project's policy object |
| [Google AP2 launch](https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol) | First-party | 16 Sep 2025 | ecosystem and protocol purpose | announcement, not full spec |
| [Runtime verification](https://arxiv.org/abs/2602.06345) | Research preprint | 6 Feb 2026 | concurrency, replay, context binding | preprint; reported benchmarks not independently reproduced here |
| [Formal protocol analysis](https://arxiv.org/abs/2609.00060) | Research preprint | 1 Sep 2026 | cross-stage consistency | very recent preprint |
| [AP2 threat analysis](https://arxiv.org/abs/2608.23858) | Research preprint | Aug 2026 | pre-authorization/tool interaction gap | preprint |
| Public Buildathon repos linked above | Competitive observation | checked 5 Sep 2026 | non-exhaustive differentiation check | self-reported evidence; can change |
| Current repository and 61-test run | Internal proof | checked 5 Sep 2026 | execution baseline | not production or regulatory evidence |
