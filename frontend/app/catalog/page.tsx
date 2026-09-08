"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { api, inr, type CatalogItem, type MerchantCapabilities } from "@/lib/api";

export default function CatalogAndPolicyPage() {
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [merchant, setMerchant] = useState<MerchantCapabilities | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.agentCommerce.catalog().catch(() => []),
      api.agentCommerce.merchant().catch(() => null),
    ]).then(([cat, m]) => {
      setCatalog(cat);
      setMerchant(m);
      setLoading(false);
    });
  }, []);

  const filteredCatalog = catalog.filter((item) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      item.name.toLowerCase().includes(q) ||
      item.sku.toLowerCase().includes(q) ||
      item.category.toLowerCase().includes(q) ||
      item.tags.some((t) => t.toLowerCase().includes(q))
    );
  });

  return (
    <div className="space-y-8 pb-12">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">Catalog & AI Policy</h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
              Active Channel
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Server-owned catalog facts and dual-control semantic guardrails for external AI buyers
          </p>
        </div>

        <Link
          href="/playground"
          className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-[#0C6CF2] hover:bg-blue-600 text-white text-xs font-semibold shadow-xs transition"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span>Test in Playground</span>
        </Link>
      </div>

      {/* Semantic Guardrail Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Guardrail 1: Channel Cap */}
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Merchant AI Budget Cap</span>
            <span className="p-1.5 rounded-lg bg-blue-50 text-[#0C6CF2]">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </span>
          </div>
          <div className="mt-3 text-2xl font-bold text-slate-900 font-mono">₹1,000.00</div>
          <p className="mt-1 text-xs text-slate-500">Weekly ceiling per agent shopper session</p>
        </div>

        {/* Guardrail 2: Bound Rail */}
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Closed Registered Rail</span>
            <span className="p-1.5 rounded-lg bg-emerald-50 text-emerald-600">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </span>
          </div>
          <div className="mt-3 text-lg font-bold font-mono text-slate-900 truncate">create_payment_link</div>
          <p className="mt-1 text-xs text-slate-500">Zero capture, refund, or payout access to buyers</p>
        </div>

        {/* Guardrail 3: Catalog Revision */}
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Catalog Truth State</span>
            <span className="p-1.5 rounded-lg bg-purple-50 text-purple-600">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
              </svg>
            </span>
          </div>
          <div className="mt-3 text-lg font-bold font-mono text-slate-900">
            {merchant?.catalog_revision ?? "cat_rev_20260905"}
          </div>
          <p className="mt-1 text-xs text-slate-500">{catalog.length} verified products server-resolved</p>
        </div>
      </div>

      {/* Dual Control Authorization Matrix */}
      <section className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-2">
          Dual-Control Semantic Authorization Matrix
        </h2>
        <p className="text-xs text-slate-600 leading-relaxed mb-6 max-w-3xl">
          Effective authority is always the intersection of the merchant&apos;s AI-channel policy, the shopper&apos;s active Purchase Envelope, and current server-owned catalog facts. Neither party can unilaterally widen authority.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 rounded-xl border border-emerald-200 bg-emerald-50/50">
            <div className="flex items-center gap-2 text-xs font-bold text-emerald-900 uppercase tracking-wider">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Allowed Categories &amp; Elasticity
            </div>
            <ul className="mt-3 space-y-2 text-xs text-emerald-900">
              <li className="flex items-center gap-2">
                <span className="font-mono font-bold text-emerald-700">&#10003;</span>
                <span><strong>grocery / pasta / sauce / herbs</strong> — permitted under envelope slots</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="font-mono font-bold text-emerald-700">&#10003;</span>
                <span><strong>In-Envelope Substitutions</strong> — brand/pack replacements matching required slot tags</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="font-mono font-bold text-emerald-700">&#10003;</span>
                <span><strong>Price Elasticity</strong> — up to envelope cap (₹600.00 per purchase)</span>
              </li>
            </ul>
          </div>

          <div className="p-4 rounded-xl border border-rose-200 bg-rose-50/50">
            <div className="flex items-center gap-2 text-xs font-bold text-rose-900 uppercase tracking-wider">
              <span className="h-2 w-2 rounded-full bg-rose-500" />
              Strictly Blocked Drift (Policy Deltas Emitted)
            </div>
            <ul className="mt-3 space-y-2 text-xs text-rose-900">
              <li className="flex items-center gap-2">
                <span className="font-mono font-bold text-rose-700">&#10005;</span>
                <span><strong>Merchant Drift</strong> — attempts targeting unapproved sellers halt immediately</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="font-mono font-bold text-rose-700">&#10005;</span>
                <span><strong>Fulfillment Profile Hijacking</strong> — delivery destination mutation requires fresh approval</span>
              </li>
              <li className="flex items-center gap-2">
                <span className="font-mono font-bold text-rose-700">&#10005;</span>
                <span><strong>Blocked Categories</strong> — alcohol, tobacco, gift cards, luxury electronics</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* Verified Catalog Items Table */}
      <section className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
              Merchant Catalog ({filteredCatalog.length} Products)
            </h2>
            <p className="text-xs text-slate-500">
              Server-authoritative prices and stock facts. AI buyers cannot override these values.
            </p>
          </div>

          <div className="w-full sm:w-64">
            <input
              type="text"
              placeholder="Search catalog by name or tag..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:border-[#0C6CF2]"
            />
          </div>
        </div>

        {loading ? (
          <div className="py-12 text-center text-xs text-slate-400">Loading catalog...</div>
        ) : filteredCatalog.length === 0 ? (
          <div className="py-12 text-center text-xs text-slate-400">No products matching &quot;{search}&quot;.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-600">
              <thead className="bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-500 border-b border-slate-200">
                <tr>
                  <th className="py-3.5 px-4">SKU</th>
                  <th className="py-3.5 px-4">Product Name</th>
                  <th className="py-3.5 px-4">Category</th>
                  <th className="py-3.5 px-4">Unit Price</th>
                  <th className="py-3.5 px-4">Stock Status</th>
                  <th className="py-3.5 px-4">Eligible Tags</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-sans">
                {filteredCatalog.map((p) => (
                  <tr key={p.sku} className="hover:bg-slate-50/80 transition">
                    <td className="py-3 px-4 font-mono font-semibold text-slate-900">{p.sku}</td>
                    <td className="py-3 px-4 font-medium text-slate-800">{p.name}</td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-medium uppercase font-mono">
                        {p.category}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-mono font-bold text-slate-900">{inr(p.price_paise)}</td>
                    <td className="py-3 px-4">
                      {p.in_stock ? (
                        <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 font-medium">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                          In Stock
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] text-rose-700 font-medium">
                          <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
                          Out of Stock
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex flex-wrap gap-1">
                        {p.tags.map((t) => (
                          <span
                            key={t}
                            className="px-1.5 py-0.5 text-[10px] rounded bg-blue-50 text-[#0C6CF2] border border-blue-100 font-mono"
                          >
                            #{t}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Boundary Proof: Allowed MCP Toolset */}
      <section className="bg-slate-900 text-white rounded-2xl p-6 shadow-sm border border-slate-800">
        <div className="flex items-center justify-between mb-4">
          <div>
            <span className="text-[10px] font-mono text-blue-400 uppercase tracking-wider">
              Northbound MCP Boundary
            </span>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider mt-0.5">
              Customer-Scoped MCP Allowlist (6 Tools)
            </h3>
          </div>
          <span className="text-xs px-2.5 py-1 rounded bg-blue-950 text-blue-300 border border-blue-800 font-mono">
            Zero Raw Razorpay Tools
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
          {[
            { name: "discover_storefront", desc: "Project merchant public identity, supported currency, rails, & readiness" },
            { name: "search_catalog", desc: "Search merchant catalog by keyword or tags (server-owned verified facts)" },
            { name: "draft_purchase", desc: "Proposal-only: drafts Purchase Envelope and mints opaque approval URL" },
            { name: "request_quote", desc: "Authoritative merchant quote computation from current server facts" },
            { name: "request_checkout", desc: "Atomic headroom reservation & single-use CAS dispatch through Firewall" },
            { name: "get_checkout_status", desc: "Query purchase attempt telemetry (safe read-only, never redispatches)" },
          ].map((tool) => (
            <div key={tool.name} className="p-3 rounded-xl bg-slate-800/80 border border-slate-700">
              <div className="font-mono text-blue-300 font-bold">{tool.name}</div>
              <p className="text-[11px] text-slate-400 mt-1">{tool.desc}</p>
            </div>
          ))}
        </div>

        <p className="mt-4 text-xs text-slate-400 border-t border-slate-800 pt-3">
          Raw payment operations (e.g. <code className="text-rose-300">payment_link.create</code>, <code className="text-rose-300">capture</code>, <code className="text-rose-300">refund</code>) are protected inside the Action Firewall and can never be invoked directly by external buyer agents.
        </p>
      </section>
    </div>
  );
}
