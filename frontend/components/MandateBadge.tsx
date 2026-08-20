"use client";
import { inr, type Decision } from "@/lib/api";

const COPY: Record<string, string> = {
  ALLOW: "Within mandate",
  BLOCK_NO_MANDATE: "No mandate authorised",
  BLOCK_MANDATE_REVOKED: "Mandate revoked",
  BLOCK_WINDOW_CAP_EXCEEDED: "Mandate cap exceeded",
  BLOCK_PER_TXN_CAP_EXCEEDED: "Per-transaction cap exceeded",
  BLOCK_CATEGORY_NOT_ALLOWED: "Category not authorised",
};

/** The verdict chip. This is the object the judges should be looking at. */
export function MandateBadge({ d }: { d: Decision }) {
  const ok = d.allowed;
  return (
    <div
      className={`rounded-xl border p-3 text-xs ${
        ok ? "border-allow/40 bg-allow/10" : "border-block/40 bg-block/10"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={ok ? "text-allow" : "text-block"}>{ok ? "●" : "■"}</span>
        <span className="font-medium">{COPY[d.code] ?? d.code}</span>
        <span className="ml-auto font-mono text-muted">{d.code}</span>
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 font-mono text-[11px] text-muted">
        <div>cart {inr(d.cart_total_paise)}</div>
        <div>cap {inr(d.cap_paise)}</div>
        <div>headroom {inr(d.headroom_paise)}</div>
      </div>
      {d.mandate_id && (
        <div className="mt-1 font-mono text-[10px] text-muted">
          {d.mandate_id} · v{d.mandate_version}
        </div>
      )}
    </div>
  );
}
