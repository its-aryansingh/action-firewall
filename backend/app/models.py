"""Domain models. All money is in PAISE (integer) — never float rupees.
This is deliberate: it is the first thing a Razorpay engineer looks for."""
from __future__ import annotations
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, StrictInt, computed_field, model_validator


class Window(str, Enum):
    PER_TXN = "per_transaction"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class Mandate(BaseModel):
    """A shopper-defined application policy for one AI buyer.

    The legacy class name is retained for API and database compatibility. This
    is not a banking mandate or a claim of payment-rail delegation.
    """
    id: str
    user_id: str
    agent_id: str
    label: str = "AI Groceries Agent"
    cap_paise: int = Field(..., ge=0, description="Ceiling for the window")
    window: Window = Window.WEEKLY
    per_txn_cap_paise: Optional[int] = None
    allowed_categories: list[str] = Field(default_factory=list)  # empty = all
    blocked_categories: list[str] = Field(default_factory=list)
    active: bool = True
    version: int = 1          # bumps on every edit -> revocation latency metric
    created_at: float
    updated_at: float


class CartLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    name: str
    category: str
    unit_price_paise: int = Field(..., ge=0)
    qty: StrictInt = Field(default=1, ge=1, le=100)

    @property
    def line_total_paise(self) -> int:
        return self.unit_price_paise * self.qty


class Cart(BaseModel):
    lines: list[CartLine] = Field(default_factory=list)

    @property
    def total_paise(self) -> int:
        return sum(l.line_total_paise for l in self.lines)


class CartOperation(BaseModel):
    """Strict planner output. Model data is untrusted until this parses."""
    model_config = ConfigDict(extra="forbid")

    op: Literal["add", "remove", "clear"]
    sku: str | None = None
    qty: StrictInt = Field(default=1, ge=1, le=100)

    @model_validator(mode="after")
    def validate_shape(self) -> "CartOperation":
        if self.op == "clear":
            if self.sku is not None:
                raise ValueError("clear must not name a SKU")
        elif not self.sku:
            raise ValueError(f"{self.op} requires a SKU")
        return self


class PlannerOutput(BaseModel):
    """The model may propose cart operations, never transaction authority."""
    model_config = ConfigDict(extra="forbid")

    reply: str
    cart_ops: list[CartOperation] = Field(default_factory=list)
    intent: Literal["discover", "checkout"] = "discover"


class DecisionCode(str, Enum):
    ALLOW = "ALLOW"
    BLOCK_NO_MANDATE = "BLOCK_NO_MANDATE"
    BLOCK_MANDATE_REVOKED = "BLOCK_MANDATE_REVOKED"
    BLOCK_WINDOW_CAP_EXCEEDED = "BLOCK_WINDOW_CAP_EXCEEDED"
    BLOCK_PER_TXN_CAP_EXCEEDED = "BLOCK_PER_TXN_CAP_EXCEEDED"
    BLOCK_CATEGORY_NOT_ALLOWED = "BLOCK_CATEGORY_NOT_ALLOWED"
    BLOCK_STALE_POLICY_VERSION = "BLOCK_STALE_POLICY_VERSION"
    BLOCK_CART_CHANGED = "BLOCK_CART_CHANGED"
    BLOCK_INVALID_ACTION = "BLOCK_INVALID_ACTION"


class EnvelopeStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    CONSUMED = "consumed"
    REVOKED = "revoked"


class EnvelopeSlot(BaseModel):
    """A server-normalized requirement that a quote must satisfy exactly once."""
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    required_tags: list[str] = Field(..., min_length=1)
    quantity: StrictInt = Field(default=1, ge=1, le=20)


class PurchaseEnvelope(BaseModel):
    """One revocable shopper approval for one bounded purchase job."""
    id: str
    user_id: str
    agent_id: str
    label: str
    goal: str
    merchant_id: str
    currency: Literal["INR"] = "INR"
    max_total_paise: int = Field(..., gt=0)
    fulfillment_profile_id: str
    delivery_deadline: float
    expires_at: float
    slots: list[EnvelopeSlot] = Field(..., min_length=1)
    blocked_categories: list[str] = Field(default_factory=list)
    max_purchases: Literal[1] = 1
    action_name: Literal["create_payment_link"] = "create_payment_link"
    status: EnvelopeStatus
    version: int = Field(..., ge=1)
    envelope_hash: str
    mandate_id: str | None = None
    created_at: float
    updated_at: float


class EnvelopeDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., min_length=3, max_length=280)
    max_total_rupees: StrictInt = Field(..., ge=1, le=1_000_000)
    merchant_id: Literal["merchant_demo"] = "merchant_demo"
    fulfillment_profile_id: Literal["saved_office"] = "saved_office"
    expires_in_minutes: StrictInt = Field(default=30, ge=5, le=1440)
    delivery_in_minutes: StrictInt = Field(default=45, ge=15, le=1440)
    user_id: str = "user_demo"


class EnvelopeActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_envelope_hash: str = Field(..., min_length=64, max_length=64)


class EnvelopeRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(..., ge=1)


class QuoteSubstitution(BaseModel):
    slot_id: str
    selected_sku: str
    preferred_sku: str | None = None
    reason: str


class MerchantQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_id: str
    currency: Literal["INR"] = "INR"
    fulfillment_profile_id: str
    delivery_eta: float
    cart: Cart
    substitutions: list[QuoteSubstitution] = Field(default_factory=list)
    quote_hash: str


class PolicyDelta(BaseModel):
    field: str
    expected: str
    actual: str
    recovery: Literal["repair", "fresh_approval", "stop"]


class EnvelopeDecision(BaseModel):
    allowed: bool
    code: str
    envelope_id: str
    envelope_version: int
    quote_total_paise: int
    deltas: list[PolicyDelta] = Field(default_factory=list)
    human_message: str


class AutopilotScenario(str, Enum):
    NORMAL = "normal"
    STOCK_LOSS = "stock_loss"
    PRICE_DRIFT = "price_drift"
    MERCHANT_DRIFT = "merchant_drift"
    FULFILLMENT_DRIFT = "fulfillment_drift"
    TIMEOUT_AFTER_DISPATCH = "timeout_after_dispatch"


class AutopilotExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope_id: str
    expected_envelope_version: int = Field(..., ge=1)
    expected_envelope_hash: str = Field(..., min_length=64, max_length=64)
    session_id: str
    idempotency_key: str | None = None
    scenario: AutopilotScenario = AutopilotScenario.NORMAL


class MandateDecision(BaseModel):
    """The single object the agent is allowed to act on. If allowed is False,
    no Razorpay MCP tool is ever reached — the block is at the logic layer."""
    allowed: bool
    code: DecisionCode
    mandate_id: Optional[str] = None
    mandate_version: Optional[int] = None
    cart_total_paise: int = 0
    cap_paise: int = 0
    already_spent_paise: int = 0
    headroom_paise: int = 0
    offending_skus: list[str] = Field(default_factory=list)
    human_message: str = ""

    @property
    def is_breach(self) -> bool:
        return not self.allowed and self.code != DecisionCode.ALLOW


class Reservation(BaseModel):
    """Legacy helper result for asking for headroom under an application policy.

    `granted` is the only field the caller may branch on to decide whether to
    reach a money tool. `replayed` marks an idempotent retry of work that has
    already reached the helper's committed state; the caller must return the
    stored result rather than calling the provider a second time.
    """
    granted: bool
    id: Optional[str] = None
    mandate_id: Optional[str] = None
    amount_paise: int = 0
    replayed: bool = False
    razorpay_ref: Optional[str] = None
    headroom_paise: int = 0
    reason: str = ""


class ActionState(str, Enum):
    AUTHORIZED = "authorized"
    DISPATCHING = "dispatching"
    ACTION_ISSUED = "action_issued"
    SETTLED = "settled"
    DEFINITIVE_FAILURE = "definitive_failure"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"


class ActionContext(BaseModel):
    """Server-side identity presented to the actuator with an opaque grant."""
    model_config = ConfigDict(extra="forbid")

    user_id: str
    agent_id: str
    session_id: str
    merchant_id: str = "merchant_demo"


class AuthorizationRequest(BaseModel):
    """Canonical action presented to the atomic policy-and-reservation gate."""
    model_config = ConfigDict(extra="forbid")

    context: ActionContext
    mandate_id: str
    expected_mandate_version: int = Field(..., ge=1)
    action_name: str
    action_schema_hash: str
    args: dict[str, Any]
    cart: Cart
    cart_hash: str
    purchase_attempt_id: str
    envelope_id: str | None = None
    expected_envelope_version: int | None = Field(default=None, ge=1)
    expected_envelope_hash: str | None = None
    quote: MerchantQuote | None = None
    ttl_seconds: int = Field(default=180, ge=1, le=900)


class ActionGrant(BaseModel):
    """Opaque, exact-bound, one-use authority for one adapter action."""
    id: str
    mandate_id: str
    mandate_version: int
    policy_hash: str
    user_id: str
    agent_id: str
    session_id: str
    merchant_id: str
    action_name: str
    action_schema_hash: str
    args_hash: str
    cart_hash: str
    amount_paise: int = Field(..., ge=0)
    currency: str
    purchase_attempt_id: str
    envelope_id: str | None = None
    envelope_version: int | None = None
    envelope_hash: str | None = None
    quote_hash: str | None = None
    state: ActionState
    expires_at: float | None = None
    provider_ref: str | None = None
    result: dict[str, Any] | None = None
    created_at: float
    updated_at: float


class ReceiptAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grant_id: str
    envelope_id: str | None = None
    envelope_version: int | None = None
    envelope_hash: str | None = None
    policy_id: str
    policy_version: int
    policy_hash: str
    action_name: str
    args_hash: str
    cart_hash: str
    quote_hash: str | None = None
    purchase_attempt_id: str
    created_at: float


class ReceiptStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ActionState
    provider_ref: str | None = None
    updated_at: float


class ActionReceipt(BaseModel):
    grant_id: str
    envelope_id: str | None = None
    envelope_version: int | None = None
    envelope_hash: str | None = None
    policy_id: str
    policy_version: int
    policy_hash: str
    action_name: str
    args_hash: str
    cart_hash: str
    quote_hash: str | None = None
    purchase_attempt_id: str
    created_at: float

    state: ActionState
    provider_ref: str | None = None
    updated_at: float

    authorization_signature: str
    status_signature: str
    signature: str = ""
    signature_algorithm: Literal["HMAC-SHA256"] = "HMAC-SHA256"

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            auth = data.get("authorization")
            if isinstance(auth, dict):
                for k, v in auth.items():
                    data.setdefault(k, v)
            st = data.get("status")
            if isinstance(st, dict):
                for k, v in st.items():
                    data.setdefault(k, v)
            if not data.get("signature") and data.get("authorization_signature"):
                data["signature"] = data["authorization_signature"]
            elif not data.get("authorization_signature") and data.get("signature"):
                data["authorization_signature"] = data["signature"]
            if not data.get("status_signature") and data.get("signature"):
                data["status_signature"] = data["signature"]
        return data

    @computed_field
    @property
    def authorization(self) -> ReceiptAuthorization:
        return ReceiptAuthorization(
            grant_id=self.grant_id,
            envelope_id=self.envelope_id,
            envelope_version=self.envelope_version,
            envelope_hash=self.envelope_hash,
            policy_id=self.policy_id,
            policy_version=self.policy_version,
            policy_hash=self.policy_hash,
            action_name=self.action_name,
            args_hash=self.args_hash,
            cart_hash=self.cart_hash,
            quote_hash=self.quote_hash,
            purchase_attempt_id=self.purchase_attempt_id,
            created_at=self.created_at,
        )

    @computed_field
    @property
    def status(self) -> ReceiptStatus:
        return ReceiptStatus(
            state=self.state,
            provider_ref=self.provider_ref,
            updated_at=self.updated_at,
        )


class ActionReceiptVerification(BaseModel):
    valid: bool
    authorization_valid: bool
    status_current: bool
    status_as_of: float
    grant_id: str
    application_signed: bool = True

    def __bool__(self) -> bool:
        return self.authorization_valid


class AutopilotExecuteResponse(BaseModel):
    envelope: PurchaseEnvelope
    quote: MerchantQuote | None = None
    envelope_decision: EnvelopeDecision
    action_status: ActionState | None = None
    grant_id: str | None = None
    payment_link: str | None = None
    receipt: ActionReceipt | None = None
    recovery_applied: bool = False
    provider_mode: str


class AuthorizationOutcome(BaseModel):
    authorized: bool
    decision: MandateDecision
    grant: ActionGrant | None = None
    replayed: bool = False
    in_progress: bool = False
    reason: str = ""


class ChatRequest(BaseModel):
    session_id: str
    user_id: str = "user_demo"
    agent_id: str = "agent_groceries"
    message: str
    # Stripe-style: the client may pin the identity of a purchase attempt so a
    # dropped response can be safely re-sent. If omitted we derive one that is
    # scoped to this session, because two shoppers buying the same basket are
    # two purchases, not one retry.
    idempotency_key: Optional[str] = None


class CheckoutConfirmRequest(BaseModel):
    """Explicit user confirmation for the exact cart currently in a session."""
    model_config = ConfigDict(extra="forbid")

    session_id: str
    expected_cart_hash: str
    idempotency_key: str | None = None


class ToolInvocation(BaseModel):
    name: str
    args: dict
    result: dict | None = None
    blocked: bool = False


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    cart: Cart
    decision: MandateDecision | None = None
    tools: list[ToolInvocation] = Field(default_factory=list)
    trace_url: str | None = None
    cart_hash: str = ""
    confirmation_required: bool = False
    action_status: ActionState | None = None
    grant_id: str | None = None


class MandateCreate(BaseModel):
    user_id: str = "user_demo"
    agent_id: str = "agent_groceries"
    label: str = "AI Groceries Agent"
    cap_rupees: int = 1000
    window: Window = Window.WEEKLY
    per_txn_cap_rupees: Optional[int] = None
    allowed_categories: list[str] = Field(default_factory=list)
    blocked_categories: list[str] = Field(default_factory=list)


class MandateUpdate(BaseModel):
    cap_rupees: Optional[int] = None
    per_txn_cap_rupees: Optional[int] = None
    active: Optional[bool] = None
    allowed_categories: Optional[list[str]] = None
    blocked_categories: Optional[list[str]] = None
