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

  function handleReviewLimits() {
    setStep("approval");
  }

  async function handleApproveAndFinish() {
    if (!envelope || !sessionId || !attemptId) return;
    setBusy(true);
    setError(null);
    setStep("progress");

    try {
      const active = await api.activateEnvelope(envelope.id, envelope.envelope_hash);
      setEnvelope(active);
      await new Promise((r) => setTimeout(r, 900));

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
    <div className="space-y-8 max-w-5xl mx-auto py-6">
      <section className="bg-[#0B1020] border border-blue-900/40 rounded-2xl p-6 text-white shadow-md">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-900/50 text-blue-300 border border-blue-700/50">
              Preserved Safe Autopilot Baseline
            </span>
            <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-300">
              Track 01 Reference
            </span>
          </div>
          <Link href="/" className="text-xs font-semibold text-blue-400 hover:underline">
            &larr; Back to Merchant Overview
          </Link>
        </div>

        <h1 className="mt-4 text-2xl sm:text-3xl font-bold text-white tracking-tight">
          Safe Autopilot Shopper Flow
        </h1>
        <p className="mt-2 text-sm text-slate-300 max-w-xl">
          One approval for the job. Zero authority beyond it. The agent proposes and replaces stock within the envelope bounds.
        </p>
      </section>

      <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
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
              <CheckoutReady outcome={outcome} onStartNewOrder={handleReset} />
            )}
            {outcome.kind === "paused" && (
              <CheckoutPaused
                outcome={outcome}
                onReviewNewApproval={handleReset}
                onCancelOrder={handleReset}
              />
            )}
            {outcome.kind === "confirming" && (
              <CheckoutConfirming outcome={outcome} onStartNewOrder={handleReset} />
            )}
          </div>
        )}
      </section>
    </div>
  );
}

export default function SafeAutopilotPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-slate-500">Loading Safe Autopilot Baseline...</div>}>
      <SafeAutopilotContent />
    </Suspense>
  );
}
