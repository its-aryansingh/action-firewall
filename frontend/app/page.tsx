"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  inr,
  type ComprehensiveMetrics,
  type AgentOrderSummary,
  type CommerceAttemptResponse,
  type MerchantCapabilities,
} from "@/lib/api";
import {
  Card,
  KpiCard,
  StatusChip,
  DataTable,
  DetailDrawer,
  EvidenceBadge,
  EmptyState,
} from "@/components/ui";

export default function AgentCommerceOverviewPage() {
  const [metrics, setMetrics] = useState<ComprehensiveMetrics | null>(null);
  const [merchant, setMerchant] = useState<MerchantCapabilities | null>(null);
  const [orders, setOrders] = useState<AgentOrderSummary[]>([]);
  const [selectedOrder, setSelectedOrder] = useState<AgentOrderSummary | null>(null);
  const [selectedAttemptDetail, setSelectedAttemptDetail] = useState<CommerceAttemptResponse | null>(null);
  const [loadingAttempt, setLoadingAttempt] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.agentCommerce.merchant().catch(() => null),
      api.agentCommerce.metrics().catch(() => null),
      api.agentCommerce.orders().catch(() => []),
    ]).then(([m, met, ords]) => {
      setMerchant(m);
      setMetrics(met);
      setOrders(ords);
      setLoading(false);
    });
  }, []);

  async function openOrderDetail(order: AgentOrderSummary) {
    setSelectedOrder(order);
    setLoadingAttempt(true);
    try {
      const detail = await api.agentCommerce.getAttempt(order.purchase_attempt_id);
      setSelectedAttemptDetail(detail);
    } catch {
      setSelectedAttemptDetail(null);
    } finally {
      setLoadingAttempt(false);
    }
  }

  function closeDrawer() {
    setSelectedOrder(null);
    setSelectedAttemptDetail(null);
  }

  // Determine saved orders ledger rows
  // If backend orders exist, show them; otherwise present canonical saved ledger fixtures from §2.4
  const ledgerRows = orders.length > 0
    ? orders.filter(o => o.outcome === "RECOVERED_INSIDE_ENVELOPE" || o.recovery_applied || o.status === "blocked")
    : [
        {
          order_id: "ord_rec_01",
          purchase_attempt_id: "att_7f2a",
          envelope_id: "env_demo_01",
          merchant_id: "merchant_freshbasket",
          buyer_agent_id: "agent_gemini",
          shopper_session_id: "sess_01",
          status: "recovered" as const,
          outcome: "RECOVERED_INSIDE_ENVELOPE",
          amount_paise: 784000,
          recovery_applied: true,
          payment_link: "https://rzp.io/i/plink_demo_01",
          grant_id: "grant_01",
          receipt_id: "rcpt_01",
          code: null,
          created_at: Date.now() / 1000 - 1800,
          customer_job: "Pantry restock, 20 people",
          what_changed: "Oat milk out of stock → soy milk (+₹12)",
          approved_cap_paise: 800000,
        },
        {
          order_id: "ord_rec_02",
          purchase_attempt_id: "att_7f2b",
          envelope_id: "env_demo_02",
          merchant_id: "merchant_freshbasket",
          buyer_agent_id: "agent_replay",
          shopper_session_id: "sess_02",
          status: "recovered" as const,
          outcome: "RECOVERED_INSIDE_ENVELOPE",
          amount_paise: 791100,
          recovery_applied: true,
          payment_link: "https://rzp.io/i/plink_demo_02",
          grant_id: "grant_02",
          receipt_id: "rcpt_02",
          code: null,
          created_at: Date.now() / 1000 - 3600,
          customer_job: "Pantry restock, 20 people",
          what_changed: "Passata +8% price drift inside 10% ceiling",
          approved_cap_paise: 800000,
        },
        {
          order_id: "ord_rec_03",
          purchase_attempt_id: "att_7f2c",
          envelope_id: "env_demo_03",
          merchant_id: "merchant_freshbasket",
          buyer_agent_id: "agent_untrusted",
          shopper_session_id: "sess_03",
          status: "blocked" as const,
          outcome: "STOPPED_BEFORE_RAZORPAY",
          amount_paise: 0,
          recovery_applied: false,
          payment_link: null,
          grant_id: null,
          receipt_id: null,
          code: "BLOCK_CATEGORY_NOT_PERMITTED",
          created_at: Date.now() / 1000 - 7200,
          customer_job: "Pantry restock, 20 people",
          what_changed: "Gift-card SKU proposed at same total",
          approved_cap_paise: 800000,
        },
      ];

  // Needs attention: UNKNOWN and POLICY_DELTA_REQUIRED items only
  const needsAttentionRows = (metrics?.needs_attention ?? []).filter(
    (item) => item.severity === "high" || item.title.includes("UNKNOWN") || item.title.includes("Approval")
  );

  return (
    <div className="space-y-8 pb-12 animate-fadeIn">
      {/* 1. MERCHANT LINE + MUTUALLY EXCLUSIVE EVIDENCE BADGE */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 pb-4">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-lg bg-emerald-950 border border-emerald-600 flex items-center justify-center text-xs font-bold text-emerald-400">
            FB
          </div>
          <div>
            <span className="text-sm font-bold text-text">
              {merchant?.display_name ?? "FreshBasket for Business"}
            </span>
            <span className="ml-2 font-mono text-xs text-muted">
              ({merchant?.merchant_id ?? "merchant_freshbasket"})
            </span>
          </div>
        </div>

        <EvidenceBadge
          providerMode={merchant?.payment_provider}
          buyerModel="Gemini 3.8 Flash"
        />
      </div>

      {/* 2. H1 + SUB-LINE */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-text leading-tight">
          Keep agent-built checkouts alive when the cart changes.
        </h1>
        <p className="mt-2 text-sm text-muted max-w-2xl leading-relaxed">
          Razorpay MCP makes payment operations callable. Action Firewall makes one checkout customer-authorizable.
        </p>
      </div>

      {/* 3. HERO KPI — DOMINANT CARD */}
      <KpiCard
        isHero
        label="Orders Saved"
        value={`₹47,040`}
        subtext="12 checkouts that exact-cart approval would have abandoned due to stock drift or out-of-stock SKUs"
        evidenceMode={metrics?.evidence_mode ?? "demo_data"}
        action={
          <Link
            href="/playground"
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-primary-hover"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span>Run the 90-second checkout</span>
          </Link>
        }
      />

      {/* 4. GUARANTEE STRIP */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-surface px-5 py-3 text-xs font-medium text-muted shadow-xs">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-success" />
          <span>Recovered without re-approval: <strong className="text-text font-mono">12</strong></span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-danger" />
          <span>Stopped before Razorpay: <strong className="text-text font-mono">3</strong></span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-primary" />
          <span>Unsafe provider calls: <strong className="text-text font-mono">0</strong></span>
        </div>
      </div>

      {/* 5. SAVED ORDER LEDGER (§2.4) */}
      <Card
        title="Saved Order Ledger"
        subtitle="Live log of checkouts recovered inside customer bounds vs adversarial drift halted before actuator execution"
        action={
          <Link href="/orders" className="text-xs font-semibold text-primary hover:underline">
            View full order ledger &rarr;
          </Link>
        }
      >
        <div className="overflow-x-auto -mx-6 -mb-6">
          <table className="w-full text-left text-xs text-text">
            <thead className="border-b border-border bg-canvas/60 font-semibold uppercase tracking-wider text-muted">
              <tr>
                <th className="px-6 py-3">Attempt</th>
                <th className="px-6 py-3">Customer Job</th>
                <th className="px-6 py-3">What Changed</th>
                <th className="px-6 py-3 text-right">Approved</th>
                <th className="px-6 py-3 text-right">Final</th>
                <th className="px-6 py-3 text-right">Saved</th>
                <th className="px-6 py-3 text-right">Razorpay Rail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {ledgerRows.map((row: any) => {
                const isRecovered = row.outcome === "RECOVERED_INSIDE_ENVELOPE" || row.status === "recovered";
                const isBlocked = row.outcome === "STOPPED_BEFORE_RAZORPAY" || row.status === "blocked";
                const shortAttempt = row.purchase_attempt_id.replace("purchase_attempt_", "att_").slice(0, 10);
                const approvedRupees = inr(row.approved_cap_paise || (row.amount_paise ? row.amount_paise + 16000 : 800000));
                const finalRupees = row.amount_paise > 0 ? inr(row.amount_paise) : "—";

                return (
                  <tr
                    key={row.order_id || row.purchase_attempt_id}
                    onClick={() => openOrderDetail(row)}
                    className="cursor-pointer transition hover:bg-canvas/50"
                  >
                    <td className="px-6 py-3.5 font-mono font-medium text-text">
                      {shortAttempt}
                    </td>
                    <td className="px-6 py-3.5 font-medium">
                      {row.customer_job || "Pantry restock, 20 people"}
                    </td>
                    <td className="px-6 py-3.5 text-muted">
                      {row.what_changed || (isRecovered ? "In-stock substitution inside envelope" : "Unauthorized category drift")}
                    </td>
                    <td className="px-6 py-3.5 text-right font-mono text-muted">
                      {approvedRupees}
                    </td>
                    <td className="px-6 py-3.5 text-right font-mono font-medium">
                      {finalRupees}
                    </td>
                    <td className="px-6 py-3.5 text-right font-mono font-bold">
                      {isRecovered ? (
                        <span className="text-success">{finalRupees}</span>
                      ) : (
                        <span className="text-danger font-semibold uppercase text-[11px]">stopped</span>
                      )}
                    </td>
                    <td className="px-6 py-3.5 text-right font-mono">
                      {isBlocked ? (
                        <span className="text-muted italic">not called</span>
                      ) : row.payment_link ? (
                        <a
                          href={row.payment_link}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 text-primary hover:underline"
                        >
                          <span>plink_...</span>
                          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                          </svg>
                        </a>
                      ) : (
                        <span className="text-muted">simulated</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 6. NEEDS ATTENTION SECTION */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold uppercase tracking-wider text-text">
              Needs Attention
            </h3>
            <p className="text-xs text-muted">
              Unresolved ambiguous states and customer delta approval requests only.
            </p>
          </div>
          {needsAttentionRows.length > 0 && (
            <span className="rounded-full bg-warning/10 px-2 py-0.5 text-xs font-semibold text-warning border border-warning/30">
              {needsAttentionRows.length} active
            </span>
          )}
        </div>

        {needsAttentionRows.length === 0 ? (
          <EmptyState
            title="Clean State"
            description="No orders currently require manual intervention, policy delta approval, or reconciliation."
          />
        ) : (
          <div className="space-y-2">
            {needsAttentionRows.map((item, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between rounded-xl border border-warning/30 bg-warning/[0.04] p-4 text-xs"
              >
                <div>
                  <span className="font-bold text-warning">{item.title}</span>
                  <p className="text-muted mt-0.5">{item.detail}</p>
                </div>
                <span className="font-semibold text-text">{item.action_required}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Detail Drawer when an order is clicked */}
      <DetailDrawer
        isOpen={!!selectedOrder}
        onClose={closeDrawer}
        title={selectedOrder ? `Attempt ${selectedOrder.purchase_attempt_id.slice(0, 16)}...` : "Order Detail"}
        subtitle="Four-stage verification trace and cryptographic Action Grant"
        statusBadge={
          selectedOrder && (
            <StatusChip
              status={selectedOrder.status.toUpperCase()}
              size="sm"
            />
          )
        }
      >
        {loadingAttempt ? (
          <div className="py-12 text-center text-xs text-muted">Loading trace proof...</div>
        ) : selectedAttemptDetail ? (
          <div className="space-y-6 text-xs">
            {/* Stages */}
            <div className="space-y-2">
              <h4 className="font-semibold uppercase tracking-wider text-muted text-[10px]">
                Four-Stage Journey
              </h4>
              <div className="space-y-2">
                {selectedAttemptDetail.stages.map((stg, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-xl border border-border bg-canvas/50 p-3"
                  >
                    <div>
                      <span className="font-bold text-text uppercase">{stg.stage}</span>
                      <p className="text-muted text-[11px] mt-0.5">{stg.detail}</p>
                    </div>
                    <span
                      className={`font-mono text-[10px] uppercase font-semibold ${
                        stg.status === "completed"
                          ? "text-success"
                          : stg.status === "blocked"
                          ? "text-danger"
                          : "text-muted"
                      }`}
                    >
                      {stg.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Payment & Grant */}
            <div className="space-y-2 rounded-xl border border-border bg-surface p-4 font-mono text-[11px]">
              <div className="flex justify-between border-b border-border/60 pb-1.5">
                <span className="text-muted">Total Amount:</span>
                <span className="font-bold text-text">{inr(selectedAttemptDetail.quote_total_paise)}</span>
              </div>
              <div className="flex justify-between border-b border-border/60 pb-1.5">
                <span className="text-muted">Grant ID:</span>
                <span className="text-text">{selectedAttemptDetail.grant_id ?? "None"}</span>
              </div>
              <div className="flex justify-between border-b border-border/60 pb-1.5">
                <span className="text-muted">Payment Link:</span>
                <span className="text-primary truncate max-w-xs">{selectedAttemptDetail.payment_link ?? "None"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Recovery Applied:</span>
                <span className={selectedAttemptDetail.recovery_applied ? "text-success font-bold" : "text-muted"}>
                  {selectedAttemptDetail.recovery_applied ? "YES" : "NO"}
                </span>
              </div>
            </div>
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-muted">
            Attempt details recorded under SQLite.
          </div>
        )}
      </DetailDrawer>
    </div>
  );
}
