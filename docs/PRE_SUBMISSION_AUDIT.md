# Pre-submission audit — Action Firewall

**Audited:** 3 September 2026, from a clean copy of the repository, in an isolated
Linux container with no access to the original working tree.

**Verdict: the submission is sound. Stop building and submit.**

## What was verified independently

| Claim | Where claimed | Result |
|---|---|---|
| 51 tests pass | README, BUILD_PLAN, project brief, both decks | **PASS** at audit time — `51 passed`. Now **54** after the adversarial pass added three regressions; see `AUDIT_FINDINGS.md`. All artifacts updated. |
| Offline rehearsal passes with no network or keys | DEMO_SCRIPT, SUBMISSION_STRATEGY | **PASS** — `REHEARSAL PASSED`, all four acts |
| Naive check-then-act records ₹2,400 against a ₹1,000 cap | README, project brief, DEMO_SCRIPT | **PASS** — ₹2,400 exactly, 12 trials out of 12 |
| Atomic reservation caps 8 concurrent ₹300 requests at ₹900 | README, project brief | **PASS** — 10 concurrency tests green |
| Denial → recovery → issuance arc (₹2,034 → ₹486) | DEMO_SCRIPT, both decks | **PASS** — reproduced exactly |
| Evidence block is honest about payment state | Invariant 10 | **PASS** — reports `payment_link_issued_value_paise`, `outstanding_authorized_exposure_paise`, `confirmed_test_payment_value_paise: 0`. No settlement claimed. |

### Demo run, verbatim

```json
{
  "authorization_attempts": 3,
  "authorization_denial_rate": 0.6667,
  "cart_policy_previews": 5,
  "confirmed_test_payment_value_paise": 0,
  "denied_authorizations": 2,
  "denied_requested_value_paise": 258300,
  "outstanding_authorized_exposure_paise": 48600,
  "payment_link_issued_value_paise": 48600,
  "unauthorized_actuator_calls": 0,
  "unknown_outcome_value_paise": 0
}
```

## Claim-consistency sweep

`CLAUDE.md` requires test counts and demo amounts to agree across the README, the
script, the HTML deck and the PowerPoint deck. They do.

- Test count: **54** in README, BUILD_PLAN, project brief, SUBMISSION_STRATEGY,
  HTML deck and PPTX slide 10. The earlier **51** in the audit table is explicitly
  labelled as the isolated audit-time result before the three regression tests
  were added. The `49` in SUBMISSION_STRATEGY is a changelog row recording that
  stale references were fixed — correct as written.
- Amounts: `₹1,000` cap, `₹2,034` denied, `₹486` issued, `₹549` post-revocation,
  `₹2,583` denied total. Identical across DEMO_SCRIPT, SUBMISSION_STRATEGY, HTML
  deck and PPTX slides 1 and 7.
- PPTX is 10 slides and carries no number the runtime does not produce.

## Overclaim sweep

Scanned README, all `docs/*.md`, the HTML deck and the frontend for the language
`CLAUDE.md` forbids: UAP/NPCI compliance, zero chargebacks, prevented fraud value,
settlement from link creation, and any Vulcan API, SDK, partnership or private
access.

**Every hit is a prohibition, not a claim.** The docs instruct against exactly these
framings. No violation found in any user-facing artifact.

## One precision note

`README.md:175` states the naive path "can record ₹2,400 against a ₹1,000 cap". The
test asserts the weaker invariant (`committed > CAP_PAISE`), which is the right
engineering choice — pinning an exact figure on a thread race invites flakes on a
loaded machine. Empirically ₹2,400 held in 12 of 12 trials here, so the claim is
safe. If a reviewer's run shows ₹2,100, the wording already permits it ("can
record"). No change needed; recorded so nobody is surprised on camera.

## Submission logistics — the one existential item

The buildathon page publishes **no deadline**. It does publish the application
route:

> "Four steps: pick a track, build something real, show your work (a public repo,
> a 5 minute pitch video, the architecture), and if it has signal we call you in."

Form: <https://forms.gle/d9r2gvxp8cmoZhon9>

Positions are stated as starting "in-person (Bangalore, from September)". September
has begun. **The marginal value of another feature is now lower than the marginal
risk of submitting late.**

## What is still genuinely missing, ranked

From `SUBMISSION_STRATEGY.md`'s own list, re-ranked by value per remaining hour:

1. **The five-minute video.** Not started. Nothing else moves the outcome as much,
   and the repo is ready to be filmed today.
2. **Broad multi-model adversarial corpus.** The one substantive proof gap. Genuinely
   differentiating, but it is a build item — attempt only after the video exists and
   the form is submitted.
3. **Provider reconciliation** (signed webhook consumer). Architecturally correct,
   invisible in a five-minute video. Post-submission.
4. **Cryptographic audit evidence** (hash chaining). Same.
5. **Production identity and tenancy.** Correctly scoped out; say so on camera rather
   than building it.

## Recommended order for the remaining time

1. Fill in the form. Repo link, architecture link, video link — even if the video
   URL is added by editing the response afterwards, if the form allows it.
2. Record the video against `docs/DEMO_SCRIPT.md`. Open on the denial, not on
   slides. Run the rehearsal three times first.
3. Publish the repo and confirm it is public and clones clean.
4. Only then, if time genuinely remains, add the adversarial corpus.

## On the Track 03 alternative

An earlier strategy pass in a separate session recommended pivoting to a Track 03
mandate-retry-sequencer. `SUBMISSION_STRATEGY.md` already rebuts that on readiness,
overlap with Razorpay's documented Smart Payment Retries, and the absence of a
public retry-sequencing action surface. That rebuttal is correct and this audit does
not reopen it. `CLAUDE.md`'s rule against unprompted pivots should hold.
