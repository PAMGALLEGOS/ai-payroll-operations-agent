"""Routing matrix (every cell) and session store."""

from datetime import datetime, timedelta, timezone

import pytest

from app.agent.router import decide_route
from app.agent.session import MAX_TURNS, SessionStore

E, P = "EMP024", "2026-09"


@pytest.mark.parametrize(
    "intent,employee,period,legal,route,reason",
    [
        ("policy_question", None, None, False, "RAG", None),
        ("policy_question", E, P, False, "RAG", None),
        ("validation_lookup", E, P, False, "TOOL", None),
        ("validation_lookup", None, P, False, "CLARIFY", "missing_employee"),
        ("validation_lookup", E, None, False, "CLARIFY", "missing_period"),
        ("validation_explanation", E, P, False, "TOOL_RAG", None),
        ("validation_explanation", None, P, False, "CLARIFY", "missing_employee"),
        ("validation_explanation", E, None, False, "CLARIFY", "missing_period"),
        ("aggregate_lookup", None, P, False, "TOOL", None),
        ("aggregate_lookup", None, None, False, "CLARIFY", "missing_period"),
        ("readiness_question", None, P, False, "TOOL_RAG", None),
        ("readiness_question", None, None, False, "CLARIFY", "missing_period"),
        ("out_of_scope", None, None, False, "OUT_OF_SCOPE", "off_topic"),
        ("out_of_scope", None, None, True, "OUT_OF_SCOPE", "legal_advice"),
        ("unclear", E, P, False, "CLARIFY", "unclear_intent"),
        ("something_unexpected", E, P, False, "CLARIFY", "unclear_intent"),
    ],
)
def test_routing_matrix(intent, employee, period, legal, route, reason):
    decision = decide_route(intent, employee_id=employee, period=period, legal_reference=legal)
    assert (decision.route, decision.reason) == (route, reason)


def test_missing_employee_reports_what_is_missing():
    assert decide_route("validation_explanation", employee_id=None, period=P).missing == "employee_id"


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def test_session_is_created_and_reused():
    store = SessionStore()
    first = store.get("a")
    first.employee_id = "EMP024"
    assert store.get("a").employee_id == "EMP024"
    assert store.get("b").employee_id is None


def test_session_expires_after_ttl():
    clock = Clock()
    store = SessionStore(ttl_minutes=30, clock=clock)
    store.get("a").employee_id = "EMP024"
    clock.now += timedelta(minutes=31)
    assert store.get("a").employee_id is None


def test_touch_keeps_session_alive():
    clock = Clock()
    store = SessionStore(ttl_minutes=30, clock=clock)
    state = store.get("a")
    state.employee_id = "EMP024"
    clock.now += timedelta(minutes=20)
    store.touch(state)
    clock.now += timedelta(minutes=20)
    assert store.get("a").employee_id == "EMP024"


def test_turn_history_is_bounded():
    state = SessionStore().get("a")
    for i in range(MAX_TURNS + 5):
        state.record_turn(f"m{i}", "RAG", "policy_question", {})
    assert len(state.turns) == MAX_TURNS
    assert state.turns[-1]["message"] == f"m{MAX_TURNS + 4}"


def test_llm_sees_only_structured_session_summary():
    state = SessionStore().get("a")
    state.employee_id, state.last_intent = "EMP024", "validation_explanation"
    state.record_turn("a long message " * 50, "TOOL_RAG", "validation_explanation", {})
    summary = state.summary_for_llm()
    assert summary == {"employee_in_context": "EMP024", "period_in_context": None,
                       "last_intent": "validation_explanation", "last_route": None}
