"""The publication-value number must stay honest as the corpus grows.

`scripts/publication_value.py` produces the one figure the acceptance-policy
endpoint is sold on: how many refusals an agent would have avoided by reading the
merchant's published rules first. Two ways that number can quietly become a lie:

  1. A violating family is added to the benchmark and never labelled, so it drops
     out of the denominator and the percentage rises for free.
  2. A family is labelled `acceptance_policy` when the rule it violates is
     actually on the customer's envelope — which the merchant does not publish
     and could not. That is how an earlier draft reached 88% instead of 50%.

The first is mechanical and the script already exits non-zero on it. The second
is a judgement call, so it is pinned here: every family credited to the published
document must correspond to a clause that document actually contains.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))

from publication_value import (  # noqa: E402
    DOCUMENT,
    ENVELOPE,
    NEITHER,
    DISCLOSURE,
    VIOLATING_FAMILIES,
    _check_coverage,
)

from app.acceptance_policy import build_acceptance_policy  # noqa: E402


def test_every_violating_family_is_labelled():
    """The denominator must cover the whole corpus, not the convenient part."""
    assert _check_coverage() == [], (
        "these violating families have no disclosure label, so publication_value.py "
        "would silently exclude them from its denominator"
    )


def test_no_family_is_labelled_beyond_the_corpus():
    """A stale label is a rule that no longer exists being counted as prevented."""
    extra = sorted(set(DISCLOSURE) - set(VIOLATING_FAMILIES))
    assert extra == [], f"labels for families the benchmark no longer builds: {extra}"


def test_only_the_three_channels_are_used():
    channels = {channel for channel, _clause in DISCLOSURE.values()}
    assert channels <= {DOCUMENT, ENVELOPE, NEITHER}


@pytest.mark.parametrize(
    "family",
    sorted(f for f, (c, _) in DISCLOSURE.items() if c == DOCUMENT),
)
def test_document_credit_is_backed_by_a_real_clause(family):
    """Credit claimed for the endpoint must be findable in what it serves.

    This is the assertion that would have caught the 88% overclaim: it fails the
    moment a family is credited to the published document while the rule it
    breaks lives somewhere the merchant does not publish.
    """
    document = build_acceptance_policy()
    # The clause names a path into the document (`will_refuse.categories`) or a
    # top-level key (`merchant_id`). Either way its first segment must exist.
    _channel, clause = DISCLOSURE[family]
    head = clause.split(" ")[0].split(".")[0].split("_—")[0].strip()
    assert head in document, (
        f"'{family}' is credited to the acceptance policy via '{clause}', but the "
        f"document has no '{head}' — the credit is not backed by anything published"
    )


def test_tampering_is_never_credited_to_publication():
    """Publication prevents mistakes, not attacks. This is the line that must hold."""
    for family in ("catalog_fact_tamper", "quote_hash_tamper"):
        channel, _clause = DISCLOSURE[family]
        assert channel == NEITHER, (
            f"'{family}' forges input. Crediting it to a published document would "
            f"claim publication stops attackers, which it does not."
        )
