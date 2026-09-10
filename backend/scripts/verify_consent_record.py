#!/usr/bin/env python3
"""Re-derive every claim in a consent record. No database, no key, no network.

    python scripts/verify_consent_record.py consent.json

This is the whole argument for the artifact. A merchant answering a dispute can
hand over the record; the acquirer, the customer, or anyone else runs this
against the published source and checks it themselves. Evidence a third party
can verify is evidence. Evidence only the record-keeper can verify is an
assertion wearing the costume of one.

Exit codes: 0 valid, 1 a binding failed, 2 the file could not be read.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.consent import verify_consent_record  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    try:
        record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"could not read {sys.argv[1]}: {exc}")
        return 2

    result = verify_consent_record(record)
    if result["valid"]:
        print("VALID — every binding in this consent record re-derives.\n")
        print(f"  envelope        {result['envelope_id']}")
        print(f"  envelope hash   {result['envelope_hash']}")
        print(f"  sentence hash   {result['displayed_text_hash']}\n")
        print("  checked:")
        for line in result["checked"]:
            print(f"    - {line}")
        print("\n  NOT checked — say so when you rely on this:")
        for line in result["not_checked"]:
            print(f"    - {line}")
        print("\n  The sentence the customer was shown:\n")
        print(f"    {record['displayed_text']}")
        return 0

    print("FAILED — this consent record does not hold up.\n")
    print(f"  field     {result['failed_field']}")
    print(f"  reason    {result['reason']}")
    print(f"  expected  {result['expected'][:120]}")
    print(f"  found     {result['actual'][:120]}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
