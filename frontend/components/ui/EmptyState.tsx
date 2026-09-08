import React from "react";

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({
  title,
  description,
  icon,
  action,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-canvas/40 px-6 py-10 text-center ${className}`}
    >
      {icon && <div className="mb-3 text-muted">{icon}</div>}
      <h4 className="text-sm font-semibold text-text">{title}</h4>
      {description && (
        <p className="mt-1 max-w-sm text-xs text-muted leading-relaxed">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
