# Razorpay AI Buildathon 2026 — Market Context and Winning Submission Strategy

**Research cut-off:** 31 August 2026 (Asia/Kolkata)  
**Decision:** Ship **Action Firewall — Agentic Checkout Authorization for Razorpay** in **Track 01: AI Growth & Agentic Commerce**. Keep **Retry Budget** as a 48-hour challenger only; do not pivot unless it clears the proof gate in this document.  
**Status:** Supporting market context. The authoritative build specification remains `claude/project-brief.md`. That file was not present in this workspace during this research pass, so this document does not silently amend it.  
**Evidence labels:** **Primary** = first-party Razorpay, NPCI, RBI, TRAI, or official repository documentation; **Secondary** = credible reporting or industry interpretation; **Internal** = supplied project notes or locally verified build evidence; **Inference** = a recommendation derived from the evidence rather than a published fact.  
**Regulatory note:** This is product and hackathon research, not legal advice. Any production policy pack requires review by Razorpay/NPCI-participant compliance and counsel.

> **1 September 2026 correction and refinement.** The strategic decision still stands, but three claims in the 31 August snapshot are no longer supportable as first-party facts. The live Buildathon page and official application currently show **no submission deadline**, expose **no separate four-dimension scoring rubric**, and contain **no dedicated “what broke/how recovered” application field**. The five-minute video, repository, project objectives, and Track 01 requirement for one graceful failure remain current. A previously reported 5 September date may be used only as an internal urgency assumption sourced to secondary listings, not as a confirmed-current official deadline. The official MCP repository also lists **45 tools in the dated 1 September snapshot**, rather than the older marketing shorthand alone. The detailed engineering review further found that the present Boolean allow decision is not yet an exact action authorization boundary. The controlling refinement is [ACTION_FIREWALL_STRATEGY_MEMO_2026-09-01.md](ACTION_FIREWALL_STRATEGY_MEMO_2026-09-01.md), supported by [DEMO_SCRIPT_ACTION_FIREWALL_5_MIN.md](DEMO_SCRIPT_ACTION_FIREWALL_5_MIN.md), [BUILD_PLAN_ACTION_FIREWALL.md](BUILD_PLAN_ACTION_FIREWALL.md), and [RISK_REGISTER_ACTION_FIREWALL.md](RISK_REGISTER_ACTION_FIREWALL.md). Where this dated correction conflicts with the historical body below, this correction controls.

## 1. Executive summary

Razorpay is not asking for the fanciest agent; it is asking for evidence that a student can be trusted with a real payment workflow. The current Buildathon page makes the Track 01 standard unusually explicit: use test-mode APIs or make a merchant transactable by an AI buyer, keep money actions explainable, bounded, and gated, maintain an audit trail, and show one graceful failure. The current first-party pages do not display a deadline; operate urgently, but do not present the earlier 5 September date as confirmed-current official evidence. Vulcan reinforces the strategic direction—shared, payment-native intelligence for routing, fraud, and checkout decisions—but no public Vulcan API or SDK is available, so pretending to integrate it would reduce credibility. Track 03's Retry Budget is the strongest greenfield concept because Razorpay names mandate retry sequencing and asks for measured batch recovery, but Razorpay also already markets an Intelligent Retry Engine and Subscription Recovery agent. With a verified Track 01 implementation already at 20 commits and 32 passing backend tests, the higher-probability submission is to harden the existing project as an **Agentic Payment Action Firewall**: the LLM may retrieve, interpret, and propose a cart; a short-lived, exact-bound, versioned, concurrency-safe policy receipt alone may authorize one Razorpay action. Add the fail-closed action registry, ambiguous-outcome reconciliation, adversarial certification harness, benign-traffic metrics, an honest test-mode tool call, and the actual TOCTOU/idempotency failure story. This is narrower, more original, more complete, and more defensible than an unfinished retry optimizer built on synthetic claims.

## 2. Decision first

### Recommended submission

**Action Firewall — Agentic Checkout Authorization for Razorpay**  
**Track:** 01 — AI Growth & Agentic Commerce  
**Thesis:** *Agentic commerce is an authorization problem before it is a checkout problem.*  
**One-line value proposition:** *The AI can propose what to buy; only a deterministic, customer-defined policy can authorize a Razorpay payment action.*

### Why this wins the decision now

