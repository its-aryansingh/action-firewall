"use client";

import { useEffect, useRef, useState } from "react";
import {
  api,
  inr,
  type ChatResponse,
  type Decision,
  type Mandate,
  type ToolInvocation,
} from "@/lib/api";
import { MandateBadge } from "@/components/MandateBadge";
import { CartPanel } from "@/components/CartPanel";

type Msg = {
  role: "user" | "agent";
  text: string;
  decision?: Decision | null;
  tools?: ToolInvocation[];
  traceUrl?: string | null;
  actionStatus?: ChatResponse["action_status"];
  grantId?: string | null;
};

const PROMPTS = [
  "I need supplies for a pasta dinner",
  "Add the Parmigiano Reggiano and the olive oil",
  "Checkout please",
];

function purchaseAttemptId(): string {
  return "attempt_" + globalThis.crypto.randomUUID();
}

export default function ChatPage() {
  const [sessionId] = useState(
    () => "sess_" + Math.random().toString(36).slice(2, 10),
  );
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<ChatResponse | null>(null);
  const [mandate, setMandate] = useState<Mandate | null>(null);
  const [exposure, setExposure] = useState(0);
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const refresh = async () => {
    try {
      const policies = await api.listMandates();
      const current = policies[0] ?? null;
      setMandate(current);
      if (current) {
        const usage = await api.usage(current.id);
        setExposure(usage.spent_paise);
      }
    } catch {
      // The app remains usable while the backend starts.
    }
  };

  useEffect(() => {
    refresh();
  }, []);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  function appendAgentResponse(response: ChatResponse) {
    setRes(response);
    setMsgs((current) => [
      ...current,
      {
        role: "agent",
        text: response.reply,
        decision: response.decision,
        tools: response.tools,
        traceUrl: response.trace_url,
        actionStatus: response.action_status,
        grantId: response.grant_id,
      },
    ]);
  }

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setInput("");
    setMsgs((current) => [...current, { role: "user", text }]);
    setBusy(true);
    try {
      const response = await api.chat(sessionId, text);
      appendAgentResponse(response);
      setAttemptId(response.cart.lines.length ? purchaseAttemptId() : null);
      await refresh();
    } catch (error) {
      setMsgs((current) => [
        ...current,
        {
          role: "agent",
          text:
            "Backend unreachable (" +
            String(error) +
            "). Is uvicorn running on :8000?",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function authorizePaymentLink() {
    if (!res?.cart_hash || !res.cart.lines.length || busy) return;
    const stableAttemptId = attemptId ?? purchaseAttemptId();
    setAttemptId(stableAttemptId);
    setMsgs((current) => [
      ...current,
      { role: "user", text: "Authorize this exact payment-link action." },
    ]);
    setBusy(true);
    try {
      const response = await api.confirmCheckout(
        sessionId,
        res.cart_hash,
        stableAttemptId,
      );
      appendAgentResponse(response);
      if (!response.cart.lines.length) setAttemptId(null);
      await refresh();
    } catch (error) {
      setMsgs((current) => [
        ...current,
        {
          role: "agent",
          text:
            "Authorization request failed (" +
            String(error) +
            "). The same purchase-attempt ID is retained for a safe retry.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <section className="card flex h-[70vh] flex-col">
        <div className="label">AI Buyer — proposal only</div>

        <div className="mt-4 flex-1 space-y-4 overflow-y-auto pr-2">
          {msgs.length === 0 && (
            <div className="text-sm text-muted">
              <p>Try the demo sequence:</p>
              <ul className="mt-2 space-y-1">
                {PROMPTS.map((prompt) => (
                  <li key={prompt}>
                    <button
                      className="text-brand hover:underline"
                      onClick={() => send(prompt)}
                    >
                      → {prompt}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {msgs.map((message, index) => (
            <div
              key={message.role + "-" + index}
              className={message.role === "user" ? "text-right" : ""}
            >
              <div
                className={
                  "inline-block max-w-[85%] rounded-2xl px-4 py-2 text-sm " +
                  (message.role === "user"
                    ? "bg-brand text-white"
                    : "border border-edge bg-ink")
                }
              >
                {message.text}
              </div>

              {message.decision && (
                <div className="mt-2 max-w-[85%]">
                  <MandateBadge d={message.decision} />
                </div>
              )}

              {message.actionStatus && (
                <div className="mt-1 max-w-[85%] rounded-lg border border-edge bg-ink px-3 py-1.5 font-mono text-[11px]">
                  action {message.actionStatus}
                  {message.grantId ? " · " + message.grantId : ""}
                </div>
              )}

              {message.tools?.map((tool, index) => (
                <div
                  key={tool.name + "-" + index}
                  className="mt-1 max-w-[85%] rounded-lg border border-edge bg-ink px-3 py-1.5 font-mono text-[11px]"
                >
                  <span className={tool.blocked ? "text-block" : "text-allow"}>
                    {tool.blocked ? "DENIED" : "ACTION ISSUED"}
                  </span>{" "}
                  mcp:{tool.name}
                  {tool.result?.short_url ? (
                    <a
                      href={String(tool.result.short_url)}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-2 text-brand hover:underline"
                    >
                      open test link
                    </a>
                  ) : null}
                </div>
              ))}

              {message.traceUrl && (
                <a
                  href={message.traceUrl}
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
          onSubmit={(event) => {
            event.preventDefault();
            send(input);
          }}
        >
          <input
            className="input"
            placeholder="I need supplies for a pasta dinner…"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            disabled={busy}
          />
          <button className="btn" disabled={busy || !input.trim()}>
            {busy ? "…" : "Propose"}
          </button>
        </form>
      </section>

      <aside className="space-y-4">
        <CartPanel
          cart={res?.cart ?? { lines: [] }}
          mandate={mandate}
          exposure={exposure}
          busy={busy}
          onAuthorize={authorizePaymentLink}
        />
        {mandate && (
          <div className="card text-sm">
            <div className="label">Current authorization policy</div>
            <p className="mt-2">{mandate.label}</p>
            <p className="font-mono text-muted">
              {inr(mandate.cap_paise)} / {mandate.window}
            </p>
            <p className="mt-1 font-mono text-[11px] text-muted">
              v{mandate.version} · {mandate.active ? "active" : "revoked"}
            </p>
            <a href="/mandate" className="btn-ghost mt-3 inline-block">
              Edit policy
            </a>
          </div>
        )}
      </aside>
    </div>
  );
}
