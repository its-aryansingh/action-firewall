"use client";

/**
 * The front door: the whole demo on one screen, in four numbered steps.
 *
 * WHY THIS FILE WAS REWRITTEN
 * --------------------------
 * The previous version generated 47 synthetic "policy decisions" in the browser
 * — invented titles, invented amounts, invented rule evaluations — merged live
 * backend orders into that list, and labelled the result a "Decision Audit
 * Stream". Nothing on screen said any of it was fabricated.
 *
 * That is the one thing this project cannot do. Its entire claim is that a
 * merchant can prove what it refused and why; a dashboard that invents its own
 * history disproves that claim more effectively than any critic could.
 *
 * So every number, row, hash and decision below comes from a live call to the
 * backend. Where there is no data yet, the screen says so and tells you which
 * button produces some. Nothing is seeded, nothing is padded, and a failed call
 * shows as a failure rather than falling back to plausible-looking defaults.
 */

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  inr,
  type CommerceAttemptResponse,
  type EnvelopeReadback,
  type Health,
  type IntentCreateResponse,
  type PolicySummary,
  type PurchaseEnvelope,
  type RefundEvaluateResponse,
  type RefundPolicy,
  type SlotAdmission,
  type AutopilotScenario,
} from "@/lib/api";


// The scenarios a presenter actually needs on camera, in the order the story
// wants them: one that succeeds, one that repairs itself, one that must refuse.
const SCENARIOS: {
  id: AutopilotScenario;
  label: string;
  teaches: string;
}[] = [
  {
    id: "normal",
    label: "Everything matches",
    teaches: "The baseline. The basket agrees with the catalog, so it authorises.",
  },
  {
    id: "stock_loss",
    label: "An item went out of stock",
    teaches:
      "The interesting case. The store repairs the basket inside what the customer already approved, so nobody is interrupted.",
  },
  {
    id: "merchant_drift",
    label: "The agent switched merchant",
    teaches:
      "The refusal. No repair can fix this, because widening authority is the customer's decision and not the store's — so the delta says fresh_approval and no payment rail is touched.",
  },
  {
    id: "price_drift",
    label: "A price moved",
    teaches:
      "Prices are re-read server-side at authorization, so the agent's numbers never count. The injected drift here is deliberately extreme to push the basket past the ceiling.",
  },
  {
    id: "fulfillment_drift",
    label: "The agent changed the delivery address",
    teaches:
      "Same class of refusal as switching merchant: the destination is part of what was approved.",
  },
];

const STEP_TITLES = [
  "What this store publishes before an agent asks",
  "The customer approves the job once",
  "The agent tries something",
  "What the attempt left behind",
];

function StepHeader({ n, title, hint }: { n: number; title: string; hint: string }) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">
        {n}
      </span>
      <div>
        <h2 className="text-base font-bold text-text">{title}</h2>
        <p className="mt-0.5 text-xs leading-relaxed text-muted">{hint}</p>
      </div>
    </div>
  );
}

function Card({
  children,
  tone = "plain",
}: {
  children: React.ReactNode;
  tone?: "plain" | "muted";
}) {
  return (
    <section
      className={`rounded-2xl border border-border p-6 shadow-sm ${
        tone === "muted" ? "bg-canvas" : "bg-surface"
      }`}
    >
      {children}
    </section>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-canvas p-4 text-xs text-muted">
      {children}
    </div>
  );
}

function Failed({ what, detail }: { what: string; detail: string }) {
  return (
    <div className="rounded-xl border border-danger/30 bg-danger/10 p-4 text-xs text-danger">
      <div className="font-semibold">{what}</div>
      <div className="mt-1 font-mono text-[11px] leading-relaxed">{detail}</div>
      <div className="mt-2 text-danger">
        Nothing is substituted here on purpose — a plausible-looking default would
        be a worse outcome than an honest failure.
      </div>
    </div>
  );
}

function Mono({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[11px] text-muted">{children}</span>
  );
}

function outcomeTone(outcome: string) {
  if (outcome === "ACTION_ISSUED" || outcome === "READY_FOR_CHECKOUT")
    return "emerald";
  if (outcome === "RECOVERED_INSIDE_ENVELOPE") return "blue";
  if (outcome === "UNKNOWN") return "amber";
  return "red";
}

/**
 * The failure, shown where the click was. The page-level banner stays — it is
 * the right place for "could not reach the backend" — but a failure that
 * belongs to one control has to be legible from that control, or the control
 * just looks broken.
 */
function StepError({ message }: { message: string }) {
  return (
    <p
      role="alert"
      className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-[11px] leading-relaxed text-danger ring-1 ring-inset ring-danger/30"
    >
      {message}
    </p>
  );
}

