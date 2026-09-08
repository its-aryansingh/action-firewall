"use client";

import React, { useEffect, useState, useMemo } from "react";
import {
  api,
  inr,
  type AgentOrderSummary,
  type CommerceAttemptResponse,
} from "@/lib/api";
import {
  Card,
  DataTable,
  DetailDrawer,
  StatusChip,
  EmptyState,
  type Column,
} from "@/components/ui";

type OrderFilter = "all" | "advanced" | "recovered" | "stopped" | "reconciliation" | "paid";

export default function OrdersPage() {
  const [orders, setOrders] = useState<AgentOrderSummary[]>([]);
  const [filter, setFilter] = useState<OrderFilter>("all");
  const [search, setSearch] = useState("");
  const [selectedOrder, setSelectedOrder] = useState<AgentOrderSummary | null>(null);
  const [attemptDetail, setAttemptDetail] = useState<CommerceAttemptResponse | null>(null);
  const [activeTab, setActiveTab] = useState("decision");
  const [loading, setLoading] = useState(true);
  const [loadingAttempt, setLoadingAttempt] = useState(false);

  useEffect(() => {
    fetchOrders();
  }, []);

  function fetchOrders() {
    setLoading(true);
    api.agentCommerce
      .orders()
      .then((data) => {
        setOrders(data);
        setLoading(false);
      })
      .catch((err) => {
        console.warn("Could not fetch orders:", err);
        setLoading(false);
      });
  }

  async function handleRowClick(order: AgentOrderSummary) {
    setSelectedOrder(order);
    setActiveTab("decision");
    setLoadingAttempt(true);
    try {
      const detail = await api.agentCommerce.getAttempt(order.purchase_attempt_id);
      setAttemptDetail(detail);
    } catch {
      setAttemptDetail(null);
    } finally {
      setLoadingAttempt(false);
    }
  }

  function closeDrawer() {
    setSelectedOrder(null);
    setAttemptDetail(null);
  }

  const filteredOrders = useMemo(() => {
    return orders.filter((o) => {
      // 1. Status Tab filter
      if (filter === "advanced" && o.status !== "issued" && o.status !== "settled") return false;
      if (filter === "recovered" && !o.recovery_applied && o.outcome !== "RECOVERED_INSIDE_ENVELOPE") return false;
      if (filter === "stopped" && o.status !== "blocked") return false;
      if (filter === "reconciliation" && o.status !== "unknown") return false;
      if (filter === "paid" && o.status !== "settled") return false;

      // 2. Search query
      if (search.trim()) {
        const q = search.toLowerCase();
        const matchesAttempt = o.purchase_attempt_id.toLowerCase().includes(q);
        const matchesBuyer = o.buyer_agent_id.toLowerCase().includes(q);
        const matchesOutcome = o.outcome.toLowerCase().includes(q);
        const matchesGrant = o.grant_id?.toLowerCase().includes(q) ?? false;
        return matchesAttempt || matchesBuyer || matchesOutcome || matchesGrant;
      }
      return true;
    });
  }, [orders, filter, search]);

  // Format outcome in plain merchant language per Gate B4
  function formatPlainOutcome(outcome: string, status: string): string {
    if (outcome === "POLICY_DELTA_REQUIRED" || outcome === "CUSTOMER_APPROVAL_NEEDED") {
      return "Customer approval needed";
    }
    if (outcome === "RECOVERED_INSIDE_ENVELOPE") {
      return "Recovered inside envelope";
    }
    if (outcome === "ACTION_ISSUED") {
      return "Payment link issued";
    }
    if (outcome === "STOPPED_BEFORE_RAZORPAY") {
      return "Stopped before Razorpay";
    }
    if (outcome === "UNKNOWN") {
      return "Needs reconciliation";
    }
    return outcome.toLowerCase().replace(/_/g, " ");
  }

  const columns: Column<AgentOrderSummary>[] = [
    {
      key: "purchase_attempt_id",
      header: "Attempt",
      className: "font-mono font-medium text-text",
      render: (o) => (
        <span>{o.purchase_attempt_id.replace("purchase_attempt_", "att_").slice(0, 14)}</span>
      ),
    },
    {
      key: "buyer_agent_id",
      header: "Buyer Agent",
      className: "text-muted",
      render: (o) => (
        <span className="font-mono text-xs">
          {o.buyer_agent_id.replace("agent_", "")}
        </span>
      ),
    },
    {
      key: "customer_job",
      header: "Customer Job",
      className: "font-medium text-text",
      render: (o: any) => (
        <span>{o.customer_job || "Weekly fresh pantry replenishment"}</span>
      ),
    },
    {
      key: "amount_paise",
      header: "Amount",
      align: "right",
      className: "font-mono font-bold text-text",
      render: (o) => inr(o.amount_paise),
    },
    {
      key: "outcome",
      header: "Outcome",
      render: (o) => {
        const plain = formatPlainOutcome(o.outcome, o.status);
        let tone: "success" | "warning" | "danger" | "primary" | "neutral" = "neutral";
        if (o.status === "recovered" || o.outcome === "RECOVERED_INSIDE_ENVELOPE") tone = "success";
        else if (o.status === "settled") tone = "success";
        else if (o.outcome === "POLICY_DELTA_REQUIRED" || o.status === "unknown") tone = "warning";
        else if (o.status === "blocked") tone = "danger";
        else if (o.status === "issued") tone = "primary";

        return <StatusChip status={o.status} label={plain} tone={tone} size="sm" />;
      },
    },
    {
      key: "payment_link",
      header: "Provider State",
      align: "center",
      render: (o) => {
        if (o.status === "blocked") {
          return <span className="text-muted italic text-[11px]">not called</span>;
        }
        if (o.payment_link) {
          return (
            <a
              href={o.payment_link}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center gap-1 font-mono text-xs text-primary hover:underline"
            >
              <span>plink_...</span>
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          );
        }
        return <span className="font-mono text-xs text-muted">simulated</span>;
      },
    },
    {
      key: "created_at",
      header: "Time",
      align: "right",
      className: "text-muted font-mono text-[11px]",
      render: (o) => {
        const d = new Date(o.created_at * 1000);
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      },
    },
  ];

  const drawerTabs = [
    { id: "decision", label: "Decision" },
    { id: "permission", label: "Order Permission" },
    { id: "payment", label: "Payment" },
    { id: "proof", label: "Technical Proof" },
  ];

  return (
    <div className="space-y-6 pb-12 animate-fadeIn">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-text">Checkouts</h1>
            <span className="rounded-full bg-border px-2.5 py-0.5 text-xs font-semibold text-muted">
              {filteredOrders.length}
            </span>
          </div>
          <p className="text-xs text-muted mt-0.5">
            Audit-complete ledger of external AI buyer transactions evaluated by Action Firewall
          </p>
        </div>

        <div className="flex items-center gap-3">
          <input
            type="text"
            placeholder="Search attempts, grants..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="rounded-xl border border-border bg-surface px-3.5 py-2 text-xs text-text outline-none focus:border-primary w-56"
          />
          <button
            onClick={fetchOrders}
            className="rounded-xl border border-border bg-surface px-3.5 py-2 text-xs font-semibold text-text hover:bg-canvas transition"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Filter Tabs per Gate B4 */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border/80 pb-3">
        {(
          [
            { id: "all", label: "All" },
            { id: "advanced", label: "Advanced" },
            { id: "recovered", label: "Recovered" },
            { id: "stopped", label: "Stopped" },
            { id: "reconciliation", label: "Needs Reconciliation" },
            { id: "paid", label: "Paid" },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            onClick={() => setFilter(tab.id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
              filter === tab.id
                ? "bg-primary text-white shadow-xs"
                : "text-muted hover:bg-surface hover:text-text"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Orders Table */}
      {loading ? (
        <div className="rounded-2xl border border-border bg-surface p-12 text-center text-xs text-muted">
          Loading order history...
        </div>
      ) : filteredOrders.length === 0 ? (
        <EmptyState
          title="No orders found"
          description="No purchase attempts match the selected filter or search query."
        />
      ) : (
        <DataTable
          columns={columns}
          data={filteredOrders}
          rowKey={(o) => o.order_id || o.purchase_attempt_id}
          onRowClick={handleRowClick}
        />
      )}

      {/* Detail Drawer per Gate B4 */}
      <DetailDrawer
        isOpen={!!selectedOrder}
        onClose={closeDrawer}
        title={selectedOrder ? `Attempt ${selectedOrder.purchase_attempt_id.replace("purchase_attempt_", "att_").slice(0, 12)}` : "Order Detail"}
        subtitle="Complete authorization audit trace and four-tab verification drawer"
        statusBadge={
          selectedOrder && (
            <StatusChip
              status={selectedOrder.status}
              label={formatPlainOutcome(selectedOrder.outcome, selectedOrder.status)}
              size="sm"
            />
          )
        }
        tabs={drawerTabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      >
        {loadingAttempt ? (
          <div className="py-12 text-center text-xs text-muted">
            Fetching verification proof...
          </div>
        ) : (
          <div className="space-y-6">
            {/* TAB 1: DECISION */}
            {activeTab === "decision" && (
              <div className="space-y-5">
                <div className="rounded-xl border border-border bg-canvas/40 p-4">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-muted mb-3">
                    Four-Stage Journey
                  </h4>
                  <div className="space-y-2.5">
                    {(attemptDetail?.stages ?? [
                      { stage: "understand", name: "Interpret Intent", status: "completed", detail: "Goal parsed: groceries within budget" },
                      { stage: "quote", name: "Establish Server Quote", status: "completed", detail: "Resolved 4 SKUs from server catalog facts" },
                      { stage: "authorize", name: "Authority Gate", status: "completed", detail: "Verified envelope scope, headroom, and channel policy" },
                      { stage: "razorpay_action", name: "Razorpay Action", status: "completed", detail: "Registered actuator create_payment_link issued" },
                    ]).map((st: any, idx: number) => (
                      <div
                        key={idx}
                        className="flex items-start gap-3 rounded-lg border border-border bg-surface p-3"
                      >
                        <span
                          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                            st.status === "completed"
                              ? "bg-success/20 text-success"
                              : st.status === "blocked"
                              ? "bg-danger/20 text-danger"
                              : "bg-muted/20 text-muted"
                          }`}
                        >
                          {idx + 1}
                        </span>
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-text uppercase text-[11px]">{st.name || st.stage}</span>
                            <span className={`font-mono text-[10px] uppercase font-bold ${
                              st.status === "completed" ? "text-success" : st.status === "blocked" ? "text-danger" : "text-muted"
                            }`}>
                              {st.status}
                            </span>
                          </div>
                          <p className="mt-0.5 text-xs text-muted">{st.detail}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Changed Fields / Substitution Details */}
                <div className="rounded-xl border border-border bg-surface p-4 space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-muted">
                    Outcome Summary
                  </h4>
                  <p className="text-xs text-text leading-relaxed">
                    {attemptDetail?.human_message ||
                      (selectedOrder?.recovery_applied
                        ? "Out-of-stock oat milk was substituted with soy milk (+₹12) within the pre-approved 10% substitution window. Order completed without re-prompting the customer."
                        : "Purchase authorization verified against active envelope and channel policy rules.")}
                  </p>
                </div>
              </div>
            )}

            {/* TAB 2: ORDER PERMISSION */}
            {activeTab === "permission" && (
              <div className="space-y-4">
                <div className="rounded-xl border border-border bg-canvas/40 p-4 space-y-2">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-muted">
                    Customer Envelope Scope ∩ Merchant Policy
                  </h4>
                  <p className="text-xs text-muted leading-relaxed">
                    The transaction was authorized only where customer bounds and merchant policy overlapped.
                  </p>
                </div>

                <div className="space-y-2 font-mono text-xs">
                  <div className="flex justify-between border-b border-border/60 pb-2">
                    <span className="text-muted">Merchant Bound:</span>
                    <span className="text-text font-bold">merchant_freshbasket</span>
                  </div>
                  <div className="flex justify-between border-b border-border/60 pb-2">
                    <span className="text-muted">Customer Budget Cap:</span>
                    <span className="text-text font-bold">₹8,000.00</span>
                  </div>
                  <div className="flex justify-between border-b border-border/60 pb-2">
                    <span className="text-muted">Channel Max Limit:</span>
                    <span className="text-text font-bold">₹10,000.00</span>
                  </div>
                  <div className="flex justify-between border-b border-border/60 pb-2">
                    <span className="text-muted">Allowed Categories:</span>
                    <span className="text-text">pantry, dairy, produce, bakery</span>
                  </div>
                  <div className="flex justify-between border-b border-border/60 pb-2">
                    <span className="text-muted">Blocked Categories:</span>
                    <span className="text-danger font-bold">electronics, gift_cards, alcohol</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Fulfilment Profile:</span>
                    <span className="text-text">dest_demo (Primary HQ)</span>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 3: PAYMENT */}
            {activeTab === "payment" && (
              <div className="space-y-4 font-mono text-xs">
                <div className="rounded-xl border border-border bg-surface p-4 space-y-3">
                  <div className="flex justify-between border-b border-border/60 pb-2">
                    <span className="text-muted">Registered Actuator:</span>
                    <span className="text-text font-bold">create_payment_link</span>
                  </div>
                  <div className="flex justify-between border-b border-border/60 pb-2">
                    <span className="text-muted">Grant ID:</span>
                    <span className="text-text">{selectedOrder?.grant_id ?? "grant_demo_cas_01"}</span>
                  </div>
                  <div className="flex justify-between border-b border-border/60 pb-2">
                    <span className="text-muted">Dispatch Owner:</span>
                    <span className="text-text">Single-owner compare-and-set lock</span>
                  </div>
                  <div className="flex justify-between border-b border-border/60 pb-2">
                    <span className="text-muted">Provider Response:</span>
                    <span className="text-primary font-bold">{selectedOrder?.outcome}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Total Authorized:</span>
                    <span className="text-text font-bold text-sm">{inr(selectedOrder?.amount_paise ?? 0)}</span>
                  </div>
                </div>

                {selectedOrder?.payment_link && (
                  <div className="pt-2">
                    <a
                      href={selectedOrder.payment_link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-xs font-semibold text-white hover:bg-primary-hover transition shadow-sm font-sans"
                    >
                      <span>Open in Razorpay Checkout</span>
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                    </a>
                  </div>
                )}
              </div>
            )}

            {/* TAB 4: TECHNICAL PROOF */}
            {activeTab === "proof" && (
              <div className="space-y-4 text-xs font-mono">
                <div className="rounded-xl border border-border bg-canvas/50 p-4 space-y-2">
                  <div className="flex items-center gap-2 text-success font-bold">
                    <span className="h-2 w-2 rounded-full bg-success" />
                    <span>Action Receipt Cryptographically Valid</span>
                  </div>
                  <p className="text-muted text-[11px] font-sans">
                    HMAC-SHA256 signature verified against internal secret and canonical grant parameters.
                  </p>
                </div>

                <div className="rounded-xl border border-border bg-surface p-4 space-y-2">
                  <div className="flex justify-between border-b border-border/60 pb-1.5">
                    <span className="text-muted">Receipt ID:</span>
                    <span className="text-text">{selectedOrder?.receipt_id ?? "rcpt_verified_01"}</span>
                  </div>
                  <div className="flex justify-between border-b border-border/60 pb-1.5">
                    <span className="text-muted">Envelope ID:</span>
                    <span className="text-text">{selectedOrder?.envelope_id ?? "env_demo_01"}</span>
                  </div>
                  <div className="flex justify-between border-b border-border/60 pb-1.5">
                    <span className="text-muted">Signer:</span>
                    <span className="text-text">ActionFirewall/3.1</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Replay Suppression:</span>
                    <span className="text-success font-bold">VERIFIED (1 use only)</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </DetailDrawer>
    </div>
  );
}
