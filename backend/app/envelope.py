"""Deterministic Purchase Envelope drafting, quoting, and verification.

The language model may help turn a shopper goal into a draft. Every fact used
to authorize money is then rehydrated from the server-owned catalog and checked
here without model judgment.
"""
from __future__ import annotations

import json
import re
import time
import uuid

from pydantic import ValidationError

from . import catalog
from .authorization import digest
from .config import get_settings
from .models import (
    AutopilotScenario,
    Cart,
    CartLine,
    EnvelopeDecision,
    EnvelopeDraftRequest,
    EnvelopeSlot,
    EnvelopeStatus,
    MerchantQuote,
    PolicyDelta,
    PurchaseEnvelope,
    QuoteSubstitution,
)

ENVELOPE_AGENT_ID = "agent_safe_autopilot"


def envelope_payload(envelope: PurchaseEnvelope) -> dict[str, object]:
    return {
        "id": envelope.id,
        "user_id": envelope.user_id,
        "agent_id": envelope.agent_id,
        "label": envelope.label,
        "goal": envelope.goal,
        "merchant_id": envelope.merchant_id,
        "currency": envelope.currency,
        "max_total_paise": envelope.max_total_paise,
        "fulfillment_profile_id": envelope.fulfillment_profile_id,
        "delivery_deadline": envelope.delivery_deadline,
        "expires_at": envelope.expires_at,
        "slots": [slot.model_dump(mode="json") for slot in envelope.slots],
        "blocked_categories": sorted(envelope.blocked_categories),
        "max_purchases": envelope.max_purchases,
        "action_name": envelope.action_name,
        "status": envelope.status.value,
        "version": envelope.version,
        "mandate_id": envelope.mandate_id,
    }


def compute_envelope_hash(envelope: PurchaseEnvelope) -> str:
    return digest(envelope_payload(envelope))


def quote_payload(quote: MerchantQuote) -> dict[str, object]:
    return {
        "merchant_id": quote.merchant_id,
        "currency": quote.currency,
        "fulfillment_profile_id": quote.fulfillment_profile_id,
        "delivery_eta": quote.delivery_eta,
        "cart": quote.cart.model_dump(mode="json"),
        "substitutions": [item.model_dump(mode="json") for item in quote.substitutions],
    }


def compute_quote_hash(quote: MerchantQuote) -> str:
    return digest(quote_payload(quote))


def _llm_slots(goal: str) -> list[EnvelopeSlot] | None:
    settings = get_settings()
    if not settings.openai_api_key or settings.demo_mode:
        return None
    tag_vocabulary = sorted(
        {tag for item in catalog.load_catalog() for tag in item.get("tags", [])}
    )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Convert a shopping goal into 1 to 4 required purchase slots. "
                        "Use only tags from TAG_VOCABULARY. This is a draft, never an "
                        "authorization. Return JSON: {\"slots\":[{\"id\":str,"
                        "\"label\":str,\"required_tags\":[str],\"quantity\":int}]}."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"goal": goal, "tag_vocabulary": tag_vocabulary},
                        separators=(",", ":"),
                    ),
                },
            ],
        )
        raw = json.loads(response.choices[0].message.content)
        slots = [EnvelopeSlot.model_validate(item) for item in raw.get("slots", [])]
        if 1 <= len(slots) <= 4:
            return slots
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError, KeyError):
        return None
    except Exception:
        return None
    return None


def _deterministic_slots(goal: str) -> list[EnvelopeSlot]:
    low = goal.lower()
    if "pasta" in low:
        return [
            EnvelopeSlot(
                id="pasta", label="Pasta", required_tags=["pasta", "staple"]
            ),
            EnvelopeSlot(
                id="sauce", label="Tomato pasta sauce", required_tags=["pasta", "sauce"]
            ),
            EnvelopeSlot(
                id="herb",
                label="Fresh Italian herb",
                required_tags=["italian", "fresh", "herb"],
            ),
        ]

    vocabulary = {
        tag.lower()
        for item in catalog.load_catalog()
        for tag in item.get("tags", [])
    }
    tokens = [token for token in re.findall(r"[a-z]+", low) if token in vocabulary]
    tag = tokens[0] if tokens else "staple"
    return [
        EnvelopeSlot(
            id="requested_item",
            label=f"Item matching {tag}",
            required_tags=[tag],
        )
    ]


