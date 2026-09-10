#!/usr/bin/env python3
"""Re-execute an authorisation decision from its evidence pack.

    python scripts/verify_dispute_pack.py pack.json

No database. No signing key. No network. Everything this checks, it checks by
re-deriving it from the pack and the published source — including the decision
itself, which it re-runs on the recorded inputs and compares to the recorded
outcome.

That last check is the point. A merchant answering a chargeback can hand this
file to the acquirer, the customer, or anyone else, and they can confirm the
outcome without trusting the merchant, the model, or us. A design that consults a
language model at authorisation time cannot offer it: the samples that produced
the decision are gone.

Exit codes: 0 valid, 1 a check failed, 2 the file could not be read.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dispute import verify_dispute_pack  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    try:
        pack = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"could not read {sys.argv[1]}: {exc}")
        return 2

    result = verify_dispute_pack(pack)
    if not result["valid"]:
        print("FAILED — this evidence pack does not hold up.\n")
        print(f"  check     {result['failed_check']}")
        print(f"  reason    {result['reason']}")
        print(f"  expected  {result['expected'][:160]}")
        print(f"  found     {result['actual'][:160]}")
        return 1

    print("VALID — every claim in this pack re-derives.\n")
    print(f"  attempt   {result['purchase_attempt_id']}")
    print(f"  outcome   {result['outcome']}\n")
    print("  Independently re-derived — no trust in the merchant required:")
    for line in result["independently_rederived"]:
        print(f"    - {line}")
    print("\n  Attested by the merchant, NOT proven:")
    for line in result["attested_by_the_merchant_not_proven"]:
        print(f"    - {line}")
    print()
    consent = pack.get("consent") or {}
    if consent.get("displayed_text"):
        print("  The rule the customer approved, in the words they were shown:\n")
        print(f"    {consent['displayed_text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
