"""The trace_id of the interaction being processed.

A context variable lets any component (the Agent, the LLM wrapper, the API)
attach the current trace_id to its events without passing it through every
function signature.
"""

from __future__ import annotations

import contextvars
import uuid

_TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    return f"TRACE-{uuid.uuid4().hex[:8]}"


def current_trace_id() -> str | None:
    return _TRACE_ID.get()


def set_trace_id(trace_id: str) -> contextvars.Token:
    return _TRACE_ID.set(trace_id)


def reset_trace_id(token: contextvars.Token) -> None:
    _TRACE_ID.reset(token)
