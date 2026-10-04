"""Event catalogue and the observer interface.

The Agent calls `observer.emit(event, **fields)` at each step. The default
observer does nothing, so observability can never change an answer (D4-08).

| event               | emitted when                                  | main fields                                    |
|---------------------|-----------------------------------------------|------------------------------------------------|
| request_received    | a message arrives                             | language, message_length, message_hash          |
| intent_identified   | the intent is classified                      | intent, source                                  |
| tool_called         | the Validation Tool is queried                | period, filters                                 |
| engine_result       | the Tool answered                             | found, results, fail_count, run_id              |
| tool_error          | the Tool refused (no run / integrity)         | error_type                                      |
| rag_retrieved       | retrieval finished or was blocked             | evidence_status, chunks, top_score              |
| llm_called          | an LLM call finished                          | task, duration_ms, ok (+ error_type, redacted   |
|                     |                                               | error on failure, F1)                           |
| llm_fallback        | an LLM task failed and a deterministic        | task                                            |
|                     | fallback replaced it (F2)                     |                                                 |
| auditor_result      | the Auditor reviewed an answer                | attempt, verdict, failed_checks                 |
| route_decided       | the final route is known                      | route, intent, route_source                     |
| response_completed  | the answer is ready                           | route, answer_mode, evidence_status, verdict,   |
|                     |                                               | revised, latency_ms                             |
| error               | an unexpected exception was contained         | component, error_type                           |
| api_request         | an HTTP request finished                      | method, path, status_code, duration_ms          |
| ingest_completed    | the knowledge index was rebuilt               | provider, chunks, index_status                  |
"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

EVENTS = (
    "request_received", "intent_identified", "tool_called", "engine_result", "tool_error",
    "rag_retrieved", "llm_called", "llm_fallback", "auditor_result", "route_decided", "response_completed",
    "error", "api_request", "ingest_completed",
)


class AgentObserver(Protocol):
    def emit(self, event: str, **fields: Any) -> None: ...


class NullObserver:
    """Default observer: does nothing."""

    def emit(self, event: str, **fields: Any) -> None:
        return None


class RecordingObserver:
    """Keeps events in memory (tests and diagnostics)."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event: str, **fields: Any) -> None:
        from app.observability.context import current_trace_id

        self.events.append({"event": event, "trace_id": current_trace_id(), **fields})

    def names(self, trace_id: str | None = None) -> list[str]:
        return [e["event"] for e in self.events if trace_id is None or e["trace_id"] == trace_id]


class FanOutObserver:
    """Sends every event to several observers."""

    def __init__(self, *observers: AgentObserver):
        self.observers = observers

    def emit(self, event: str, **fields: Any) -> None:
        for observer in self.observers:
            observer.emit(event, **fields)


def message_fingerprint(message: str) -> str:
    """Truncated SHA-256 of the message: correlates repeats without storing content (D4-09)."""
    return hashlib.sha256(message.encode("utf-8")).hexdigest()[:12]
