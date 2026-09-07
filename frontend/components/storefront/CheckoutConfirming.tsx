"use client";

import React, { useState } from "react";
import type { CheckoutOutcomeView } from "@/lib/presentation";
import { TrustDetails } from "./TrustDetails";

interface CheckoutConfirmingProps {
  outcome: Extract<CheckoutOutcomeView, { kind: "confirming" }>;
  onCheckStatus?: () => void;
  onStartNewOrder: () => void;
}

export const CheckoutConfirming: React.FC<CheckoutConfirmingProps> = ({
  outcome,
  onCheckStatus,
  onStartNewOrder,
}) => {
  const [checking, setChecking] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const handleCheck = async () => {
    setChecking(true);
    setStatusMessage(null);
    if (onCheckStatus) {
      await onCheckStatus();
    } else {
      await new Promise((r) => setTimeout(r, 1200));
    }
    setChecking(false);
    setStatusMessage("Reconciler queried. Provider status remains pending. Authority and single-use exposure remain safely held.");
  };

  return (
    <div className="card space-y-6 border-brand/30 bg-panel/90 p-6 sm:p-8 animate-fadeIn shadow-2xl">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-edge/80 pb-4">
        <div>
          <span className="label text-brand font-semibold">Step 5 · Distributed Systems Hold</span>
          <h2 className="mt-1 text-2xl font-bold tracking-tight text-white sm:text-3xl flex items-center gap-2.5">
            <span>We&apos;re confirming the checkout</span>
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand/20 text-brand text-sm">
              ⏳
            </span>
          </h2>
        </div>

        <div className="text-right">
          <span className="rounded-full border border-brand/40 bg-brand/10 px-3 py-1 font-mono text-xs font-semibold text-brand">
            OUTCOME PENDING RECONCILIATION
          </span>
        </div>
      </div>

      {/* Clear Plain-Language Explanation */}
      <div className="rounded-xl border border-brand/30 bg-brand/[0.04] p-4 text-sm text-slate-200 leading-relaxed">
        {outcome.summary}
      </div>

      {/* Status Grid */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl border border-edge/80 bg-ink/70 p-3.5 text-center">
          <p className="text-[10px] uppercase tracking-wider text-muted font-medium">Provider Action</p>
          <p className="mt-1 font-semibold text-white text-xs sm:text-sm">One request sent</p>
        </div>

        <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.05] p-3.5 text-center">
          <p className="text-[10px] uppercase tracking-wider text-amber-400 font-medium">Duplicate Retry</p>
          <p className="mt-1 font-semibold text-amber-300 text-xs sm:text-sm">Frozen (Suppressed)</p>
        </div>

        <div className="rounded-xl border border-edge/80 bg-ink/70 p-3.5 text-center">
          <p className="text-[10px] uppercase tracking-wider text-muted font-medium">Headroom Exposure</p>
          <p className="mt-1 font-semibold text-slate-200 text-xs sm:text-sm">Held atomically</p>
        </div>
      </div>

      {statusMessage && (
        <div className="rounded-xl border border-edge/80 bg-ink/60 p-3 text-xs text-slate-300">
          ℹ️ {statusMessage}
        </div>
      )}

      {/* Primary Actions: Check Status, but NEVER a blind duplicate retry */}
      <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
        <button
          type="button"
          onClick={onStartNewOrder}
          className="btn btn-ghost text-xs"
        >
          ← Start new shopping job
        </button>

        <button
          type="button"
          onClick={handleCheck}
          disabled={checking}
          className="btn btn-primary inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold"
        >
          {checking ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              <span>Checking reconciliation...</span>
            </>
          ) : (
            <span>Check provider status</span>
          )}
        </button>
      </div>

      {/* Progressive Technical Disclosure */}
      <TrustDetails
        title="Technical status: UNKNOWN (Idempotent hold)"
        items={[
          { label: "Action Status", value: outcome.actionStatus, mono: true },
          { label: "Grant ID", value: outcome.grantId, mono: true },
          { label: "Single Use Consumed", value: "True (Held in spend_ledger)" },
          { label: "Retry Behavior", value: "Same grant returned; zero duplicate dispatches" },
          { label: "Reconciliation Mode", value: "Authoritative provider poll / webhook sweep" },
        ]}
        badges={[
          { label: "Unknown Outcome Preserved", tone: "brand" },
          { label: "Blind Retry Suppressed", tone: "allow" },
        ]}
      />
    </div>
  );
};
