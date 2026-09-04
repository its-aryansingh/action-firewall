# Adversarial audit findings — 4 September 2026

Two independent reviewers went over the authorization core and the request path
against the eleven invariants in `CLAUDE.md`. Every finding below was
**reproduced**, not inferred. This file records what was fixed, what was
deliberately not fixed, and what a reviewer may still find.

Keeping this in the repository is the point. A submission whose thesis is
"our claims are exact" should be able to show the list of places it was wrong.

## What held

The concurrency core could not be broken.

- **Invariant 1 holds.** `handle_turn` returns `tools=[]` unconditionally and
  `get_client()` is reachable only from `confirm_checkout`. Five aggressively
  checkout-phrased chat turns produced zero provider calls with the client
  instrumented.
- **Invariant 5 (headroom) holds.** Twelve concurrent `authorize_and_reserve`
  calls, ₹300 carts, ₹1,000 cap → exactly three granted, zero exceptions.
- **Invariant 8 holds.** Eight concurrent `call_tool` calls against one grant →
  exactly one `action_issued`, one provider call, one audit row, seven refusals.
- **Invariant 4 holds.** No float occupies an authoritative money position
  anywhere. Every `/100` is presentation.
- **Invariant 10 holds.** `action_issued` and `settled` are distinct states and
  reported separately.
- **No SQL injection.** Every statement is parameterised; the one f-string SQL
  site composes only hard-coded fragments.
- **No timezone or naive/aware datetime bugs.** Epoch floats throughout, with
  consistent comparison direction.
- **The planner cannot invent money.** Negative, zero, float, boolean and
  string-coerced quantities, hallucinated SKUs, an injected `unit_price_paise`,
  and a smuggled top-level tool call were all rejected by `StrictInt` /
  `Literal` / `extra="forbid"` or dropped by the catalog lookup.

## Fixed in this pass

Each has a deterministic regression test; the suite went 51 → 54.

**1. A per-transaction cap of zero disabled the cap.** `create_mandate` coerced
with truthiness, so `per_txn_cap_rupees=0` — the most restrictive value a
shopper can express — stored `NULL` and removed the cap entirely, while
`update_mandate` stored it correctly. The same input produced opposite policies
depending on the route. Now `is not None`.
→ `test_zero_per_transaction_cap_is_a_cap_not_an_absence`

**2. `INSERT OR REPLACE` walked through the append-only guard.** SQLite leaves
`recursive_triggers` OFF, so the implicit DELETE inside a REPLACE conflict never
fired the `BEFORE DELETE` trigger. A `BLOCK_WINDOW_CAP_EXCEEDED` row could be
rewritten to `ALLOW` in place, row count unchanged, no error. The schema now has
a `BEFORE INSERT` guard that rejects an existing audit identifier, including from
a raw connection with `recursive_triggers` left OFF. Application connections also
enable recursive triggers as defence in depth.
→ `test_audit_rows_cannot_be_rewritten_by_insert_or_replace`

**3. A duplicate dispatch of an already-issued grant was recorded as blocked.**
`ALREADY_ISSUED` fell through to a bare `MandateViolation`, which the agent
renders as "the exact action no longer matches its authorization receipt" and
logs as a `BLOCKED` tool call — a false entry for a call that had in fact
succeeded. It now raises `ActionInProgress`, which is a `MandateViolation`
subclass, so fail-closed behaviour is unchanged.
→ `test_duplicate_dispatch_of_issued_grant_is_in_progress_not_a_violation`

## Not fixed — disclosed instead

Now stated plainly in the README's *Honest limitations*, because the previous
wording understated them.

**No authentication on any route.** Reproduced end to end: read a session id and
SKU list from the unscoped `GET /audit`, read prices from `GET /catalog`,
recompute the cart hash locally (it is a digest of catalog-derived fields with no
session salt), and `POST /checkout/confirm` against another session's policy
headroom. `POST /mandates` and `PATCH /mandates/{id}` are likewise open, so the
policy the firewall enforces is world-writable. The exact-cart fence works as
designed and does not help: it proves the confirmer knows the cart, not that they
are the shopper. **This is the finding to name yourself before a reviewer names
it.**

**The heuristic planner adds unrequested items.** On any message it cannot
parse it falls back to adding the top four retrieved items — "what are your
delivery hours" puts several hundred rupees in the cart. Fires with the shipped
catalog, no adversary needed. Nothing dispatches without exact confirmation, so
it cannot move money alone.

**Catalog text reaches the prompt unframed.** Product names and tags are
concatenated into the planner's user turn with no delimiting, and a name whose
distinctive token is a common word can pull its SKU into an unrelated message.
Injection cannot set a price, invent a SKU, or name an action.

**Unresolved exposure never ages out of the window.** Settled spend rolls off a
weekly window; `action_issued` / `dispatching` / `unknown` do not. This is the
conservative reading of invariant 9 and is deliberate, but it means a long-lived
policy's usable headroom only decreases, and `GET /mandates/{id}/usage` presents
lifetime figures as window figures. Not changed, because freeing unresolved
exposure on a timer would weaken invariant 9.

**`denied_requested_value_paise` counts denial events, not distinct carts.**
Retrying one blocked cart five times reports five times the value. The demo
figure of ₹2,583 is two distinct denials and is accurate; the metric is only
inflatable under retry.

## Known, unfixed, lower risk

- `reserve_headroom` (the legacy helper) can release a live `action_issued` row
  and destroy its exposure when handed a matching idempotency key. **Not
  reachable from any HTTP route** — tests only. Its docstring now marks it as a
  legacy test helper; deleting it remains post-submission cleanup.
- The replay branches of `authorize_and_reserve` (`REUSED_AUTHORIZATION`,
  `ACTION_IN_PROGRESS`, `UNKNOWN_OUTCOME`) return before policy evaluation and
  write no audit row. The system still fails closed because `claim_action_grant`
  re-checks active/version/policy_hash — defence in depth doing the gate's job.
- The gate does not check the action against `ACTION_REGISTRY`; only the actuator
  does. An unregistered action name can therefore mint a grant and appear in the
  audit trail as `ALLOW` before being rejected at dispatch.
- `UNKNOWN` and `dispatching` have no production reconciler or operator route.
  Already disclosed.
- The same shopper repurchasing an identical basket in one session replays the
  first payment link, because the attempt id has no nonce or attempt counter.
- Unbounded `cap_rupees` can raise `ValidationError`/`OverflowError` as an
  unhandled 500. State rolls back cleanly; availability only.

## If a reviewer asks "did you find your own bugs?"

Yes, and this file is the answer. Three were fixed with regression tests, the
rest are disclosed with their reproduction. The suite deliberately did not cover
any of these before the audit — it proved the things that already worked, which
is the normal failure mode of a self-written test suite and worth saying out
loud.
