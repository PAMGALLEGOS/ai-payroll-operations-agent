"""JSON contracts of the API (spec §14). They mirror the CP1–CP3 contracts.

Monetary values stay strings ("350.00"), exactly as the Engine persisted them,
so nothing is ever converted to a float on the way to the user.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SESSION_ID_PATTERN = r"^[A-Za-z0-9_\-]{1,64}$"


# --------------------------------------------------------------------- chat
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000, description="The user's question, in English or Spanish")
    session_id: str | None = Field(
        default=None, pattern=SESSION_ID_PATTERN,
        description="Conversation id. Omit it to start a new conversation; the server returns one (D4-04).",
    )


class ChatResponse(BaseModel):
    """The Agent's full structured response (D4-05)."""

    trace_id: str
    session_id: str
    language: str
    route: Literal["RAG", "TOOL", "TOOL_RAG", "CLARIFY", "OUT_OF_SCOPE"]
    route_source: str
    intent: str | None
    entities: dict[str, Any]
    entities_source: dict[str, str]
    answer: str
    answer_mode: str
    validation: dict[str, Any] | None = None
    evidence_status: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    clarification: dict[str, Any] | None = None
    out_of_scope: dict[str, Any] | None = None
    audit: dict[str, Any] = Field(default_factory=dict)
    human_in_the_loop: str | None = None
    versions: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int


# --------------------------------------------------------------- validation
class ValidationResultModel(BaseModel):
    employee_id: str
    country: str
    currency: str
    period: str
    validation_type: str
    expected_value: str | None
    actual_value: str | None
    difference: str | None
    tolerance: str
    status: Literal["PASS", "FAIL"]
    exception: bool
    reason_code: str
    detail: str
    engine_version: str
    rules_version: str
    run_id: str
    run_timestamp: str


class ValidationResponse(BaseModel):
    found: bool
    period: str
    filters: dict[str, Any]
    run: dict[str, Any]
    results: list[ValidationResultModel]
    summary: dict[str, Any]


# ------------------------------------------------------------------ ingest
class IngestResponse(BaseModel):
    provider: str
    model: str
    documents: int
    chunks: int
    knowledge_fingerprint: str
    index_status: str


# ------------------------------------------------------------------ health
class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    components: dict[str, Any]
    versions: dict[str, Any]


class ErrorResponse(BaseModel):
    error: str
    message: str
    trace_id: str | None
