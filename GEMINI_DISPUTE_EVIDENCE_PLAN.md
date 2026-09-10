# Work orders — Dispute-grade evidence for agent-initiated payments

For the coding agent. Read `CLAUDE.md` first, then this. Written 2026-09-10.
This is the finishing move on the competitive push; `ANTIGRAVITY_WORK_ORDERS.md`
still holds for WO-0/WO-1/WO-3 and is not superseded.

---

## 1. Why this is the move, in one argument

IntentGuard protects the **buyer** from their own agent. That is a consumer-safety
story. Razorpay's customer is the **merchant**, and the merchant's problem with
agentic commerce is not "my customer's agent bought the wrong cheese":

> An agent-initiated charge carries no cardholder-present evidence. When the
> customer says *"my agent was not authorised to buy that"*, the merchant eats
> the chargeback, and today there is no artifact they can produce.

You cannot take *"the model returned a 0.87 fit score"* to a dispute. IntentGuard
structurally cannot fix this: their rule is re-derived by an LLM at each
transaction, so there is no stable object to point at afterwards, and the samples
that produced the decision no longer exist.

We can produce something better than a record. **We can let a third party
re-execute the authorisation decision and get the same answer.** That is what
determinism buys, it is worth nothing until it is packaged as evidence, and it is
the one claim a sampling-based design can never make.

Position the product as: *the merchant-side acceptance layer that makes an
agent-initiated charge defensible.* Same code. Different customer.

---

## 2. State of the world

| fact | value |
|---|---|
| backend tests | **482 passing**, CPython 3.11.15 |
| audit chain | shipped, `b4daebc` — `GET /evidence/audit-chain/verify` |
| envelope readback | shipped, `cfd2bee` — `render_envelope_english()` is PURE |
| consent record | written and tested; **commit unconfirmed** (see below) |

**Before starting, check whether the consent-record commit landed.** The desktop
disconnected mid-commit. Run:

```powershell
git log --oneline -3
git status --porcelain
```

If `Prove what the customer was shown, not only that they clicked` is absent, the
five files are on disk uncommitted — `backend/app/consent.py`,
`backend/app/store.py`, `backend/app/main.py`,
`backend/tests/test_consent_record.py`,
`backend/scripts/verify_consent_record.py`. Commit exactly those, nothing else.

Also still uncommitted from another agent, unrelated to this work:
`backend/app/agent.py`, `backend/app/mcp_client.py`,
`frontend/app/baseline/page.tsx`, `frontend/app/playground/page.tsx`,
`frontend/components/layout/MerchantShell.tsx`, `frontend/lib/api.ts`.
Do not stage them with yours.

---

## 3. The finding that shapes everything below

**The evidence a dispute pack needs is not persisted today.** Verified by reading
the schema, not assumed:

`spend_ledger` stores `args_hash`, `cart_hash`, `quote_hash`, `envelope_hash`,
`policy_hash`, `result_json`, `error`. It does **not** store:

- the `EnvelopeDecision` — the code, the deltas, the human message
- the `MerchantQuote` itself, only its hash
- **the stock readings the decision was taken against**

Without those, a dispute pack can prove a charge is *bound* to an approved rule
but cannot show *why it was allowed* — and a refusal cannot be evidenced at all.
So WO-A comes first. A plan that skipped it would assemble a pack out of hashes
and discover the gap at demo time.

---

## 4. WO-A · Persist the decision record · ~4 hours · PREREQUISITE

**Goal:** every authorisation attempt — allowed, refused or unknown — leaves
enough behind to re-derive its own outcome.

### 4.1 New table, `backend/app/store.py`

