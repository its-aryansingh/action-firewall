"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  api,
  type AutopilotResponse,
  type AutopilotScenario,
  type Health,
  type PurchaseEnvelope,
} from "@/lib/api";
import {
  envelopeToApprovalSummary,
  envelopeToShoppingPlan,
  autopilotToOutcomeView,
  type CheckoutOutcomeView,
} from "@/lib/presentation";
import { IntentComposer } from "@/components/storefront/IntentComposer";
import { ShoppingPlan } from "@/components/storefront/ShoppingPlan";
import { ApprovalSheet } from "@/components/storefront/ApprovalSheet";
import { AgentProgress } from "@/components/storefront/AgentProgress";
import { CheckoutReady } from "@/components/storefront/CheckoutReady";
import { CheckoutPaused } from "@/components/storefront/CheckoutPaused";
import { CheckoutConfirming } from "@/components/storefront/CheckoutConfirming";

type FlowStep = "intent" | "plan" | "approval" | "progress" | "outcome";

function SafeAutopilotContent() {
  const searchParams = useSearchParams();
  const queryScenario = searchParams.get("scenario") as AutopilotScenario | null;

  const [step, setStep] = useState<FlowStep>("intent");
  const [goal, setGoal] = useState("Buy supplies for a pasta dinner");
  const [budget, setBudget] = useState("600");
  const [envelope, setEnvelope] = useState<PurchaseEnvelope | null>(null);
  const [outcome, setOutcome] = useState<CheckoutOutcomeView | null>(null);
  const [scenario, setScenario] = useState<AutopilotScenario>(queryScenario || "stock_loss");
  const [health, setHealth] = useState<Health | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [attemptId, setAttemptId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSessionId(`safe_session_${globalThis.crypto.randomUUID()}`);
    setAttemptId(`att_${globalThis.crypto.randomUUID()}`);
    api.health()
      .then((h) => {
        setHealth(h);
        if (h.payment_provider === "razorpay_mcp" || !h.fault_injection_enabled) {
          setScenario("normal");
        }
      })
      .catch(() => setHealth(null));
  }, []);

  const planView = useMemo(() => {
    if (!envelope) return null;
    return envelopeToShoppingPlan(envelope);
  }, [envelope]);

  const approvalView = useMemo(() => {
    if (!envelope) return null;
    return envelopeToApprovalSummary(envelope);
  }, [envelope]);

  // Step 1 -> 2: Draft Shopping Plan
  async function handlePlanOrder() {
    const rupees = Number.parseInt(budget, 10);
    if (!goal.trim() || !Number.isFinite(rupees) || rupees <= 0) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.draftEnvelope(goal.trim(), rupees);
      setEnvelope(created);
      setAttemptId(`att_${globalThis.crypto.randomUUID()}`);
      setStep("plan");
    } catch (caught) {
      setError(`Could not compose shopping plan: ${String(caught)}`);
    } finally {
      setBusy(false);
    }
  }

  // Step 2 -> 3: Review Limits
  function handleReviewLimits() {
    setStep("approval");
  }

  // Step 3 -> 4 & 5: Approve limits once and let agent finish
  async function handleApproveAndFinish() {
    if (!envelope || !sessionId || !attemptId) return;
    setBusy(true);
    setError(null);
    setStep("progress");

    try {
      // 1. Activate envelope with expected hash
      const active = await api.activateEnvelope(envelope.id, envelope.envelope_hash);
      setEnvelope(active);

      // Brief progress display
      await new Promise((r) => setTimeout(r, 900));

      // 2. Execute autopilot checkout with bound attempt
      const executed = await api.executeAutopilot(
        active,
        sessionId,
        attemptId,
        scenario,
      );

      setEnvelope(executed.envelope);
      const outcomeModel = autopilotToOutcomeView(executed, planView?.totalPaise || 41700);
      setOutcome(outcomeModel);
      setStep("outcome");
    } catch (caught) {
      setError(`Checkout execution interrupted: ${String(caught)}`);
      setStep("approval");
    } finally {
      setBusy(false);
    }
  }

  function handleReset() {
    setEnvelope(null);
    setOutcome(null);
    setError(null);
    setStep("intent");
    setAttemptId(`att_${globalThis.crypto.randomUUID()}`);
  }

  return (
    <div className="space-y-8">
      {/* Product Hero */}
      <section className="hero-shell">
        <div className="hero-orb hero-orb-one" />
        <div className="hero-orb hero-orb-two" />
        <div className="relative">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="status-pill border-brand/40 bg-brand/10 text-brand font-semibold">
                Track 01: AI Growth & Agentic Commerce
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

            <Link
              href="/impact"
              className="text-xs font-semibold text-brand hover:underline inline-flex items-center gap-1"
            >
              See Merchant Impact &rarr;
            </Link>
          </div>

          <h1 className="mt-5 text-3xl font-bold tracking-tight text-white sm:text-5xl max-w-2xl leading-[1.1]">
            Tell us what you need.{" "}
            <span className="text-gradient">Approve the limits once.</span> The agent handles the cart.
          </h1>

          <p className="mt-3.5 max-w-xl text-sm leading-relaxed text-slate-300">
            Safe Autopilot turns conversational intent into a verified checkout and recovers from eligible stock changes without sending the shopper back through the cart.
          </p>
        </div>
      </section>

      {/* Main Experience Flow */}
      <section className="relative">
        {step === "intent" && (
          <IntentComposer
            goal={goal}
            setGoal={setGoal}
            budget={budget}
            setBudget={setBudget}
            busy={busy}
            error={error}
            onPlan={handlePlanOrder}
            aiVoiceConfigured={health?.voice_ai_configured ?? false}
          />
        )}

        {step === "plan" && planView && (
          <ShoppingPlan
            plan={planView}
            onEditGoal={() => setStep("intent")}
            onReviewLimits={handleReviewLimits}
            busy={busy}
          />
        )}

        {step === "approval" && approvalView && (
          <ApprovalSheet
            summary={approvalView}
            onApprove={handleApproveAndFinish}
            onEdit={() => setStep("plan")}
            busy={busy}
            error={error}
          />
        )}

        {step === "progress" && (
          <AgentProgress
            planPaise={planView?.totalPaise || 41700}
            providerDegraded={false}
          />
        )}

        {step === "outcome" && outcome && (
          <div>
            {outcome.kind === "ready" && (
              <CheckoutReady
                outcome={outcome}
                onStartNewOrder={handleReset}
              />
            )}

            {outcome.kind === "paused" && (
              <CheckoutPaused
                outcome={outcome}
                onReviewNewApproval={handleReset}
                onCancelOrder={handleReset}
              />
            )}

            {outcome.kind === "confirming" && (
              <CheckoutConfirming
                outcome={outcome}
                onStartNewOrder={handleReset}
              />
            )}
          </div>
        )}
      </section>

      {/* Footer reassurance */}
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-edge/60 bg-panel/40 p-4 text-xs text-muted">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-allow" />
          <span>Deterministic authorization: model creativity never establishes trusted prices or payment authority.</span>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/impact" className="hover:text-white transition-colors">
            Merchant Impact
          </Link>
          <span>·</span>
          <Link href="/audit" className="hover:text-white transition-colors">
            Technical Trust Evidence
          </Link>
        </div>
      </section>
    </div>
  );
}

export default function SafeAutopilotPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-muted">Loading Safe Autopilot...</div>}>
      <SafeAutopilotContent />
    </Suspense>
  );
}
