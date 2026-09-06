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
  envelopes_activated: number;
  envelope_quotes_allowed: number;
  envelope_quotes_blocked: number;
  in_envelope_recoveries: number;
  generated_at: number;
};

export type AuthorityView = {
  user_id: string;
  window: string;
  ceiling_paise: number;
  ceiling_rupees: number;
  total_exposure_paise: number;
  total_exposure_rupees: number;
  remaining_headroom_paise: number;
  remaining_headroom_rupees: number;
  active_envelopes_count: number;
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

export type EnvelopeSlot = {
  id: string;
  label: string;
  required_tags: string[];
  quantity: number;
};

export type PurchaseEnvelope = {
  id: string;
  user_id: string;
  agent_id: string;
  label: string;
  goal: string;
  merchant_id: string;
  currency: "INR";
  max_total_paise: number;
  fulfillment_profile_id: string;
  delivery_deadline: number;
  expires_at: number;
  slots: EnvelopeSlot[];
  blocked_categories: string[];
  max_purchases: 1;
  action_name: "create_payment_link";
  status: "draft" | "active" | "consumed" | "revoked";
  version: number;
  envelope_hash: string;
  mandate_id: string | null;
  created_at: number;
  updated_at: number;
};

export type QuoteSubstitution = {
  slot_id: string;
  selected_sku: string;
  preferred_sku: string | null;
  reason: string;
};

export type MerchantQuote = {
  merchant_id: string;
  currency: "INR";
  fulfillment_profile_id: string;
  delivery_eta: number;
  cart: Cart;
  substitutions: QuoteSubstitution[];
  quote_hash: string;
};

export type PolicyDelta = {
  field: string;
  expected: string;
  actual: string;
  recovery: "repair" | "fresh_approval" | "stop";
};

export type EnvelopeDecision = {
  allowed: boolean;
  code: string;
  envelope_id: string;
  envelope_version: number;
  quote_total_paise: number;
  deltas: PolicyDelta[];
  human_message: string;
};

export type ReceiptAuthorization = {
  grant_id: string;
  envelope_id: string | null;
  envelope_version: number | null;
  envelope_hash: string | null;
  policy_id: string;
  policy_version: number;
  policy_hash: string;
  action_name: string;
  args_hash: string;
  cart_hash: string;
  quote_hash: string | null;
  purchase_attempt_id: string;
  created_at: number;
};

export type ReceiptStatus = {
  state: ChatResponse["action_status"];
  provider_ref: string | null;
  updated_at: number;
};

export type ActionReceiptVerification = {
  valid: boolean;
  authorization_valid: boolean;
  status_current: boolean;
  status_as_of: number;
  grant_id: string;
  application_signed: boolean;
};

export type ActionReceipt = {
  authorization?: ReceiptAuthorization;
  status?: ReceiptStatus;
  authorization_signature?: string;
  status_signature?: string;
  grant_id: string;
  envelope_id: string | null;
  envelope_version: number | null;
  envelope_hash: string | null;
  policy_id: string;
  policy_version: number;
  policy_hash: string;
  action_name: string;
  args_hash: string;
  cart_hash: string;
  quote_hash: string | null;
  purchase_attempt_id: string;
  state: ChatResponse["action_status"];
  provider_ref: string | null;
  created_at: number;
  updated_at: number;
  signature_algorithm: "HMAC-SHA256";
  signature: string;
};

export type AutopilotScenario =
  | "normal"
  | "stock_loss"
  | "price_drift"
  | "merchant_drift"
  | "fulfillment_drift"
  | "timeout_after_dispatch";

export type AutopilotResponse = {
  envelope: PurchaseEnvelope;
  quote: MerchantQuote | null;
  envelope_decision: EnvelopeDecision;
  action_status: ChatResponse["action_status"];
  grant_id: string | null;
  payment_link: string | null;
  receipt: ActionReceipt | null;
  recovery_applied: boolean;
  provider_mode: string;
};

export type Health = {
  ok: boolean;
  demo_mode: boolean;
  catalog_size: number;
  mcp: string;
};

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${API}/health`, { cache: "no-store" }).then(j<Health>),

  draftEnvelope: (goal: string, max_total_rupees: number) =>
    fetch(`${API}/envelopes/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, max_total_rupees }),
    }).then(j<PurchaseEnvelope>),

  activateEnvelope: (id: string, expected_envelope_hash: string) =>
    fetch(`${API}/envelopes/${id}/activate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_envelope_hash }),
    }).then(j<PurchaseEnvelope>),

  revokeEnvelope: (id: string, expected_version: number) =>
    fetch(`${API}/envelopes/${id}/revoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version }),
    }).then(j<PurchaseEnvelope>),

  executeAutopilot: (
    envelope: PurchaseEnvelope,
    session_id: string,
    purchase_attempt_id: string,
    scenario: AutopilotScenario,
  ) =>
    fetch(`${API}/autopilot/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        envelope_id: envelope.id,
        expected_envelope_version: envelope.version,
        expected_envelope_hash: envelope.envelope_hash,
        session_id,
        purchase_attempt_id,
        scenario,
      }),
    }).then(j<AutopilotResponse>),

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

  verifyReceipt: (grant_id: string, receipt: ActionReceipt) =>
    fetch(`${API}/receipts/${grant_id}/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(receipt),
    }).then(j<ActionReceiptVerification>),

  audit: (session_id?: string) =>
    fetch(`${API}/audit${session_id ? `?session_id=${session_id}` : ""}`, {
      cache: "no-store",
    }).then(j<AuditEvent[]>),

  authority: (user_id: string = "user_demo") =>
    fetch(`${API}/authority?user_id=${encodeURIComponent(user_id)}`, {
      cache: "no-store",
    }).then(j<AuthorityView>),
};

export const inr = (paise: number) =>
  `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
