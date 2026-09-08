"""Strict Pydantic schemas for the Agent Commerce Gateway external buyer surface."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from .models import (
    DEFAULT_FULFILLMENT_PROFILE_ID,
    ActionReceipt,
    AutopilotScenario,
    Cart,
    EnvelopeDecision,
    PolicyDelta,
    PurchaseEnvelope,
    QuoteSubstitution,
)


class MerchantCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_id: str
    display_name: str
    currency: str = "INR"
    supported_currencies: list[str] = Field(default_factory=lambda: ["INR"])
    fulfillment_modes: list[str] = Field(default_factory=lambda: ["delivery", "pickup"])
    default_fulfillment_profile_id: str = DEFAULT_FULFILLMENT_PROFILE_ID
    catalog_revision: str
    environment: str
    payment_provider: str
    capabilities: list[str] = Field(
        default_factory=lambda: [
            "catalog_search",
            "intent_drafting",
            "quote",
            "purchase_envelope",
            "create_payment_link",
        ]
    )
    action_name: str = "create_payment_link"


class CatalogSearchResponseItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    name: str
    category: str
    price_paise: int
    in_stock: bool
    tags: list[str] = Field(default_factory=list)
    revision: str = "cat_rev_20260905"


class IntentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_request_id: str = Field(..., min_length=1)
    buyer_agent_id: str | None = None
    shopper_session_id: str = "sess_demo"
    natural_language_intent: str = Field(..., min_length=1)
    voice_transcript: str | None = None
    budget_paise: int | None = Field(default=None, ge=100)
    merchant_id: str = "merchant_freshbasket"
    idempotency_key: str | None = None


class IntentCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str
    agent_request_id: str
    buyer_agent_id: str
    shopper_session_id: str
    natural_language_intent: str
    normalized_intent: dict[str, Any]
    missing_fields: list[str] = Field(default_factory=list)
    draft_envelope: PurchaseEnvelope | None = None
    evidence_mode: str
    message: str
    provider_action_called: bool = False


class QuoteItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    quantity: StrictInt = Field(default=1, ge=1, le=100)


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_id: str = "merchant_freshbasket"
    fulfillment_profile_id: str = DEFAULT_FULFILLMENT_PROFILE_ID
    items: list[QuoteItemRequest] = Field(..., min_length=1)
    envelope_id: str | None = None


class QuoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_id: str
    merchant_id: str
    currency: str = "INR"
    fulfillment_profile_id: str
    cart: Cart
    substitutions: list[QuoteSubstitution] = Field(default_factory=list)
    total_paise: int
    quote_hash: str
    valid_until: float


class CommerceAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope_id: str
    quote_id: str | None = None
    purchase_attempt_id: str = Field(..., min_length=1)
    buyer_agent_id: str | None = None
    shopper_session_id: str = "sess_demo"
    scenario: AutopilotScenario = AutopilotScenario.NORMAL
    candidate_cart: Cart | None = None
    expected_envelope_version: int | None = None
    expected_envelope_hash: str | None = None


class CommerceAttemptStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["understand", "quote", "authorize", "razorpay_action"]
    name: str
    status: Literal["pending", "completed", "blocked", "failed", "unknown"]
    detail: str


class CommerceAttemptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str
    envelope_id: str
    outcome: str
    stages: list[CommerceAttemptStage]
    allowed: bool
    code: str
    human_message: str
    quote_total_paise: int
    payment_link: str | None = None
    grant_id: str | None = None
    receipt: ActionReceipt | None = None
    deltas: list[PolicyDelta] = Field(default_factory=list)
    recovery_applied: bool = False
    provider_mode: str
    razorpay_action_called: bool = False


class AgentCommerceMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    agent_gmv_issued_paise: int
    settled_agent_gmv_paise: int
    agent_orders_count: int
    orders_recovered_count: int
    unsafe_attempts_blocked_count: int
    unknown_attempts_count: int
    evidence_mode: str
    generated_at: float
    store_readiness: str = "READY_FOR_AI_BUYERS"
    unknown_exposure_paise: int = 0
    funnel: list[dict[str, Any]] = Field(default_factory=list)
    needs_attention: list[dict[str, Any]] = Field(default_factory=list)


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = "user_demo"
    ttl_seconds: int = 3600
    session_id: str | None = None


class SessionCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    token: str
    user_id: str
    expires_at: float


class BuyerPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., min_length=3, max_length=280)
    budget_paise: int = Field(default=60000, ge=100)
    buyer_mode: Literal["auto", "openai", "replay"] = "auto"
    shopper_session_id: str | None = None


class BuyerPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    budget_paise: int
    understood: bool
    slots: list[dict[str, Any]]
    suggested_skus: list[str]
    quote_total_paise: int | None = None
    reasoning: str
    mode_used: str
    fallback_reason: str | None = None
    latency_ms: float


