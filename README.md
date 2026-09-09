# Action Firewall — AI Commerce Permissions

**Razorpay AI Buildathon — Track 01: AI Growth & Agentic Commerce**

**Live Demo:** [action-firewall.vercel.app](https://action-firewall.vercel.app) · **Documentation & Pitch:** [docs/pitch-deck.html](docs/pitch-deck.html)

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

The suite has **316 passing backend tests** (344 parametrized test cases, 0 failures).

### Policy Compliance & Recovery Benchmark (900 Cases)

Evaluated across 18 failure families and 50 fixed random seeds ($k=5$ repetitions per fixture), covering ST-WebAgentBench's six security dimensions with held-out seed evaluation:

```text
python scripts/benchmark_agent_authorization.py --k 5
```

```text
Agent-authorization benchmark
  corpus                      900 cases (50 seeds x 18 families), k=5
  composition                 250 legitimate / 650 constructed policy violations
  Completion under Policy     56.4%   (share of ALL proposals ending in a clean completed order)
    of legitimate proposals   100.0%
  replay identity (5x)      100.0%   (regression guard, not a reliability metric)
  violation escape rate       0.00%
  acceptance (compliant)      100.0%
  repair rate (of refused)    39.7%
  false-positive rate         0.00%
  false-positive cost         Rs 0.00
  value recovered by repair   Rs 126,749.00
  value that would have completed without the layer, in violation  Rs 653,944.72
  cap-only guard would let through  540 of 650 violations (83.1%)
  held out (15 unseen seeds)   escape 0.00%, false-positive 0.00%

  modelled cost of each configuration (assumptions, not measurements):
    no_layer             Rs    1,498,945
    cap_only_guard       Rs      964,060
    action_firewall      Rs     -121,589
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

### Concurrency Benchmark: Headroom Under Contention (16 Threads, 20 Trials)

Measures check-then-act race conditions when concurrent orders collide under a thread barrier:

```text
python scripts/benchmark_concurrency.py --threads 16 --trials 20
```

```text
Concurrency benchmark — does the cap hold when orders collide?
  cap Rs 1,000  ·  order Rs 200  ·  5 fit inside  ·  16 arrive at once  ·  20 trials

  read-compare-write
    trials that breached the cap   20/20  (100%)
    mean orders authorised          15.4  (only 5 fit)
    mean overspend                  Rs 2,080.00
    worst overspend                 Rs 2,200.00
    total overspend across trials   Rs 41,600.00

  authorize-and-reserve
    trials that breached the cap   0/20  (0%)
    mean orders authorised          5  (only 5 fit)
    mean overspend                  Rs 0.00
    worst overspend                 Rs 0.00
    total overspend across trials   Rs 0.00

  Local SQLite, one process, threads through a barrier. Measures one specific race: check-then-act on a shared budget. Does not measure network partitions, provider duplicates, or clock skew. The read-compare-write arm is a faithful reproduction of the common pattern, written here, not copied from anyone's repository.
```

---

## 4. Architecture: Five Structural Guarantees

Action Firewall decouples probabilistic AI planning from deterministic payment authorization through five architectural invariants:

1. **Closed Action Registry:** Only registered, strictly schema-validated actions can reach an external payment provider. The current registry supports `create_payment_link` (Track 01 inbound payment creation) and `refund` (outbound merchant protection, treated as future-scope proof in the roadmap).
2. **Exact One-Use Action Grant:** A grant is exact, expiring, and cryptographically bound to actor identity, buyer agent, session, merchant, attempt ID, cart hash, quote hash, envelope version and hash, action schema, amount in integer paise, and currency.
3. **Atomic Authorize-and-Reserve:** Policy evaluation and financial balance reservation occur atomically inside a `BEGIN IMMEDIATE` database transaction. If authority checks pass, exposure is locked before any actuator is invoked.
4. **Single CAS Dispatch Owner:** A single compare-and-set ownership transition redeems the grant immediately prior to dispatch. Double-spending, thread races, and duplicate payment links are eliminated.
5. **Authoritative `UNKNOWN` Outcome Semantics:** When an actuator call times out or returns an ambiguous status, the state transitions to `UNKNOWN`. Reserved headroom remains held, exposure is protected, and automated blind retries are suppressed until reconciliation.

---

## 5. What this is not (Honest Limits)

To preserve technical integrity, we state explicit boundaries:

- **Not an NPCI, UPI, or Banking Mandate:** The Purchase Envelope is an application-level permission container enforcing merchant-side semantic bounds. It does not replace card network rules or UPI rails.
- **Not a Private Vulcan Integration:** Vulcan is product context for intelligent routing and checkout optimization. This repository does not claim access to unreleased Vulcan APIs or internal Razorpay models.
- **Synthetic Correctness Evidence:** The 900-case and 650-case benchmarks measure synthetic deterministic authorization correctness under adversarial inputs. They do not claim measured human conversion, merchant revenue lift, or production settlement rates.
- **Cost Model Assumptions:** The economic model uses stated assumptions across merchant margins and dispute costs to demonstrate relative ordering robustness under parameter sweeps; it is not derived from audited financial books.
- **Reserve Pay Integration:** There is currently no public Reserve Pay API. We model its operational and semantic characteristics based on published NPCI circulars and circular guidelines.

---

## 6. Run it (Three Commands from Clean Clone)

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
```

---

## Technical Reference & Artifacts

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — Implemented trust boundaries, lifecycle state machine, and data schema.
- [docs/EVALUATION.md](docs/EVALUATION.md) — Benchmark methodology, statistical definitions, and error taxonomies.
- [docs/pitch-deck.html](docs/pitch-deck.html) — Standalone presentation deck with live verifiable metrics.
- [docs/SAFE_AUTOPILOT_DEMO.md](docs/SAFE_AUTOPILOT_DEMO.md) — 5-minute offline demonstration narrative.
