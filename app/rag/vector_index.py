"""A small, inspectable vector index (decision D18: no vector database).

The whole index is one JSON file: index metadata, then one entry per chunk with
its text, metadata and vector. For ~50 chunks a linear scan with cosine
similarity is instant, and anyone can open the file and see exactly what was
indexed and with which model.

Cosine similarity is written out in plain Python on purpose, so the maths is
visible: similarity = (a · b) / (|a| × |b|), from -1 (opposite) to 1 (same direction).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

INDEX_FORMAT_VERSION = 1


class VectorIndexError(RuntimeError):
    """The index file is missing, malformed or incompatible."""


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"Vectors have different sizes: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass(frozen=True)
class IndexEntry:
    chunk_id: str
    content: str
    metadata: dict[str, Any]
    vector: list[float]


@dataclass(frozen=True)
class IndexInfo:
    format_version: int
    embeddings_provider: str
    embeddings_model: str
    dimensions: int
    knowledge_fingerprint: str   # SHA-256 of the indexed documents
    chunk_count: int
    created_at: str


class VectorIndex:
    def __init__(self, info: IndexInfo, entries: list[IndexEntry]):
        if info.chunk_count != len(entries):
            raise VectorIndexError("chunk_count does not match the number of entries")
        for entry in entries:
            if len(entry.vector) != info.dimensions:
                raise VectorIndexError(f"Vector of {entry.chunk_id} has the wrong size")
        self.info = info
        self.entries = entries

    def search(self, query_vector: Sequence[float], top_k: int) -> list[tuple[IndexEntry, float]]:
        """Top-k entries by cosine similarity. Ties are broken by chunk_id so order is stable."""
        scored = [(entry, cosine_similarity(query_vector, entry.vector)) for entry in self.entries]
        scored.sort(key=lambda pair: (-pair[1], pair[0].chunk_id))
        return scored[:top_k]

    # -------------------------------------------------------- persistence
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"index": asdict(self.info), "entries": [asdict(e) for e in self.entries]}
        path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "VectorIndex":
        if not path.exists():
            raise VectorIndexError(
                f"Vector index not found: {path}. Build it with scripts/ingest_knowledge.py"
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            info = IndexInfo(**payload["index"])
            entries = [IndexEntry(**e) for e in payload["entries"]]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise VectorIndexError(f"Vector index is malformed: {error}") from None
        if info.format_version != INDEX_FORMAT_VERSION:
            raise VectorIndexError(f"Unsupported index format version {info.format_version}")
        return cls(info, entries)
