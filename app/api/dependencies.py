"""Shared request dependencies: access to the API state, the Agent and the ingest token."""

from __future__ import annotations

import secrets

from fastapi import Header, Request

from app.agent.orchestrator import Agent
from app.api.errors import ApiError
from app.api.state import ApiState


def get_state(request: Request) -> ApiState:
    return request.app.state.api


def get_agent(request: Request) -> Agent:
    state = get_state(request)
    if state.agent is None:
        raise ApiError(503, "agent_unavailable",
                       f"The Agent is not available: {state.startup_error or 'not initialised'}")
    return state.agent


def check_ingest_token(request: Request, x_ingest_token: str | None = Header(default=None)) -> None:
    """D4-06: when INGEST_TOKEN is configured, POST /documents/ingest requires it."""
    configured = get_state(request).settings.ingest_token
    if configured is None or not configured.get_secret_value():
        return
    if x_ingest_token is None or not secrets.compare_digest(x_ingest_token, configured.get_secret_value()):
        raise ApiError(401, "unauthorized", "A valid X-Ingest-Token header is required to rebuild the index")
