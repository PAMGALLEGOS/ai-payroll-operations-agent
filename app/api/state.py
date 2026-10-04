"""What the API keeps alive between requests: one Agent, its providers and paths.

Building the Agent can fail (for example GEMINI_API_KEY missing). The API still
starts, reports the problem in GET /health, and answers 503 on endpoints that
need the Agent, instead of crashing at import time.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.agent.orchestrator import Agent
from app.core.config import Settings
from app.observability.events import AgentObserver, NullObserver
from app.rag.embeddings import EmbeddingProvider
from app.validation.tool import ValidationTool


@dataclass
class ApiState:
    settings: Settings
    tool: ValidationTool
    index_dir: Path
    knowledge_dir: Path
    observer: AgentObserver = field(default_factory=NullObserver)
    agent: Agent | None = None
    embeddings: EmbeddingProvider | None = None
    startup_error: str | None = None
    ingest_lock: threading.Lock = field(default_factory=threading.Lock)
