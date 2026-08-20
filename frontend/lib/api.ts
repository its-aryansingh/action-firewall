export const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type CartLine = {
  sku: string; name: string; category: string;
  unit_price_paise: number; qty: number;
};
export type Cart = { lines: CartLine[] };

export type Decision = {
  allowed: boolean;
  code: string;
  mandate_id: string | null;
  mandate_version: number | null;
  cart_total_paise: number;
  cap_paise: number;
  already_spent_paise: number;
  headroom_paise: number;
  offending_skus: string[];
  human_message: string;
};

export type ToolInvocation = {
  name: string; args: Record<string, unknown>;
  result: Record<string, unknown> | null; blocked: boolean;
};

export type ChatResponse = {
  session_id: string; reply: string; cart: Cart;
  decision: Decision | null; tools: ToolInvocation[]; trace_url: string | null;
};

export type Mandate = {
  id: string; user_id: string; agent_id: string; label: string;
  cap_paise: number; window: string; per_txn_cap_paise: number | null;
  allowed_categories: string[]; blocked_categories: string[];
  active: boolean; version: number; created_at: number; updated_at: number;
};

export type Metrics = {
  mandate_checks: number;
  mandate_breach_attempts: number;
  mandate_breach_attempt_rate: number;
  value_blocked_paise: number;
  value_settled_paise: number;
  chargeback_liability_paise: number;
};

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export const api = {
  chat: (session_id: string, message: string) =>
    fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id, message }),
    }).then(j<ChatResponse>),

  activeMandate: () =>
    fetch(`${API}/mandates/active`, { cache: "no-store" }).then(j<Mandate>),

  listMandates: () =>
    fetch(`${API}/mandates`, { cache: "no-store" }).then(j<Mandate[]>),

  createMandate: (body: Record<string, unknown>) =>
    fetch(`${API}/mandates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(j<Mandate>),

  updateMandate: (id: string, body: Record<string, unknown>) =>
    fetch(`${API}/mandates/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(j<Mandate>),

  usage: (id: string) =>
    fetch(`${API}/mandates/${id}/usage`, { cache: "no-store" }).then(
      j<{ cap_paise: number; spent_paise: number; headroom_paise: number; utilisation: number; version: number }>
    ),

  metrics: () => fetch(`${API}/metrics`, { cache: "no-store" }).then(j<Metrics>),

  audit: (session_id?: string) =>
    fetch(`${API}/audit${session_id ? `?session_id=${session_id}` : ""}`, {
      cache: "no-store",
    }).then(j<any[]>),
};

export const inr = (paise: number) =>
  `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
