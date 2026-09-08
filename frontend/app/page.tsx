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

export default function MerchantOverviewPage() {
  const [metrics, setMetrics] = useState<ComprehensiveMetrics | null>(null);
  const [merchant, setMerchant] = useState<MerchantCapabilities | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<AgentOrderSummary | null>(null);
  const [selectedAttemptDetail, setSelectedAttemptDetail] = useState<CommerceAttemptResponse | null>(null);
  const [loadingAttempt, setLoadingAttempt] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.agentCommerce.merchant().catch(() => null),
      api.agentCommerce.metrics().catch(() => null),
    ]).then(([m, met]) => {
      setMerchant(m);
      setMetrics(met);
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

  return (
    <div className="space-y-8 pb-12">
      {/* 1. FIRST GLANCE VALUE CARD — THE SEMANTIC CONTRAST */}
      <section className="bg-white border border-slate-200 rounded-2xl p-6 sm:p-8 shadow-sm">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-blue-50 text-[#0C6CF2] border border-blue-100 mb-3">
              <span>Track 01</span>
              <span>·</span>
              <span>AI Commerce Permissions</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 leading-tight">
              Razorpay MCP makes payment operations callable.
              <br />
              <span className="text-[#0C6CF2]">Action Firewall makes one checkout customer-authorizable.</span>
            </h1>
            <p className="mt-3 text-sm text-slate-600 leading-relaxed">
              Amount-only payment requests cannot verify whether an AI buyer bought groceries or alcohol, substituted brands, accepted price spikes, changed delivery addresses, or retried blindly on timeout. Action Firewall bounds exact merchant, catalog, category, price, substitution, and action parameters before Razorpay executes.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row lg:flex-col gap-3 shrink-0">
            <Link
              href="/playground"
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-[#0C6CF2] hover:bg-blue-600 text-white text-sm font-semibold shadow-sm transition"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <span>Run a protected agent checkout</span>
            </Link>
            <Link
              href="/orders"
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold transition"
            >
              <span>View all agent orders &rarr;</span>
            </Link>
          </div>
        </div>

        {/* Amount-only vs Semantic Authority Contrast Box */}
        <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-4 pt-6 border-t border-slate-100">
          <div className="p-4 rounded-xl bg-rose-50/50 border border-rose-100">
            <div className="flex items-center gap-2 text-xs font-semibold text-rose-800 uppercase tracking-wider">
              <svg className="h-4 w-4 text-rose-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              Standard Amount-Only Request
            </div>
            <p className="mt-2 text-xs text-rose-900/80 leading-relaxed">
              Authorizes an arbitrary ₹8,000 spend. Cannot detect if the model bought the wrong items, substituted luxury brands, changed the shipping destination, or charged twice after an ambiguous network timeout.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-blue-50/60 border border-blue-100">
            <div className="flex items-center gap-2 text-xs font-semibold text-blue-800 uppercase tracking-wider">
              <svg className="h-4 w-4 text-[#0C6CF2]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              Action Firewall Purchase Envelope
            </div>
            <p className="mt-2 text-xs text-blue-900/80 leading-relaxed">
              Binds exact merchant, catalog, allowed categories, price ceiling, and delivery profile. Permits safe stock substitutions inside authority while halting drift before actuator invocation.
            </p>
          </div>
        </div>
      </section>

      {/* 2. STORE READINESS & AI CHANNEL STRIP */}
      <section className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="h-10 w-10 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-slate-900">{merchant?.display_name ?? "FreshBasket for Business"}</span>
              <span className="text-[11px] font-mono text-slate-500">({merchant?.merchant_id ?? "merchant_freshbasket"})</span>
              <span className="px-2 py-0.5 text-[10px] font-semibold rounded bg-emerald-100 text-emerald-800">
                {metrics?.store_readiness ?? "READY_FOR_AI_BUYERS"}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Catalog Revision: <code className="font-mono text-slate-700">{merchant?.catalog_revision ?? "cat_rev_20260905"}</code> · Registered Rail: <code className="font-mono text-slate-700">create_payment_link</code>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/catalog"
            className="text-xs font-semibold text-slate-700 hover:text-slate-900 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 transition"
          >
            Manage AI Catalog &rarr;
          </Link>
          <Link
            href="/audit"
            className="text-xs font-semibold text-slate-700 hover:text-slate-900 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 transition"
          >
            Audit Log &rarr;
          </Link>
        </div>
      </section>

      {/* 3. CORE 4 KPIS */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Agent GMV Issued */}
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Agent GMV Issued</span>
            <span className="p-1.5 rounded-lg bg-blue-50 text-[#0C6CF2]">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 font-mono">
              {inr(metrics?.agent_gmv_issued_paise ?? 0)}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Across {metrics?.agent_orders_count ?? 0} agent purchase attempts
          </p>
        </div>

        {/* KPI 2: Settled GMV (Strict Separation) */}
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Settled GMV</span>
            <span className="p-1.5 rounded-lg bg-emerald-50 text-emerald-600">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 font-mono">
              {inr(metrics?.settled_agent_gmv_paise ?? 0)}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            Truthful provider proof required for settlement
          </p>
        </div>

        {/* KPI 3: Orders Recovered */}
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Orders Recovered</span>
            <span className="p-1.5 rounded-lg bg-emerald-50 text-emerald-600">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl sm:text-3xl font-bold tracking-tight text-emerald-600 font-mono">
              {metrics?.orders_recovered_count ?? 0}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Stock drift repaired inside customer envelope
          </p>
        </div>

        {/* KPI 4: Unsafe Attempts Blocked */}
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Drift Blocked</span>
            <span className="p-1.5 rounded-lg bg-amber-50 text-amber-600">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
              </svg>
            </span>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl sm:text-3xl font-bold tracking-tight text-amber-600 font-mono">
              {metrics?.unsafe_attempts_blocked_count ?? 0}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Stopped before actuator; Policy Delta emitted
          </p>
        </div>
      </section>

      {/* 4. CHECKOUT FUNNEL & ATTENTION ROW */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Checkout Funnel */}
        <section className="lg:col-span-2 bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">Agent Checkout Funnel</h2>
              <p className="text-xs text-slate-500">Strict stage progression from natural language intent to settled funds</p>
            </div>
            <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600">
              Live Conversions
            </span>
          </div>

          <div className="space-y-4">
            {(metrics?.funnel ?? []).map((step, idx) => {
              const pct = Math.round(step.conversion_rate * 100);
              return (
                <div key={step.stage} className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-slate-700 flex items-center gap-2">
                      <span className="flex h-5 w-5 rounded-full bg-slate-100 text-slate-600 text-[10px] items-center justify-center font-bold">
                        {idx + 1}
                      </span>
                      {step.stage}
                    </span>
                    <div className="flex items-center gap-3 font-mono">
                      <span className="text-slate-900 font-bold">{step.count}</span>
                      <span className="text-slate-400 text-[11px]">({pct}%)</span>
                    </div>
                  </div>
                  <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        idx === 4
                          ? "bg-emerald-500"
                          : idx === 3
                          ? "bg-[#0C6CF2]"
                          : "bg-blue-400"
                      }`}
                      style={{ width: `${Math.max(4, pct)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <span>Proposal-only at Intent</span>
            <span>Customer authority gate at Approval</span>
            <span>Single CAS owner at Issuance</span>
          </div>
        </section>

        {/* Needs Attention Section */}
        <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">Needs Attention</h2>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                (metrics?.needs_attention?.length ?? 0) > 0
                  ? "bg-amber-100 text-amber-800"
                  : "bg-slate-100 text-slate-600"
              }`}>
                {metrics?.needs_attention?.length ?? 0} Items
              </span>
            </div>

            {(!metrics?.needs_attention || metrics.needs_attention.length === 0) ? (
              <div className="py-8 text-center text-slate-400 text-xs">
                <svg className="h-8 w-8 mx-auto text-slate-300 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Zero urgent items. All agent checkouts operating safely within bounds.
              </div>
            ) : (
              <div className="space-y-3">
                {metrics.needs_attention.map((item) => (
                  <div
                    key={item.item_id}
                    className={`p-3 rounded-xl border text-xs ${
                      item.severity === "high"
                        ? "bg-purple-50/70 border-purple-200 text-purple-900"
                        : "bg-amber-50/70 border-amber-200 text-amber-900"
                    }`}
                  >
                    <div className="font-semibold flex items-center justify-between">
                      <span>{item.title}</span>
                      <span className="font-mono text-[10px] uppercase font-bold">{item.severity}</span>
                    </div>
                    <p className="mt-1 text-[11px] opacity-90">{item.detail}</p>
                    <div className="mt-2 text-[10px] font-medium font-mono text-slate-600 bg-white/70 px-2 py-1 rounded">
                      Action: {item.action_required}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 text-[11px] text-slate-400">
            Timeout outcomes hold reserved exposure until provider reconciliation.
          </div>
        </section>
      </div>

      {/* 5. RECENT AGENT ORDERS */}
      <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">Recent Agent Orders</h2>
            <p className="text-xs text-slate-500">Autonomous transactions executed through Action Firewall</p>
          </div>
          <Link
            href="/orders"
            className="text-xs font-semibold text-[#0C6CF2] hover:underline"
          >
            View all orders &rarr;
          </Link>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-600">
            <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-500 border-y border-slate-200">
              <tr>
                <th className="py-3 px-4">Attempt ID</th>
                <th className="py-3 px-4">Buyer Agent</th>
                <th className="py-3 px-4">Amount</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Outcome</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-sans">
              {(metrics?.recent_orders ?? []).map((order) => {
                const isIssued = order.status === "issued";
                const isRecovered = order.outcome === "RECOVERED_INSIDE_ENVELOPE" || order.recovery_applied;
                const isBlocked = order.status === "blocked";
                const isUnknown = order.status === "unknown";

                return (
                  <tr key={order.order_id} className="hover:bg-slate-50/80 transition">
                    <td className="py-3 px-4 font-mono font-medium text-slate-900">
                      {order.purchase_attempt_id}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-600">
                      {order.buyer_agent_id}
                    </td>
                    <td className="py-3 px-4 font-mono font-semibold text-slate-900">
                      {inr(order.amount_paise)}
                    </td>
                    <td className="py-3 px-4">
                      {isRecovered ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          Recovered
                        </span>
                      ) : isIssued ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-[#0C6CF2] border border-blue-200">
                          Action Issued
                        </span>
                      ) : isBlocked ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                          Blocked
                        </span>
                      ) : isUnknown ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
                          Unknown
                        </span>
                      ) : (
                        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600">
                          {order.status}
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-600">
                      {order.outcome}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => openOrderDetail(order)}
                        className="text-xs font-semibold text-[#0C6CF2] hover:text-blue-700 hover:underline"
                      >
                        Inspect &rarr;
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* 6. SLIDE-OVER ORDER DETAIL DRAWER */}
      {selectedOrder && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-black/40 backdrop-blur-xs flex justify-end">
          <div className="w-full max-w-lg bg-white h-full shadow-2xl flex flex-col overflow-y-auto border-l border-slate-200 animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="p-6 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div>
                <span className="text-xs font-mono uppercase text-slate-500 tracking-wider">Order Details</span>
                <h3 className="text-lg font-bold text-slate-900 font-mono mt-0.5">
                  {selectedOrder.purchase_attempt_id}
                </h3>
              </div>
              <button
                onClick={closeDrawer}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Drawer Body */}
            <div className="p-6 space-y-6 flex-1">
              {/* Summary Pill */}
              <div className="flex items-center justify-between p-4 rounded-xl bg-slate-50 border border-slate-200">
                <div>
                  <div className="text-[11px] text-slate-500 uppercase tracking-wider">Order Value</div>
                  <div className="text-xl font-bold font-mono text-slate-900">{inr(selectedOrder.amount_paise)}</div>
                </div>
                <div className="text-right">
                  <div className="text-[11px] text-slate-500 uppercase tracking-wider">Outcome</div>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded bg-blue-100 text-blue-800">
                    {selectedOrder.outcome}
                  </span>
                </div>
              </div>

              {/* 4-Stage Lifecycle Breakdown */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
                  Lifecycle Execution Stages
                </h4>
                {loadingAttempt ? (
                  <div className="py-6 text-center text-xs text-slate-400">Loading attempt stages...</div>
                ) : selectedAttemptDetail?.stages ? (
                  <div className="space-y-2">
                    {selectedAttemptDetail.stages.map((st, i) => (
                      <div
                        key={st.stage}
                        className={`p-3 rounded-xl border flex items-start gap-3 ${
                          st.status === "completed"
                            ? "bg-emerald-50/50 border-emerald-200"
                            : st.status === "blocked"
                            ? "bg-amber-50/50 border-amber-200"
                            : "bg-slate-50 border-slate-200"
                        }`}
                      >
                        <div className={`mt-0.5 flex h-5 w-5 rounded-full text-[10px] font-bold items-center justify-center shrink-0 ${
                          st.status === "completed" ? "bg-emerald-500 text-white" : "bg-amber-500 text-white"
                        }`}>
                          {i + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-slate-900">{st.name}</span>
                            <span className="text-[10px] font-mono uppercase font-bold text-slate-500">{st.status}</span>
                          </div>
                          <p className="text-[11px] text-slate-600 mt-0.5">{st.detail}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">Detailed stage telemetry recorded in SQLite spend ledger.</p>
                )}
              </div>

              {/* Action Link / Grant Information */}
              <div className="space-y-3 pt-4 border-t border-slate-100">
                {selectedOrder.payment_link && (
                  <div>
                    <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                      Issued Razorpay Payment Link
                    </label>
                    <div className="mt-1 flex items-center gap-2">
                      <input
                        type="text"
                        readOnly
                        value={selectedOrder.payment_link}
                        className="w-full text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg p-2 text-slate-800"
                      />
                      <a
                        href={selectedOrder.payment_link}
                        target="_blank"
                        rel="noreferrer"
                        className="px-3 py-2 text-xs font-semibold bg-[#0C6CF2] text-white rounded-lg hover:bg-blue-600 shrink-0"
                      >
                        Open
                      </a>
                    </div>
                  </div>
                )}

                {selectedOrder.grant_id && (
                  <div>
                    <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                      Action Grant ID (One-Time Execution Token)
                    </label>
                    <div className="mt-1 font-mono text-xs text-slate-700 bg-slate-50 p-2 rounded-lg border border-slate-200">
                      {selectedOrder.grant_id}
                    </div>
                  </div>
                )}

                {selectedOrder.receipt_id && (
                  <div>
                    <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                      Dual-Signature Receipt ID
                    </label>
                    <div className="mt-1 font-mono text-xs text-emerald-700 bg-emerald-50/50 p-2 rounded-lg border border-emerald-200 flex items-center justify-between">
                      <span className="truncate">{selectedOrder.receipt_id}</span>
                      <span className="text-[10px] font-bold uppercase bg-emerald-200 text-emerald-900 px-1.5 py-0.5 rounded shrink-0">
                        Verified
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Drawer Footer */}
            <div className="p-4 bg-slate-50 border-t border-slate-200 flex items-center justify-end">
              <button
                onClick={closeDrawer}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-900 bg-white border border-slate-300 rounded-lg shadow-xs"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
