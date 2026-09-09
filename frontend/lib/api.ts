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
  payment_provider: "simulated" | "razorpay_mcp";
  catalog_retrieval_mode: "keyword" | "pinecone";
  envelope_drafting_mode: "deterministic" | "llm" | "replay";
  voice_ai_configured: boolean;
  voice_transcription_model: string;
  fault_injection_enabled: boolean;
  mcp: string;
};

export type VoiceTranscription = {
  text: string;
  provider: "openai";
  model: string;
  draft_only: true;
};

export type MerchantCapabilities = {
  merchant_id: string;
  display_name: string;
  currency: string;
  default_fulfillment_profile_id: string;
  supported_destinations?: string[];
  capabilities: string[];
  action_name: string;
  catalog_revision: string;
  store_readiness?: string;
  payment_provider?: string;
  environment?: string;
};

export type CatalogItem = {
  sku: string;
  name: string;
  category: string;
  price_paise: number;
  in_stock: boolean;
  tags: string[];
  description: string;
};

export type FunnelStep = {
  stage: string;
  count: number;
  conversion_rate: number;
};

export type NeedsAttentionItem = {
  item_id: string;
  item_type: "unknown_outcome" | "policy_delta_blocked" | "stale_attempt" | string;
  attempt_id: string;
  severity: "high" | "medium" | "low";
  title: string;
  detail: string;
  action_required: string;
  created_at: number;
};

export type AgentOrderSummary = {
  order_id: string;
  purchase_attempt_id: string;
  envelope_id: string | null;
  merchant_id: string;
  buyer_agent_id: string;
  shopper_session_id: string;
  status: "issued" | "recovered" | "blocked" | "unknown" | "settled";
  outcome: string;
  amount_paise: number;
  recovery_applied: boolean;
  payment_link: string | null;
  grant_id: string | null;
  receipt_id: string | null;
  code: string | null;
  created_at: number;
  updated_at?: number;
};

export type ComprehensiveMetrics = {
  merchant_id: string;
  evidence_mode: string;
  store_readiness: string;
  agent_gmv_issued_paise: number;
  settled_agent_gmv_paise: number;
  agent_orders_count: number;
  orders_recovered_count: number;
  unsafe_attempts_blocked_count: number;
  unknown_attempts_count: number;
  unknown_exposure_paise: number;
  funnel: FunnelStep[];
  needs_attention: NeedsAttentionItem[];
  recent_orders: AgentOrderSummary[];
  generated_at: number;
};

export type CommerceAttemptStage = {
  stage: "understand" | "quote" | "authorize" | "razorpay_action";
  name: string;
  status: "pending" | "completed" | "blocked" | "unknown";
  detail: string;
};

export type CommerceAttemptResponse = {
  attempt_id: string;
  envelope_id: string;
  outcome: "ACTION_ISSUED" | "RECOVERED_INSIDE_ENVELOPE" | "POLICY_DELTA_REQUIRED" | "STOPPED_BEFORE_RAZORPAY" | "UNKNOWN" | "READY_FOR_CHECKOUT";
  stages: CommerceAttemptStage[];
  allowed: boolean;
  code: string;
  human_message: string;
  quote_total_paise: number;
  payment_link: string | null;
  grant_id: string | null;
  receipt: ActionReceipt | null;
  deltas: PolicyDelta[];
  recovery_applied: boolean;
  provider_mode: string;
  razorpay_action_called: boolean;
};

export type IntentCreateResponse = {
  agent_request_id: string;
  draft_envelope: PurchaseEnvelope;
  missing_fields: string[];
  evidence_mode: string;
  message: string;
  provider_action_called: boolean;
};

