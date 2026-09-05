"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api, inr, type AuditEvent, type AuthorityView, type Metrics } from "@/lib/api";

export default function AuditPage() {
  const [rows, setRows] = useState<AuditEvent[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [authority, setAuthority] = useState<AuthorityView | null>(null);

  async function load() {
    try {
      const [auditRows, metricData, authData] = await Promise.all([
        api.audit(),
        api.metrics(),
        api.authority(),
      ]);
      setRows(auditRows);
      setMetrics(metricData);
      setAuthority(authData);
    } catch {
      // Keep the last verified snapshot visible during a transient refresh error.
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-2xl border border-edge bg-panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="label">User Authority Ceiling · Cross-Envelope Fence</div>
            <h2 className="mt-1 text-xl font-semibold">
              {authority ? inr(authority.ceiling_paise) : "₹2,000"} / {authority?.window ?? "weekly"}
            </h2>
            <p className="mt-1 text-xs text-muted">
              Aggregate hard stop spanning all Purchase Envelopes for user_demo. Enforced atomically in SQLite.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-6 text-sm">
            <div>
              <p className="text-xs text-muted">Total Exposure</p>
              <p className="font-semibold text-slate-100">{authority ? inr(authority.total_exposure_paise) : "₹0"}</p>
            </div>
            <div>
              <p className="text-xs text-muted">Remaining Headroom</p>
              <p className="font-semibold text-allow">{authority ? inr(authority.remaining_headroom_paise) : "₹2,000"}</p>
            </div>
            <div>
              <p className="text-xs text-muted">Active Envelopes</p>
              <p className="font-semibold text-slate-100">{authority?.active_envelopes_count ?? 0}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Stat
          label="Purchase Envelopes activated"
          value={metrics?.envelopes_activated ?? 0}
        />
        <Stat
          label="In-envelope recoveries"
          value={metrics?.in_envelope_recoveries ?? 0}
          tone="allow"
        />
        <Stat
          label="Out-of-envelope quotes refused"
          value={metrics?.envelope_quotes_blocked ?? 0}
          tone="block"
        />
        <Stat
          label="Explicit authorization attempts"
          value={metrics?.authorization_attempts ?? 0}
        />
        <Stat
          label="Denied authorizations"
          value={metrics?.denied_authorizations ?? 0}
          tone="block"
        />
        <Stat
          label="Actuator mismatches denied"
          value={metrics?.unauthorized_actuator_calls ?? 0}
          tone="allow"
        />
        <Stat
          label="Payment links issued"
          value={inr(metrics?.payment_link_issued_value_paise ?? 0)}
        />
        <Stat
          label="Confirmed test payments"
          value={inr(metrics?.confirmed_test_payment_value_paise ?? 0)}
          tone="allow"
        />
        <Stat
          label="Unknown outcome exposure"
          value={inr(metrics?.unknown_outcome_value_paise ?? 0)}
          tone={metrics?.unknown_outcome_value_paise ? "block" : undefined}
        />
      </section>

      <section className="card">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="label">Application event log & Action Receipts</div>
            <p className="mt-1 text-xs text-muted">
              Authorization, dispatch, issuance, denial, and settlement events
              are recorded with opaque action-grant IDs. Every issued action carries a dual-signed receipt
              whose immutable authorization core survives settlement.
            </p>
          </div>
          <span className="rounded-full border border-brand/30 bg-brand/10 px-2.5 py-1 text-[11px] text-brand">
            Dual HMAC-SHA256
          </span>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-[12px]">
            <thead className="text-muted">
              <tr className="border-b border-edge">
                <th className="py-2 pr-4">time</th>
                <th className="py-2 pr-4">event</th>
                <th className="py-2 pr-4">code</th>
                <th className="py-2 pr-4">amount</th>
                <th className="py-2 pr-4">cap</th>
                <th className="py-2 pr-4">policy</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {rows.map((row) => {
                const denied =
                  row.code !== null &&
                  !["ALLOW", "ACTION_ISSUED", "DISPATCHING"].includes(row.code);
                return (
                  <tr key={row.id} className="border-b border-edge/50">
                    <td className="py-1.5 pr-4 text-muted">
                      {new Date(row.created_at * 1000).toLocaleTimeString()}
                    </td>
                    <td className="py-1.5 pr-4">{row.event}</td>
                    <td
                      className={
                        "py-1.5 pr-4 " +
                        (denied ? "text-block" : "text-allow")
                      }
                    >
                      {row.code ?? "—"}
                    </td>
                    <td className="py-1.5 pr-4">
                      {row.cart_total_paise !== null
                        ? inr(row.cart_total_paise)
                        : "—"}
                    </td>
                    <td className="py-1.5 pr-4 text-muted">
                      {row.cap_paise ? inr(row.cap_paise) : "—"}
                    </td>
                    <td className="py-1.5 pr-4 text-muted">
                      {row.mandate_id ?? "—"}
                      {row.mandate_version ? " v" + row.mandate_version : ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rows.length === 0 && (
            <p className="py-6 text-center text-sm text-muted">
              No events yet — create a proposal and explicitly authorize it.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: ReactNode;
  tone?: "allow" | "block";
}) {
  const toneClass =
    tone === "block" ? "text-block" : tone === "allow" ? "text-allow" : "";
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className={"mt-2 text-2xl font-semibold " + toneClass}>{value}</div>
    </div>
  );
}
