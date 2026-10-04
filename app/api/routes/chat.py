"""POST /chat — a thin adapter over the CP3 Agent. It decides nothing itself."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.agent.contracts import AgentRequest
from app.agent.orchestrator import Agent
from app.api.dependencies import get_agent
from app.api.schemas import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, agent: Agent = Depends(get_agent)) -> ChatResponse:
    session_id = body.session_id or f"S-{uuid.uuid4().hex[:12]}"   # D4-04
    response = agent.handle(AgentRequest(session_id=session_id, message=body.message))
    return ChatResponse(**response.to_dict())
