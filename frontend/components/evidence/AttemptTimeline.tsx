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
      <div className="rounded-2xl border border-edge/60 bg-panel/40 p-8 text-center text-muted text-sm">
        No purchase attempts recorded yet. Run a shopping flow from the Shop tab.
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
                ? "border-allow/30 bg-panel/70"
                : group.status === "blocked"
                ? "border-rose-500/30 bg-panel/70"
                : group.status === "unknown"
                ? "border-amber-500/30 bg-panel/70"
                : "border-edge/70 bg-panel/50"
            } p-5`}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wider border ${
                      group.status === "ready"
                        ? "border-allow/40 bg-allow/10 text-allow"
                        : group.status === "blocked"
                        ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
                        : group.status === "unknown"
                        ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                        : "border-brand/40 bg-brand/10 text-brand"
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
                  <span className="font-mono text-xs text-muted">
                    {new Date(group.latestEvent.created_at * 1000).toLocaleTimeString()}
                  </span>
                </div>

                <h3 className="mt-2 text-base font-bold text-white capitalize">
                  {group.label}
                </h3>
              </div>

              <div className="text-right">
                <p className="font-mono text-lg font-bold text-slate-100">
                  {inr(group.totalPaise)}
                </p>
                <p className="font-mono text-[10px] text-muted">
                  attempt: {group.attemptId.slice(0, 14)}…
                </p>
              </div>
            </div>

            {/* Stage Progress Sequence */}
            <div className="mt-4 flex flex-wrap items-center gap-1.5 font-mono text-[11px] text-muted">
              {group.events.map((ev, i) => (
                <React.Fragment key={ev.id}>
                  <span className="rounded bg-ink/70 px-2 py-0.5 text-slate-200 border border-edge/50">
                    {ev.event.replace("ENVELOPE_", "").replace("ACTION_", "")}
                  </span>
                  {i < group.events.length - 1 && <span className="text-muted/60">→</span>}
                </React.Fragment>
              ))}
            </div>

            {/* Explanatory summary */}
            <div className="mt-3.5 text-xs text-slate-300 leading-relaxed border-t border-edge/60 pt-3">
              {group.status === "ready" && (
                <p className="text-slate-200">
                  ✓ <strong>Authorized inside bounds:</strong>{" "}
                  {recoveryEv
                    ? "In-envelope substitution safely applied. Exactly one Razorpay action issued."
                    : "Quote verified against envelope policy. Action issued."}
                </p>
              )}
              {group.status === "blocked" && (
                <p className="text-rose-300">
                  ✕ <strong>Pre-actuator refusal:</strong> Quote drifted from approved envelope limits. Razorpay was not called.
                </p>
              )}
              {group.status === "unknown" && (
                <p className="text-amber-300">
                  ⏳ <strong>Unknown held:</strong> Provider timed out after dispatch. Retries are suppressed; exposure is held.
                </p>
              )}
            </div>

            {/* Toggle technical disclosure */}
            <div className="mt-3 pt-2">
              <button
                type="button"
                onClick={() => setExpandedId(isExpanded ? null : group.attemptId)}
                className="text-[11px] text-brand hover:underline font-mono flex items-center gap-1"
              >
                <span>{isExpanded ? "▼ Hide technical digests" : "▶ Inspect technical digests & receipts"}</span>
              </button>
            </div>

            {isExpanded && (
              <div className="mt-3 space-y-2 rounded-xl border border-edge/60 bg-ink/80 p-3.5 font-mono text-[11px] text-slate-300 animate-fadeIn">
                <div className="grid gap-2 sm:grid-cols-2">
                  <div>
                    <span className="text-muted uppercase text-[9px]">Session ID:</span>
                    <p className="break-all">{group.sessionId || "—"}</p>
                  </div>
                  <div>
                    <span className="text-muted uppercase text-[9px]">Attempt ID:</span>
                    <p className="break-all">{group.attemptId}</p>
                  </div>
                  <div>
                    <span className="text-muted uppercase text-[9px]">Grant ID:</span>
                    <p className="break-all">
                      {(actionEv?.payload?.grant_id as string) || (group.latestEvent.payload?.grant_id as string) || "None"}
                    </p>
                  </div>
                  <div>
                    <span className="text-muted uppercase text-[9px]">Event Count:</span>
                    <p>{group.events.length} audit records</p>
                  </div>
                </div>

                {Boolean(blockedEv?.payload?.deltas) && (
                  <div className="border-t border-edge/60 pt-2 text-rose-300">
                    <span className="text-muted uppercase text-[9px]">Policy Deltas:</span>
                    <pre className="mt-1 text-[10px] overflow-x-auto bg-black/40 p-2 rounded">
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
