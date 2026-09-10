"use client";

import React, { useEffect, useState, use } from "react";
import Link from "next/link";
import { api, inr, type PurchaseEnvelope } from "@/lib/api";

interface ApprovePageProps {
  params: Promise<{ token: string }>;
}

export default function HumanApprovalPage({ params }: ApprovePageProps) {
  const { token } = use(params);
  const [data, setData] = useState<any | null>(null);
  const [activeEnvelope, setActiveEnvelope] = useState<PurchaseEnvelope | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.agentCommerce
      .getApproval(token)
      .then((res) => {
        setData(res);
        if (res.redeemed && res.envelope) {
          setActiveEnvelope(res.envelope);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Failed to load approval details");
        setLoading(false);
      });
  }, [token]);

  async function handleApprove() {
    setBusy(true);
    setError(null);
    try {
      const active = await api.agentCommerce.redeemApproval(token);
      setActiveEnvelope(active);
      setData((prev: any) => ({ ...prev, redeemed: true }));
    } catch (err: any) {
      setError(err.message || "Approval failed");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="max-w-xl mx-auto py-16 text-center text-muted text-xs">
        Loading customer approval request...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="max-w-xl mx-auto py-12">
        <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 text-center space-y-3">
          <div className="h-10 w-10 mx-auto rounded-full bg-rose-100 text-rose-600 flex items-center justify-center font-bold">
            !
          </div>
          <h2 className="text-base font-bold text-rose-900">Approval Request Unavailable</h2>
          <p className="text-xs text-rose-700">{error || "Invalid or expired approval token."}</p>
          <div className="pt-2">
            <Link
              href="/"
              className="text-xs font-semibold text-rose-900 underline hover:text-rose-950"
            >
              &larr; Return to Merchant Dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const envelope: PurchaseEnvelope | null = activeEnvelope || data.envelope;
  const isExpired = data.expired;
  const isRedeemed = data.redeemed;

  return (
    <div className="max-w-xl mx-auto py-8 px-4 space-y-6">
      {/* Brand Header */}
      <div className="text-center space-y-1">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-primary/10 text-[#0C6CF2] border border-primary/30">
          <span>Action Firewall</span>
          <span>·</span>
          <span>Customer Purchase Authority</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-text">
          Review &amp; Authorize Purchase
        </h1>
        <p className="text-xs text-muted">
          Your AI buyer requested authority to transact. Review exact bounds below.
        </p>
      </div>

      {/* Authority Card */}
      <div className="bg-surface border border-border rounded-2xl p-6 shadow-sm space-y-6">
        {/* Merchant & Cap Strip */}
        <div className="flex items-center justify-between p-4 rounded-xl bg-canvas border border-border">
          <div>
            <div className="text-[11px] text-muted uppercase tracking-wider font-semibold">
              Authorized Merchant
            </div>
            <div className="text-sm font-bold text-text mt-0.5">
              FreshBasket for Business <span className="text-muted font-mono text-xs">({envelope?.merchant_id || "merchant_freshbasket"})</span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[11px] text-muted uppercase tracking-wider font-semibold">
              Max Authority Ceiling
            </div>
            <div className="text-lg font-bold font-mono text-[#0C6CF2]">
              {envelope ? inr(envelope.max_total_paise) : "₹8,000.00"}
            </div>
          </div>
        </div>

        {/* Bounded Shopping Slots */}
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-muted mb-2">
            Permitted Purchase Slots
          </h3>
          <div className="space-y-2">
            {(envelope?.slots ?? []).map((slot, i) => (
              <div
                key={slot.id || i}
                className="p-3 rounded-xl border border-border bg-canvas/50 flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 rounded-full bg-primary/10 text-[#0C6CF2] text-[10px] font-bold items-center justify-center">
                    {i + 1}
                  </span>
                  <span className="font-semibold text-text">{slot.label}</span>
                </div>
                <span className="text-[11px] font-mono text-muted">
                  Tags: {slot.required_tags.join(", ")}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Dual Control Invariant Strip */}
        <div className="p-3.5 rounded-xl bg-primary/10/50 border border-primary/20 text-xs text-primary space-y-1">
          <div className="font-bold flex items-center gap-1.5 text-primary">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            Zero Blind Authority Beyond These Bounds
          </div>
          <p className="text-[11px] text-primary/80 leading-relaxed">
            Approving this envelope permits exactly 1 transaction for the specified slots up to the ceiling. The model cannot mutate the merchant, shipping destination, or buy unauthorized categories.
          </p>
        </div>

        {/* Action Button */}
        <div>
          {isRedeemed ? (
            <div className="p-4 rounded-xl bg-success/10 border border-success/30 text-center space-y-2">
              <div className="text-sm font-bold text-success flex items-center justify-center gap-1.5">
                <svg className="h-5 w-5 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Purchase Envelope Activated!
              </div>
              <p className="text-xs text-success">
                The agent is now authorized to execute this checkout within your envelope bounds.
              </p>
              <div className="pt-2">
                <Link
                  href="/orders"
                  className="inline-flex items-center gap-1 text-xs font-bold text-success underline"
                >
                  View Order Status in Operations &rarr;
                </Link>
              </div>
            </div>
          ) : isExpired ? (
            <div className="p-4 rounded-xl bg-warning/10 border border-warning/30 text-center text-xs text-warning">
              This approval link has expired. Request your AI buyer to propose a fresh shopping intent.
            </div>
          ) : (
            <button
              onClick={handleApprove}
              disabled={busy}
              className="w-full py-3 px-4 rounded-xl bg-[#0C6CF2] hover:bg-primary disabled:opacity-50 text-white text-sm font-bold shadow-sm transition flex items-center justify-center gap-2"
            >
              {busy ? "Activating Authority..." : "Approve & Activate Envelope Once"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
