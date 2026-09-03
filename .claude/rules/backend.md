---
paths:
  - "backend/**/*.py"
---

# Backend rules

- Keep `mandate.verify()` pure: no database, network, clock, or environment I/O.
- Represent money as integer paise. Reject floating-point money at boundaries.
- Keep `/chat` proposal-only. State-changing payment work begins only in the exact
  confirmation flow.
- Re-read current policy and account for live exposure inside the same write
  transaction that reserves headroom.
- Do not move idempotent replay handling behind a policy check that includes the
  attempt's own committed exposure.
- Bind grants to the full canonical action and purchase context. Reject extra,
  coerced, substituted, stale, expired, or mismatched values before transport.
- Preserve one-owner dispatch and dispatch-token fencing under concurrency.
- Release exposure only for a definitive failure. Preserve it for `UNKNOWN`.
- Database migrations must be additive for existing demo databases.
- Add deterministic tests for every authorization, lifecycle, migration, or
  concurrency change. Avoid LLM judges for safety invariants.
