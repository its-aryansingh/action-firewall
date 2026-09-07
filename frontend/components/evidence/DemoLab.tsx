"use client";

import React, { useState } from "react";
import Link from "next/link";
import { type AutopilotScenario, type Health } from "@/lib/api";

interface DemoLabProps {
  health: Health | null;
}

const SCENARIOS: Array<{
  id: AutopilotScenario;
  title: string;
  description: string;
  expectedResult: string;
  tone: "allow" | "risk" | "hold";
}> = [
  {
    id: "stock_loss",
    title: "1 · Stock Loss → Safe Substitute",
    description: "Preferred pasta runs out. Recover from approved equivalent catalog SKUs without reapproval.",
    expectedResult: "ALLOW_ENVELOPE (Penne replaces Spaghetti, ₹427 <= ₹600)",
    tone: "allow",
  },
  {
    id: "merchant_drift",
    title: "2 · Merchant Drift → Refusal",
    description: "Quote moves to an unapproved vendor. Refuse immediately before actuator invocation.",
    expectedResult: "BLOCK_ENVELOPE_MISMATCH (merchant_id mismatch; 0 Razorpay calls)",
    tone: "risk",
  },
  {
    id: "price_drift",
    title: "3 · Price Cap Drift → Refusal",
    description: "Final quote exceeds the shopper's approved ceiling.",
    expectedResult: "BLOCK_ENVELOPE_MISMATCH (max_total_paise breached)",
    tone: "risk",
  },
  {
    id: "timeout_after_dispatch",
    title: "4 · Provider Timeout → Idempotent Hold",
    description: "Actuator times out after dispatch. State held as UNKNOWN; blind retry is suppressed.",
    expectedResult: "UNKNOWN (One use occupied, retry returns same grant)",
    tone: "hold",
  },
  {
    id: "normal",
    title: "5 · Clean In-Bounds Checkout",
    description: "Baseline quote matching all approved parameters.",
    expectedResult: "ALLOW_ENVELOPE (Exact match, payment link issued)",
    tone: "allow",
  },
];

export const DemoLab: React.FC<DemoLabProps> = ({ health }) => {
  const [open, setOpen] = useState(false);

  const canInject = Boolean(health?.demo_mode && health?.fault_injection_enabled);

  return (
    <div className="rounded-2xl border border-edge/80 bg-panel/70 p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-edge/60 pb-3">
        <div>
          <span className="label">Evaluator & Presentation Sandbox</span>
          <h3 className="text-base font-bold text-white mt-0.5">
            Judge Demo Lab
          </h3>
        </div>

        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="btn btn-ghost text-xs"
        >
          {open ? "Hide Demo Lab" : "Open Demo Lab"}
        </button>
      </div>

      <p className="text-xs text-muted leading-relaxed">
        {canInject ? (
          <span>
            ⚠️ <strong>Controlled Demo Condition:</strong> Injects deterministic boundary scenarios on camera to verify authorization gates. The backend strictly rejects simulated faults when running against live providers.
          </span>
        ) : (
          <span>
            🔒 <strong>Live Provider Protected:</strong> Fault injection is disabled when live Razorpay credentials or production mode is active.
          </span>
        )}
      </p>

      {open && (
        <div className="space-y-3 pt-2 animate-fadeIn">
          {SCENARIOS.map((sc) => (
            <div
              key={sc.id}
              className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-xl border border-edge/60 bg-ink/70"
            >
              <div className="space-y-1 max-w-xl">
                <div className="flex items-center gap-2">
                  <h4 className="text-xs font-bold text-white">{sc.title}</h4>
                  <span
                    className={`rounded px-1.5 py-0.2 font-mono text-[9px] uppercase tracking-wider ${
                      sc.tone === "allow"
                        ? "bg-allow/10 text-allow"
                        : sc.tone === "risk"
                        ? "bg-rose-500/10 text-rose-300"
                        : "bg-amber-500/10 text-amber-300"
                    }`}
                  >
                    {sc.tone === "allow" ? "ALLOW" : sc.tone === "risk" ? "BLOCK" : "HOLD"}
                  </span>
                </div>
                <p className="text-xs text-muted">{sc.description}</p>
                <p className="text-[11px] font-mono text-slate-300">
                  Expected: <span className="text-brand">{sc.expectedResult}</span>
                </p>
              </div>

              <div>
                <Link
                  href={`/?scenario=${sc.id}`}
                  className="btn btn-primary text-xs py-1.5 px-3 whitespace-nowrap inline-flex items-center gap-1.5"
                >
                  <span>Launch in Shop</span>
                  <span aria-hidden="true">&rarr;</span>
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
