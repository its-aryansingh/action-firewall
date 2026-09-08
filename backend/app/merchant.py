"""Single-merchant public capability projection for external AI buyers."""
from __future__ import annotations

from . import catalog, mcp_client
from .authorization import digest
from .buyer_models import MerchantCapabilities
from .config import get_settings

DEFAULT_MERCHANT_ID = "merchant_freshbasket"
DEFAULT_MERCHANT_NAME = "FreshBasket for Business"
SUPPORTED_MERCHANT_IDS = {"merchant_freshbasket", "merchant_demo"}
def compute_catalog_revision() -> str:
    """Content-derived catalog revision.

    A frozen constant can never differ between quote time and checkout time, which
    makes the REQUOTE_REQUIRED guard unreachable. Deriving it from catalog content
    means any edit to data/catalog.json changes the revision and stale quotes are
    correctly refused.
    """
    return "cat_" + digest(catalog.load_catalog())[:16]


CATALOG_REVISION = compute_catalog_revision()


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
