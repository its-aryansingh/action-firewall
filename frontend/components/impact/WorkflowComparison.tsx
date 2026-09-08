"use client";

import React, { useEffect, useState } from "react";
import { fetchWorkflowBenchmark, type WorkflowBenchmarkReport, VERIFIED_BENCHMARK } from "@/lib/benchmark";

export const WorkflowComparison: React.FC = () => {
  const [data, setData] = useState<WorkflowBenchmarkReport>(VERIFIED_BENCHMARK);

  useEffect(() => {
    fetchWorkflowBenchmark().then(setData);
  }, []);

  const { exact_cart_approval, purchase_envelope } = data.results;

  return (
    <div className="space-y-6">
      <div className="grid gap-5 md:grid-cols-2">
        {/* Exact-Cart Approval Card */}
        <div className="rounded-2xl border border-edge/80 bg-panel/60 p-6 space-y-5">
          <div className="flex items-center justify-between border-b border-edge/60 pb-3">
            <span className="label">Legacy Industry Pattern</span>
            <span className="font-mono text-xs text-muted">Exact-Cart Approval</span>
          </div>

          <div className="space-y-4">
            <div>
              <p className="text-3xl font-bold font-mono text-slate-300">
                {exact_cart_approval.completed_without_action_time_intervention} / 100
              </p>
              <p className="text-xs text-muted mt-1">
                modeled checkouts continue without later intervention
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2 border-t border-edge/40 text-xs">
              <div>
                <p className="text-muted">Stock Losses Recovered</p>
                <p className="text-base font-bold font-mono text-rose-400 mt-0.5">
                  {exact_cart_approval.eligible_stock_loss_recovered_without_reapproval} / 50
                </p>
                <p className="text-[10px] text-muted">Forces re-approval</p>
              </div>

              <div>
                <p className="text-muted">Approval Prompts</p>
                <p className="text-base font-bold font-mono text-slate-300 mt-0.5">
                  {exact_cart_approval.approval_prompts_per_legitimate_completion.toFixed(1)} / job
                </p>
                <p className="text-[10px] text-muted">+50% extra prompts</p>
              </div>
            </div>

            <div className="pt-2 border-t border-edge/40 flex items-center justify-between text-xs">
              <span className="text-muted">Unsafe Automatic Actions:</span>
              <span className="font-mono font-bold text-allow">0 (Fails closed)</span>
            </div>
          </div>
        </div>

        {/* Safe Autopilot Card */}
        <div className="rounded-2xl border border-brand/40 bg-brand/[0.04] p-6 space-y-5 shadow-[0_0_40px_rgba(51,149,255,0.08)] relative overflow-hidden">
          <div className="absolute top-0 right-0 w-32 h-32 bg-brand/10 rounded-full blur-2xl pointer-events-none" />

          <div className="flex items-center justify-between border-b border-brand/20 pb-3">
            <span className="label text-brand font-semibold">Safe Autopilot</span>
            <span className="rounded-full border border-brand/30 bg-brand/10 px-2.5 py-0.5 font-mono text-[10px] font-bold text-brand uppercase">
              2× Continuity
            </span>
          </div>

          <div className="space-y-4">
            <div>
              <p className="text-3xl font-bold font-mono text-white">
                {purchase_envelope.completed_without_action_time_intervention} / 100
              </p>
              <p className="text-xs text-brand/80 font-medium mt-1">
                modeled checkouts continue without later intervention
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2 border-t border-brand/20 text-xs">
              <div>
                <p className="text-muted">Stock Losses Recovered</p>
                <p className="text-base font-bold font-mono text-allow mt-0.5">
                  {purchase_envelope.eligible_stock_loss_recovered_without_reapproval} / 50
                </p>
                <p className="text-[10px] text-allow">100% recovered inside limits</p>
              </div>

              <div>
                <p className="text-muted">Approval Prompts</p>
                <p className="text-base font-bold font-mono text-white mt-0.5">
                  {purchase_envelope.approval_prompts_per_legitimate_completion.toFixed(1)} / job
                </p>
                <p className="text-[10px] text-muted">Exactly one approval</p>
              </div>
            </div>

            <div className="pt-2 border-t border-brand/20 flex items-center justify-between text-xs">
              <span className="text-muted">Unsafe Automatic Actions:</span>
              <span className="font-mono font-bold text-allow">0 / 150 blocked</span>
            </div>
          </div>
        </div>
      </div>

      {/* Mandatory Scope Limitation Callout */}
      <div className="rounded-xl border border-border bg-canvas p-4 text-xs text-muted leading-relaxed">
        <p className="font-semibold text-text mb-1">Methodology & Empirical Verification Scope</p>
        <p>
          Synthetic catalog workflow benchmark over {data.corpus.legitimate_jobs} legitimate jobs ({data.corpus.eligible_stock_loss_jobs} eligible stock-loss cases) and {data.corpus.unsafe_drift_attempts} adversarial drift attempts across 10 goal families.
          This measures modeled workflow continuity and authorization correctness, <strong>not production conversion, GMV, payment success, or revenue uplift</strong>.
        </p>
      </div>
    </div>
  );
};
