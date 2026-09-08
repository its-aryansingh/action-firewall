"""Single-merchant public capability projection and onboarding control plane."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException
import httpx
from pydantic import BaseModel
DEFAULT_MERCHANT_ID = "merchant_freshbasket"
DEFAULT_MERCHANT_NAME = "FreshBasket for Business"
SUPPORTED_MERCHANT_IDS = {"merchant_freshbasket", "merchant_demo"}

from . import catalog, channel_policy, mcp_client
from .authorization import digest
from .buyer_models import MerchantCapabilities
from .config import get_settings
from .models import DEFAULT_FULFILLMENT_PROFILE_ID


def compute_catalog_revision() -> str:
    """Content-derived catalog revision.

    A frozen constant can never differ between quote time and checkout time, which
    makes the REQUOTE_REQUIRED guard unreachable. Deriving it from catalog content
    means any edit to data/catalog.json changes the revision and stale quotes are
    correctly refused.
    """
    return "cat_" + digest(catalog.load_catalog())[:16]


CATALOG_REVISION = compute_catalog_revision()


def get_catalog_categories() -> list[str]:
    """Dynamically derive categories from data/catalog.json (prevents D10 mismatch)."""
    items = catalog.load_catalog()
    return sorted({item.get("category", "").strip().lower() for item in items if item.get("category")})


_MERCHANT_CONNECTION_STATE: dict[str, Any] = {
    "connected": False,
    "key_id_masked": None,
    "provider_answered": "simulated",
    "verified_at": None,
    "kill_switch_toggled_at": None,
}


def reset_merchant_state() -> None:
    _MERCHANT_CONNECTION_STATE["connected"] = False
    _MERCHANT_CONNECTION_STATE["key_id_masked"] = None
    _MERCHANT_CONNECTION_STATE["provider_answered"] = "simulated"
    _MERCHANT_CONNECTION_STATE["verified_at"] = None
    _MERCHANT_CONNECTION_STATE["kill_switch_toggled_at"] = None
    channel_policy.DEFAULT_CHANNEL_POLICY["enabled"] = True


class RazorpayConnectRequest(BaseModel):
    key_id: str
    key_secret: str


class RazorpayConnectResponse(BaseModel):
    connected: bool
    merchant_name: str
    key_id_masked: str
    key_secret_masked: str
    provider_answered: str
    verified_at: float
    message: str


class OnboardingStatusResponse(BaseModel):
    store_readiness: str
    merchant_id: str
    merchant_name: str
    razorpay_connected: bool
    key_id_masked: str | None
    provider_mode: str
    catalog_summary: dict[str, Any]
    channel_policy: dict[str, Any]
    ai_channel_active: bool
    kill_switch_toggled_at: float | None


class ChannelPolicyUpdateRequest(BaseModel):
    allowed_categories: list[str] | None = None
    blocked_categories: list[str] | None = None
    max_order_rupees: float | None = None
    substitutions_allowed: bool | None = None


class ChannelToggleRequest(BaseModel):
    enabled: bool | None = None


merchant_router = APIRouter(prefix="/merchant", tags=["merchant"])


@merchant_router.post("/connect/razorpay", response_model=RazorpayConnectResponse)
def connect_razorpay(req: RazorpayConnectRequest) -> RazorpayConnectResponse:
    key_id = req.key_id.strip()
    key_secret = req.key_secret.strip()

    if not key_id.startswith("rzp_test_"):
        raise HTTPException(
            status_code=400,
            detail="Live keys are refused. Please provide Razorpay Test Mode credentials starting with 'rzp_test_'.",
        )
    if not key_secret:
        raise HTTPException(
            status_code=400,
            detail="Test Mode Key Secret is required.",
        )

    settings = get_settings()
    provider_answered = "RazorpayRESTClient"

    # In simulated / test mode, we attempt the read call against Razorpay: GET /v1/payment_links?count=1
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                "https://api.razorpay.com/v1/payment_links?count=1",
                auth=(key_id, key_secret),
            )
            if resp.status_code != 200:
                if resp.status_code in (401, 403):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Razorpay authentication failed ({resp.status_code}): Invalid Test Mode Key ID or Secret.",
                    )
                resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=400, detail=f"Razorpay API returned error: {exc}")
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        if settings.demo_mode and "demo" in key_id:
            provider_answered = "SimulatedMCPClient"
        else:
            raise HTTPException(status_code=502, detail=f"Could not connect to Razorpay: {exc}")

    settings.razorpay_key_id = key_id
    settings.razorpay_key_secret = key_secret
    if settings.payment_provider == "simulated":
        settings.payment_provider = "razorpay_rest"

    now = time.time()
    _MERCHANT_CONNECTION_STATE["connected"] = True
    _MERCHANT_CONNECTION_STATE["key_id_masked"] = f"rzp_test_...{key_id[-4:]}" if len(key_id) > 8 else "rzp_test_••••"
    _MERCHANT_CONNECTION_STATE["provider_answered"] = provider_answered
    _MERCHANT_CONNECTION_STATE["verified_at"] = now

    return RazorpayConnectResponse(
        connected=True,
        merchant_name=DEFAULT_MERCHANT_NAME,
        key_id_masked=_MERCHANT_CONNECTION_STATE["key_id_masked"],
        key_secret_masked="••••••••••••••••••••",
        provider_answered=provider_answered,
        verified_at=now,
        message="Connected to Razorpay Test Mode",
    )


@merchant_router.get("/onboarding/status", response_model=OnboardingStatusResponse)
def get_onboarding_status() -> OnboardingStatusResponse:
    settings = get_settings()
    items = catalog.load_catalog()
    in_stock_count = sum(1 for item in items if item.get("stock", 1) > 0)
    policy = channel_policy.DEFAULT_CHANNEL_POLICY
    is_connected = _MERCHANT_CONNECTION_STATE["connected"] or bool(settings.razorpay_key_id and settings.razorpay_key_secret)
    is_active = policy.get("enabled", True)

    readiness = "READY_FOR_AI_BUYERS" if (is_connected and is_active) else "CONFIGURING"

    return OnboardingStatusResponse(
        store_readiness=readiness,
        merchant_id=DEFAULT_MERCHANT_ID,
        merchant_name=DEFAULT_MERCHANT_NAME,
        razorpay_connected=is_connected,
        key_id_masked=_MERCHANT_CONNECTION_STATE["key_id_masked"] or (f"rzp_test_...{settings.razorpay_key_id[-4:]}" if settings.razorpay_key_id else None),
        provider_mode=mcp_client.get_active_provider_mode(),
        catalog_summary={
            "total_products": len(items),
            "in_stock_count": in_stock_count,
            "catalog_revision": CATALOG_REVISION,
            "categories": get_catalog_categories(),
        },
        channel_policy={
            "allowed_categories": policy["allowed_categories"],
            "blocked_categories": policy["blocked_categories"],
            "max_order_paise": policy["max_order_paise"],
            "substitutions_allowed": policy.get("substitutions_allowed", True),
            "connected_buyers": ["Gemini 3.8 Flash", "Replay buyer"],
        },
        ai_channel_active=is_active,
        kill_switch_toggled_at=_MERCHANT_CONNECTION_STATE.get("kill_switch_toggled_at"),
    )


@merchant_router.post("/channel-policy/toggle")
def toggle_ai_channel(req: ChannelToggleRequest | None = None) -> dict[str, Any]:
    current = channel_policy.DEFAULT_CHANNEL_POLICY.get("enabled", True)
    new_val = req.enabled if (req and req.enabled is not None) else not current
    channel_policy.DEFAULT_CHANNEL_POLICY["enabled"] = new_val
    now = time.time()
    _MERCHANT_CONNECTION_STATE["kill_switch_toggled_at"] = now
    status_str = "ON" if new_val else "OFF"
    return {
        "ai_channel_active": new_val,
        "toggled_at": now,
        "message": f"Merchant AI channel is now {status_str}",
    }


@merchant_router.get("/catalog/categories")
def get_categories() -> dict[str, Any]:
    cats = get_catalog_categories()
    return {
        "merchant_id": DEFAULT_MERCHANT_ID,
        "catalog_revision": CATALOG_REVISION,
        "categories": cats,
        "count": len(cats),
    }


@merchant_router.post("/channel-policy")
def update_channel_policy(req: ChannelPolicyUpdateRequest) -> dict[str, Any]:
    if req.allowed_categories is not None:
        channel_policy.DEFAULT_CHANNEL_POLICY["allowed_categories"] = [c.strip().lower() for c in req.allowed_categories]
    if req.blocked_categories is not None:
        channel_policy.DEFAULT_CHANNEL_POLICY["blocked_categories"] = [c.strip().lower() for c in req.blocked_categories]
    if req.max_order_rupees is not None:
        channel_policy.DEFAULT_CHANNEL_POLICY["max_order_paise"] = int(req.max_order_rupees * 100)
    if req.substitutions_allowed is not None:
        channel_policy.DEFAULT_CHANNEL_POLICY["substitutions_allowed"] = req.substitutions_allowed

    return {
        "status": "updated",
        "policy": channel_policy.DEFAULT_CHANNEL_POLICY,
    }


def get_merchant_capabilities(merchant_id: str = DEFAULT_MERCHANT_ID) -> MerchantCapabilities:
    """Return public merchant identity and safe gateway capabilities.

    Never returns secrets, internal policy rows, or customer identities.
    """
    settings = get_settings()
    env = "demo" if settings.demo_mode else "test"
    display_name = DEFAULT_MERCHANT_NAME if merchant_id in SUPPORTED_MERCHANT_IDS else merchant_id.replace("_", " ").title()

    return MerchantCapabilities(
        merchant_id=merchant_id,
        display_name=display_name,
        currency="INR",
        supported_currencies=["INR"],
        fulfillment_modes=["delivery", "pickup"],
        default_fulfillment_profile_id=DEFAULT_FULFILLMENT_PROFILE_ID,
        catalog_revision=CATALOG_REVISION,
        environment=env,
        payment_provider=mcp_client.get_active_provider_mode(),
        capabilities=[
            "catalog_search",
            "intent_drafting",
            "quote",
            "purchase_envelope",
            "create_payment_link",
        ],
        action_name="create_payment_link",
    )
