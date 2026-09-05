@claude/project-brief.md

# Claude Code project instructions

## Start here

- Work from the repository root.
- Read `README.md`, `docs/ARCHITECTURE.md`, and `docs/BUILD_PLAN.md` before
  changing the authorization path.
- Treat the imported project brief as the authoritative product specification.
- Extend the existing Action Firewall direction. Do not restart ideation, pivot
  tracks, or rename the product without explicit user direction and evidence.
- Preserve user changes. Never discard, reset, or overwrite unrelated work.

## Non-negotiable authorization invariants

1. `POST /chat` is proposal-only and cannot dispatch a payment action.
2. The exact-confirmation baseline requires separate confirmation of the current cart
   hash. Safe Autopilot instead requires explicit activation of a canonical Purchase
   Envelope; only a final quote proven to be inside that envelope may derive an exact
   Action Grant without another cart approval.
3. Prices, totals, action arguments, and hashes are computed server-side.
4. All money uses integer paise; rupees are presentation only.
5. Current policy evaluation and headroom reservation are atomic.
6. Every grant is exact, expiring, one-use, and bound to actor, agent, session,
   cart, policy revision, action, arguments, amount, currency, and purchase attempt.
7. Only actions in the closed registry may reach a provider. The MVP registry
   contains only `create_payment_link`.
8. One compare-and-set dispatch owner may redeem a grant.
9. A definite provider rejection may release exposure. An ambiguous outcome must
   become `UNKNOWN`, retain exposure, and suppress blind redispatch.
10. `ACTION_ISSUED` is not payment, capture, settlement, or recovered revenue.
11. Audit evidence is append-only at the application database layer, not
    cryptographically immutable.
12. LLMs may draft envelopes, plan carts, rank eligible recoveries, and explain
    decisions. They may not activate authority, define trusted catalog facts, decide
    envelope membership, widen policy, mint grants, or dispatch actions.
13. An invalid candidate may be repaired only from a deterministic eligible set. If
    no eligible candidate exists, the system must present an exact Policy Delta or
    abort.

If a requested change weakens any invariant, stop and explain the conflict before
editing code.

## Product and evidence language

- User-facing terms: **Purchase Envelope**, **Policy Delta**, **Action Grant**, and
  **Action Receipt**. Existing `mandate` routes, tables, and Python names are
  compatibility debt, not a banking claim.
- Vulcan is strategic context only. Never claim a Vulcan API, SDK, model endpoint,
  partnership, or private Razorpay access.
- Never claim NPCI/UAP compliance, zero chargebacks, prevented fraud value, or
  settlement from payment-link creation.
- Label simulated, test-mode, and live-provider evidence separately.
- Keep first-party evidence, internal proof, secondary sources, inference, and
  unconfirmed claims distinct. Use `market-context.md` as the source ledger.

## Development workflow

1. Inspect `git status`, the current branch, recent commits, and active remote
   before editing.
2. Read the relevant implementation and tests before changing behavior.
3. Make one logical change at a time and add a deterministic regression test for
   every safety-boundary change.
4. Run the narrow tests while iterating, then the full verification below.
5. Before committing, verify the Git identity is Aryan Singh
   `<arajsingh0505@gmail.com>` and pull with rebase from the current upstream.
6. Use small commits with no `Co-Authored-By` or generated-AI attribution.
7. Never force-push, hard-reset, or clean untracked files.
8. Push only when the user asks or the task explicitly includes publishing.

## Verification

Backend:

```powershell
cd backend
python -m pytest -q
python -m compileall -q app tests scripts
python scripts/evaluate_autopilot.py
python scripts/demo_autopilot.py
python scripts/demo.py
```

Frontend:

```powershell
cd frontend
npm ci
npm run build
npm audit --audit-level=high
```

Before calling work complete, also run `git diff --check`, scan staged changes for
secrets, and confirm the working tree contains only intended changes.

## Secrets and external services

- Never read, print, log, stage, or commit actual `.env` files, API keys, merchant
  tokens, database files, or provider credentials.
- Keep deterministic offline fallbacks working. External services must not be
  required to prove the authorization invariants.
- Do not add `.mcp.json` with Razorpay credentials. Runtime Razorpay integration
  belongs behind the existing backend adapter and environment variables.

## Documentation discipline

- Update tests, `README.md`, `docs/ARCHITECTURE.md`, and the project brief together
  when a public contract or invariant changes.
- Keep test counts and demo amounts consistent across the README, script, HTML deck,
  and PowerPoint deck.
- Do not edit the binary deck unless the corresponding source claims and demo path
  are also reviewed.
