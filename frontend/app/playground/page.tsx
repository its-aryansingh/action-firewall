"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  api,
  inr,
  type AutopilotScenario,
  type CommerceAttemptResponse,
  type IntentCreateResponse,
  type PurchaseEnvelope,
  type SlippageItem,
  type RefundPolicy,
  type RefundEvaluateResponse,
  type RefundExecuteResponse,
  type Health,
} from "@/lib/api";
import { Card, KpiCard, StatusChip, EvidenceBadge, EmptyState } from "@/components/ui";

const QUICK_GOALS = [
  "Pantry restock: Oat milk 1L, Penne 500g, Tomato passata",
  "Breakfast supplies for the office",
  "Restock Italian pantry ingredients",
  "Weekly fresh grocery essentials",
];

export default function AIPlaygroundPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [goal, setGoal] = useState("Pantry restock: Oat milk 1L, Penne 500g, Tomato passata");
  const [budgetRupees, setBudgetRupees] = useState("7840");
  const [buyerType, setBuyerType] = useState<"gemini" | "replay">("gemini");
  const [scenario, setScenario] = useState<AutopilotScenario>("normal");

  // Workbench Mode: "single", "race", or "refund"
  const [workbenchMode, setWorkbenchMode] = useState<"race" | "single" | "refund">("single");

  // Slippage & Outbound Refund States
  const [slippageItems, setSlippageItems] = useState<SlippageItem[]>([]);
  const [slippageBusy, setSlippageBusy] = useState(false);
  const [refundPolicy, setRefundPolicy] = useState<RefundPolicy | null>(null);
  const [refundPaymentId, setRefundPaymentId] = useState("pay_test_01");
  const [refundAmountRupees, setRefundAmountRupees] = useState("300");
  const [refundReason, setRefundReason] = useState("Damaged item during transit");
  const [refundOriginalAmountRupees, setRefundOriginalAmountRupees] = useState("2000");
  const [refundAlreadyRefundedRupees, setRefundAlreadyRefundedRupees] = useState("0");
  const [refundOrderAgeDays, setRefundOrderAgeDays] = useState(5);
  const [refundAutoRepair, setRefundAutoRepair] = useState(true);
  const [refundEvalResult, setRefundEvalResult] = useState<RefundEvaluateResponse | null>(null);
  const [refundExecResult, setRefundExecResult] = useState<RefundExecuteResponse | null>(null);
  const [refundBusy, setRefundBusy] = useState(false);
  const [refundNotice, setRefundNotice] = useState<string | null>(null);

  useEffect(() => {
    api.health().then((h) => {
      setHealth(h);
      if (h.payment_provider === "razorpay_rest") {
        setWorkbenchMode("single");
        setScenario("normal");
      }
    }).catch(() => {});
  }, []);

  const isLiveRazorpay = health?.payment_provider === "razorpay_rest";

  // Load slippage and policy when refund tab opens
  useEffect(() => {
    if (workbenchMode === "refund") {
      loadSlippageAndPolicy();
    }
  }, [workbenchMode]);

  async function loadSlippageAndPolicy() {
    try {
      const [slip, pol] = await Promise.all([
        api.agentCommerce.getSlippageState(),
        api.agentCommerce.getRefundPolicy(),
      ]);
      setSlippageItems(slip);
      setRefundPolicy(pol);
    } catch (err) {
      console.warn("Could not load slippage/policy data", err);
    }
  }

  async function handleDepleteStock(sku: string) {
    setSlippageBusy(true);
    try {
      await api.agentCommerce.depleteStock(sku);
      const slip = await api.agentCommerce.getSlippageState();
      setSlippageItems(slip);
      setRefundNotice(`Stock depleted for SKU: ${sku}. Mid-demo inventory drift simulated.`);
    } catch (err: any) {
      setRefundNotice(`Deplete stock failed: ${err.message || String(err)}`);
    } finally {
      setSlippageBusy(false);
    }
  }

  async function handleResetStock() {
    setSlippageBusy(true);
    try {
      await api.agentCommerce.resetStock();
      const slip = await api.agentCommerce.getSlippageState();
      setSlippageItems(slip);
      setRefundNotice("Catalog stock reset to baseline quantities across all items.");
    } catch (err: any) {
      setRefundNotice(`Reset stock failed: ${err.message || String(err)}`);
    } finally {
      setSlippageBusy(false);
    }
  }

  async function handleEvaluateRefund() {
    setRefundBusy(true);
    setRefundNotice(null);
    try {
      const amountPaise = (Number.parseFloat(refundAmountRupees) || 0) * 100;
      const origPaise = (Number.parseFloat(refundOriginalAmountRupees) || 0) * 100;
      const alreadyPaise = (Number.parseFloat(refundAlreadyRefundedRupees) || 0) * 100;
      const res = await api.agentCommerce.evaluateRefund({
        payment_id: refundPaymentId,
        amount_paise: amountPaise,
        reason: refundReason,
        original_amount_paise: origPaise,
        already_refunded_paise: alreadyPaise,
        order_age_days: refundOrderAgeDays,
      });
      setRefundEvalResult(res);
      setRefundExecResult(null);
    } catch (err: any) {
      setRefundNotice(`Refund evaluation failed: ${err.message || String(err)}`);
    } finally {
      setRefundBusy(false);
    }
  }

  async function handleExecuteRefund() {
    setRefundBusy(true);
    setRefundNotice(null);
    try {
      const amountPaise = (Number.parseFloat(refundAmountRupees) || 0) * 100;
      const origPaise = (Number.parseFloat(refundOriginalAmountRupees) || 0) * 100;
      const alreadyPaise = (Number.parseFloat(refundAlreadyRefundedRupees) || 0) * 100;
      const res = await api.agentCommerce.executeRefund({
        payment_id: refundPaymentId,
        amount_paise: amountPaise,
        reason: refundReason,
        attempt_id: `ref_att_${Date.now()}`,
        auto_repair: refundAutoRepair,
        original_amount_paise: origPaise,
        already_refunded_paise: alreadyPaise,
      });
      setRefundExecResult(res);
    } catch (err: any) {
      setRefundNotice(`Refund execution failed: ${err.message || String(err)}`);
    } finally {
      setRefundBusy(false);
    }
  }

  // Race States
  const [raceRunning, setRaceRunning] = useState(false);
  const [raceCompleted, setRaceCompleted] = useState(false);
  const [baselineResult, setBaselineResult] = useState<{
    stage: string;
    status: "quote" | "drift" | "abandoned";
    message: string;
    loss_amount: string;
  } | null>(null);
  const [firewallResult, setFirewallResult] = useState<{
    stage: string;
    status: "quote" | "recovering" | "issued" | "failed";
    message: string;
    link: string | null;
    saved_amount: string;
    scope?: string;
  } | null>(null);

  // Single Checkout Workflow states
  const [busy, setBusy] = useState(false);
  const [currentStage, setCurrentStage] = useState<number>(0); // 0=idle, 1=understand, 2=quote, 3=authorize, 4=done
  const [intentResp, setIntentResp] = useState<IntentCreateResponse | null>(null);
  const [activeEnvelope, setActiveEnvelope] = useState<PurchaseEnvelope | null>(null);
  const [attemptResp, setAttemptResp] = useState<CommerceAttemptResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleReset() {
    setIntentResp(null);
    setActiveEnvelope(null);
    setAttemptResp(null);
    setError(null);
    setCurrentStage(0);
    setRaceCompleted(false);
    setBaselineResult(null);
    setFirewallResult(null);
    setRefundEvalResult(null);
    setRefundExecResult(null);
    setRefundNotice(null);
  }

  // --- TWO-LANE RACE ---
  //
  // The right-hand lane is a real call: it drafts an envelope, has it activated,
  // and submits an attempt under the stock_loss scenario. Every figure it shows
  // comes back from that call.
  //
  // It used to send buyer_agent_id "buyer_mcp", which the identity guard
  // refuses with a 403 — and the catch block then displayed a SUCCESSFUL
  // recovery with a fabricated Razorpay link anyway, so the lane looked right
  // whether or not the backend did anything. A demo that reports success when
  // the call failed is worse than one that breaks, so a failure now says so.
  //
  // The left-hand lane is not a second backend: it is what an exact-cart
  // checkout does when the cart hash is invalidated by a stock change. It is
  // labelled as a comparison, and its rupee figure is the same real cart total
  // the right-hand lane recovered, so the two sides are never quoting different
  // baskets at each other.
  async function runTwoLaneRace() {
    setRaceRunning(true);
    setRaceCompleted(false);
    setError(null);

    setBaselineResult({
      stage: "Quoting the exact cart",
      status: "quote",
      message: "Shopper confirms an exact basket at checkout.",
      loss_amount: "—",
    });
    setFirewallResult({
      stage: "Drafting the envelope",
      status: "quote",
      message: "Customer approves the job once, before the agent shops.",
      link: null,
      saved_amount: "—",
    });

    try {
      const reqId = `race_${Date.now()}`;
      const sessId = `sess_race_${Date.now()}`;

      const draftRes = await api.agentCommerce.createIntent({
        agent_request_id: reqId,
        natural_language_intent: goal,
        budget_paise: 800000,
        buyer_agent_id: "buyer_replay",
        shopper_session_id: sessId,
      });

      const capPaise = draftRes.draft_envelope.max_total_paise;
      setFirewallResult({
        stage: "Awaiting human activation",
        status: "quote",
        message: "Drafted. Nothing can be authorised until a person activates it.",
        link: null,
        saved_amount: "—",
        scope: `${inr(capPaise)} ceiling · ${draftRes.draft_envelope.slots.length} slots`,
      });

      await api.agentCommerce.activateEnvelope(
        draftRes.draft_envelope.id,
        draftRes.draft_envelope.envelope_hash,
      );

      setBaselineResult({
        stage: "Catalog drift detected",
        status: "drift",
        message: "An item goes out of stock. The confirmed cart hash no longer matches.",
        loss_amount: "—",
      });

      const attemptRes = await api.agentCommerce.submitAttempt({
        envelope_id: draftRes.draft_envelope.id,
        purchase_attempt_id: `att_${Date.now()}`,
        scenario: "stock_loss",
        buyer_agent_id: "buyer_replay",
      });

      const totalPaise = attemptRes.quote_total_paise;
      const completed =
        attemptRes.outcome === "ACTION_ISSUED" ||
        attemptRes.outcome === "RECOVERED_INSIDE_ENVELOPE";

      setBaselineResult({
        stage: "Order abandoned",
        status: "abandoned",
        message:
          "The exact cart is stale, so the shopper is sent back to re-confirm. Most do not return.",
        loss_amount: completed ? `${inr(totalPaise)} lost` : "—",
      });

      setFirewallResult({
        stage: completed ? "Recovered and issued" : `Stopped — ${attemptRes.code}`,
        status: completed ? "issued" : "failed",
        message: attemptRes.human_message,
        link: attemptRes.payment_link ?? null,
        saved_amount: completed ? `${inr(totalPaise)} completed` : "nothing issued",
        scope: `${inr(capPaise)} ceiling · repaired in-envelope: ${
          attemptRes.recovery_applied ? "yes" : "no"
        }`,
      });

      setRaceCompleted(true);
    } catch (err: any) {
      // No fabricated outcome here on purpose.
      const detail = err?.message || String(err);
      setError(`Race failed: ${detail}`);
      setBaselineResult(null);
      setFirewallResult({
        stage: "Call failed",
        status: "failed",
        message: detail,
        link: null,
        saved_amount: "—",
      });
      setRaceCompleted(false);
    } finally {
      setRaceRunning(false);
    }
  }

  // --- SINGLE CHECKOUT 4-STAGE FLOW ---
  async function handleStartCheckout() {
    setError(null);
    setBusy(true);
    setCurrentStage(1);
    const budgetPaise = (Number.parseInt(budgetRupees, 10) || 7840) * 100;
    const reqId = `req_${Math.random().toString(36).slice(2, 10)}`;
    const sessId = `sess_${Math.random().toString(36).slice(2, 10)}`;

    try {
      const res = await api.agentCommerce.createIntent({
        agent_request_id: reqId,
        natural_language_intent: goal,
        budget_paise: budgetPaise,
        buyer_agent_id: buyerType === "gemini" ? "buyer_gemini" : "buyer_replay",
        shopper_session_id: sessId,
      });

      setIntentResp(res);
      setCurrentStage(2);
    } catch (err: any) {
      setError(`Failed to draft intent: ${err.message || String(err)}`);
      setCurrentStage(0);
    } finally {
      setBusy(false);
    }
  }

  async function handleActivateEnvelope() {
    if (!intentResp?.draft_envelope) return;
    setBusy(true);
    setError(null);
    try {
      const active = await api.agentCommerce.activateEnvelope(
        intentResp.draft_envelope.id,
        intentResp.draft_envelope.envelope_hash
      );
      setActiveEnvelope(active);
      setCurrentStage(3);
    } catch (err: any) {
      setError(`Activation failed: ${err.message || String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleExecuteAttempt() {
    const env = activeEnvelope || intentResp?.draft_envelope;
    if (!env) return;
    setBusy(true);
    setError(null);
    const attemptId = `att_${Math.random().toString(36).slice(2, 10)}`;

    try {
      const resp = await api.agentCommerce.submitAttempt({
        envelope_id: env.id,
        purchase_attempt_id: attemptId,
        scenario: scenario,
        buyer_agent_id: buyerType === "gemini" ? "buyer_gemini" : "buyer_replay",
      });

      setAttemptResp(resp);
      setCurrentStage(4);
    } catch (err: any) {
      setError(`Attempt execution failed: ${err.message || String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8 pb-12 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border/80 pb-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-text">Agent Checkout Playground</h1>
            <EvidenceBadge buyerModel={buyerType === "gemini" ? "Gemini 3.8 Flash" : "Replay buyer"} />
          </div>
          <p className="text-xs text-muted mt-0.5">
            Test the 4-stage Protected Agent Checkout and the side-by-side Two-Lane race
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Mode Switcher */}
          <div className="inline-flex rounded-xl border border-border bg-surface p-1 text-xs">
            <button
              onClick={() => setWorkbenchMode("race")}
              className={`rounded-lg px-3 py-1.5 font-semibold transition ${
                workbenchMode === "race"
                  ? "bg-primary text-white shadow-xs"
                  : "text-muted hover:text-text"
              }`}
            >
              Two-Lane Race
            </button>
            <button
              onClick={() => setWorkbenchMode("single")}
              className={`rounded-lg px-3 py-1.5 font-semibold transition ${
                workbenchMode === "single"
                  ? "bg-primary text-white shadow-xs"
                  : "text-muted hover:text-text"
              }`}
            >
              4-Stage Workbench
            </button>
            <button
              onClick={() => setWorkbenchMode("refund")}
              className={`rounded-lg px-3 py-1.5 font-semibold transition ${
                workbenchMode === "refund"
                  ? "bg-primary text-white shadow-xs"
                  : "text-muted hover:text-text"
              }`}
            >
              Refund &amp; Slippage
            </button>
          </div>

          <button
            onClick={handleReset}
            className="rounded-xl border border-border bg-surface px-3.5 py-2 text-xs font-semibold text-text hover:bg-canvas transition"
          >
            Reset
          </button>
        </div>
      </div>

      {/* ========================================================= */}
      {/* MODE 1: THE TWO-LANE RACE (GATE B5)                       */}
      {/* ========================================================= */}
      {workbenchMode === "race" && (
        <div className="space-y-6">
          <Card
            title="The Two-Lane Race: Exact-Cart vs Action Firewall"
            subtitle="Runs the exact same checkout under catalog drift through traditional cart approval versus Action Firewall semantic authority"
            action={
              <button
                onClick={runTwoLaneRace}
                disabled={raceRunning || isLiveRazorpay}
                title={isLiveRazorpay ? "Drift race requires Simulated provider mode per Invariant 17" : undefined}
                className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-primary-hover disabled:opacity-50 transition"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <span>{raceRunning ? "Running race..." : "Run the 20-Second Race"}</span>
              </button>
            }
          >
            {isLiveRazorpay && (
              <div className="mb-6 rounded-xl border border-warning/30 bg-warning/10 p-4 text-xs">
                <div className="flex items-center gap-2 font-bold text-warning">
                  <span>⚠️ Connected to Razorpay Test Mode ({health?.payment_provider})</span>
                </div>
                <p className="mt-1 text-muted leading-relaxed">
                  Under Action Firewall <strong>Security Invariant 17</strong>, synthetic fault injection (catalog stock loss drift) is strictly blocked when connected to a live payment gateway.
                  To run live checkouts with real Razorpay payment links, switch to the <strong>4-Stage Workbench</strong>.
                  To demonstrate this side-by-side catalog drift race, set <code className="font-mono text-text bg-canvas px-1.5 py-0.5 rounded">PAYMENT_PROVIDER=simulated</code> in <code className="font-mono text-text bg-canvas px-1.5 py-0.5 rounded">backend/.env</code>.
                </p>
              </div>
            )}
            {/* Goal Input Bar */}
            <div className="mb-6 rounded-xl border border-border bg-canvas/40 p-4">
              <label className="text-[11px] font-bold uppercase tracking-wider text-muted block mb-1">
                Active Shopping Intent
              </label>
              <div className="text-sm font-semibold text-text">{goal}</div>
              <p className="mt-1 text-xs text-muted">
                Condition: an item goes out of stock during agent execution. Every figure below comes from the run.
              </p>
            </div>

            {/* Side-by-Side Lanes Grid */}
            <div className="grid gap-6 md:grid-cols-2">
              {/* LANE 1: EXACT-CART APPROVAL */}
              <div className="flex flex-col justify-between rounded-2xl border-2 border-danger/30 bg-danger/[0.02] p-6">
                <div>
                  <div className="flex items-center justify-between border-b border-danger/20 pb-3">
                    <div>
                      <span className="text-[10px] font-mono uppercase font-bold text-danger">Lane 1</span>
                      <h3 className="text-base font-bold text-text">Exact-Cart Approval (/baseline)</h3>
                    </div>
                    <span className="rounded-full bg-danger/10 px-2.5 py-0.5 text-xs font-semibold text-danger">
                      Traditional Cart
                    </span>
                  </div>

                  <div className="mt-5 space-y-4 text-xs">
                    <div className="flex items-center justify-between border-b border-border/60 pb-2">
                      <span className="text-muted">Cart at authorization:</span>
                      <span className="font-mono font-bold text-text">{firewallResult?.saved_amount ?? "—"}</span>
                    </div>

                    <div className="rounded-xl border border-border bg-surface p-3 space-y-1">
                      <span className="text-[10px] font-bold uppercase text-muted">Inventory Fact</span>
                      <p className="text-text">{baselineResult?.message ?? "An item goes out of stock mid-checkout."}</p>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-danger font-medium">
                        <span>✖</span>
                        <span>Cart hash mismatch / invalid cart</span>
                      </div>
                      <div className="flex items-center gap-2 text-danger font-medium">
                        <span>✖</span>
                        <span>Customer must re-approve cart manually</span>
                      </div>
                      <div className="flex items-center gap-2 text-danger font-medium">
                        <span>✖</span>
                        <span>Order abandoned by shopper</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-6 border-t border-danger/20 pt-4 text-center">
                  <div className="font-mono text-2xl font-extrabold text-danger">
                    {baselineResult ? baselineResult.loss_amount : "—"}
                  </div>
                  <span className="text-[11px] text-muted">Provider actuator never completed</span>
                </div>
              </div>

              {/* LANE 2: ACTION FIREWALL */}
              <div className="flex flex-col justify-between rounded-2xl border-2 border-success/30 bg-success/[0.02] p-6 shadow-sm">
                <div>
                  <div className="flex items-center justify-between border-b border-success/20 pb-3">
                    <div>
                      <span className="text-[10px] font-mono uppercase font-bold text-success">Lane 2</span>
                      <h3 className="text-base font-bold text-text">Action Firewall Gateway</h3>
                    </div>
                    <span className="rounded-full bg-success/10 px-2.5 py-0.5 text-xs font-semibold text-success">
                      Semantic Scope
                    </span>
                  </div>

                  <div className="mt-5 space-y-4 text-xs">
                    <div className="flex items-center justify-between border-b border-border/60 pb-2">
                      <span className="text-muted">Customer Scope Bound:</span>
                      <span className="font-mono font-bold text-text">{firewallResult?.scope ?? "set once, by the customer"}</span>
                    </div>

                    <div className="rounded-xl border border-border bg-surface p-3 space-y-1">
                      <span className="text-[10px] font-bold uppercase text-muted">Inventory Fact</span>
                      <p className="text-text">{baselineResult?.message ?? "An item goes out of stock mid-checkout."}</p>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-success font-medium">
                        <span>✔</span>
                        <span>{firewallResult?.message ?? "The store substitutes inside what was already approved."}</span>
                      </div>
                      <div className="flex items-center gap-2 text-success font-medium">
                        <span>✔</span>
                        <span>Inside pre-approved 10% substitution ceiling</span>
                      </div>
                      <div className="flex items-center gap-2 text-success font-medium">
                        <span>✔</span>
                        <span>One-time Action Grant minted without re-prompt</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-6 border-t border-success/20 pt-4 text-center">
                  <div className="font-mono text-2xl font-extrabold text-success">
                    {firewallResult ? firewallResult.saved_amount : "—"}
                  </div>
                  <div className="mt-1">
                    {firewallResult?.link ? (
                      <a
                        href={firewallResult.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 font-mono text-xs font-semibold text-primary hover:underline"
                      >
                        <span>Open the issued link ↗</span>
                      </a>
                    ) : (
                      <span className="font-mono text-xs text-muted">No link — nothing was issued</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* ========================================================= */}
      {/* MODE 2: 4-STAGE INTERACTIVE WORKBENCH                     */}
      {/* ========================================================= */}
      {workbenchMode === "single" && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Controls Column */}
          <div className="lg:col-span-5 rounded-2xl border border-border bg-surface p-6 shadow-sm space-y-5">
            <div>
              <h2 className="text-xs font-bold text-text uppercase tracking-wider">
                1. Natural Language Shopping Goal
              </h2>
              <div className="mt-2 space-y-2">
                <textarea
                  rows={3}
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  className="w-full text-xs p-3 bg-canvas border border-border rounded-xl focus:outline-none focus:border-primary focus:bg-surface resize-none transition text-text"
                />
                <div className="flex flex-wrap gap-1.5">
                  {QUICK_GOALS.map((g) => (
                    <button
                      key={g}
                      type="button"
                      onClick={() => setGoal(g)}
                      className="text-[11px] px-2.5 py-1 rounded-lg bg-canvas text-muted hover:text-text hover:bg-border/60 transition"
                    >
                      {g}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Budget & Model Selector */}
            <div className="grid grid-cols-2 gap-3 pt-2">
              <div>
                <label className="text-[11px] font-bold text-text uppercase tracking-wider block">
                  Budget (INR)
                </label>
                <input
                  type="number"
                  value={budgetRupees}
                  onChange={(e) => setBudgetRupees(e.target.value)}
                  className="mt-1 w-full text-xs p-2.5 bg-canvas border border-border rounded-lg focus:outline-none focus:border-primary font-mono text-text"
                />
              </div>

              <div>
                <label className="text-[11px] font-bold text-text uppercase tracking-wider block">
                  AI Buyer Adapter
                </label>
                <select
                  value={buyerType}
                  onChange={(e) => setBuyerType(e.target.value as any)}
                  className="mt-1 w-full text-xs p-2.5 bg-canvas border border-border rounded-lg focus:outline-none focus:border-primary text-text"
                >
                  <option value="gemini">Gemini 3.8 Flash (MCP Tool Buyer)</option>
                  <option value="replay">Deterministic Replay Buyer</option>
                </select>
              </div>
            </div>

            {/* Simulation Scenario Selector */}
            <div className="pt-2">
              <label className="text-[11px] font-bold text-text uppercase tracking-wider block mb-1">
                Simulation Scenario
              </label>
              <div className="space-y-2">
                {[
                  {
                    id: "normal",
                    name: "Normal Checkout",
                    desc: "Catalog verified; live Razorpay payment link issued immediately",
                    liveReady: true,
                  },
                  {
                    id: "stock_loss",
                    name: "Stock Loss (In-Envelope Recovery)",
                    desc: "Penne is out of stock; automatically substitutes Spaghetti No.5 inside envelope",
                    liveReady: false,
                  },
                  {
                    id: "merchant_drift",
                    name: "Merchant Drift (Adversarial Refusal)",
                    desc: "Agent attempts unapproved merchant drift; stopped before actuator with Policy Delta",
                    liveReady: false,
                  },
                  {
                    id: "timeout_after_dispatch",
                    name: "Provider Timeout (Safety Holding)",
                    desc: "Provider call hangs; outcome held as UNKNOWN with zero blind retries",
                    liveReady: false,
                  },
                ].map((s) => {
                  const disabled = isLiveRazorpay && !s.liveReady;
                  return (
                    <label
                      key={s.id}
                      className={`flex items-start gap-3 p-3 rounded-xl border text-xs transition ${
                        disabled
                          ? "opacity-50 cursor-not-allowed border-border bg-canvas/20"
                          : scenario === s.id
                          ? "border-primary bg-primary/[0.03] shadow-xs cursor-pointer"
                          : "border-border bg-canvas/40 hover:bg-canvas cursor-pointer"
                      }`}
                    >
                      <input
                        type="radio"
                        name="scenario"
                        value={s.id}
                        disabled={disabled}
                        checked={scenario === s.id}
                        onChange={() => setScenario(s.id as AutopilotScenario)}
                        className="mt-0.5 text-primary focus:ring-0"
                      />
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-text">{s.name}</span>
                          {s.liveReady && isLiveRazorpay && (
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-success/10 text-success border border-success/30">
                              Live Ready
                            </span>
                          )}
                          {!s.liveReady && isLiveRazorpay && (
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-muted/10 text-muted border border-border">
                              Simulated Only (Inv. 17)
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-muted mt-0.5 leading-snug">{s.desc}</div>
                      </div>
                    </label>
                  );
                })}
              </div>
            </div>

            {/* Primary Submit CTA */}
            <div className="pt-3">
              <button
                onClick={handleStartCheckout}
                disabled={busy}
                className="w-full py-3 px-4 rounded-xl bg-primary hover:bg-primary-hover disabled:opacity-50 text-white text-xs font-bold shadow-sm transition flex items-center justify-center gap-2"
              >
                {busy ? (
                  <span>Executing Stage {currentStage}...</span>
                ) : (
                  <>
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    <span>Start Protected Agent Checkout</span>
                  </>
                )}
              </button>
            </div>

            {error && (
              <div className="p-3 bg-danger/10 rounded-lg border border-danger/30 text-xs text-danger">
                {error}
              </div>
            )}
          </div>

          {/* 4-Stage Execution Timeline Column */}
          <div className="lg:col-span-7 space-y-4">
            <div className="rounded-2xl border border-border bg-surface p-4 shadow-sm flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-muted">
                Four Stages: Understand &rarr; Quote &rarr; Authorize &rarr; Razorpay Action
              </span>
              <span className="text-[11px] font-mono text-muted">
                Stage: {currentStage === 0 ? "Idle" : `${currentStage} of 4`}
              </span>
            </div>

            {/* Stage 1 */}
            <div className={`p-5 rounded-2xl border transition-all ${currentStage >= 1 ? "bg-surface border-border shadow-sm" : "bg-canvas/40 border-border/60 opacity-60"}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 rounded-full bg-primary/10 text-primary text-xs font-bold items-center justify-center">1</span>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-text">Stage 1: Understand (Draft Purchase Envelope)</h3>
                </div>
                {intentResp && <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-warning/10 text-warning border border-warning/30">Proposal-Only</span>}
              </div>
              {intentResp?.draft_envelope ? (
                <div className="mt-3 space-y-2 text-xs bg-canvas p-3 rounded-xl border border-border font-mono">
                  <div className="flex justify-between">
                    <span className="text-muted">Envelope ID:</span>
                    <span className="text-text font-bold">{intentResp.draft_envelope.id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Max Budget:</span>
                    <span className="text-text font-bold">{inr(intentResp.draft_envelope.max_total_paise)}</span>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-muted mt-1">Translates goal into bounded slots. Zero payment provider authority active.</p>
              )}
            </div>

            {/* Stage 2 */}
            <div className={`p-5 rounded-2xl border transition-all ${currentStage >= 2 ? "bg-surface border-border shadow-sm" : "bg-canvas/40 border-border/60 opacity-60"}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 rounded-full bg-primary/10 text-primary text-xs font-bold items-center justify-center">2</span>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-text">Stage 2: Quote (Server-Resolved Catalog Facts)</h3>
                </div>
                {currentStage >= 2 && <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-success/10 text-success border border-success/30">Server Verified</span>}
              </div>
              {currentStage >= 2 ? (
                <div className="mt-3 text-xs bg-canvas p-3 rounded-xl border border-border space-y-1 font-mono">
                  <div className="flex justify-between">
                    <span className="text-muted">Target Merchant:</span>
                    <span className="font-bold text-text">merchant_freshbasket</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Estimated Total:</span>
                    <span className="font-bold text-primary">{firewallResult?.saved_amount ?? "set by the run"}</span>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-muted mt-1">Server evaluates inventory, unit prices in paise, and delivery profile.</p>
              )}
            </div>

            {/* Stage 3 */}
            <div className={`p-5 rounded-2xl border transition-all ${currentStage >= 2 ? "bg-surface border-border shadow-sm" : "bg-canvas/40 border-border/60 opacity-60"}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 rounded-full bg-primary/10 text-primary text-xs font-bold items-center justify-center">3</span>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-text">Stage 3: Authorize (Human Customer Activation)</h3>
                </div>
                {activeEnvelope ? (
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-success/10 text-success border border-success/30">Activated</span>
                ) : (
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-canvas text-muted border border-border">Awaiting Approval</span>
                )}
              </div>
              {currentStage >= 2 && !activeEnvelope && (
                <div className="mt-3 p-3.5 bg-primary/[0.04] border border-primary/20 rounded-xl">
                  <p className="text-xs text-text">The AI model cannot self-authorize. The human customer must review and activate.</p>
                  <button
                    onClick={handleActivateEnvelope}
                    disabled={busy}
                    className="mt-3 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-xs font-bold shadow-xs transition"
                  >
                    Approve &amp; Activate Envelope
                  </button>
                </div>
              )}
              {activeEnvelope && (
                <div className="mt-3 p-3 bg-success/[0.04] border border-success/20 rounded-xl text-xs space-y-2">
                  <div className="text-success font-semibold flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-success" />
                    Envelope activated! Ready for single atomic execution.
                  </div>
                  {currentStage === 3 && (
                    <button
                      onClick={handleExecuteAttempt}
                      disabled={busy}
                      className="mt-2 px-4 py-2 bg-success hover:bg-emerald-700 text-white rounded-lg text-xs font-bold shadow-xs transition"
                    >
                      Execute Attempt via Action Firewall &rarr;
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Stage 4 */}
            <div className={`p-5 rounded-2xl border transition-all ${currentStage >= 4 ? "bg-surface border-border shadow-sm" : "bg-canvas/40 border-border/60 opacity-60"}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 rounded-full bg-primary/10 text-primary text-xs font-bold items-center justify-center">4</span>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-text">Stage 4: Razorpay Action (Atomic Dispatch)</h3>
                </div>
              </div>
              {attemptResp ? (
                <div className="mt-3 space-y-3 text-xs">
                  {attemptResp.outcome === "RECOVERED_INSIDE_ENVELOPE" && (
                    <div className="p-4 rounded-xl bg-success/[0.06] border border-success/30 text-text space-y-2">
                      <div className="font-bold text-sm text-success flex items-center gap-1.5">
                        In-Envelope Stock Loss Recovery Applied
                      </div>
                      <p className="text-xs text-muted leading-relaxed">
                        Penne was out of stock. Action Firewall substituted <strong>Spaghetti No.5 (SKU-PAS-002)</strong> inside envelope bounds without re-prompting.
                      </p>
                      {attemptResp.payment_link && (
                        <div className="pt-2 flex items-center gap-2">
                          <input type="text" readOnly value={attemptResp.payment_link} className="flex-1 text-xs font-mono bg-surface border border-border rounded-lg p-2 text-text" />
                          <a href={attemptResp.payment_link} target="_blank" rel="noreferrer" className="px-3.5 py-2 text-xs font-bold bg-primary text-white rounded-lg hover:bg-primary-hover shrink-0">Open Link</a>
                        </div>
                      )}
                    </div>
                  )}
                  {attemptResp.outcome === "ACTION_ISSUED" && (
                    <div className="p-4 rounded-xl bg-primary/[0.06] border border-primary/30 text-text space-y-2">
                      <div className="font-bold text-sm text-primary flex items-center gap-1.5">Payment Link Issued Successfully</div>
                      {attemptResp.payment_link && (
                        <div className="pt-2 flex items-center gap-2">
                          <input type="text" readOnly value={attemptResp.payment_link} className="flex-1 text-xs font-mono bg-surface border border-border rounded-lg p-2 text-text" />
                          <a href={attemptResp.payment_link} target="_blank" rel="noreferrer" className="px-3.5 py-2 text-xs font-bold bg-primary text-white rounded-lg hover:bg-primary-hover shrink-0">Open Link</a>
                        </div>
                      )}
                    </div>
                  )}
                  {attemptResp.outcome === "POLICY_DELTA_REQUIRED" && (
                    <div className="p-4 rounded-xl bg-warning/[0.06] border border-warning/30 text-text space-y-2">
                      <div className="font-bold text-sm text-warning flex items-center gap-1.5">Customer Approval Needed (Policy Delta)</div>
                      <p className="text-xs text-muted leading-relaxed">{attemptResp.human_message || "Item or merchant changed outside envelope bounds."}</p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-muted mt-1">Single-owner compare-and-set dispatch. Issues payment link after headroom check.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================= */}
      {/* MODE 3: REFUND & SLIPPAGE SIMULATOR                      */}
      {/* ========================================================= */}
      {workbenchMode === "refund" && (
        <div className="space-y-6">
          {/* Notification banner */}
          {refundNotice && (
            <div className="p-3.5 rounded-xl bg-primary/[0.06] border border-primary/20 text-xs text-primary flex items-center justify-between">
              <span>{refundNotice}</span>
              <button onClick={() => setRefundNotice(null)} className="text-xs font-bold hover:underline">Dismiss</button>
            </div>
          )}

          {/* Section 1: Live Stock Slippage Controls */}
          <Card
            title="Catalog Stock & Mid-Demo Slippage Controls"
            subtitle="Simulate live stock movements to test how Action Firewall transparently triggers in-envelope repairs instead of crashing"
            action={
              <button
                onClick={handleResetStock}
                disabled={slippageBusy}
                className="rounded-xl border border-border bg-surface px-4 py-2 text-xs font-semibold text-text hover:bg-canvas disabled:opacity-50 transition"
              >
                Reset All Inventory
              </button>
            }
          >
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {(slippageItems.length > 0 ? slippageItems : [
                { sku: "SKU-DAI-001", name: "Oat Milk 1L", committed_stock: 12, live_stock: 12 },
                { sku: "SKU-PAS-001", name: "Durum Wheat Penne 500g", committed_stock: 24, live_stock: 24 },
                { sku: "SKU-SAU-001", name: "Tomato Passata 700g", committed_stock: 18, live_stock: 18 },
                { sku: "SKU-DAI-002", name: "Soy Milk 1L (Substitute)", committed_stock: 30, live_stock: 30 },
              ]).map((item) => (
                <div key={item.sku} className="rounded-xl border border-border bg-surface p-3.5 space-y-2">
                  <div className="flex items-start justify-between gap-1">
                    <div>
                      <div className="font-semibold text-xs text-text truncate max-w-[140px]">{item.name}</div>
                      <div className="font-mono text-[10px] text-muted">{item.sku}</div>
                    </div>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      item.live_stock > 0 ? "bg-success/10 text-success" : "bg-danger/10 text-danger"
                    }`}>
                      {item.live_stock > 0 ? `${item.live_stock} in stock` : "Out of stock"}
                    </span>
                  </div>
                  <div className="pt-1">
                    <button
                      onClick={() => handleDepleteStock(item.sku)}
                      disabled={slippageBusy || item.live_stock === 0}
                      className="w-full py-1.5 px-2 rounded-lg bg-canvas hover:bg-border/60 text-text text-[11px] font-semibold border border-border disabled:opacity-40 transition"
                    >
                      {item.live_stock === 0 ? "Exhausted" : "Deplete Stock"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] text-muted italic">
              *Depleting Oat Milk or Penne triggers deterministic in-envelope substitution during agent checkout.
            </p>
          </Card>

          {/* Section 2: Outbound Refund Evaluator & Repair Ladder */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Refund Inputs */}
            <div className="lg:col-span-6 rounded-2xl border border-border bg-surface p-6 shadow-sm space-y-4">
              <div>
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-text uppercase tracking-wider">
                    Outbound Refund Authorization
                  </h3>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-primary/10 text-primary font-bold">
                    4-Way Repair Ladder
                  </span>
                </div>
                <p className="text-xs text-muted mt-1">
                  Enforces merchant outbound limits: caps, 30-day window, ratio limits, and automatic step-down repair.
                </p>
              </div>

              {/* Policy Header */}
              <div className="rounded-xl border border-border bg-canvas/40 p-3 text-xs space-y-1 font-mono">
                <div className="flex justify-between">
                  <span className="text-muted">Per-Refund Max Cap:</span>
                  <span className="text-text font-bold">{refundPolicy ? inr(refundPolicy.max_refund_paise) : "₹500.00"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Max Refund Ratio:</span>
                  <span className="text-text font-bold">{refundPolicy ? `${(refundPolicy.max_refund_ratio * 100).toFixed(0)}%` : "50%"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Eligible Window:</span>
                  <span className="text-text font-bold">{refundPolicy?.window_days ?? 30} days</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Escalation Reasons:</span>
                  <span className="text-warning font-bold">fraud, chargebacks</span>
                </div>
              </div>

              {/* Presets */}
              <div>
                <label className="text-[11px] font-bold text-muted uppercase tracking-wider block mb-1.5">
                  Quick Presets
                </label>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <button
                    type="button"
                    onClick={() => {
                      setRefundAmountRupees("300");
                      setRefundOriginalAmountRupees("2000");
                      setRefundOrderAgeDays(5);
                      setRefundReason("Damaged item during delivery");
                      setRefundAlreadyRefundedRupees("0");
                    }}
                    className="p-2 rounded-lg bg-canvas border border-border text-left hover:bg-border/40 transition"
                  >
                    <div className="font-semibold text-text">1. Compliant (₹300)</div>
                    <div className="text-[10px] text-success">ALLOW_REFUND</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setRefundAmountRupees("1500");
                      setRefundOriginalAmountRupees("2000");
                      setRefundOrderAgeDays(5);
                      setRefundReason("Customer requested return");
                      setRefundAlreadyRefundedRupees("0");
                    }}
                    className="p-2 rounded-lg bg-canvas border border-border text-left hover:bg-border/40 transition"
                  >
                    <div className="font-semibold text-text">2. Over-Limit (₹1,500)</div>
                    <div className="text-[10px] text-warning">REPAIR_REFUND (Auto-cap)</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setRefundAmountRupees("400");
                      setRefundOriginalAmountRupees("2000");
                      setRefundOrderAgeDays(5);
                      setRefundReason("Suspected fraud / unauthorized use");
                      setRefundAlreadyRefundedRupees("0");
                    }}
                    className="p-2 rounded-lg bg-canvas border border-border text-left hover:bg-border/40 transition"
                  >
                    <div className="font-semibold text-text">3. Fraud Reason</div>
                    <div className="text-[10px] text-warning">ESCALATE_REFUND</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setRefundAmountRupees("300");
                      setRefundOriginalAmountRupees("2000");
                      setRefundOrderAgeDays(45);
                      setRefundReason("Customer return");
                      setRefundAlreadyRefundedRupees("0");
                    }}
                    className="p-2 rounded-lg bg-canvas border border-border text-left hover:bg-border/40 transition"
                  >
                    <div className="font-semibold text-text">4. Expired (45 Days)</div>
                    <div className="text-[10px] text-danger">BLOCK_REFUND</div>
                  </button>
                </div>
              </div>

              {/* Form Fields */}
              <div className="space-y-3 pt-1">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] font-bold text-muted uppercase block">Refund Amount (₹)</label>
                    <input
                      type="number"
                      value={refundAmountRupees}
                      onChange={(e) => setRefundAmountRupees(e.target.value)}
                      className="mt-1 w-full text-xs p-2.5 bg-canvas border border-border rounded-lg font-mono text-text outline-none focus:border-primary"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-bold text-muted uppercase block">Original Order (₹)</label>
                    <input
                      type="number"
                      value={refundOriginalAmountRupees}
                      onChange={(e) => setRefundOriginalAmountRupees(e.target.value)}
                      className="mt-1 w-full text-xs p-2.5 bg-canvas border border-border rounded-lg font-mono text-text outline-none focus:border-primary"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] font-bold text-muted uppercase block">Order Age (Days)</label>
                    <input
                      type="number"
                      value={refundOrderAgeDays}
                      onChange={(e) => setRefundOrderAgeDays(Number.parseInt(e.target.value, 10) || 0)}
                      className="mt-1 w-full text-xs p-2.5 bg-canvas border border-border rounded-lg font-mono text-text outline-none focus:border-primary"
                    />
                  </div>
                  <div>
                    <label className="text-[11px] font-bold text-muted uppercase block">Already Refunded (₹)</label>
                    <input
                      type="number"
                      value={refundAlreadyRefundedRupees}
                      onChange={(e) => setRefundAlreadyRefundedRupees(e.target.value)}
                      className="mt-1 w-full text-xs p-2.5 bg-canvas border border-border rounded-lg font-mono text-text outline-none focus:border-primary"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-[11px] font-bold text-muted uppercase block">Reason</label>
                  <input
                    type="text"
                    value={refundReason}
                    onChange={(e) => setRefundReason(e.target.value)}
                    className="mt-1 w-full text-xs p-2.5 bg-canvas border border-border rounded-lg text-text outline-none focus:border-primary"
                  />
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="autoRepairToggle"
                    checked={refundAutoRepair}
                    onChange={(e) => setRefundAutoRepair(e.target.checked)}
                    className="rounded text-primary focus:ring-0"
                  />
                  <label htmlFor="autoRepairToggle" className="text-xs text-text cursor-pointer select-none">
                    Auto-repair down to max allowable policy cap if proposal exceeds limits
                  </label>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="grid grid-cols-2 gap-3 pt-2">
                <button
                  onClick={handleEvaluateRefund}
                  disabled={refundBusy}
                  className="py-2.5 px-4 rounded-xl border border-primary bg-primary/10 hover:bg-primary/20 text-primary text-xs font-bold transition disabled:opacity-50"
                >
                  {refundBusy ? "Evaluating..." : "Evaluate Policy"}
                </button>
                <button
                  onClick={handleExecuteRefund}
                  disabled={refundBusy}
                  className="py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-white text-xs font-bold transition shadow-sm disabled:opacity-50"
                >
                  {refundBusy ? "Executing..." : "Execute Refund"}
                </button>
              </div>
            </div>

            {/* Refund Results Column */}
            <div className="lg:col-span-6 space-y-4">
              <div className="rounded-2xl border border-border bg-surface p-6 shadow-sm space-y-4">
                <h3 className="text-xs font-bold text-text uppercase tracking-wider">
                  Firewall Evaluation Decision
                </h3>

                {refundEvalResult ? (
                  <div className="space-y-4 text-xs">
                    <div className={`p-4 rounded-xl border ${
                      refundEvalResult.decision?.decision === "ALLOW_REFUND"
                        ? "bg-success/10 border-success/30 text-success"
                        : refundEvalResult.decision?.decision === "REPAIR_REFUND"
                        ? "bg-warning/10 border-warning/30 text-warning"
                        : refundEvalResult.decision?.decision === "ESCALATE_REFUND"
                        ? "bg-warning/10 border-warning/30 text-warning"
                        : "bg-danger/10 border-danger/30 text-danger"
                    }`}>
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-sm uppercase">
                          {refundEvalResult.decision?.decision || "ALLOW_REFUND"}
                        </span>
                        <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-surface/80 border border-current font-bold">
                          {refundEvalResult.code}
                        </span>
                      </div>
                      <p className="mt-2 text-xs leading-relaxed">
                        {refundEvalResult.human_message}
                      </p>
                    </div>

                    {/* Repaired proposal details if present */}
                    {refundEvalResult.repaired_proposal && (
                      <div className="p-3.5 rounded-xl border border-border bg-canvas/40 space-y-2">
                        <div className="font-semibold text-text text-[11px] uppercase tracking-wide">
                          Repaired Proposal Step-Down
                        </div>
                        <div className="grid grid-cols-2 gap-2 font-mono text-xs">
                          <div>
                            <span className="text-muted block text-[10px]">Requested:</span>
                            <span className="text-danger line-through font-bold">
                              {inr(refundEvalResult.proposal.amount_paise)}
                            </span>
                          </div>
                          <div>
                            <span className="text-muted block text-[10px]">Repaired Cap:</span>
                            <span className="text-success font-bold">
                              {inr(refundEvalResult.repaired_proposal.amount_paise)}
                            </span>
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="space-y-2 font-mono text-[11px] bg-canvas p-3 rounded-xl border border-border">
                      <div className="flex justify-between">
                        <span className="text-muted">Target Payment:</span>
                        <span className="text-text">{refundEvalResult.proposal.payment_id}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted">Policy Hash:</span>
                        <span className="text-text truncate max-w-[180px]">{refundEvalResult.policy_hash}</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <EmptyState
                    title="No refund evaluated yet"
                    description="Select a preset or enter values on the left and click 'Evaluate Policy'."
                  />
                )}

                {/* Execution Result */}
                {refundExecResult && (
                  <div className="mt-4 pt-4 border-t border-border space-y-3">
                    <h4 className="text-xs font-bold text-text uppercase tracking-wider">
                      Provider Actuator Result
                    </h4>
                    <div className={`p-4 rounded-xl border ${
                      refundExecResult.allowed ? "bg-success/10 border-success/30" : "bg-danger/10 border-danger/30"
                    }`}>
                      <div className="flex items-center justify-between">
                        <span className={`font-bold text-xs uppercase ${refundExecResult.allowed ? "text-success" : "text-danger"}`}>
                          {refundExecResult.outcome}
                        </span>
                        <span className="font-mono text-xs font-bold text-text">
                          {inr(refundExecResult.amount_paise)}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-text">{refundExecResult.human_message}</p>
                      {refundExecResult.refund_id && (
                        <div className="mt-2 text-[11px] font-mono text-muted">
                          Refund ID: <span className="text-primary font-semibold">{refundExecResult.refund_id}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
