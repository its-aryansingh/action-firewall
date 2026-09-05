# Market context — Razorpay AI Buildathon 2026

**Research cut-off:** 5 September 2026
**Purpose:** supporting evidence for Action Firewall. This file is not a payment,
regulatory, or integration specification. The implementation and architecture
documents remain authoritative for what the repository actually proves.

## Evidence labels

- **[First-party]** Razorpay, NPCI, RBI, or a Razorpay-owned source.
- **[Internal proof]** behavior reproduced by this repository's tests or
  disposable demo.
- **[Secondary]** reporting or analysis outside the relevant first party.
- **[Inference]** a product or strategy conclusion drawn from evidence.
- **[Unconfirmed]** a claim that could not be established from an operative,
  current primary source.

## Decision summary

**[Internal proof, 5 September] Safe Autopilot Checkout is now implemented.**
The original exact-cart flow remains at `/baseline`. The primary path adds a
shopper-activated Purchase Envelope, deterministic catalog-fact rehydration,
in-envelope stock-loss recovery, field-level Policy Deltas, atomic one-purchase
reservation, envelope-bound Action Grants, application-signed receipts, and a
provider-mode-labelled UI. The current verified evidence is 76 passing backend
tests, a 400-case synthetic authorization corpus with zero failures in its stated
scope, two disposable offline rehearsals, a successful frontend production
build, and zero vulnerabilities reported by the current npm audit. These are
repository results, not production or regulatory evidence.

**[Inference] Action Firewall remains the primary Track 01 submission.** The
published Track 01 bar asks for explainable, bounded, gated money actions, an
audit trail, and one graceful failure. Those requirements map directly to the
current implementation and can be demonstrated without inventing private data
or proprietary model access.

**[Inference] Retry Budget remains a secondary Track 03 challenger.** Track 03
does name failed-subscription recovery and mandate retry sequencing, but it also
requires measured money recovered across a batch, compliant escalation, stopping
rules, and an audit trail. Razorpay already documents automatic Smart Payment
Retries, and no dedicated public retry-sequencing control surface appears in the
current MCP tool list. The challenger therefore has more overlap, more
integration work, and a higher evidence burden than the existing build.

## What Razorpay currently asks builders to prove

