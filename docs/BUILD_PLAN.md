# Action Firewall — Finish and Submit Plan

**Primary:** Track 01 — AI Growth & Agentic Commerce

**Secondary challenger:** Retry Budget — Track 03

**Decision:** finish and submit Action Firewall. Do not pivot unless Retry Budget
produces materially stronger reproducible proof before the submission freeze.

## Current proof baseline

Already implemented:

- proposal-only `POST /chat` and explicit `POST /checkout/confirm`;
- confirmation bound to the exact cart hash;
- deterministic complete-policy evaluation and headroom reservation in one SQLite
  write transaction;
- versioned policy edits serialized against authorization and dispatch;
- one-use grant bound to identity, session, purchase attempt, policy, cart, action,
  arguments, amount and currency;
- closed action registry with `create_payment_link` as the only permitted action;
- one-owner dispatch claim with a dispatch token;
- `UNKNOWN` outcome that keeps exposure reserved and forbids blind retry;
- separate `action_issued` and `settled` states;
- startup recovery from stale `dispatching` to `UNKNOWN`;
- deterministic offline catalog and payment clients;
- 51 passing backend tests, including database-enforced audit append-only behavior,
  plus a passing frontend production build and a clean npm audit
  at the latest full verification.

Do not weaken these invariants for presentation polish.

## Submission gates

| Priority | Gate | Done when |
|---|---|---|
| P0 | Safety regression suite | Full backend suite passes on the final commit; concurrency, stale policy, one-use dispatch and unknown-outcome tests remain green |
| P0 | Offline demo reliability | `python scripts/demo.py` runs from a disposable database with no keys or network and produces the same lifecycle evidence three times consecutively |
| P0 | Five-minute story | One rehearsed path fits under 4:45 and shows proposal, explicit cap denial, price-fit recovery, allowed issuance, revocation, concurrency proof and audit evidence |
| P0 | Truthful terminology | Every surface says policy/authorization; issuance is never called settlement; no claim of Vulcan access or unsupported protocol compliance remains |
| P0 | Artifact consistency | README, architecture, demo script, browser deck, PPTX and video use the same totals, state names and limitations |
| P1 | Audit receipt integrity | Update/delete guards and stable event identifiers are shipped; add a tamper-evident hash chain only if it does not threaten the demo freeze |
| P1 | Reconciliation runbook | Document the operator steps for `UNKNOWN`, including the authoritative evidence required before issue/failure resolution |
| P1 | Frontend recovery copy | Every blocked, stale, in-progress and unknown state gives one safe next action and never suggests a blind retry |
| P2 | Live test integration | Demonstrate Remote MCP or Pinecone only after the offline submission path is frozen and repeatable |

## Immediate work order

### 1. Freeze the authorization contract

Treat the following as release invariants:

1. A chat turn cannot dispatch a payment action.
2. Confirmation must name the exact current cart hash.
3. Authorization uses the current persisted policy inside the reservation transaction.
4. A policy change before dispatch invalidates the grant.
5. A grant can have only one dispatch owner.
6. The dispatched name and canonical arguments must exactly match the grant.
7. A definitive failure may release headroom; an ambiguous result may not.
8. Payment-link issuance does not imply customer payment or settlement.

Any refactor touching `agent.py`, `store.py`, `mandate.py` or `mcp_client.py` must
add or update a regression test for the affected invariant.

### 2. Complete the adversarial matrix

Add deterministic tests where gaps remain. Prefer assertions over an LLM judge.

| Attack or fault | Required assertion |
|---|---|
| Cart mutation after preview | Confirmation rejected; zero actuator calls |
| Stale policy version/hash | Grant cancelled; zero actuator calls |
| Revocation between confirmation and claim | Grant cancelled; exposure released safely |
| Action-name substitution | Registry rejects it before external I/O |
| Argument, amount or currency substitution | Grant claim rejected; zero actuator calls |
| Same grant claimed concurrently | Exactly one dispatch token is returned |
| Same purchase attempt with different cart | Idempotency conflict, not replay |
| Two sessions with the same basket | Independent attempts; cap still enforced atomically |
| Timeout after provider acceptance | `UNKNOWN`; exposure remains held; no automatic second call |
| Crash while `dispatching` | Startup recovery produces `UNKNOWN`, not `authorized` |
| Late response from original dispatch owner | Matching token may resolve; stale/non-owner token may not |
| Hallucinated or poisoned SKU | Unknown SKU is never priced or dispatched |
| Cap−1, cap and cap+1 | Inclusive boundary is explicit and stable |

