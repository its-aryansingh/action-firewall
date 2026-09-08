"use client";

import Link from "next/link";
import { WorkflowComparison } from "@/components/impact/WorkflowComparison";

export default function MerchantImpactPage() {
  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Hero */}
      <section className="hero-shell">
        <div className="relative">
          <span className="status-pill border-primary/40 bg-primary/10 text-primary font-semibold">
            Merchant Value
          </span>

          <h1 className="mt-4 text-3xl font-bold tracking-tight text-text sm:text-5xl max-w-3xl leading-[1.1]">
            Keep agent-built checkouts alive{" "}
            <span className="text-primary">when the cart changes.</span>
          </h1>

          <p className="mt-3.5 max-w-2xl text-sm leading-relaxed text-muted sm:text-base">
            Exact-cart approvals break as soon as an item goes out of stock. Safe Autopilot obtains one approval for the shopping outcome and recovers inside approved bounds without dropping the customer back into the cart.
          </p>
        </div>
      </section>

      {/* Continuity Evidence Comparison */}
      <section className="space-y-4">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight">
            Modeled Checkout Continuity
          </h2>
          <p className="text-xs text-muted mt-0.5">
            2× modeled checkout continuity demonstrated in controlled catalog inventory benchmarks.
          </p>
        </div>

        <WorkflowComparison />
      </section>

      {/* Architecture & Integration Flow */}
      <section className="card space-y-6 border-edge/80 bg-panel/70 p-6 sm:p-8">
        <div>
          <span className="label">Integration Architecture</span>
          <h2 className="mt-1 text-xl font-bold text-white tracking-tight">
            How Safe Autopilot fits into Razorpay Commerce
          </h2>
          <p className="mt-1 text-xs text-muted">
            Safe Autopilot sits between conversational AI planners and Razorpay actuators, establishing the deterministic authorization boundary.
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-3 font-mono text-xs">
          <div className="rounded-2xl border border-border bg-surface p-5 space-y-2">
            <span className="text-primary font-bold text-[10px] uppercase tracking-wider">Step 1 · Ingestion</span>
            <h3 className="font-semibold text-text text-sm">Merchant Catalog</h3>
            <p className="text-xs text-muted leading-relaxed font-sans">
              Trusted SKUs, fixed integer-paise pricing, and real-time inventory provided directly from the merchant database.
            </p>
          </div>

          <div className="rounded-2xl border border-primary/40 bg-primary/[0.04] p-5 space-y-2">
            <span className="text-primary font-bold text-[10px] uppercase tracking-wider">Step 2 · Action Firewall</span>
            <h3 className="font-semibold text-text text-sm">Safe Autopilot Engine</h3>
            <p className="text-xs text-muted leading-relaxed font-sans">
              Bounded Purchase Envelope, one explicit human approval, stock-loss substitution, and atomic headroom reservation under SQLite.
            </p>
          </div>

          <div className="rounded-2xl border border-border bg-surface p-5 space-y-2">
            <span className="text-success font-bold text-[10px] uppercase tracking-wider">Step 3 · Actuation</span>
            <h3 className="font-semibold text-text text-sm">Razorpay Checkout</h3>
            <p className="text-xs text-muted leading-relaxed font-sans">
              One exact registered payment link action executed with cryptographic Action Receipt proof. Zero duplicate dispatches.
            </p>
          </div>
        </div>

        <div className="border-t border-edge/60 pt-4 flex flex-wrap items-center justify-between gap-4 text-xs">
          <p className="text-muted">
            Ready to test? Try the live storefront or inspect cryptographic receipts.
          </p>
          <div className="flex items-center gap-3">
            <Link href="/" className="btn btn-primary text-xs py-2 px-4">
              Try Safe Autopilot &rarr;
            </Link>
            <Link href="/audit" className="btn btn-ghost text-xs py-2 px-4">
              View Trust Evidence &rarr;
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
