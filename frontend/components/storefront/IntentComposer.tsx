"use client";

import React, { useState } from "react";
import { VoiceIntentInput } from "@/components/VoiceIntentInput";

interface IntentComposerProps {
  goal: string;
  setGoal: (goal: string) => void;
  budget: string;
  setBudget: (budget: string) => void;
  busy: boolean;
  error: string | null;
  onPlan: () => void;
  aiVoiceConfigured: boolean;
}

const SUGGESTED_GOALS = [
  "Buy supplies for a pasta dinner",
  "Restock office snacks",
  "Breakfast run",
  "High-protein lunch",
];

const BUDGET_PRESETS = [
  { label: "Under ₹400", value: "400" },
  { label: "Under ₹600", value: "600" },
  { label: "Under ₹1,000", value: "1000" },
];

export const IntentComposer: React.FC<IntentComposerProps> = ({
  goal,
  setGoal,
  budget,
  setBudget,
  busy,
  error,
  onPlan,
  aiVoiceConfigured,
}) => {
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);

  const handleVoiceTranscript = (text: string) => {
    setGoal(text);
    setVoiceNotice("Transcript added. Review or edit your goal.");
  };

  return (
    <div className="card space-y-6 border-brand/20 bg-panel/80 p-6 sm:p-8">
      <div>
        <div className="flex items-center justify-between">
          <span className="label">Step 1 · Outcome-First Intent</span>
          <span className="text-xs text-muted">Protected by Action Firewall</span>
        </div>
        <h2 className="mt-2 text-2xl font-bold tracking-tight text-white sm:text-3xl">
          What do you need?
        </h2>
        <p className="mt-1 text-sm text-muted">
          Describe the outcome. Safe Autopilot composes the cart and verifies pricing against merchant stock.
        </p>
      </div>

      <div className="space-y-4">
        {/* Main Intent Input Box */}
        <div className="relative rounded-2xl border border-border bg-surface p-2 shadow-sm focus-within:border-primary focus-within:ring-2 focus-within:ring-primary/20 transition-all">
          <textarea
            value={goal}
            onChange={(e) => {
              setGoal(e.target.value);
              setVoiceNotice(null);
            }}
            placeholder="e.g. Buy supplies for a pasta dinner..."
            rows={2}
            disabled={busy}
            className="w-full resize-none bg-transparent px-3 py-2 text-base text-white placeholder-slate-500 outline-none disabled:opacity-50"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (goal.trim() && !busy) onPlan();
              }
            }}
          />

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-edge/60 px-2 pt-2 sm:px-3">
            <div className="flex items-center gap-2">
              <VoiceIntentInput
                aiConfigured={aiVoiceConfigured}
                disabled={busy}
                onTranscript={handleVoiceTranscript}
              />
            </div>

            <button
              type="button"
              onClick={onPlan}
              disabled={busy || !goal.trim() || !budget}
              className="btn btn-primary inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold"
            >
              {busy ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  <span>Planning cart...</span>
                </>
              ) : (
                <>
                  <span>Plan my order</span>
                  <span aria-hidden="true">&rarr;</span>
                </>
              )}
            </button>
          </div>
        </div>

        {voiceNotice && (
          <p className="text-xs text-brand font-medium animate-fadeIn">
            ✓ {voiceNotice}
          </p>
        )}

        {/* Budget & Store Chips */}
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <div className="flex items-center gap-1.5 text-xs text-muted">
            <span>Budget:</span>
            {BUDGET_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                onClick={() => setBudget(preset.value)}
                className={`store-chip ${budget === preset.value ? "store-chip-active" : ""}`}
              >
                {preset.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5 text-xs text-muted sm:ml-auto">
            <span>Store:</span>
            <span className="store-chip store-chip-active cursor-default">
              FreshBasket for Business
            </span>
          </div>
        </div>

        {/* Suggested Goals */}
        <div className="pt-2">
          <p className="text-xs text-muted mb-2">Try one of these goals:</p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTED_GOALS.map((suggested) => (
              <button
                key={suggested}
                type="button"
                onClick={() => {
                  setGoal(suggested);
                  setVoiceNotice(null);
                }}
                className="rounded-lg border border-edge/60 bg-panel/40 px-3 py-1.5 text-xs text-slate-300 transition hover:border-brand/40 hover:bg-panel hover:text-white"
              >
                {suggested}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs text-rose-300">
          <strong>Notice:</strong> {error}
        </div>
      )}

      <div className="border-t border-edge/60 pt-4 text-center">
        <p className="text-xs text-muted">
          🔒 Nothing can be purchased until you review and approve the limits.
        </p>
      </div>
    </div>
  );
};
