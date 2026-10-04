"""FastAPI application (CP4, spec §14).

    uvicorn app.api.main:app --port 8000

Endpoints: POST /chat · GET /validation · POST /documents/ingest · GET /health
Interactive contract documentation: /docs

`create_app` is a factory so tests can inject an Agent built with fake providers
and temporary folders. The module-level `app` builds everything from .env at
startup; if building the Agent fails (for example no GEMINI_API_KEY), the API
still starts and reports the problem in /health.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request

from app.agent.factory import build_agent
from app.agent.orchestrator import Agent
from app.api.errors import register_error_handlers
from app.api.routes import chat, documents, health, validation
from app.api.state import ApiState
from app.core.config import Settings, get_settings
from app.core.paths import KNOWLEDGE_DIR, REPO_ROOT, VALIDATION_RESULTS_DIR, VECTOR_INDEX_DIR
from app.llm.client import LLMError
from app.observability.context import new_trace_id, reset_trace_id, set_trace_id
from app.observability.events import AgentObserver
from app.observability.logger import JsonEventLogger, configure_event_logging
from app.rag.embeddings import EmbeddingsError, create_embedding_provider
from app.validation.tool import ValidationTool


def _default_observer(settings: Settings) -> AgentObserver:
    log_file = (REPO_ROOT / settings.log_file) if settings.log_file else None
    return JsonEventLogger(configure_event_logging(log_file, settings.log_level))


def create_app(
    settings: Settings | None = None,
    *,
    agent: Agent | None = None,
    observer: AgentObserver | None = None,
    results_dir: Path = VALIDATION_RESULTS_DIR,
    index_dir: Path = VECTOR_INDEX_DIR,
    knowledge_dir: Path = KNOWLEDGE_DIR,
    llm_provider: str | None = None,
    embeddings_provider: str | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state = ApiState(
            settings=settings,
            tool=agent.tool if agent else ValidationTool(results_dir),
            index_dir=index_dir,
            knowledge_dir=knowledge_dir,
            observer=observer or (agent.observer if agent else _default_observer(settings)),
            agent=agent,
        )
        if agent is not None:
            state.embeddings = agent.retriever.provider if agent.retriever else create_embedding_provider(
                settings, embeddings_provider)
        else:
            try:
                state.embeddings = create_embedding_provider(settings, embeddings_provider)
                state.agent = build_agent(settings, llm_provider=llm_provider, embeddings=state.embeddings,
                                          results_dir=results_dir, index_dir=index_dir,
                                          knowledge_dir=knowledge_dir, observer=state.observer)
            except (LLMError, EmbeddingsError) as error:
                state.startup_error = str(error)
        app.state.api = state
        yield

    app = FastAPI(
        title="AI Payroll Operations & Validation Agent",
        description="Academic PoC — synthetic data only. The Validation Engine is the source of truth; "
                    "the Agent explains, it never approves payroll.",
        version="0.4.0",
        lifespan=lifespan,
    )
    register_error_handlers(app)

    @app.middleware("http")
    async def trace_requests(request: Request, call_next):
        trace_id = new_trace_id()
        request.state.trace_id = trace_id
        token = set_trace_id(trace_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            reset_trace_id(token)
        response.headers["X-Trace-Id"] = trace_id
        state = getattr(request.app.state, "api", None)
        if state is not None:
            state.observer.emit("api_request", trace_id=trace_id, method=request.method, path=request.url.path,
                                status_code=response.status_code,
                                duration_ms=int((time.perf_counter() - started) * 1000))
        return response

    for module in (chat, validation, documents, health):
        app.include_router(module.router)
    return app


app = create_app()
