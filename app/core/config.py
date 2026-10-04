"""Runtime settings, read from environment variables or a local .env file.

Secrets never live in code or in git: `.env` is git-ignored and `.env.example`
documents every variable with an empty value.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import REPO_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,  # an empty value in .env means "use the default"
    )

    # --- Shared Gemini credential ---
    gemini_api_key: SecretStr | None = None

    # --- Embeddings (CP2) ---
    # "gemini" is the approved provider (D2). "fake" is a deterministic,
    # offline test double for development, tests and demos without credentials.
    embeddings_provider: Literal["gemini", "fake"] = "gemini"
    # The "models/" prefix is required by the current Gemini API / SDK (confirmed in CP3, D4-02).
    gemini_embedding_model: str = "models/gemini-embedding-001"
    gemini_embedding_dimensions: int = 768

    # --- Retrieval (CP2) ---
    rag_top_k: int = 4
    # Minimum cosine similarity for a chunk to count as evidence. Empty means
    # "use the provider's default" (see app/rag/retriever.py).
    rag_min_score: float | None = None

    # --- Agent LLM (CP3) ---
    llm_provider: Literal["gemini", "fake"] = "gemini"
    # No default on purpose (decision C3-08): the text model must be chosen
    # explicitly and confirmed against the real Gemini API.
    gemini_model: str | None = None
    llm_timeout_seconds: int = 30

    # --- Session (CP3, decision D17) ---
    session_ttl_minutes: int = 30

    # --- API, UI and observability (CP4) ---
    api_base_url: str = "http://127.0.0.1:8000"      # where the Streamlit UI finds the API (D10)
    api_timeout_seconds: int = 60
    log_level: str = "INFO"
    log_file: str = "logs/agent.jsonl"               # relative to the repository root; empty = stdout only
    # Optional protection of POST /documents/ingest (D4-06). Mandatory in the cloud (CP5).
    ingest_token: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
