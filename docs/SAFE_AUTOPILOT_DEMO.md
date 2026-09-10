# Safe Autopilot — five-minute demo

## The one-sentence claim

> The shopper approves one bounded purchase job; AI may recover inside it, but
> only deterministic code can derive and dispatch one exact Razorpay action.

## Preflight

Use `DEMO_MODE=true`. Open:

1. `/` — Safe Autopilot storefront;
2. `/impact` — Merchant impact comparison;
3. `/audit` — Lifecycle evidence, attempt timeline, and demo lab;
4. a terminal at `backend/` with `python scripts/demo_autopilot.py` ready.

Run before presenting:

```powershell
python -m pytest -q
python scripts/evaluate_autopilot.py
python scripts/demo_autopilot.py
```

The offline path uses the same envelope verifier, atomic reservation, exact
grant, actuator boundary, lifecycle store, and receipt code as the UI. It uses
a simulated provider and must be labeled as such.

## 0:00–0:30 — the thesis: evidence beats assertion

**Screen:** `/`.

**Say:**

> “In agentic commerce, evidence you can re-run beats assertion you have to trust.
> Early on, we thought publishing merchant rules could prevent 88% of order
> failures—until an audit caught us conflating store rules with customer envelopes.
> The true measured figure was 47.1% (400 of 850 violations). We didn’t hide it;
> we put the error in the docstring and locked it in CI.
>
> That discipline taught us what’s really broken: a spend cap does almost none
> of the work. On this demo envelope, our admission readback shows `cap_binds = false`:
> the dearest permitted basket is ₹527 against a ₹7,840 ceiling. A budget limits
> amount, but an Envelope limits meaning—and a cap-only guard leaks 81.2% of
> policy violations.”

Point to the four-step pipeline: published rules, customer-approved Envelope,
agent execution, and tamper-evident dispute pack.

## 0:30–1:20 — activate bounded authority

Use **Speak purchase intent** when `OPENAI_API_KEY` is configured, or the clearly
labeled **Use device voice** fallback. Say “Buy supplies for an office pantry restock.” Point
out that the transcript only edits the goal field. Keep the ₹8,000 ceiling (or ₹600 for pasta dinner; office pantry totals ₹7,840) and click
**Generate approval draft**.

Point to:

- merchant **FreshBasket for Business** (`merchant_freshbasket`);
- saved fulfilment profile;
- three required item slots;
- blocked `gift_cards` category;
- `create_payment_link`, one use;
- version and envelope hash.

Click **Approve this envelope once**.

**Say:**

> “Voice and model output stop at editable intent. The model may translate
> language into this draft, but this click is the
> activation event. The server versions and hashes the complete envelope and
> creates the exact spend fence. The model cannot perform this transition.”

## 1:20–2:20 — win on useful autonomy

Select **Stock loss → safe substitute** and run it.

Point to the substitution, final total, `ALLOW_ENVELOPE`, `ACTION_ISSUED`, and
the signed receipt hashes.

**Say:**

> “The preferred pasta went out of stock. The planner ranked alternatives, but
> deterministic code rehydrated catalog facts and proved the replacement still
> satisfied every slot, the same merchant, address, deadline and maximum. It
> then minted one exact Action Grant. No second approval was required.”

Then say:

> “This is a simulated Razorpay payment link, not a settled payment. The receipt
> is application-signed evidence of what our firewall authorized, not a
> Razorpay signature or immutable ledger.”

## 2:20–3:20 — prove refusal is field-specific

Click **New job**, draft and approve the same goal. Select **Merchant changed →
refuse** and run it.

Point to the exact delta:

```text
merchant_id
approved: merchant_demo
actual: merchant_unapproved
next: fresh approval
```

**Say:**

> “I'm injecting this failure deliberately, the same way you'd run a chaos test.
> The point isn't that the merchant changed, it's what the verifier does when it
> did — and the endpoint refuses to accept an injected scenario outside demo
> mode.”
>
> “The cart can still look reasonable, but merchant identity is authority, not
> preference. The quote is refused before a grant exists and before the
> provider adapter is called. Recovery cannot silently widen this field.”

If time permits, repeat with price drift to show `max_total_paise` and a repair
decision rather than fresh approval.

## 3:20–4:10 — show the hard distributed-systems case

Either use a third job with **Provider timeout → hold**, or show the prepared
terminal rehearsal.

**Say:**

> “After dispatch, a timeout is not proof of failure. We record UNKNOWN, keep
> the envelope's single use and policy exposure occupied, and return the same
> grant on retry. We reconcile; we never blind-fire a second payment action.”

## 4:10–4:45 — show evidence

Open `/impact` to show the merchant continuity comparison (100% vs 50% checkout completion, 1.0 vs 1.5 approvals, 0 unsafe actions).

Then open `/audit`. Point to the separate events grouped by purchase attempt:

- `ENVELOPE_DRAFTED` and `ENVELOPE_ACTIVATED`;
- `ENVELOPE_RECOVERY_APPLIED`;
- `AUTHORIZATION_ATTEMPT`;
- `ACTION_DISPATCH_STARTED` and `ACTION_ISSUED`;
- `ENVELOPE_QUOTE_BLOCKED` for the merchant drift.

Point out the dual-signature receipt inspection, provider mode, and the distinct
issued, settled, and unknown value metrics.

## 4:45–5:00 — close on proof

**Say:**

> “The evaluator passes 650 generated boundary cases across 10 goal families. The 368-test integration suite
> drives eight concurrent attempts under one envelope to one issued action,
> reproduces revocation between authorization and dispatch, and proves UNKNOWN
> suppresses redispatch. Vulcan can decide what is likely to work. Action
> Firewall proves whether this agent is allowed to do it.”

Stop.

## Do not say

- Do not say “powered by Vulcan”; no public Vulcan runtime is used.
- Do not call a Purchase Envelope a bank, NPCI, UPI, or regulatory mandate.
- Do not claim AP2 compliance. “AP2-shaped” or “standards-aligned” is the limit.
- Do not call a created link paid, settled, recovered revenue, or GMV.
- Do not imply the HMAC receipt is signed by Razorpay.
- Do not claim production readiness: routes remain unauthenticated and the
  demo catalog, inventory scenarios, and provider are simulated.

## Live failure recovery

- Browser/backend problem: run `python scripts/demo_autopilot.py` and label the
  provider simulated.
- Voice permission or provider problem: type the same intent. Voice is an input
  convenience, not part of the authorization trust boundary.
- Model/Pinecone failure: continue with the deterministic fallback. Degraded
  intelligence never widens authority.
- Unexpected provider response: preserve the attempt ID, show `UNKNOWN`, and
  reconcile. Do not start a new attempt.
- Unexpected quote: read the UI's canonical fields; do not use memorized totals.
