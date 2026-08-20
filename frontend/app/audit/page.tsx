"use client";
import { useEffect, useState } from "react";
import { api, inr, type Metrics } from "@/lib/api";

export default function AuditPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [m, setM] = useState<Metrics | null>(null);

  async function load() {
    try {
      setRows(await api.audit());
      setM(await api.metrics());
    } catch { /* backend down */ }
  }
  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-6">
      <section className="grid gap-4 sm:grid-cols-4">
        <Stat label="Mandate checks" value={m?.mandate_checks ?? 0} />
        <Stat label="Breach attempts blocked" value={m?.mandate_breach_attempts ?? 0} tone="block" />
        <Stat label="Breach attempt rate"
              value={`${((m?.mandate_breach_attempt_rate ?? 0) * 100).toFixed(1)}%`} />
        <Stat label="Chargeback liability"
              value={inr(m?.chargeback_liability_paise ?? 0)} tone="allow" />
      </section>

      <section className="card">
        <div className="label">Append-only audit log</div>
        <p className="mt-1 text-xs text-muted">
          Every mandate evaluation is recorded before any Razorpay MCP tool is reachable.
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-[12px]">
            <thead className="text-muted">
              <tr className="border-b border-edge">
                <th className="py-2 pr-4">time</th>
                <th className="py-2 pr-4">event</th>
                <th className="py-2 pr-4">code</th>
                <th className="py-2 pr-4">cart</th>
                <th className="py-2 pr-4">cap</th>
                <th className="py-2 pr-4">mandate</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {rows.map((r) => {
                const bad = r.code && r.code !== "ALLOW";
                return (
                  <tr key={r.id} className="border-b border-edge/50">
                    <td className="py-1.5 pr-4 text-muted">
                      {new Date(r.created_at * 1000).toLocaleTimeString()}
                    </td>
                    <td className="py-1.5 pr-4">{r.event}</td>
                    <td className={`py-1.5 pr-4 ${bad ? "text-block" : "text-allow"}`}>
                      {r.code ?? "—"}
                    </td>
                    <td className="py-1.5 pr-4">
                      {r.cart_total_paise != null ? inr(r.cart_total_paise) : "—"}
                    </td>
                    <td className="py-1.5 pr-4 text-muted">
                      {r.cap_paise ? inr(r.cap_paise) : "—"}
                    </td>
                    <td className="py-1.5 pr-4 text-muted">
                      {r.mandate_id ?? "—"}{r.mandate_version ? ` v${r.mandate_version}` : ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {rows.length === 0 && (
            <p className="py-6 text-center text-sm text-muted">
              No events yet — run a chat turn.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div className="card">
      <div className="label">{label}</div>
      <div className={`mt-2 text-2xl font-semibold ${
        tone === "block" ? "text-block" : tone === "allow" ? "text-allow" : ""}`}>
        {value}
      </div>
    </div>
  );
}
