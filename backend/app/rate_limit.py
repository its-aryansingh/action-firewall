"""Local write rate limiter for external AI buyer endpoints.

Implements an in-memory sliding-window limiter per buyer key and per shopper session.
Thread-safe and deterministic.
"""
from __future__ import annotations

import collections
import threading
import time
from fastapi import HTTPException


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter tracking request timestamps per partition key."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._partitions: dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)

    def check_and_record(
        self, key: str, max_requests: int = 60, window_seconds: float = 60.0, now: float | None = None
    ) -> tuple[bool, float]:
        current_time = time.time() if now is None else now
        cutoff = current_time - window_seconds

        with self._lock:
            q = self._partitions[key]
            # Evict timestamps outside the sliding window
            while q and q[0] <= cutoff:
                q.popleft()

            if len(q) >= max_requests:
                earliest = q[0]
                retry_after = max(1.0, (earliest + window_seconds) - current_time)
                return False, retry_after

            q.append(current_time)
            return True, 0.0

    def reset(self) -> None:
        with self._lock:
            self._partitions.clear()


# Global limiter instance
_WRITE_LIMITER = SlidingWindowRateLimiter()


def get_limiter() -> SlidingWindowRateLimiter:
    return _WRITE_LIMITER


def enforce_rate_limit(
    buyer: str | Any,
    shopper_session_id: str,
    max_buyer_requests: int = 60,
    max_session_requests: int = 30,
    window_seconds: float = 60.0,
) -> None:
    """Enforce rate limits per buyer agent and per shopper session."""
    limiter = get_limiter()
    buyer_id = buyer.buyer_agent_id if hasattr(buyer, "buyer_agent_id") else str(buyer)

    # 1. Check buyer limit
    allowed, retry_after = limiter.check_and_record(
        f"buyer:{buyer_id}",
        max_requests=max_buyer_requests,
        window_seconds=window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Buyer rate limit exceeded for '{buyer_id}'. Retry in {int(retry_after)} seconds.",
            headers={"Retry-After": str(int(retry_after))},
        )

    # 2. Check shopper session limit
    allowed, retry_after = limiter.check_and_record(
        f"session:{shopper_session_id}",
        max_requests=max_session_requests,
        window_seconds=window_seconds,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Shopper session rate limit exceeded for '{shopper_session_id}'. Retry in {int(retry_after)} seconds.",
            headers={"Retry-After": str(int(retry_after))},
        )
