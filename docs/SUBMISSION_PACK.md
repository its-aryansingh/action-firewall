# Submission pack — Action Firewall

Everything needed to submit today. The repo is verified (see
`PRE_SUBMISSION_AUDIT.md`); what remains is the form, the video, and two small
README fixes.

---

## 0. Do this first, before anything else

**The form is live right now** and it is genuinely Razorpay's — it self-identifies
as *"This form was created inside of Razorpay."*

<https://forms.gle/d9r2gvxp8cmoZhon9>

Razorpay publishes **no deadline** — not on the site, not on the form. A "5
September" date circulates widely, but every carrier is an SEO job-aggregator, none
cites a source, and sites published the same week say flatly that no date has been
announced. It has the signature of one site inventing a plausible date and the rest
copying it.

**Assume it is real anyway.** It costs nothing to submit early and everything to be
wrong. There is no version of this where waiting helps.

**Hard gate to check first:** the graduation-year dropdown offers only **2027, 2028,
2029**. If yours is outside that range, there is no path through this form and the
rest of this document is moot.

---

## 0.5 Rename the GitHub repo before you paste the link

The remote is:

    https://github.com/its-aryansingh/razorpay-uap-mandate-agent

The product is **Action Firewall**. `SUBMISSION_STRATEGY.md` records the rename away
from "UAP Mandate Verification" specifically to avoid claiming a banking mandate or
a protocol implementation — and then the URL a reviewer clicks first says
`uap-mandate-agent`.

That is the one place the submission still contradicts its own carefully-drawn
line, and it is the *first* thing a reviewer sees. Rename it to something like
`action-firewall`. GitHub redirects the old URL automatically, so nothing breaks;
just re-point your local remote afterwards:

```powershell
git remote set-url origin https://github.com/its-aryansingh/action-firewall.git
```

Also check the repo **description and topics** on GitHub for stale UAP/mandate
wording — the description shows in search results and link previews.

---

## 1. Form answers, drafted

Field names from a third-party enumeration of the later pages — the live form is
authoritative, so adapt wording to what it actually asks.

### Track
**Track 01 — AI Growth & Agentic Commerce**

### Project name
**Action Firewall**

### Problem you are solving

> AI shopping collapses discovery, recommendation and checkout into one
> conversation, which creates authority ambiguity: a model can misread intent, act
> on a stale cart, cross a spending cap under concurrency, retry after a timeout, or
> substitute tool arguments at the boundary. A prompt instruction is not an
> authorization guarantee.
>
> Action Firewall puts a deterministic authorization boundary between an AI shopping
> agent and Razorpay's payment tools. The model may search the catalog and assemble
> a cart. It cannot approve spend, mint its own authority, change payment arguments
> after approval, or dispatch a payment action from chat. The shopper confirms one
> exact cart; the backend re-reads the current policy and reserves headroom
> atomically; only then can one registered action be dispatched exactly once.

### Public repo
Paste the GitHub URL. **Open it in a logged-out incognito window first** — a repo
the reviewer cannot open is the most mundane way to lose, and it is on Colosseum's
named list of fatal submission mistakes.

### Pitch video
See §2. Same incognito check on the link.

### What broke, and how you fixed it

This field is a gift for this project. Answer with the concurrency race — it is a
real defect, it was caught by a test, and the failing test is still in the repo.

> The authorization path was originally check-then-act: evaluate the policy, then
> call Razorpay. Between those two steps nothing held the headroom, so two
> concurrent purchase attempts could both read the same remaining cap and both
> spend it.
>
> I reproduced it deterministically rather than reasoning about it. Eight threads
> released through a barrier against a ₹1,000 cap settle **₹2,400** — stable across
> every run. That test is still in the repository, and it is written to fail if the
> race ever stops reproducing, so the regression cannot quietly disappear.
>
> The fix is a two-phase reservation. Policy evaluation and headroom reservation now
> happen inside one `BEGIN IMMEDIATE` transaction, so a live reservation counts
> against the cap while the provider call is in flight; it commits on success and is
> released on definite failure. Eight concurrent ₹300 requests against the same
> ₹1,000 cap now settle exactly ₹900.
>
> Fixing it surfaced two more defects the first fix had hidden. The idempotency key
> was scoped to the policy rather than the purchase attempt, so two shoppers with
> identical carts collided and the second was handed the first one's payment link.
> And the idempotency check ran *behind* the cap check, so a legitimate retry of an
> already-settled purchase was blocked by the cap its own spend had just filled.
> Both were found by tests written after the first fix looked complete.

That last paragraph is the strongest thing in the whole answer. Finding bugs *in
your own fix* is the single clearest signal that the work is real.

### Preferred duration
Whichever you actually want. Do not hedge.

### Resume
Attach it. The "no resume screening" line means resumes do not gate the screen, not
that the field is absent.

---

## 2. Video storyboard — 5:00

Judges form an opinion in the first 30 seconds and spend the rest looking for
evidence to support it. So the first shot is the product failing safely, not a title
card and not a problem slide.

