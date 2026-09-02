"""Closed action registry for the Razorpay actuator boundary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from .authorization import action_args_hash, digest


class ActionNotRegistered(ValueError):
    pass


class InvalidActionArguments(ValueError):
    pass


class CreatePaymentLinkArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    amount: StrictInt = Field(..., gt=0)
    currency: Literal["INR"]
    description: str = Field(..., min_length=1, max_length=255)
    accept_partial: Literal[False]
    reference_id: str = Field(..., min_length=1, max_length=64)
    notes: dict[str, str] = Field(default_factory=dict)


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
        version="create_payment_link@1",
        arguments_model=CreatePaymentLinkArgs,
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
