"""The judge rehearsal must be deterministic on a stock Windows terminal."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = BACKEND_ROOT / "mandates.db"


def _digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def test_demo_is_offline_disposable_and_cp1252_safe() -> None:
    before = _digest(DEFAULT_DB)
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    environment["NO_COLOR"] = "1"

    completed = subprocess.run(
        [sys.executable, "scripts/demo.py"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="cp1252",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "BLOCK_WINDOW_CAP_EXCEEDED" in completed.stdout
    assert "state=action_issued" in completed.stdout
    assert "BLOCK_MANDATE_REVOKED" in completed.stdout

    # Settlement is reachable now, so the rehearsal must show the loop closing
    # in the right order: reconciling an unpaid link changes nothing, and the
    # confirmed figure moves only after the provider reports the payment.
    assert "changed=False" in completed.stdout
    assert "action_issued -> settled" in completed.stdout
    assert '"confirmed_test_payment_value_paise": 48600' in completed.stdout
    assert "REHEARSAL PASSED" in completed.stdout
    assert _digest(DEFAULT_DB) == before