export type PolicySummary = {
  money_in: {
    merchant_id: string;
    merchant_name: string;
    full_merchant_name: string;
    max_order_paise: number;
    currency: string;
    blocked_tags: string[];
    allowed_categories: string[];
    action_name: string;
  };
  money_out: {
    enabled: boolean;
    max_refund_paise: number;
    window_days: number;
    daily_cap_paise: number;
    escalate_reasons: string[];
    action_name: string;
  };
};

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${API}/health`, { cache: "no-store" }).then(j<Health>),

  transcribeVoice: (audio: Blob) =>
    fetch(`${API}/voice/transcribe`, {
      method: "POST",
      headers: { "Content-Type": audio.type || "audio/webm" },
      body: audio,
    }).then(j<VoiceTranscription>),

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

  agentCommerce: {
    policySummary: () =>
      fetch(`${API}/agent-commerce/v1/permissions/policy-summary`, { cache: "no-store" }).then(j<PolicySummary>),

    merchant: () =>
      fetch(`${API}/agent-commerce/v1/merchant`, { cache: "no-store" }).then(j<MerchantCapabilities>),

    metrics: () =>
      fetch(`${API}/agent-commerce/v1/metrics`, { cache: "no-store" }).then(j<ComprehensiveMetrics>),

    getApproval: (token: string) =>
      fetch(`${API}/agent-commerce/v1/approvals/${encodeURIComponent(token)}`, { cache: "no-store" }).then(
        j<{
          token: string;
          envelope_id: string;
          envelope_hash: string;
          expires_at: number;
          redeemed_at: number | null;
          expired: boolean;
          redeemed: boolean;
          envelope: PurchaseEnvelope | null;
        }>
      ),

    redeemApproval: (token: string) =>
      fetch(`${API}/agent-commerce/v1/approvals/${encodeURIComponent(token)}/redeem`, {
        method: "POST",
      }).then(j<PurchaseEnvelope>),

    orders: (status?: string) =>
      fetch(`${API}/agent-commerce/v1/orders${status ? `?status=${encodeURIComponent(status)}` : ""}`, {
        cache: "no-store",
      }).then(j<AgentOrderSummary[]>),

    catalog: (q?: string) =>
      fetch(`${API}/agent-commerce/v1/catalog/search${q ? `?q=${encodeURIComponent(q)}` : ""}`, {
        cache: "no-store",
      }).then(j<CatalogItem[]>),

    getAttempt: (id: string) =>
      fetch(`${API}/agent-commerce/v1/attempts/${encodeURIComponent(id)}`, { cache: "no-store" }).then(
        j<CommerceAttemptResponse>
      ),

    createIntent: (req: {
      agent_request_id: string;
      natural_language_intent: string;
      budget_paise?: number;
      buyer_agent_id?: string;
      shopper_session_id?: string;
      merchant_id?: string;
    }) =>
      fetch(`${API}/agent-commerce/v1/intents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      }).then(j<IntentCreateResponse>),

    activateEnvelope: (envelopeId: string, expected_envelope_hash: string) =>
      fetch(`${API}/agent-commerce/v1/envelopes/${envelopeId}/activate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_envelope_hash }),
      }).then(j<PurchaseEnvelope>),

    submitAttempt: (req: {
      envelope_id: string;
      purchase_attempt_id: string;
      scenario?: AutopilotScenario;
      buyer_agent_id?: string;
      shopper_session_id?: string;
    }) =>
      fetch(`${API}/agent-commerce/v1/attempts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      }).then(j<CommerceAttemptResponse>),

    planBuyer: (req: {
      goal: string;
      merchant_id?: string;
      buyer_type?: "replay" | "openai";
    }) =>
      fetch(`${API}/agent-commerce/v1/buyer/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      }).then(j<{ plan: any; model_used: string; latency_ms: number; raw_plan_untrusted: boolean }>),

    getRefundPolicy: () =>
      fetch(`${API}/agent-commerce/v1/refunds/policy`, { cache: "no-store" }).then(j<RefundPolicy>),

    evaluateRefund: (req: {
      payment_id: string;
      amount_paise: number;
      reason: string;
      original_amount_paise?: number;
      already_refunded_paise?: number;
      order_age_days?: number;
    }) =>
      fetch(`${API}/agent-commerce/v1/refunds/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      }).then(j<RefundEvaluateResponse>),

    executeRefund: (req: {
      payment_id: string;
      amount_paise: number;
      reason: string;
      attempt_id: string;
      auto_repair?: boolean;
      original_amount_paise?: number;
      already_refunded_paise?: number;
    }) =>
      fetch(`${API}/agent-commerce/v1/refunds/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      }).then(j<RefundExecuteResponse>),

    getSlippageState: () =>
      fetch(`${API}/agent-commerce/v1/demo/slippage/state`, { cache: "no-store" }).then(j<SlippageItem[]>),

    depleteStock: (sku: string) =>
      fetch(`${API}/agent-commerce/v1/demo/slippage/deplete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sku }),
      }).then(j<any>),

    resetStock: () =>
      fetch(`${API}/agent-commerce/v1/demo/slippage/reset`, {
        method: "POST",
      }).then(j<any>),

    costModel: () =>
      fetch(`${API}/agent-commerce/v1/metrics/cost-model`, { cache: "no-store" }).then(j<CostModelResponse>),
  },
};

export type RefundPolicy = {
  id: string;
  merchant_id: string;
  max_refund_paise: number;
  max_refund_ratio: number;
  window_days: number;
  daily_cap_paise: number;
  escalate_reasons: string[];
  version: number;
  policy_hash: string;
};

export type RefundProposal = {
  payment_id: string;
  amount_paise: number;
  reason: string;
  original_amount_paise: number;
  already_refunded_paise: number;
  order_age_days: number;
  refunded_today_paise: number;
};

export type RefundEvaluateResponse = {
  allowed: boolean;
  code: string;
  human_message: string;
  decision: any;
  proposal: RefundProposal;
  repaired_proposal: RefundProposal | null;
  policy_hash: string;
};

export type RefundExecuteResponse = {
  allowed: boolean;
  outcome: string;
  code: string;
  human_message: string;
  refund_id: string | null;
  amount_paise: number;
  payment_id: string;
  razorpay_action_called: boolean;
  repaired: boolean;
  decision?: any;
};

export type SlippageItem = {
  sku: string;
  name: string;
  committed_stock: number;
  live_stock: number;
};

export type CostModelResponse = {
  comparison: {
    assumptions: Record<string, any>;
    configurations: Record<string, {
      violations_authorised_paise: number;
      legitimate_refused_paise: number;
      revenue_kept_by_repair_paise: number;
      total_paise: number;
    }>;
    lowest_cost: string;
    highest_cost: string;
    difference_paise: number;
    caveat: string;
  };
  sensitivity: {
    baseline_winner: string;
    ordering_is_robust: boolean;
    assumptions_that_change_the_answer: string[];
    per_assumption: Record<string, any>;
  };
};

export const inr = (paise: number) =>
  `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