```sql
CREATE TABLE IF NOT EXISTS decision_records (
    id TEXT PRIMARY KEY,
    purchase_attempt_id TEXT NOT NULL,
    envelope_id TEXT NOT NULL,
    envelope_version INTEGER NOT NULL,
    envelope_hash TEXT NOT NULL,
    grant_id TEXT,                    -- NULL for a refusal
    outcome TEXT NOT NULL,            -- issued | refused | unknown
    decision_json TEXT NOT NULL,      -- the whole EnvelopeDecision
    quote_json TEXT NOT NULL,         -- the server-priced quote, in full
    quote_hash TEXT NOT NULL,
    catalog_revision TEXT NOT NULL,
    -- Stock is a point-in-time reading and is the ONE input a third party
    -- cannot independently reproduce. Recording it is what lets the decision be
    -- re-derived at all; labelling it as attested rather than proven is what
    -- keeps the artifact honest.
    stock_at_decision_json TEXT NOT NULL,   -- {sku: units} for cart SKUs only
    decided_at REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_decision_attempt
    ON decision_records(purchase_attempt_id);
```

Add to `_migrate()` the same way the other additive migrations are done. Never
drop or rewrite an existing table.

### 4.2 Write it where the decision is made

In `app/autopilot.py` and `app/commerce_service.py`, wherever `verify_quote` is
called on the dispatch path, record the result **in the same transaction as the
grant** where one is minted. A decision record written outside that transaction
can survive a rolled-back grant and describe an authorisation that never existed.

Refusals must be recorded too. *"Whatever happened, the store can prove it
afterwards — including, and especially, a refusal"* is already the claim on the
front door; this is what makes it true.

### 4.3 Tests — `backend/tests/test_decision_record.py` (new)

- an issued attempt writes exactly one record, `outcome="issued"`, `grant_id` set
- a refused attempt writes one, `outcome="refused"`, `grant_id` NULL, deltas intact
- an `UNKNOWN` outcome writes `outcome="unknown"` and keeps the grant id
- `stock_at_decision` covers **every SKU in the cart** and nothing else
- a rolled-back grant leaves **no** decision record (drive a failure inside the
  transaction and assert the table is empty)
- replaying an idempotent attempt does not write a second record

---

## 5. WO-B · The dispute pack · ~4 hours

### 5.1 `GET /evidence/dispute-pack/{purchase_attempt_id}`

Unauthenticated is wrong here — this is merchant data about one customer. Gate it
with `verify_merchant_admin`, the dependency already used for the merchant-only
evidence routes. The *verifier* is public; the *pack* is not.

Assemble, in `backend/app/dispute.py` (new):

```python
DISPUTE_PACK_SCHEMA = "action-firewall/dispute-pack@1"

def build_dispute_pack(purchase_attempt_id: str) -> dict:
    ...
```

Contents:

| key | source | why it is in the pack |
|---|---|---|
| `consent` | `build_consent_record(envelope)` | what the customer was shown |
| `quote` + `quote_hash` | decision record | what was actually priced |
| `decision` | decision record | the outcome and every delta |
| `grant` | `spend_ledger` row | the exact bound authority, or absent on a refusal |
| `receipt` | `build_receipt(grant)` | the signed statement |
| `catalog_snapshot` + `catalog_revision` | `catalog.load_catalog()` at export | closes the pack: the verifier needs the facts the decision saw |
| `stock_at_decision` | decision record | the one attested input |
| `audit` | chain rows for this attempt + `head_hash` | timing and tamper-evidence |
| `verify_with` | a command string | the pack tells you how to check it |

**Include the full catalog snapshot, not just the SKUs in the cart.** It is ~14 KB
for 46 products, and `catalog_revision` is a hash of the whole catalog — a partial
snapshot cannot be checked against it, so a partial snapshot is unverifiable.

### 5.2 Tests — `backend/tests/test_dispute_pack.py` (new)

- a pack for an issued attempt contains every key above
- a pack for a **refused** attempt contains the decision and its deltas, and no grant
- `compute_catalog_revision(pack["catalog_snapshot"]) == pack["catalog_revision"]`
- an unknown attempt id → 404
- the route rejects a non-admin caller
- the pack contains **no** API keys, no signing secret, no other customer's data
  (assert on the serialised JSON, by substring)

---

