import "./globals.css";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { MerchantShell } from "@/components/layout/MerchantShell";

/**
 * tailwind.config.ts has declared Inter as the sans stack since the beginning,
 * but nothing ever loaded it — so every screen in this app was rendering in
 * whatever the operating system happened to fall back to. Declaring a typeface
 * and never fetching it is the quietest way to make a designed product look
 * generic, because nothing appears broken.
 */
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Action Firewall — AI Commerce Permissions for Razorpay Merchants",
  description:
    "Your store can't say yes to an AI buyer yet. Action Firewall is the layer that lets it — completing valid checkouts under catalog drift and stopping unapproved drift before Razorpay is called.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      {/* Tokens, not hex literals: the previous values here (#F8FAFC, #0C6CF2)
          matched neither `canvas` nor `primary` in the Tailwind config, so the
          root layout was subtly off-palette from every page inside it. */}
      <body className="min-h-screen bg-canvas font-sans text-text antialiased selection:bg-primary/20 selection:text-primary">
        <MerchantShell>{children}</MerchantShell>
      </body>
    </html>
  );
}
