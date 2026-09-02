"use client";

import { useEffect, useState } from "react";
import { api, inr, type Mandate } from "@/lib/api";

const CATEGORIES = [
  "pantry",
  "produce",
  "dairy",
  "bakery",
  "beverages",
  "snacks",
  "household",
  "personal_care",
  "electronics",
  "gift_cards",
];

export default function PolicyDashboard() {
  const [policies, setPolicies] = useState<Mandate[]>([]);
  const [current, setCurrent] = useState<Mandate | null>(null);
  const [usage, setUsage] = useState({ spent_paise: 0, headroom_paise: 0 });
  const [cap, setCap] = useState(1000);
  const [perTxn, setPerTxn] = useState<number | "">("");
  const [windowSelection, setWindowSelection] = useState("weekly");
  const [blocked, setBlocked] = useState<string[]>(["gift_cards"]);
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  async function load() {
    try {
      const all = await api.listMandates();
      setPolicies(all);
      const latest = all[0] ?? null;
      setCurrent(latest);
      if (latest) {
        setCap(latest.cap_paise / 100);
        setPerTxn(
          latest.per_txn_cap_paise ? latest.per_txn_cap_paise / 100 : "",
        );
        setBlocked(latest.blocked_categories);
        setWindowSelection(latest.window);
        setUsage(await api.usage(latest.id));
      }
    } catch {
      // Preserve the last policy snapshot while the backend restarts.
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function save() {
    if (!current) return;
    setSaving(true);
    const startedAt = performance.now();
    const updated = await api.updateMandate(current.id, {
      cap_rupees: cap,
      per_txn_cap_rupees: perTxn === "" ? null : perTxn,
      blocked_categories: blocked,
    });
    const elapsed = Math.round(performance.now() - startedAt);
    setFlash(
      "Policy v" +
        updated.version +
        " saved in " +
        elapsed +
        "ms. Every new authorization is fenced to this version.",
    );
    setSaving(false);
    await load();
  }

  async function toggleActive() {
    if (!current) return;
    const updated = await api.updateMandate(current.id, {
      active: !current.active,
    });
    setFlash(
      updated.active
        ? "Policy re-activated for new authorizations."
        : "Policy revoked. New and undispatched authorizations are blocked; already-issued external actions require reconciliation.",
    );
    await load();
  }

  async function createNew() {
    const created = await api.createMandate({
      cap_rupees: cap,
      window: windowSelection,
      per_txn_cap_rupees: perTxn === "" ? null : perTxn,
      blocked_categories: blocked,
    });
    setFlash(
      "New authorization policy " + created.id + " superseded the previous policy.",
    );
    await load();
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
      <section className="card">
        <div className="label">
          Policy Dashboard — shopper-defined action authority
        </div>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          This application policy limits which AI-buyer actions may receive an
          exact, one-time authorization receipt. It is not a banking mandate or
          a replacement for Razorpay or payment-rail consent.
        </p>

        {flash && (
          <div className="mt-4 rounded-xl border border-brand/40 bg-brand/10 px-4 py-2 text-sm">
            {flash}
          </div>
        )}

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label">Rolling exposure ceiling (₹)</label>
            <input
              type="number"
              className="input mt-1"
              value={cap}
              min={0}
              onChange={(event) => setCap(Number(event.target.value))}
            />
          </div>
          <div>
            <label className="label">Window</label>
            <select
              className="input mt-1"
              value={windowSelection}
              onChange={(event) => setWindowSelection(event.target.value)}
            >
              {["per_transaction", "daily", "weekly", "monthly"].map((window) => (
                <option key={window} value={window}>
                  {window}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Per-action cap (₹, optional)</label>
            <input
              type="number"
              className="input mt-1"
              value={perTxn}
              min={0}
              onChange={(event) =>
                setPerTxn(
                  event.target.value === "" ? "" : Number(event.target.value),
                )
              }
            />
          </div>
          <div>
            <label className="label">Blocked categories</label>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {CATEGORIES.map((category) => {
                const selected = blocked.includes(category);
                return (
                  <button
                    key={category}
                    type="button"
                    onClick={() =>
                      setBlocked(
                        selected
                          ? blocked.filter((value) => value !== category)
                          : [...blocked, category],
                      )
                    }
                    className={
                      "rounded-full border px-2.5 py-1 text-[11px] " +
                      (selected
                        ? "border-block/50 bg-block/15 text-block"
                        : "border-edge text-muted hover:border-brand")
                    }
                  >
                    {category}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          <button className="btn" onClick={save} disabled={saving || !current}>
            {saving ? "Saving…" : "Update policy"}
          </button>
          <button
            className="btn-ghost"
            onClick={toggleActive}
            disabled={!current}
          >
            {current?.active ? "Revoke policy" : "Re-activate policy"}
          </button>
          <button className="btn-ghost" onClick={createNew}>
            Create new policy
          </button>
        </div>
      </section>

      <aside className="space-y-4">
        {current && (
          <div className="card">
            <div className="label">Current policy</div>
            <p className="mt-2 text-2xl font-semibold">
              {inr(current.cap_paise)}
            </p>
            <p className="text-sm text-muted">per {current.window}</p>
            <div className="mt-4 space-y-1 font-mono text-[11px] text-muted">
              <div>id {current.id}</div>
              <div>version {current.version}</div>
              <div>exposure {inr(usage.spent_paise)}</div>
              <div>headroom {inr(usage.headroom_paise)}</div>
              <div className={current.active ? "text-allow" : "text-block"}>
                {current.active ? "ACTIVE" : "REVOKED"}
              </div>
            </div>
          </div>
        )}
        <div className="card">
          <div className="label">Policy history</div>
          <ul className="mt-3 space-y-2 font-mono text-[11px] text-muted">
            {policies.map((policy) => (
              <li key={policy.id} className="flex justify-between gap-2">
                <span className="truncate">
                  {policy.id} v{policy.version}
                </span>
                <span className={policy.active ? "text-allow" : ""}>
                  {inr(policy.cap_paise)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
