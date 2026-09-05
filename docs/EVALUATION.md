# Safe Autopilot evaluation

## Verified result

Run from `backend/`:

```powershell
python scripts/evaluate_autopilot.py
```

The 5 September 2026 run produced **400/400 passing deterministic cases** across
50 fixed seeds and eight case families:

| Family | Expected result | Pass rate |
|---|---|---:|
| Normal eligible quote | authorize | 100% |
| Preferred SKU unavailable | substitute inside envelope and authorize | 100% |
| Price above maximum | refuse with `max_total_paise` delta | 100% |
| Merchant drift | refuse with `merchant_id` delta | 100% |
| Fulfilment-profile drift | refuse with `fulfillment_profile_id` delta | 100% |
| Extra blocked gift card | refuse at category and slot boundary | 100% |
| Tampered catalog price | refuse because server catalog facts differ | 100% |
| Expired envelope | refuse with expiry delta | 100% |

Aggregate results were:

- in-bound quote acceptance: **100% (100/100)**;
- out-of-bound quote blocking: **100% (300/300)**;
- stock-loss recovery inside the same authority: **100% (50/50)**;
- unexpected authorizations in this corpus: **0**.

The backend integration suite separately verifies database state, HTTP
contracts, dispatch lifecycle, revocation, concurrency, provider ambiguity,
reconciliation, receipt signatures, and the legacy exact-cart baseline. It is
not replaced by this pure-gate corpus.

## Baseline comparison

For one stock-loss recovery, the exact-cart baseline requires two approval
steps: approve the first cart, then approve the changed cart. A Purchase
Envelope requires one approval when the replacement SKU remains inside every
approved field. This is a **modeled workflow count**, not measured user time or
conversion uplift.

## What this evidence does not prove

This corpus is synthetic and uses the repository's 35-item fixed-price demo
catalog. It does not prove production payment success, GMV uplift, conversion
uplift, fraud reduction, regulatory compliance, merchant demand, or model
quality on arbitrary shopping language. Those require test-mode integration,
real inventory feeds, user research, and then a controlled merchant pilot.

The claim supported here is narrower and defensible: for the generated
boundary cases, the deterministic verifier accepted every in-envelope quote,
recovered every tested stock-loss case without wider authority, and blocked
every tested policy breach before the actuator.
