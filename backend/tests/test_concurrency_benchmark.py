"""The concurrency benchmark's two claims, guarded.

Claim 1: the ordinary read-compare-write budget check breaches its own cap.
Claim 2: authorize-and-reserve does not.

Claim 1 matters as much as claim 2. If the naive arm ever stops breaching, the
comparison has stopped measuring anything — the race got harder to hit on this
machine, not fixed — and the benchmark would be quietly flattering itself.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from benchmark_concurrency import (  # noqa: E402
    CAP_PAISE,
    SEATS,
    trial_authorize_and_reserve,
    trial_read_compare_write,
)

THREADS = 16


def test_read_compare_write_breaches_the_cap():
    with tempfile.TemporaryDirectory() as td:
        result = trial_read_compare_write(Path(td), 0, THREADS)
    assert result["overspend_paise"] > 0, (
        "the unguarded arm must breach; if it stops, the comparison is vacuous"
    )
    assert result["granted"] > SEATS


def test_authorize_and_reserve_never_breaches_the_cap():
    with tempfile.TemporaryDirectory() as td:
        result = trial_authorize_and_reserve(Path(td), 0, THREADS)
    assert result["overspend_paise"] == 0
    assert result["granted"] == SEATS, f"expected exactly {SEATS} winners"
    assert result["committed_paise"] <= CAP_PAISE
    assert result["errors"] == 0


def test_the_two_arms_enforce_the_same_rule():
    """Same cap, same order size, same thread count. Only the mechanism differs."""
    with tempfile.TemporaryDirectory() as td:
        naive = trial_read_compare_write(Path(td), 1, THREADS)
        safe = trial_authorize_and_reserve(Path(td), 1, THREADS)
    assert naive["granted"] > safe["granted"], (
        "the naive arm should authorise more orders than fit; that is the point"
    )
    assert safe["committed_paise"] <= CAP_PAISE < naive["committed_paise"]
