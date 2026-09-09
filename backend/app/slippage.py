"""Demo-time control over the facts the world is allowed to change.

WHY
---
A recovery story only lands if the audience watches something actually go wrong.
Describing a substitution is a claim; depleting a shelf on stage and watching the
order repair itself is evidence. This is borrowed openly from a competing entry
(`Subhra-Nandi/apex-commerce`, `backend/app/recovery/slippage.py`), which is the
best single idea in that repository: it mutates reality mid-demo so the safety
layer has something real to recover from.

WHAT IT MAY AND MAY NOT DO
--------------------------
It moves STOCK, which is a fact about the world, and nothing else. It cannot
touch a policy, an envelope, a grant, a cap or a hash — a demo control that could
widen authority would be a back door with a friendly name, and the fact that it
is only reachable in demo mode would not make that acceptable.

Every mutation is reversible through `reset_all()`, which restores the committed
catalog rather than a remembered snapshot, so the demo survives a server restart.
"""
from __future__ import annotations

from . import catalog
from .config import get_settings


class SlippageNotPermitted(RuntimeError):
    """Raised when demo controls are reached in a configuration that forbids them."""


def _require_demo_mode() -> None:
    """Fail closed. Same guard the fault-injection scenarios use.

    Checked on every call rather than at import, because settings are reloaded
    between requests and a control that was safe at boot must not stay reachable
    after the configuration changes underneath it.
    """
    settings = get_settings()
    if not getattr(settings, "fault_injection_enabled", False):
        raise SlippageNotPermitted(
            "Demo controls require FAULT_INJECTION_ENABLED. They are unavailable in "
            "any configuration that can reach a live provider."
        )
    if getattr(settings, "payment_provider", "") not in ("simulated", ""):
        raise SlippageNotPermitted(
            "Demo controls are unavailable while a real payment provider is configured."
        )


def deplete(sku: str) -> dict[str, object]:
    """Take one SKU off the shelf. The move that makes recovery visible."""
    _require_demo_mode()
    if sku not in catalog.by_sku():
        raise LookupError(f"Unknown SKU: {sku}")
    before = catalog.available_stock(sku)
    catalog.set_stock(sku, 0)
    return {"sku": sku, "stock_before": before, "stock_now": 0, "action": "depleted"}


def set_stock(sku: str, units: int) -> dict[str, object]:
    """Set a SKU's stock to an exact number, for the 'only two left' beat."""
    _require_demo_mode()
    if sku not in catalog.by_sku():
        raise LookupError(f"Unknown SKU: {sku}")
    if units < 0:
        raise ValueError("Stock cannot be negative")
    before = catalog.available_stock(sku)
    catalog.set_stock(sku, units)
    return {"sku": sku, "stock_before": before, "stock_now": units, "action": "set"}


def reset_all() -> dict[str, object]:
    """Return every SKU to the committed catalog. Re-runnable after a restart."""
    _require_demo_mode()
    catalog.reset_stock()
    return {"action": "reset", "skus_restored": len(catalog.by_sku())}


def current_state() -> list[dict[str, object]]:
    """What the shelf looks like now, and which rows have been moved."""
    rows = []
    for product in catalog.load_catalog():
        sku = product["sku"]
        live = catalog.available_stock(sku)
        committed = int(product.get("stock", 0))
        if live != committed:
            rows.append({
                "sku": sku, "name": product["name"],
                "committed_stock": committed, "live_stock": live,
            })
    return rows
