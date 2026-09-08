import React from "react";

export type EvidenceTier =
  | "demo_simulated"
  | "replay_test_mode"
  | "gemini_test_mode";

interface EvidenceBadgeProps {
  providerMode?: string;
  buyerModel?: string;
  tier?: EvidenceTier;
  className?: string;
}

export function EvidenceBadge({
  providerMode,
  buyerModel,
  tier,
  className = "",
}: EvidenceBadgeProps) {
  // Determine mutually exclusive tier
  let activeTier: EvidenceTier = "demo_simulated";

  if (tier) {
    activeTier = tier;
  } else {
    const isRealProvider =
      providerMode === "razorpay_rest" ||
      providerMode === "remote_mcp" ||
      providerMode === "RazorpayRESTClient";
    const isGemini =
      buyerModel?.toLowerCase().includes("gemini") ?? false;

    if (isRealProvider) {
      activeTier = isGemini ? "gemini_test_mode" : "replay_test_mode";
    } else {
      activeTier = "demo_simulated";
    }
  }

  const badgeConfig = {
    demo_simulated: {
      text: "Demo data · Simulated provider",
      dotClass: "bg-amber-500",
      containerClass: "bg-amber-500/10 text-amber-800 border-amber-500/30",
    },
    replay_test_mode: {
      text: "Replay buyer · Razorpay Test Mode",
      dotClass: "bg-primary",
      containerClass: "bg-primary/10 text-primary border-primary/30",
    },
    gemini_test_mode: {
      text: "Live Gemini · Razorpay Test Mode",
      dotClass: "bg-success",
      containerClass: "bg-success/10 text-success border-success/30",
    },
  }[activeTier];

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${badgeConfig.containerClass} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${badgeConfig.dotClass}`} />
      {badgeConfig.text}
    </span>
  );
}
