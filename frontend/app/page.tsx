"use client";

import { useEffect, useMemo, useState } from "react";
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

  useEffect(() => {
    setSessionId(newIdentity("safe_session"));
    setAttemptId(newIdentity("safe_attempt"));
    api.health().then(setHealth).catch(() => setHealth(null));
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
      setAttemptId(newIdentity("safe_attempt"));
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
    setSessionId(newIdentity("safe_session"));
    setAttemptId(newIdentity("safe_attempt"));
  }

  return (
    <div className="space-y-7">
      <section className="overflow-hidden rounded-3xl border border-brand/30 bg-gradient-to-br from-brand/15 via-panel to-ink p-7 shadow-2xl shadow-brand/5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full border border-brand/40 bg-brand/10 px-3 py-1 text-xs font-medium text-brand">
            Track 01 · AI Growth & Agentic Commerce
          </span>
          <span
            className={
              "rounded-full border px-3 py-1 text-xs " +
              (health?.ok
                ? "border-allow/40 bg-allow/10 text-allow"
                : "border-edge text-muted")
            }
          >
            {health?.ok
              ? `${health.demo_mode ? "SIMULATED" : "LIVE"} actuator · ${health.mcp}`
              : "backend status unavailable"}
          </span>
        </div>
        <div className="mt-6 max-w-4xl">
          <p className="label text-brand">Safe Autopilot Checkout</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-5xl">
            One approval for the job.
            <span className="block text-brand">Zero authority beyond it.</span>
          </h1>
          <p className="mt-4 max-w-3xl text-sm leading-6 text-muted sm:text-base">
            AI may plan and recover a purchase. Only a deterministic, versioned
            Purchase Envelope can authorize the final Razorpay action.
          </p>
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

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(340px,0.8fr)]">
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

              <div className="mt-5 rounded-xl border border-edge bg-ink p-3 font-mono text-[11px] text-muted">
                <div>version {envelope.version}</div>
                <div>envelope {shortHash(envelope.envelope_hash)}</div>
                <div>expires {new Date(envelope.expires_at * 1000).toLocaleTimeString()}</div>
              </div>

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
                    <p className="label">Fault injection (demo only)</p>
                    <span className="rounded-full border border-brand/30 bg-brand/10 px-2 py-0.5 font-mono text-[11px] text-brand">
                      provider: {result?.provider_mode ?? (health?.demo_mode ? `Simulated (${health.mcp})` : (health?.mcp ?? "simulated"))}
                    </span>
                  </div>
                  <h2 className="mt-1 text-lg font-semibold">Simulate real-world faults</h2>
                  <p className="mt-1 text-xs text-muted">
                    These scenarios are injected by the demo operator to exercise the verifier deterministically; the endpoint refuses them outside DEMO_MODE.
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
                        : "border-edge bg-ink hover:border-brand")
                    }
                    onClick={() => {
                      setScenario(item.id);
                      setAttemptId(newIdentity("safe_attempt"));
                    }}
                    disabled={busy}
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
          <BoundaryCard />
          {result ? <ResultCard result={result} /> : <WaitingCard />}
        </aside>
      </div>
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

function BoundaryCard() {
  return (
    <section className="card">
      <p className="label">Control boundary</p>
      <div className="mt-4 space-y-3 text-sm">
        <BoundaryRow actor="AI" action="Draft, plan, rank, explain" allowed />
        <BoundaryRow actor="Code" action="Verify every final field" allowed />
        <BoundaryRow actor="AI" action="Activate or widen authority" allowed={false} />
        <BoundaryRow actor="Actuator" action="Redeem one exact Action Grant" allowed />
      </div>
      <p className="mt-4 border-t border-edge pt-4 text-xs leading-5 text-muted">
        The envelope is application-level authority, not a banking mandate and not
        a claim of access to private Razorpay or Vulcan APIs.
      </p>
    </section>
  );
}

function BoundaryRow({ actor, action, allowed }: { actor: string; action: string; allowed: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span className={allowed ? "text-allow" : "text-block"}>{allowed ? "✓" : "×"}</span>
      <span className="w-16 font-mono text-xs text-muted">{actor}</span>
      <span>{action}</span>
    </div>
  );
}

function WaitingCard() {
  return (
    <section className="card border-dashed">
      <p className="label">Evidence receipt</p>
      <p className="mt-3 text-sm leading-6 text-muted">
        The result appears here: exact quote facts, policy deltas, provider state,
        and the application-signed receipt digest.
      </p>
    </section>
  );
}

function ResultCard({ result }: { result: AutopilotResponse }) {
  const allowed = result.envelope_decision.allowed;
  return (
    <section
      className={
        "rounded-2xl border p-5 " +
        (allowed ? "border-allow/50 bg-allow/5" : "border-block/50 bg-block/5")
      }
    >
      <div className="flex items-center justify-between gap-3">
        <p className="label">Decision</p>
        <span className={allowed ? "text-allow" : "text-block"}>
          {allowed ? "AUTHORIZED" : "REFUSED"}
        </span>
      </div>
      <p className="mt-3 text-sm leading-6">{result.envelope_decision.human_message}</p>
      <div className="mt-3 rounded-xl border border-edge bg-ink p-3 font-mono text-[11px]">
        <div className={allowed ? "text-allow" : "text-block"}>
          {result.envelope_decision.code}
        </div>
        <div className="mt-1 text-muted">provider {result.provider_mode}</div>
        <div className="text-muted">state {result.action_status ?? "no action"}</div>
      </div>

      {result.recovery_applied && (
        <div className="mt-3 rounded-xl border border-allow/30 bg-allow/10 p-3 text-xs text-allow">
          In-envelope recovery applied. No new approval was required.
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
        <a
          href={result.payment_link}
          target="_blank"
          rel="noreferrer"
          className="btn mt-4 inline-block"
        >
          Open simulated Razorpay link
        </a>
      )}

      {result.receipt && (
        <div className="mt-4 rounded-xl border border-edge bg-ink p-3 font-mono text-[11px] text-muted">
          <div className="flex items-center justify-between">
            <p className="text-slate-100 font-medium">Application-signed Action Receipt</p>
            <span className="rounded-full bg-allow/10 border border-allow/30 px-2 py-0.5 text-[10px] text-allow">
              auth core valid
            </span>
          </div>
          <div className="mt-2 space-y-1">
            <p className="text-slate-300 font-sans text-xs">Authorization core (stable across settlement):</p>
            <p className="pl-2">grant {shortHash(result.receipt.grant_id)}</p>
            <p className="pl-2">quote {shortHash(result.receipt.quote_hash)}</p>
            <p className="pl-2">args {shortHash(result.receipt.args_hash)}</p>
            <p className="pl-2">auth_sig {shortHash(result.receipt.authorization_signature ?? result.receipt.signature)}</p>
            <p className="mt-2 text-slate-300 font-sans text-xs">Status block ({result.action_status}):</p>
            <p className="pl-2">status_sig {shortHash(result.receipt.status_signature ?? result.receipt.signature)}</p>
          </div>
          <p className="mt-2 text-[10px] text-muted">Dual HMAC-SHA256 · auth core survives settlement</p>
        </div>
      )}
    </section>
  );
}
