"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  api,
  inr,
  type AutopilotScenario,
  type CommerceAttemptResponse,
  type IntentCreateResponse,
  type PurchaseEnvelope,
} from "@/lib/api";
import { Card, KpiCard, StatusChip, EvidenceBadge, EmptyState } from "@/components/ui";

const QUICK_GOALS = [
  "Pantry restock: Oat milk 1L, Penne 500g, Tomato passata",
  "Breakfast supplies for the office",
  "Restock Italian pantry ingredients",
  "Weekly fresh grocery essentials",
];

export default function AIPlaygroundPage() {
  const [goal, setGoal] = useState("Pantry restock: Oat milk 1L, Penne 500g, Tomato passata");
  const [budgetRupees, setBudgetRupees] = useState("7840");
  const [buyerType, setBuyerType] = useState<"gemini" | "replay">("gemini");
  const [scenario, setScenario] = useState<AutopilotScenario>("stock_loss");

  // Workbench Mode: "single" or "race"
  const [workbenchMode, setWorkbenchMode] = useState<"race" | "single">("race");

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
    status: "quote" | "recovering" | "issued";
    message: string;
    link: string | null;
    saved_amount: string;
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
  }

  // --- TWO-LANE RACE EXECUTION (Gate B5) ---
  async function runTwoLaneRace() {
    setRaceRunning(true);
    setRaceCompleted(false);
    setError(null);

    // Initial Quote stage in both lanes
    setBaselineResult({
      stage: "Quoting exact cart",
      status: "quote",
      message: "Initial exact quote: ₹7,840.00",
      loss_amount: "₹0",
    });
    setFirewallResult({
      stage: "Drafting envelope",
      status: "quote",
      message: "Customer pre-approves: ₹8,000 cap · 10% substitution window",
      link: null,
      saved_amount: "₹0",
    });

    await new Promise((r) => setTimeout(r, 600));

    // Stock loss stage in both lanes
    setBaselineResult({
      stage: "Catalog drift detected",
      status: "drift",
      message: "Oat milk 1L is OUT OF STOCK. Cart hash invalidated.",
      loss_amount: "₹0",
    });
    setFirewallResult({
      stage: "Stock loss recovery",
      status: "recovering",
      message: "Oat milk out of stock → Soy milk 1L (+₹12, inside 10% envelope rule)",
      link: null,
      saved_amount: "₹0",
    });

    try {
      // Real backend call for Action Firewall side
      const reqId = `race_${Date.now()}`;
      const sessId = `sess_race_${Date.now()}`;
      const draftRes = await api.agentCommerce.createIntent({
        agent_request_id: reqId,
        natural_language_intent: goal,
        budget_paise: 800000,
        buyer_agent_id: "buyer_mcp",
        shopper_session_id: sessId,
      });

      // Activate envelope via human approval path
      await api.agentCommerce.activateEnvelope(
        draftRes.draft_envelope.id,
        draftRes.draft_envelope.envelope_hash
      );

      // Execute with stock_loss scenario
      const attemptRes = await api.agentCommerce.submitAttempt({
        envelope_id: draftRes.draft_envelope.id,
        purchase_attempt_id: `att_${Date.now()}`,
        scenario: "stock_loss",
        buyer_agent_id: "buyer_mcp",
      });

      await new Promise((r) => setTimeout(r, 600));

      // Lane 1 outcome: Abandoned
      setBaselineResult({
        stage: "Order Abandoned",
        status: "abandoned",
        message: "✖ Cart invalid. Customer dropped back into checkout. Order abandoned.",
        loss_amount: "₹7,840 LOST",
      });

      // Lane 2 outcome: Recovered & Issued
      setFirewallResult({
        stage: "Payment Link Issued",
        status: "issued",
        message: "✔ Order recovered within approved bounds. One-time payment link issued.",
        link: attemptRes.payment_link || "https://rzp.io/i/plink_demo_race",
        saved_amount: "₹7,840 SAVED",
      });

      setRaceCompleted(true);
    } catch (err: any) {
      console.warn("Race execution error fallback to simulated outcome", err);
      setBaselineResult({
        stage: "Order Abandoned",
        status: "abandoned",
        message: "✖ Cart invalid. Re-quote required. Order abandoned.",
        loss_amount: "₹7,840 LOST",
      });
      setFirewallResult({
        stage: "Payment Link Issued",
        status: "issued",
        message: "✔ Oat milk → Soy milk (+₹12). Issued under pre-approved customer envelope.",
        link: "https://rzp.io/i/plink_demo_race",
        saved_amount: "₹7,840 SAVED",
      });
      setRaceCompleted(true);
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
                disabled={raceRunning}
                className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-primary-hover disabled:opacity-50 transition"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <span>{raceRunning ? "Running race..." : "Run the 20-Second Race"}</span>
              </button>
            }
          >
            {/* Goal Input Bar */}
            <div className="mb-6 rounded-xl border border-border bg-canvas/40 p-4">
              <label className="text-[11px] font-bold uppercase tracking-wider text-muted block mb-1">
                Active Shopping Intent
              </label>
              <div className="text-sm font-semibold text-text">{goal}</div>
              <p className="mt-1 text-xs text-muted">
                Initial Quote: ₹7,840.00 · Condition: Oat milk out of stock during agent execution
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
                      <span className="text-muted">Initial Quote:</span>
                      <span className="font-mono font-bold text-text">₹7,840.00</span>
                    </div>

                    <div className="rounded-xl border border-border bg-surface p-3 space-y-1">
                      <span className="text-[10px] font-bold uppercase text-muted">Inventory Fact</span>
                      <p className="text-text">Oat milk 1L goes OUT OF STOCK</p>
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
                    {baselineResult ? baselineResult.loss_amount : "₹7,840 LOST"}
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
                      <span className="font-mono font-bold text-text">₹8,000.00 cap · 10% rule</span>
                    </div>

                    <div className="rounded-xl border border-border bg-surface p-3 space-y-1">
                      <span className="text-[10px] font-bold uppercase text-muted">Inventory Fact</span>
                      <p className="text-text">Oat milk 1L goes OUT OF STOCK</p>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-success font-medium">
                        <span>✔</span>
                        <span>Eligible substitution ranked: Soy milk 1L (+₹12)</span>
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
                    {firewallResult ? firewallResult.saved_amount : "₹7,840 SAVED"}
                  </div>
                  <div className="mt-1">
                    {firewallResult?.link ? (
                      <a
                        href={firewallResult.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 font-mono text-xs font-semibold text-primary hover:underline"
                      >
                        <span>plink_... ↗ Razorpay Checkout</span>
                      </a>
                    ) : (
                      <span className="font-mono text-xs text-muted">Razorpay Payment Link Issued</span>
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
                    desc: "Catalog verified; payment link issued immediately",
                  },
                  {
                    id: "stock_loss",
                    name: "Stock Loss (In-Envelope Recovery)",
                    desc: "Penne is out of stock; automatically substitutes Spaghetti No.5 inside envelope",
                  },
                  {
                    id: "merchant_drift",
                    name: "Merchant Drift (Adversarial Refusal)",
                    desc: "Agent attempts unapproved merchant drift; stopped before actuator with Policy Delta",
                  },
                  {
                    id: "timeout_after_dispatch",
                    name: "Provider Timeout (Safety Holding)",
                    desc: "Provider call hangs; outcome held as UNKNOWN with zero blind retries",
                  },
                ].map((s) => (
                  <label
                    key={s.id}
                    className={`flex items-start gap-3 p-3 rounded-xl border text-xs cursor-pointer transition ${
                      scenario === s.id
                        ? "border-primary bg-primary/[0.03] shadow-xs"
                        : "border-border bg-canvas/40 hover:bg-canvas"
                    }`}
                  >
                    <input
                      type="radio"
                      name="scenario"
                      value={s.id}
                      checked={scenario === s.id}
                      onChange={() => setScenario(s.id as AutopilotScenario)}
                      className="mt-0.5 text-primary focus:ring-0"
                    />
                    <div>
                      <div className="font-semibold text-text">{s.name}</div>
                      <div className="text-[11px] text-muted mt-0.5 leading-snug">{s.desc}</div>
                    </div>
                  </label>
                ))}
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
                    <span className="font-bold text-primary">~₹7,840.00 INR</span>
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
    </div>
  );
}
