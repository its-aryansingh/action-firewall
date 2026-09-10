"""Concurrency benchmark: does the budget hold when orders arrive at once?

WHY THIS EXISTS SEPARATELY
--------------------------
`benchmark_agent_authorization.py` measures whether the layer authorises the
right carts. It runs one order at a time, so it cannot see the failure that
actually loses a merchant money: two agent orders arriving in the same instant,
both reading the same remaining budget, both deciding they fit.

That failure is invisible to a policy benchmark and invisible to a demo. It only
appears under contention, and it is the difference between a spend cap that is a
rule and a spend cap that is a suggestion.

WHAT IT COMPARES
----------------
Two implementations of the same rule -- "never exceed the cap" -- on the same
cap, same order size, same thread count, same barrier:

  read-compare-write   Read spent-so-far, compare against the cap, then write.
                       This is the ordinary implementation, and it is what a
                       budget check looks like when nobody has thought about
                       contention. No lock, no reservation, no transaction
                       spanning the read and the write.

  authorize-and-reserve  The re-check and the write inside one BEGIN IMMEDIATE
                       transaction, so the row that decides is the row that is
                       written.

Both are run through a `threading.Barrier`, so the threads genuinely collide
rather than politely queueing.

WHAT IT REPORTS
---------------
Overspend, in rupees, as a fraction of the cap. Not "a race condition exists" --
how much money leaves the building.

HONESTY
-------
This is a local SQLite process, not a distributed system, and it measures a
specific race (check-then-act on a shared budget). It does not measure network
partitions, provider-side duplicates, or clock skew. The read-compare-write arm
is a faithful reproduction of the common pattern, written here rather than
lifted from a real codebase, so it can be read alongside the arm it loses to.

Usage:  python scripts/benchmark_concurrency.py [--threads 16] [--trials 20] [--json]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import threading
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))

CAP_RUPEES = 1_000
CAP_PAISE = CAP_RUPEES * 100
ORDER_PAISE = 20_000          # Rs 200 -- exactly 5 orders fit inside the cap
SEATS = CAP_PAISE // ORDER_PAISE


def _collide(fn, n: int) -> list:
    """Fire n threads through one barrier so they arrive together."""
    barrier = threading.Barrier(n)
    results: list = [None] * n

    def wrapped(i: int) -> None:
        barrier.wait()
        try:
            results[i] = fn(i)
        except Exception as exc:  # noqa: BLE001
            results[i] = exc

    threads = [threading.Thread(target=wrapped, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def _fresh_mandate(tmpdir: Path, trial: int):
    """One trial, one database, and the caller's DB_PATH restored afterwards.

    `_conn()` reads `get_settings().db_path` on every call, so pointing DB_PATH at
    a new file and clearing the settings cache is enough — no module reload. That
    matters: reloading `app.store` swaps the module object out from under anything
    that already imported it, which breaks every other test in the same process.
    """
    import os
    from contextlib import contextmanager

    from app.config import get_settings
    from app import store as _store
    from app.models import MandateCreate

    @contextmanager
    def _scoped_db():
        previous = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = str(tmpdir / f"conc_{trial}.db")
        get_settings.cache_clear()
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = previous
            get_settings.cache_clear()

    return _scoped_db, _store, MandateCreate


def trial_read_compare_write(tmpdir: Path, trial: int, threads: int) -> dict:
    scoped_db, store, MandateCreate = _fresh_mandate(tmpdir, trial)
    with scoped_db():
        return _read_compare_write(store, MandateCreate, threads)


def _read_compare_write(store, MandateCreate, threads: int) -> dict:
    store.init_db()
    mandate = store.create_mandate(MandateCreate(cap_rupees=CAP_RUPEES))

    def naive(_i: int) -> bool:
        spent = store.spent_in_window(mandate.id, mandate.window)
        if spent + ORDER_PAISE <= CAP_PAISE:   # the check
            store.record_spend(mandate.id, ORDER_PAISE)   # ... and the act
            return True
        return False

    results = _collide(naive, threads)
    committed = store.spent_in_window(mandate.id, mandate.window)
    return {
        "granted": sum(1 for r in results if r is True),
        "committed_paise": committed,
        "overspend_paise": max(0, committed - CAP_PAISE),
        "errors": sum(1 for r in results if isinstance(r, Exception)),
    }


def trial_authorize_and_reserve(tmpdir: Path, trial: int, threads: int) -> dict:
    scoped_db, store, MandateCreate = _fresh_mandate(tmpdir, trial + 10_000)
    with scoped_db():
        return _authorize_and_reserve(store, MandateCreate, threads, trial)


def _authorize_and_reserve(store, MandateCreate, threads: int, trial: int) -> dict:
    store.init_db()
    mandate = store.create_mandate(MandateCreate(cap_rupees=CAP_RUPEES))

    def reserve(i: int):
        return store.reserve_headroom(mandate.id, ORDER_PAISE, f"key-{trial}-{i}")

    results = _collide(reserve, threads)
    committed = store.spent_in_window(mandate.id, mandate.window)
    return {
        "granted": sum(1 for r in results if getattr(r, "granted", False)),
        "committed_paise": committed,
        "overspend_paise": max(0, committed - CAP_PAISE),
        "errors": sum(1 for r in results if isinstance(r, Exception)),
    }


def summarise(name: str, trials: list[dict], threads: int, n_trials: int) -> dict:
    over = [t["overspend_paise"] for t in trials]
    breached = sum(1 for o in over if o > 0)
    return {
        "implementation": name,
        "trials": n_trials,
        "threads_per_trial": threads,
        "cap_paise": CAP_PAISE,
        "seats_inside_cap": SEATS,
        "trials_that_breached_the_cap": breached,
        "breach_rate": round(breached / n_trials, 4),
        "mean_overspend_paise": round(statistics.mean(over), 1),
        "max_overspend_paise": max(over),
        "total_overspend_paise": sum(over),
        "mean_granted": round(statistics.mean(t["granted"] for t in trials), 2),
        "errors": sum(t["errors"] for t in trials),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threads", type=int, default=16,
                    help="concurrent orders per trial (default 16, cap fits 5)")
    ap.add_argument("--trials", type=int, default=20, help="independent trials (default 20)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        naive = [trial_read_compare_write(tmpdir, i, args.threads) for i in range(args.trials)]
        safe = [trial_authorize_and_reserve(tmpdir, i, args.threads) for i in range(args.trials)]

    a = summarise("read-compare-write", naive, args.threads, args.trials)
    b = summarise("authorize-and-reserve", safe, args.threads, args.trials)

    report = {
        "schema_version": "concurrency-benchmark@1",
        "scope": (
            "Local SQLite, one process, threads through a barrier. Measures one "
            "specific race: check-then-act on a shared budget. Does not measure "
            "network partitions, provider duplicates, or clock skew. The "
            "read-compare-write arm is a faithful reproduction of the common "
            "pattern, reproduced here so it can be read alongside the arm it loses to."
        ),
        "setup": {
            "cap_rupees": CAP_RUPEES,
            "order_rupees": ORDER_PAISE // 100,
            "orders_that_fit": SEATS,
            "concurrent_orders": args.threads,
            "trials": args.trials,
        },
        "read_compare_write": a,
        "authorize_and_reserve": b,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Concurrency benchmark — does the cap hold when orders collide?")
        print(f"  cap Rs {CAP_RUPEES:,}  ·  order Rs {ORDER_PAISE // 100}  ·  "
              f"{SEATS} fit inside  ·  {args.threads} arrive at once  ·  "
              f"{args.trials} trials\n")
        for r in (a, b):
            print(f"  {r['implementation']}")
            print(f"    trials that breached the cap   {r['trials_that_breached_the_cap']}"
                  f"/{r['trials']}  ({r['breach_rate']:.0%})")
            print(f"    mean orders authorised          {r['mean_granted']}  "
                  f"(only {SEATS} fit)")
            print(f"    mean overspend                  Rs {r['mean_overspend_paise']/100:,.2f}")
            print(f"    worst overspend                 Rs {r['max_overspend_paise']/100:,.2f}")
            print(f"    total overspend across trials   Rs {r['total_overspend_paise']/100:,.2f}\n")
        print(f"  {report['scope']}")

    # The reservation arm must never breach. The naive arm is expected to.
    sys.exit(1 if b["trials_that_breached_the_cap"] > 0 else 0)


if __name__ == "__main__":
    main()
