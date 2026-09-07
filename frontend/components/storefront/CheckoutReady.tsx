"use client";

import React, { useState } from "react";
import { inr } from "@/lib/api";
import type { CheckoutOutcomeView } from "@/lib/presentation";
import { TrustDetails } from "./TrustDetails";

interface CheckoutReadyProps {
  outcome: Extract<CheckoutOutcomeView, { kind: "ready" }>;
  onStartNewOrder: () => void;
}

export const CheckoutReady: React.FC<CheckoutReadyProps> = ({
  outcome,
  onStartNewOrder,
}) => {
  const [mockPaid, setMockPaid] = useState(false);
  const hasSubstitutions = outcome.substitutions.length > 0;

  return (
    <div className="card space-y-6 border-allow/30 bg-panel/90 p-6 sm:p-8 animate-fadeIn shadow-2xl">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-edge/80 pb-4">
        <div>
          <span className="label text-allow font-semibold">Step 5 · Checkout Ready</span>
          <h2 className="mt-1 text-2xl font-bold tracking-tight text-white sm:text-3xl flex items-center gap-2.5">
            <span>Checkout preserved</span>
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-allow/20 text-allow text-sm">
              ✓
            </span>
          </h2>
        </div>

        <div className="text-right">
          <span className="rounded-full border border-allow/40 bg-allow/10 px-3 py-1 font-mono text-xs font-semibold text-allow">
            {outcome.providerMode === "razorpay_mcp" ? "RAZORPAY TEST MODE" : "SIMULATED PROVIDER"}
          </span>
        </div>
      </div>

      {/* Main explanation */}
      <div className="rounded-xl border border-allow/20 bg-allow/[0.04] p-4 text-sm text-slate-200 leading-relaxed">
        {outcome.summary}
      </div>

      {/* Before / After Price Comparison */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4">
        <div className="rounded-xl border border-edge/80 bg-ink/60 p-4">
          <p className="text-[11px] uppercase tracking-wider text-muted font-medium">Initial Plan</p>
          <p className="mt-1 font-mono text-xl font-bold text-slate-300">
            {inr(outcome.previousTotalPaise)}
          </p>
        </div>

        <div className="rounded-xl border border-allow/40 bg-ink/80 p-4">
          <p className="text-[11px] uppercase tracking-wider text-allow font-medium">Final Total (Approved)</p>
          <p className="mt-1 font-mono text-xl font-bold text-white">
            {inr(outcome.finalTotalPaise)} <span className="text-xs font-normal text-muted">of {inr(outcome.maxAllowedPaise)} limit</span>
          </p>
        </div>
      </div>

      {/* Substitution Diff Pill */}
      {hasSubstitutions && (
        <div className="rounded-2xl border border-edge/80 bg-ink/70 p-4 space-y-2.5">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted">
            Eligible In-Envelope Substitution
          </p>
          {outcome.substitutions.map((sub, idx) => (
            <div key={idx} className="flex flex-wrap items-center justify-between gap-2 p-3 rounded-xl border border-edge/60 bg-panel/40">
              <div className="flex items-center gap-2.5 text-xs font-medium">
                <span className="line-through text-muted">{sub.previousName}</span>
                <span className="text-brand font-bold">&rarr;</span>
                <span className="text-white font-semibold">{sub.newName}</span>
              </div>
              <div className="flex items-center gap-2 font-mono text-xs">
                <span className="rounded bg-white/5 px-2 py-0.5 text-slate-300">
                  {sub.reason}
                </span>
                <span className="text-amber-300 font-semibold">
                  +{inr(sub.priceDifferencePaise)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Primary Checkout CTA */}
      <div className="space-y-3 pt-2">
        {outcome.paymentLink ? (
          <a
            href={outcome.paymentLink}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-primary flex w-full items-center justify-center gap-2 py-3 text-base font-bold"
          >
            <span>Open Razorpay checkout</span>
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
          </a>
        ) : (
          <button
            type="button"
            onClick={() => setMockPaid(true)}
            className="btn btn-primary flex w-full items-center justify-center gap-2 py-3 text-base font-bold"
          >
            {mockPaid ? "✓ Simulated checkout completed" : "Open Razorpay checkout (Simulated)"}
          </button>
        )}

        <p className="text-center text-xs text-muted">
          Payment Link issued; payment is not yet settled. Provider observation required for settlement.
        </p>
      </div>

      {/* Expandable Technical Proof */}
      <TrustDetails
        title="Why this was allowed (Action Firewall Proof)"
        items={[
          { label: "Action Grant ID", value: outcome.grantId, mono: true },
          { label: "Final Total", value: inr(outcome.finalTotalPaise) },
          { label: "Approved Limit", value: inr(outcome.maxAllowedPaise) },
          { label: "Within Approved Cap", value: "Yes (₹427 <= ₹600)" },
          { label: "Category Match", value: "Preserved (pasta -> pasta)" },
          { label: "Provider Mode", value: outcome.providerMode },
          { label: "Dual Action Receipt Signature", value: outcome.receiptSignature, mono: true },
        ]}
        badges={[
          { label: "Dual HMAC-SHA256 Signed", tone: "allow" },
          { label: "Headroom Reserved", tone: "brand" },
        ]}
      />

      <div className="border-t border-edge/60 pt-4 flex justify-between items-center">
        <button
          type="button"
          onClick={onStartNewOrder}
          className="btn btn-ghost text-xs"
        >
          ← Start new shopping job
        </button>
      </div>
    </div>
  );
};
