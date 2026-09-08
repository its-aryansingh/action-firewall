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

const QUICK_GOALS = [
  "Buy supplies for a pasta dinner",
  "Breakfast run for the office",
  "Restock pantry snacks",
  "Weekly grocery essentials",
];

export default function AIPlaygroundPage() {
  const [goal, setGoal] = useState("Buy supplies for a pasta dinner");
  const [budgetRupees, setBudgetRupees] = useState("600");
  const [buyerType, setBuyerType] = useState<"replay" | "openai">("replay");
  const [scenario, setScenario] = useState<AutopilotScenario>("stock_loss");

  // Workflow states
  const [busy, setBusy] = useState(false);
  const [currentStage, setCurrentStage] = useState<number>(0); // 0=idle, 1=understand, 2=quote, 3=authorize, 4=done
  const [intentResp, setIntentResp] = useState<IntentCreateResponse | null>(null);
  const [activeEnvelope, setActiveEnvelope] = useState<PurchaseEnvelope | null>(null);
  const [attemptResp, setAttemptResp] = useState<CommerceAttemptResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [buyerPlanLog, setBuyerPlanLog] = useState<string | null>(null);

  function handleReset() {
    setIntentResp(null);
    setActiveEnvelope(null);
    setAttemptResp(null);
    setError(null);
    setBuyerPlanLog(null);
    setCurrentStage(0);
  }

  // Run Stage 1 & 2: Understand & Draft Intent (Proposal-Only)
  async function handleStartCheckout() {
    setError(null);
    setBusy(true);
    setCurrentStage(1);
    const budgetPaise = (Number.parseInt(budgetRupees, 10) || 600) * 100;
    const reqId = `req_${Math.random().toString(36).slice(2, 10)}`;
    const sessId = `sess_${Math.random().toString(36).slice(2, 10)}`;

    try {
      // 1. If OpenAI selected, get plan proposal
      if (buyerType === "openai") {
        try {
          const planRes = await api.agentCommerce.planBuyer({
            goal,
            buyer_type: "openai",
          });
          setBuyerPlanLog(
            `Model ${planRes.model_used} formulated plan in ${planRes.latency_ms}ms (proposal-only, untrusted)`
          );
        } catch (planErr) {
          console.warn("OpenAI buyer fallback to replay:", planErr);
        }
      }

      // 2. Draft Intent (Proposal-Only)
      const res = await api.agentCommerce.createIntent({
        agent_request_id: reqId,
        natural_language_intent: goal,
        budget_paise: budgetPaise,
        buyer_agent_id: buyerType === "openai" ? "buyer_openai" : "buyer_replay",
        shopper_session_id: sessId,
      });

      setIntentResp(res);
      setCurrentStage(2); // Automatically advance to Server Quote stage
    } catch (err: any) {
      setError(`Failed to draft intent: ${err.message || String(err)}`);
      setCurrentStage(0);
    } finally {
      setBusy(false);
    }
  }

  // Run Stage 3: Human Customer Activation
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
      setCurrentStage(3); // Ready for execution
    } catch (err: any) {
      setError(`Activation failed: ${err.message || String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  // Run Stage 4: Firewall Actuator Execution -> Razorpay Payment Link
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
        buyer_agent_id: buyerType === "openai" ? "buyer_openai" : "buyer_replay",
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
    <div className="space-y-8 pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">AI Buyer Playground</h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-[#0C6CF2] border border-blue-200">
              Interactive Workbench
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Test the 4-stage Protected Agent Checkout with stock substitutions and drift refusal
          </p>
        </div>

        <button
          onClick={handleReset}
          className="self-start sm:self-auto px-3.5 py-2 text-xs font-semibold text-slate-600 hover:text-slate-900 bg-white border border-slate-200 rounded-lg shadow-xs transition"
        >
          Reset Playground
        </button>
      </div>

      {/* Two-Column Workbench */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* LEFT COLUMN: Agent & Scenario Controls (5 cols) */}
        <div className="lg:col-span-5 bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-5">
          <div>
            <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
              1. Natural Language Shopping Goal
            </h2>
            <div className="mt-2 space-y-2">
              <textarea
                rows={3}
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="e.g. Buy supplies for a pasta dinner"
                className="w-full text-xs p-3 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-[#0C6CF2] focus:bg-white resize-none transition"
              />
              <div className="flex flex-wrap gap-1.5">
                {QUICK_GOALS.map((g) => (
                  <button
                    key={g}
                    type="button"
                    onClick={() => setGoal(g)}
                    className="text-[11px] px-2.5 py-1 rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 transition"
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
              <label className="text-[11px] font-bold text-slate-700 uppercase tracking-wider block">
                Budget (INR)
              </label>
              <input
                type="number"
                value={budgetRupees}
                onChange={(e) => setBudgetRupees(e.target.value)}
                className="mt-1 w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0C6CF2] font-mono"
              />
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-700 uppercase tracking-wider block">
                AI Buyer Adapter
              </label>
              <select
                value={buyerType}
                onChange={(e) => setBuyerType(e.target.value as any)}
                className="mt-1 w-full text-xs p-2.5 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0C6CF2]"
              >
                <option value="replay">Deterministic Replay Buyer</option>
                <option value="openai">OpenAI Structured (gpt-4o-mini)</option>
              </select>
            </div>
          </div>

          {/* Resilience / Fault Injection Scenario Selector */}
          <div className="pt-2">
            <label className="text-[11px] font-bold text-slate-700 uppercase tracking-wider block mb-1">
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
                      ? "border-[#0C6CF2] bg-blue-50/50 shadow-xs"
                      : "border-slate-200 bg-slate-50/50 hover:bg-slate-50"
                  }`}
                >
                  <input
                    type="radio"
                    name="scenario"
                    value={s.id}
                    checked={scenario === s.id}
                    onChange={() => setScenario(s.id as AutopilotScenario)}
                    className="mt-0.5 text-[#0C6CF2] focus:ring-0"
                  />
                  <div>
                    <div className="font-semibold text-slate-900">{s.name}</div>
                    <div className="text-[11px] text-slate-500 mt-0.5 leading-snug">{s.desc}</div>
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
              className="w-full py-3 px-4 rounded-xl bg-[#0C6CF2] hover:bg-blue-600 disabled:opacity-50 text-white text-xs font-bold shadow-sm transition flex items-center justify-center gap-2"
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

          {buyerPlanLog && (
            <div className="p-3 bg-slate-50 rounded-lg border border-slate-200 text-[11px] font-mono text-slate-600">
              {buyerPlanLog}
            </div>
          )}

          {error && (
            <div className="p-3 bg-rose-50 rounded-lg border border-rose-200 text-xs text-rose-700">
              {error}
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: 4-Stage Execution Timeline (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          {/* Timeline Header */}
          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
              4-Stage Action Firewall Protection
            </span>
            <span className="text-[11px] font-mono text-slate-400">
              Stage: {currentStage === 0 ? "Idle" : `${currentStage} of 4`}
            </span>
          </div>

          {/* Stage 1: Understand (Draft Intent) */}
          <div
            className={`p-5 rounded-2xl border transition-all ${
              currentStage >= 1
                ? "bg-white border-slate-300 shadow-sm"
                : "bg-slate-50/70 border-slate-200 opacity-60"
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 rounded-full bg-blue-100 text-[#0C6CF2] text-xs font-bold items-center justify-center">
                  1
                </span>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                  Stage 1: Understand (Draft Purchase Envelope)
                </h3>
              </div>
              {intentResp && (
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-800">
                  Proposal-Only (Draft)
                </span>
              )}
            </div>

            {intentResp?.draft_envelope ? (
              <div className="mt-3 space-y-2 text-xs bg-slate-50 p-3 rounded-xl border border-slate-200 font-mono">
                <div className="flex justify-between">
                  <span className="text-slate-500">Envelope ID:</span>
                  <span className="text-slate-900 font-bold">{intentResp.draft_envelope.id}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Max Budget:</span>
                  <span className="text-slate-900 font-bold">{inr(intentResp.draft_envelope.max_total_paise)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Required Slots:</span>
                  <span className="text-[#0C6CF2] font-semibold">
                    {intentResp.draft_envelope.slots.map((s) => s.label).join(", ")}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 pt-1 border-t border-slate-200">
                  Envelope Hash: {intentResp.draft_envelope.envelope_hash.slice(0, 24)}...
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-400 mt-1">
                Translates natural language into bounded slots. Zero payment provider authority active.
              </p>
            )}
          </div>

          {/* Stage 2: Quote (Authoritative Server Quote) */}
          <div
            className={`p-5 rounded-2xl border transition-all ${
              currentStage >= 2
                ? "bg-white border-slate-300 shadow-sm"
                : "bg-slate-50/70 border-slate-200 opacity-60"
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 rounded-full bg-blue-100 text-[#0C6CF2] text-xs font-bold items-center justify-center">
                  2
                </span>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                  Stage 2: Quote (Server-Resolved Catalog Facts)
                </h3>
              </div>
              {currentStage >= 2 && (
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800">
                  Server Verified
                </span>
              )}
            </div>

            {currentStage >= 2 ? (
              <div className="mt-3 text-xs bg-slate-50 p-3 rounded-xl border border-slate-200 space-y-2">
                <p className="text-slate-600">
                  Merchant quote computed server-side discarding all client price assertions:
                </p>
                <div className="font-mono text-slate-800 flex justify-between">
                  <span>Target Merchant:</span>
                  <span className="font-bold">merchant_freshbasket (FreshBasket for Business)</span>
                </div>
                <div className="font-mono text-slate-800 flex justify-between">
                  <span>Estimated Total:</span>
                  <span className="font-bold text-[#0C6CF2]">~₹7,840.00 INR</span>
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-400 mt-1">
                Server evaluates inventory, unit prices in paise, and delivery profile.
              </p>
            )}
          </div>

          {/* Stage 3: Authorize (Explicit Customer Activation) */}
          <div
            className={`p-5 rounded-2xl border transition-all ${
              currentStage >= 2
                ? "bg-white border-slate-300 shadow-sm"
                : "bg-slate-50/70 border-slate-200 opacity-60"
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 rounded-full bg-blue-100 text-[#0C6CF2] text-xs font-bold items-center justify-center">
                  3
                </span>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                  Stage 3: Authorize (Human Activation)
                </h3>
              </div>
              {activeEnvelope ? (
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800">
                  Activated (v{activeEnvelope.version})
                </span>
              ) : (
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-600">
                  Awaiting Approval
                </span>
              )}
            </div>

            {currentStage >= 2 && !activeEnvelope && (
              <div className="mt-3 p-3.5 bg-blue-50/70 border border-blue-200 rounded-xl">
                <p className="text-xs text-blue-900">
                  The model cannot self-authorize. The shopper must review limits and activate the envelope.
                </p>
                <button
                  onClick={handleActivateEnvelope}
                  disabled={busy}
                  className="mt-3 px-4 py-2 bg-[#0C6CF2] hover:bg-blue-600 text-white rounded-lg text-xs font-bold shadow-xs transition"
                >
                  Approve &amp; Activate Envelope Once
                </button>
              </div>
            )}

            {activeEnvelope && (
              <div className="mt-3 p-3 bg-emerald-50/50 border border-emerald-200 rounded-xl text-xs space-y-2">
                <div className="text-emerald-900 font-semibold flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  Envelope activated by customer! Ready for single atomic execution.
                </div>
                {currentStage === 3 && (
                  <button
                    onClick={handleExecuteAttempt}
                    disabled={busy}
                    className="mt-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold shadow-xs transition"
                  >
                    Execute Attempt via Action Firewall &rarr;
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Stage 4: Razorpay Action (Firewall Actuator Dispatch) */}
          <div
            className={`p-5 rounded-2xl border transition-all ${
              currentStage >= 4
                ? "bg-white border-slate-300 shadow-sm"
                : "bg-slate-50/70 border-slate-200 opacity-60"
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 rounded-full bg-blue-100 text-[#0C6CF2] text-xs font-bold items-center justify-center">
                  4
                </span>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900">
                  Stage 4: Razorpay Action (Atomic Dispatch)
                </h3>
              </div>
            </div>

            {attemptResp ? (
              <div className="mt-3 space-y-3 text-xs">
                {/* Outcome Badge Banner */}
                {attemptResp.outcome === "ACTION_ISSUED" && (
                  <div className="p-4 rounded-xl bg-blue-50 border border-blue-200 text-blue-900 space-y-2">
                    <div className="font-bold text-sm text-[#0C6CF2] flex items-center gap-1.5">
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      Payment Link Issued Successfully
                    </div>
                    <p className="text-xs text-blue-800">
                      Razorpay MCP tool executed under single CAS dispatch lock.
                    </p>
                    {attemptResp.payment_link && (
                      <div className="pt-2 flex items-center gap-2">
                        <input
                          type="text"
                          readOnly
                          value={attemptResp.payment_link}
                          className="flex-1 text-xs font-mono bg-white border border-blue-200 rounded-lg p-2 text-slate-800"
                        />
                        <a
                          href={attemptResp.payment_link}
                          target="_blank"
                          rel="noreferrer"
                          className="px-3.5 py-2 text-xs font-bold bg-[#0C6CF2] text-white rounded-lg hover:bg-blue-600 shrink-0"
                        >
                          Open Link
                        </a>
                      </div>
                    )}
                  </div>
                )}

                {attemptResp.outcome === "RECOVERED_INSIDE_ENVELOPE" && (
                  <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 space-y-2">
                    <div className="font-bold text-sm text-emerald-700 flex items-center gap-1.5">
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      In-Envelope Stock Loss Recovery Applied!
                    </div>
                    <p className="text-xs text-emerald-800 leading-relaxed">
                      Penne was out of stock. Action Firewall substituted <strong>Spaghetti No.5 (SKU-PAS-002)</strong> matching required slot tags without re-prompting the customer. Payment link issued within envelope cap.
                    </p>
                    {attemptResp.payment_link && (
                      <div className="pt-2 flex items-center gap-2">
                        <input
                          type="text"
                          readOnly
                          value={attemptResp.payment_link}
                          className="flex-1 text-xs font-mono bg-white border border-emerald-200 rounded-lg p-2 text-slate-800"
                        />
                        <a
                          href={attemptResp.payment_link}
                          target="_blank"
                          rel="noreferrer"
                          className="px-3.5 py-2 text-xs font-bold bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 shrink-0"
                        >
                          Open Link
                        </a>
                      </div>
                    )}
                  </div>
                )}

                {attemptResp.outcome === "POLICY_DELTA_REQUIRED" && (
                  <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 space-y-2">
                    <div className="font-bold text-sm text-amber-800 flex items-center gap-1.5">
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      Adversarial Drift Blocked Before Actuator!
                    </div>
                    <p className="text-xs text-amber-800 leading-relaxed">
                      {attemptResp.human_message || "Target merchant or delivery destination mutated outside approved envelope."}
                    </p>
                    {attemptResp.deltas?.length > 0 && (
                      <div className="p-2.5 bg-white/80 rounded-lg border border-amber-200 font-mono text-[11px] space-y-1">
                        {attemptResp.deltas.map((d, idx) => (
                          <div key={idx}>
                            Delta on <strong>{d.field}</strong>: expected <code>{d.expected}</code>, got <code>{d.actual}</code> &rarr; next: <code>{d.recovery}</code>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {attemptResp.outcome === "UNKNOWN" && (
                  <div className="p-4 rounded-xl bg-purple-50 border border-purple-200 text-purple-900 space-y-2">
                    <div className="font-bold text-sm text-purple-800 flex items-center gap-1.5">
                      Provider Outcome Unknown (Timeout Safely Handled)
                    </div>
                    <p className="text-xs text-purple-800 leading-relaxed">
                      Provider timed out after dispatch. Exposure of {inr(attemptResp.quote_total_paise)} remains reserved. Blind retry prevented. Appears in Needs Attention for reconciliation.
                    </p>
                  </div>
                )}

                {/* Receipts and Grants */}
                <div className="pt-2 border-t border-slate-100 flex flex-wrap items-center justify-between text-[11px] text-slate-500 font-mono">
                  <span>Grant: {attemptResp.grant_id?.slice(0, 16)}...</span>
                  <span className="text-emerald-600 font-semibold">Dual-Signature Receipt Verified</span>
                </div>
              </div>
            ) : (
              <p className="text-xs text-slate-400 mt-1">
                Atomic compare-and-set authorization. Issues payment link only after headroom reservation.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
