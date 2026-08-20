"use client";
import { inr, type Cart, type Mandate } from "@/lib/api";

export function CartPanel({ cart, mandate, spent }: {
  cart: Cart; mandate: Mandate | null; spent: number;
}) {
  const total = cart.lines.reduce((s, l) => s + l.unit_price_paise * l.qty, 0);
  const cap = mandate?.cap_paise ?? 0;
  const projected = spent + total;
  const pct = cap ? Math.min(100, (projected / cap) * 100) : 0;
  const over = cap > 0 && projected > cap;

  return (
    <div className="card">
      <div className="label">Cart</div>
      {cart.lines.length === 0 ? (
        <p className="mt-3 text-sm text-muted">Empty — ask the agent for something.</p>
      ) : (
        <ul className="mt-3 space-y-2 text-sm">
          {cart.lines.map((l) => (
            <li key={l.sku} className="flex justify-between gap-3">
              <span className="truncate">
                {l.name} {l.qty > 1 && <span className="text-muted">×{l.qty}</span>}
              </span>
              <span className="font-mono text-muted">
                {inr(l.unit_price_paise * l.qty)}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 flex justify-between border-t border-edge pt-3 text-sm">
        <span>Total</span>
        <span className={`font-mono ${over ? "text-block" : ""}`}>{inr(total)}</span>
      </div>

      {mandate && (
        <div className="mt-4">
          <div className="flex justify-between text-[11px] text-muted">
            <span>Mandate utilisation</span>
            <span className="font-mono">
              {inr(projected)} / {inr(cap)}
            </span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-ink">
            <div
              className={`h-full transition-all ${over ? "bg-block" : "bg-allow"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
          {over && (
            <p className="mt-2 text-[11px] text-block">
              This cart would breach the mandate. Checkout will be hard-blocked.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
