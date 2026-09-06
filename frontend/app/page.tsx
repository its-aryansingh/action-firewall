"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { VoiceIntentInput } from "@/components/VoiceIntentInput";
import {
  api,
  inr,
  type AutopilotResponse,
  type AutopilotScenario,
  type Health,
  type PurchaseEnvelope,
} from "@/lib/api";

const SCENARIOS: Array<{
  id: AutopilotScenario;
  label: string;
  detail: string;
  tone: "safe" | "risk";
}> = [
  {
    id: "normal",
    label: "Approved quote → checkout",
    detail: "Build the quote, verify every bound, then issue one exact payment action.",
    tone: "safe",
  },
  {
    id: "stock_loss",
    label: "Stock loss → safe substitute",
    detail: "The preferred pasta disappears. Recover only from eligible SKUs.",
    tone: "safe",
  },
  {
    id: "merchant_drift",
    label: "Merchant changed → refuse",
    detail: "The quote moves to an unapproved merchant. Require fresh approval.",
    tone: "risk",
  },
  {
    id: "price_drift",
    label: "Price exceeds cap → refuse",
    detail: "The final quote breaches the exact approved maximum.",
    tone: "risk",
  },
  {
    id: "timeout_after_dispatch",
    label: "Provider timeout → hold",
    detail: "Outcome becomes UNKNOWN. Never fire a blind retry.",
    tone: "risk",
  },
];

const SUGGESTED_GOALS = [
  "Buy supplies for a pasta dinner",
  "Restock office snacks",
  "Breakfast run",
  "Quick lunch run",
  "Team coffee restock",
];

function shortHash(value: string | null | undefined): string {
  if (!value) return "—";
  return value.slice(0, 10) + "…" + value.slice(-6);
}

function newIdentity(prefix: string): string {
  return `${prefix}_${globalThis.crypto.randomUUID()}`;
}

