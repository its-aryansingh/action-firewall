import "./globals.css";
import type { Metadata } from "next";
import { MerchantShell } from "@/components/layout/MerchantShell";

export const metadata: Metadata = {
  title: "Action Firewall — AI Commerce Permissions for Razorpay Merchants",
  description:
    "Your store can't say yes to an AI buyer yet. Action Firewall is the layer that lets it — completing valid checkouts under catalog drift and stopping unapproved drift before Razorpay is called.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#F8FAFC] antialiased selection:bg-[#0C6CF2]/20 selection:text-[#0C6CF2]">
        <MerchantShell>{children}</MerchantShell>
      </body>
    </html>
  );
}
