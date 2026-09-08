"use client";

import React, { useState } from "react";
import { inr, type AuditEvent } from "@/lib/api";

interface AttemptGroup {
  attemptId: string;
  sessionId: string | null;
  events: AuditEvent[];
  latestEvent: AuditEvent;
  status: "ready" | "blocked" | "unknown" | "in_progress";
  totalPaise: number;
  label: string;
}

export function groupEventsByAttempt(events: AuditEvent[]): AttemptGroup[] {
  const map = new Map<string, AuditEvent[]>();

  for (const ev of events) {
    const attemptId =
      (ev.payload?.purchase_attempt_id as string) ||
      ev.session_id ||
      `legacy_${ev.id}`;

    const list = map.get(attemptId) || [];
    list.push(ev);
    map.set(attemptId, list);
  }

  const groups: AttemptGroup[] = [];

  for (const [attemptId, evs] of map.entries()) {
    // sort chronological
    evs.sort((a, b) => a.created_at - b.created_at);
    const latest = evs[evs.length - 1];

    let status: AttemptGroup["status"] = "in_progress";
    if (evs.some((e) => e.event === "ACTION_ISSUED" || e.event === "ACTION_SETTLED")) {
      status = "ready";
    } else if (
      evs.some(
        (e) =>
          e.event === "ENVELOPE_QUOTE_BLOCKED" ||
          e.event === "MANDATE_BLOCKED" ||
          (e.code && e.code.startsWith("BLOCK_"))
      )
    ) {
      status = "blocked";
    } else if (
      evs.some(
        (e) =>
          e.event === "ACTION_OUTCOME_UNKNOWN" ||
          (e.code && e.code.includes("UNKNOWN"))
      )
    ) {
      status = "unknown";
    }

    const totalPaise =
      latest.cart_total_paise ||
      evs.find((e) => e.cart_total_paise)?.cart_total_paise ||
      42700;

    let label = "Purchase Goal";
    const draftedEv = evs.find((e) => e.event === "ENVELOPE_DRAFTED" || e.payload?.goal);
    if (draftedEv?.payload?.goal) {
      label = String(draftedEv.payload.goal);
    } else if (latest.payload?.goal) {
      label = String(latest.payload.goal);
    }

    groups.push({
      attemptId,
      sessionId: latest.session_id,
      events: evs,
      latestEvent: latest,
      status,
      totalPaise,
      label,
    });
  }

  // Sort groups newest first
  return groups.sort((a, b) => b.latestEvent.created_at - a.latestEvent.created_at);
}

