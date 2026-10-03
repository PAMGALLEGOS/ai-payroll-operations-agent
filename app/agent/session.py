"""In-memory session context with TTL (decision D17; spec §11: no long-term memory).

Only structured state is kept — never full answers — and only this structured
summary is shown to the LLM. Less text means less drift and fewer tokens.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

MAX_TURNS = 10


@dataclass
class PendingQuestion:
    """A question waiting for a missing piece of information after CLARIFY."""

    intent: str
    missing: str                     # "employee_id" | "period"
    original_message: str
    validation_type: str | None = None
    period: str | None = None
    employee_id: str | None = None


@dataclass
class SessionState:
    session_id: str
    language: str = "en"
    employee_id: str | None = None
    period: str | None = None
    validation_focus: list[str] = field(default_factory=list)   # failed types of the last result
    last_intent: str | None = None
    last_route: str | None = None
    pending: PendingQuestion | None = None
    turns: list[dict[str, Any]] = field(default_factory=list)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def summary_for_llm(self) -> dict[str, Any]:
        return {
            "employee_in_context": self.employee_id,
            "period_in_context": self.period,
            "last_intent": self.last_intent,
            "last_route": self.last_route,
        }

    def record_turn(self, message: str, route: str, intent: str | None, entities: dict[str, Any]) -> None:
        self.turns.append({"message": message[:200], "route": route, "intent": intent, "entities": entities})
        del self.turns[:-MAX_TURNS]


class SessionStore:
    def __init__(self, ttl_minutes: int = 30, clock: Callable[[], datetime] | None = None):
        self.ttl = timedelta(minutes=ttl_minutes)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._sessions: dict[str, SessionState] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def lock(self, session_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(session_id, threading.Lock())

    def get(self, session_id: str) -> SessionState:
        """Return the live session, or a fresh one if it never existed or expired."""
        now = self.clock()
        with self._guard:
            self._expire(now)
            state = self._sessions.get(session_id)
            if state is None:
                state = SessionState(session_id=session_id, updated_at=now)
                self._sessions[session_id] = state
            return state

    def touch(self, state: SessionState) -> None:
        state.updated_at = self.clock()

    def _expire(self, now: datetime) -> None:
        for sid in [s for s, st in self._sessions.items() if now - st.updated_at > self.ttl]:
            del self._sessions[sid]
            self._locks.pop(sid, None)

    def __len__(self) -> int:
        return len(self._sessions)
