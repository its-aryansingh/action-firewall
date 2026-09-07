"use client";

import React from "react";
import type { CheckoutOutcomeView } from "@/lib/presentation";
import { TrustDetails } from "./TrustDetails";

interface CheckoutPausedProps {
  outcome: Extract<CheckoutOutcomeView, { kind: "paused" }>;
  onReviewNewApproval: () => void;
  onCancelOrder: () => void;
}

export const CheckoutPaused: React.FC<CheckoutPausedProps> = ({
  outcome,
  onReviewNewApproval,
  onCancelOrder,
}) => {
  return (
    <div className="card space-y-6 border-amber-500/30 bg-panel/90 p-6 sm:p-8 animate-fadeIn shadow-2xl">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-edge/80 pb-4">
        <div>
          <span className="label text-amber-400 font-semibold">Step 5 · Protected Checkout Boundary</span>
          <h2 className="mt-1 text-2xl font-bold tracking-tight text-white sm:text-3xl flex items-center gap-2.5">
            <span>I paused this order</span>
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/20 text-amber-400 text-sm">
              !
            </span>
          </h2>
        </div>

        <div className="text-right">
          <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 font-mono text-xs font-semibold text-amber-400">
            PROTECTED BY ACTION FIREWALL
          </span>
        </div>
      </div>

      {/* Clear Plain-Language Explanation */}
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.05] p-4 text-sm text-slate-200 leading-relaxed">
        {outcome.summary}
      </div>

      {/* Field Comparison Table */}
      <div className="rounded-2xl border border-edge/90 bg-ink/70 overflow-hidden divide-y divide-edge/60">
        <div className="flex items-center justify-between px-4 py-3 sm:px-6">
          <span className="text-xs text-muted">Field changed</span>
          <span className="font-mono text-xs font-semibold text-amber-300">
            {outcome.changedField}
          </span>
        </div>

        <div className="flex items-center justify-between px-4 py-3 sm:px-6">
          <span className="text-xs text-muted">Approved by you</span>
          <span className="text-xs font-semibold text-slate-200">
            {outcome.expectedValue}
          </span>
        </div>

        <div className="flex items-center justify-between px-4 py-3 sm:px-6">
          <span className="text-xs text-muted">Attempted by AI</span>
          <span className="text-xs font-semibold text-rose-400">
            {outcome.actualValue}
          </span>
        </div>

        <div className="flex items-center justify-between px-4 py-3 sm:px-6 bg-allow/[0.03]">
          <span className="text-xs text-muted">Razorpay contacted?</span>
          <span className="text-xs font-bold text-allow">
            No — zero money or actuator calls made
          </span>
        </div>
      </div>

      {/* Graceful Next Actions */}
      <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={onCancelOrder}
          className="btn btn-ghost text-xs"
        >
          Cancel order
        </button>

        <button
          type="button"
          onClick={onReviewNewApproval}
          className="btn btn-primary inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold"
        >
          <span>Review new approval</span>
          <span aria-hidden="true">&rarr;</span>
        </button>
      </div>

      {/* Progressive Technical Disclosure */}
      <TrustDetails
        title={`Technical reason: ${outcome.code}`}
        items={[
          { label: "Refusal Code", value: outcome.code, mono: true },
          { label: "Policy Delta Field", value: outcome.changedField, mono: true },
          { label: "Expected Value", value: outcome.expectedValue },
          { label: "Attempted Value", value: outcome.actualValue },
          { label: "Recovery Route", value: outcome.nextAction, mono: true },
          { label: "Actuator Invoked", value: "False (Denied pre-flight)" },
          { label: "Engine Message", value: outcome.humanMessage },
        ]}
        badges={[
          { label: "Pre-Actuator Denial", tone: "risk" },
          { label: "Zero Authority Leakage", tone: "allow" },
        ]}
      />
    </div>
  );
};
