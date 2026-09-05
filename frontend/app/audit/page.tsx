"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api, inr, type AuditEvent, type Metrics } from "@/lib/api";

export default function AuditPage() {
  const [rows, setRows] = useState<AuditEvent[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  async function load() {
    try {
      setRows(await api.audit());
      setMetrics(await api.metrics());
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
        <div className="label">Application event log</div>
        <p className="mt-1 text-xs text-muted">
          Authorization, dispatch, issuance, denial, and unknown-outcome events
          are recorded with the policy version and opaque action-grant ID.
        </p>
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
