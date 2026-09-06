import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Action Firewall — Safe Autopilot Checkout",
  description:
    "One approval for the job. Zero authority beyond it.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="sticky top-0 z-50 border-b border-edge/80 bg-ink/80 backdrop-blur-xl">
          <div className="mx-auto flex max-w-7xl items-center gap-5 px-4 py-3 sm:px-6">
            <Link href="/" className="flex items-center gap-2.5 text-sm font-semibold tracking-tight">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-brand/30 bg-brand/10 text-brand shadow-[0_0_20px_rgba(51,149,255,0.12)]">
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden="true">
                  <path d="M12 3 5.5 5.7v5.7c0 4.2 2.6 7.9 6.5 9.6 3.9-1.7 6.5-5.4 6.5-9.6V5.7L12 3Z" stroke="currentColor" strokeWidth="1.8" />
                  <path d="m9 12 2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <span><span className="text-slate-100">Action</span> <span className="text-brand">Firewall</span></span>
            </Link>
            <nav className="ml-auto hidden items-center gap-1 rounded-xl border border-edge/70 bg-panel/40 p-1 text-xs text-muted sm:flex">
              <Link href="/" className="rounded-lg px-3 py-2 hover:bg-white/5 hover:text-slate-100">Autopilot</Link>
              <Link href="/baseline" className="rounded-lg px-3 py-2 hover:bg-white/5 hover:text-slate-100">Control</Link>
              <Link href="/audit" className="rounded-lg px-3 py-2 hover:bg-white/5 hover:text-slate-100">Evidence</Link>
            </nav>
            <span className="ml-auto inline-flex items-center gap-2 rounded-full border border-edge bg-panel/40 px-3 py-1.5 font-mono text-[9px] uppercase tracking-wider text-muted sm:ml-0">
              <i className="h-1.5 w-1.5 rounded-full bg-allow" /> Bound by policy
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">{children}</main>
      </body>
    </html>
  );
}
