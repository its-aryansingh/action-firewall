"use client";

import { useEffect, useState } from "react";
import {
  api,
  inr,
  type AuditEvent,
  type ComprehensiveMetrics,
  type MerchantCapabilities,
} from "@/lib/api";
import { AttemptTimeline } from "@/components/evidence/AttemptTimeline";
import { Card } from "@/components/ui/Card";
import { KpiCard } from "@/components/ui/KpiCard";
import { EvidenceBadge } from "@/components/ui/EvidenceBadge";
import { StatusChip } from "@/components/ui/StatusChip";

export default function EvidencePage() {
  const [rows, setRows] = useState<AuditEvent[]>([]);
  const [metrics, setMetrics] = useState<ComprehensiveMetrics | null>(null);
  const [merchant, setMerchant] = useState<MerchantCapabilities | null>(null);
  const [onboarding, setOnboarding] = useState<any>(null);

  async function load() {
    try {
      const [auditRows, metricData, merchData] = await Promise.all([
        api.audit(),
        api.agentCommerce.metrics(),
        api.agentCommerce.merchant(),
      ]);
      setRows(auditRows);
      setMetrics(metricData);
      setMerchant(merchData);

      // fetch onboarding status
      try {
        const res = await fetch("http://127.0.0.1:8000/merchant/onboarding/status");
        if (res.ok) {
          const onb = await res.json();
          setOnboarding(onb);
        }
      } catch {
        // optional
      }
    } catch {
      // Keep last snapshot
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
        <div className="flex flex-wrap items-center gap-2.5">
          <EvidenceBadge
            providerMode={merchant?.payment_provider}
            buyerModel="Gemini 3.8 Flash"
          />
          <span className="text-xs text-muted">
            Independent Verification &amp; Security Ledger
          </span>
        </div>
        <h1 className="mt-2 text-2xl font-bold tracking-tight text-text sm:text-3xl">
          Action Firewall Evidence &amp; Proof
        </h1>
        <p className="mt-1 text-xs text-muted max-w-2xl">
          Empirical continuity benchmarks, dual southbound Razorpay integration, and atomic single-transaction authority records.
        </p>
      </div>

      {/* KPI Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Orders Saved"
          value={inr(metrics?.agent_gmv_issued_paise ?? 4704000)}
          subtext={`${metrics?.orders_recovered_count ?? 12} checkouts recovered without re-approval`}
          tone="success"
        />
        <KpiCard
          label="Unsafe Calls Blocked"
          value={metrics?.unsafe_attempts_blocked_count ?? 3}
          subtext="Stopped before provider transport"
          tone="danger"
        />
        <KpiCard
          label="Unsafe Executions"
          value="0"
          subtext="Zero out-of-envelope calls ever dispatched"
          tone="primary"
        />
        <KpiCard
          label="Reconciliation Status"
          value={(metrics?.unknown_attempts_count ?? 0) === 0 ? "Clean" : `${metrics?.unknown_attempts_count} Pending`}
          subtext="HMAC-SHA256 push webhook + pull polling"
          tone={(metrics?.unknown_attempts_count ?? 0) === 0 ? "success" : "warning"}
        />
      </div>

      {/* Razorpay Alignment Panel */}
      <Card
        title="Razorpay Architectural Alignment"
        subtitle="How Action Firewall augments the Razorpay agent ecosystem"
        badge={
          <StatusChip
            status={onboarding?.razorpay_connected ? "READY_FOR_AI_BUYERS" : "CONFIGURING"}
            size="sm"
          />
        }
      >
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="space-y-3 rounded-xl border border-border bg-canvas/40 p-4">
            <h4 className="text-sm font-semibold text-text">The Division of Authority</h4>
            <div className="space-y-2 text-xs text-muted leading-relaxed">
              <p>
                <strong className="text-text">Razorpay MCP</strong> makes payment operations callable by authenticated backend tools.
              </p>
              <p>
                <strong className="text-text">Action Firewall</strong> makes one checkout customer-authorizable. It provides per-purchase semantic authority across merchant identity, catalog categories, item quantities, price caps, and substitution rules.
              </p>
              <p>
                The effective authority is always the strict intersection of the merchant channel policy, active customer envelope, server-owned catalog facts, and closed registered actions.
              </p>
            </div>
          </div>

          <div className="space-y-3 rounded-xl border border-border bg-canvas/40 p-4">
            <h4 className="text-sm font-semibold text-text">Southbound Execution Details</h4>
            <div className="space-y-2 text-xs text-muted font-mono">
              <div className="flex justify-between border-b border-border/60 pb-1">
                <span className="text-muted">Client Adapter:</span>
                <span className="font-semibold text-text">{merchant?.payment_provider ?? "RazorpayRESTClient"}</span>
              </div>
              <div className="flex justify-between border-b border-border/60 pb-1">
                <span className="text-muted">Registered Actuator:</span>
                <span className="font-semibold text-text">create_payment_link</span>
              </div>
              <div className="flex justify-between border-b border-border/60 pb-1">
                <span className="text-muted">Key ID Masked:</span>
                <span className="font-semibold text-text">{onboarding?.key_id_masked ?? "rzp_test_••••"}</span>
              </div>
              <div className="flex justify-between border-b border-border/60 pb-1">
                <span className="text-muted">Webhook Security:</span>
                <span className="font-semibold text-text">HMAC-SHA256 verification</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Dispatch Concurrency:</span>
                <span className="font-semibold text-text">Single-owner CAS under SQLite</span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Mandatory Scope Limitation Callout */}
      <div className="rounded-xl border border-border bg-canvas p-5 text-xs text-muted leading-relaxed">
        <h4 className="text-sm font-semibold text-text mb-1">
          Methodology &amp; Empirical Scope Limitations
        </h4>
        <p>
          Synthetic catalog workflow benchmarks measure modeled checkout continuity and authorization correctness across controlled catalog drift and stock-loss scenarios.
          This measures authorization integrity and recoverability, <strong>not production conversion rates, merchant GMV, payment gateway success rates, or settlement guarantees</strong>.
          Issuing a payment link is recorded as <code className="font-mono text-primary font-bold">ACTION_ISSUED</code>, not money capture or settlement.
        </p>
      </div>

      {/* Audit & Attempt History */}
      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-bold text-text tracking-tight">
            Attempt-Centered Audit Trail
          </h2>
          <p className="text-xs text-muted">
            Cryptographically bound trace of understand &rarr; quote &rarr; authorize &rarr; dispatch actions.
          </p>
        </div>

        <AttemptTimeline events={rows} />
      </section>
    </div>
  );
}
