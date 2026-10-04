"""LLM client wrapper that reports every call to the observer.

It forwards calls unchanged to the wrapped client and emits `llm_called` with
the task, duration and success. On failure it also records the redacted reason
(F1), so a failing provider is diagnosable from the log. Prompts and outputs
are never recorded (D4-09).
Any other attribute (for example the fake client's `script` / `calls_for`
helpers used by tests) is forwarded to the wrapped client.
"""

from __future__ import annotations

import time
from typing import Any

from app.llm.client import LLMClient, LLMError, SchemaT
from app.observability.events import AgentObserver
from app.observability.redact import redact


class ObservedLLMClient(LLMClient):
    def __init__(self, inner: LLMClient, observer: AgentObserver):
        self._inner = inner
        self._observer = observer
        self.name = inner.name
        self.model = inner.model

    def __getattr__(self, attribute: str) -> Any:
        return getattr(self._inner, attribute)

    def _timed(self, task: str, call):
        started = time.perf_counter()
        try:
            result = call()
        except LLMError as error:
            self._observer.emit("llm_called", task=task, duration_ms=int((time.perf_counter() - started) * 1000),
                                ok=False, error_type=type(error).__name__, error=redact(str(error)))
            raise
        self._observer.emit("llm_called", task=task, duration_ms=int((time.perf_counter() - started) * 1000), ok=True)
        return result

    def generate_json(self, *, task: str, system: str, user: str, schema: type[SchemaT]) -> SchemaT:
        return self._timed(task, lambda: self._inner.generate_json(task=task, system=system, user=user, schema=schema))

    def generate_text(self, *, task: str, system: str, user: str) -> str:
        return self._timed(task, lambda: self._inner.generate_text(task=task, system=system, user=user))
