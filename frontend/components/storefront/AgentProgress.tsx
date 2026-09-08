"use client";

import React from "react";
import { inr } from "@/lib/api";

interface AgentProgressProps {
  planPaise: number;
  providerDegraded?: boolean;
}

export const AgentProgress: React.FC<AgentProgressProps> = ({
  planPaise,
  providerDegraded = false,
}) => {
  return (
    <div className="card space-y-6 border-brand/25 bg-panel/90 p-6 sm:p-8 animate-fadeIn text-center sm:text-left">
      <div>
        <span className="label">Step 4 · Autonomous Execution</span>
        <h2 className="mt-1 text-2xl font-bold text-white">
          Agent finishing your order...
        </h2>
        <p className="mt-1 text-xs text-muted">
          Verifying real-time stock and pricing against approved limits.
        </p>
      </div>

      <div className="space-y-3 rounded-2xl border border-border bg-canvas p-5 font-mono text-xs">
        <div className="flex items-center gap-3 text-allow font-medium">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-allow/20 text-[11px]">✓</span>
          <span>Understood your goal</span>
        </div>

        <div className="flex items-center gap-3 text-allow font-medium">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-allow/20 text-[11px]">✓</span>
          <span>Built a {inr(planPaise)} plan</span>
        </div>

        <div className="flex items-center gap-3 text-brand font-medium">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand/20">
            <span className="h-2 w-2 rounded-full bg-brand animate-ping" />
          </span>
          <span>Checking current stock and final price</span>
        </div>

        <div className="flex items-center gap-3 text-muted">
          <span className="flex h-5 w-5 items-center justify-center rounded-full border border-edge text-[10px]">○</span>
          <span>Preparing Razorpay checkout</span>
        </div>
      </div>

      {providerDegraded && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">
          ⚠️ Shopping assistance is temporarily limited. Your approved limits remain unchanged.
        </div>
      )}
    </div>
  );
};
