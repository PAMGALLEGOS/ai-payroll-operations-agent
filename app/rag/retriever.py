"""Semantic retrieval: Question -> Question Embedding -> Similarity Search -> Relevant Chunks.

The retriever answers only "what does the documented knowledge say?". It never
calculates payroll, never decides PASS / FAIL and never touches Validation
Engine results.

Weak evidence: a chunk counts as evidence only if its similarity is at least
`min_score`. When no chunk reaches it, the response is marked
`sufficient_evidence = False`, so the Agent (CP3) can say it has no documented
answer instead of guessing. Scores are not comparable across embedding models,
so each provider has its own default threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.rag.embeddings import EmbeddingProvider
from app.rag.vector_index import VectorIndexError, VectorIndex

# Default minimum similarity per provider.
#   fake:   calibrated on tests/evaluation/retrieval_cases.yaml (word-overlap scores).
#   gemini: calibrated with real Gemini (CP2 evaluation, decision N5): lowest
#           in-scope top score 0.7111, highest out-of-scope 0.5640 -> 0.638.
DEFAULT_MIN_SCORE = {"fake": 0.13, "gemini": 0.638}


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    content: str
    score: float
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "score": round(self.score, 4),
            "content": self.content,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class RetrievalResponse:
    query: str
    results: list[RetrievedChunk]          # only chunks with score >= min_score
    sufficient_evidence: bool
    top_score: float
    min_score: float
    embeddings_provider: str
    embeddings_model: str
    below_threshold: list[RetrievedChunk] = field(default_factory=list)  # for diagnostics only

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "sufficient_evidence": self.sufficient_evidence,
            "top_score": round(self.top_score, 4),
            "min_score": self.min_score,
            "embeddings_provider": self.embeddings_provider,
            "embeddings_model": self.embeddings_model,
            "results": [r.to_dict() for r in self.results],
        }


class Retriever:
    def __init__(
        self,
        index: VectorIndex,
        provider: EmbeddingProvider,
        top_k: int = 4,
        min_score: float | None = None,
    ):
        info = index.info
        if (info.embeddings_provider, info.embeddings_model, info.dimensions) != (
            provider.name,
            provider.model,
            provider.dimensions,
        ):
            raise VectorIndexError(
                "Index was built with "
                f"{info.embeddings_provider}/{info.embeddings_model}/{info.dimensions} but the query "
                f"provider is {provider.name}/{provider.model}/{provider.dimensions}. Rebuild the index."
            )
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        self.index = index
        self.provider = provider
        self.top_k = top_k
        self.min_score = DEFAULT_MIN_SCORE.get(provider.name, 0.5) if min_score is None else min_score

    def search(self, query: str) -> RetrievalResponse:
        if not query or not query.strip():
            raise ValueError("Query must not be empty")

        query_vector = self.provider.embed_query(query.strip())
        ranked = [
            RetrievedChunk(entry.chunk_id, entry.content, score, entry.metadata)
            for entry, score in self.index.search(query_vector, self.top_k)
        ]
        relevant = [c for c in ranked if c.score >= self.min_score]
        weak = [c for c in ranked if c.score < self.min_score]

        return RetrievalResponse(
            query=query,
            results=relevant,
            sufficient_evidence=bool(relevant),
            top_score=ranked[0].score if ranked else 0.0,
            min_score=self.min_score,
            embeddings_provider=self.provider.name,
            embeddings_model=self.provider.model,
            below_threshold=weak,
        )
