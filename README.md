# Action Firewall — AI Commerce Permissions

**Razorpay AI Buildathon — Track 01: AI Growth & Agentic Commerce**

**Documentation & Pitch:** [docs/pitch-deck.html](docs/pitch-deck.html) · **Runs locally in three commands** ([§7](#7-run-it-three-commands-from-clean-clone))

---

## 1. What this is

AI buyers are beginning to place real orders at merchant storefronts, but stores today face a binary choice: refuse agent traffic and lose the volume, or accept it and carry liability for mistaken or drifted purchases that no payment network covers. Action Firewall is the merchant-side layer that makes a store safely transactable by AI buyers: customers approve their purchase boundaries once, the store repairs minor stock and price variations automatically inside those boundaries, and any unapproved drift is stopped before a payment rail is called. For example, at reference merchant **FreshBasket for Business**, an agent executing a ₹7,840 pantry replenishment order within an ₹8,000 ceiling can repair out-of-stock items in-envelope while blocking unapproved cross-merchant or high-drift attempts.

---

## 2. Why now, in India

Razorpay and NPCI put agentic payments onto UPI in rapid succession (9 October 2025 with OpenAI; **20 February 2026 on Claude with Zomato, Swiggy and Zepto live**; 25 March 2026 with Sarvam over MCP).

NPCI circular **NPCI/UPI/OC-228/2025-26** established UPI Reserve Pay at up to ₹10,000 for 90 days as a Single Block Multi-Debit mechanism. After the initial customer UPI PIN authentication, **subsequent debits against the blocked balance require no re-authentication**.

> **The block bounds how much. Nothing bounds what for.**

Furthermore, no Indian payment regulation assigns chargeback liability for an agent-placed purchase: RBI's June 2026 liability framework strictly governs *unauthorised* transactions, whereas an agent executing inside an active customer mandate is legally *authorised*. If an agent orders the wrong goods or drifts into off-policy categories, the customer has no chargeback recourse and the merchant carries the full dispute and reputational burden. Action Firewall establishes per-purchase semantic authority at the merchant boundary before money rails execute.

---

## 3. Verified Benchmarks

Every number in this section is printed by a script in `backend/scripts/`, and every one of those scripts **exits non-zero when its claim stops holding**. All of them are gated in [`.github/workflows/ci.yml`](.github/workflows/ci.yml), so a regression fails the build instead of quietly editing this file.

### 3.1 Test suite

```powershell
cd backend
python -m pytest -q
```

```text
390 passed, 1 skipped, 1 warning in 102.33s (0:01:42)
```

That is **368 passing backend tests** — the count of test functions under `backend/tests/`, which parametrization expands into the 390 executed cases above. 0 failures.

The single skip is the whole of `tests/test_authorization_properties.py` (14 of those 368 functions), which needs `hypothesis` — declared in `requirements.txt` and installed by CI. With it present those 14 run as well, each exploring 300 generated examples.

Those 14 are the only tests here that assert *invariants* rather than examples, which is what makes them worth calling out: they generate envelope/quote pairs from a grammar rather than from a fixture list, so they are not limited to the failure modes the author thought of.

```text
a forbidden tag is never authorised          a widened envelope is never authorised
the cap is never exceeded                    authorisation is deterministic
a blocked category is never authorised       allowed implies no deltas, and the converse
a non-active envelope is never authorised    every delta carries an actionable recovery
an expired envelope is never authorised      a decision never reports a total it did not compute
tampered catalog facts are never authorised  insufficient stock is never authorised
a quote whose hash was not recomputed is never authorised
```

The first test in the file is `test_the_grammar_can_produce_authorised_orders`. Without it the other thirteen could all pass against a generator that only ever emits carts nothing would authorise — a property suite that proves nothing while looking rigorous.

### 3.2 Policy compliance and recovery (1,050 cases)

50 fixed seeds × 21 failure families, grouped under ST-WebAgentBench's six policy dimensions, with 15 seeds held out until the numbers were final.

```powershell
python scripts/benchmark_agent_authorization.py --k 5
```

```text
Agent-authorization benchmark
  corpus                      1050 cases (50 seeds x 21 families), k=5
  composition                 250 legitimate / 800 constructed policy violations
  Completion under Policy     53.1%   (share of ALL proposals ending in a clean completed order)
    of legitimate proposals   100.0%
  replay identity (5x)      100.0%   (regression guard, not a reliability metric)
  violation escape rate       0.00%
  acceptance (compliant)      100.0%
  repair rate (of refused)    38.5%
  false-positive rate         0.00%
  false-positive cost         Rs 0.00
  value recovered by repair   Rs 156,709.00
  value that would have completed without the layer, in violation  Rs 748,774.72
  cap-only guard would let through  640 of 800 violations (80.0%)
  held out (15 unseen seeds)   escape 0.00%, false-positive 0.00%

  modelled cost of each configuration (assumptions, not measurements):
    no_layer             Rs    1,788,775
    cap_only_guard       Rs    1,158,930
    action_firewall      Rs     -150,549
    lowest cost: action_firewall  ·  ordering robust to every single-assumption sweep: True

  risk by policy dimension (bands are ours, not ST-WebAgentBench's):
    user_consent_and_action_confirmation 0.00%  Low
    boundary_and_scope_limitation 0.00%  Low
    strict_execution_and_hallucination 0.00%  Low
    hierarchy_adherence        0.00%  Low
    robustness_and_security    0.00%  Low
    error_handling_and_safety_nets 0.00%  Low

  Synthetic, deterministic policy-compliance measurement of the merchant authorization layer. Constructed proposals, not sampled live agent behaviour. No claim of production conversion, settlement, or recovered revenue. Rupee figures are face value of synthetic carts.
```

**The row that matters is the comparator.** A spend cap is what almost every "AI spending guardrail" in the wild actually is, and it lets 640 of these 800 violations through. Zero escapes is only interesting next to that 80%.

The 250 legitimate proposals include near-miss families — carts sitting exactly on a boundary — so that a layer which simply refuses everything scores badly rather than perfectly. It refuses none of them.

### 3.3 Ablation: does every rule earn its place?

A layer that reports zero escapes tells you it works. It does not tell you which part is doing the work. This removes one rule at a time — by changing the envelope, never by patching the verifier — and **exits non-zero if any rule turns out never to change an outcome.**

```powershell
python scripts/ablation.py
```

```text
  ablation                            escaped     of     rate  note
  full_layer                                0    800     0.0%  every rule active — the shipped configuration
  no_ingredient_tag_rule                   50    800     6.2%  merchant sets no blocked_tags
  no_category_rule                         50    800     6.2%  merchant sets no blocked_categories
  no_spend_cap                             50    800     6.2%  cap raised beyond any cart in the corpus
  no_expiry                                50    800     6.2%  envelope never expires
  no_slot_requirements                    190    800    23.8%  slots accept almost anything
  no_stock_check                          100    800    12.5%  every shelf refilled, so availability never binds
  envelope_widened_and_rehashed           200    800    25.0%  ATTACK, not a setting: every rule removed and the digest recomputed

  Every rule changed an outcome on at least one case: none is dead weight.
```

Every row except the last is a configuration a real merchant could choose, which makes each one also an answer to "what happens if I don't set this?"

### 3.4 Concurrency: does the cap hold when orders collide?

```powershell
python scripts/benchmark_concurrency.py --threads 16 --trials 20
```

```text
Concurrency benchmark — does the cap hold when orders collide?
  cap Rs 1,000  ·  order Rs 200  ·  5 fit inside  ·  16 arrive at once  ·  20 trials

  read-compare-write
    trials that breached the cap   20/20  (100%)
    mean orders authorised          15.75  (only 5 fit)
    mean overspend                  Rs 2,150.00
    worst overspend                 Rs 2,200.00
    total overspend across trials   Rs 43,000.00

  authorize-and-reserve
    trials that breached the cap   0/20  (0%)
    mean orders authorised          5  (only 5 fit)
    mean overspend                  Rs 0.00
    worst overspend                 Rs 0.00
    total overspend across trials   Rs 0.00

  Local SQLite, one process, threads through a barrier. Measures one specific race: check-then-act on a shared budget. Does not measure network partitions, provider duplicates, or clock skew. The read-compare-write arm is a faithful reproduction of the common pattern, written here, not copied from anyone's repository.
```

A ₹1,000 cap checked the obvious way authorises ₹3,150 of orders under contention, every single trial. This is the reason authorization and reservation are one `BEGIN IMMEDIATE` transaction rather than two steps ([§4.3](#4-architecture-five-structural-guarantees)).

### 3.5 What publishing the rules is worth

```powershell
python scripts/publication_value.py
```

```text
  channel                 violations  hard refusals     value at stake
  acceptance_policy              400            292      Rs 420,505.00
  purchase_envelope              300            150       Rs 89,880.00
  neither                        100             50       Rs 29,960.00
```

Of 800 constructed violations, **400 (50%) would never have been proposed** by an agent that fetched the merchant acceptance policy ([§5](#5-what-an-agent-can-read-before-it-proposes)) first. Of the 492 refusals no repair could rescue, 292 were preventable that way — **₹4,20,505 of orders that died for want of a rule the store already knew and never said.**

A further 300 were preventable from the customer's own Purchase Envelope, which the agent already holds. Those are counted **separately and not claimed for the endpoint**, because slots and quantities are per-customer and not the merchant's to publish. The remaining 100 are forged prices and forged digests: publication prevents mistakes, not attacks, and the script says so in its own output.

---

## 4. Architecture: Five Structural Guarantees

Action Firewall decouples probabilistic AI planning from deterministic payment authorization through five architectural invariants:

1. **Closed Action Registry:** Only registered, strictly schema-validated actions can reach an external payment provider. The current registry supports `create_payment_link` (Track 01 inbound payment creation) and `refund` (outbound merchant protection, treated as future-scope proof in the roadmap).
2. **Exact One-Use Action Grant:** A grant is exact, expiring, and cryptographically bound to actor identity, buyer agent, session, merchant, attempt ID, cart hash, quote hash, envelope version and hash, action schema, amount in integer paise, and currency.
3. **Atomic Authorize-and-Reserve:** Policy evaluation and financial balance reservation occur atomically inside a `BEGIN IMMEDIATE` database transaction. If authority checks pass, exposure is locked before any actuator is invoked.
4. **Single CAS Dispatch Owner:** A single compare-and-set ownership transition redeems the grant immediately prior to dispatch. Double-spending, thread races, and duplicate payment links are eliminated.
5. **Authoritative `UNKNOWN` Outcome Semantics:** When an actuator call times out or returns an ambiguous status, the state transitions to `UNKNOWN`. Reserved headroom remains held, exposure is protected, and automated blind retries are suppressed until reconciliation.

**Inbound from the provider** is held to the same standard. `POST /provider/webhooks/razorpay` verifies an HMAC-SHA256 signature over the **raw request body before parsing it**, rejects a mismatched or missing signature with an audit row, is idempotent by provider event id, never auto-creates a grant it cannot match, and applies state transitions through the same reconciler state machine as every other observation. A webhook that cannot be authenticated cannot move money in this system.

---

## 5. What an agent can read before it proposes

An AI buyer can already discover what a store *sells*. It cannot discover what a store will *refuse* — so today it drafts an order, submits it, and learns the rules by breaking them. ACP standardises checkout, UCP standardises discovery, AP2 standardises how an authorization is represented; none of them standardises the refusal set.

```text
GET /agent-commerce/v1/acceptance-policy      (no authentication — a policy behind a key is not published)
```

The document states the blocked categories, the blocked ingredient tags, the order ceiling, the registered actions and their schema hashes, the four things the store requires (human activation, server-side pricing, single-use authorization, stock re-read at authorization), what each refusal recovery means, and — deliberately — **what the document does not cover**. It carries a `policy_hash` an agent can pin.

Two design decisions are worth stating plainly:

- **It is generated, never hand-maintained.** The document is built from the same objects the verifier reads (`DEFAULT_CHANNEL_POLICY`, `DEFAULT_BLOCKED_TAGS`, `ACTION_REGISTRY`). A published policy that has drifted from enforcement is worse than none, because it invites an agent to rely on a promise the server will not keep. `tests/test_acceptance_policy.py` proves each published rule *behaviourally* — it builds a cart that violates the rule and asserts the verifier actually refuses — and one test fails if a rule is added to the verifier and never published.
- **It is not served at `/.well-known/ucp`.** UCP's well-known path is a real convention with a real schema and a council behind it. Serving something else there would be a near-miss of a published standard rather than an implementation of one. This is our own document and it says so in its `schema` field.

---

## 6. What this is not (Honest Limits)

To preserve technical integrity, we state explicit boundaries:

- **Not an NPCI, UPI, or Banking Mandate:** The Purchase Envelope is an application-level permission container enforcing merchant-side semantic bounds. It does not replace card network rules or UPI rails.
- **Not a Private Vulcan Integration:** Vulcan is product context for intelligent routing and checkout optimization. This repository does not claim access to unreleased Vulcan APIs or internal Razorpay models.
- **Synthetic Correctness Evidence:** The 1,050-case corpus (800 of them constructed violations) measures synthetic deterministic authorization correctness under adversarial inputs. It does not claim measured human conversion, merchant revenue lift, or production settlement rates. Rupee figures are the face value of synthetic carts.
- **Not the First Deterministic Agentic-Commerce Benchmark:** AIP-Bench (arXiv:2607.21824) describes itself that way. The corpus here is a policy-compliance harness for this specific authorization layer, with a held-out seed split — not a general benchmark, and not a first.
- **Risk Bands Are Ours:** The Low/Medium/High bands applied to the six ST-WebAgentBench policy dimensions are this project's thresholds. ST-WebAgentBench defines the dimensions; it does not define those bands.
- **Cost Model Assumptions:** The economic model uses stated assumptions across merchant margins and dispute costs to demonstrate relative ordering robustness under parameter sweeps; it is not derived from audited financial books. Every assumption is a named constant in `app/cost_model.py` with its source.
- **Reserve Pay Integration:** There is currently no public Reserve Pay API. We model its operational and semantic characteristics based on published NPCI circulars.

---

## 7. Run it (Three Commands from Clean Clone)

### 1. Start Backend API & MCP Gateway

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

### 2. Start Operations Control Plane

```powershell
cd frontend
npm install
npm run dev
```

### 3. Run Full Verification Suite

```powershell
cd backend
python -m pytest -q
python scripts/benchmark_agent_authorization.py --k 5
python scripts/ablation.py
python scripts/benchmark_concurrency.py --threads 16 --trials 20
python scripts/publication_value.py
```

---

## Technical Reference & Artifacts

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — Implemented trust boundaries, lifecycle state machine, and data schema.
- [docs/EVALUATION.md](docs/EVALUATION.md) — Benchmark methodology, statistical definitions, and error taxonomies.
- [docs/pitch-deck.html](docs/pitch-deck.html) — Standalone presentation deck with live verifiable metrics.
- [docs/SAFE_AUTOPILOT_DEMO.md](docs/SAFE_AUTOPILOT_DEMO.md) — 5-minute offline demonstration narrative.