## 6. WO-C · The offline verifier · ~6 hours · THE KNOCKOUT

`backend/scripts/verify_dispute_pack.py`, extending the pattern of
`verify_consent_record.py`. No database, no signing key, no network.

### 6.1 What it checks, in order

**Independently re-derived — needs nothing but the pack and the published source:**

1. the consent record verifies (`verify_consent_record`)
2. `compute_catalog_revision(catalog_snapshot) == catalog_revision`
3. `compute_quote_hash(quote) == quote_hash`
4. `cart_hash(quote.cart) == grant.cart_hash`
5. `action_args_hash(args) == grant.args_hash`
6. `grant.envelope_hash == consent.envelope_hash` — the authority is bound to the
   rule the customer approved, not to some other envelope
7. `grant.quote_hash == quote_hash`
8. the receipt's authorization block equals the grant field for field
9. the audit slice's links hold and each `entry_hash` recomputes
10. **the decision re-derives.** Rebuild the exact catalog state the decision saw
    from `catalog_snapshot` + `stock_at_decision`, call
    `verify_quote(envelope, quote, now=decided_at)`, and assert it equals the
    recorded decision — `allowed`, `code`, and every delta field.

**Check 10 is the whole point.** Anyone can re-execute the authorisation and get
the same answer. Say so in the output in those words.

**Attested, not proven — state it plainly rather than burying it:**

- `stock_at_decision` — a point-in-time reading only the merchant observed. The
  audit chain fixes *when* it was recorded; nothing can prove *what was on the
  shelf*.
- the receipt HMAC — needs the merchant's signing key; whoever holds it checks
  that separately.
- that a human read the sentence — unknowable from any artifact.

An evidence tool that does not name its own limits invites being read as proving
more than it does, and the first person to notice will be someone deciding
whether to trust the rest of it.

### 6.2 The catalog seam

`verify_quote` reads `catalog.by_sku()` and `catalog.available_stock()` live.
Add an explicit override beside the existing `_STOCK_OVERRIDE`, which the module
already documents as exactly this kind of seam:

```python
_CATALOG_OVERRIDE: list[dict] | None = None

def use_snapshot(rows: list[dict]) -> None: ...
def clear_snapshot() -> None: ...
```

`load_catalog()` and `by_sku()` return the override when set. Do **not** have the
verifier monkeypatch module internals — a verifier that reaches into private
state is one a reviewer cannot trust. Remember `load_catalog` and `by_sku` are
`@lru_cache`d; the setter must clear both caches.

### 6.3 Tests — `backend/tests/test_dispute_pack_verify.py` (new)

A clean pack verifies. Then one test per tamper, each naming the failed field:

| tamper | must fail on |
|---|---|
| raise the cap in the embedded envelope | `envelope_hash` |
| change a line's price in the quote | `quote_hash` |
| change a line's price in the **catalog snapshot** | `catalog_revision` |
| swap the grant's `envelope_hash` for another envelope's | `grant.envelope_hash` |
| edit one delta out of the recorded decision | `decision` (re-derivation mismatch) |
| flip `allowed` from false to true on a refusal | `decision` |
| raise `stock_at_decision` so a refused-for-stock case would have passed | `decision` |
| edit an audit row's payload | `audit` |

That last-but-one is the sharpest test in the suite: it proves the *attested*
input cannot be doctored to change the *derived* outcome without the mismatch
surfacing.

---

## 7. WO-D · Chain checkpoints · ~3 hours · makes inclusion provable

Today `verify_audit_chain` proves the chain is internally consistent, and the
truncation blind spot is documented. A dispute pack that carries a slice cannot
prove that slice is *in* the chain.

Fix cheaply: publish periodic checkpoints.

```sql
CREATE TABLE IF NOT EXISTS audit_checkpoints (
    seq INTEGER PRIMARY KEY,
    head_hash TEXT NOT NULL,
    created_at REAL NOT NULL
);
```

