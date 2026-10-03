"""Embeddings providers behind one interface (decision D2: Gemini Embeddings).

The rest of the RAG layer only knows `EmbeddingProvider`. Swapping Gemini for
another provider means adding one class here; ingestion, the index and the
retriever do not change.

Two methods instead of one because retrieval models embed documents and
questions differently (Gemini calls these RETRIEVAL_DOCUMENT and
RETRIEVAL_QUERY). Using the right one for each side improves ranking.

Providers:
  * GeminiEmbeddingProvider — the approved provider. Needs GEMINI_API_KEY.
  * FakeEmbeddingProvider   — deterministic, offline test double based on word
    hashing. It captures word overlap, not meaning: good enough to test the
    pipeline end to end, NOT a measure of real retrieval quality.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Any, Sequence

from app.core.config import Settings


class EmbeddingsError(RuntimeError):
    """The provider failed to produce embeddings."""


class EmbeddingsConfigError(EmbeddingsError):
    """The provider cannot be created with the current settings (e.g. no API key)."""


def l2_normalize(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return [0.0 for _ in vector]
    return [v / norm for v in vector]


class EmbeddingProvider(ABC):
    """Contract every embeddings provider must satisfy."""

    name: str
    model: str
    dimensions: int

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed knowledge chunks (called once, at ingestion)."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a user question (called per query)."""


# --------------------------------------------------------------------- fake
_TOKEN = re.compile(r"[a-z0-9_]+")
_STOPWORDS = frozenset(
    "a an and are as at be by can does for from how if in is it its of on or "
    "the this that to was what when which who why with not no do".split()
)


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic feature-hashing embeddings. Same text -> same vector, always.

    Each word (and each pair of consecutive words) is hashed with SHA-256 into
    one of `dimensions` buckets; the vector is then L2-normalised. SHA-256 is
    used instead of Python's hash() because hash() changes between runs.
    """

    name = "fake"
    model = "fake-hashing-v1"

    def __init__(self, dimensions: int = 1024):
        self.dimensions = dimensions

    def _tokens(self, text: str) -> list[str]:
        return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = self._tokens(text)
        features = tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]
        for feature in features:
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        return l2_normalize(vector)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


# ------------------------------------------------------------------- gemini
class GeminiEmbeddingProvider(EmbeddingProvider):
    """Gemini embeddings through the google-genai SDK.

    * Default model gemini-embedding-001 with task_type RETRIEVAL_DOCUMENT /
      RETRIEVAL_QUERY. Vectors are L2-normalised here because the model only
      returns normalised vectors at 3072 dimensions.
    * gemini-embedding-2 is NOT supported in this PoC: it does not accept
      task_type and needs a different prompt format, which has not been
      validated here. It is refused explicitly instead of half-supported.

    `client` can be injected so tests verify the request without network access.
    """

    name = "gemini"
    BATCH_SIZE = 100

    def __init__(self, api_key: str, model: str, dimensions: int, client: Any | None = None):
        if not api_key:
            raise EmbeddingsConfigError("GEMINI_API_KEY is empty")
        if "embedding-2" in model:
            raise EmbeddingsConfigError(
                f"Model '{model}' does not support task_type and is not supported in this PoC; "
                "use gemini-embedding-001"
            )
        self.model = model
        self.dimensions = dimensions
        if client is None:
            from google import genai  # imported lazily: tests never need the SDK

            client = genai.Client(api_key=api_key)
        self._client = client

    def _call(self, texts: list[str], task_type: str) -> list[list[float]]:
        from google.genai import types

        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dimensions)
        try:
            response = self._client.models.embed_content(model=self.model, contents=texts, config=config)
        except Exception as error:  # SDK raises several error types; surface one clear error
            raise EmbeddingsError(f"Gemini embeddings request failed: {error}") from error

        vectors = [list(e.values) for e in (response.embeddings or [])]
        if len(vectors) != len(texts):
            raise EmbeddingsError(f"Gemini returned {len(vectors)} embeddings for {len(texts)} texts")
        if any(len(v) != self.dimensions for v in vectors):
            raise EmbeddingsError(f"Gemini returned vectors with unexpected size (expected {self.dimensions})")
        return [l2_normalize(v) for v in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.BATCH_SIZE):
            vectors.extend(self._call(texts[start:start + self.BATCH_SIZE], "RETRIEVAL_DOCUMENT"))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._call([text], "RETRIEVAL_QUERY")[0]


# ------------------------------------------------------------------ factory
def create_embedding_provider(settings: Settings, provider: str | None = None) -> EmbeddingProvider:
    """Build the configured provider, failing early and clearly when it cannot work."""
    name = provider or settings.embeddings_provider
    if name == "fake":
        return FakeEmbeddingProvider()
    if name == "gemini":
        key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
        if not key:
            raise EmbeddingsConfigError(
                "Gemini embeddings need GEMINI_API_KEY. Set it in .env (see .env.example), "
                "or use the offline test double with EMBEDDINGS_PROVIDER=fake."
            )
        return GeminiEmbeddingProvider(
            api_key=key,
            model=settings.gemini_embedding_model,
            dimensions=settings.gemini_embedding_dimensions,
        )
    raise EmbeddingsConfigError(f"Unknown embeddings provider '{name}' (use 'gemini' or 'fake')")
