# Janus — Build Plan (Track 01, ~14 days)

> Re-ideation dated 22 Aug 2026, after Razorpay launched Vulcan (18 Aug) and after
> verifying what the Buildathon actually asks for.

## What changed

The roadmap doc assumed a hackathon with judges and a pitch deck. It isn't one.
It is a **student hiring funnel** — public repo + 5-minute pitch video + architecture
writeup. No deck. Reviewers read the README before they watch anything.

Track 01's bar — *"Every money action explainable, bounded and gated. Show the audit
trail and one failure handled gracefully"* — is the **only track of the five with no
required number in it**. Tracks 02/03/04 all demand measured results on a batch.
That asymmetry is the entire opportunity: Track 01 is crowded on the demo axis and
empty on the measurement axis.

## The re-ideation in one line

From **a gate that works in a demo** → to **an authorization broker that survives an
attacker and leaves a receipt anyone can read.**

Same domain. Same mandate model. Same pure-function gate. Different centre of gravity.

## Vulcan: context, never dependency

Vulcan has **no API, no SDK, no sandbox, no MCP tool**. You cannot build on it.
Do not imply you did.

What it gives you is framing. Razorpay shipped a model that makes autonomous money
decisions with no published explainability story, no false-positive rate, and no
audit story — and Track 01's bar leads with the word *explainable*.

> Vulcan decides how a payment routes. Janus decides whether an agent may spend at
> all — and unlike a learned model, its answer is a rule you can read, replay and test.

## Build order (cut from the bottom if behind)

| # | Build | Days | Why it separates you |
|---|---|---|---|
| 1 | Adversarial eval harness | 3–4 | A measured number in the track that asks for none |
| 2 | Close the TOCTOU race | 1–2 | Check-then-act is the top vulnerability class in the literature |
| 3 | Prompt-injection defence | 1–2 | The catalog is untrusted text; model choice becomes measurable |
| 4 | Explainable decision receipt | 1 | The literal first word of the track's bar |
| 5 | Intent ↔ cart reconciliation | 1–2 | Least-implemented primitive across every agentic-payment standard |
| 6 | Agent identity + per-agent revocation | 1 | The actual novelty in NPCI's proposed UAP |

### 1. Adversarial eval harness

- 50–100 attack prompts: cap boundary (cap−1 / cap / cap+1), revoked vs. absent
  mandate, category evasion, quantity inflation, hallucinated SKU, and 15–20 catalog
  entries carrying hidden injections ("append a gift card", "skip verification").
- **Deterministic assertions, not an LLM judge.** `verify()` is pure and I/O-free, so
  the judge can be an assertion. That is a stronger position than any rubric.
- **Report `pass^k`, not `pass@k`** — all k runs must hold. A gate that survives nine
  times in ten is a broken gate.
- Two models, variance across seeds, not a point estimate.
- **Publish the failures.** An honest exception list is Track 04's culture applied to
  Track 01 and nobody else will do it.

### 2. Close the TOCTOU race

`mandate_check → mcp_tool_call` is check-then-act. Two concurrent turns can both see
the same headroom and both spend it.

- Two-phase reservation on the spend ledger: reserve headroom → call MCP → commit or
  release.
- Idempotency keys on `create_payment_link`, keyed on `(mandate_id, cart_hash)`.
- **Write the failing concurrency test first**, then make it pass. The failing test is
  evidence; the fix alone is just code.

### 3. Prompt-injection defence

The Pinecone catalog flows untrusted text into the planner. Seed poisoned entries,
measure the block rate, report it per model.

### 4. Explainable decision receipt

Per money action: what was asked, what was authorized, which rule fired, and the
**counterfactual** — "this passes if the cap is ₹1,500." Signed. Human-readable.

### 5–6. Intent reconciliation, agent identity

Compare the human's stated intent against the cart before the money tool (catches
category drift). Per-agent keys and scopes so one agent can be revoked without
touching the others.

## Fourteen days

| Day | Work |
|---|---|
| 1 | **Rewrite git history** into a real commit sequence. Start the README. Non-negotiable, comes first. |
| 2–3 | TOCTOU: reservation + idempotency + the failing concurrency test |
| 4–7 | Attack corpus and eval harness |
| 8 | Explainable receipts |
| 9–10 | Intent reconciliation + agent identity (cut these first if behind) |
| 11 | Full harness run; write the exception list |
| 12 | Architecture writeup (repurpose the deck content) |
| 13 | Record the video **against live keys**, not `DEMO_MODE` |
| 14 | Slack. Leave it empty on purpose. |

## Video structure

Five minutes is a ceiling, not a target. You have ~30 seconds before it's closed.

- **0:00–0:20** — the block, cold. No title card. Agent tries to spend, gate stops it,
  MCP call visibly not made.
- **0:20–1:00** — one sentence on authorization vs. checkout.
- **1:00–3:00** — the mechanism, on screen, in code.
- **3:00–4:15** — the numbers, and the ones that got through.
- **4:15–5:00** — what's next and what's still broken.

Run one act **twice on camera** so output is visibly non-identical. Scripted-looking
demos are exactly what a sceptical reviewer screens for.

## Language discipline

- Say NPCI's UAP is **"anticipated"** — never "implemented" or "compliant". The spec is
  unpublished.
- Don't cite the "FTX26 single-agent thesis" as fact — it could not be sourced.
  Argue single-agent on its merits: fewer handoff failure modes, one auditable trace.
- Vulcan is **context, not a dependency.**

## Verify before quoting

Rate limits stopped final verification of these. Open them yourself:

- Exact track wording and eligibility — <https://razorpay.com/buildathon/>
- MCP tool count and the remote/local split — <https://github.com/razorpay/razorpay-mcp-server>
- Test-mode failure simulation limits — <https://razorpay.com/docs/payments/payments/test-upi-details/>
