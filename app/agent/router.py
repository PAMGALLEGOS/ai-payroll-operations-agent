"""Deterministic routing matrix (decision C3-02).

The LLM's intent label is an INPUT here; the route is decided by this table,
together with what deterministic code knows about the entities. A missing
employee therefore always produces CLARIFY, whatever the LLM believed.

| intent                 | needs employee | needs period | route        |
|------------------------|----------------|--------------|--------------|
| policy_question        | no             | no           | RAG          |
| validation_lookup      | yes            | yes          | TOOL         |
| validation_explanation | yes            | yes          | TOOL_RAG     |
| aggregate_lookup       | no             | yes          | TOOL         |
| readiness_question     | no             | yes          | TOOL_RAG     |
| out_of_scope           | -              | -            | OUT_OF_SCOPE |
| unclear                | -              | -            | CLARIFY      |
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.contracts import Route

_MATRIX: dict[str, tuple[Route, bool, bool]] = {
    # intent: (route, needs_employee, needs_period)
    "policy_question": ("RAG", False, False),
    "validation_lookup": ("TOOL", True, True),
    "validation_explanation": ("TOOL_RAG", True, True),
    "aggregate_lookup": ("TOOL", False, True),
    "readiness_question": ("TOOL_RAG", False, True),
}


@dataclass(frozen=True)
class RouteDecision:
    route: Route
    reason: str | None = None        # CLARIFY / OUT_OF_SCOPE reason
    missing: str | None = None       # "employee_id" | "period" when CLARIFY needs data


def needs_employee(intent: str) -> bool:
    return _MATRIX.get(intent, ("", False, False))[1]


def needs_period(intent: str) -> bool:
    return _MATRIX.get(intent, ("", False, False))[2]


def decide_route(intent: str, *, employee_id: str | None, period: str | None,
                 legal_reference: bool = False) -> RouteDecision:
    if intent == "out_of_scope":
        return RouteDecision("OUT_OF_SCOPE", "legal_advice" if legal_reference else "off_topic")
    if intent not in _MATRIX:  # "unclear" or anything unexpected
        return RouteDecision("CLARIFY", "unclear_intent")

    route, wants_employee, wants_period = _MATRIX[intent]
    if wants_employee and employee_id is None:
        return RouteDecision("CLARIFY", "missing_employee", "employee_id")
    if wants_period and period is None:
        return RouteDecision("CLARIFY", "missing_period", "period")
    return RouteDecision(route)
