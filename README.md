# Action Firewall

### **[▸ Live demo](https://resplendent-kindness-production-4c97.up.railway.app/)** · Razorpay AI Buildathon — Track 01: AI Growth & Agentic Commerce

**A store that can safely say yes to an AI buyer.**

An AI agent shows up at your storefront holding a customer's money. Right now you get two options. Refuse it and lose the order, or take it and carry the liability when the agent buys the wrong thing.

There is no third option today, and that is not an oversight. RBI's liability framework covers *unauthorised* transactions. An agent acting inside a live customer mandate is authorised. So when it drifts — wrong merchant, wrong item, right budget — the customer has no chargeback and the merchant eats it.

This is the third option. The customer approves what the money is *for*, once. After that the store checks every purchase against that rule by itself, with no model in the loop, and can prove afterwards to someone who does not trust it that the check was right.

---

## What is actually different here

**You can re-run my authorisation decision yourself.** Every attempt saves a file containing everything the decision looked at: the approved rule, the words the customer read, the server-priced quote, the catalog facts, the stock count. Run `scripts/verify_dispute_pack.py` against it and the script re-executes the authorisation and compares its answer to the recorded one. No database. No signing key. No network. A merchant answering a chargeback can hand that file to the acquirer and be *checked* instead of believed.

Anything that asks a language model at authorisation time cannot do this. The samples that made its decision are gone the moment it answers.

**The customer approves a rule, not a sentence.** Their shopping goal gets compiled once into a Purchase Envelope — slots, tags, merchant, ceiling, expiry — and read back to them in plain English. That English is a pure function of the envelope, so anyone can recompute the exact words that were on screen. Not a log line saying they approved `env_9f3a`. The words themselves, derivable from the hash.