def draft_envelope(req: EnvelopeDraftRequest, now: float | None = None) -> PurchaseEnvelope:
    created = time.time() if now is None else now
    slots = _llm_slots(req.goal) or _deterministic_slots(req.goal)
    draft = PurchaseEnvelope(
        id=f"env_{uuid.uuid4().hex}",
        user_id=req.user_id,
        agent_id=ENVELOPE_AGENT_ID,
        label="Safe Autopilot purchase",
        goal=req.goal,
        merchant_id=req.merchant_id,
        max_total_paise=req.max_total_rupees * 100,
        fulfillment_profile_id=req.fulfillment_profile_id,
        delivery_deadline=created + req.delivery_in_minutes * 60,
        expires_at=created + req.expires_in_minutes * 60,
        slots=slots,
        blocked_categories=["gift_cards"],
        status=EnvelopeStatus.DRAFT,
        version=1,
        envelope_hash="",
        created_at=created,
        updated_at=created,
    )
    return draft.model_copy(update={"envelope_hash": compute_envelope_hash(draft)})


def _eligible_products(slot: EnvelopeSlot, blocked: set[str]) -> list[dict]:
    required = set(slot.required_tags)
    products = [
        item
        for item in catalog.load_catalog()
        if item["category"] not in blocked
        and required.issubset(set(item.get("tags", [])))
    ]
    return sorted(products, key=lambda item: (item["price_paise"], item["sku"]))


def build_quote(
    envelope: PurchaseEnvelope,
    scenario: AutopilotScenario = AutopilotScenario.NORMAL,
    now: float | None = None,
) -> tuple[MerchantQuote, bool]:
    """Build the cheapest eligible quote and recover deterministically from stock loss."""
    quoted_at = time.time() if now is None else now
    used: set[str] = set()
    lines: list[CartLine] = []
    substitutions: list[QuoteSubstitution] = []
    recovery_applied = False

    for slot in envelope.slots:
        candidates = [
            item
            for item in _eligible_products(slot, set(envelope.blocked_categories))
            if item["sku"] not in used
        ]
        if not candidates:
            continue
        preferred = candidates[0]
        selected = preferred
        if scenario is AutopilotScenario.STOCK_LOSS and not recovery_applied:
            if len(candidates) > 1:
                selected = candidates[1]
                recovery_applied = True
                substitutions.append(
                    QuoteSubstitution(
                        slot_id=slot.id,
                        preferred_sku=preferred["sku"],
                        selected_sku=selected["sku"],
                        reason="Preferred SKU unavailable; selected next eligible catalog item.",
                    )
                )
        used.add(selected["sku"])
        price = int(selected["price_paise"])
        if scenario is AutopilotScenario.PRICE_DRIFT and not lines:
            price += envelope.max_total_paise
        lines.append(
            CartLine(
                sku=selected["sku"],
                name=selected["name"],
                category=selected["category"],
                unit_price_paise=price,
                qty=slot.quantity,
            )
        )

    quote = MerchantQuote(
        merchant_id=(
            "merchant_unapproved"
            if scenario is AutopilotScenario.MERCHANT_DRIFT
            else envelope.merchant_id
        ),
        fulfillment_profile_id=(
            "unknown_address"
            if scenario is AutopilotScenario.FULFILLMENT_DRIFT
            else envelope.fulfillment_profile_id
        ),
        # The demo quote is stable across a network retry, so the same
        # idempotency identity replays instead of conflicting on a timestamp.
        delivery_eta=min(envelope.delivery_deadline, envelope.created_at + 30 * 60),
        cart=Cart(lines=lines),
        substitutions=substitutions,
        quote_hash="",
    )
    return quote.model_copy(update={"quote_hash": compute_quote_hash(quote)}), recovery_applied


