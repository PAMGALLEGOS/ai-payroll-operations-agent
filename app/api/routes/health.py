"""GET /health — status of each component. Always HTTP 200 while the process is alive.

status = "ok" only when the Agent is built, a validation run exists and the
knowledge index is current; otherwise "degraded", with the reason per component.
No secrets are ever included.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies import get_state
from app.api.schemas import HealthResponse
from app.api.state import ApiState
from app.validation import ENGINE_VERSION

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(state: ApiState = Depends(get_state)) -> HealthResponse:
    periods = state.tool.available_periods()
    agent = state.agent
    components: dict = {
        "validation_runs": {"status": "ok" if periods else "missing", "periods": periods},
        "agent": {"status": "ok" if agent else "unavailable", "error": state.startup_error},
    }
    if agent is not None:
        index_status = agent.guard.status()
        index = agent.guard.index
        components["knowledge_index"] = {
            "status": index_status,
            "provider": index.info.embeddings_provider if index else None,
            "model": index.info.embeddings_model if index else None,
            "chunks": index.info.chunk_count if index else 0,
        }
        components["llm"] = {"status": "ok", "provider": agent.llm.name, "model": agent.llm.model}
    else:
        components["knowledge_index"] = {"status": "unknown"}
        components["llm"] = {"status": "unavailable"}

    healthy = (agent is not None and bool(periods) and components["knowledge_index"]["status"] == "ok")
    return HealthResponse(
        status="ok" if healthy else "degraded",
        components=components,
        versions={"engine_version": ENGINE_VERSION,
                  "ingest_protected": bool(state.settings.ingest_token
                                           and state.settings.ingest_token.get_secret_value())},
    )
