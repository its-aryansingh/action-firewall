"""Domain models. All money is in PAISE (integer) — never float rupees.
This is deliberate: it is the first thing a Razorpay engineer looks for."""
from __future__ import annotations
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class Window(str, Enum):
    PER_TXN = "per_transaction"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class Mandate(BaseModel):
    """A human-authorised spending authority delegated to an AI agent.
    Models NPCI UAP / UPI Circle delegated-payer semantics."""
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
    """The outcome of asking for headroom under a mandate.

    `granted` is the only field the caller may branch on to decide whether to
    reach a money tool. `replayed` marks an idempotent retry of work that has
    already settled — the caller must return the stored result rather than
    calling Razorpay a second time.
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
    state: ActionState
    expires_at: float | None = None
    provider_ref: str | None = None
    result: dict[str, Any] | None = None
    created_at: float
    updated_at: float


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
