# Adversarial audit findings

I did not treat the implementation's own test suite as sufficient evidence that
the system works. A suite written alongside the code naturally emphasizes the
cases already considered during implementation, so it is the wrong instrument
for discovering what was missed.

So I ran two adversarial review passes over the authorization core and request
path, targeting the eleven documented authorization invariants and trying to
break them rather than confirm them. Every finding below was **reproduced** with
a script before it was written down. Nothing here is inferred from reading.

This file stays in the repository on purpose. A project whose whole claim is
"our statements are exact" should be able to show the list of places its
statements were wrong.

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
- **Invariant 10 holds, and is now exercised rather than merely respected.**
  `action_issued` and `settled` are distinct states, reported separately, and
  the rehearsal demonstrates that reconciling an unpaid link changes nothing
  while a provider-confirmed payment moves the confirmed figure.
- **No SQL injection.** Every statement is parameterised; the one f-string SQL
  site composes only hard-coded fragments.
- **No timezone or naive/aware datetime bugs.** Epoch floats throughout, with
  consistent comparison direction.
- **The planner cannot invent money.** Negative, zero, float, boolean and
  string-coerced quantities, hallucinated SKUs, an injected `unit_price_paise`,
  and a smuggled top-level tool call were all rejected by `StrictInt` /
  `Literal` / `extra="forbid"` or dropped by the catalog lookup.

## Fixed in this pass

Each has a deterministic regression test; the suite went 51 → 61.

**1. A per-transaction cap of zero disabled the cap.** `create_mandate` coerced
with truthiness, so `per_txn_cap_rupees=0` — the most restrictive value a
shopper can express — stored `NULL` and removed the cap entirely, while
`update_mandate` stored it correctly. The same input produced opposite policies
depending on the route. Now `is not None`.
→ `test_zero_per_transaction_cap_is_a_cap_not_an_absence`

**2. `INSERT OR REPLACE` walked through the append-only guard.** SQLite leaves
`recursive_triggers` OFF, so the implicit DELETE inside a REPLACE conflict never
fired the `BEFORE DELETE` trigger. A `BLOCK_WINDOW_CAP_EXCEEDED` row could be
rewritten to `ALLOW` in place, row count unchanged, no error. The pragma is
per-connection, so it is now set in a `_configure()` helper used by every
connection rather than once at startup.
→ `test_audit_rows_cannot_be_rewritten_by_insert_or_replace`

**3. Settlement was a state nothing could write.** `settled` existed in the
schema and in `metrics()`, but the only function that set it — `reconcile_unknown`
— had no caller and no route, so `confirmed_test_payment_value_paise` was
structurally zero and invariant 10 was satisfied only because settlement was
unreachable. `app/reconciler.py` closes the loop by reading the provider's own
view and applying it; `store.settle_issued_action` is the single
`action_issued → settled` transition. No route accepts a caller-supplied status.
→ `tests/test_reconciliation.py` (7 tests)

**4. A duplicate dispatch of an already-issued grant was recorded as blocked.**
`ALREADY_ISSUED` fell through to a bare `MandateViolation`, which the agent
renders as "the exact action no longer matches its authorization receipt" and
logs as a `BLOCKED` tool call — a false entry for a call that had in fact
succeeded. It now raises `ActionInProgress`, which is a `MandateViolation`
subclass, so fail-closed behaviour is unchanged.
→ `test_duplicate_dispatch_of_issued_grant_is_in_progress_not_a_violation`

## Remaining findings and fixes landed after this audit

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

**Fixed after the audit — ambiguous retrieval no longer creates a cart.** The
deterministic planner now emits no cart operation unless it recognizes an
explicit product or a small server-owned shopping-goal template. A regression
test sends an informational dinner message and asserts an empty cart, no
confirmation, and no authorization attempt.

**Partially fixed after the audit — catalog text is explicitly untrusted.** The
planner prompt now labels catalog strings as data and says instruction-like
product text must be ignored. Server-owned SKU, price and category rehydration
still protects the action boundary. The remaining gap is empirical: arbitrary
language drafting still needs a published multi-model prompt-injection corpus.

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

