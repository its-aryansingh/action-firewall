"use client";
import { useEffect, useRef, useState } from "react";
import { api, inr, type ChatResponse, type Decision, type Mandate, type ToolInvocation } from "@/lib/api";
import { MandateBadge } from "@/components/MandateBadge";
import { CartPanel } from "@/components/CartPanel";

type Msg = {
  role: "user" | "agent";
  text: string;
  decision?: Decision | null;
  tools?: ToolInvocation[];
  traceUrl?: string | null;
};

const PROMPTS = [
  "I need supplies for a pasta dinner",
  "Add the Parmigiano Reggiano and the olive oil",
  "Checkout please",
];

export default function ChatPage() {
  const [sessionId] = useState(() => `sess_${Math.random().toString(36).slice(2, 10)}`);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<ChatResponse | null>(null);
  const [mandate, setMandate] = useState<Mandate | null>(null);
  const [spent, setSpent] = useState(0);
  const endRef = useRef<HTMLDivElement>(null);

  const refresh = async () => {
    try {
      const m = await api.activeMandate();
      setMandate(m);
      const u = await api.usage(m.id);
      setSpent(u.spent_paise);
    } catch { /* backend not up yet */ }
  };

  useEffect(() => { refresh(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      // The mandate is re-read server-side on every turn: revocation binds here.
      const r = await api.chat(sessionId, text);
      setRes(r);
      setMsgs((m) => [...m, {
        role: "agent", text: r.reply, decision: r.decision,
        tools: r.tools, traceUrl: r.trace_url,
      }]);
      refresh();
    } catch (e) {
      setMsgs((m) => [...m, {
        role: "agent",
        text: `Backend unreachable (${String(e)}). Is uvicorn running on :8000?`,
      }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <section className="card flex h-[70vh] flex-col">
        <div className="label">AI Buyer</div>

        <div className="mt-4 flex-1 space-y-4 overflow-y-auto pr-2">
          {msgs.length === 0 && (
            <div className="text-sm text-muted">
              <p>Try the demo script:</p>
              <ul className="mt-2 space-y-1">
                {PROMPTS.map((p) => (
                  <li key={p}>
                    <button className="text-brand hover:underline" onClick={() => send(p)}>
                      → {p}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {msgs.map((m, i) => (
            <div key={i} className={m.role === "user" ? "text-right" : ""}>
              <div
                className={`inline-block max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
                  m.role === "user" ? "bg-brand text-white" : "border border-edge bg-ink"
                }`}
              >
                {m.text}
              </div>

              {m.decision && (
                <div className="mt-2 max-w-[85%]">
                  <MandateBadge d={m.decision} />
                </div>
              )}

              {m.tools?.map((t, k) => (
                <div
                  key={k}
                  className="mt-1 max-w-[85%] rounded-lg border border-edge bg-ink px-3 py-1.5 font-mono text-[11px]"
                >
                  <span className={t.blocked ? "text-block" : "text-allow"}>
                    {t.blocked ? "BLOCKED" : "CALLED"}
                  </span>{" "}
                  mcp:{t.name}
                  {t.result?.short_url ? (
                    <a
                      href={String(t.result.short_url)}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-2 text-brand hover:underline"
                    >
                      open link
                    </a>
                  ) : null}
                </div>
              ))}

              {m.traceUrl && (
                <a
                  href={m.traceUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 block text-[11px] text-brand hover:underline"
                >
                  View Langfuse trace →
                </a>
              )}
            </div>
          ))}
          <div ref={endRef} />
        </div>

        <form
          className="mt-4 flex gap-2"
          onSubmit={(e) => { e.preventDefault(); send(input); }}
        >
          <input
            className="input"
            placeholder="I need supplies for a pasta dinner…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy}
          />
          <button className="btn" disabled={busy || !input.trim()}>
            {busy ? "…" : "Send"}
          </button>
        </form>
      </section>

      <aside className="space-y-4">
        <CartPanel cart={res?.cart ?? { lines: [] }} mandate={mandate} spent={spent} />
        {mandate && (
          <div className="card text-sm">
            <div className="label">Active mandate</div>
            <p className="mt-2">{mandate.label}</p>
            <p className="font-mono text-muted">
              {inr(mandate.cap_paise)} / {mandate.window}
            </p>
            <p className="mt-1 font-mono text-[11px] text-muted">
              v{mandate.version} · {mandate.active ? "active" : "revoked"}
            </p>
            <a href="/mandate" className="btn-ghost mt-3 inline-block">Edit limits</a>
          </div>
        )}
      </aside>
    </div>
  );
}
