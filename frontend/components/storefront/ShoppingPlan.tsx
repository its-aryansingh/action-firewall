"use client";

import React from "react";
import { inr } from "@/lib/api";
import type { ShoppingPlanView } from "@/lib/presentation";
import { ProductLineCard } from "./ProductLineCard";

interface ShoppingPlanProps {
  plan: ShoppingPlanView;
  onEditGoal: () => void;
  onReviewLimits: () => void;
  busy: boolean;
}

export const ShoppingPlan: React.FC<ShoppingPlanProps> = ({
  plan,
  onEditGoal,
  onReviewLimits,
  busy,
}) => {
  return (
    <div className="card space-y-6 border-brand/20 bg-panel/80 p-6 sm:p-8 animate-fadeIn">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-edge/80 pb-5">
        <div>
          <span className="label">Step 2 · AI Shopping Plan</span>
          <h2 className="mt-1 text-2xl font-bold tracking-tight text-white capitalize sm:text-3xl">
            {plan.goal}
          </h2>
          <p className="mt-1 text-xs text-muted">
            Store: <strong className="text-slate-200">{plan.merchantName}</strong> · Standard delivery (within 45m)
          </p>
        </div>

        <div className="rounded-2xl border border-border bg-surface px-5 py-3 text-right">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted">Estimated Plan Total</p>
          <p className="font-mono text-2xl font-bold tracking-tight text-white sm:text-3xl">
            {inr(plan.totalPaise)}
          </p>
        </div>
      </div>

      {/* Grid of Items */}
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted mb-3">
          Composed Basket ({plan.items.length} items)
        </h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {plan.items.map((item) => (
            <ProductLineCard key={item.sku} item={item} />
          ))}
        </div>
      </div>

      {/* Grounded Explanation */}
      <div className="rounded-xl border border-brand/20 bg-brand/[0.04] p-4">
        <div className="flex items-start gap-3">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand text-xs font-bold">
            AI
          </span>
          <div className="space-y-1 text-xs leading-relaxed text-slate-300">
            <p className="font-semibold text-white">Why this works</p>
            <p>{plan.explanation}</p>
          </div>
        </div>
      </div>

      {/* CTAs */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-edge/60 pt-5">
        <button
          type="button"
          onClick={onEditGoal}
          disabled={busy}
          className="btn btn-ghost text-xs"
        >
          ← Edit goal
        </button>

        <button
          type="button"
          onClick={onReviewLimits}
          disabled={busy}
          className="btn btn-primary inline-flex items-center gap-2 px-6 py-2.5 text-sm font-semibold"
        >
          <span>Review limits</span>
          <span aria-hidden="true">&rarr;</span>
        </button>
      </div>
    </div>
  );
};
