"use client";

import { inr, type Cart, type Mandate } from "@/lib/api";

export function CartPanel({
  cart,
  mandate,
  exposure,
  busy,
  onAuthorize,
}: {
  cart: Cart;
  mandate: Mandate | null;
  exposure: number;
  busy: boolean;
  onAuthorize: () => void;
}) {
  const total = cart.lines.reduce(
    (sum, line) => sum + line.unit_price_paise * line.qty,
    0,
  );
  const cap = mandate?.cap_paise ?? 0;
  const projected = exposure + total;
  const over = cap > 0 && projected > cap;
  const canAuthorize = Boolean(cart.lines.length && mandate?.active);

  return (
    <div className="card">
      <div className="label">Canonical cart proposal</div>
      {cart.lines.length === 0 ? (
        <p className="mt-3 text-sm text-muted">
          Empty — ask the agent for a shopping goal.
        </p>
      ) : (
        <ul className="mt-3 space-y-2 text-sm">
          {cart.lines.map((line) => (
            <li key={line.sku} className="flex justify-between gap-3">
              <span className="truncate">
                {line.name}{" "}
                {line.qty > 1 && <span className="text-muted">×{line.qty}</span>}
              </span>
              <span className="font-mono text-muted">
                {inr(line.unit_price_paise * line.qty)}
              </span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 flex justify-between border-t border-edge pt-3 text-sm">
        <span>Total</span>
        <span className={"font-mono " + (over ? "text-block" : "")}>
          {inr(total)}
        </span>
      </div>

      {mandate && (
        <div className="mt-4">
          <div className="flex justify-between text-[11px] text-muted">
            <span>Policy exposure after this action</span>
            <span className="font-mono">
              {inr(projected)} / {inr(cap)}
            </span>
          </div>
          <progress
            className={"mt-1 h-2 w-full " + (over ? "accent-block" : "accent-allow")}
            value={Math.min(projected, cap || projected || 1)}
            max={cap || projected || 1}
          />
          {over && (
            <p className="mt-2 text-[11px] text-block">
              The confirmation will be denied by the current policy.
            </p>
          )}
          {!mandate.active && (
            <p className="mt-2 text-[11px] text-block">
              The policy is revoked; no new action receipt can be issued.
            </p>
          )}
        </div>
      )}

      {cart.lines.length > 0 && (
        <div className="mt-4 border-t border-edge pt-4">
          <button
            className="btn w-full"
            type="button"
            onClick={onAuthorize}
            disabled={busy || !canAuthorize}
          >
            {busy ? "Authorizing…" : "Authorize payment link"}
          </button>
          <p className="mt-2 text-[10px] text-muted">
            This explicitly confirms one cart hash and one exact Razorpay action.
          </p>
        </div>
      )}
    </div>
  );
}
