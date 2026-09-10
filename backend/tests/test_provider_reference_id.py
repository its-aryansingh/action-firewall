"""A caller-supplied attempt id must never be able to break the provider call.

THE BUG THIS PINS
-----------------
Purchase attempt ids are chosen by the caller. The baseline UI sent
`attempt_` + a hyphenated UUID — 44 characters — straight into a Payment Link's
`reference_id`, which Razorpay caps at 40. Every checkout from that page failed
with a 409 quoting a Pydantic rule about string length: an error that named our
schema instead of the user's order, at the one boundary where a clear failure
matters most.

Widening the schema would have been the wrong fix. 40 is the provider's limit,
not ours, and a field that lies about what the provider accepts moves the
failure from our process to theirs. So the id is MAPPED instead, and these tests
fix the three properties that mapping has to have.
"""
from __future__ import annotations

import uuid

import pytest

from app.actions import (
    PROVIDER_REFERENCE_MAX_LEN,
    CreatePaymentLinkArgs,
    canonicalize_action,
    provider_reference_id,
)


def _args(reference_id: str) -> dict:
    return {
        "amount": 41_700,
        "currency": "INR",
        "description": "test",
        "accept_partial": False,
        "reference_id": reference_id,
        "notes": {"purchase_attempt_id": reference_id},
    }


# ---------------------------------------------------------------------------
# The three properties the mapping must have
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "attempt_id",
    [
        "att_" + uuid.uuid4().hex,                 # 36 — what the UI sends now
        "attempt_" + str(uuid.uuid4()),            # 44 — what it used to send
        "a",                                       # minimum
        "x" * PROVIDER_REFERENCE_MAX_LEN,          # exactly at the limit
        "x" * (PROVIDER_REFERENCE_MAX_LEN + 1),    # one over
        "purchase_attempt_" + "9" * 200,           # absurd, but a caller may send it
    ],
)
def test_the_result_always_fits_the_provider_field(attempt_id):
    """Whatever the caller sends, the action must validate."""
    reference = provider_reference_id(attempt_id)
    assert 1 <= len(reference) <= PROVIDER_REFERENCE_MAX_LEN
    # The real assertion: the registry accepts it.
    canonicalize_action("create_payment_link", _args(reference))


def test_the_mapping_is_deterministic():
    """A retry of the same attempt must reach the same reference.

    The UI promises 'the same purchase-attempt ID is retained for a safe retry'.
    If this mapping were random, a retry would look like a new payment link to
    the provider, and the idempotency that promise depends on would be gone.
    """
    long_id = "attempt_" + str(uuid.uuid4())
    assert provider_reference_id(long_id) == provider_reference_id(long_id)


def test_distinct_attempts_do_not_collide():
    ids = ["attempt_" + str(uuid.uuid4()) for _ in range(500)]
    references = {provider_reference_id(i) for i in ids}
    assert len(references) == len(ids)


def test_an_id_that_already_fits_is_passed_through_untouched():
    """Shortening something that was already fine would break existing links."""
    fits = "att_" + uuid.uuid4().hex
    assert len(fits) <= PROVIDER_REFERENCE_MAX_LEN
    assert provider_reference_id(fits) == fits


# ---------------------------------------------------------------------------
# The constraint itself
# ---------------------------------------------------------------------------

def test_the_schema_still_refuses_an_over_long_reference():
    """The limit stays enforced. The fix is the mapping, not a wider field."""
    from app.actions import InvalidActionArguments

    with pytest.raises(InvalidActionArguments):
        canonicalize_action(
            "create_payment_link",
            _args("x" * (PROVIDER_REFERENCE_MAX_LEN + 1)),
        )


def test_the_full_attempt_id_survives_in_notes():
    """Nothing is lost by shortening: reconciliation still has the real id."""
    long_id = "attempt_" + str(uuid.uuid4())
    args = _args(long_id)
    args["reference_id"] = provider_reference_id(long_id)
    canonical = canonicalize_action("create_payment_link", args)
    assert canonical.args["notes"]["purchase_attempt_id"] == long_id
    assert canonical.args["reference_id"] != long_id


def test_the_ui_generated_shape_validates():
    """Guards the frontend's generator: 'att_' + 32 hex characters."""
    generated = "att_" + uuid.uuid4().hex
    assert len(generated) == 36
    canonicalize_action("create_payment_link", _args(generated))
