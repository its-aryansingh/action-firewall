"""Canonical hashing for policy-bound action authorization.

Only server-owned, normalized values enter these digests. A model or browser
may propose data, but neither may supply an authoritative amount or hash.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import Cart, Mandate


def canonical_json(value: Any) -> str:
    """Return one stable JSON representation for hashing and persistence."""
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def cart_payload(cart: Cart) -> list[dict[str, Any]]:
    return [
        {
            "sku": line.sku,
            "name": line.name,
            "category": line.category,
            "unit_price_paise": line.unit_price_paise,
            "qty": line.qty,
        }
        for line in sorted(cart.lines, key=lambda item: item.sku)
    ]


def cart_hash(cart: Cart) -> str:
    return digest(cart_payload(cart))


def action_args_hash(action_name: str, args: dict[str, Any]) -> str:
    return digest({"action_name": action_name, "args": args})


def policy_payload(mandate: Mandate) -> dict[str, Any]:
    return {
        "id": mandate.id,
        "user_id": mandate.user_id,
        "agent_id": mandate.agent_id,
        "label": mandate.label,
        "cap_paise": mandate.cap_paise,
        "window": mandate.window.value,
        "per_txn_cap_paise": mandate.per_txn_cap_paise,
        "allowed_categories": sorted(mandate.allowed_categories),
        "blocked_categories": sorted(mandate.blocked_categories),
        "active": mandate.active,
        "version": mandate.version,
    }


def policy_hash(mandate: Mandate) -> str:
    return digest(policy_payload(mandate))
