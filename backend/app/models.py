"""Domain models. All money is in PAISE (integer) — never float rupees.
This is deliberate: it is the first thing a Razorpay engineer looks for."""
from __future__ import annotations
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


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
    sku: str
    name: str
    category: str
    unit_price_paise: int
    qty: int = 1

    @property
    def line_total_paise(self) -> int:
        return self.unit_price_paise * self.qty


class Cart(BaseModel):
    lines: list[CartLine] = Field(default_factory=list)

    @property
    def total_paise(self) -> int:
        return sum(l.line_total_paise for l in self.lines)


class DecisionCode(str, Enum):
    ALLOW = "ALLOW"
    BLOCK_NO_MANDATE = "BLOCK_NO_MANDATE"
    BLOCK_MANDATE_REVOKED = "BLOCK_MANDATE_REVOKED"
    BLOCK_WINDOW_CAP_EXCEEDED = "BLOCK_WINDOW_CAP_EXCEEDED"
    BLOCK_PER_TXN_CAP_EXCEEDED = "BLOCK_PER_TXN_CAP_EXCEEDED"
    BLOCK_CATEGORY_NOT_ALLOWED = "BLOCK_CATEGORY_NOT_ALLOWED"


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


class ChatRequest(BaseModel):
    session_id: str
    user_id: str = "user_demo"
    agent_id: str = "agent_groceries"
    message: str


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
