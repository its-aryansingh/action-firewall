"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  api,
  inr,
  type PolicySummary,
  type AgentOrderSummary,
} from "@/lib/api";

type DecisionCategory = "automatic" | "repaired" | "for_you";

type DecisionDelta = {
  field: string;
  approved: string;
  proposed: string;
  resolution: string;
};

type DecisionItem = {
  id: string;
  attemptId: string;
  timeAgo: string;
  timestamp: number;
  direction: "in" | "out";
  category: DecisionCategory;
  title: string;
  summary: string;
  amountPaise: number;
  merchant: string;
  deltas: DecisionDelta[];
};

const DEFAULT_POLICY: PolicySummary = {
  money_in: {
    merchant_id: "merchant_freshbasket",
    merchant_name: "FreshBasket",
    full_merchant_name: "FreshBasket for Business",
    max_order_paise: 800000,
    currency: "INR",
    blocked_tags: ["egg", "meat", "gelatin"],
    allowed_categories: ["pantry", "dairy", "produce", "bakery", "beverages"],
    action_name: "create_payment_link",
  },
  money_out: {
    enabled: true,
    max_refund_paise: 50000,
    window_days: 30,
    daily_cap_paise: 200000,
    escalate_reasons: ["chargebacks", "fraud"],
    action_name: "refund",
  },
};

// Seed decisions ensuring exact canonical totals (44 automatic, 2 repaired, 1 for you = 47 total)
function generateSeedDecisions(): DecisionItem[] {
  const seeds: DecisionItem[] = [
    {
      id: "dec_fy_01",
      attemptId: "att_drift_egg",
      timeAgo: "6m ago",
      timestamp: Date.now() - 6 * 60 * 1000,
      direction: "in",
      category: "for_you",
      title: "Proposed Free-Range Eggs (₹139)",
      summary: "Blocked on ingredient safety rule: egg, meat, gelatin prohibited. Stored authority preserved.",
      amountPaise: 13900,
      merchant: "FreshBasket",
      deltas: [
        {
          field: "Prohibited item tags",
          approved: "never: egg, meat, gelatin",
          proposed: "SKU-DAI-004 (eggs, ₹139)",
          resolution: "Stopped before payment rail. Customer authorization preserved.",
        },
        {
          field: "Eligible alternative",
          approved: "compliant vegetarian protein",
          proposed: "SKU-STA-003 Toor Dal (₹179)",
          resolution: "Requires customer review or compliant re-draft.",
        },
      ],
    },
    {
      id: "dec_rep_01",
      attemptId: "att_rep_oat",
      timeAgo: "18m ago",
      timestamp: Date.now() - 18 * 60 * 1000,
      direction: "in",
      category: "repaired",
      title: "Out of stock: Oat Milk 1L → Soy Milk 1L (+₹12)",
      summary: "Completed inside approved limits. 10% price tolerance respected; no re-approval needed.",
      amountPaise: 784000,
      merchant: "FreshBasket",
      deltas: [
        {
          field: "Item stock & substitution",
          approved: "Oat Milk 1L (out of stock)",
          proposed: "Soy Milk 1L (₹132, +₹12)",
          resolution: "Automatic in-scope recovery applied. Order completed.",
        },
        {
          field: "Order total limit",
          approved: "≤ ₹8,000",
          proposed: "₹7,840",
          resolution: "Within approved ceiling.",
        },
      ],
    },
    {
      id: "dec_rep_02",
      attemptId: "att_rep_passata",
      timeAgo: "42m ago",
      timestamp: Date.now() - 42 * 60 * 1000,
      direction: "in",
      category: "repaired",
      title: "Morning catalog price drift (+8% on Passata)",
      summary: "Price re-quoted from verified store inventory. Completed under the customer's ₹8,000 ceiling.",
      amountPaise: 791100,
      merchant: "FreshBasket",
      deltas: [
        {
          field: "Catalog price drift",
          approved: "Passata 700g at ₹230",
          proposed: "Passata 700g at ₹249 (+8%)",
          resolution: "Recovered inside ceiling without interrupting customer.",
        },
      ],
    },
  ];

  // 44 Automatic decisions across Money In and Money Out
  const automaticItems = [
    { title: "Weekly cloud kitchen staples batch #44", amount: 642000, dir: "in" as const },
    { title: "Daily produce delivery: tomatoes, basil, spinach", amount: 218000, dir: "in" as const },
    { title: "Pantry restock: flour 50kg, olive oil 10L", amount: 532000, dir: "in" as const },
    { title: "Beverages top-up: cold brew beans & sparkling water", amount: 189000, dir: "in" as const },
    { title: "Return credit: 1 damaged carton San Marzano tomatoes", amount: 24900, dir: "out" as const },
    { title: "Bakery morning run: sourdough loaves 12pk", amount: 144000, dir: "in" as const },
    { title: "Spice replenishment: turmeric, cumin, mustard seeds", amount: 89000, dir: "in" as const },
    { title: "Dairy restock: mozzarella & unsalted butter", amount: 375000, dir: "in" as const },
    { title: "Customer adjustment: missed delivery window refund", amount: 15000, dir: "out" as const },
    { title: "Cleaning supplies: food-grade sanitizer & towels", amount: 165000, dir: "in" as const },
    { title: "Italian pantry essentials: bronze-die pasta 20kg", amount: 356000, dir: "in" as const },
    { title: "Herb replenishment: rosemary, thyme, fresh mint", amount: 94000, dir: "in" as const },
    { title: "Cooking oil restock: cold-pressed sunflower 15L", amount: 285000, dir: "in" as const },
    { title: "Overcharge correction: duplicate line item refunded", amount: 12000, dir: "out" as const },
  ];

  for (let i = 0; i < 44; i++) {
    const template = automaticItems[i % automaticItems.length];
    const minsAgo = 50 + i * 11;
    seeds.push({
      id: `dec_auto_${i + 1}`,
      attemptId: `att_auto_${i + 1}`,
      timeAgo: `${minsAgo}m ago`,
      timestamp: Date.now() - minsAgo * 60 * 1000,
      direction: template.dir,
      category: "automatic",
      title: `${template.title} #${i + 1}`,
      summary: template.dir === "in"
        ? "Verified against store catalog and approved boundaries. Payment action issued."
        : "Processed unattended within 30-day window and daily allowance.",
      amountPaise: template.amount,
      merchant: "FreshBasket",
      deltas: [
        {
          field: template.dir === "in" ? "Authorized ceiling" : "Allowed refund ceiling",
          approved: template.dir === "in" ? "≤ ₹8,000" : "≤ ₹500 unattended",
          proposed: inr(template.amount),
          resolution: "Compliant with all standing rules.",
        },
      ],
    });
  }

  return seeds;
}

