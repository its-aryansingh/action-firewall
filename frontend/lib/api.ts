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
  cart_hash: string;
  confirmation_required: boolean;
  action_status: "authorized" | "dispatching" | "action_issued" | "settled"
    | "definitive_failure" | "unknown" | "cancelled" | null;
  grant_id: string | null;
};

export type Mandate = {
  id: string; user_id: string; agent_id: string; label: string;
  cap_paise: number; window: string; per_txn_cap_paise: number | null;
  allowed_categories: string[]; blocked_categories: string[];
  active: boolean; version: number; created_at: number; updated_at: number;
};

export type Metrics = {
  authorization_attempts: number;
  denied_authorizations: number;
  authorization_denial_rate: number;
  denied_requested_value_paise: number;
  payment_link_issued_value_paise: number;
  confirmed_test_payment_value_paise: number;
  unknown_outcome_value_paise: number;
  outstanding_authorized_exposure_paise: number;
  unauthorized_actuator_calls: number;
  cart_policy_previews: number;
  generated_at: number;
};

export type AuditEvent = {
  id: string;
  session_id: string | null;
  mandate_id: string | null;
  mandate_version: number | null;
  event: string;
  code: string | null;
  cart_total_paise: number | null;
  cap_paise: number | null;
  payload: Record<string, unknown>;
  created_at: number;
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

  confirmCheckout: (
    session_id: string,
    expected_cart_hash: string,
    idempotency_key: string,
  ) =>
    fetch(`${API}/checkout/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id, expected_cart_hash, idempotency_key }),
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
    }).then(j<AuditEvent[]>),
};

export const inr = (paise: number) =>
  `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