export default function SafeAutopilotPage() {
  const [goal, setGoal] = useState("Buy supplies for a pasta dinner");
  const [budget, setBudget] = useState("600");
  const [envelope, setEnvelope] = useState<PurchaseEnvelope | null>(null);
  const [result, setResult] = useState<AutopilotResponse | null>(null);
  const [scenario, setScenario] = useState<AutopilotScenario>("stock_loss");
  const [health, setHealth] = useState<Health | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [attemptId, setAttemptId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const workflowRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setSessionId(newIdentity("safe_session"));
    setAttemptId(newIdentity("att"));
    api.health()
      .then((current) => {
        setHealth(current);
        if (current.payment_provider === "razorpay_mcp" || !current.fault_injection_enabled) {
          setScenario("normal");
        }
      })
      .catch(() => setHealth(null));
  }, []);

  const step = !envelope ? 1 : envelope.status === "draft" ? 2 : 3;
  const selectedScenario = useMemo(
    () => SCENARIOS.find((item) => item.id === scenario) ?? SCENARIOS[0],
    [scenario],
  );

  async function draft() {
    const rupees = Number.parseInt(budget, 10);
    if (!goal.trim() || !Number.isFinite(rupees) || rupees <= 0) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const created = await api.draftEnvelope(goal.trim(), rupees);
      setEnvelope(created);
      setAttemptId(newIdentity("att"));
    } catch (caught) {
      const raw = String(caught);
      let message = raw;
      try {
        const jsonMatch = raw.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          const parsed = JSON.parse(jsonMatch[0]);
          if (parsed.detail) {
            message = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
          }
        }
      } catch {
        // fallback
      }
      setError(`Could not draft the approval: ${message}`);
    } finally {
      setBusy(false);
    }
  }

  async function activate() {
    if (!envelope || envelope.status !== "draft") return;
    setBusy(true);
    setError(null);
    try {
      setEnvelope(await api.activateEnvelope(envelope.id, envelope.envelope_hash));
    } catch (caught) {
      setError(`Approval was not activated: ${String(caught)}`);
    } finally {
      setBusy(false);
    }
  }

  async function run() {
    if (!envelope || envelope.status !== "active" || !sessionId || !attemptId) return;
    setBusy(true);
    setError(null);
    try {
      const executed = await api.executeAutopilot(
        envelope,
        sessionId,
        attemptId,
        scenario,
      );
      setResult(executed);
      setEnvelope(executed.envelope);
    } catch (caught) {
      setError(
        `Execution response was lost: ${String(caught)}. Retry keeps the same attempt ID.`,
      );
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    if (!envelope || envelope.status !== "active") return;
    setBusy(true);
    setError(null);
    try {
      setEnvelope(await api.revokeEnvelope(envelope.id, envelope.version));
    } catch (caught) {
      setError(`Revocation failed: ${String(caught)}`);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setEnvelope(null);
    setResult(null);
    setError(null);
    setAttemptId(newIdentity("att"));
  }

  return (
    <div className="space-y-7">
      <section className="hero-shell">
        <div className="hero-orb hero-orb-one" />
        <div className="hero-orb hero-orb-two" />
        <div className="relative grid gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)] lg:items-end">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="status-pill border-brand/40 bg-brand/10 text-brand">
                Razorpay Buildathon · Track 01
              </span>
              <span
                className={
                  "status-pill font-semibold " +
                  (health?.payment_provider === "razorpay_mcp"
                    ? "border-allow/40 bg-allow/10 text-allow"
                    : "border-edge bg-ink/50 text-muted")
                }
              >
                {health?.payment_provider === "razorpay_mcp"
                  ? "RAZORPAY TEST MODE"
                  : "SAFE DEMO MODE"}
              </span>
            </div>
            <p className="mt-7 text-xs font-semibold uppercase tracking-[0.22em] text-brand">
              Agentic checkout authorization
            </p>
            <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-[1.05] tracking-[-0.035em] sm:text-6xl">
              Let AI finish the purchase.
              <span className="mt-1 block text-gradient">Never let it expand permission.</span>
            </h1>
            <p className="mt-5 max-w-2xl text-sm leading-6 text-slate-300 sm:text-base">
              A shopper approves one bounded job. The AI may recover from stock changes,
              but deterministic code alone decides whether one exact Razorpay action may run.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button
                className="btn btn-primary min-h-11"
                onClick={() => workflowRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
              >
                Run the 90-second proof
              </button>
              <Link href="/audit" className="btn-ghost inline-flex min-h-11 items-center">
                Inspect live evidence
              </Link>
            </div>
          </div>

          <div className="proof-panel">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="label">Controlled workflow benchmark</p>
                <p className="mt-1 text-sm font-medium text-slate-200">Useful autonomy, bounded risk</p>
              </div>
              <span className="live-dot"><i /> REPRODUCIBLE</span>
            </div>
            <div className="mt-5 grid grid-cols-3 gap-2">
              <ProofMetric value="100/100" label="jobs completed" tone="brand" />
              <ProofMetric value="50/50" label="stock recoveries" tone="allow" />
              <ProofMetric value="0/150" label="unsafe actions" tone="allow" />
            </div>
            <p className="mt-4 text-[10px] leading-4 text-muted">
              Synthetic catalog benchmark. These are authorization and workflow results—not
              production conversion, GMV, or payment-success claims.
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-3 md:grid-cols-3">
        <Step number="1" title="Describe the job" active={step === 1} done={step > 1} />
        <Step number="2" title="Approve exact authority" active={step === 2} done={step > 2} />
        <Step number="3" title="Execute or refuse" active={step === 3} done={Boolean(result)} />
      </section>

      {error && (
        <div className="rounded-2xl border border-block/40 bg-block/10 px-4 py-3 text-sm text-block">
          {error}
        </div>
      )}

      <div className="scroll-mt-24 grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(340px,0.8fr)]" ref={workflowRef}>
        <div className="space-y-6">
          <section className="card">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="label">Shopper intent</p>
                <h2 className="mt-1 text-lg font-semibold">Define one purchase job</h2>
              </div>
              {envelope && (
                <button className="btn-ghost" onClick={reset} disabled={busy}>
                  New job
                </button>
              )}
            </div>
            {!envelope && (
              <div className="mt-5">
                <VoiceIntentInput
                  aiConfigured={Boolean(health?.voice_ai_configured)}
                  disabled={busy}
                  onTranscript={(transcript) => {
                    setGoal(transcript);
                    setError(null);
                  }}
                />
              </div>
            )}
            <label className="mt-5 block text-sm text-muted">
              Goal
              <textarea
                className="input mt-2 min-h-24 resize-none"
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                disabled={busy || Boolean(envelope)}
              />
            </label>
            {!envelope && (
              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                <span className="text-xs text-muted">Try:</span>
                {SUGGESTED_GOALS.map((sug) => (
                  <button
                    key={sug}
                    type="button"
                    className="rounded-full border border-edge bg-panel px-2.5 py-1 text-xs text-muted hover:border-brand/50 hover:text-ink transition-colors"
                    onClick={() => {
                      setGoal(sug);
                      setError(null);
                    }}
                    disabled={busy}
                  >
                    {sug}
                  </button>
                ))}
              </div>
            )}
            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              <label className="text-sm text-muted">
                Maximum total
                <div className="mt-2 flex items-center rounded-xl border border-edge bg-ink px-3 focus-within:border-brand">
                  <span className="text-muted">₹</span>
                  <input
                    className="w-full bg-transparent px-2 py-2 text-sm outline-none"
                    inputMode="numeric"
                    value={budget}
                    onChange={(event) => setBudget(event.target.value)}
                    disabled={busy || Boolean(envelope)}
                  />
                </div>
              </label>
              <FixedField label="Merchant" value="Acme Grocery · merchant_demo" />
              <FixedField label="Deliver to" value="Saved office · ≤45 min" />
            </div>
            {!envelope && (
              <button className="btn mt-5" onClick={draft} disabled={busy}>
                {busy ? "Drafting…" : "Generate approval draft"}
              </button>
            )}
          </section>

          {envelope && (
            <section className="card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="label">Purchase Envelope</p>
                  <h2 className="mt-1 text-lg font-semibold">
                    Human-readable approval, machine-verifiable boundary
                  </h2>
                </div>
                <StatusBadge status={envelope.status} />
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <Bound label="Maximum" value={inr(envelope.max_total_paise)} />
                <Bound label="Merchant" value={envelope.merchant_id} />
                <Bound label="Destination" value={envelope.fulfillment_profile_id} />
                <Bound label="Action" value="create_payment_link · one use" />
              </div>

              <div className="mt-5">
                <p className="label">Required slots</p>
                <div className="mt-2 grid gap-2 sm:grid-cols-3">
                  {envelope.slots.map((slot) => (
                    <div key={slot.id} className="rounded-xl border border-edge bg-ink p-3">
                      <p className="text-sm font-medium">{slot.label}</p>
                      <p className="mt-1 text-xs text-muted">
                        {slot.required_tags.join(" · ")} · qty {slot.quantity}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <details className="mt-5 rounded-xl border border-edge bg-ink/60 p-3 text-[11px] text-muted group">
                <summary className="cursor-pointer font-sans font-medium text-slate-300 hover:text-white flex items-center justify-between">
                  <span>Technical evidence (cryptographic digests & identity)</span>
                  <span className="text-xs text-muted group-open:rotate-180 transition-transform">▼</span>
                </summary>
                <div className="mt-2 space-y-1 font-mono pt-2 border-t border-edge/40">
                  <div>version: {envelope.version}</div>
                  <div>envelope_hash: {envelope.envelope_hash}</div>
                  <div>mandate_id: {envelope.mandate_id ?? "unassigned (mints on activation)"}</div>
                  <div>expires: {new Date(envelope.expires_at * 1000).toLocaleTimeString()}</div>
                </div>
              </details>

              {envelope.status === "draft" && (
                <div className="mt-5 flex flex-wrap items-center gap-3">
                  <button className="btn" onClick={activate} disabled={busy}>
                    {busy ? "Activating…" : "Approve this envelope once"}
                  </button>
                  <p className="text-xs text-muted">
                    AI drafted these fields. Your click activates them; AI cannot.
                  </p>
                </div>
              )}
            </section>
          )}

          {envelope?.status === "active" && (
            <section className="card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="label">
                      {health?.payment_provider === "razorpay_mcp" ? "Live test checkout" : "Judge proof lab"}
                    </p>
                    <span className="rounded-full border border-brand/30 bg-brand/10 px-2 py-0.5 font-mono text-[11px] text-brand">
                      provider: {result?.provider_mode ?? health?.payment_provider ?? "simulated"}
                    </span>
                  </div>
                  <h2 className="mt-1 text-lg font-semibold">
                    {health?.payment_provider === "razorpay_mcp"
                      ? "Issue one verified Razorpay test action"
                      : "Prove recovery and refusal behavior"}
                  </h2>
                  <p className="mt-1 text-xs text-muted">
                    {health?.payment_provider === "razorpay_mcp"
                      ? "Fault injection is locked in live mode. Only the approved quote can reach Razorpay."
                      : "Each scenario changes a controlled quote fact, then runs the same deterministic gate."}
                  </p>
                </div>
                <button className="btn-ghost text-block" onClick={revoke} disabled={busy}>
                  Revoke now
                </button>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {SCENARIOS.map((item) => (
                  <button
                    key={item.id}
                    className={
                      "rounded-xl border p-3 text-left transition " +
                      (scenario === item.id
                        ? item.tone === "safe"
                          ? "border-allow bg-allow/10"
                          : "border-block bg-block/10"
                        : "border-edge bg-ink hover:border-brand") +
                      ((health?.payment_provider === "razorpay_mcp" || !health?.fault_injection_enabled) && item.id !== "normal"
                        ? " cursor-not-allowed opacity-[0.35]"
                        : "")
                    }
                    onClick={() => {
                      setScenario(item.id);
                      setAttemptId(newIdentity("att"));
                    }}
                    disabled={
                      busy ||
                      ((health?.payment_provider === "razorpay_mcp" || !health?.fault_injection_enabled) &&
                        item.id !== "normal")
                    }
                  >
                    <span className="text-sm font-medium">{item.label}</span>
                    <span className="mt-1 block text-xs leading-5 text-muted">
                      {item.detail}
                    </span>
                  </button>
                ))}
              </div>
              <button className="btn mt-5" onClick={run} disabled={busy || !sessionId}>
                {busy ? "Verifying exact authority…" : `Run: ${selectedScenario.label}`}
              </button>
            </section>
          )}
        </div>

        <aside className="space-y-6">
          <BoundaryCard envelope={envelope} result={result} busy={busy} />
          {result ? <ResultCard result={result} /> : <WaitingCard />}
        </aside>
      </div>
    </div>
  );
}

function ProofMetric({
  value,
  label,
  tone,
}: {
  value: string;
  label: string;
  tone: "brand" | "allow";
}) {
  return (
    <div className="rounded-2xl border border-edge/80 bg-ink/60 px-3 py-4 text-center">
      <p className={tone === "allow" ? "proof-value text-allow" : "proof-value text-brand"}>
        {value}
      </p>
      <p className="mt-1 text-[10px] uppercase leading-4 tracking-wider text-muted">{label}</p>
    </div>
  );
}

function Step({
  number,
  title,
  active,
  done,
}: {
  number: string;
  title: string;
  active: boolean;
  done: boolean;
}) {
  return (
    <div
      className={
        "rounded-2xl border px-4 py-3 text-sm " +
        (active
          ? "border-brand bg-brand/10"
          : done
            ? "border-allow/30 bg-allow/5"
            : "border-edge bg-panel/40 text-muted")
      }
    >
      <span className="mr-2 font-mono text-xs">{done ? "✓" : number}</span>
      {title}
    </div>
  );
}

function FixedField({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-sm text-muted">
      {label}
      <div className="mt-2 rounded-xl border border-edge bg-ink px-3 py-2 text-slate-100">
        {value}
      </div>
    </div>
  );
}

function Bound({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-edge bg-ink px-3 py-3">
      <p className="label">{label}</p>
      <p className="mt-1 font-mono text-sm">{value}</p>
    </div>
  );
}

function StatusBadge({ status }: { status: PurchaseEnvelope["status"] }) {
  const tone =
    status === "active"
      ? "border-allow/40 bg-allow/10 text-allow"
      : status === "draft"
        ? "border-brand/40 bg-brand/10 text-brand"
        : "border-edge bg-ink text-muted";
  return (
    <span className={`rounded-full border px-3 py-1 text-xs uppercase ${tone}`}>
      {status}
    </span>
  );
}

function BoundaryCard({
  envelope,
  result,
  busy,
}: {
  envelope: PurchaseEnvelope | null;
  result: AutopilotResponse | null;
  busy: boolean;
}) {
  const drafted = Boolean(envelope);
  const activated = envelope?.status === "active" || envelope?.status === "consumed";
  const decided = Boolean(result);
  const dispatched = Boolean(result?.payment_link);
  return (
    <section className="card overflow-hidden border-brand/20">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="label">Live authorization path</p>
          <p className="mt-1 text-sm font-semibold">Who controls each decision</p>
        </div>
        <span className={busy ? "live-dot text-brand" : "live-dot"}>
          <i className={busy ? "animate-ping" : ""} /> {busy ? "CHECKING" : "READY"}
        </span>
      </div>
      <div className="mt-5 space-y-1">
        <JourneyStage
          index="01"
          actor="AI"
          title="Draft purchase intent"
          state={drafted ? "done" : "active"}
          note="Probabilistic and editable"
        />
        <JourneyStage
          index="02"
          actor="YOU"
          title="Activate exact bounds"
          state={activated ? "done" : drafted ? "active" : "locked"}
          note="A human-only transition"
        />
        <JourneyStage
          index="03"
          actor="CODE"
          title="Verify the final quote"
          state={decided ? (result?.envelope_decision.allowed ? "done" : "blocked") : activated ? "active" : "locked"}
          note="Deterministic, field by field"
        />
        <JourneyStage
          index="04"
          actor="MCP"
          title="Redeem one action grant"
          state={dispatched ? "done" : decided && !result?.envelope_decision.allowed ? "blocked" : "locked"}
          note={decided && !result?.envelope_decision.allowed ? "Provider never called" : "Exact canonical arguments"}
        />
      </div>
      <p className="mt-5 border-t border-edge pt-4 text-[11px] leading-5 text-muted">
        Voice and model output stop at step 01. Only shopper activation and deterministic
        verification can move the flow closer to Razorpay.
      </p>
    </section>
  );
}

function JourneyStage({
  index,
  actor,
  title,
  note,
  state,
}: {
  index: string;
  actor: string;
  title: string;
  note: string;
  state: "locked" | "active" | "done" | "blocked";
}) {
  const dot =
    state === "done" ? "bg-allow text-ink" : state === "blocked" ? "bg-block text-white" : state === "active" ? "bg-brand text-white" : "bg-edge text-muted";
  return (
    <div className={`journey-stage journey-${state}`}>
      <span className={`journey-index ${dot}`}>{state === "done" ? "✓" : state === "blocked" ? "×" : index}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium text-slate-100">{title}</p>
          <span className="font-mono text-[9px] tracking-wider text-muted">{actor}</span>
        </div>
        <p className="mt-0.5 text-[11px] leading-4 text-muted">{note}</p>
      </div>
    </div>
  );
}

function WaitingCard() {
  return (
    <section className="card border-dashed border-edge/80">
      <p className="label">Why the envelope matters</p>
      <h3 className="mt-2 text-base font-semibold">Autonomy without reusable payment power</h3>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
        <div className="rounded-xl border border-block/20 bg-block/[0.04] p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-block">Exact-cart approval</p>
          <p className="mt-2 text-xs leading-5 text-muted">Stock changes → checkout stops → shopper returns.</p>
        </div>
        <div className="rounded-xl border border-allow/25 bg-allow/[0.05] p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-allow">Purchase Envelope</p>
          <p className="mt-2 text-xs leading-5 text-muted">Stock changes → safe substitute → policy re-check.</p>
        </div>
      </div>
      <p className="mt-4 text-[11px] leading-5 text-muted">
        After execution, this panel becomes a field-level decision and signed Action Receipt.
      </p>
    </section>
  );
}

function ResultCard({ result }: { result: AutopilotResponse }) {
  const allowed = result.envelope_decision.allowed;
  const unknown = result.action_status === "unknown";
  const decisionTitle = unknown
    ? "Outcome unknown — retry frozen"
    : allowed
      ? result.recovery_applied
        ? "Safe recovery authorized"
        : "Exact action issued"
      : "Out of bounds — stopped";
  const cardTone = unknown
    ? "border-amber-400/50 bg-amber-400/[0.06]"
    : allowed
      ? "border-allow/50 bg-allow/5"
      : "border-block/50 bg-block/5";
  const accentTone = unknown ? "text-amber-300" : allowed ? "text-allow" : "text-block";
  return (
    <section className={`rounded-2xl border p-5 shadow-[0_18px_60px_rgba(0,0,0,0.2)] ${cardTone}`}>
      <div className="flex items-start gap-3">
        <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-current/30 bg-ink/50 text-xl ${accentTone}`}>
          {unknown ? "!" : allowed ? "✓" : "×"}
        </span>
        <div className="min-w-0 flex-1">
          <p className="label">Deterministic decision</p>
          <h3 className={`mt-1 text-lg font-semibold ${accentTone}`}>{decisionTitle}</h3>
        </div>
      </div>
      <p className="mt-3 text-sm leading-6">{result.envelope_decision.human_message}</p>
      <div className="mt-4 grid grid-cols-2 gap-2 font-mono text-[10px]">
        <div className="rounded-xl border border-edge bg-ink/70 p-3">
          <p className="text-muted">GATE RESULT</p>
          <div className={`mt-1 ${accentTone}`}>
          {result.envelope_decision.code}
          </div>
        </div>
        <div className="rounded-xl border border-edge bg-ink/70 p-3">
          <p className="text-muted">RAZORPAY BOUNDARY</p>
          <div className={`mt-1 ${allowed ? "text-slate-200" : "text-allow"}`}>
            {allowed ? result.action_status ?? "pending" : "NOT CALLED"}
          </div>
        </div>
      </div>

      {result.recovery_applied && (
        <div className="mt-3 rounded-xl border border-allow/40 bg-allow/10 p-3.5 text-xs text-allow">
          <p className="font-semibold text-allow">
            Spaghetti became unavailable. Replaced with Penne. Final total {inr(result.envelope_decision.quote_total_paise)} of {inr(result.envelope.max_total_paise)}. No new approval required.
          </p>
        </div>
      )}

      {result.quote && (
        <div className="mt-4">
          <div className="flex items-center justify-between">
            <p className="label">Final quote</p>
            <p className="font-mono text-sm">{inr(result.envelope_decision.quote_total_paise)}</p>
          </div>
          <div className="mt-2 space-y-2">
            {result.quote.cart.lines.map((line) => (
              <div key={line.sku} className="flex justify-between gap-3 text-xs">
                <span>{line.name}</span>
                <span className="font-mono text-muted">{inr(line.unit_price_paise * line.qty)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {result.envelope_decision.deltas.length > 0 && (
        <div className="mt-4 space-y-2">
          <p className="label">Policy delta</p>
          {result.envelope_decision.deltas.map((delta) => (
            <div key={delta.field} className="rounded-xl border border-block/30 bg-ink p-3 text-xs">
              <p className="font-mono text-block">{delta.field}</p>
              <p className="mt-1 text-muted">approved: {delta.expected}</p>
              <p className="text-muted">actual: {delta.actual}</p>
              <p className="mt-1 uppercase text-slate-300">next: {delta.recovery.replace("_", " ")}</p>
            </div>
          ))}
        </div>
      )}

      {result.payment_link && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <a
            href={result.payment_link}
            target="_blank"
            rel="noreferrer"
            className={
              "inline-block rounded-xl px-5 py-2.5 font-medium transition " +
              (result.provider_mode?.toLowerCase().includes("razorpay")
                ? "bg-emerald-600 text-white shadow-lg shadow-emerald-600/20 hover:bg-emerald-500"
                : "btn")
            }
          >
            {result.provider_mode?.toLowerCase().includes("razorpay") ? "Open Razorpay test link ↗" : "Inspect simulated link ↗"}
          </a>
          <span className="text-[10px] leading-4 text-muted">Issued ≠ paid. Settlement needs provider evidence.</span>
        </div>
      )}

      {result.receipt && (
        <details className="mt-4 rounded-xl border border-edge bg-ink/60 p-3 font-mono text-[11px] text-muted group">
          <summary className="cursor-pointer font-sans font-medium text-slate-200 hover:text-white flex items-center justify-between">
            <span className="flex items-center gap-2">
              <span>Technical evidence · Action Receipt</span>
              <span className="rounded-full bg-allow/10 border border-allow/30 px-2 py-0.5 text-[10px] text-allow">
                auth core valid
              </span>
            </span>
            <span className="text-xs text-muted group-open:rotate-180 transition-transform">▼</span>
          </summary>
          <div className="mt-3 space-y-1 pt-2 border-t border-edge/40">
            <p className="text-slate-300 font-sans text-xs">Authorization core (stable across settlement):</p>
            <p className="pl-2">grant {shortHash(result.receipt.grant_id)}</p>
            <p className="pl-2">quote {shortHash(result.receipt.quote_hash)}</p>
            <p className="pl-2">args {shortHash(result.receipt.args_hash)}</p>
            <p className="pl-2">auth_sig {shortHash(result.receipt.authorization_signature ?? result.receipt.signature)}</p>
            <p className="mt-2 text-slate-300 font-sans text-xs">Status block ({result.action_status}):</p>
            <p className="pl-2">status_sig {shortHash(result.receipt.status_signature ?? result.receipt.signature)}</p>
            <p className="mt-2 text-[10px] text-muted">Dual HMAC-SHA256 · auth core survives settlement</p>
          </div>
        </details>
      )}
      <Link href="/audit" className="mt-4 inline-flex text-xs font-medium text-brand hover:text-sky-300">
        Open full audit trail →
      </Link>
    </section>
  );
}
