"use client";

import { useEffect, useState } from "react";
import {
  api,
  inr,
  type AuditEvent,
  type AuthorityView,
  type Health,
  type Metrics,
} from "@/lib/api";
import { AttemptTimeline } from "@/components/evidence/AttemptTimeline";
import { DemoLab } from "@/components/evidence/DemoLab";

export default function AuditPage() {
  const [rows, setRows] = useState<AuditEvent[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [authority, setAuthority] = useState<AuthorityView | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [showRawTable, setShowRawTable] = useState(false);

  async function load() {
    try {
      const [auditRows, metricData, authData, healthData] = await Promise.all([
        api.audit(),
        api.metrics(),
        api.authority(),
        api.health(),
      ]);
      setRows(auditRows);
      setMetrics(metricData);
      setAuthority(authData);
      setHealth(healthData);
    } catch {
      // Keep last verified snapshot
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <span className="status-pill border-brand/40 bg-brand/10 text-brand font-semibold">
            Track 01 · Trust Engine
          </span>
          <span className="text-xs text-muted">
            Independent Technical Proof
          </span>
        </div>
        <h1 className="mt-2 text-3xl font-bold text-white tracking-tight sm:text-4xl">
          Action Firewall Evidence & Audit
        </h1>
        <p className="mt-1 text-sm text-muted max-w-2xl">
          Attempt-centered lifecycle history, cross-envelope authority bounds, and cryptographic HMAC-SHA256 Action Receipts.
        </p>
      </div>

      {/* User Authority Ceiling */}
      <section className="overflow-hidden rounded-2xl border border-edge bg-panel/70 p-5 shadow-lg">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <span className="label">User Authority Ceiling · Cross-Envelope Fence</span>
            <h2 className="mt-1 text-2xl font-bold text-white font-mono">
              {authority ? inr(authority.ceiling_paise) : "₹2,000"} / {authority?.window ?? "weekly"}
            </h2>
            <p className="mt-1 text-xs text-muted max-w-xl">
              Aggregate hard stop spanning all Purchase Envelopes for user_demo. Enforced atomically under SQLite BEGIN IMMEDIATE before any actuator call.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-6 text-sm">
            <div>
              <p className="text-xs text-muted">Total Exposure</p>
              <p className="font-semibold text-slate-100 font-mono">
                {authority ? inr(authority.total_exposure_paise) : "₹0"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted">Remaining Headroom</p>
              <p className="font-semibold text-allow font-mono">
                {authority ? inr(authority.remaining_headroom_paise) : "₹2,000"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted">Active Envelopes</p>
              <p className="font-semibold text-slate-100 font-mono">
                {authority?.active_envelopes_count ?? 0}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Metric Stats Grid */}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-edge/80 bg-panel/50 p-4">
          <p className="text-[11px] uppercase tracking-wider text-muted font-medium">Envelopes Activated</p>
          <p className="mt-1 font-mono text-xl font-bold text-white">
            {metrics?.envelopes_activated ?? 0}
          </p>
        </div>

        <div className="rounded-xl border border-allow/30 bg-allow/[0.04] p-4">
          <p className="text-[11px] uppercase tracking-wider text-allow font-medium">In-Envelope Recoveries</p>
          <p className="mt-1 font-mono text-xl font-bold text-allow">
            {metrics?.in_envelope_recoveries ?? 0}
          </p>
        </div>

        <div className="rounded-xl border border-rose-500/30 bg-rose-500/[0.04] p-4">
          <p className="text-[11px] uppercase tracking-wider text-rose-300 font-medium">Drifts Blocked</p>
          <p className="mt-1 font-mono text-xl font-bold text-rose-300">
            {metrics?.envelope_quotes_blocked ?? 0}
          </p>
        </div>

        <div className="rounded-xl border border-edge/80 bg-panel/50 p-4">
          <p className="text-[11px] uppercase tracking-wider text-muted font-medium">Payment Links Issued</p>
          <p className="mt-1 font-mono text-xl font-bold text-white">
            {inr(metrics?.payment_link_issued_value_paise ?? 0)}
          </p>
        </div>
      </section>

      {/* Judge Demo Lab Sandbox */}
      <section>
        <DemoLab health={health} />
      </section>

      {/* Attempt-Centered Timeline */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white tracking-tight">
              Purchase Attempt Timelines
            </h2>
            <p className="text-xs text-muted mt-0.5">
              Individual shopping journeys correlated by attempt identity and cryptographic receipts.
            </p>
          </div>
          <span className="font-mono text-xs text-muted">
            {rows.length} Total Audit Records
          </span>
        </div>

        <AttemptTimeline events={rows} />
      </section>

      {/* Collapsible Forensic Raw Log */}
      <section className="rounded-2xl border border-edge/60 bg-panel/40 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-white">Raw Forensic Audit Log</h3>
            <p className="text-xs text-muted">Append-only SQLite event trail for deep compliance audit.</p>
          </div>
          <button
            type="button"
            onClick={() => setShowRawTable(!showRawTable)}
            className="btn btn-ghost text-xs"
          >
            {showRawTable ? "Hide Raw Table" : "Show Raw Table"}
          </button>
        </div>

        {showRawTable && (
          <div className="overflow-x-auto rounded-xl border border-edge/60 bg-ink/90 animate-fadeIn">
            <table className="w-full text-left font-mono text-xs text-slate-300">
              <thead className="border-b border-edge bg-panel/60 text-[10px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="px-3 py-2">Time</th>
                  <th className="px-3 py-2">Event</th>
                  <th className="px-3 py-2">Code</th>
                  <th className="px-3 py-2">Total</th>
                  <th className="px-3 py-2">Attempt / Session</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge/40">
                {rows.slice(0, 50).map((r) => (
                  <tr key={r.id} className="hover:bg-white/[0.02]">
                    <td className="px-3 py-2 text-muted whitespace-nowrap">
                      {new Date(r.created_at * 1000).toLocaleTimeString()}
                    </td>
                    <td className="px-3 py-2 font-semibold text-slate-200">
                      {r.event}
                    </td>
                    <td className="px-3 py-2 text-brand">
                      {r.code || "—"}
                    </td>
                    <td className="px-3 py-2">
                      {r.cart_total_paise ? inr(r.cart_total_paise) : "—"}
                    </td>
                    <td className="px-3 py-2 text-muted text-[10px] truncate max-w-xs">
                      {(r.payload?.purchase_attempt_id as string) || r.session_id || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
