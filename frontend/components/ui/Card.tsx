import React from "react";

interface CardProps {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  badge?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function Card({ title, subtitle, badge, action, children, className = "" }: CardProps) {
  return (
    <div className={`rounded-2xl border border-border bg-surface p-6 shadow-sm ${className}`}>
      {(title || badge || action) && (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-border/60 pb-3">
          <div>
            <div className="flex items-center gap-2">
              {title && typeof title === "string" ? (
                <h3 className="text-base font-semibold text-text">{title}</h3>
              ) : (
                title
              )}
              {badge}
            </div>
            {subtitle && (
              <p className="mt-0.5 text-xs text-muted">{subtitle}</p>
            )}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