- Write one every N entries (N = 50) and on demand.
- `GET /evidence/audit-chain/checkpoints` — public, list only.
- A dispute pack carries the checkpoint immediately **before** its first entry
  and the one **after** its last, plus every entry between. The verifier walks
  from the earlier checkpoint's head to the later one and confirms both match.
  Inclusion is then proven against two values published independently of the pack.

Honest scope note for the docs: this is a linear chain, so proof size grows with
the checkpoint interval. A Merkle tree would give logarithmic proofs. Do not
build one; say in `docs/ARCHITECTURE.md` that it is the obvious next step and why
it was not needed at this size. Naming the limitation you did not fix is more
convincing than pretending it is not there.

---

## 8. WO-E · The Disputes screen · ~5 hours

`frontend/app/disputes/page.tsx` (new), linked from the sidebar in
`components/layout/MerchantShell.tsx` under CONTROL PLANE.

A table of agent-initiated attempts: attempt id, when, amount, outcome chip
(`issued` / `refused` / `unknown`), and per row:

- **Download evidence pack** — the JSON
- **Verify** — runs the same checks in the browser via a `POST /evidence/dispute-pack/verify` endpoint that calls the identical code path as the CLI. One implementation, two front doors; two implementations would drift and the drift would be discovered by a judge.
- a green / red badge, and on red the failed field and reason

Above the table, one line of copy stating the actual value:

> Every agent charge here can be re-checked by someone who does not trust us.
> The rule the customer approved, the words they were shown, and the decision
> itself all re-derive from the pack alone.

Empty state: *"No agent-initiated charges yet."* — not a spinner, not a fake row.

`npx tsc --noEmit` and `npm run build` must be clean.

---

## 9. WO-F · Reframe the README · ~2 hours · LAST

Open on the merchant's problem, not the shopper's. Then one table, every cell
defensible from a public repo:

| in a dispute, can you produce… | LLM-judgement layer | Action Firewall |
|---|---|---|
| the rule the customer approved, verbatim | no — the rule is re-derived per transaction | yes, and it recomputes from the hash |
| the decision, re-executable by a third party | no — the samples are gone | yes |
| proof the charge is bound to that rule | partial | yes |
| a refusal, evidenced | no | yes |
| an evidence file a stranger can check | no | yes |

Rules for writing it:
- Do not name IntentGuard. Describe the mechanism, let the reader connect it.
- Every claim in the left column must be checkable in their public repo, and
  every claim in the right column must be runnable in ours.
- Do not overstate. An exaggeration a judge can check discredits the whole table.

---

## 10. Verification

```powershell
cd backend
python -m pytest -q
python -m compileall -q app tests scripts
python scripts/verify_consent_record.py docs/samples/consent.json
python scripts/verify_dispute_pack.py docs/samples/dispute_pack.json
python scripts/benchmark_agent_authorization.py --k 5
cd ..\frontend
npm run build
npx tsc --noEmit
cd ..
git diff --check
git status --porcelain
```

Commit one sample pack under `docs/samples/` so a reviewer can run the verifier
without setting up the app. Scrub it first: no keys, no real customer data.

Paste the measured pytest line into the commit message. Do not predict it.

---

## 11. Do not do these

- Do not make the dispute-pack route public. The verifier is public; the pack is
  merchant data about one customer.
- Do not claim the pack proves stock levels, that a human read anything, or that
  the audit log is immutable. Every one of those is checkable and false.
- Do not let the browser verifier and the CLI verifier be separate
  implementations. They will drift, and a judge will find the drift.
- Do not put a model anywhere on this path. It is evidence; a model's opinion is
  the thing we are arguing is not evidence.
- Do not write a decision record outside the grant's transaction.
- Do not `git add -A`.
- Do not use the phrase "legally binding" anywhere.

## 12. If you only get through two

**WO-A and WO-C.** The decision record and the offline verifier. Together they
support the one sentence that ends the comparison:

> Anyone can take this file and re-execute the authorisation decision. They do
> not have to trust the merchant, the model, or us — and they will get the same
> answer we did.
