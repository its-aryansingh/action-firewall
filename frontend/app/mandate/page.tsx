"use client";
import { useEffect, useState } from "react";
import { api, inr, type Mandate } from "@/lib/api";

const CATEGORIES = ["pantry", "produce", "dairy", "bakery", "beverages",
  "snacks", "household", "personal_care", "electronics", "gift_cards"];

export default function MandateDashboard() {
  const [mandates, setMandates] = useState<Mandate[]>([]);
  const [active, setActive] = useState<Mandate | null>(null);
  const [usage, setUsage] = useState({ spent_paise: 0, headroom_paise: 0 });
  const [cap, setCap] = useState(1000);
  const [perTxn, setPerTxn] = useState<number | "">("");
  const [windowSel, setWindow] = useState("weekly");
  const [blocked, setBlocked] = useState<string[]>(["gift_cards"]);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  async function load() {
    try {
      const all = await api.listMandates();
      setMandates(all);
      const a = all.find((m) => m.active) ?? null;
      setActive(a);
      if (a) {
        setCap(a.cap_paise / 100);
        setPerTxn(a.per_txn_cap_paise ? a.per_txn_cap_paise / 100 : "");
        setBlocked(a.blocked_categories);
        setWindow(a.window);
        const u = await api.usage(a.id);
        setUsage(u);
      }
    } catch { /* backend down */ }
  }
  useEffect(() => { load(); }, []);

  async function save() {
    if (!active) return;
    setSaving(true);
    const t0 = performance.now();
    await api.updateMandate(active.id, {
      cap_rupees: cap,
      per_txn_cap_rupees: perTxn === "" ? null : perTxn,
      blocked_categories: blocked,
    });
    const ms = Math.round(performance.now() - t0);
    // Revocation latency: the agent re-reads the mandate on its next turn,
    // so the new ceiling binds immediately — there is no cache to invalidate.
    setFlash(`Mandate updated in ${ms}ms — binds on the agent's very next prompt.`);
    setSaving(false);
    load();
  }

  async function toggleActive() {
    if (!active) return;
    await api.updateMandate(active.id, { active: !active.active });
    setFlash(active.active ? "Mandate revoked. The agent can no longer spend."
                           : "Mandate re-activated.");
    load();
  }

  async function createNew() {
    await api.createMandate({
      cap_rupees: cap, window: windowSel,
      per_txn_cap_rupees: perTxn === "" ? null : perTxn,
      blocked_categories: blocked,
    });
    setFlash("New mandate issued; the previous one was superseded.");
    load();
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <section className="card">
        <div className="label">Mandate Dashboard — human-authorised spending authority</div>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Models NPCI&apos;s Unified Agent Protocol delegation, built on the UPI Circle
          pattern: a primary user grants a capped, revocable authority to a secondary
          payer — here, an AI agent.
        </p>

        {flash && (
          <div className="mt-4 rounded-xl border border-brand/40 bg-brand/10 px-4 py-2 text-sm">
            {flash}
          </div>
        )}

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Spending ceiling (₹)</label>
            <input type="number" className="input mt-1" value={cap}
                   onChange={(e) => setCap(Number(e.target.value))} />
          </div>
          <div>
            <label className="label">Window</label>
            <select className="input mt-1" value={windowSel}
                    onChange={(e) => setWindow(e.target.value)}>
              {["per_transaction", "daily", "weekly", "monthly"].map((w) => (
                <option key={w} value={w}>{w}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Per-transaction cap (₹, optional)</label>
            <input type="number" className="input mt-1" value={perTxn}
                   onChange={(e) => setPerTxn(e.target.value === "" ? "" : Number(e.target.value))} />
          </div>
          <div>
            <label className="label">Blocked categories</label>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {CATEGORIES.map((c) => {
                const on = blocked.includes(c);
                return (
                  <button key={c} type="button"
                    onClick={() => setBlocked(on ? blocked.filter((x) => x !== c) : [...blocked, c])}
                    className={`rounded-full border px-2.5 py-1 text-[11px] ${
                      on ? "border-block/50 bg-block/15 text-block"
                         : "border-edge text-muted hover:border-brand"}`}>
                    {c}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <button className="btn" onClick={save} disabled={saving || !active}>
            {saving ? "Saving…" : "Update limits"}
          </button>
          <button className="btn-ghost" onClick={toggleActive} disabled={!active}>
            {active?.active ? "Revoke mandate" : "Re-activate"}
          </button>
          <button className="btn-ghost" onClick={createNew}>Issue new mandate</button>
        </div>
      </section>

      <aside className="space-y-4">
        {active && (
          <div className="card">
            <div className="label">Current authority</div>
            <p className="mt-2 text-2xl font-semibold">{inr(active.cap_paise)}</p>
            <p className="text-sm text-muted">per {active.window}</p>
            <div className="mt-4 space-y-1 font-mono text-[11px] text-muted">
              <div>id {active.id}</div>
              <div>version {active.version}</div>
              <div>spent {inr(usage.spent_paise)}</div>
              <div>headroom {inr(usage.headroom_paise)}</div>
              <div className={active.active ? "text-allow" : "text-block"}>
                {active.active ? "ACTIVE" : "REVOKED"}
              </div>
            </div>
          </div>
        )}
        <div className="card">
          <div className="label">Mandate history</div>
          <ul className="mt-3 space-y-2 text-[11px] font-mono text-muted">
            {mandates.map((m) => (
              <li key={m.id} className="flex justify-between gap-2">
                <span className="truncate">{m.id} v{m.version}</span>
                <span className={m.active ? "text-allow" : ""}>{inr(m.cap_paise)}</span>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
