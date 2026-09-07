"use client";

import React, { useState } from "react";

interface TrustDetailsProps {
  title?: string;
  items: Array<{ label: string; value: string | number | null | undefined; mono?: boolean }>;
  badges?: Array<{ label: string; tone?: "brand" | "allow" | "risk" | "neutral" }>;
}

export const TrustDetails: React.FC<TrustDetailsProps> = ({
  title = "Technical authority details",
  items,
  badges = [],
}) => {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl border border-edge/60 bg-ink/40">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between p-3.5 text-left text-xs font-medium text-muted transition hover:text-slate-200"
      >
        <span className="flex items-center gap-2">
          <span className="text-brand font-mono text-[11px]">{open ? "▼" : "▶"}</span>
          <span>{title}</span>
        </span>
        <span className="text-[10px] text-muted uppercase tracking-wider font-mono">
          {open ? "Hide audit proof" : "Inspect audit proof"}
        </span>
      </button>

      {open && (
        <div className="border-t border-edge/60 p-4 space-y-3.5 animate-fadeIn">
          {badges.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pb-1">
              {badges.map((b, idx) => (
                <span
                  key={idx}
                  className={`rounded px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider border ${
                    b.tone === "allow"
                      ? "border-allow/30 bg-allow/10 text-allow"
                      : b.tone === "risk"
                      ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
                      : "border-brand/30 bg-brand/10 text-brand"
                  }`}
                >
                  {b.label}
                </span>
              ))}
            </div>
          )}

          <dl className="grid gap-2 text-xs sm:grid-cols-2">
            {items.map((item, idx) => (
              <div key={idx} className="rounded-lg border border-edge/40 bg-panel/30 p-2.5">
                <dt className="text-[10px] uppercase tracking-wider text-muted">{item.label}</dt>
                <dd
                  className={`mt-1 font-semibold text-slate-200 break-all ${
                    item.mono ? "font-mono text-[11px]" : ""
                  }`}
                >
                  {item.value || "—"}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
};
