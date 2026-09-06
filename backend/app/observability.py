"""Optional Langfuse tracing for proposals and explicit authorization.

Proposal traces contain retrieval, planning, and a non-authorizing policy
preview. Confirmation traces contain authorization and, only after an exact
grant is claimed, the registered Razorpay action. Local database state remains
authoritative if tracing is disabled or unavailable.
"""
from __future__ import annotations
import contextlib
from typing import Any

from .config import get_settings

_client = None


def get_langfuse():
    global _client
    if _client is not None:
        return _client
    s = get_settings()
    if not (s.langfuse_public_key and s.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse
        host = s.langfuse_base_url or s.langfuse_host or "https://cloud.langfuse.com"
        _client = Langfuse(public_key=s.langfuse_public_key,
                           secret_key=s.langfuse_secret_key, host=host)
        return _client
    except Exception as exc:  # pragma: no cover
        print(f"[langfuse] disabled: {exc}")
        return None


class Trace:
    """Thin wrapper so the agent code reads the same with or without Langfuse."""

    def __init__(self, name: str, session_id: str, user_id: str, input: Any = None):
        self._lf = get_langfuse()
        self._trace = None
        if self._lf:
            self._trace = self._lf.trace(name=name, session_id=session_id,
                                         user_id=user_id, input=input,
                                         tags=["action-firewall", "track01"])

    @contextlib.contextmanager
    def span(self, name: str, input: Any = None):
        span = self._trace.span(name=name, input=input) if self._trace else None
        holder: dict[str, Any] = {}
        try:
            yield holder
        finally:
            if span:
                span.end(output=holder.get("output"),
                         level=holder.get("level", "DEFAULT"),
                         status_message=holder.get("status_message"))

    def event(self, name: str, **kwargs) -> None:
        if self._trace:
            self._trace.event(name=name, **kwargs)

    def score(self, name: str, value: float, comment: str | None = None) -> None:
        if self._trace:
            self._trace.score(name=name, value=value, comment=comment)

    def end(self, output: Any = None) -> None:
        if self._trace:
            self._trace.update(output=output)
            lf = get_langfuse()
            if lf:
                lf.flush()

    @property
    def url(self) -> str | None:
        try:
            return self._trace.get_trace_url() if self._trace else None
        except Exception:
            return None
