# Action Firewall — authoritative project brief

**Status:** submission-ready baseline handed to Claude Code on 3 September 2026

**Primary track:** Razorpay AI Buildathon Track 01 — AI Growth & Agentic Commerce

**Challenger:** Retry Budget — Track 03, research only

## Thesis

An AI agent may propose or assemble a cart, but only a deterministic, versioned,
shopper-defined application policy may authorize one exact Razorpay payment action.

The product is an authorization boundary, not a generic shopping chatbot and not a
bank, NPCI, UPI, or UAP mandate implementation.

## Frozen decision

Continue Action Firewall. Do not pivot to Retry Budget unless it first produces
verified primary-source constraints, a runnable batch harness, an idempotent action
surface, and measured incremental recovery against fixed-schedule and oracle
baselines. A finished, inspectable Track 01 submission is stronger than a speculative
Track 03 rebuild under deadline pressure.

## Current workflow

```text
catalog retrieval -> AI cart proposal -> deterministic preview
                                      -> explicit exact-cart confirmation
                                      -> atomic current-policy authorization
                                      -> headroom reservation
                                      -> exact one-use grant
                                      -> one-owner dispatch claim
                                      -> registered create_payment_link action
```

Provider outcomes are classified as `ACTION_ISSUED`, `SETTLED`,
`DEFINITIVE_FAILURE`, `UNKNOWN`, or `CANCELLED`. Payment-link creation ends at
`ACTION_ISSUED`; only separate authoritative provider evidence can establish later
payment or settlement state.

## Proof baseline

- 51 deterministic backend tests passing.
- Frontend production build passing with zero reported npm vulnerabilities.
- Offline disposable rehearsal passing three consecutive times.
- Naive concurrency regression records ₹2,400 against a ₹1,000 cap.
- Atomic reservation caps eight concurrent ₹300 requests at ₹900.
- Eight concurrent claims on one grant produce one simulated provider call.
- Cart, policy, action, argument, amount, currency, and replay tampering are denied
  before provider transport.
- Provider timeout becomes `UNKNOWN`, retains exposure, and cannot auto-retry.
- SQLite triggers reject audit-row updates and deletes.

## Five-minute demo contract

1. Show the active ₹1,000 policy.
2. Propose the ₹486 pasta cart; prove chat made no payment call.
3. Grow the cart to ₹2,034; explicit authorization is denied before actuation.
4. Remove premium items; explicitly authorize the exact ₹486 cart and show one
   `ACTION_ISSUED` simulated payment link.
5. Revoke policy version 2; the next ₹549 coffee authorization is denied.
6. Show audit metrics, 61 tests, concurrency ownership, and `UNKNOWN` semantics.

Canonical narration and failure handling live in `docs/DEMO_SCRIPT.md`.

## Key implementation files

- `backend/app/agent.py`: proposal and confirmation flows.
- `backend/app/mandate.py`: pure deterministic policy evaluator.
- `backend/app/store.py`: policy history, atomic authorization, reservations,
  grants, dispatch state, reconciliation transitions, and audit events.
- `backend/app/actions.py`: closed action registry and canonical schemas.
- `backend/app/mcp_client.py`: simulated and Razorpay Remote MCP adapters.
- `backend/tests/`: policy, boundary, concurrency, recovery, and demo proof.
- `frontend/lib/api.ts`: browser-to-backend contract.
- `docs/ARCHITECTURE.md`: current detailed architecture and limitations.
- `market-context.md`: dated evidence ledger and public-source boundaries.

## Known limitations

- Browser-provided identities are not production authentication or tenant isolation.
- SQLite proves one-service-instance serialization, not distributed safety.
- The audit log is database-guarded but not signed or externally anchored.
- `UNKNOWN` has safe accounting but no background Razorpay reconciliation worker.
- The reliable submission path uses a simulated actuator; Remote MCP is optional
  test-mode evidence.
- No Vulcan interface or private Razorpay capability is available to this project.

## Next development order

P0 before feature work:

1. Record and verify the sub-five-minute submission video.
2. Repeat the documented quick start from a fresh clone.
3. Confirm the official application form, deadline, and submission fields.

P1 only after P0 is frozen:

1. Add a deterministic reconciliation adapter and signed-webhook fixture.
2. Publish a machine-readable adversarial corpus and evaluation report.
3. Demonstrate one Remote MCP test-mode link separately from the offline proof.

Do not add a multi-agent swarm, model router, second payment action, broad MCP
pass-through, production deployment, or retry optimizer before the submission path
is recorded and frozen.
