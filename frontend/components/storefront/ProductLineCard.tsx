import React from "react";
import { inr } from "@/lib/api";
import type { ShoppingPlanItem } from "@/lib/presentation";

interface ProductLineCardProps {
  item: ShoppingPlanItem;
}

export const ProductLineCard: React.FC<ProductLineCardProps> = ({ item }) => {
  return (
    <article className="group relative flex flex-col justify-between rounded-xl border border-edge/80 bg-panel/70 p-3.5 transition hover:border-brand/40 hover:bg-panel">
      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="rounded-md border border-edge/70 bg-ink/60 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted">
            {item.role || item.category}
          </span>
          <span className="inline-flex items-center gap-1 text-[10px] font-medium text-allow">
            <span className="h-1.5 w-1.5 rounded-full bg-allow" />
            In Stock
          </span>
        </div>
        <h4 className="mt-2.5 text-sm font-semibold tracking-tight text-white group-hover:text-brand transition-colors line-clamp-1">
          {item.name}
        </h4>
        <p className="mt-0.5 text-xs text-muted">
          Qty: {item.qty}
        </p>
      </div>

      <div className="mt-3.5 flex items-baseline justify-between border-t border-edge/60 pt-2.5">
        <span className="text-[11px] text-muted">Price</span>
        <span className="font-mono text-sm font-bold text-slate-100">
          {inr(item.pricePaise)}
        </span>
      </div>
    </article>
  );
};
