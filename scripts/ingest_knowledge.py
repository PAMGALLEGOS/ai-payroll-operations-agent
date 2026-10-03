"""Build the vector index from the synthetic documents in knowledge/.

Usage:
    python scripts/ingest_knowledge.py                    # provider from .env (default: gemini)
    python scripts/ingest_knowledge.py --provider fake    # offline test double, no API key

Writes data/vector_index/<provider>/index.json. Document embeddings are created
here once; searches reuse them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.rag.embeddings import EmbeddingsError, create_embedding_provider  # noqa: E402
from app.rag.ingest import ingest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the knowledge vector index.")
    parser.add_argument("--provider", choices=["gemini", "fake"], help="Override EMBEDDINGS_PROVIDER")
    args = parser.parse_args()

    try:
        provider = create_embedding_provider(get_settings(), args.provider)
        index, path = ingest(provider)
    except EmbeddingsError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    info = index.info
    documents = sorted({e.metadata["source_document"] for e in index.entries})
    print(f"Provider / model  : {info.embeddings_provider} / {info.embeddings_model}")
    print(f"Dimensions        : {info.dimensions}")
    print(f"Documents         : {len(documents)}")
    print(f"Chunks indexed    : {info.chunk_count}")
    print(f"Knowledge hash    : {info.knowledge_fingerprint}")
    print(f"Index file        : {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
