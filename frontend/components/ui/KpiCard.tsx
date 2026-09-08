import React from "react";

interface KpiCardProps {
  label: string;
  value: React.ReactNode;
  subtext?: React.ReactNode;
  trend?: string;
  tone?: "primary" | "success" | "warning" | "danger" | "neutral";
  evidenceMode?: string;
  isHero?: boolean;
  action?: React.ReactNode;
  className?: string;
}

export function KpiCard({
  label,
  value,
  subtext,
  trend,
  tone = "primary",
  evidenceMode,
  isHero = false,
  action,
  className = "",
}: KpiCardProps) {
  const toneBg = {
    primary: "border-primary/20 bg-primary/[0.02]",
    success: "border-success/30 bg-success/[0.03]",
    warning: "border-warning/30 bg-warning/[0.03]",
    danger: "border-danger/30 bg-danger/[0.03]",
    neutral: "border-border bg-surface",
  }[tone];

  const toneText = {
    primary: "text-primary",
    success: "text-success",
    warning: "text-warning",
    danger: "text-danger",
    neutral: "text-text",
  }[tone];

  if (isHero) {
    return (
      <div
        className={`rounded-2xl border-2 border-primary/40 bg-gradient-to-br from-surface to-primary/[0.04] p-6 shadow-sm sm:p-8 ${className}`}
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-widest text-primary">
                {label}
              </span>
              {evidenceMode && (
                <span className="rounded-full bg-border/60 px-2 py-0.5 font-mono text-[10px] text-muted">
                  {evidenceMode}
                </span>
              )}
            </div>
            <div className="text-3xl font-extrabold tracking-tight text-text sm:text-4xl">
              {value}
            </div>
            {subtext && (
              <p className="max-w-2xl text-sm font-medium text-muted">{subtext}</p>
            )}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      </div>
    );
  }

  return (
    <div
      className={`rounded-2xl border p-5 shadow-sm transition hover:border-primary/40 ${toneBg} ${className}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted">
          {label}
        </span>
        {evidenceMode && (
          <span className="rounded-full bg-border/60 px-1.5 py-0.2 font-mono text-[9px] text-muted">
            {evidenceMode}
          </span>
        )}
      </div>
      <div className={`mt-2 text-2xl font-bold tracking-tight ${toneText}`}>
        {value}
      </div>
      {subtext && (
        <p className="mt-1 text-xs text-muted leading-relaxed">{subtext}</p>
      )}
      {trend && (
        <div className="mt-2 text-[11px] font-medium text-success">{trend}</div>
      )}
    </div>
  );
}