**And it shows you what the rule would let through, before you sign it.** "One item tagged `cheese`" looks harmless. The readback tells you it admits 3 items, ₹135 to ₹899, dearest being Parmigiano Reggiano. It also tells you your ₹7,840 ceiling is doing nothing, because the most expensive basket that rule permits is ₹527. Most "AI spending guardrails" *are* that ceiling. [§3.2](#32-policy-compliance-and-recovery-1100-cases) measures what one lets through.

Every number below is printed by a script that fails the build when it stops being true. That machinery exists because I published wrong numbers three times. [§8](#8-three-times-this-repository-was-wrong) is what broke.

| Where to look | |
|---|---|
| Authorization core | `backend/app/envelope.py`, `backend/app/store.py` |
| Evidence | `backend/app/consent.py`, `backend/app/dispute.py` |
| Check it yourself | `scripts/verify_dispute_pack.py` + [`docs/samples/dispute_pack.json`](docs/samples/dispute_pack.json) |
| Pitch deck | [docs/pitch-deck.html](docs/pitch-deck.html) |
| Run it locally | three commands, [§7](#7-run-it-three-commands-from-clean-clone) |

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

### 3.2 Policy compliance and recovery (1,100 cases)

50 fixed seeds × 22 failure families, grouped under ST-WebAgentBench's six policy dimensions, with 15 seeds held out until the numbers were final.

```powershell
python scripts/benchmark_agent_authorization.py --k 5
```

```text
Agent-authorization benchmark
  corpus                      1100 cases (50 seeds x 22 families), k=5
  composition                 250 legitimate / 850 constructed policy violations
  Completion under Policy     55.3%   (share of ALL proposals ending in a clean completed order)
    of legitimate proposals   100.0%
  replay identity (5x)      100.0%   (regression guard, not a reliability metric)
  violation escape rate       0.00%
  acceptance (compliant)      100.0%
  repair rate (of refused)    42.1%
  false-positive rate         0.00%
  false-positive cost         Rs 0.00
  value recovered by repair   Rs 186,669.00
  value that would have completed without the layer, in violation  Rs 821,184.72
  cap-only guard would let through  690 of 850 violations (81.2%)
  held out (15 unseen seeds)   escape 0.00%, false-positive 0.00%

  modelled cost of each configuration (assumptions, not measurements):
    no_layer             Rs    1,926,185
    cap_only_guard       Rs    1,296,340
    action_firewall      Rs     -179,509
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

**The row that matters is the comparator.** A spend cap is what almost every "AI spending guardrail" in the wild actually is, and it lets 690 of these 850 violations through. Zero escapes is only interesting next to that 81.2%.

The 250 legitimate proposals include near-miss families — carts sitting exactly on a boundary — so that a layer which simply refuses everything scores badly rather than perfectly. It refuses none of them.

### 3.3 Ablation: does every rule earn its place?

A layer that reports zero escapes tells you it works. It does not tell you which part is doing the work. This removes one rule at a time — by changing the envelope, never by patching the verifier — and **exits non-zero if any rule turns out never to change an outcome.**

```powershell
python scripts/ablation.py
```

```text
  ablation                            escaped     of     rate  note
  full_layer                                0    850     0.0%  every rule active — the shipped configuration
  no_ingredient_tag_rule                   50    850     5.9%  merchant sets no blocked_tags
  no_category_rule                         50    850     5.9%  merchant sets no blocked_categories
  no_spend_cap                             50    850     5.9%  cap raised beyond any cart in the corpus
  no_expiry                                50    850     5.9%  envelope never expires
  no_slot_requirements                    240    850    28.2%  slots accept almost anything
  no_stock_check                          100    850    11.8%  every shelf refilled, so availability never binds
  envelope_widened_and_rehashed           200    850    23.5%  ATTACK, not a setting: every rule removed and the digest recomputed

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
  purchase_envelope              350            150       Rs 89,880.00
  neither                        100             50       Rs 29,960.00
```

Of 850 constructed violations, **400 (47.1%) would never have been proposed** by an agent that fetched the merchant acceptance policy ([§5](#5-what-an-agent-can-read-before-it-proposes)) first. Of the 492 refusals no repair could rescue, 292 were preventable that way — **₹4,20,505 of orders that died for want of a rule the store already knew and never said.**

A further 350 were preventable from the customer's own Purchase Envelope, which the agent already holds. Those are counted **separately and not claimed for the endpoint**, because slots and quantities are per-customer and not the merchant's to publish. The remaining 100 are forged prices and forged digests: publication prevents mistakes, not attacks, and the script says so in its own output.

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

### Evidence endpoints

Three artifacts, each answering a different question a dispute actually asks.

```
GET  /evidence/consent/{envelope_id}            # what the customer was shown
GET  /evidence/dispute-pack/{attempt_id}        # everything one decision consumed  (merchant-admin only)
POST /evidence/dispute-pack/verify              # check a pack        (unauthenticated)
GET  /evidence/audit-chain/verify               # walk the audit hash chain (unauthenticated)
```

**The pack is merchant-only; the verifiers are public.** An integrity check nobody outside can run proves nothing, and a customer's basket and prices are not public. The two need opposite answers, and one implementation serves both the HTTP route and the CLI — two verifiers drift, and the drift gets found by whoever trusted the wrong one.

```powershell
python scripts/verify_dispute_pack.py docs/samples/dispute_pack.json
```

```text
VALID — every claim in this pack re-derives.

  Independently re-derived — no trust in the merchant required:
    - the rule the customer approved, and the words they were shown
    - the catalog facts the decision was taken against
    - the quote, and that the authority is bound to it
    - that the authority is bound to the approved rule and basket
    - that the receipt describes this authority
    - that the audit entries in this pack are linked
    - THE DECISION ITSELF — re-running it on these inputs gives this outcome

  Attested by the merchant, NOT proven:
    - stock at decision time — nobody can prove what was on a shelf; the audit
      chain fixes when the reading was recorded, not what it was
    - the receipt HMAC — needs the merchant's signing key
    - that a human read the sentence — unknowable from any artifact
```

Stock is the one input a third party cannot independently prove, so the obvious attack is to overstate it and claim the order should have gone through. It does not work: the decision is re-derived **from** the attested figure, so inflating it changes the re-derived outcome and the mismatch surfaces. `test_inflating_the_attested_stock_cannot_launder_a_refusal` is the assertion.

**Refusals are evidenced too** — the case a merchant most needs and an authorisation ledger structurally never keeps, because nothing was authorised to leave a row.

Walks the hash-linked audit entries from genesis and reports whether every entry's digest and predecessor pointer hold. It is unauthenticated so third parties can independently verify log integrity without holding application credentials. The honest limit: while interior edits, deletions, or reorderings break the chain and are locatable, truncating the tail leaves an internally consistent chain unless verified against an external `head_hash`.

---

## 6. What this is not (Honest Limits)

To preserve technical integrity, we state explicit boundaries:

- **Not an NPCI, UPI, or Banking Mandate:** The Purchase Envelope is an application-level permission container enforcing merchant-side semantic bounds. It does not replace card network rules or UPI rails.
- **Not a Private Vulcan Integration:** Vulcan is product context for intelligent routing and checkout optimization. This repository does not claim access to unreleased Vulcan APIs or internal Razorpay models.
- **Synthetic Correctness Evidence:** The 1,100-case corpus (850 of them constructed violations) measures synthetic deterministic authorization correctness under adversarial inputs. It does not claim measured human conversion, merchant revenue lift, or production settlement rates. Rupee figures are the face value of synthetic carts.
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

### 4. Or deploy it

Both halves ship as containers — `backend/Dockerfile` and `frontend/Dockerfile`,
with `railway.json` and `frontend/railway.json` pinning the build for each. The
deployed instance runs the real authorization engine against the **simulated**
provider: no Razorpay key is baked into either image, `.dockerignore` keeps
`.env` and `*.db` out of the build context, and `/health` reports the active
provider so the claim is checkable from outside. See [DEPLOY.md](DEPLOY.md).

---

---

## 8. Three times I published something wrong

Every number above comes out of a script that fails the build when it stops being
true. I did not build that because I am careful. I built it because I kept
getting caught.

### 8.1 The 88% that was really 47%

For about two days the best number in this project was that **88% of policy
violations would never have been proposed** by an agent that read the merchant's
published rules first. I liked that number a lot. I put it in the pitch.

It was wrong, and the reason is boring. I had counted two different things as one.
Some violations break a rule the *merchant* publishes — a blocked category, an
order ceiling. Others break a rule from the *customer's own* Purchase Envelope —
a slot, a quantity. The second kind is per-customer. No merchant policy could
ever have prevented them. Folding them together made publishing look almost twice
as useful as it is.

I did not fix it by editing the number. I wrote `scripts/publication_value.py`,
which recomputes it from the corpus on every CI run and reports the two channels
in separate rows so nobody can add them up again by accident. The docstring says
what the old number was and why it was wrong, because deleting that felt like
cheating. The real figure is in [§3.5](#35-what-publishing-the-rules-is-worth),
and it moves when the corpus grows. That is the point.

### 8.2 pip had never once installed this project

First deploy. Build failed:

```
requirements.txt pins   pydantic==2.10.4
mcp==1.27.0 requires    pydantic>=2.11.0,<3.0.0
```

There is no version of pydantic that satisfies both. Not a version conflict I
introduced that day. `pip install -r requirements.txt` had never worked, at any
commit, in the entire history of the repository.

It survived because nobody had ever tried. My machine already had a much newer
stack sitting in it — fastapi 0.141 against a pinned 0.115, pydantic 2.13 against
a pinned 2.10, pinecone 10 against a pinned 5. Every local run I had ever done
used packages the file did not describe. `hypothesis` was not even listed, and
`tests/test_authorization_properties.py` imports it. The first environment to
read that file honestly was the deployment, and it refused.

Fixing the pins was ten minutes. The part that mattered took longer: building a
clean CPython 3.11.15 virtualenv — the version `backend/Dockerfile` and CI both
use, and which had therefore never actually run the test suite, because install
failed before pytest could start — installing from scratch, and running
everything there.

### 8.3 The verifier caught me, not an attacker

I wrote `scripts/verify_dispute_pack.py` to catch a merchant doctoring evidence.
I ran it on the first pack I generated. Completely honest pack, straight out of
the code I had just written. It failed:

```
FAILED — this evidence pack does not hold up.
  check     grant.envelope_hash
  reason    the authority is bound to a different rule from the one the customer approved
```

The pack builder was rebuilding the consent record from `get_envelope(id)` —
whatever that envelope looks like *now*. A consumed envelope has a bumped version
and a new hash. So the pack's own consent record and its own grant disagreed
about which rule the customer had approved.

Every evidence pack I would ever have shipped would have failed the moment anyone
checked it. And it would have failed looking exactly like fraud.

The envelope as it stood at decision time is now stored in `decision_records` and
used to build the pack. The bug lived about ninety seconds, and only because I
had written the verifier to assume the pack in front of it is a forgery —
including when the forger is me.

### 8.4 The one that never shipped

Two writers appending to the audit chain read the same tail and compute the same
`prev_hash`. Now there are two entries claiming the same predecessor, both
internally valid, and no way afterwards to say which one is the real history.

On a single-threaded demo this never appears. `UNIQUE(seq)` turns the fork into a
constraint violation the losing writer retries.
`test_concurrent_writers_produce_one_chain_not_two` starts four threads, appends
ten events each, and asserts exactly forty linked entries.

Same reasoning is why authorisation and reservation are one `BEGIN IMMEDIATE`
transaction instead of two steps.
[§3.4](#34-concurrency-does-the-cap-hold-when-orders-collide) shows what the
obvious version does: a ₹1,000 cap authorising ₹3,150 of orders, in every single
trial.

### The pattern

I did not find any of these by reading my own code carefully. I found them by
building things whose whole job is to disagree with the thing that made them — a
script that recomputes a claim instead of quoting it, a clean environment that
has never seen my laptop, a verifier that assumes the evidence is fake.

Which is the same argument the product makes. Evidence you can re-run beats
assertion you have to trust. It applies to me first.


## Technical Reference & Artifacts

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — Implemented trust boundaries, lifecycle state machine, and data schema.
- [docs/EVALUATION.md](docs/EVALUATION.md) — Benchmark methodology, statistical definitions, and error taxonomies.
- [docs/pitch-deck.html](docs/pitch-deck.html) — Standalone presentation deck with live verifiable metrics.
- [docs/SAFE_AUTOPILOT_DEMO.md](docs/SAFE_AUTOPILOT_DEMO.md) — 5-minute offline demonstration narrative.
