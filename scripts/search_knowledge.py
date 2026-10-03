"""Ask the knowledge index a question and print the retrieved chunks.

Usage:
    python scripts/search_knowledge.py "Who approves the payroll?" --provider fake
    python scripts/search_knowledge.py "What is the net pay tolerance?" --top-k 3 --json

Only retrieval: no LLM is called and no answer is generated (that is CP3).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.rag.embeddings import EmbeddingsError, create_embedding_provider  # noqa: E402
from app.rag.ingest import index_path, is_index_stale  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.rag.vector_index import VectorIndex, VectorIndexError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Semantic search over the knowledge index.")
    parser.add_argument("question")
    parser.add_argument("--provider", choices=["gemini", "fake"], help="Override EMBEDDINGS_PROVIDER")
    parser.add_argument("--top-k", type=int, help="Number of chunks to return")
    parser.add_argument("--json", action="store_true", help="Print the structured response as JSON")
    args = parser.parse_args()

    settings = get_settings()
    try:
        provider = create_embedding_provider(settings, args.provider)
        index = VectorIndex.load(index_path(provider.name))
        if is_index_stale(index):
            print("WARNING: knowledge/ changed since the index was built. Re-run ingest_knowledge.py.\n")
        retriever = Retriever(index, provider, top_k=args.top_k or settings.rag_top_k, min_score=settings.rag_min_score)
        response = retriever.search(args.question)
    except (EmbeddingsError, VectorIndexError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
        return 0

    print(f"Question  : {response.query}")
    print(f"Provider  : {response.embeddings_provider} / {response.embeddings_model}")
    print(f"Evidence  : {'sufficient' if response.sufficient_evidence else 'INSUFFICIENT'} "
          f"(top score {response.top_score:.4f}, threshold {response.min_score})\n")
    for rank, chunk in enumerate(response.results, start=1):
        meta = chunk.metadata
        print(f"[{rank}] {chunk.score:.4f}  {chunk.chunk_id}  {meta['document_title']} > {meta['section']}")
        print(f"     source: {meta['source_document']} ({meta['document_type']})")
        preview = " ".join(chunk.content.split())
        print(f"     {preview[:220]}{'...' if len(preview) > 220 else ''}\n")
    if not response.results:
        print("No chunk reached the similarity threshold: the knowledge base has no documented answer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