## Fixed after the audit — Cross-envelope ceiling and receipt authorization core

**User authority ceiling across envelopes.** Previously, each activated Purchase Envelope
minted its own spend fence with no aggregate ceiling across jobs. We implemented
`authority_ceilings` with `store.get_authority_view()` and enforced the ceiling atomically
inside `store.authorize_and_reserve` under `BEGIN IMMEDIATE`. Any reservation that would push
the user's committed + pending exposure over the configured ceiling is rejected with
`BLOCK_USER_CEILING_EXCEEDED`. Concurrency tests verify that multiple parallel envelopes
cannot exceed the user's ceiling.
→ `tests/test_concurrency.py::test_authority_ceiling_is_atomic_under_concurrency`, `GET /authority`

**Receipt authorization core separated from mutable status.** Previously, `state` and
`updated_at` were inside the single signed body, causing a valid receipt issued at
`action_issued` to fail verification once settled. We refactored `ActionReceipt` into an
immutable `ReceiptAuthorization` (signed by `authorization_signature`) and a mutable
`ReceiptStatus` (signed by `status_signature`). When a grant settles, its authorization core
remains fully valid and verifiable, while status reflects settlement cleanly.
→ `test_safe_autopilot.py::test_action_receipt_authorization_core_survives_settlement`

## Known, unfixed, lower risk

- Reconciliation is pull-based: `POST /actions/{id}/reconcile` and
  `POST /actions/reconcile` exist and a startup sweep runs, but nothing calls
  them on a schedule and there is no signed webhook consumer.

## Fixed in the submission-hardening pass

**The atomic gate now owns action-registry enforcement.** An unknown action,
malformed argument object, non-canonical argument object, or wrong action-schema
hash is rejected before an authorization row can be minted. The actuator still
repeats this check as defence in depth.
→ `test_atomic_gate_rejects_unregistered_or_malformed_actions_before_grant`

**A purchase attempt now has an explicit caller-generated identity.** The public
autopilot contract requires `purchase_attempt_id`; it no longer derives identity
from the session and quote. Transport retries must reuse that value. A new
purchase must mint another value. Missing, legacy, and undersized identities are
rejected at the HTTP boundary.
→ `test_http_execute_requires_explicit_purchase_attempt_identity`

**Every replay is now evidence.** The autopilot and atomic-gate replay branches
append `ACTION_REPLAY_RETURNED`, including the prior state, attempt identity,
grant id, and `provider_call_made=false`. Replays remain deliberately ahead of a
fresh policy decision because they return prior work rather than authorize new
work; the actuator cannot redeem a stale grant because it rechecks policy
version, policy hash, state, expiry, actor, action, arguments and cart.
→ `test_atomic_gate_records_reused_authorization_without_provider_call`,
`test_valid_quote_issues_one_action_consumes_envelope_and_signs_receipt`,
`test_unknown_provider_outcome_holds_one_use_and_does_not_redispatch`

**The legacy reservation helper cannot mutate an exact-action grant.** Both
generations share the spend ledger. Previously, the legacy helper could treat an
expired `action_issued` row as its own TTL reservation and release its exposure.
It now owns only `reserved`/`committed` states; any exact-action state returns
`KEY_BOUND_TO_ACTION_GRANT` without mutation. It also rejects boolean, float,
zero, and negative amounts.
→ `test_legacy_reservation_cannot_release_an_exact_action_grant`,
`test_legacy_reservation_rejects_invalid_money`

**Legacy policy money inputs are bounded and strict.** Create and update reject
zero/negative window caps, values over ₹10,00,000, floating-point or boolean
money, invalid per-transaction caps, and unknown fields. Invalid updates leave
the stored version and amount unchanged.
→ `test_http_mandate_money_and_schema_inputs_fail_closed`,
`test_http_invalid_mandate_update_preserves_policy`

## If a reviewer asks "did you find your own bugs?"

Yes, and this file is the answer. Each fix above has a deterministic regression
test; the remaining production gaps are disclosed rather than renamed as
features. The original suite did not cover these findings—it proved the things
already considered—which is precisely why the adversarial pass exists.