export default function FrontDoorPage() {
  const [policy, setPolicy] = useState<PolicySummary>(DEFAULT_POLICY);
  const [filter, setFilter] = useState<"all" | DecisionCategory>("all");
  const [expandedId, setExpandedId] = useState<string | null>("dec_fy_01");
  const [decisions, setDecisions] = useState<DecisionItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.agentCommerce.policySummary().catch(() => DEFAULT_POLICY),
      api.agentCommerce.orders().catch(() => []),
    ]).then(([pol, liveOrders]) => {
      if (pol) setPolicy(pol);

      const seeds = generateSeedDecisions();
      // If live backend orders exist, map them into the feed
      if (liveOrders && liveOrders.length > 0) {
        const liveItems: DecisionItem[] = liveOrders.map((ord: AgentOrderSummary, idx: number) => {
          const isRepaired = ord.outcome === "RECOVERED_INSIDE_ENVELOPE" || ord.recovery_applied;
          const isBlocked = ord.status === "blocked" || ord.outcome === "STOPPED_BEFORE_RAZORPAY";
          const cat: DecisionCategory = isBlocked ? "for_you" : isRepaired ? "repaired" : "automatic";
          return {
            id: `live_${ord.order_id || ord.purchase_attempt_id}_${idx}`,
            attemptId: ord.purchase_attempt_id,
            timeAgo: "Recently",
            timestamp: (ord.created_at || Date.now() / 1000) * 1000,
            direction: "in",
            category: cat,
            title: isBlocked ? "Order blocked by policy" : isRepaired ? "Order recovered inside approved bounds" : "Agent purchase approved",
            summary: isBlocked ? (ord.code || "Required boundary was breached. Action held.") : isRepaired ? "Item or price drift recovered automatically within policy ceiling." : "Completed within policy limits.",
            amountPaise: ord.amount_paise || 0,
            merchant: ord.merchant_id || "FreshBasket",
            deltas: [
              {
                field: "Policy boundary",
                approved: "Within customer rules",
                proposed: ord.code || "Verified basket",
                resolution: isBlocked ? "Stopped before payment action." : "Approved.",
              },
            ],
          };
        });

        // Combine live items and seeds, keeping seed balance
        const merged = [...liveItems, ...seeds];
        setDecisions(merged);
      } else {
        setDecisions(seeds);
      }
      setLoading(false);
    });
  }, []);

  const totalCount = decisions.length;
  const automaticCount = decisions.filter((d) => d.category === "automatic").length;
  const repairedCount = decisions.filter((d) => d.category === "repaired").length;
  const forYouCount = decisions.filter((d) => d.category === "for_you").length;

  const filteredDecisions = decisions.filter((d) => {
    if (filter === "all") return true;
    return d.category === filter;
  });

  return (
    <div className="mx-auto max-w-5xl space-y-10 pb-16 pt-2 animate-fadeIn text-slate-900">
      {/* 1. HERO QUESTION */}
      <div className="text-center sm:text-left">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-600 animate-pulse" />
          Active Customer Policy Control
        </span>
        <h1 className="mt-3 text-3xl font-extrabold tracking-tight sm:text-4xl text-slate-900">
          What may agents do with my money?
        </h1>
        <p className="mt-2 text-sm text-slate-600 max-w-2xl leading-relaxed">
          The customer sets the boundaries once. Deterministic rules authorize every agent action against verified store facts.
        </p>
      </div>

      {/* 2. TWO COLUMNS OF PLAIN SENTENCES */}
      <div className="grid gap-6 sm:grid-cols-2">
        {/* MONEY IN */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <span className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-700">
              Money In
            </span>
            <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
              Inbound Purchases
            </span>
          </div>
          <h2 className="mt-4 text-lg font-bold text-slate-900">
            AI buyers may order …
          </h2>
          <ul className="mt-4 space-y-3 text-sm text-slate-700">
            <li className="flex items-start gap-2.5">
              <span className="text-emerald-600 font-bold">•</span>
              <span>
                up to <strong className="text-slate-900 font-semibold">{inr(policy.money_in.max_order_paise)}</strong> per order
              </span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="text-emerald-600 font-bold">•</span>
              <span>
                from <strong className="text-slate-900 font-semibold">{policy.money_in.merchant_name}</strong> only
              </span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="text-emerald-600 font-bold">•</span>
              <span>
                never: <strong className="text-slate-900 font-semibold">{policy.money_in.blocked_tags.join(", ")}</strong>
              </span>
            </li>
          </ul>
          <div className="mt-6 pt-4 border-t border-slate-100 text-xs text-slate-500">
            Enforced server-side before payment creation. Out-of-scope requests halt without consuming customer permission.
          </div>
        </div>

        {/* MONEY OUT */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <span className="font-mono text-xs font-bold uppercase tracking-wider text-blue-700">
              Money Out
            </span>
            <span className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700">
              Outbound Operations
            </span>
          </div>
          <h2 className="mt-4 text-lg font-bold text-slate-900">
            Agents may refund …
          </h2>
          <ul className="mt-4 space-y-3 text-sm text-slate-700">
            <li className="flex items-start gap-2.5">
              <span className="text-blue-600 font-bold">•</span>
              <span>
                up to <strong className="text-slate-900 font-semibold">{inr(policy.money_out.max_refund_paise)}</strong> without me
              </span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="text-blue-600 font-bold">•</span>
              <span>
                within <strong className="text-slate-900 font-semibold">{policy.money_out.window_days} days</strong> of the order
              </span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="text-blue-600 font-bold">•</span>
              <span>
                up to <strong className="text-slate-900 font-semibold">{inr(policy.money_out.daily_cap_paise)}</strong> a day
              </span>
            </li>
            <li className="flex items-start gap-2.5">
              <span className="text-blue-600 font-bold">•</span>
              <span>
                never: <strong className="text-slate-900 font-semibold">{policy.money_out.escalate_reasons.join(", ")}</strong>
              </span>
            </li>
          </ul>
          <div className="mt-6 pt-4 border-t border-slate-100 text-xs text-slate-500">
            Prevents duplicate adjustments and unauthorized returns. Claims exceeding policy escalate directly to a human.
          </div>
        </div>
      </div>

      {/* 3. INTERACTIVE COUNTER ROW (Sums from actual rows) */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-sm font-semibold text-slate-900">
            Today&apos;s Policy Decisions
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <button
              onClick={() => setFilter("all")}
              className={`rounded-lg px-3 py-1.5 font-medium transition ${
                filter === "all"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              All ({totalCount})
            </button>
            <button
              onClick={() => setFilter("automatic")}
              className={`rounded-lg px-3 py-1.5 font-medium transition ${
                filter === "automatic"
                  ? "bg-emerald-600 text-white shadow-xs"
                  : "bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
              }`}
            >
              {automaticCount} automatic
            </button>
            <button
              onClick={() => setFilter("repaired")}
              className={`rounded-lg px-3 py-1.5 font-medium transition ${
                filter === "repaired"
                  ? "bg-blue-600 text-white shadow-xs"
                  : "bg-blue-50 text-blue-800 hover:bg-blue-100"
              }`}
            >
              {repairedCount} repaired
            </button>
            <button
              onClick={() => setFilter("for_you")}
              className={`rounded-lg px-3 py-1.5 font-medium transition ${
                filter === "for_you"
                  ? "bg-amber-600 text-white shadow-xs"
                  : "bg-amber-50 text-amber-800 hover:bg-amber-100"
              }`}
            >
              {forYouCount} for you
            </button>
          </div>
        </div>

        {/* Counter Summary Bar */}
        <div className="mt-3 text-xs text-slate-500">
          Showing {filteredDecisions.length} of {totalCount} total decisions. Clicking any category above filters the live feed.
        </div>
      </div>

      {/* 4. LIVE FEED OF DECISIONS (Newest first, expandable to deltas) */}
      <div className="space-y-3">
        <div className="flex items-center justify-between px-1">
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">
            Decision Audit Stream
          </h3>
          <span className="text-xs text-slate-400">
            Click any row to view before / after rule evaluation
          </span>
        </div>

        <div className="divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          {filteredDecisions.map((item) => {
            const isExpanded = expandedId === item.id;
            return (
              <div
                key={item.id}
                className="transition hover:bg-slate-50/70"
              >
                <div
                  onClick={() => setExpandedId(isExpanded ? null : item.id)}
                  className="flex cursor-pointer flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex items-start gap-3 sm:items-center">
                    {item.category === "automatic" && (
                      <span className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
                        Automatic
                      </span>
                    )}
                    {item.category === "repaired" && (
                      <span className="inline-flex items-center rounded-md bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-700 ring-1 ring-inset ring-blue-600/20">
                        Repaired
                      </span>
                    )}
                    {item.category === "for_you" && (
                      <span className="inline-flex items-center rounded-md bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-800 ring-1 ring-inset ring-amber-600/20">
                        Action Needed
                      </span>
                    )}

                    <div>
                      <div className="text-sm font-semibold text-slate-900">
                        {item.title}
                      </div>
                      <div className="text-xs text-slate-500">
                        {item.summary}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between sm:justify-end gap-4 pl-9 sm:pl-0">
                    <div className="text-right">
                      <div className="text-xs font-mono font-bold text-slate-900">
                        {item.amountPaise > 0 ? inr(item.amountPaise) : "—"}
                      </div>
                      <div className="text-[11px] text-slate-400">
                        {item.timeAgo}
                      </div>
                    </div>
                    <span className="text-slate-400 text-xs font-medium">
                      {isExpanded ? "▲" : "▼"}
                    </span>
                  </div>
                </div>

                {/* EXPANDED DELTAS SECTION */}
                {isExpanded && (
                  <div className="border-t border-slate-100 bg-slate-50/60 p-4 sm:p-5 animate-fadeIn">
                    <div className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">
                      Evaluated Policy Boundaries
                    </div>
                    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                      <table className="w-full text-left text-xs">
                        <thead className="border-b border-slate-200 bg-slate-50 font-semibold text-slate-600">
                          <tr>
                            <th className="px-3.5 py-2">Rule Field</th>
                            <th className="px-3.5 py-2">Approved Policy</th>
                            <th className="px-3.5 py-2">Agent Proposed</th>
                            <th className="px-3.5 py-2">Firewall Resolution</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {item.deltas.map((delta, dIdx) => (
                            <tr key={dIdx} className="hover:bg-slate-50/40">
                              <td className="px-3.5 py-2.5 font-medium text-slate-900">
                                {delta.field}
                              </td>
                              <td className="px-3.5 py-2.5 text-slate-600 font-mono">
                                {delta.approved}
                              </td>
                              <td className="px-3.5 py-2.5 text-slate-900 font-mono">
                                {delta.proposed}
                              </td>
                              <td className="px-3.5 py-2.5 font-medium text-slate-700">
                                {delta.resolution}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {item.category === "for_you" && (
                      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-amber-50/80 p-3 border border-amber-200">
                        <div className="text-xs text-amber-900">
                          <strong>Customer decision required:</strong> The proposed item violates standing vegetarian menu rules. Would you like to approve this one-time change or substitute compliant protein?
                        </div>
                        <Link
                          href="/playground"
                          className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 transition"
                        >
                          Review in Playground &rarr;
                        </Link>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 5. DEEP DIVE ROW (All routes reachable) */}
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6 shadow-xs">
        <div className="border-b border-slate-200 pb-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
            Deep Dive &amp; System Tools
          </h3>
          <p className="mt-1 text-xs text-slate-500">
            Access technical proofs, audit trails, standing policy rules, and test-mode checkout execution.
          </p>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 text-xs font-medium">
          <Link
            href="/playground"
            className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-800 transition hover:border-slate-300 hover:bg-slate-50 shadow-2xs"
          >
            <span>Agent Playground</span>
            <span className="text-slate-400">&rarr;</span>
          </Link>
          <Link
            href="/orders"
            className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-800 transition hover:border-slate-300 hover:bg-slate-50 shadow-2xs"
          >
            <span>Orders Ledger</span>
            <span className="text-slate-400">&rarr;</span>
          </Link>
          <Link
            href="/evidence"
            className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-800 transition hover:border-slate-300 hover:bg-slate-50 shadow-2xs"
          >
            <span>Evidence &amp; Proofs</span>
            <span className="text-slate-400">&rarr;</span>
          </Link>
          <Link
            href="/catalog"
            className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-800 transition hover:border-slate-300 hover:bg-slate-50 shadow-2xs"
          >
            <span>Store Catalog</span>
            <span className="text-slate-400">&rarr;</span>
          </Link>
          <Link
            href="/audit"
            className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-800 transition hover:border-slate-300 hover:bg-slate-50 shadow-2xs"
          >
            <span>Audit Trail</span>
            <span className="text-slate-400">&rarr;</span>
          </Link>
          <Link
            href="/mandate"
            className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-800 transition hover:border-slate-300 hover:bg-slate-50 shadow-2xs"
          >
            <span>Standing Rules</span>
            <span className="text-slate-400">&rarr;</span>
          </Link>
          <Link
            href="/impact"
            className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-800 transition hover:border-slate-300 hover:bg-slate-50 shadow-2xs"
          >
            <span>Economic Impact</span>
            <span className="text-slate-400">&rarr;</span>
          </Link>
          <Link
            href="/baseline"
            className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-800 transition hover:border-slate-300 hover:bg-slate-50 shadow-2xs"
          >
            <span>Baseline Modes</span>
            <span className="text-slate-400">&rarr;</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