def verify_quote(envelope: PurchaseEnvelope, quote: MerchantQuote, now: float | None = None) -> EnvelopeDecision:
    checked_at = time.time() if now is None else now
    deltas: list[PolicyDelta] = []

    def delta(field: str, expected: object, actual: object, recovery: str) -> None:
        deltas.append(
            PolicyDelta(
                field=field,
                expected=str(expected),
                actual=str(actual),
                recovery=recovery,
            )
        )

    if envelope.status is not EnvelopeStatus.ACTIVE:
        delta("status", EnvelopeStatus.ACTIVE.value, envelope.status.value, "stop")
    if checked_at >= envelope.expires_at:
        delta("expires_at", f"> {checked_at:.0f}", f"{envelope.expires_at:.0f}", "stop")
    if quote.quote_hash != compute_quote_hash(quote):
        delta("quote_hash", "canonical quote digest", quote.quote_hash, "stop")
    if quote.merchant_id != envelope.merchant_id:
        delta("merchant_id", envelope.merchant_id, quote.merchant_id, "fresh_approval")
    if quote.currency != envelope.currency:
        delta("currency", envelope.currency, quote.currency, "fresh_approval")
    if quote.fulfillment_profile_id != envelope.fulfillment_profile_id:
        delta(
            "fulfillment_profile_id",
            envelope.fulfillment_profile_id,
            quote.fulfillment_profile_id,
            "fresh_approval",
        )
    if quote.delivery_eta > envelope.delivery_deadline:
        delta("delivery_deadline", envelope.delivery_deadline, quote.delivery_eta, "repair")
    if quote.cart.total_paise > envelope.max_total_paise:
        delta("max_total_paise", envelope.max_total_paise, quote.cart.total_paise, "repair")

    authoritative = catalog.by_sku()
    line_tags: dict[int, set[str]] = {}
    for index, line in enumerate(quote.cart.lines):
        product = authoritative.get(line.sku)
        if not product:
            delta(f"cart.lines[{index}].sku", "known catalog SKU", line.sku, "stop")
            continue
        expected_facts = (product["name"], product["category"], product["price_paise"])
        actual_facts = (line.name, line.category, line.unit_price_paise)
        if expected_facts != actual_facts:
            delta(
                f"cart.lines[{index}].catalog_facts",
                expected_facts,
                actual_facts,
                "repair",
            )
        if line.category in envelope.blocked_categories:
            delta(f"cart.lines[{index}].category", "not blocked", line.category, "stop")
        line_tags[index] = set(product.get("tags", []))

    unused = set(range(len(quote.cart.lines)))
    for slot in sorted(envelope.slots, key=lambda item: -len(item.required_tags)):
        match = next(
            (
                index
                for index in sorted(unused)
                if set(slot.required_tags).issubset(line_tags.get(index, set()))
                and quote.cart.lines[index].qty == slot.quantity
            ),
            None,
        )
        if match is None:
            delta(f"slots.{slot.id}", slot.required_tags, "not satisfied", "repair")
        else:
            unused.remove(match)
    for index in sorted(unused):
        delta(
            f"cart.lines[{index}]",
            "item satisfying one required slot",
            quote.cart.lines[index].sku,
            "repair",
        )

    allowed = not deltas
    code = "ALLOW_ENVELOPE" if allowed else "BLOCK_ENVELOPE_MISMATCH"
    return EnvelopeDecision(
        allowed=allowed,
        code=code,
        envelope_id=envelope.id,
        envelope_version=envelope.version,
        quote_total_paise=quote.cart.total_paise,
        deltas=deltas,
        human_message=(
            "The final quote is inside every approved envelope field."
            if allowed
            else "The final quote exceeded or changed approved authority; no payment action was sent."
        ),
    )
