"use client";

import React from "react";
import { inr } from "@/lib/api";
import type { ApprovalSummaryView } from "@/lib/presentation";
import { TrustDetails } from "./TrustDetails";

interface ApprovalSheetProps {
  summary: ApprovalSummaryView;
  onApprove: () => void;
  onEdit: () => void;
  busy: boolean;
  error: string | null;
}

export const ApprovalSheet: React.FC<ApprovalSheetProps> = ({
  summary,
  onApprove,
  onEdit,
  busy,
  error,
}) => {
  return (
    <div className="card space-y-6 border-brand/30 bg-panel/90 p-6 sm:p-8 animate-fadeIn shadow-2xl">
      <div className="border-b border-edge/80 pb-4">
        <div className="flex items-center justify-between">
          <span className="label">Step 3 · Human Authorization</span>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-brand/30 bg-brand/10 px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-brand">
            Single-Use Authority
          </span>
        </div>
        <h2 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl">
          Approve this shopping job?
        </h2>
        <p className="mt-1 text-xs text-muted">
          Review your bounded terms. The agent may recover from stock changes only within these exact constraints.
        </p>
      </div>

      {/* Structured Terms Table */}
      <div className="rounded-2xl border border-edge/90 bg-ink/70 overflow-hidden divide-y divide-edge/60">
        <div className="flex items-center justify-between px-4 py-3 sm:px-6">
          <span className="text-xs text-muted">Store</span>
          <span className="text-sm font-semibold text-white">{summary.merchantName}</span>
        </div>

        <div className="flex items-center justify-between px-4 py-3 sm:px-6">
          <span className="text-xs text-muted">Spend up to</span>
          <span className="font-mono text-base font-bold text-allow">
            {inr(summary.maxTotalPaise)}
          </span>
        </div>

        <div className="flex items-center justify-between px-4 py-3 sm:px-6">
          <span className="text-xs text-muted">Must include</span>
          <span className="text-xs font-semibold text-slate-200 text-right">
            {summary.requiredItems.join(" · ")}
          </span>
        </div>

        <div className="flex items-center justify-between px-4 py-3 sm:px-6">
          <span className="text-xs text-muted">Substitutions</span>
          <span className="text-xs text-slate-300">{summary.substitutionRule}</span>
        </div>

        <div className="flex items-center justify-between px-4 py-3 sm:px-6">
          <span className="text-xs text-muted">Deliver to</span>
          <span className="text-xs text-slate-200">{summary.destinationLabel}</span>
        </div>

        <div className="flex items-center justify-between px-4 py-3 sm:px-6">
          <span className="text-xs text-muted">Expires in</span>
          <span className="text-xs font-mono text-slate-300">
            {summary.expiresInMinutes} minutes
          </span>
        </div>

        <div className="flex items-center justify-between px-4 py-3 sm:px-6">
          <span className="text-xs text-muted">Allowed purchases</span>
          <span className="text-xs font-semibold text-brand">
            Exactly one purchase (1-use)
          </span>
        </div>
      </div>

      <div className="rounded-xl border border-edge/60 bg-panel/50 px-4 py-3 text-center">
        <p className="text-xs font-medium text-slate-300">
          🛡️ <strong className="text-white">The agent cannot change these limits.</strong> Any alteration to merchant, price cap, destination, or items requires fresh approval.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs text-rose-300">
          <strong>Activation failed:</strong> {error}
        </div>
      )}

      {/* Progressive Disclosure of Cryptographic Authority */}
      <TrustDetails
        title="Technical authority details"
        items={[
          { label: "Envelope ID", value: summary.envelopeId, mono: true },
          { label: "Version", value: `v${summary.envelopeVersion}` },
          { label: "Envelope SHA-256 Hash", value: summary.envelopeHash, mono: true },
          { label: "Registered Action", value: summary.actionName, mono: true },
          { label: "Merchant Identifier", value: summary.merchantId, mono: true },
          { label: "Blocked Categories", value: summary.blockedCategories.join(", ") || "None" },
        ]}
        badges={[
          { label: "Action Firewall Gated", tone: "brand" },
          { label: "Closed Actuator", tone: "allow" },
        ]}
      />

      {/* Action Buttons */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-edge/60 pt-4">
        <button
          type="button"
          onClick={onEdit}
          disabled={busy}
          className="btn btn-ghost text-xs"
        >
          ← Edit plan
        </button>

        <button
          type="button"
          onClick={onApprove}
          disabled={busy}
          className="btn btn-primary inline-flex items-center gap-2 px-6 py-2.5 text-sm font-semibold"
        >
          {busy ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              <span>Activating envelope...</span>
            </>
          ) : (
            <>
              <span>Approve & let agent finish</span>
              <span aria-hidden="true">&rarr;</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
};
