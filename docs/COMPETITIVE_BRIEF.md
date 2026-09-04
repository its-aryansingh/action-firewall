# Competitive brief — the nearest public entry

Read in full on 4 Sept 2026: `github.com/srikrishna0603/razorpay-buildathon`,
"Revenue Resilience AI". This is the only public buildathon repo whose thesis
overlaps ours. It is **Track 03**, not Track 01.

Written to sharpen our own framing. Nothing here is to be copied, and nothing here
belongs in the video as a comparison — a submission that talks about another
submission looks small.

---

## What they built, accurately

A deterministic recovery engine for failed payments. Their framing, verbatim:

> "We strictly sandbox the LLM, stripping it of all execution authority… The LLM
> proposes *why* a failure occurred. The Policy Engine decides *if and how* to act.
> The Database guarantees it happens exactly once."

Their four code-enforced invariants:

1. **At-most-once execution** — an atomic SQLite WAL `PENDING` lock taken before
   the LLM runs.
2. **Economic floors** — abort if the transaction is below a fixed cost threshold.
3. **No LLM decisioning** — the model emits a `DiagnosisClass`; the engine maps it
   deterministically to `RETRY` / `OFFER_ALTERNATE_METHOD` / `STOP_AND_ESCALATE` /
   `NO_ACTION`.
4. **Primary-key idempotency** — the executor writes `razorpay_ref` against a PK on
   `event_id`, so the database physically rejects a double-charge even if the code
   loops.

Three adversarial scenarios: concurrent webhooks (10 simultaneous, one wins),
stale reservation (crash mid-evaluation, lock swept), duplicate executor (network
drop before dispatch).

**Their evaluation harness is the strongest thing they have, and it is genuinely
good.** Chronological 70/30 split; ground-truth labels (`is_synthetic_incident`,
`incident_type`) structurally stripped before the agent sees an event; four policies
compared — No Action, Blind Retry, Deterministic Rule Baseline, Agent; net value
accounted as gross contribution minus retry cost, friction penalty and escalation
cost; false interventions counted separately; deterministic pseudo-randomness keyed
on `event_id` so runs reproduce; and a **sensitivity analysis** varying the friction
penalty. There is an explicit `Limitations` docstring.

Respect that. It is better measurement discipline than most professional work.

---

## Why this does not threaten our submission

**Different track, different bar.** Track 03 demands *measured money recovered
across a batch*. Track 01 demands *every money action explainable, bounded and
gated, with an audit trail and one failure handled gracefully*. Their harness answers
their bar. Our invariants answer ours. We are not competing for the same slot, and
we should not try to out-measure a project whose bar is measurement.

**The deeper difference is what "safe" means.** Their guarantee is *at-most-once
execution*. Ours is *bounded authority*. Those are not the same claim:

- Executing once does not constrain **what** is executed. Their executor obeys a
  `DiagnosisClass → action` mapping, but nothing binds the *arguments* of the
  dispatched call to anything a human approved. A lock answers "how many times";
  a grant answers "what, exactly, and under whose authority".
- They have **no human confirmation step** — their trigger is a webhook. So a stale
  approval, a cart that changed after approval, or an amount edited between approval
  and dispatch are not failure modes their design has to survive. That gap is the
  entire middle of our system.
- Their stale-reservation sweep **frees** the abandoned lock and degrades to
  `STOP_AND_ESCALATE`. Ours does the opposite: an ambiguous outcome becomes
  `UNKNOWN` and **keeps consuming headroom**. Both are defensible engineering; ours
  is the more conservative choice about money, and we can say why in one sentence.

---

## The four differentiators already have named tests

This is the important finding. Nothing needs to be built — it needs to be *shown*.
Every claim in the video is already a test name in `tests/test_action_firewall.py`:

| Differentiator | Test that proves it |
|---|---|
| Exact confirmation; approval dies when the cart changes | `test_same_attempt_different_binding_is_conflict` |
| Grant bound to a policy revision | `test_policy_edit_before_dispatch_invalidates_grant` |
| One-use authority | `test_one_grant_is_consumed_once` |
| Argument substitution rejected before transport | `test_amount_tamper_is_rejected_before_transport` |
| Closed action registry | `test_unknown_state_changing_tool_fails_closed` |
| Typed argument schema, no coercion | `test_action_schema_rejects_extra_or_coerced_arguments` |
| Single dispatch owner under concurrency | `test_concurrent_claims_have_one_dispatch_owner` |
| **`UNKNOWN` retains exposure** | `test_stale_dispatching_recovers_to_unknown_without_releasing_headroom` |
| Append-only evidence | `test_audit_rows_cannot_be_updated` / `_deleted` |

**Put that last test name on screen in the video.** The name *is* the argument:
"recovers to unknown without releasing headroom". A reviewer who has seen a dozen
projects claim safety will register a test named after the exact property being
claimed.

---

## Next steps — nothing new gets built

Ordered. Steps 1–3 are blocking; step 4 is the only optional item.

### 1. Ship the submission (today, ~30 minutes)

- Rename the GitHub repo off `uap-mandate-agent` (see `SUBMISSION_PACK.md` §0.5).
- Move the "Continue with Claude Code" section out from between *Quick start* and
  *Demo proof*.
- Submit the form. It is live and Razorpay publishes no deadline; waiting has no
  upside.

### 2. Record the video (§2 of `SUBMISSION_PACK.md`)

One change to the storyboard given what we now know. In the **3:25–4:15 proof
block**, do not just show `61 passed` — scroll the test *names*. Ten seconds of

```
test_policy_edit_before_dispatch_invalidates_grant
test_amount_tamper_is_rejected_before_transport
test_unknown_state_changing_tool_fails_closed
test_stale_dispatching_recovers_to_unknown_without_releasing_headroom
```

does more than any sentence about safety, because each name is a falsifiable claim.

Then give `UNKNOWN` its full sentence, roughly:

> "When Razorpay times out after we have already sent the request, we do not know
> whether money moved. Most systems free the budget and retry. We hold the exposure,
> mark it unknown, and refuse to redispatch until an authoritative observation
> resolves it — because the failure mode we care about is charging someone twice."

### 3. Verify and stop

Run the pre-flight checklist in `SUBMISSION_PACK.md` §4. Then stop touching the
repository. `SUBMISSION_STRATEGY.md` reached this conclusion first and it was right.

### 4. Only if the submission is already in

The one addition that would close our remaining gap is a **multi-model
prompt-injection corpus** against the proposal path — 40–60 poisoned catalog entries
and shopper prompts, run across two models, reporting the block rate and the cases
that got through. `SUBMISSION_STRATEGY.md` already lists it as the outstanding proof
gap.

It is genuinely valuable and it is genuinely optional. It is also the one thing that
would answer a reviewer who has seen both projects and is asking which team thinks
harder about adversaries. Do not start it before the form is submitted.

### What not to do

- Do not add an economic recovery harness. That is Track 03's bar, we would be
  playing on their axis, and the number would be one we invented.
- Do not mention another submission anywhere in ours.
- Do not add a fifth registered action to look more capable. One is the argument.
