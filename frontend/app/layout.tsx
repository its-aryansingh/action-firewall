import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Action Firewall — Agentic Checkout Authorization",
  description:
    "Agentic commerce is an authorization problem, not a checkout problem.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="border-b border-edge">
          <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-4">
            <Link href="/" className="text-sm font-semibold tracking-tight">
              <span className="text-brand">Action Firewall</span>
            </Link>
            <nav className="flex gap-4 text-sm text-muted">
              <Link href="/" className="hover:text-slate-100">Chat</Link>
              <Link href="/mandate" className="hover:text-slate-100">Policy</Link>
              <Link href="/audit" className="hover:text-slate-100">Evidence</Link>
            </nav>
            <span className="ml-auto rounded-full border border-edge px-3 py-1 text-xs text-muted">
              Razorpay MCP-compatible actuator
            </span>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
