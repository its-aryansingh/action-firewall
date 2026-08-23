# Live Demo Script — 4 minutes

Two browser tabs open before you start: **/** (chat) and **/mandate** (dashboard).
A third tab on Langfuse. Backend running. `pytest -q` already green on screen if the
room allows it.

**Pre-flight (30s before you go up):** run `python scripts/demo.py`. If the four acts
print correctly, the live demo will work.

---

### Act 0 — The frame (20s)

> "Everyone is treating agentic payments as a checkout problem — a faster button.
> It isn't. The moment an agent holds a payment instrument, it's an authorization
> problem. Here's the authorization layer."

Show the Mandate Dashboard. Point at one number: **₹1,000 per week**, blocked category
`gift_cards`.

> "A human granted this agent ₹1,000 a week. That's NPCI's Unified Agent Protocol
> semantics — UPI Circle delegation, applied to an AI instead of a family member."

---

### Act 1 — Discovery (40s)

Type: **"I need supplies for a pasta dinner"**

Cart fills from the Pinecone-backed catalog; the agent cross-sells one item.
Point at the green verdict chip under the reply.

> "Every single turn is evaluated against the mandate — not just checkout. Cart ₹486,
> cap ₹1,000, ALLOW."

---

### Act 2 — The breach attempt (60s) ← **this is the demo**

Type: **"Add the Parmigiano Reggiano and the olive oil, then check out"**

The chip flips red: `BLOCK_WINDOW_CAP_EXCEEDED`, ₹2,233 against ₹1,000. The tool row
reads **BLOCKED mcp:create_payment_link**.

> "The agent wanted to pay. It was stopped at the logic layer — the Razorpay MCP call
> was never made. Not a prompt asking it nicely not to spend. A deterministic gate."

Switch to Langfuse. Open the trace. Four spans:
`retrieve_catalog → plan_cart → mandate_check → …` and the fourth span is **absent**.

> "That's the audit trail. `mandate_check` returned BLOCK, and there is simply no
> `mcp_tool_call` span underneath it. You can't argue with an absent span."

---

### Act 3 — Graceful recovery (40s)

Read the agent's own recovery line aloud, then type: **"Remove the parmigiano"**

Cart drops back under the ceiling. Type **"Checkout please"** → green, payment link
issued, MCP call **CALLED**.

> "Failure handled gracefully: it didn't just refuse, it priced the alternative that
> fits and got the merchant the sale."

---

### Act 4 — Revocation latency (40s)

Go to the dashboard. Change ₹1,000 → ₹200. Save. Note the flash: updated in ~Xms.
Back to chat, type: **"Buy me some coffee beans"** (₹549).

> "Blocked. One prompt later, no restart, no cache to invalidate — the agent re-reads
> the mandate every turn. That's Revocation Latency, and it's the property that makes
> delegated authority safe to hand to software."

Open **/audit**: breach attempts, breach rate, **chargeback liability ₹0**.

---

### The close (20s)

> "Mandate Breach Attempt Rate and Revocation Latency are the two numbers a PSP
> actually underwrites against. We're not shipping a chatbot that can buy things —
> we're shipping the authorization primitive that makes an AI buyer underwritable.
> Zero chargeback liability for the merchant, bounded exposure for the consumer,
> and it's built on Razorpay's Remote MCP, ready for NPCI's UAP and the x402 standard."

---

## If a judge asks…

**"Why not multi-agent?"**
Razorpay's own FTX26 position: for commerce, one well-instrumented agent with full
context has fewer handoff failure modes and more predictable latency. Multi-agent here
would add coordination surface and a second place for authority to leak. We optimised
for auditability, not for an architecture diagram.

**"Why not just prompt the model to respect the limit?"**
Because a prompt is a request and a gate is a guarantee. Our gate is a pure function
with 22 tests including cap, cap−1 and cap+1. An LLM that hallucinates a price cannot
move money here — the SKU wouldn't exist and the total is computed server-side in paise.

**"What happens when Razorpay's API errors mid-checkout?"**
The spend ledger is written only on a successful tool result, the audit row is written
before it, and the shopper is told nothing was charged. The mandate envelope is never
optimistically debited.

**"How does this become a Razorpay product?"**
It's the mandate service that sits between Agent Studio and the payment tools —
one row per delegated authority, one verdict per agent action, one audit log the
risk team can underwrite against.