1. **It answers Track 01's stated bar directly.** Razorpay asks for money actions that are bounded, gated, explainable, audited, and able to fail gracefully. The project already implements that boundary rather than promising it. [Razorpay AI Buildathon](https://razorpay.com/buildathon/)
2. **It has verified execution evidence.** On 31 August, the existing repository had a clean working tree, 20 commits, and **32/32 backend tests passing in 4.36 seconds**. The suite includes a barrier-based concurrency reproduction, reservation/idempotency tests, and mandate boundary tests. This is current local evidence, not a pitch claim.
3. **It has the strongest answer to Track 01's graceful-failure requirement.** The project can show a genuine check-then-act race and then show the two-phase reservation that prevents it. The exact unsafe total must be generated by a deterministic barrier fixture rather than memorized or presented as a current application-form question.
4. **It is complementary to Vulcan without inventing access.** Vulcan scores payment routes and detects ecosystem-level patterns; the firewall answers a separate question: whether an AI agent is authorized to initiate the action at all. [Razorpay's Vulcan launch article](https://razorpay.com/blog/?p=27542)
5. **It avoids the largest Track 03 objection.** Razorpay already presents Subscription Recovery, merchant-configurable retry logic, and an Intelligent Retry Engine. A new timing model built on synthetic data can look like a smaller clone unless its compliance/evaluation control plane is already working. [Agent Studio](https://razorpay.com/agent-studio/) · [Intelligent Revenue-Protect](https://razorpay.com/blog/upi-autopay-with-intelligent-revenue-protect/)

### What changes from the existing public framing

- Rename the product from **“UAP Mandate Agent”** to **“Action Firewall”** or **“Agentic Checkout Authorization Policy.”** “Mandate” can be mistaken for a regulated UPI AutoPay mandate; this product is a shopper-defined authorization policy, not a banking mandate or legal substitute.
- Keep the single-agent pipeline, but describe the boundary as `retrieve → propose → authorize/reserve → act/reconcile`.
- Promote the concurrency fix, policy-version receipt, and adversarial CI gate to first-class product features.
- Stop leading with “value blocked” or “₹0 chargeback liability.” Blocked test-mode value is **protected exposure**, not audited savings, and no prototype can prove zero liability.
- Pair safety with utility: measure benign checkout completion, false blocks, constrained cart-repair success, and authorization latency—not only denials.

## 3. What the current evidence actually says

### 3.1 This is a hiring funnel, and the submission should demonstrate judgment

The official page describes a student-only program for hiring AI Builder Interns, with a ₹75,000 monthly stipend, six- or twelve-month terms, and in-person work in Bengaluru from September. When rechecked on 1 September, the live application requested identity/college details, availability, duration, track, project title, project objectives, a GitHub URL, and a five-minute video. It did not expose a separate public scoring rubric or dedicated failure-recovery answer.

The following remain useful **inferred review themes**, not published scoring dimensions:

- **Problem taste:** does the project address something that matters?
- **Build quality:** does it run, is it structured, and would an engineer trust it?
- **AI judgment:** was AI used only where it belongs?
- **Failure recovery:** does the Track 01 graceful failure expose sound recovery behavior?

The current official page and form do not display a deadline, shortlist date, result date, prize pool, numeric scoring weights, or judge list. Optimize for engineering-panel trust, not hackathon spectacle, and label any secondary deadline as unconfirmed-current. [Buildathon page](https://razorpay.com/buildathon/) · [official application](https://docs.google.com/forms/d/e/1FAIpQLScJ9XSqVCB2oaPwEMH0Zk3I1OpILFW1WpWdWweQ2950jdRzlg/viewform?usp=send_form)

The tracks reveal a consistent pattern:

| Track | Official signal | Evidence expected |
|---|---|---|
| **01 — AI Growth & Agentic Commerce** | Grow merchant revenue or make a merchant transactable by an AI buyer. | Bounded, gated, explainable money actions; audit trail; one graceful failure. |
| **02 — AI Risk Manager** | Solve one fraud, return, chargeback, or abuse loss class. | Held-out precision/recall, false-positive cost, defense-only behavior. |
| **03 — AI Revenue Recovery** | Detect revenue at risk, choose an intervention, and execute a bounded recovery loop. | Measured batch recovery, compliant escalation, stopping rules, audit. |
| **04 — AI Finance Controller** | Close one finance-operations loop across at least 50 synthetic records. | Throughput, measured accuracy/match rate, and an honest exception list. |
| **05 — Open** | Solve a real problem with meaningful AI and a working product. | Same reliability and depth bar, with less strategic guidance. |

**Inference:** Razorpay is selecting for builders who can turn uncertain AI output into a deterministic, inspectable operational decision. A chatbot, polished UI, or one cherry-picked success is weak evidence.

### 3.2 Vulcan is payment intelligence, not a Buildathon API

Razorpay describes Vulcan as a proprietary, transformer-based payments foundation model trained on payment behavior—not a conversational LLM. Published production uses include pre-attempt route scoring, network fraud detection, return-to-origin risk, payment-method/checkout personalization, and offer targeting. Razorpay says it handles almost four billion customer-to-merchant payments annually; an AWS-hosted Razorpay release separately says Vulcan was trained on nearly three trillion data points across four billion payments and roughly 3,000 transaction signals. Those two “four billion” figures should not be assumed to describe the same period or population. [Razorpay article](https://razorpay.com/blog/?p=27542) · [AWS-hosted Razorpay release](https://press.aboutamazon.com/aws-international/2026/8/razorpay-launches-vulcan-indias-first-ai-payments-foundation-model-fueled-by-nvidia-and-aws-re-architecting-payments-for-a-350-bn-e-comm-future-by-2030) · [Vulcan product page](https://razorpay.com/foundation-model/)

Razorpay reports an 8–10% payment-success improvement and other fraud/personalization gains, but the public material does not expose baseline definitions, evaluation windows, confidence intervals, or independent validation. Attribute those outcomes to Razorpay if used; do not present them as independently proven.

As of the research cut-off, the public site, developer documentation, official GitHub organization, and MCP server expose no Vulcan API, SDK, endpoint, model weights, or builder integration guide. Absence from public documentation cannot rule out private partner access, but it does establish the safe submission claim:

> **Vulcan-aligned and complementary—not powered by Vulcan.**

For Action Firewall, the clean boundary is: **Vulcan can help choose how a payment should travel; Action Firewall proves whether this agent is authorized to initiate it.** A future Vulcan score may be accepted as untrusted advisory input, but it can never bypass customer policy.

### 3.3 Razorpay is signaling bounded agents, not autonomous theater

Razorpay's Agent Studio principles emphasize merchant-defined scope and ceilings, explicit review or confirmation for irreversible actions, a kill switch, verified connected data, independent platform validation, complete action logs, consent/opt-out controls, and continuous evaluation. These are product principles rather than formal Buildathon scoring weights, but they are the clearest first-party description of trustworthy agent behavior. [Agent Studio guardrails](https://razorpay.com/blog/razorpay-agent-studio-principles-guardrails-and-merchant-control/)

Agent Studio's product page also reveals what is already crowded: Dispute Responder, Subscription Recovery, Abandoned Cart Conversion, RTO Shield/Insights, Settlement Insights, and Cashflow Forecaster. A submission that merely reproduces one of those cards with a chat interface is easy to dismiss. [Agent Studio](https://razorpay.com/agent-studio/)

Razorpay's official MCP repository provides a genuinely native action surface. Its current table contains **45 tools**, including `initiate_payment`, `capture_payment`, payment-link and order operations, refunds, QR codes, settlements, payouts, and token operations. Four listed tools are unavailable on the remote server: `create_refund`, `close_qr_code`, `create_instant_settlement`, and `create_registration_link`. The repository does not list subscription execution, mandate-debit, invoice, dispute, or chargeback tools. [Official Razorpay MCP repository](https://github.com/razorpay/razorpay-mcp-server)

**Implication for Action Firewall:** guard an allowlist of real test-mode MCP operations and demonstrate at least one genuine Razorpay call. `create_payment_link` is a consent-preserving action, not proof that money was debited; label it correctly. If time permits, add a sandbox path for a stronger action such as `initiate_payment` or `capture_payment`, with explicit user confirmation and the same policy receipt.

**Implication for Retry Budget:** mandate execution must use Razorpay REST/S2S APIs, webhooks, the test dashboard, or a simulation adapter. Do not claim MCP is the retry actuator.

### 3.4 Why Retry Budget remains the strongest challenger

Track 03 explicitly names “Failed-subscription recovery” and “Mandate retry sequencer,” and its bar maps almost perfectly to the proposed proof: batch-level recovery, compliant escalation, stopping, and audit. The regulatory constraints also make it a real bounded optimization problem rather than a generic dunning bot:

- NPCI's May 2025 UPI API-usage circular limits an AutoPay mandate execution sequence to **one initial attempt plus three retries** and requires non-peak execution. The consistently published peak periods are 10:00–13:00 and 17:00–21:30, leaving windows before 10:00, 13:00–17:00, and after 21:30. Treat “per mandate, per sequence number” as a cycle-level cap, not four lifetime attempts. [NPCI circular](https://www.npci.org.in/PDF/npci/upi/circular/2025/UPI-OC-No-215-A-FY-2025-26-Guidelines-on-usage-of-UPI-APIs.pdf) · [text-readable mirror](https://avantiscdnprodstorage.blob.core.windows.net/legalupdatedocs/42884/NPCI-issued-guidelines-on-the-usage-of-UPI-API-May222025.pdf)
- RBI's consolidated 2026 e-mandate directions require a pre-transaction notification at least **24 hours before debit**, with an opt-out path, subject to specified exceptions. The ₹15,000 general and ₹1,00,000 insurance/mutual-fund/credit-card-bill thresholds determine when a subsequent transaction can proceed without AFA; they are not universal mandate caps. [RBI Digital Payments — E-mandate Framework, 2026](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=13374&Mode=0) · [NPCI AutoPay overview](https://www.npci.org.in/product/autopay)
- Razorpay's test Subscriptions flow can demonstrate a charge as success or failure from the dashboard. Four consecutive failed subscription attempts move it to `halted`; this product state machine is not proof of the NPCI UPI 1+3 rule. Test-card tokens remain valid for only three days. [Test Subscriptions](https://razorpay.com/docs/payments/subscriptions/test/?preferred-country=IN) · [Payment Retries](https://razorpay.com/docs/payments/subscriptions/payment-retries/?preferred-country=IN)
- TRAI classifications are content-based. A factual, consented notice that facilitates an ongoing service can remain a service communication; adding discounts, cross-sells, or promotional inducements can make the whole communication promotional. Use registered, allowlisted templates and keep service facts separate from marketing. [TCCCPR Second Amendment, 2025](https://www.trai.gov.in/sites/default/files/2025-02/Regulation_12022025.pdf) · [TRAI Advice to Senders](https://www.trai.gov.in/advice-to-senders)

The opportunity is therefore real—but Razorpay's own recurring stack already advertises merchant-configurable retry cadence/templates, intelligent retry logic, WhatsApp recovery, and Subscription Recovery. [Intelligent Revenue-Protect](https://razorpay.com/blog/upi-autopay-with-intelligent-revenue-protect/) A Buildathon entry can differentiate only by becoming the **compliance, concurrency, and evaluation control plane around any recovery engine**, not by claiming that a synthetic model found a smarter hour.

### 3.5 Current execution evidence changes the theoretical ranking

The supplied Track 01 build log was verified against `C:\Users\user\projects\razorpay-uap-mandate-agent` on 31 August:

- clean Git working tree;
- 20 commits at `bbab876a6ec0308cc1908767388023e29e77b9d4`;
- `python -m pytest -q` from `backend/`: **32 passed in 4.36 seconds**;
- a pure mandate verifier, integer-paise money, revocation semantics, append-before-act audit, a two-phase reservation, TTL, and session-scoped idempotency are present in the code/test evidence;
- `tests/test_concurrency.py::test_naive_check_then_act_overspends` reproduces the unguarded race before the fixed path is tested.

No equivalent running Track 03 repository, batch harness, held-out uplift report, or actuator proof was supplied for this research pass. Under the current submission urgency—even though the official first-party deadline is not displayed—that proof difference remains strategically decisive.

## 4. Candidate concepts and scorecard

Scores are research judgment, not Razorpay's undisclosed judging weights. Each dimension is rated 1–5. Weighted total: Razorpay fit **20%**, technical credibility **15%**, demo clarity/wow **15%**, measurable impact **15%**, hackathon feasibility **15%**, novelty without fantasy **10%**, Vulcan alignment **10%**. Feasibility reflects current submission urgency and the verified build state, not a confirmed-current first-party deadline.

| Rank | Candidate | Track | Fit | Cred. | Demo | Impact | Feas. | Novel | Vulcan | Total | Judge-risk summary |
|---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **1** | **Action Firewall — agentic checkout authorization** | 01 | 5 | 5 | 5 | 4 | 5 | 5 | 4 | **95** | Already working; strongest trust/failure story. Must avoid regulated “mandate” language and prove utility, not only blocking. |
| **2** | **MCP Checkout Certification Harness** | 05 standalone / 01 as a layer | 5 | 5 | 4 | 4 | 5 | 5 | 4 | **92** | Extremely defensible but a weaker standalone revenue product; best embedded as Action Firewall's evaluation moat. |
| **3** | **Retry Budget — compliant AutoPay attempt control plane** | 03 | 5 | 5 | 5 | 5 | 4 | 3 | 3 | **89** | Perfect named-track fit and metrics; dangerous overlap with Razorpay Intelligent Retry and no working batch proof yet. |
| **4** | **Pre-Debit Proof Rescheduler** | 03 | 5 | 5 | 4 | 4 | 5 | 4 | 2 | **86** | Clean refusal/recovery demo; may look like a rules engine with decorative AI. |
| **5** | **Mandate-Aware Cart Rescue** | 01 | 5 | 4 | 5 | 4 | 4 | 4 | 3 | **85** | Converts a safe deny into revenue; harder to prove a moat and could distract from the authorization thesis. |
| **6** | **False-Decline Rescue Decisioner** | 03 | 5 | 3 | 5 | 5 | 2 | 4 | 5 | **83** | Strong Vulcan adjacency and business value; honest validation needs proprietary route/outcome data. |
| **7** | **Dispute Evidence Completeness Gate** | 02 | 5 | 4 | 4 | 5 | 4 | 3 | 2 | **81** | Measurable loss prevention; overlaps Dispute Responder and needs realistic evidence labels. |
| **8** | **Razorpay Integration Regression Co-Pilot** | 05 | 5 | 5 | 4 | 4 | 4 | 2 | 2 | **79** | Useful and testable; visibly duplicates RAY Co-Pilot unless narrowed to payment invariants. |
| **9** | **Vulcan Route-Decision Shadow Auditor** | 02 | 5 | 2 | 4 | 5 | 2 | 4 | 5 | **77** | Attractive on slides, weak in reality: no public Vulcan endpoint or authentic route-decision dataset. |
| **10** | **Reconciliation Exception Resolver** | 04 | 5 | 4 | 4 | 5 | 3 | 2 | 2 | **76** | Real merchant pain and clear metrics; crowded by existing finance/settlement products and realistic data costs time. |
| **11** | **Receivables Contact-Policy Agent** | 03 | 4 | 3 | 5 | 4 | 3 | 2 | 2 | **69** | Flashy, but risks becoming a generic voice/WhatsApp agent and creates TRAI classification complexity. |

## 5. Full concept — Action Firewall

### 5.1 Problem statement

AI buyers can already discover products and invoke payment tools, but an LLM is probabilistic, prompt-injectable, and unaware of live spending headroom. A shopper saying “buy dinner supplies” is not the same as authorizing any SKU, any quantity, any category, or any amount. A check performed before an external call can also become stale when two turns run concurrently. The missing layer is an independent, deterministic authorization boundary that the model and tool client cannot bypass.

### 5.2 Target user

- **Primary:** a consumer or merchant deploying an AI buyer against Razorpay test-mode payment actions.
- **Economic buyer inside Razorpay:** Agentic Payments / Agent Studio platform teams that need a reusable pre-action authorization and certification layer.
- **Operational user:** merchant risk/support teams reviewing denied actions, replaying receipts, and managing policies or a kill switch.

### 5.3 Why now

- Razorpay is piloting agentic commerce with ChatGPT/Claude and emphasizes spending limits, visibility, confirmation, and instant revocation. These pilots make authorization a current platform problem rather than a speculative one. [Razorpay–Claude agentic-payments pilot](https://razorpay.com/newsroom/?p=4701)
- Track 01 explicitly demands bounded, gated, explainable money actions with audit and graceful failure. [Buildathon](https://razorpay.com/buildathon/)
- Razorpay's MCP exposes AI-callable payment actions such as `initiate_payment`, `capture_payment`, order creation, and payment links. [MCP repository](https://github.com/razorpay/razorpay-mcp-server)
- The local build has already found concurrency and idempotency failures that a normal happy-path checkout demo would miss.

### 5.4 Why Razorpay

This is native to the boundary between Razorpay's agentic commerce surfaces, MCP/payment APIs, and payment-control doctrine. It uses Razorpay test mode, tool schemas, payment/order identifiers, integer paise, server-side credentials, audit-before-act semantics, and payment reconciliation. Its central artifact—a versioned decision receipt—could sit in front of any Razorpay money-relevant tool, not only the grocery demo.

### 5.5 Why Vulcan

Vulcan is relevant because it shows Razorpay's future: shared payment-native intelligence will make more decisions across routing, fraud, and checkout. More intelligence increases the need for an orthogonal authorization boundary. Action Firewall does not compete with Vulcan and does not pretend to call it:

- **Vulcan/advisory intelligence:** estimate which route, method, or offer is likely to work.
- **Action Firewall/authority:** determine whether this actor, policy version, cart, amount, category, and attempt may proceed.
- **Non-bypass rule:** a future Vulcan score can change an advisory recommendation; it cannot override a denial or create headroom.

This is the strongest defensible Vulcan alignment available without private access.

### 5.6 Core workflow

1. **Retrieve catalog:** use Pinecone when configured; use the deterministic catalog fallback for offline demos. Retrieval returns known SKUs and source metadata.
2. **Propose cart:** one LLM interprets intent and proposes cart operations. It never assigns prices, authorizes spend, or sees payment secrets.
3. **Canonicalize:** deterministic code drops unknown SKUs, resolves products only on discriminating evidence, applies integer-paise prices, multiplies quantity, and creates a canonical cart hash.
4. **Re-read policy:** fetch the latest shopper authorization on every turn. Distinguish “none,” “revoked,” “expired,” and “active”; record `policy_version`.
5. **Pure decision:** `verify(cart, policy, spent)` returns `ALLOW`, a typed denial, or `REQUIRE_CONFIRMATION` with a reason-code tree. No I/O occurs inside the verifier.
6. **Atomic reservation:** for an allowed checkout, re-check live headroom and write a hold in one database transaction. The idempotency identity includes session/purchase context; a retry reuses the same reservation. TTL releases orphaned holds.
7. **Audit before action:** append the decision, policy version, cart hash, amount, actor, idempotency identity, and reason before any external call.
8. **Act through an allowlist:** the tool client independently refuses any denied decision. Call a real Razorpay test-mode MCP operation only after reservation and any required user confirmation.
9. **Reconcile:** commit the reservation only after a confirmed success; release on a definitive failure; quarantine an unknown outcome and fetch/reconcile before another attempt.
10. **Repair or stop:** on a recoverable denial, propose a constrained, lower-priced cart using only valid SKUs, then re-run the entire authorization path. On revocation, forbidden category, unknown policy, or kill switch, stop.

### 5.7 Model and agent architecture

Use **one agent**, not a performative multi-agent swarm:

```text
shopper intent
    ↓
catalog retrieval ──→ cited/known SKUs
    ↓
LLM cart proposal
    ↓
deterministic canonicalizer
    ↓
pure policy decision ── deny ──→ audit receipt + bounded repair/stop
    ↓ allow
atomic headroom reservation
    ↓
append-only audit
    ↓
allowlisted Razorpay MCP/test-mode action
    ↓
webhook/fetch reconciliation ──→ commit or release reservation
```

**AI belongs in:** natural-language intent interpretation, retrieval-query generation, cart proposal, and constrained repair language.  
**AI does not belong in:** price truth, SKU validity, caps, categories, revocation, idempotency, atomic reservation, tool allowlists, audit, or settlement truth.

Trace one turn with named spans for retrieval, planning, authorization/reservation, and actuation. A denied turn must provably lack the actuation span. Keep the catalog RAG because product knowledge changes; do not fine-tune a model to memorize a dynamic catalog. The single-agent divergence from fashionable multi-agent capstones is intentional: authorization is easier to reason about when one orchestrator crosses one independently enforced boundary.

### 5.8 Data inputs

- versioned shopper policy: window cap, per-transaction cap, category allow/block lists, status, version, effective time;
- spend ledger plus live reservations;
- canonical catalog with SKU, category, integer-paise price, and retrieval provenance;
- session/user/agent identity and client idempotency key when available;
- Razorpay test-mode tool response, payment/order identifiers, and webhook/fetch state;
- public, versioned adversarial corpus plus benign-intent set;
- trace metadata with secrets and unnecessary PII removed.

No proprietary Razorpay transaction dataset is needed. Pinecone and Langfuse have deterministic/no-network fallbacks so the demo remains reproducible.

### 5.9 Outputs and actions

- `ALLOW_RESERVED`
- `DENY_WINDOW_CAP`
- `DENY_PER_TRANSACTION_CAP`
- `DENY_CATEGORY`
- `DENY_REVOKED`
- `DENY_UNKNOWN_SKU`
- `DENY_CONCURRENCY_HEADROOM`
- `REQUIRE_USER_CONFIRMATION`
- `REPAIR_CART`
- `QUARANTINE_UNKNOWN_PAYMENT_STATE`

Every result produces a replayable decision receipt containing policy version, canonical inputs/hash, reason codes, reservation/action references, timing, and final reconciliation state. External actions are limited to an explicit server-side allowlist.

### 5.10 Safety and guardrails

**MVP invariants that must be demonstrated:**

- integer paise end to end;
- pure deterministic policy verification;
- current policy re-read per turn; revocation binds on the next turn;
- deny-by-default on missing/ambiguous state;
- unknown SKUs cannot be priced or purchased;
- atomic two-phase headroom reservation;
- session-scoped/client-supplied idempotency and safe replay;
- append audit before the external call;
- spend ledger commits only after success;
- tool client refuses denied decisions independently;
- no secret or raw credential enters browser or model context;
- kill switch and an explicit confirmation step for the strongest irreversible action;
- no retry after an unknown outcome until reconciliation.

**Production path, not a current hackathon claim:** signed policy attestations, durable outbox, webhook signature verification, distributed database/locking, stronger identity binding, policy-pack migration controls, data-retention rules, redaction, RBAC, and independent security review.

### 5.11 Evaluation plan and metrics

The current 32 tests are the floor. The winning evidence is an adversarial certification report that shows the system remains safe *and useful*.

**Corpus:** at least 50–100 attacks, three or more seeds, and two models if budget permits; publish all prompts, expected invariants, configuration, and every exception. Include:

- prompt injection and tool-call coercion;
- hallucinated SKU and shared-word product confusion;
- quantity, cap-splitting, category-laundering, and price manipulation;
- revoked/stale policy;
- same-session replay and cross-session identical baskets;
- concurrent turns, double-clicks, crash/TTL, and delayed webhook;
- MCP timeout, malformed response, and unknown payment state;
- benign prompts close to policy boundaries to measure false blocks.

**Hard safety gate — must be zero:**

- unauthorized actuator calls;
- duplicate committed effects for one purchase identity;
- denied turns containing an actuation span;
- purchases of unknown SKUs;
- actions after a revoked policy becomes effective;
- audit rows written after rather than before action.

**Utility and reliability metrics:**

- benign checkout completion rate;
- false-block rate and false-block value;
- compliant cart-repair success rate;
- policy-decision and end-to-end p50/p95 latency;
- idempotent replay success;
- reconciliation exception rate;
- `pass^k`: percentage of cases for which all `k` stochastic runs preserve every safety invariant.

**Economic reporting:** report test-mode settled value and protected exposure separately. Do not call protected exposure “revenue saved,” and do not claim chargebacks were eliminated.

**CI rule:** any hard-safety violation fails the build. Utility metrics may have disclosed thresholds and exceptions; they must not be hidden behind a single average.

### 5.12 Four-minute demo plan

**0:00–0:25 — The product in one sentence**  
Show the policy and chat side by side: “The model proposes; the firewall authorizes.” Put the current CI safety result on screen.

**0:25–1:10 — Legitimate purchase**  
Ask for pasta-dinner supplies. Show retrieved SKUs, the policy receipt, the reservation, and one real Razorpay test-mode MCP action. Label a payment link as a link/consent step, not as a completed debit.

**1:10–1:55 — Breach and proof of non-action**  
Inject an over-cap or forbidden addition. Show the typed denial, audit row, protected exposure, and—most importantly—the trace with no actuator span and no Razorpay call.

**1:55–2:35 — Graceful recovery**  
Offer a constrained downgrade using known SKUs. Re-run the gate; the compliant cart succeeds. Show that safety preserves conversion rather than merely blocking.

**2:35–3:20 — The real failure story**  
Show the barrier test: eight concurrent attempts through the naive check-then-act path settle ₹2,400 against a ₹1,000 cap. Then run the reservation test and show only permitted headroom is committed. Briefly show the idempotency replay.

**3:20–4:00 — Revocation and evidence**  
Revoke or reduce the policy; the next turn fails closed. End on the audit receipt and adversarial report: zero unauthorized calls, zero duplicate effects, benign completion/false-block numbers, and the published exception list.

### 5.13 Stretch goals, in priority order

1. Add the adversarial certification harness and HTML/JSON report. This is not optional if core work remains unfinished.
2. Guard a stronger real test-mode MCP action (`initiate_payment` or `capture_payment`) with explicit confirmation.
3. Sign/hash decision receipts and add replay verification.
4. Add an unknown-outcome reconciler and durable outbox.
5. Add policy simulation: “Would this proposed edit block normal weekly behavior?”
6. Add an optional Vulcan-score adapter interface, disabled by default and never required for authorization.

Do not spend submission time on a multi-agent rewrite, voice UI, extra dashboards, fine-tuning, or production cloud scale before the corpus and demo are complete.

## 6. Likely judge objections and defensible answers

| Judge objection | Strong answer | Evidence to show, not merely say |
|---|---|---|
| **“This is just rules, not AI.”** | The LLM handles ambiguous intent, catalog retrieval, cart planning, and constrained repair. Deterministic code owns irreversible authorization because the rubric rewards knowing where not to use AI. | One trace separating model spans from the pure decision and tool boundary. |
| **“A payment link does not move money.”** | Correct. It proves a real Razorpay integration and consent-preserving action, not a debit. The policy wrapper is action-agnostic; guard `initiate_payment`/`capture_payment` if a stable test path is available. | Clearly labeled test-mode action and no inflated settlement claim. |
| **“UAP mandate sounds like UPI AutoPay.”** | The public name is now Agentic Checkout Authorization Policy. It is a shopper policy, not a regulated bank mandate. | Updated deck, UI, README, and schema language. |
| **“Blocking purchases destroys conversion.”** | Recoverable denials trigger a constrained repair and full re-authorization. We measure false blocks, benign completion, and repair success. | Benign set and repair metric, not only blocked rupees. |
| **“What prevents two workers from spending the same headroom?”** | A database transaction re-checks consumption and creates a two-phase hold; idempotency, TTL, and reconciliation control retries and crashes. | Red race reproduction followed by green concurrency tests. |
| **“What if the model bypasses your route?”** | The MCP client independently rejects denied receipts, and no alternate actuator is allowlisted. Authorization is enforced at the tool boundary, not trusted to the prompt. | Direct unit test calling the client with a denied decision. |
| **“Where is Vulcan?”** | No public Vulcan integration exists. Vulcan selects likely payment outcomes/routes; the firewall enforces authority. A future score is advisory and non-bypassable. | Architecture boundary and public-source citation. |
| **“Why Razorpay-specific?”** | It wraps Razorpay MCP/test-mode tools, orders/payment identifiers, confirmation, reconciliation, reason codes, and agentic-payment controls. | Real sandbox call plus a Razorpay-shaped audit receipt. |
| **“Can you claim ₹0 chargeback liability?”** | No. We report test-mode settlement and protected exposure; production liability needs real outcomes and legal context. | Honest metric labels and limitations panel. |
| **“Why not Track 03 Retry Budget?”** | It is the best challenger, but Razorpay already has Intelligent Retry and the current deadline rewards completed proof. We chose the stronger, working authorization primitive and kept a measurable switch gate. | This scorecard, current test run, and 48-hour gate results. |

## 7. Brutally honest: why this can win

### The winning case

- The value is understandable in under 30 seconds: an AI buyer can be useful without being trusted to authorize itself.
- It addresses the exact Track 01 phraseology—bounded, gated, explainable, audited money actions—and Razorpay's published guardrail doctrine.
- It has a real system boundary, not a conversational wrapper: the model can be swapped without changing financial safety invariants.
- It has unusually strong failure evidence for a student submission: a reproduced concurrency bug, idempotency mistakes, catalog-resolution failure, and tested fixes.
- It is shippable with test-mode APIs and deterministic fallbacks; no secret proprietary dataset or imaginary Vulcan access is required.
- The adversarial corpus makes the project look like platform infrastructure Razorpay could reuse across agentic checkout, not one grocery demo.
- The submission can show both safety and conversion recovery, avoiding the “a system that rejects everything is safe” trap.

### How it still loses

- If the deck continues to call the policy a regulated-sounding UAP mandate, judges may spend the pitch correcting terminology.
- If the only real integration is a payment link and the narration calls it a debit, credibility collapses.
- If the 32 deterministic tests remain the only evaluation, the project may look like good backend engineering with insufficient AI evaluation.
- If the dashboard is polished but the benign false-block rate, attack corpus, and exception list are absent, it misses Razorpay's evidence standard.
- If Pinecone, Langfuse, MCP, or an LLM fails live and no deterministic demo fallback is rehearsed, the “graceful failure” story becomes theory.
- If the pitch says “powered by Vulcan,” “zero chargeback liability,” or “production-ready,” a strong judge can disprove the claim immediately.

### Non-negotiable acceptance gate before submission

The Action Firewall should be submitted only after all of the following are true:

- current 32 tests still pass;
- adversarial CI corpus exists and all hard-safety invariants pass;
- benign completion/false-block numbers are published;
- at least one real Razorpay test-mode action is captured in the demo;
- demo mode runs with no keys/network;
- failure/recovery story is shown from reproducible tests;
- public naming no longer conflates the policy with a regulated mandate;
- repo URL, five-minute video, architecture, and application answers are final before the deadline.

## 8. The Retry Budget challenger gate

Retry Budget may replace Action Firewall **only** if a working proof exists by the end of **2 September 2026 IST**, preserving the remaining time for hardening and the five-minute submission video. It must clear every gate:

1. **Running batch harness:** a published generator and at least one held-out evaluation batch; registration, remitter-bank execution, and PSP execution are never conflated.
2. **Honest baselines:** fixed legal schedule, random legal schedule, learned ranking, and oracle upper bound; report mean/variance across seeds and call all rupee results simulated.
3. **Measurable lift:** learned ranking beats the fixed baseline on held-out data. If it does not, remove the learned component rather than hiding the result.
4. **Control-plane differentiation:** code visibly verifies failure taxonomy, mandate/cycle, 24-hour notification evidence, legal window, attempt budget, stopping rule, and communication policy before ranking/actuation.
5. **Concurrency proof:** atomic attempt reservation, unique `(mandate, cycle, attempt)` identity, unknown-outcome reconciliation, and a barrier test prevent double fire.
6. **Actuator honesty:** Razorpay dashboard/test mode proves integration behavior; the synthetic harness proves batch policy/model behavior. Do not claim an API-selectable failure outcome or an MCP mandate tool.
7. **Product boundary:** one slide distinguishes the control plane from Razorpay Intelligent Retry/Subscription Recovery. If the UI and code cannot make that distinction obvious, the pivot fails.

If any gate is missing, stay with Action Firewall. A finished, measured Track 01 system is more likely to be shortlisted than an unfinished Track 03 concept, even though Retry Budget is the stronger greenfield idea.

If Retry Budget clears the gate, its narrow product contract should be:

```text
ingest failure
  → deterministic Razorpay error diagnosis
  → versioned eligibility/notification/attempt policy
  → learned ranking among already-legal windows only
  → atomic attempt reservation
  → REST/S2S or simulation actuator
  → webhook reconciliation
  → stopping rule + machine-verifiable receipt
```

Its leading metric should be **attempts per recovery**, followed by incremental simulated recovery versus fixed scheduling, mandates preserved, zero policy violations, zero duplicate attempts, calibration/regret versus oracle, and a published exception list. Its failure demo should rank a window, refuse to fire because 24-hour notification proof is absent, log the refusal, slide to the next legal window after proof arrives, and recover without violating the attempt budget.

## 9. Do not build

1. **A generic Razorpay chatbot or dashboard Q&A bot.** Razorpay already has conversational dashboard and assistant surfaces; natural language alone is not a product loop.
2. **A plain “smart retry scheduler.”** It duplicates Intelligent Retry and cannot credibly beat proprietary production intelligence with synthetic timing data.
3. **A direct Vulcan integration demo.** There is no public builder API/SDK. Mocking a Vulcan response and calling it integration is worse than omitting it.
4. **A multi-agent commerce workspace.** More agents add latency, handoff failure, and audit ambiguity without improving the authorization invariant. One agent plus an independent gate is easier to defend.
5. **A fine-tuned catalog model.** Catalog/price knowledge is dynamic; use retrieval plus deterministic truth. Fine-tuning is appropriate only for stable behavior/format alignment and is unnecessary here.
6. **A voice/WhatsApp receivables chaser as the core.** It is crowded by Agent Studio, vulnerable to TRAI consent/classification objections, and easy to reduce to a generic communications wrapper.
7. **A dispute auto-responder without a labeled held-out set.** Razorpay already markets one; a polished evidence packet without measurable completeness/win-proxy evaluation is weak.
8. **A route optimizer or false-decline model without authentic outcomes.** This is Vulcan's strongest territory and requires proprietary network features; synthetic uplift will not withstand questioning.
9. **A reconciliation agent demonstrated on five hand-picked rows.** Track 04 explicitly demands batch throughput, accuracy, and honest exceptions.
10. **An everything-agent combining checkout, retries, disputes, RTO, bookkeeping, and support.** It cannot show one loop deeply enough, and every additional actuator expands the unsafe surface.

## 10. Claims that must not appear unqualified

| Do not claim | Safe wording |
|---|---|
| “Powered by/integrated with Vulcan” | “Vulcan-aligned; designed to accept future advisory scores if access is granted.” |
| “Vulcan is an LLM” | “A proprietary transformer-based payments foundation model.” |
| “Vulcan improves success by 8–10%” as independent fact | “Razorpay reports an 8–10% improvement; public methodology is limited.” |
| “Razorpay MCP has 35 tools” as an exact current count | “The official repository listed 45 tools on 31 August; product docs say 35+.” |
| “MCP executes subscription/mandate retries” | “Recurring operations require REST/S2S, dashboard, webhooks, or a simulation adapter.” |
| “Test mode API lets us select failure” | “The test Subscriptions dashboard can charge a test cycle as success or failure.” |
| “One attempt plus three retries for the mandate's lifetime” | “One initial attempt plus three retries per mandate execution sequence/cycle.” |
| “₹15,000 is the maximum mandate amount” | “₹15,000 is the general no-AFA threshold for subsequent transactions under the framework.” |
| “Every retry message is promotional” | “Classification depends on content, consent, and purpose; mixed promotional content changes treatment.” |
| “₹0 chargeback liability” | “Zero unauthorized calls in the evaluated corpus; production liability is not measured.” |
| “Blocked value is recovered revenue” | “Blocked value is protected test-mode exposure.” |
| “Production-ready” | “Hackathon MVP with explicit production-hardening requirements.” |
| “Razorpay's AI checkout is generally available” | “Razorpay has announced pilots/private-beta agentic commerce experiences.” |
| “The Buildathon has a conventional winner/prize structure” | “The public program is a student hiring funnel; no prize mechanics are published.” |

## 11. Source and evidence ledger

| Claim area | Source | Class | Used for | Limitation |
|---|---|---|---|---|
| Buildathon tracks, bars, offer, rubric, deadline | [Razorpay Buildathon](https://razorpay.com/buildathon/) and [official application](https://docs.google.com/forms/d/e/1FAIpQLScJ9XSqVCB2oaPwEMH0Zk3I1OpILFW1WpWdWweQ2950jdRzlg/viewform?usp=send_form) | Primary | Track selection, evidence standard, time constraint | No public scoring weights, judge list, or result calendar; page/form contain a minor résumé-field mismatch. |
| Vulcan scope and production uses | [Razorpay article](https://razorpay.com/blog/?p=27542), [product page](https://razorpay.com/foundation-model/), [AWS-hosted Razorpay release](https://press.aboutamazon.com/aws-international/2026/8/razorpay-launches-vulcan-indias-first-ai-payments-foundation-model-fueled-by-nvidia-and-aws-re-architecting-payments-for-a-350-bn-e-comm-future-by-2030) | Primary/company release | Routing/fraud/personalization scope; alignment boundary | Impact numbers are company-reported; no public API does not prove no private access. |
| Agentic commerce pilots | [Claude pilot](https://razorpay.com/newsroom/?p=4701) | Primary | Why authorization is timely | Pilot/small-group context; do not imply general availability. |
| Agent control doctrine | [Agent Studio guardrails](https://razorpay.com/blog/razorpay-agent-studio-principles-guardrails-and-merchant-control/) | Primary | Scope, approval, kill switch, logging, consent, evaluation | Product doctrine, not formal Buildathon scoring. |
| Crowded Agent Studio categories | [Agent Studio](https://razorpay.com/agent-studio/) | Primary | “Do not build” and duplication analysis | Several agents are early access/beta. |
| Intelligent retry overlap | [Intelligent Revenue-Protect](https://razorpay.com/blog/upi-autopay-with-intelligent-revenue-protect/) | Primary | Retry Budget differentiation risk | Marketing statistics lack visible methodology. |
| MCP actions and gaps | [Official Razorpay MCP repository](https://github.com/razorpay/razorpay-mcp-server) | Primary/code | Native tool surface; 45-tool snapshot; no recurring actuator | Repository changes over time; date the count. |
| UPI retry budget/non-peak requirement | [NPCI circular](https://www.npci.org.in/PDF/npci/upi/circular/2025/UPI-OC-No-215-A-FY-2025-26-Guidelines-on-usage-of-UPI-APIs.pdf) and [mirror](https://avantiscdnprodstorage.blob.core.windows.net/legalupdatedocs/42884/NPCI-issued-guidelines-on-the-usage-of-UPI-API-May222025.pdf) | Primary plus mirror | Track 03 policy boundary | Exact clock intervals are hard to extract from the official PDF; consistently corroborated, but production policy still needs participant validation. |
| Current AutoPay execution layers | [NPCI AutoPay ecosystem statistics](https://www.npci.org.in/product/ecosystem-statistics/autopay) | Primary/live table | Avoid registration/remitter/PSP conflation | Monthly page changes; re-pull immediately before pitch. “Total Volume” unit is not shown beside the live table. |
| 24-hour notification/AFA | [RBI 2026 e-mandate framework](https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=13374&Mode=0) | Primary/regulatory | Track 03 notification gate and threshold correction | Prototype rules are not a substitute for legal/compliance review. |
| Test subscription behavior | [Test Subscriptions](https://razorpay.com/docs/payments/subscriptions/test/?preferred-country=IN), [Payment Retries](https://razorpay.com/docs/payments/subscriptions/payment-retries/?preferred-country=IN) | Primary/docs | Actuation/failure demo limits | Dashboard behavior is not proof of an API-selectable failure or NPCI timing policy. |
| Messaging classification | [TRAI TCCCPR amendment](https://www.trai.gov.in/sites/default/files/2025-02/Regulation_12022025.pdf), [Advice to Senders](https://www.trai.gov.in/advice-to-senders) | Primary/regulatory | Service versus promotional boundary | Apply with counsel/provider guidance to final templates/channels. |
| Existing Track 01 build | Local repo, current Git/test inspection; supplied build log | Internal/current | Feasibility and recommendation | Backend tests were verified; this research pass did not re-run every frontend, live-key, or browser check. |
| Indian AI market/capstone standards | Supplied August 2026 market note | Internal/supporting | Evaluation, RAG, observability context | Supporting context only; not used to override official Razorpay evidence. |

## 12. Immediate execution order

1. Freeze the Track 01 decision unless Retry Budget clears all challenger gates by 2 September.
2. Rename the product language and update the README/deck/UI consistently.
3. Build the adversarial plus benign evaluation harness; make the hard-safety gate part of CI.
4. Add or record one honest real Razorpay test-mode action; retain full offline demo mode.
5. Generate the evaluation report and exception list before visual polish.
6. Rehearse the four-minute arc and record a five-minute video with buffer.
7. Use the TOCTOU and idempotency evidence to satisfy Track 01's graceful-failure requirement; do not present it as a dedicated current application-form question.
8. Re-pull the official Buildathon page, MCP repository, and any monthly NPCI statistics immediately before submission.
9. Final-check the public repo for secrets, placeholders, stale “mandate” terminology, unsupported claims, and reproducibility.

The winning story is not “we built an autonomous buyer.” It is: **“We built the boundary that makes autonomous buying trustworthy, proved how it failed under concurrency, fixed it, and can certify that the AI never crosses it.”**
