"""Single-merchant public capability projection for external AI buyers."""
from __future__ import annotations

from .buyer_models import MerchantCapabilities
from .config import get_settings

DEFAULT_MERCHANT_ID = "merchant_freshbasket"
DEFAULT_MERCHANT_NAME = "FreshBasket for Business"
SUPPORTED_MERCHANT_IDS = {"merchant_freshbasket", "merchant_demo"}
CATALOG_REVISION = "cat_rev_20260905"


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
        default_fulfillment_profile_id="dest_demo",
        catalog_revision=CATALOG_REVISION,
        environment=env,
        payment_provider=settings.payment_provider,
        capabilities=[
            "catalog_search",
            "intent_drafting",
            "quote",
            "purchase_envelope",
            "create_payment_link",
        ],
        action_name="create_payment_link",
    )
