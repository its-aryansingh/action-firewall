"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api, type ComprehensiveMetrics, type MerchantCapabilities } from "@/lib/api";

interface MerchantShellProps {
  children: React.ReactNode;
}

/**
 * What rail is actually dispatching, said plainly.
 *
 * The previous version compared `evidence_mode` against `"test_mode"` — a value
 * the backend never emits — so the badge read "Simulated Razorpay MCP" in every
 * configuration, including one creating real Razorpay payment links. Two bugs
 * stacked: the metric was derived from DEMO_MODE rather than from the provider,
 * and the comparison could never be true. A badge that cannot be wrong-looking
 * is not reassuring; it is just not reporting anything.
 *
 * Unknown values fall through to the raw string rather than a comforting
 * default, because guessing here is how the original bug read to a viewer.
 */
function providerBadge(mode: string | undefined): { label: string; className: string } {
  const LIVE = "bg-amber-50 text-[#9A5B00] border border-amber-200";
  const SIM = "bg-blue-50 text-[#2B6EF3] border border-blue-200";
  const UNKNOWN = "bg-slate-50 text-slate-500 border border-slate-200";
  switch (mode) {
    case "simulated":
      return { label: "Simulated Razorpay MCP", className: SIM };
    case "razorpay_mcp":
      return { label: "Live Razorpay MCP", className: LIVE };
    case "razorpay_rest":
      return { label: "Live Razorpay REST", className: LIVE };
    case undefined:
      return { label: "Payment rail…", className: UNKNOWN };
    default:
      return { label: `Payment rail: ${mode}`, className: UNKNOWN };
  }
}

export function MerchantShell({ children }: MerchantShellProps) {
  const pathname = usePathname();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [metrics, setMetrics] = useState<ComprehensiveMetrics | null>(null);
  const [merchant, setMerchant] = useState<MerchantCapabilities | null>(null);

  useEffect(() => {
    api.agentCommerce
      .merchant()
      .then(setMerchant)
      .catch((err) => console.warn("Could not load merchant capabilities", err));
    api.agentCommerce
      .metrics()
      .then(setMetrics)
      .catch((err) => console.warn("Could not load metrics", err));
  }, []);

  const isBaseline = pathname.startsWith("/baseline");

  // Exactly three primary routes in navigation per Gate B2
  const navItems = [
    {
      label: "Agent Commerce",
      href: "/",
      icon: (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
        </svg>
      ),
      active: pathname === "/",
    },
    {
      label: "Checkouts",
      href: "/orders",
      icon: (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
        </svg>
      ),
      badge: metrics?.agent_orders_count,
      active: pathname === "/orders",
    },
    {
      label: "Evidence",
      href: "/evidence",
      icon: (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      ),
      active: pathname === "/evidence" || pathname === "/audit",
    },
  ];

  return (
    <div className="min-h-screen bg-[#F7F8FC] text-[#192233] flex flex-col antialiased">
      <div className="flex flex-1">
        {/* Dark Navy Sidebar (#0B1020) */}
        <aside
          className={`fixed inset-y-0 left-0 z-40 w-64 bg-[#0B1020] text-white flex flex-col transition-transform duration-200 ease-in-out lg:static lg:translate-x-0 ${
            sidebarOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          {/* Logo / Header */}
          <div className="h-16 px-5 border-b border-[#1E293B] flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2.5">
              <div className="h-8 w-8 rounded-lg bg-[#2B6EF3] flex items-center justify-center font-bold text-white shadow-sm">
                AF
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-semibold tracking-tight text-white">Action Firewall</span>
                <span className="text-[10px] font-medium tracking-wide text-blue-400">Agent Commerce Gateway</span>
              </div>
            </Link>
            <button
              onClick={() => setSidebarOpen(false)}
              className="lg:hidden text-slate-400 hover:text-white p-1"
              aria-label="Close sidebar"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Three Nav Items Only */}
          <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
            <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Control Plane
            </div>
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-medium transition-colors ${
                  item.active
                    ? "bg-[#2B6EF3] text-white font-semibold shadow-sm"
                    : "text-slate-300 hover:bg-[#13233F] hover:text-white"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <span className={item.active ? "text-white" : "text-slate-400"}>{item.icon}</span>
                  <span>{item.label}</span>
                </div>
                {item.badge !== undefined && item.badge > 0 && (
                  <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-slate-800 text-slate-200">
                    {item.badge}
                  </span>
                )}
              </Link>
            ))}

            {/* Regression Reference Link */}
            <div className="pt-8 px-3 pb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Reference
            </div>
            <Link
              href="/baseline"
              onClick={() => setSidebarOpen(false)}
              className={`flex items-center gap-2.5 px-3.5 py-2 rounded-xl text-xs font-medium transition-colors ${
                isBaseline
                  ? "bg-[#2B6EF3] text-white font-semibold shadow-sm"
                  : "text-slate-400 hover:bg-[#13233F] hover:text-slate-200"
              }`}
            >
              <svg className="h-4 w-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Exact-Cart Baseline</span>
            </Link>
          </nav>

          {/* Merchant Profile Footer */}
          <div className="p-3 border-t border-[#1E293B] bg-[#070D18]">
            <div className="flex items-center gap-2.5 px-2 py-1.5">
              <div className="h-8 w-8 rounded-full bg-emerald-950 border border-emerald-600 flex items-center justify-center text-xs font-bold text-emerald-400">
                FB
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-xs font-semibold text-white truncate">
                  {merchant?.display_name ?? "FreshBasket for Business"}
                </span>
                <span className="text-[10px] font-mono text-slate-400 truncate">
                  {merchant?.merchant_id ?? "merchant_freshbasket"}
                </span>
              </div>
            </div>
          </div>
        </aside>

        {/* Mobile backdrop */}
        {sidebarOpen && (
          <div
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm lg:hidden"
          />
        )}

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col min-w-0 bg-[#F7F8FC]">
          {/* Operations Top Bar */}
          <header className="h-16 px-4 sm:px-6 bg-white border-b border-[#E5E9F0] flex items-center justify-between sticky top-0 z-20 shadow-sm">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(true)}
                className="lg:hidden text-slate-600 hover:text-slate-900 p-1.5 rounded-lg border border-border"
                aria-label="Open sidebar"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-emerald-50 text-[#138A5B] border border-emerald-200">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#138A5B] animate-pulse" />
                  Ready for AI Buyers
                </span>
                <span className={`hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium ${providerBadge(metrics?.evidence_mode).className}`}>
                  <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
                  </svg>
                  {providerBadge(metrics?.evidence_mode).label}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <Link
                href="/playground"
                className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-[#2B6EF3] hover:bg-[#1F5ED8] rounded-xl shadow-sm transition"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <span>Run a protected agent checkout</span>
              </Link>
            </div>
          </header>

          {/* Page Viewport */}
          <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}