export const AttemptTimeline: React.FC<{ events: AuditEvent[] }> = ({ events }) => {
  const groups = groupEventsByAttempt(events);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (groups.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-slate-500 text-xs">
        No purchase attempts recorded yet. Run a shopping flow from the Agent Checkout tab.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {groups.map((group) => {
        const isExpanded = expandedId === group.attemptId;
        const recoveryEv = group.events.find((e) => e.event === "ENVELOPE_RECOVERY_APPLIED");
        const blockedEv = group.events.find((e) => e.event === "ENVELOPE_QUOTE_BLOCKED");
        const actionEv = group.events.find((e) => e.event === "ACTION_ISSUED");

        return (
          <article
            key={group.attemptId}
            className={`rounded-2xl border transition-all ${
              group.status === "ready"
                ? "border-emerald-200 bg-emerald-50/20"
                : group.status === "blocked"
                ? "border-rose-200 bg-rose-50/20"
                : group.status === "unknown"
                ? "border-amber-200 bg-amber-50/20"
                : "border-slate-200 bg-white"
            } p-5 shadow-xs`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider border ${
                      group.status === "ready"
                        ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                        : group.status === "blocked"
                        ? "border-rose-300 bg-rose-50 text-rose-700"
                        : group.status === "unknown"
                        ? "border-amber-300 bg-amber-50 text-amber-700"
                        : "border-blue-300 bg-blue-50 text-[#0C6CF2]"
                    }`}
                  >
                    {group.status === "ready"
                      ? "CHECKOUT READY"
                      : group.status === "blocked"
                      ? "BLOCKED BEFORE RAZORPAY"
                      : group.status === "unknown"
                      ? "CONFIRMING (UNKNOWN)"
                      : "IN PROGRESS"}
                  </span>
                  <span className="font-mono text-xs text-slate-400">
                    {new Date(group.latestEvent.created_at * 1000).toLocaleTimeString()}
                  </span>
                </div>

                <h3 className="mt-2 text-sm font-bold text-slate-900 capitalize">
                  {group.label}
                </h3>
              </div>

              <div className="text-right">
                <p className="font-mono text-base font-bold text-slate-900">
                  {inr(group.totalPaise)}
                </p>
                <p className="font-mono text-[10px] text-slate-400">
                  attempt: {group.attemptId.slice(0, 14)}…
                </p>
              </div>
            </div>

            {/* Stage Progress Sequence */}
            <div className="mt-3.5 flex flex-wrap items-center gap-1.5 font-mono text-[11px] text-slate-500">
              {group.events.map((ev, i) => (
                <React.Fragment key={ev.id}>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-700 border border-slate-200">
                    {ev.event.replace("ENVELOPE_", "").replace("ACTION_", "")}
                  </span>
                  {i < group.events.length - 1 && <span className="text-slate-300">→</span>}
                </React.Fragment>
              ))}
            </div>

            {/* Explanatory summary */}
            <div className="mt-3.5 text-xs text-slate-600 leading-relaxed border-t border-slate-100 pt-3">
              {group.status === "ready" && (
                <p className="text-emerald-800">
                  ✓ <strong>Authorized inside bounds:</strong>{" "}
                  {recoveryEv
                    ? "In-envelope substitution safely applied. Exactly one Razorpay action issued."
                    : "Quote verified against envelope policy. Action issued."}
                </p>
              )}
              {group.status === "blocked" && (
                <p className="text-rose-800">
                  ✕ <strong>Pre-actuator refusal:</strong> Quote drifted from approved envelope limits. Razorpay was not called.
                </p>
              )}
              {group.status === "unknown" && (
                <p className="text-amber-800">
                  ⏳ <strong>Unknown held:</strong> Provider timed out after dispatch. Retries are suppressed; exposure is held.
                </p>
              )}
            </div>

            {/* Toggle technical disclosure */}
            <div className="mt-3 pt-2">
              <button
                type="button"
                onClick={() => setExpandedId(isExpanded ? null : group.attemptId)}
                className="text-[11px] text-[#0C6CF2] hover:underline font-mono flex items-center gap-1"
              >
                <span>{isExpanded ? "▼ Hide technical digests" : "▶ Inspect technical digests & receipts"}</span>
              </button>
            </div>

            {isExpanded && (
              <div className="mt-3 space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3.5 font-mono text-[11px] text-slate-700 animate-fadeIn">
                <div className="grid gap-2 sm:grid-cols-2">
                  <div>
                    <span className="text-slate-400 uppercase text-[9px]">Session ID:</span>
                    <p className="break-all text-slate-800">{group.sessionId || "—"}</p>
                  </div>
                  <div>
                    <span className="text-slate-400 uppercase text-[9px]">Attempt ID:</span>
                    <p className="break-all text-slate-800">{group.attemptId}</p>
                  </div>
                  <div>
                    <span className="text-slate-400 uppercase text-[9px]">Grant ID:</span>
                    <p className="break-all text-slate-800">
                      {(actionEv?.payload?.grant_id as string) || (group.latestEvent.payload?.grant_id as string) || "None"}
                    </p>
                  </div>
                  <div>
                    <span className="text-slate-400 uppercase text-[9px]">Event Count:</span>
                    <p className="text-slate-800">{group.events.length} audit records</p>
                  </div>
                </div>

                {Boolean(blockedEv?.payload?.deltas) && (
                  <div className="border-t border-slate-200 pt-2 text-rose-700">
                    <span className="text-slate-400 uppercase text-[9px]">Policy Deltas:</span>
                    <pre className="mt-1 text-[10px] overflow-x-auto bg-white border border-rose-200 p-2 rounded text-rose-800">
                      {JSON.stringify(blockedEv?.payload?.deltas, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
};
