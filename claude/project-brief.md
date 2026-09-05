# Action Firewall — authoritative project brief

**Status:** Safe Autopilot Checkout v2 implemented and verified on 5 September
2026; the exact-confirmation flow remains the measured baseline at `/baseline`

**Primary track:** Razorpay AI Buildathon Track 01 — AI Growth & Agentic Commerce

**Challenger:** Retry Budget — Track 03, research only

## Thesis

A shopper approves one structured, revocable Purchase Envelope for a bounded
shopping job. An AI may plan and repair a checkout inside it, but deterministic code
alone may prove envelope membership and derive one exact, one-use Razorpay Action
Grant.

The product is an authorization boundary, not a generic shopping chatbot and not a
bank, NPCI, UPI, or UAP mandate implementation.

## Frozen decision

Continue Action Firewall as **Safe Autopilot Checkout**. Do not pivot tracks or
replace the working action runtime. Preserve the exact-confirmation flow as a
feature-flagged baseline while adding a Purchase Envelope path that removes repeated
cart approval only when the exact final quote is deterministically inside the
shopper-approved envelope.

Retry Budget remains research-only unless it first produces verified primary-source
constraints, a runnable batch harness, an idempotent action surface, and measured
incremental recovery against fixed-schedule and oracle baselines.

## Implemented baseline workflow

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

## Implemented V2 workflow

```text
shopper goal -> AI drafts Purchase Envelope -> trusted structured review
             -> explicit envelope activation (version/hash bound)
             -> AI plans candidate against server-owned catalog facts
             -> fresh Merchant Quote -> deterministic envelope membership check
                 |-- valid -> atomic envelope consumption + headroom reservation
                 |          -> exact one-use Action Grant -> one-owner dispatch
                 `-- invalid -> deterministic Policy Delta
                               -> policy-eligible recovery candidates
                               -> AI ranks only eligible candidates
                               -> re-verify or request delta-only approval
```

The human authorization object is the canonical Purchase Envelope. The machine
authorization object remains the exact Action Grant. The model may draft, plan,
rank, and explain; it may not activate an envelope, decide membership, define trusted
catalog facts, mint a grant, widen a delta, or dispatch an action.

The first v2 release is deliberately limited to one merchant, INR, one purchase per
envelope, one saved fulfilment profile, a server-owned product taxonomy, and the
registered `create_payment_link` action.

## Verified proof baseline

- 76 backend integration and regression tests passing.
- 400/400 generated deterministic envelope-boundary cases passing across eight
  families and 50 fixed seeds. This is authorization-correctness evidence, not
  production uplift.
- Frontend production build passing with zero reported npm vulnerabilities.
- Primary Safe Autopilot and legacy exact-cart offline rehearsals passing.
- Naive concurrency regression records ₹2,400 against a ₹1,000 cap.
- Atomic reservation caps eight concurrent ₹300 requests at ₹900.
- Eight concurrent claims on one grant produce one simulated provider call.
- Cart, policy, action, argument, amount, currency, and replay tampering are denied
  before provider transport.
- Provider timeout becomes `UNKNOWN`, retains exposure, and cannot auto-retry.
- SQLite triggers reject audit-row updates and deletes; HMAC receipts detect
  submitted receipt tampering against the current grant state.

## V2 five-minute demo contract

1. Draft and approve one pasta-dinner Purchase Envelope under ₹600.
2. Plan a valid cart and derive one exact Action Grant without a second cart approval.
3. Introduce deterministic stock or price drift; deny an invalid premium candidate
   before transport and recover to a valid substitute inside the same envelope.
4. Change merchant or fulfilment profile; refuse execution and display the exact
   Policy Delta rather than silently widening authority.
5. Show eight concurrent claims producing one dispatch owner and demonstrate
   `UNKNOWN` retaining exposure without blind retry.
6. Show the 400-case deterministic authorization evaluation and label the one-vs-two
   approval comparison as a modeled workflow count.

`docs/SAFE_AUTOPILOT_DEMO.md` is the primary script. `docs/DEMO_SCRIPT.md` and
`backend/scripts/demo.py` remain the reliable exact-cart baseline.

## Key implementation files

- `backend/app/agent.py`: proposal and confirmation flows.
- `backend/app/envelope.py`: canonical envelope and quote hashes, deterministic
  quoting, membership verification, and Policy Deltas.
- `backend/app/autopilot.py`: primary draft, activation, recovery and execution flow.
- `backend/app/receipts.py`: application-signed Action Receipts.
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
- The audit log is database-guarded and Action Receipts are application-signed, but
  neither is externally anchored or administrator-proof.
- `UNKNOWN` has safe accounting and pull-based provider reconciliation, but no
  scheduled worker or signed webhook consumer.
- The reliable submission path uses a simulated actuator; Remote MCP is optional
  test-mode evidence.
- No Vulcan interface or private Razorpay capability is available to this project.

## Next development order after submission freeze

1. Record and freeze the current five-minute path from a clean clone.
2. Add authenticated principals and tenant-scoped authorization before any public
   deployment.
3. Add signed Razorpay webhook ingestion and a scheduled reconciler.
4. Move sessions, quotes, locks and outbox state to a durable production store.
5. Publish a labeled multi-model drafting and catalog-injection evaluation.
6. Add live test-mode evidence only when it cannot destabilize the offline demo.

Do not add a multi-agent swarm, model router, second payment action, broad MCP
pass-through, UPI Reserve Pay simulation presented as live, or retry optimizer before
the v2 path and evaluation are frozen.