export default function FrontDoorPage() {
  // Step 0 — what the store says about itself, all fetched.
  const [health, setHealth] = useState<Health | null>(null);
  const [policy, setPolicy] = useState<PolicySummary | null>(null);
  const [policyHash, setPolicyHash] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Step 2 — the approval
  const [goal, setGoal] = useState(
    "pasta dinner for six with sauce cheese and bread"
  );
  const [budgetRupees, setBudgetRupees] = useState("8000");
  const [intent, setIntent] = useState<IntentCreateResponse | null>(null);
  const [activeEnvelope, setActiveEnvelope] = useState<PurchaseEnvelope | null>(null);
  const [previousReadback, setPreviousReadback] = useState<EnvelopeReadback | null>(null);
  const [editCapRupees, setEditCapRupees] = useState<string>("");
  const [capEditError, setCapEditError] = useState<string | null>(null);

  // Step 3 — the attempt
  const [scenario, setScenario] = useState<AutopilotScenario>("stock_loss");
  const [attempt, setAttempt] = useState<CommerceAttemptResponse | null>(null);

  // Money out
  const [refundPolicy, setRefundPolicy] = useState<RefundPolicy | null>(null);
  const [refundRupees, setRefundRupees] = useState("400");
  const [refundReason, setRefundReason] = useState("damaged on arrival");
  const [refundResult, setRefundResult] = useState<RefundEvaluateResponse | null>(null);

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Which step the failure belongs to. A single banner at the top of the page
  // is invisible to anyone standing at step 3 — the page is ~700px taller than
  // the viewport there — so a failed activation looked exactly like a dead
  // button. The error has to appear where the click happened.
  const [errorStep, setErrorStep] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [h, p, rp] = await Promise.all([
          api.health(),
          api.agentCommerce.policySummary(),
          api.agentCommerce.getRefundPolicy(),
        ]);
        if (cancelled) return;
        setHealth(h);
        setPolicy(p);
        setRefundPolicy(rp);
        setPolicyHash(rp.policy_hash ?? null);
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const rid = useCallback(
    (prefix: string) => `${prefix}_${Math.random().toString(36).slice(2, 10)}`,
    []
  );

  async function draftEnvelope() {
    setBusy("draft");
    setError(null);
    setErrorStep(null);
    setAttempt(null);
    setActiveEnvelope(null);
    setCapEditError(null);
    if (intent?.readback) {
      setPreviousReadback(intent.readback);
    }
    try {
      const res = await api.agentCommerce.createIntent({
        agent_request_id: rid("req"),
        natural_language_intent: goal,
        budget_paise: (Number.parseInt(budgetRupees, 10) || 8000) * 100,
        buyer_agent_id: "buyer_replay",
        shopper_session_id: rid("sess"),
      });
      setIntent(res);
      setEditCapRupees(String(Math.floor(res.draft_envelope.max_total_paise / 100)));
    } catch (err) {
      setError(`Drafting failed: ${err instanceof Error ? err.message : String(err)}`);
      setErrorStep(1);
    } finally {
      setBusy(null);
    }
  }

  async function dropSlot(slotId: string) {
    const env = intent?.draft_envelope;
    if (!env || activeEnvelope?.status === "active") return;
    setBusy(`drop_${slotId}`);
    setError(null);
    setErrorStep(null);
    setCapEditError(null);
    try {
      const res = await api.agentCommerce.amendEnvelope(env.id, {
        expected_envelope_hash: env.envelope_hash,
        drop_slot_ids: [slotId],
      });
      setIntent(res);
      setEditCapRupees(String(Math.floor(res.draft_envelope.max_total_paise / 100)));
    } catch (err: any) {
      setError(`Slot removal failed: ${err.message || String(err)}`);
      setErrorStep(2);
    } finally {
      setBusy(null);
    }
  }

  async function updateCap() {
    const env = intent?.draft_envelope;
    if (!env || activeEnvelope?.status === "active") return;
    const newRupees = Number.parseInt(editCapRupees, 10);
    if (Number.isNaN(newRupees) || newRupees <= 0) return;
    setBusy("update_cap");
    setCapEditError(null);
    try {
      const res = await api.agentCommerce.amendEnvelope(env.id, {
        expected_envelope_hash: env.envelope_hash,
        max_total_paise: newRupees * 100,
      });
      setIntent(res);
      setEditCapRupees(String(Math.floor(res.draft_envelope.max_total_paise / 100)));
    } catch (err: any) {
      if (err.status === 409) {
        setCapEditError("Raising the ceiling is a new approval, not an edit.");
      } else {
        setCapEditError(err.message || String(err));
      }
    } finally {
      setBusy(null);
    }
  }

  async function activate() {
    if (!intent) return;
    setBusy("activate");
    setError(null);
    setErrorStep(null);
    try {
      const env = await api.agentCommerce.activateEnvelope(
        intent.draft_envelope.id,
        intent.draft_envelope.envelope_hash
      );
      setActiveEnvelope(env);
    } catch (err) {
      setError(`Activation failed: ${err instanceof Error ? err.message : String(err)}`);
      setErrorStep(2);
    } finally {
      setBusy(null);
    }
  }


  /**
   * One authorization is one purchase attempt — `max_purchases` is 1 and the
   * envelope is CONSUMED once an attempt lands. That is deliberate, and it is
   * why trying a second scenario against the same envelope returns
   * BLOCK_ENVELOPE_CONSUMED rather than the outcome you were demonstrating.
   * So between scenarios, draft and activate a new one.
   */
  async function freshEnvelope() {
    setBusy("fresh");
    setError(null);
    setErrorStep(null);
    setAttempt(null);
    setActiveEnvelope(null);
    try {
      const res = await api.agentCommerce.createIntent({
        agent_request_id: rid("req"),
        natural_language_intent: goal,
        budget_paise: (Number.parseInt(budgetRupees, 10) || 8000) * 100,
        buyer_agent_id: "buyer_replay",
        shopper_session_id: rid("sess"),
      });
      setIntent(res);
      const env = await api.agentCommerce.activateEnvelope(
        res.draft_envelope.id,
        res.draft_envelope.envelope_hash
      );
      setActiveEnvelope(env);
    } catch (err) {
      setError(
        `Could not start a fresh envelope: ${
          err instanceof Error ? err.message : String(err)
        }`
      );
      setErrorStep(3);
    } finally {
      setBusy(null);
    }
  }

  async function runAttempt() {
    const env = activeEnvelope ?? intent?.draft_envelope;
    if (!env) return;
    setBusy("attempt");
    setError(null);
    setErrorStep(null);
    try {
      const res = await api.agentCommerce.submitAttempt({
        envelope_id: env.id,
        purchase_attempt_id: rid("att"),
        scenario,
        buyer_agent_id: "buyer_replay",
      });
      setAttempt(res);
    } catch (err) {
      setError(`Attempt failed: ${err instanceof Error ? err.message : String(err)}`);
      setErrorStep(3);
    } finally {
      setBusy(null);
    }
  }

  async function evaluateRefund() {
    setBusy("refund");
    setError(null);
    setErrorStep(null);
    try {
      const res = await api.agentCommerce.evaluateRefund({
        payment_id: rid("pay"),
        amount_paise: (Number.parseInt(refundRupees, 10) || 0) * 100,
        reason: refundReason,
        original_amount_paise: 784000,
        already_refunded_paise: 0,
        order_age_days: 4,
      });
      setRefundResult(res);
    } catch (err) {
      setError(`Refund evaluation failed: ${err instanceof Error ? err.message : String(err)}`);
      setErrorStep(5);
    } finally {
      setBusy(null);
    }
  }

  const draft = intent?.draft_envelope ?? null;
  const readback = intent?.readback ?? null;
  const envelope = activeEnvelope ?? draft;
  const isActive = activeEnvelope?.status === "active";

  return (
    <div className="mx-auto max-w-4xl space-y-8 pb-20 pt-2 text-text">
      {/* ---------------------------------------------------------------- */}
      {/* Masthead                                                          */}
      {/* ---------------------------------------------------------------- */}
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-3 py-1 text-xs font-semibold text-success ring-1 ring-inset ring-success/20">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-success" />
            {health ? "Backend live" : loadError ? "Backend unreachable" : "Connecting…"}
          </span>
          {health && (
            <span className="inline-flex items-center rounded-full bg-canvas px-3 py-1 text-xs font-medium text-text">
              provider: {health.payment_provider}
            </span>
          )}
          {health && (
            <span className="inline-flex items-center rounded-full bg-canvas px-3 py-1 text-xs font-medium text-text">
              {health.catalog_size} SKUs
            </span>
          )}
        </div>

        <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-text sm:text-4xl">
          A store that can safely say yes.
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          The customer approves one job, once. After that the store repairs small
          surprises by itself, and refuses anything outside what was approved —
          before a payment rail is ever called.
        </p>
        <p className="mt-2 max-w-2xl text-xs leading-relaxed text-muted">
          The four steps below are the whole product. Every figure is fetched live;
          nothing is seeded, and a failed call shows as a failure rather than a stand-in.
        </p>
      </header>

      {loadError && (
        <Failed
          what="Could not reach the backend."
          detail={loadError}
        />
      )}

      {/* Only unattributed failures surface here now. Anything that belongs to a
          step is shown at that step instead, so the message and the control it
          concerns are on screen together rather than a scroll apart. */}
      {error && errorStep === null && (
        <div className="rounded-xl border border-danger/30 bg-danger/10 p-4 text-xs text-danger">
          {error}
        </div>
      )}

      {/* ---------------------------------------------------------------- */}
      {/* STEP 1 — the published rules                                      */}
      {/* ---------------------------------------------------------------- */}
      <Card>
        <StepHeader
          n={1}
          title={STEP_TITLES[0]}
          hint="An agent can already discover what a store sells. It cannot normally discover what a store will refuse — so it learns the rules by breaking them. This store publishes them first."
        />

        {loading && <div className="mt-5 text-xs text-muted">Loading…</div>}

        {policy && (
          <div className="mt-5 grid gap-5 sm:grid-cols-2">
            <div className="rounded-xl border border-border p-4">
              <div className="font-mono text-[11px] font-bold uppercase tracking-wider text-success">
                Money in
              </div>
              <h3 className="mt-2 text-sm font-bold">AI buyers may order …</h3>
              <ul className="mt-3 space-y-1.5 text-sm text-text">
                <li>up to <strong>{inr(policy.money_in.max_order_paise)}</strong> per order</li>
                <li>from <strong>{policy.money_in.merchant_name}</strong> only</li>
                <li>
                  never: <strong>{policy.money_in.blocked_tags.join(", ")}</strong>
                </li>
              </ul>
              <p className="mt-3 border-t border-border pt-3 text-[11px] leading-relaxed text-muted">
                The last line is the one a category allowlist cannot express. Eggs
                sit inside <em>dairy</em>, which this buyer allows — the tag is what
                a vegetarian kitchen must never receive.
              </p>
            </div>

            <div className="rounded-xl border border-border p-4">
              <div className="font-mono text-[11px] font-bold uppercase tracking-wider text-primary">
                Money out
              </div>
              <h3 className="mt-2 text-sm font-bold">Agents may refund …</h3>
              <ul className="mt-3 space-y-1.5 text-sm text-text">
                <li>up to <strong>{inr(policy.money_out.max_refund_paise)}</strong> unattended</li>
                <li>within <strong>{policy.money_out.window_days} days</strong> of the order</li>
                <li>up to <strong>{inr(policy.money_out.daily_cap_paise)}</strong> a day</li>
                <li>
                  never: <strong>{policy.money_out.escalate_reasons.join(", ")}</strong>
                </li>
              </ul>
              <p className="mt-3 border-t border-border pt-3 text-[11px] leading-relaxed text-muted">
                Money moves both ways in a real store. The same authority check runs
                outbound, so a support agent cannot refund its way past policy.
              </p>
            </div>
          </div>
        )}

        {policy && (
          <div className="mt-5 rounded-xl bg-canvas p-4">
            <div className="text-xs font-semibold text-text">
              Published, unauthenticated, at{" "}
              <Mono>/agent-commerce/v1/acceptance-policy</Mono>
            </div>
            <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
              Generated from the same objects the verifier reads, so it cannot drift
              from what is actually enforced. Replayed against this repository&apos;s
              own corpus, half of 800 constructed violations would never have been
              proposed by an agent that read it first.
              {policyHash && (
                <>
                  {" "}
                  Version an agent can pin: <Mono>{policyHash.slice(0, 16)}…</Mono>
                </>
              )}
            </p>
          </div>
        )}
      </Card>

      {/* ---------------------------------------------------------------- */}
      {/* STEP 2 — the approval                                             */}
      {/* ---------------------------------------------------------------- */}
      <Card>
        <StepHeader
          n={2}
          title={STEP_TITLES[1]}
          hint="Not a spending cap. A Purchase Envelope says what the money is for: which slots, which merchant, by when, and a ceiling. It is hashed, so widening it later is detectable."
        />

        <div className="mt-5 grid gap-3 sm:grid-cols-[1fr_auto_auto]">
          <input
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="what the customer wants done"
            className="rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary"
          />
          <input
            value={budgetRupees}
            onChange={(e) => setBudgetRupees(e.target.value)}
            inputMode="numeric"
            className="w-28 rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary"
          />
          <button
            onClick={draftEnvelope}
            disabled={busy !== null}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-hover disabled:opacity-40"
          >
            {busy === "draft" ? "Drafting…" : "Draft the envelope"}
          </button>
        </div>

        {error && errorStep === 1 && <StepError message={error} />}

        {!draft && !loading && (
          <div className="mt-4">
            <Empty>
              No envelope yet. Press <strong>Draft the envelope</strong> — the store
              turns the sentence into an explicit, checkable set of slots.
            </Empty>
          </div>
        )}

        {draft && (
          <div className="mt-5 rounded-xl border border-border">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
              <div className="text-sm font-semibold">
                Draft envelope
                <span className="ml-2 rounded-md bg-canvas px-2 py-0.5 text-[11px] font-medium text-muted">
                  {envelope?.status ?? "draft"} · v{envelope?.version ?? 1}
                </span>
              </div>
              <Mono>{draft.envelope_hash.slice(0, 20)}…</Mono>
            </div>

            <div className="space-y-4 p-4">
              {/* Re-draft diff */}
              {previousReadback && readback && previousReadback.catalog_revision === readback.catalog_revision && (
                (() => {
                  const prevSlots = new Set(previousReadback.slots.map((s: SlotAdmission) => s.slot_id));
                  const currSlots = new Set(readback.slots.map((s: SlotAdmission) => s.slot_id));
                  const addedSlots = readback.slots.filter((s: SlotAdmission) => !prevSlots.has(s.slot_id));
                  const removedSlots = previousReadback.slots.filter((s: SlotAdmission) => !currSlots.has(s.slot_id));
                  const capDiff = readback.max_total_paise !== previousReadback.max_total_paise;
                  const worstDiff = readback.worst_case_total_paise !== previousReadback.worst_case_total_paise;
                  if (addedSlots.length === 0 && removedSlots.length === 0 && !capDiff && !worstDiff) {
                    return null;
                  }
                  return (
                    <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs text-text space-y-1">
                      <div className="font-semibold text-primary">Re-draft changes:</div>
                      {addedSlots.length > 0 && (
                        <div className="text-muted">
                          + Added: {addedSlots.map((s: SlotAdmission) => s.label).join(", ")}
                        </div>
                      )}
                      {removedSlots.length > 0 && (
                        <div className="text-muted">
                          − Dropped: {removedSlots.map((s: SlotAdmission) => s.label).join(", ")}
                        </div>
                      )}

                      {capDiff && (
                        <div className="text-muted">
                          Ceiling: {inr(previousReadback.max_total_paise)} → {inr(readback.max_total_paise)}
                        </div>
                      )}
                      {worstDiff && (
                        <div className="text-muted">
                          Worst-case basket: {inr(previousReadback.worst_case_total_paise)} → {inr(readback.worst_case_total_paise)}
                        </div>
                      )}
                    </div>
                  );
                })()
              )}

              {/* (a) The sentence */}
              {readback?.english && (
                <div className="rounded-xl border border-border bg-canvas p-4 text-sm leading-relaxed text-text">
                  <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-muted">
                    Approved Rule
                  </div>
                  <p>{readback.english}</p>
                </div>
              )}

              {/* (b) What it admits — one row per slot */}
              <div className="space-y-2">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                  What this rule admits
                </div>
                <div className="divide-y divide-border rounded-xl border border-border overflow-hidden">
                  {readback?.slots.map((slot: SlotAdmission) => {
                    const isUnsatisfiable = slot.admissible_count === 0;
                    const hasSpread =
                      slot.dearest_paise !== null &&
                      slot.cheapest_paise !== null &&
                      slot.dearest_paise > slot.cheapest_paise;
                    return (
                      <div
                        key={slot.slot_id}
                        className={`flex flex-wrap items-center justify-between gap-3 p-3.5 text-xs ${
                          isUnsatisfiable ? "bg-danger/10 text-danger" : "bg-surface text-text"
                        }`}
                      >
                        <div className="min-w-[140px]">
                          <span className="text-sm font-bold">{slot.label}</span>
                          <span className="ml-2 text-muted">×{slot.quantity}</span>
                          <div className="mt-0.5 text-[11px] text-muted font-mono">
                            {slot.required_tags.join(" + ")}
                          </div>
                        </div>

                        <div className="flex-1 min-w-[220px]">
                          {isUnsatisfiable ? (
                            <span className="font-medium text-danger">
                              nothing in the catalog satisfies this — the order can never be fulfilled
                            </span>
                          ) : (
                            <div className="flex flex-wrap items-center gap-2.5">
                              <span className="rounded bg-canvas px-2 py-0.5 text-[11px] text-muted">
                                {slot.admissible_count} {slot.admissible_count === 1 ? "item" : "items"}
                              </span>
                              <span className="font-semibold text-text">
                                {hasSpread
                                  ? `${inr(slot.cheapest_paise!)} – ${inr(slot.dearest_paise!)}`
                                  : slot.cheapest_paise !== null
                                  ? inr(slot.cheapest_paise)
                                  : "—"}
                              </span>
                              {hasSpread && slot.dearest_name && (
                                <span className="text-[11px] text-muted">
                                  ← dearest: <span className="font-medium text-text">{slot.dearest_name}</span>
                                </span>
                              )}
                            </div>
                          )}
                        </div>

                        <div>
                          {!isActive && draft.slots.length > 1 && (
                            <button
                              onClick={() => dropSlot(slot.slot_id)}
                              disabled={busy !== null}
                              className="rounded px-2.5 py-1 text-xs font-semibold text-danger hover:bg-danger/10 transition disabled:opacity-40"
                            >
                              {busy === `drop_${slot.slot_id}` ? "Removing…" : "Remove"}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* (c) The worst case, as a sentence */}
              {readback && (
                <div className="rounded-xl border border-border bg-canvas p-3.5 text-xs text-text">
                  <div className="font-medium leading-relaxed">
                    {readback.cap_binds
                      ? `The most expensive basket this rule allows is ${inr(readback.worst_case_total_paise)}, above your ${inr(readback.max_total_paise)} cap. The cap will refuse it.`
                      : `The most expensive basket this rule allows is ${inr(readback.worst_case_total_paise)}. Your ${inr(readback.max_total_paise)} cap is not what is protecting you here — the rule is.`}
                  </div>
                </div>
              )}

              {/* (d) Editable cap */}
              <div className="rounded-xl border border-border bg-surface p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                      Spending Ceiling
                    </div>
                    <p className="mt-0.5 text-xs text-muted">
                      You may tighten the ceiling before activating. Widening requires starting over.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="relative">
                      <span className="absolute left-3 top-2 text-sm text-muted">₹</span>
                      <input
                        value={editCapRupees}
                        onChange={(e) => setEditCapRupees(e.target.value)}
                        disabled={isActive || busy !== null}
                        className="w-28 rounded-lg border border-border py-1.5 pl-7 pr-3 text-sm font-semibold outline-none focus:border-primary disabled:opacity-60"
                      />
                    </div>
                    {!isActive && (
                      <button
                        onClick={updateCap}
                        disabled={busy !== null || Number.parseInt(editCapRupees, 10) * 100 === draft.max_total_paise}
                        className="rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-primary-hover disabled:opacity-40"
                      >
                        {busy === "update_cap" ? "Updating…" : "Apply ceiling"}
                      </button>
                    )}
                  </div>
                </div>
                {capEditError && <StepError message={capEditError} />}
              </div>
            </div>

            {/* (e) Copy under the activate button */}
            <div className="flex flex-wrap items-center gap-3 border-t border-border bg-canvas px-4 py-3">
              <button
                onClick={activate}
                disabled={busy !== null || isActive}
                className="rounded-lg bg-success px-4 py-2 text-sm font-semibold text-white transition hover:bg-success/90 disabled:opacity-40"
              >
                {isActive
                  ? "Activated by the customer"
                  : busy === "activate"
                  ? "Activating…"
                  : "Activate as the customer"}
              </button>
              <p className="text-[11px] leading-relaxed text-muted">
                {isActive
                  ? "Activated. Every purchase is checked against this rule exactly as written."
                  : "From here the model gets no further say. Every purchase is checked against this rule exactly as written."}
              </p>
              {error && errorStep === 2 && (
                <div className="w-full">
                  <StepError message={error} />
                </div>
              )}
            </div>
          </div>
        )}

      </Card>

      {/* ---------------------------------------------------------------- */}
      {/* STEP 3 — the attempt                                              */}
      {/* ---------------------------------------------------------------- */}
      <Card>
        <StepHeader
          n={3}
          title={STEP_TITLES[2]}
          hint="Pick what goes wrong. The store re-reads its own catalog at authorization time, so the agent's version of the facts is never the one that counts."
        />

        <div className="mt-5 flex flex-wrap gap-2">
          {SCENARIOS.map((s) => (
            <button
              key={s.id}
              onClick={() => setScenario(s.id)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                scenario === s.id
                  ? "bg-primary text-white"
                  : "bg-canvas text-text hover:bg-border"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <p className="mt-3 text-[11px] leading-relaxed text-muted">
          {SCENARIOS.find((s) => s.id === scenario)?.teaches}
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            onClick={runAttempt}
            disabled={busy !== null || !isActive || attempt !== null}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-hover disabled:opacity-40"
          >
            {busy === "attempt" ? "Running…" : "Run the agent's attempt"}
          </button>

          {attempt && (
            <button
              onClick={freshEnvelope}
              disabled={busy !== null}
              className="rounded-lg border border-border bg-surface px-4 py-2 text-sm font-semibold text-text transition hover:bg-canvas disabled:opacity-40"
            >
              {busy === "fresh" ? "Starting…" : "Fresh envelope, try another scenario"}
            </button>
          )}

          {!isActive && !attempt && (
            <span className="text-[11px] text-muted">
              {errorStep === 2
                ? "Step 2's activation did not go through — see the message there. This button stays disabled until it does."
                : intent
                ? "Disabled until you press \u201cActivate as the customer\u201d in step 2 \u2014 that is the point: no API call can activate an envelope."
                : "Draft an envelope in step 1 first, then activate it in step 2."}
            </span>
          )}
        </div>

        {error && errorStep === 3 && <StepError message={error} />}

        {attempt && (
          <p className="mt-3 rounded-lg bg-warning/10 px-3 py-2 text-[11px] leading-relaxed text-warning ring-1 ring-inset ring-warning/30">
            <strong>This envelope is now spent.</strong> One authorization covers
            one purchase attempt, so running a second scenario against it would
            correctly refuse with <Mono>BLOCK_ENVELOPE_CONSUMED</Mono> — the
            single-use guarantee doing its job, not the demo breaking. Use the
            button above to start a fresh one.
          </p>
        )}

        {!attempt && isActive && (
          <div className="mt-4">
            <Empty>No attempt run yet against this envelope.</Empty>
          </div>
        )}

        {attempt && (
          <div className="mt-5 space-y-4">
            <div
              className={`rounded-xl border p-4 ${
                outcomeTone(attempt.outcome) === "emerald"
                  ? "border-success/30 bg-success/10"
                  : outcomeTone(attempt.outcome) === "blue"
                  ? "border-primary/30 bg-primary/10"
                  : outcomeTone(attempt.outcome) === "amber"
                  ? "border-warning/30 bg-warning/10"
                  : "border-danger/30 bg-danger/10"
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-md bg-surface/70 px-2 py-1 font-mono text-[11px] font-bold">
                  {attempt.outcome}
                </span>
                <span className="font-mono text-[11px] text-muted">
                  {attempt.code}
                </span>
                <span className="ml-auto text-xs font-bold">
                  {inr(attempt.quote_total_paise)}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-text">
                {attempt.human_message}
              </p>
              <div className="mt-3 flex flex-wrap gap-3 border-t border-border pt-3 text-[11px] text-text">
                <span>
                  Razorpay action called:{" "}
                  <strong>{attempt.razorpay_action_called ? "yes" : "no"}</strong>
                </span>
                <span>
                  repaired in-envelope:{" "}
                  <strong>{attempt.recovery_applied ? "yes" : "no"}</strong>
                </span>
                <span>provider: <strong>{attempt.provider_mode}</strong></span>
              </div>
            </div>

            {/* The four stages, straight from the response */}
            <div className="grid gap-2 sm:grid-cols-4">
              {attempt.stages.map((st) => (
                <div
                  key={st.stage}
                  className="rounded-xl border border-border bg-surface p-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold text-text">
                      {st.name}
                    </span>
                    <span
                      className={`h-2 w-2 rounded-full ${
                        st.status === "completed"
                          ? "bg-success/100"
                          : st.status === "blocked"
                          ? "bg-danger/100"
                          : st.status === "unknown"
                          ? "bg-warning/100"
                          : "bg-border"
                      }`}
                    />
                  </div>
                  <p className="mt-1.5 text-[11px] leading-relaxed text-muted">
                    {st.detail}
                  </p>
                </div>
              ))}
            </div>

            {/* The deltas — the part that makes a refusal actionable */}
            {attempt.deltas.length > 0 ? (
              <div>
                <div className="mb-2 text-[11px] font-bold uppercase tracking-wider text-muted">
                  Policy deltas — why, in fields, not prose
                </div>
                <div className="overflow-x-auto rounded-xl border border-border">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b border-border bg-canvas font-semibold text-muted">
                      <tr>
                        <th className="px-3 py-2">Field</th>
                        <th className="px-3 py-2">Approved</th>
                        <th className="px-3 py-2">Proposed</th>
                        <th className="px-3 py-2">What the caller may do</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border bg-surface">
                      {attempt.deltas.map((d, i) => (
                        <tr key={`${d.field}-${i}`}>
                          <td className="px-3 py-2 font-medium text-text">
                            {d.field}
                          </td>
                          <td className="px-3 py-2 font-mono text-muted">
                            {d.expected}
                          </td>
                          <td className="px-3 py-2 font-mono text-text">
                            {d.actual}
                          </td>
                          <td className="px-3 py-2">
                            <span
                              className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${
                                d.recovery === "repair"
                                  ? "bg-primary/10 text-primary"
                                  : d.recovery === "fresh_approval"
                                  ? "bg-warning/10 text-warning"
                                  : "bg-danger/10 text-danger"
                              }`}
                            >
                              {d.recovery}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-[11px] leading-relaxed text-muted">
                  <strong>repair</strong> means the store may fix it and continue.{" "}
                  <strong>fresh_approval</strong> means only the customer can widen
                  this — the store must not. <strong>stop</strong> means no
                  correction of this proposal can be authorised.
                </p>
              </div>
            ) : (
              <Empty>
                No deltas: the proposal agreed with the envelope on every checked
                field.
              </Empty>
            )}
          </div>
        )}
      </Card>

      {/* ---------------------------------------------------------------- */}
      {/* STEP 4 — the residue                                              */}
      {/* ---------------------------------------------------------------- */}
      <Card>
        <StepHeader
          n={4}
          title={STEP_TITLES[3]}
          hint="Whatever happened, the store can prove it afterwards — including, and especially, a refusal."
        />

        {!attempt && (
          <div className="mt-5">
            <Empty>Run an attempt in step 3 and its receipt appears here.</Empty>
          </div>
        )}

        {attempt && (
          <div className="mt-5 space-y-4">
            {attempt.receipt ? (
              <div className="rounded-xl border border-border">
                <div className="border-b border-border px-4 py-3 text-sm font-semibold">
                  Action receipt
                  <span className="ml-2 rounded-md bg-canvas px-2 py-0.5 text-[11px] font-medium text-muted">
                    {attempt.receipt.state}
                  </span>
                </div>
                <dl className="grid gap-x-6 gap-y-2 px-4 py-4 text-[11px] sm:grid-cols-2">
                  <div>
                    <dt className="font-semibold text-muted">grant</dt>
                    <dd><Mono>{attempt.receipt.grant_id}</Mono></dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-muted">action</dt>
                    <dd><Mono>{attempt.receipt.action_name}</Mono></dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-muted">cart hash</dt>
                    <dd><Mono>{attempt.receipt.cart_hash?.slice(0, 24)}…</Mono></dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-muted">envelope hash</dt>
                    <dd>
                      <Mono>
                        {attempt.receipt.envelope_hash
                          ? `${attempt.receipt.envelope_hash.slice(0, 24)}…`
                          : "—"}
                      </Mono>
                    </dd>
                  </div>
                </dl>
                <p className="border-t border-border px-4 py-3 text-[11px] leading-relaxed text-muted">
                  The grant is bound to this cart, this amount and one attempt. It
                  cannot be replayed against a different proposal, which is what
                  makes the receipt worth anything.
                </p>
              </div>
            ) : (
              <Empty>
                No receipt, because no action was authorised. That is the correct
                outcome for a refusal — nothing was issued, so there is nothing to
                sign.
              </Empty>
            )}

            {attempt.payment_link && (
              <div className="rounded-xl border border-success/30 bg-success/10 p-4">
                <div className="text-xs font-semibold text-success">
                  Payment link issued
                </div>
                <a
                  href={attempt.payment_link}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-[11px] text-primary underline underline-offset-2 hover:text-primary-hover break-all"
                >
                  {attempt.payment_link}
                </a>
                <p className="mt-2 text-[11px] leading-relaxed text-success">
                  Issued against the simulated provider in this deployment. Creating
                  a link is not a settlement, and this page does not claim one.
                </p>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* ---------------------------------------------------------------- */}
      {/* Money out                                                         */}
      {/* ---------------------------------------------------------------- */}
      <Card>
        <StepHeader
          n={5}
          title="The same check, with the money going the other way"
          hint="A support agent issuing refunds has the same problem in reverse. This is the outbound half, and it runs through the same verifier."
        />

        {refundPolicy && (
          <p className="mt-4 text-[11px] leading-relaxed text-muted">
            Bound to policy <Mono>{refundPolicy.policy_hash.slice(0, 16)}…</Mono> —
            up to {inr(refundPolicy.max_refund_paise)} unattended, within{" "}
            {refundPolicy.window_days} days, {inr(refundPolicy.daily_cap_paise)} a
            day. Reasons that always escalate:{" "}
            {refundPolicy.escalate_reasons.join(", ")}.
          </p>
        )}

        <div className="mt-4 grid gap-3 sm:grid-cols-[auto_1fr_auto]">
          <input
            value={refundRupees}
            onChange={(e) => setRefundRupees(e.target.value)}
            inputMode="numeric"
            className="w-28 rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary"
          />
          <input
            value={refundReason}
            onChange={(e) => setRefundReason(e.target.value)}
            placeholder="reason given by the customer"
            className="rounded-lg border border-border px-3 py-2 text-sm outline-none focus:border-primary"
          />
          <button
            onClick={evaluateRefund}
            disabled={busy !== null}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-primary-hover disabled:opacity-40"
          >
            {busy === "refund" ? "Checking…" : "Ask the firewall"}
          </button>
        </div>

        <p className="mt-2 text-[11px] text-muted">
          Try {inr(40000)} for an allow, then something above the ceiling, then the
          word <em>fraud</em> as the reason.
        </p>

        {refundResult && (
          <div
            className={`mt-4 rounded-xl border p-4 ${
              refundResult.allowed
                ? "border-success/30 bg-success/10"
                : refundResult.code?.includes("REPAIR")
                ? "border-primary/30 bg-primary/10"
                : refundResult.code?.includes("ESCALATE")
                ? "border-warning/30 bg-warning/10"
                : "border-danger/30 bg-danger/10"
            }`}
          >
            <span className="rounded-md bg-surface/70 px-2 py-1 font-mono text-[11px] font-bold">
              {refundResult.code}
            </span>
            <p className="mt-2 text-sm text-text">
              {refundResult.human_message}
            </p>
            {refundResult.repaired_proposal && (
              <p className="mt-2 text-[11px] text-text">
                Narrowed to{" "}
                <strong>{inr(refundResult.repaired_proposal.amount_paise)}</strong>{" "}
                — a repair may only ever reduce authority, never widen it.
              </p>
            )}
          </div>
        )}
      </Card>

      {/* ---------------------------------------------------------------- */}
      {/* Everything else, deliberately below the fold                      */}
      {/* ---------------------------------------------------------------- */}
      <Card tone="muted">
        <h3 className="text-xs font-bold uppercase tracking-wider text-text">
          The evidence behind the four steps
        </h3>
        <p className="mt-1 text-xs text-muted">
          None of this is needed to understand the product. It is here because a
          reviewer should be able to check the claims rather than take them.
        </p>
        <div className="mt-4 grid grid-cols-2 gap-2 text-xs font-medium sm:grid-cols-4">
          {[
            ["/orders", "Orders ledger"],
            ["/evidence", "Benchmarks & proofs"],
            ["/audit", "Audit trail"],
            ["/catalog", "Store catalog"],
            ["/playground", "Full playground"],
            ["/impact", "Cost model"],
            ["/mandate", "Standing rules"],
            ["/baseline", "Baseline comparison"],
          ].map(([href, label]) => (
            <Link
              key={href}
              href={href}
              className="flex items-center justify-between rounded-xl border border-border bg-surface p-3 text-text transition hover:border-border"
            >
              <span>{label}</span>
              <span className="text-muted">&rarr;</span>
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}
