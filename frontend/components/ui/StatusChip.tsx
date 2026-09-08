import React from "react";

export type StatusTone = "success" | "warning" | "danger" | "primary" | "neutral";

interface StatusChipProps {
  status: string;
  label?: string;
  tone?: StatusTone;
  size?: "sm" | "md";
  className?: string;
}

export function getStatusConfig(status: string): { label: string; tone: StatusTone } {
  const norm = status.toUpperCase();

  switch (norm) {
    case "PAID":
    case "CAPTURED":
    case "SETTLED":
      return { label: "Paid", tone: "success" };
    case "RECOVERED":
      return { label: "Recovered", tone: "success" };
    case "READY_FOR_AI_BUYERS":
    case "READY":
      return { label: "Ready for AI Buyers", tone: "success" };
    case "ACTION_ISSUED":
    case "ISSUED":
      return { label: "Link Issued", tone: "primary" };
    case "POLICY_DELTA_REQUIRED":
    case "APPROVAL_PENDING":
    case "CUSTOMER_APPROVAL_NEEDED":
      return { label: "Customer Approval Needed", tone: "warning" };
    case "UNKNOWN":
    case "NEEDS_RECONCILIATION":
      return { label: "Needs Reconciliation", tone: "warning" };
    case "BLOCKED":
    case "REJECTED":
    case "STOPPED":
      return { label: "Stopped", tone: "danger" };
    case "FAILED":
      return { label: "Failed", tone: "danger" };
    case "CONFIGURING":
      return { label: "Configuring", tone: "neutral" };
    case "ACTIVE":
      return { label: "Active", tone: "success" };
    case "INACTIVE":
    case "OFF":
      return { label: "Off", tone: "neutral" };
    default:
      return { label: status, tone: "neutral" };
  }
}

export function StatusChip({
  status,
  label,
  tone,
  size = "md",
  className = "",
}: StatusChipProps) {
  const config = getStatusConfig(status);
  const finalLabel = label || config.label;
  const finalTone = tone || config.tone;

  const toneClasses: Record<StatusTone, string> = {
    success: "bg-success/10 text-success border-success/30",
    warning: "bg-warning/10 text-warning border-warning/30",
    danger: "bg-danger/10 text-danger border-danger/30",
    primary: "bg-primary/10 text-primary border-primary/30",
    neutral: "bg-canvas text-muted border-border",
  };

  const dotClasses: Record<StatusTone, string> = {
    success: "bg-success",
    warning: "bg-warning",
    danger: "bg-danger",
    primary: "bg-primary",
    neutral: "bg-muted",
  };

  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium ${toneClasses[finalTone]} ${sizeClasses} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dotClasses[finalTone]}`} />
      {finalLabel}
    </span>
  );
}
