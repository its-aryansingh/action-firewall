import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Safe Autopilot — One-Approval Intent-to-Checkout for Razorpay Merchants",
  description:
    "One approval for the job. Zero authority beyond it. Protected by Action Firewall.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-ink text-slate-100 antialiased selection:bg-brand/30 selection:text-white">
        <header className="sticky top-0 z-50 border-b border-edge/80 bg-ink/85 backdrop-blur-xl">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
            <Link href="/" className="flex items-center gap-2.5 text-sm font-semibold tracking-tight transition hover:opacity-90">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-brand/30 bg-brand/10 text-brand shadow-[0_0_20px_rgba(51,149,255,0.15)]">
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
                  <path d="M12 3 5.5 5.7v5.7c0 4.2 2.6 7.9 6.5 9.6 3.9-1.7 6.5-5.4 6.5-9.6V5.7L12 3Z" stroke="currentColor" strokeWidth="1.8" />
                  <path d="m9 12 2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <div className="flex flex-col">
                <span className="text-sm font-bold tracking-tight text-white">Safe Autopilot</span>
                <span className="text-[10px] font-medium text-brand/80">Protected by Action Firewall</span>
              </div>
            </Link>

            <nav className="flex items-center gap-1 rounded-xl border border-edge/70 bg-panel/60 p-1 text-xs font-medium text-muted">
              <Link href="/" className="rounded-lg px-3 py-1.5 transition hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand">
                Shop
              </Link>
              <Link href="/impact" className="rounded-lg px-3 py-1.5 transition hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand">
                Merchant impact
              </Link>
              <Link href="/audit" className="rounded-lg px-3 py-1.5 transition hover:bg-white/5 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand">
                Trust
              </Link>
            </nav>

            <div className="hidden items-center gap-2 sm:flex">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-edge/80 bg-panel/40 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-muted">
                <span className="h-1.5 w-1.5 rounded-full bg-allow animate-pulse" />
                Track 01
              </span>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      </body>
    </html>
  );
}
