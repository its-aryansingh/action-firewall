# Architecture Notes

## Why the gate is a pure function

`app/mandate.py:verify(cart, mandate, already_spent)` performs no I/O. It takes three
values and returns a `MandateDecision`. Everything stateful — loading the current
mandate, summing the spend window, writing the audit row — lives in
`verify_for_agent()`, a thin shell around it.

That split is what makes the property testable. The 22-test suite drives `verify()`
directly across the boundary cases (cap, cap−1, cap+1, prior spend, revoked, category,
quantity multiplication, empty cart) with no database and no mocking.

## The four-span trace

Each chat turn emits one Langfuse trace:

| Span | Input | Output | Why a judge cares |
|---|---|---|---|
| `retrieve_catalog` | shopper text | matched SKUs | proves discovery is grounded in the merchant catalog |
| `plan_cart` | text + retrieved | proposed cart ops | shows the LLM proposing, not deciding |
| `mandate_check` | cart total, SKUs | full decision object | the authorization verdict, with the numbers |
| `mcp_tool_call` | tool + args | Razorpay response | **absent on a blocked turn** |

The trace also carries a `mandate_respected` score (1.0 / 0.0), so breach attempts are
filterable and chartable in Langfuse over a whole demo session.

## Failure modes considered

| Failure | Handling |
|---|---|
| LLM proposes a SKU that doesn't exist | dropped in `_apply_ops`, never priced |
| LLM returns malformed JSON / API down | falls through to `_heuristic_plan`, demo continues |
| Pinecone unreachable | keyword retriever fallback, deterministic |
| Langfuse keys missing | `Trace` degrades to a no-op, agent unaffected |
| Razorpay MCP errors after an ALLOW | audit row written, no spend recorded, shopper told nothing was charged |
| Caller bypasses the gate | `mcp_client.call_tool` raises `MandateViolation` |
| Mandate edited mid-session | re-read every turn; `version` bumped; binds next prompt |

## Data model decisions

- **Integer paise, everywhere.** `unit_price_paise`, `cap_paise`, `amount_paise`.
  Rupees exist only at the presentation edge.
- **Append-only `audit_log`.** No updates, no deletes. A blocked attempt is as durable
  as a settled one — that is the difference between a log and evidence.
- **`spend_ledger` is separate from `audit_log`.** Money moved and money attempted are
  different facts and are queried differently.
- **One active mandate per (user, agent).** Issuing a new one supersedes rather than
  edits, so history survives.

## What would change for production

1. Mandate rows signed / stored with an HSM-backed key; the verdict becomes a signed
   attestation the PSP can verify independently of this service.
2. The spend window becomes a distributed counter with a reservation (two-phase:
   reserve headroom → call MCP → commit or release), so concurrent agent turns cannot
   both spend the last ₹100.
3. Idempotency keys on `create_payment_link`, keyed on `(mandate_id, cart_hash)`.
4. The x402 path: on HTTP 402 the agent settles inline via `capture_payment` — the same
   gate runs first, unchanged.
