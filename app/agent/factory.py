"""Build a ready-to-use Agent from settings.

Providers can be overridden ("fake" / "gemini") so the same Agent runs offline
for tests and demos, or with real Gemini for evaluation.
"""

from __future__ import annotations

from pathlib import Path

from app.agent.fake_handlers import make_fake_llm
from app.agent.knowledge_guard import KnowledgeGuard
from app.agent.orchestrator import Agent
from app.agent.session import SessionStore
from app.core.config import Settings
from app.core.paths import KNOWLEDGE_DIR, VALIDATION_RESULTS_DIR, VECTOR_INDEX_DIR
from app.llm.client import LLMClient, LLMConfigError
from app.llm.gemini_client import GeminiLLMClient
from app.observability.events import AgentObserver
from app.observability.llm import ObservedLLMClient
from app.rag.embeddings import EmbeddingProvider, create_embedding_provider
from app.rag.ingest import index_path
from app.rag.retriever import Retriever
from app.rag.vector_index import VectorIndex, VectorIndexError
from app.validation.tool import ValidationTool


def create_llm_client(settings: Settings, provider: str | None = None) -> LLMClient:
    name = provider or settings.llm_provider
    if name == "fake":
        return make_fake_llm()
    if name == "gemini":
        key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
        if not key:
            raise LLMConfigError(
                "The Gemini LLM needs GEMINI_API_KEY. Set it in .env, or use LLM_PROVIDER=fake."
            )
        return GeminiLLMClient(key, settings.gemini_model, settings.llm_timeout_seconds)
    raise LLMConfigError(f"Unknown LLM provider '{name}' (use 'gemini' or 'fake')")


def load_knowledge(
    settings: Settings,
    embeddings: EmbeddingProvider,
    index_dir: Path = VECTOR_INDEX_DIR,
    knowledge_dir: Path = KNOWLEDGE_DIR,
) -> tuple[Retriever | None, KnowledgeGuard]:
    """Load the index for this embeddings provider. A missing index yields (None, guard 'missing')."""
    try:
        index: VectorIndex | None = VectorIndex.load(index_path(embeddings.name, index_dir))
        retriever: Retriever | None = Retriever(
            index, embeddings, top_k=settings.rag_top_k, min_score=settings.rag_min_score)
    except VectorIndexError:
        index, retriever = None, None   # the Agent answers documentary questions with "index unavailable"
    return retriever, KnowledgeGuard(index, knowledge_dir)


def build_agent(
    settings: Settings,
    *,
    llm: LLMClient | None = None,
    llm_provider: str | None = None,
    embeddings: EmbeddingProvider | None = None,
    embeddings_provider: str | None = None,
    results_dir: Path = VALIDATION_RESULTS_DIR,
    index_dir: Path = VECTOR_INDEX_DIR,
    knowledge_dir: Path = KNOWLEDGE_DIR,
    observer: AgentObserver | None = None,
) -> Agent:
    llm = llm or create_llm_client(settings, llm_provider)
    if observer is not None:
        llm = ObservedLLMClient(llm, observer)   # records llm_called events (D4-08)
    embeddings = embeddings or create_embedding_provider(settings, embeddings_provider)
    retriever, guard = load_knowledge(settings, embeddings, index_dir, knowledge_dir)

    return Agent(
        tool=ValidationTool(results_dir),
        llm=llm,
        retriever=retriever,
        knowledge_guard=guard,
        sessions=SessionStore(settings.session_ttl_minutes),
        observer=observer,
    )
