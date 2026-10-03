"""Ingestion: Documents -> Parsing -> Chunking -> Embeddings -> Vector Index.

Document embeddings are computed here, ONCE, and stored in the index file.
Queries never re-embed documents; they only embed the question.

The index records a fingerprint of the knowledge documents. If a document
changes after the index was built, `is_index_stale` detects it so the index can
be rebuilt (decision D15: rebuild from the repository's knowledge/ folder only).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.core.paths import KNOWLEDGE_DIR, VECTOR_INDEX_DIR
from app.rag.chunking import chunk_documents
from app.rag.documents import KnowledgeDocument, load_documents
from app.rag.embeddings import EmbeddingProvider
from app.rag.vector_index import INDEX_FORMAT_VERSION, IndexEntry, IndexInfo, VectorIndex


def index_path(provider_name: str, index_dir: Path = VECTOR_INDEX_DIR) -> Path:
    """One index per provider, so a fake index is never queried with Gemini vectors."""
    return index_dir / provider_name / "index.json"


def knowledge_fingerprint(documents: list[KnowledgeDocument]) -> str:
    digest = hashlib.sha256()
    for doc in sorted(documents, key=lambda d: d.source_document):
        digest.update(doc.source_document.encode("utf-8"))
        digest.update(b"\0")
        digest.update(doc.body.encode("utf-8"))
        digest.update(repr(sorted(doc.front_matter.items())).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def build_index(
    provider: EmbeddingProvider,
    knowledge_dir: Path = KNOWLEDGE_DIR,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> VectorIndex:
    documents = load_documents(knowledge_dir)
    chunks = chunk_documents(documents)
    vectors = provider.embed_documents([c.embedding_text for c in chunks])

    entries = [
        IndexEntry(chunk_id=c.chunk_id, content=c.content, metadata=c.metadata, vector=v)
        for c, v in zip(chunks, vectors, strict=True)
    ]
    info = IndexInfo(
        format_version=INDEX_FORMAT_VERSION,
        embeddings_provider=provider.name,
        embeddings_model=provider.model,
        dimensions=provider.dimensions,
        knowledge_fingerprint=knowledge_fingerprint(documents),
        chunk_count=len(entries),
        created_at=clock().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    return VectorIndex(info, entries)


def ingest(
    provider: EmbeddingProvider,
    knowledge_dir: Path = KNOWLEDGE_DIR,
    index_dir: Path = VECTOR_INDEX_DIR,
) -> tuple[VectorIndex, Path]:
    """Build the index and save it. Returns the index and where it was written."""
    index = build_index(provider, knowledge_dir)
    path = index_path(provider.name, index_dir)
    index.save(path)
    return index, path


def is_index_stale(index: VectorIndex, knowledge_dir: Path = KNOWLEDGE_DIR) -> bool:
    return index.info.knowledge_fingerprint != knowledge_fingerprint(load_documents(knowledge_dir))