Report failures and exceptions rather than hiding them. If multiple model runs are
added, report the probability that **all** runs preserve the authorization invariant,
not the probability that one run passes. The deterministic gate must remain the
ultimate oracle.

### 3. Lock the five-minute demo

Use the offline path for the recorded submission and keep a live-integration branch
as optional evidence.

```text
0:00–0:25  Thesis and boundary: model proposes; policy authorizes
0:25–1:10  Cart proposal; point out that no payment action ran
1:10–2:00  Oversized checkout language plus explicit denial; zero actuator calls
2:00–2:55  Price-fit recovery; exact confirmation issues one simulated link
2:55–3:45  Revoke policy; next confirmation fails against current version
3:45–4:30  Audit, metrics and concurrency proof: one grant, 8 claims, 1 call
4:30–4:50  Limits: identity stub, no signed attestations, no automatic reconciler
4:50–5:00  Close on the invariant
```

Pre-record one clean backup run and keep screenshots of the concurrency and test
results. If the UI fails live, run the headless demo and narrate the same state
transitions. Do not switch to real credentials during the main recording.

### 4. Align every artifact

Before recording, search public artifacts for stale or misleading terms. Remove or
qualify any wording that implies:

- access to a private or public Vulcan endpoint;
- protocol or regulatory compliance that has not been tested;
- a payment link equals a successful payment or settlement;
- denied requested value equals prevented fraud, prevented loss or chargeback value;
- a rules engine alone is the product.

The product is the full action boundary: explicit user confirmation, deterministic
authorization, atomic exposure accounting, exact one-use grants, closed actuation,
recovery semantics and replayable evidence. The AI earns its place by turning natural
language intent into a useful cart proposal; it does not earn authority from being AI.

### 5. Run the final verification

Run from a clean checkout of the final commit:

```powershell
cd backend
python -m pytest -q
python -m compileall -q app tests scripts
python scripts/demo.py

cd ..\frontend
npm ci
npm run build
npm audit
```

Then verify:

- no tracked secrets or `.env` files;
- working tree clean;
- public repository clone instructions work on Windows;
- all links and screenshots load;
- deck and video totals match one fresh demo database;
- the video is under five minutes;
- the exact Buildathon deadline, eligibility and submission fields are re-checked on
  the official page immediately before submission.

## Refactors allowed before freeze

Only take refactors that reduce judge confusion or close a demonstrated safety gap:

- rename user-facing “mandate” copy to “policy” while documenting legacy route/table
  names;
- centralize state labels and recovery copy;
- add a tamper-evident audit hash chain if it is small, tested and backward-compatible;
- extract provider reconciliation behind a deterministic interface without adding a
  network-dependent demo step.

Do not add multi-agent orchestration, another payment action, a new model router,
production authentication, or a speculative retry optimizer before submission. They
increase surface area without strengthening the current proof.

## Evidence that would change the decision

Retry Budget stays secondary. Reconsider only if, before the freeze, it has all of:

1. a functioning batch harness on published synthetic data;
2. deterministic attempt-policy enforcement and idempotent actuation;
3. compliance windows and notification evidence verified from current primary
   sources;
4. measured incremental recovery against a fixed-schedule baseline, with variance;
5. a failure demo sharper and more reliable than Action Firewall's concurrency story;
6. no dependence on inaccessible Razorpay or Vulcan capabilities.

Without that evidence, a measured and defensible Action Firewall is the stronger
submission than an unfinished recovery optimizer.

## Release stop rule

Once all P0 gates pass, freeze feature work. Spend the remaining time on rehearsal,
artifact consistency, a fresh-clone smoke test and truthful answers to judge
objections. A new feature is allowed after freeze only if it fixes a reproducible
failure in the five-minute path.