Record against the **offline rehearsal** (`DEMO_MODE=true`, no network, no keys).
This is the correct recording surface, and say so on camera — a demo that survives
with the network unplugged is a stronger claim than one that needs live keys.

| Time | Shot | What you say |
|---|---|---|
| **0:00–0:25** | Terminal, mid-run. The ₹2,034 cart hits the boundary and is denied. The actuator line reads BLOCKED. No title card. | "This agent just tried to spend ₹2,034 against a ₹1,000 policy. The payment tool was never called. Not because the model was told not to — because it structurally cannot." |
| 0:25–0:50 | Cut to the trust-boundary diagram in the README. | One sentence: a model is not a payment principal. Chat proposes; a separate deterministic boundary authorizes. |
| 0:50–1:40 | The recovery. Cart drops to ₹486, shopper confirms the **exact cart hash**, link is issued. Point at the hash on screen. | "Confirmation is exact. The hash binds this approval to this cart — change one line item and the approval is void." |
| 1:40–2:40 | Code: the grant. Show what it binds — actor, agent, session, purchase attempt, policy revision, cart hash, action name, canonical arguments, amount, currency. | "This is not a boolean allow. It is one exact, expiring, one-use grant for one registered action. It cannot be replayed and its arguments cannot be substituted." |
| 2:40–3:25 | The closed registry (`actions.py`). Show that `create_payment_link` is the only entry. | "The MCP surface has dozens of consequential tools. One is registered. Anything else is rejected at the boundary, not filtered by a prompt." |
| 3:25–4:15 | **The proof.** `pytest -q` → 61 passed. Then the concurrency result: naive ₹2,400 vs reserved ₹900. | "The old design is still in the repo as a failing-by-design test. ₹2,400 against a ₹1,000 cap. The fix caps it at ₹900." |
| 4:15–4:45 | The evidence block from the demo run. Point at `confirmed_test_payment_value_paise: 0`. | "Issuing a link is not payment. We record ACTION_ISSUED, and we report zero confirmed payment, because that is the truth." |
| 4:45–5:00 | Honest limitations, straight to camera. | Name two: browser identity is a stub; no background reconciler yet. Then close on the thesis. |

**Do not** open on slides, spend more than ~30% on the problem, or let the run take
a path you have not rehearsed three times. Lock the code before recording.

### What to emphasise, given the field

Only two public competitor repos exist, and one of them —
`srikrishna0603/razorpay-buildathon`, "Revenue Resilience AI" — has substantially
your thesis: LLM proposes, deterministic engine disposes, atomic locks, idempotency
against double-charges, adversarial tests. It is aimed at Track 03, not yours, but
assume a reviewer may see both.

Your four genuine differentiators, and the video should name each explicitly:

1. **Cart-hash binding per purchase attempt** — approval is void the moment the cart
   changes, not merely rate-limited.
2. **One-use expiring grants bound to a policy revision** — a policy edit invalidates
   in-flight authority; most designs only re-read the policy.
3. **A closed action registry** — one registered action, not a filtered pass-through
   of the MCP surface.
4. **`UNKNOWN` retains exposure** — an ambiguous provider outcome does not free
   headroom and suppresses blind redispatch. This is the subtlest of the four and
   the most expensive to get right; give it a full sentence.

---

## 3. Two README fixes before you paste the link

**Move the "Continue with Claude Code" section.** It currently sits at line 134,
between *Quick start* and *Demo proof* — exactly where a reviewer is deciding
whether the implementation is real. Twenty-three lines of AI-tooling setup at that
position invites the "polished presentation masking thin implementation" read that
Devpost's judging panel names as a top red flag. This is not about concealing how it
was built; it is about README real estate. Move it to `docs/` or the bottom, and let
*Quick start* run straight into *Demo proof*.

**Put the architecture diagram above the fold.** Razorpay asks for "the
architecture" but the form has no field for it, so by elimination it has to live in
the repo and the video. Your *Trust boundary* diagram is the right artifact and it
is already in the README — just make sure a reviewer meets it before they meet
anything else. Both public competitor repos independently lead with theirs.

---

## 4. Pre-flight checklist

- [ ] Graduation year is 2027, 2028 or 2029
- [ ] `pytest -q` → 61 passed, from a clean clone
- [ ] `python scripts/demo.py` → REHEARSAL PASSED, three times running
- [ ] Repo is **public** and opens in a logged-out incognito window
- [ ] Video link plays logged-out
- [ ] README architecture diagram is above the fold
- [ ] Repo renamed away from `uap-mandate-agent`; GitHub description and topics updated
- [ ] Form submitted

**Secret hygiene: verified clean.** `*.db`, `.env` and `.env.local` are gitignored,
`backend/mandates.db` is untracked, and a full-history scan (`git log --all
--name-only`) finds no `.db` or `.env` file ever committed across all 28 commits.
Nothing to fix here.

`docs/research-history/` is currently untracked. That is a reasonable call — it is
working material rather than submission evidence — but decide deliberately rather
than by accident, since `SUBMISSION_STRATEGY.md` links to it as provenance.