**[First-party]** The [Razorpay AI Buildathon page](https://razorpay.com/buildathon/)
describes a student hiring program in which applicants pick a track, build a
working product, and show a public repository, a five-minute pitch video, and
the architecture.

For Track 01, the page says builders should grow a merchant's revenue or make a
merchant transactable by an AI buyer using Razorpay test-mode APIs. Its stated
bar is unusually precise: every money action must be explainable, bounded, and
gated, with an audit trail and one failure handled gracefully.

For Track 03, the page explicitly includes failed-subscription recovery and a
mandate retry sequencer, but its bar is different: measured money recovered over
a batch, compliant escalation, stopping rules, and an audit trail.

**[First-party, time-sensitive]** The landing page says the internship starts
“from September” but does not publish an application deadline. No third-party
deadline should be presented as confirmed without a current official form or
announcement.

## Agentic-commerce direction

**[First-party]** Razorpay's
[Agentic Payments product page](https://razorpay.com/agentic-payments/) frames
commerce as moving from clicks to conversations and publicly emphasizes
pre-authorized spending limits, real-time visibility, authentication,
compliance, and granular control. On the page rechecked on 4 September 2026,
in-app commerce is labelled beta, UPI Reserve Pay is labelled live, and UPI
Circle is labelled coming soon. These are distinct product statements and must
not be collapsed into one protocol claim.

**[First-party]** Razorpay's
[NPCI and OpenAI agentic-payments announcement](https://razorpay.com/newsroom/razorpay-npci-and-openai-come-together-to-launch-agentic-payments-ushering-in-ai-driven-commerce-at-national-scale/)
describes a catalog-to-order example that proceeds after one confirmation and
emphasizes real-time tracking and instant revocation. It describes a pilot and
does not grant this project access to its payment credentials, private rails, or
partner systems.

**[Inference]** Action Firewall is therefore best presented as an
application-layer complement: the AI proposes a useful transaction, while a
separate deterministic boundary controls whether one exact Razorpay action is
authorized. It is not an announced Razorpay product and should not be described
as endorsed by Razorpay.

## Vulcan: precise positioning

**[First-party]** Razorpay's 18 August 2026 article,
[One Foundation Model, Built for India's Payments Ecosystem](https://razorpay.com/blog/?p=27542),
positions Vulcan as a proprietary payments foundation model for reliability,
safety, and predictability. The disclosed production functions are:

- real-time route scoring;
- network-level fraud detection;
- payment-method recommendation;
- checkout and offer personalization.

The article says the model architecture and training data are proprietary. It
does not document customer policy enforcement, exact action grants, agent-tool
gating, or application audit receipts.

**[First-party negative finding]** No public Vulcan API, SDK, inference endpoint,
sandbox, authentication guide, or Buildathon entitlement was found in the
first-party material reviewed. A negative search cannot prove that private
interfaces do not exist; it does establish that this public student submission
must not claim them.

**Allowed wording:** “Vulcan can improve payment decisions; Action Firewall
determines whether this agent is authorized to invoke the payment action.”

**Prohibited wording:** “powered by Vulcan,” “integrated with Vulcan,” or “uses
the Vulcan API.”

## Razorpay MCP and the action boundary

**[First-party]** Razorpay's
[MCP documentation](https://razorpay.com/docs/mcp-server/tools-reference/) says
the server exposes 35+ tools, while the current Agentic Payments marketing page
says 40+ composable tools and APIs. The
[official MCP repository](https://github.com/razorpay/razorpay-mcp-server)
enumerated 45 tools when rechecked on 3 September 2026, including
`create_payment_link` with Remote support. The count is a changing snapshot,
not a product guarantee, and the differently scoped public counts should not be
collapsed into one claim or made central to the pitch.

**[First-party]** The
[Remote MCP setup](https://razorpay.com/docs/mcp-server/remote/) uses the
`https://mcp.razorpay.com/mcp` Streamable HTTP endpoint. Merchant-key setup uses
`Authorization: Basic base64(key_id:key_secret)`; OAuth integrations use
Bearer access tokens. These modes should not be conflated.

**[Inference]** The large MCP surface is exactly why an application should not
pass arbitrary model-selected tool names through to a payment provider. Action
Firewall intentionally registers one action, `create_payment_link`, with a
strict schema and exact grant binding. That is a conservative MVP boundary, not
a claim that Razorpay exposes only one consequential tool.

## Payment-link lifecycle

**[First-party]** Razorpay's
[Payment Link guide](https://razorpay.com/docs/payments/payment-links/create/)
says a newly created link moves to an issued state. Its
[Payment Link state guide](https://razorpay.com/docs/payments/payment-links/states/)
separates the initial link state from paid. The API reference sometimes uses
`created` for the initial response, so the public vocabulary is not completely
uniform.

**Implementation rule:** use the internal semantic `ACTION_ISSUED`, retain any
raw provider state, and never translate link creation into “paid,” “captured,”
“settled,” or “recovered revenue.” A later signed webhook or authoritative fetch
must establish payment completion.

## Why Retry Budget does not displace the current build

**[First-party]** Razorpay already documents
[Smart Payment Retries](https://razorpay.com/docs/payments/subscriptions/payment-retries/)
for failed subscription charges. The current published MCP surface has
saved-method and token-related tools, but no dedicated subscription-recovery or
retry-sequencing tool.

**[First-party]** Razorpay test mode can simulate subscription charge outcomes,
which is useful for a demo. It does not by itself expose a programmable
retry-scheduling control plane or prove incremental recovery.

**[First-party]** NPCI and RBI material support a scoped 24-hour pre-debit
notification requirement for recurring debits.

**[Unconfirmed]** This research did not recover an operative primary circular
that established both the previously claimed “one execution plus three UPI
AutoPay retries” rule and the exact non-peak execution windows. The alleged
21 April 2026 consolidated RBI framework was also not recovered from RBI's
public search surface. These claims stay out of judge-facing material until the
operative primary documents are attached.

**[Inference]** Retry Budget would replace Action Firewall only if it produced:

1. a publishable synthetic batch and generator;
2. verified notification and retry-policy constraints;
3. a real control surface for idempotent execution;
4. incremental recovery against a fixed-schedule baseline and an oracle;
5. variance across held-out seeds;
6. a sharper, more reliable failure demo than Action Firewall's concurrency and
   ambiguous-dispatch evidence.

It does not currently meet that threshold.

## Repository proof at this research cut-off

**[Internal proof]** The implementation now has:

- proposal-only chat and separate exact-cart confirmation;
- atomic full-policy authorization and headroom reservation;
- version/hash fencing against policy changes;
- exact one-use grants bound to actor, session, cart, action, arguments, amount,
  currency, policy revision, and purchase-attempt identity;
- a closed `create_payment_link` registry;
- one-owner dispatch under concurrency;
- explicit `ACTION_ISSUED`, `SETTLED`, `DEFINITIVE_FAILURE`, and `UNKNOWN`
  states;
- no automatic redispatch after an ambiguous provider outcome;
- database guards that reject updates, deletes, and duplicate-ID replacement of
  application audit events;
- deterministic offline model, retrieval, and actuator fallbacks.

The final verification on 4 September 2026 produced 54/54 passing backend tests,
a successful frontend production build, zero reported npm vulnerabilities, and
three consecutive successful offline rehearsals. A separate fresh clone of the
pushed repository reproduced the 54 tests, demo, build, and dependency audit.
Internal proof is evidence of implementation behavior, not evidence of production
revenue, regulatory compliance, or a live Razorpay payment.

## Claim discipline

Use these phrases:

- “shopper-defined application policy”;
- “exact, one-use action grant”;
- “payment-link value issued”;
- “confirmed payment requires verified provider state”;
- “append-only application event log”;
- “Razorpay MCP-compatible actuator” or “Razorpay Remote MCP in configured
  test mode”;
- “Vulcan is strategic context, not a dependency.”

Avoid these phrases:

- “NPCI-compliant mandate”;
- “zero chargeback liability”;
- “settled” immediately after link creation;
- “cryptographically immutable audit”;
- “production identity”;
- “all MCP tools are supported”;
- “Vulcan-powered authorization”;
- any unconfirmed deadline, retry cap, or execution window.

## Source ledger

| Source | Publisher | Visible date | Use | Access note |
|---|---|---:|---|---|
| [Razorpay AI Buildathon](https://razorpay.com/buildathon/) | Razorpay | not shown | tracks, bar, deliverables | rechecked 4 Sep 2026; no deadline shown |
| [Razorpay Agentic Payments](https://razorpay.com/agentic-payments/) | Razorpay | not shown | product status and control language | rechecked 4 Sep 2026; labels are time-sensitive |
| [Agentic Payments announcement](https://razorpay.com/newsroom/razorpay-npci-and-openai-come-together-to-launch-agentic-payments-ushering-in-ai-driven-commerce-at-national-scale/) | Razorpay Newsroom | 30 Oct 2025; page updated 15 Jun 2026 | confirmation, tracking, revocation, pilot scope | reviewed 2 Sep 2026 |
| [Vulcan foundation-model article](https://razorpay.com/blog/?p=27542) | Razorpay | 18 Aug 2026 | disclosed Vulcan positioning and functions | rechecked 4 Sep 2026 |
| [MCP tools reference](https://razorpay.com/docs/mcp-server/tools-reference/) | Razorpay Docs | not shown | documented tool families | rechecked 4 Sep 2026 |
| [Official Razorpay MCP repository](https://github.com/razorpay/razorpay-mcp-server) | Razorpay | live repository | dated tool snapshot and Remote support | rechecked 3 Sep 2026 |
| [Remote MCP setup](https://razorpay.com/docs/mcp-server/remote/) | Razorpay Docs | endpoint change effective 13 Aug 2025 | transport and merchant-key authentication | reviewed 2 Sep 2026 |
| [Create a Payment Link](https://razorpay.com/docs/payments/payment-links/create/) | Razorpay Docs | not shown | initial issued state and test-mode guidance | reviewed 2 Sep 2026 |
| [Payment Link states](https://razorpay.com/docs/payments/payment-links/states/) | Razorpay Docs | not shown | issued versus paid lifecycle | reviewed 2 Sep 2026 |
| [Subscription payment retries](https://razorpay.com/docs/payments/subscriptions/payment-retries/) | Razorpay Docs | not shown | existing Smart Payment Retries overlap | reviewed 2 Sep 2026 |

## Research stop condition

Discovery stopped when the primary Track 01 decision was supported by current
Razorpay sources, Vulcan and MCP access boundaries were explicit, payment-link
state semantics were reconciled, and the Track 03 challenger had a documented
product-overlap and evidence-gap analysis. Additional secondary market estimates
would not change the build decision and are intentionally excluded.
