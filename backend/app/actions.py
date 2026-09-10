"""Closed action registry for the Razorpay actuator boundary."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, model_validator

from .authorization import action_args_hash, digest

#: Razorpay caps a Payment Link's `reference_id` at 40 characters. That is the
#: provider's constraint, not ours, so the schema below enforces it rather than
#: widening to whatever we happen to generate.
PROVIDER_REFERENCE_MAX_LEN = 40


def provider_reference_id(purchase_attempt_id: str) -> str:
    """A provider-safe `reference_id` for an attempt id of any length.

    Purchase attempt ids are chosen by the CALLER — a buyer agent may send any
    string it likes, and our own UI once sent `attempt_` + a UUID, which is 44
    characters. Passing that straight through meant the provider boundary
    rejected the action with a validation error that named a Pydantic rule, so
    an operator saw a 409 about string length instead of anything about their
    order.

    An over-long id is therefore mapped, not refused: the digest is
    DETERMINISTIC, so retrying the same attempt produces the same reference and
    the provider's own idempotency still holds. Nothing is lost either — every
    caller of this passes the full attempt id in `notes.purchase_attempt_id`,
    where the limit is 256 characters, so the untruncated value stays on the
    payment link for reconciliation.
    """
    if len(purchase_attempt_id) <= PROVIDER_REFERENCE_MAX_LEN:
        return purchase_attempt_id
    digest_hex = hashlib.sha256(purchase_attempt_id.encode("utf-8")).hexdigest()
    return f"att_{digest_hex[:32]}"  # 36 characters


class ActionNotRegistered(ValueError):
    pass


class InvalidActionArguments(ValueError):
    pass


class CreatePaymentLinkArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    amount: StrictInt = Field(..., ge=100, le=100_000_000)
    currency: Literal["INR"]
    description: str = Field(..., min_length=1, max_length=255)
    accept_partial: Literal[False]
    reference_id: str = Field(..., min_length=1, max_length=40)
    notes: dict[str, str] = Field(default_factory=dict, max_length=15)

    @model_validator(mode="after")
    def validate_note_values(self) -> "CreatePaymentLinkArgs":
        if any(len(value) > 256 for value in self.notes.values()):
            raise ValueError("Payment Link note values must be at most 256 characters")
        return self


class RefundArgs(BaseModel):
    """Razorpay Refunds API: POST /v1/payments/{payment_id}/refund.

    The second registered action, and the first that moves money OUT. It is here
    to prove the registry does what it was built for: the grant, the atomic
    reservation, the single compare-and-set dispatch owner and the UNKNOWN
    outcome are all action-agnostic, so a new action is a schema and a name, not
    a second engine.

    `speed` is pinned to "normal" deliberately. "optimum" costs the merchant more
    and is a business decision, not one an agent should make unattended.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    payment_id: str = Field(..., min_length=4, max_length=64)
    amount: StrictInt = Field(..., ge=100, le=100_000_000)
    currency: Literal["INR"]
    speed: Literal["normal"] = "normal"
    receipt: str = Field(..., min_length=1, max_length=40)
    notes: dict[str, str] = Field(default_factory=dict, max_length=15)

    @model_validator(mode="after")
    def validate_note_values(self) -> "RefundArgs":
        if any(len(value) > 256 for value in self.notes.values()):
            raise ValueError("Refund note values must be at most 256 characters")
        return self


@dataclass(frozen=True)
class ActionSpec:
    name: str
    version: str
    arguments_model: type[BaseModel]

    @property
    def schema_hash(self) -> str:
        return digest({
            "name": self.name,
            "version": self.version,
            "schema": self.arguments_model.model_json_schema(),
        })


@dataclass(frozen=True)
class CanonicalAction:
    name: str
    args: dict[str, Any]
    args_hash: str
    schema_hash: str
    amount_paise: int
    currency: str


ACTION_REGISTRY: dict[str, ActionSpec] = {
    "create_payment_link": ActionSpec(
        name="create_payment_link",
        version="create_payment_link@2",
        arguments_model=CreatePaymentLinkArgs,
    ),
    "refund": ActionSpec(
        name="refund",
        version="refund@1",
        arguments_model=RefundArgs,
    ),
}


def canonicalize_action(name: str, args: dict[str, Any]) -> CanonicalAction:
    spec = ACTION_REGISTRY.get(name)
    if spec is None:
        raise ActionNotRegistered(f"Action '{name}' is not registered")
    try:
        parsed = spec.arguments_model.model_validate(args)
    except ValidationError as exc:
        raise InvalidActionArguments(str(exc)) from exc
    canonical_args = parsed.model_dump(mode="json")
    return CanonicalAction(
        name=name,
        args=canonical_args,
        args_hash=action_args_hash(name, canonical_args),
        schema_hash=spec.schema_hash,
        amount_paise=int(canonical_args["amount"]),
        currency=str(canonical_args["currency"]),
    )
