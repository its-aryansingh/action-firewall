"""Deterministic Replay Buyer Adapter for Action Firewall — Agent Commerce Gateway.

Simulates an external AI buyer executing deterministic, reproducible shopping flows
without external network or API key dependencies.
"""
from __future__ import annotations

import time
import uuid
from typing import Any
from pydantic import BaseModel, Field

from . import catalog
from .envelope import _deterministic_slots, _replay_slots
from .merchant import DEFAULT_MERCHANT_ID
from .models import EnvelopeSlot


class ReplayBuyerPlan(BaseModel):
    goal: str
    budget_paise: int
    understood: bool
    slots: list[EnvelopeSlot]
    selected_skus: list[str]
    reasoning: str
    mode: str = "replay"
    latency_ms: float = 0.0


class ReplayBuyer:
    """Deterministic buyer that plans intents and proposes carts from catalog facts."""

    def __init__(self, merchant_id: str = DEFAULT_MERCHANT_ID) -> None:
        self.merchant_id = merchant_id

    def plan_order(self, goal: str, budget_paise: int = 60000) -> ReplayBuyerPlan:
        start_t = time.perf_counter()
        try:
            slots = _replay_slots(goal) or _deterministic_slots(goal)
        except (ValueError, Exception):
            slots = None

        if not slots:
            return ReplayBuyerPlan(
                goal=goal,
                budget_paise=budget_paise,
                understood=False,
                slots=[],
                selected_skus=[],
                reasoning="Goal could not be mapped to eligible catalog items.",
                mode="replay",
                latency_ms=(time.perf_counter() - start_t) * 1000,
            )

        # Select matching catalog SKUs satisfying required tags
        used: set[str] = set()
        selected_skus: list[str] = []

        for slot in slots:
            req_tags = set(slot.required_tags)
            candidates = [
                item
                for item in catalog.load_catalog()
                if item["sku"] not in used and req_tags.issubset(set(item.get("tags", [])))
            ]
            if not candidates:
                candidates = [
                    item
                    for item in catalog.load_catalog()
                    if item["sku"] not in used and req_tags.intersection(set(item.get("tags", [])))
                ]
            if candidates:
                candidates.sort(key=lambda x: (x.get("price_paise", 0), x["sku"]))
                chosen = candidates[0]
                selected_skus.append(chosen["sku"])
                used.add(chosen["sku"])

        elapsed = (time.perf_counter() - start_t) * 1000
        return ReplayBuyerPlan(
            goal=goal,
            budget_paise=budget_paise,
            understood=True,
            slots=slots,
            selected_skus=selected_skus,
            reasoning=f"Matched {len(selected_skus)} in-stock catalog items satisfying {len(slots)} required slots.",
            mode="replay",
            latency_ms=round(elapsed, 2),
        )
