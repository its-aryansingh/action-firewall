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
    <div className="space-y-8 animate-fadeIn pb-12">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-primary/10 text-[#0C6CF2] border border-primary/30">
            Track 01 · Trust Engine
          </span>
          <span className="text-xs text-muted">
            Independent Technical Proof
          </span>
        </div>
        <h1 className="mt-2 text-2xl font-bold text-text tracking-tight sm:text-3xl">
          Action Firewall Evidence &amp; Audit
        </h1>
        <p className="mt-1 text-xs text-muted max-w-2xl">
          Attempt-centered lifecycle history, cross-envelope authority bounds, and cryptographic HMAC-SHA256 Action Receipts.
        </p>
      </div>

      {/* User Authority Ceiling */}
      <section className="overflow-hidden rounded-2xl border border-border bg-surface p-5 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <span className="text-[10px] font-mono uppercase tracking-wider text-muted font-semibold">
              User Authority Ceiling · Cross-Envelope Fence
            </span>
            <h2 className="mt-1 text-2xl font-bold text-text font-mono">
              {authority ? inr(authority.ceiling_paise) : "₹2,000"} / {authority?.window ?? "weekly"}
            </h2>
            <p className="mt-1 text-xs text-muted max-w-xl">
              Aggregate hard stop spanning all Purchase Envelopes for user_demo. Enforced atomically under SQLite BEGIN IMMEDIATE before any actuator call.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-6 text-sm">
            <div>
              <p className="text-xs text-muted">Total Exposure</p>
              <p className="font-semibold text-text font-mono">
                {authority ? inr(authority.total_exposure_paise) : "₹0"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted">Remaining Headroom</p>
              <p className="font-semibold text-success font-mono">
                {authority ? inr(authority.remaining_headroom_paise) : "₹2,000"}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted">Active Envelopes</p>
              <p className="font-semibold text-text font-mono">
                {authority?.active_envelopes_count ?? 0}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Metric Stats Grid */}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-border bg-surface p-4 shadow-xs">
          <p className="text-[11px] uppercase tracking-wider text-muted font-semibold">Envelopes Activated</p>
          <p className="mt-1 font-mono text-xl font-bold text-text">
            {metrics?.envelopes_activated ?? 0}
          </p>
        </div>

        <div className="rounded-xl border border-success/30 bg-success/10/40 p-4 shadow-xs">
          <p className="text-[11px] uppercase tracking-wider text-success font-semibold">In-Envelope Recoveries</p>
          <p className="mt-1 font-mono text-xl font-bold text-success">
            {metrics?.in_envelope_recoveries ?? 0}
          </p>
        </div>

        <div className="rounded-xl border border-rose-200 bg-rose-50/40 p-4 shadow-xs">
          <p className="text-[11px] uppercase tracking-wider text-rose-700 font-semibold">Drifts Blocked</p>
          <p className="mt-1 font-mono text-xl font-bold text-rose-700">
            {metrics?.envelope_quotes_blocked ?? 0}
          </p>
        </div>

        <div className="rounded-xl border border-border bg-surface p-4 shadow-xs">
          <p className="text-[11px] uppercase tracking-wider text-muted font-semibold">Payment Links Issued</p>
          <p className="mt-1 font-mono text-xl font-bold text-text">
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
            <h2 className="text-base font-bold text-text tracking-tight">
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
      <section className="rounded-2xl border border-border bg-surface p-5 space-y-4 shadow-xs">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-text">Raw Forensic Audit Log</h3>
            <p className="text-xs text-muted">Append-only SQLite event trail for deep compliance audit.</p>
          </div>
          <button
            type="button"
            onClick={() => setShowRawTable(!showRawTable)}
            className="px-3 py-1.5 rounded-lg border border-border hover:bg-canvas text-text text-xs font-medium transition"
          >
            {showRawTable ? "Hide Raw Table" : "Show Raw Table"}
          </button>
        </div>

        {showRawTable && (
          <div className="overflow-x-auto rounded-xl border border-border bg-surface animate-fadeIn">
            <table className="w-full text-left font-mono text-xs text-text">
              <thead className="border-b border-border bg-canvas text-[10px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="px-3.5 py-2.5">Time</th>
                  <th className="px-3.5 py-2.5">Event</th>
                  <th className="px-3.5 py-2.5">Code</th>
                  <th className="px-3.5 py-2.5">Total</th>
                  <th className="px-3.5 py-2.5">Attempt / Session</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.slice(0, 50).map((r) => (
                  <tr key={r.id} className="hover:bg-canvas/80 transition">
                    <td className="px-3.5 py-2 text-muted whitespace-nowrap">
                      {new Date(r.created_at * 1000).toLocaleTimeString()}
                    </td>
                    <td className="px-3.5 py-2 font-semibold text-text">
                      {r.event}
                    </td>
                    <td className="px-3.5 py-2 text-[#0C6CF2]">
                      {r.code || "—"}
                    </td>
                    <td className="px-3.5 py-2 font-bold text-text">
                      {r.cart_total_paise ? inr(r.cart_total_paise) : "—"}
                    </td>
                    <td className="px-3.5 py-2 text-muted text-[10px] truncate max-w-xs">
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
