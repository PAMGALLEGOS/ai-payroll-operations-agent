"""Agent contracts: request, response, intent and route vocabularies.

Canonical values (routes, intents, reason codes, validation types, identifiers)
are always English, whatever the language of the conversation (C3-12).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

Route = Literal["RAG", "TOOL", "TOOL_RAG", "CLARIFY", "OUT_OF_SCOPE"]
ROUTES: tuple[Route, ...] = ("RAG", "TOOL", "TOOL_RAG", "CLARIFY", "OUT_OF_SCOPE")

Intent = Literal[
    "policy_question",
    "validation_lookup",
    "validation_explanation",
    "aggregate_lookup",
    "readiness_question",
    "out_of_scope",
    "unclear",
]

ClarifyReason = Literal["missing_employee", "missing_period", "multiple_employees",
                        "unclear_intent", "empty_message"]
OutOfScopeReason = Literal["prohibited_action", "off_topic", "legal_advice"]
EvidenceStatus = Literal["sufficient", "insufficient", "not_used", "blocked_stale_index", "unavailable"]
AnswerMode = Literal["template", "template+llm", "llm", "safe_fallback"]


class IntentOutput(BaseModel):
    """Schema the LLM must return when classifying a message."""

    intent: Intent
    retrieval_query: str = Field(
        default="",
        max_length=300,
        description="The question rewritten in English for searching an English knowledge base. "
                    "Same meaning, no new facts. Empty if no documentation search is needed.",
    )
    confidence: Literal["high", "medium", "low"] = "medium"


@dataclass(frozen=True)
class AgentRequest:
    session_id: str
    message: str


@dataclass
class AgentResponse:
    trace_id: str
    session_id: str
    language: str
    route: Route
    route_source: str                 # "rule" | "llm_intent" | "fallback" | "pending_clarification"
    intent: str | None
    entities: dict[str, Any]
    entities_source: dict[str, str]
    answer: str
    answer_mode: AnswerMode
    validation: dict[str, Any] | None = None
    evidence_status: EvidenceStatus = "not_used"
    evidence: list[dict[str, Any]] = field(default_factory=list)
    clarification: dict[str, Any] | None = None
    out_of_scope: dict[str, Any] | None = None
    audit: dict[str, Any] = field(default_factory=dict)
    human_in_the_loop: str | None = None
    versions: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
