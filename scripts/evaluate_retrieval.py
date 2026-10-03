"""Evaluate retrieval quality against tests/evaluation/retrieval_cases.yaml.

This is the step that REQUIRES REAL GEMINI ACCESS to be meaningful:

    python scripts/ingest_knowledge.py --provider gemini
    python scripts/evaluate_retrieval.py --provider gemini

With --provider fake it still runs (useful to check the script), but the fake
provider only measures word overlap, not real semantic quality.

Metrics:
  hit@1            share of in-scope questions whose first chunk comes from an expected document
  hit@k            share whose expected document appears anywhere in the top-k
  MRR              mean reciprocal rank of the first expected document
  out-of-scope     share of out-of-scope questions correctly reported as insufficient evidence
  false negatives  in-scope questions wrongly reported as insufficient evidence

It also prints the score distribution used to calibrate the similarity
threshold (RAG_MIN_SCORE) for the provider.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.core.paths import REPO_ROOT  # noqa: E402
from app.rag.embeddings import EmbeddingsError, create_embedding_provider  # noqa: E402
from app.rag.ingest import index_path  # noqa: E402
from app.rag.retriever import Retriever  # noqa: E402
from app.rag.vector_index import VectorIndex, VectorIndexError  # noqa: E402

CASES_FILE = REPO_ROOT / "tests" / "evaluation" / "retrieval_cases.yaml"


@dataclass
class EvaluationReport:
    provider: str
    model: str
    top_k: int
    min_score: float
    in_scope_cases: int
    out_of_scope_cases: int
    hit_at_1: float
    hit_at_k: float
    mrr: float
    out_of_scope_rejection: float
    false_negatives: list[str]
    misses: list[dict[str, Any]]
    lowest_in_scope_top_score: float
    highest_out_of_scope_top_score: float


def load_cases(path: Path = CASES_FILE) -> dict[str, list[dict[str, Any]]]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def evaluate(retriever: Retriever, cases: dict[str, list[dict[str, Any]]]) -> EvaluationReport:
    hits_1 = hits_k = 0
    reciprocal_ranks: list[float] = []
    misses: list[dict[str, Any]] = []
    false_negatives: list[str] = []
    in_scope_top: list[float] = []

    for case in cases["in_scope"]:
        response = retriever.search(case["query"])
        # Rank over ALL top-k chunks (including below-threshold) to measure ranking quality.
        ranked = sorted(response.results + response.below_threshold, key=lambda c: (-c.score, c.chunk_id))
        doc_ids = [c.metadata["doc_id"] for c in ranked]
        expected = set(case["expected_doc_ids"])
        in_scope_top.append(response.top_score)

        if not response.sufficient_evidence:
            false_negatives.append(case["id"])
        first = next((i for i, d in enumerate(doc_ids) if d in expected), None)
        if first == 0:
            hits_1 += 1
        if first is not None:
            hits_k += 1
            reciprocal_ranks.append(1 / (first + 1))
        else:
            reciprocal_ranks.append(0.0)
            misses.append({"id": case["id"], "query": case["query"], "retrieved": doc_ids})

    out_top: list[float] = []
    rejected = 0
    for case in cases["out_of_scope"]:
        response = retriever.search(case["query"])
        out_top.append(response.top_score)
        if not response.sufficient_evidence:
            rejected += 1

    n_in, n_out = len(cases["in_scope"]), len(cases["out_of_scope"])
    return EvaluationReport(
        provider=retriever.provider.name,
        model=retriever.provider.model,
        top_k=retriever.top_k,
        min_score=retriever.min_score,
        in_scope_cases=n_in,
        out_of_scope_cases=n_out,
        hit_at_1=round(hits_1 / n_in, 4),
        hit_at_k=round(hits_k / n_in, 4),
        mrr=round(sum(reciprocal_ranks) / n_in, 4),
        out_of_scope_rejection=round(rejected / n_out, 4) if n_out else 1.0,
        false_negatives=false_negatives,
        misses=misses,
        lowest_in_scope_top_score=round(min(in_scope_top), 4),
        highest_out_of_scope_top_score=round(max(out_top), 4) if out_top else 0.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate knowledge retrieval.")
    parser.add_argument("--provider", choices=["gemini", "fake"], help="Override EMBEDDINGS_PROVIDER")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    try:
        provider = create_embedding_provider(settings, args.provider)
        index = VectorIndex.load(index_path(provider.name))
        retriever = Retriever(index, provider, top_k=settings.rag_top_k, min_score=settings.rag_min_score)
        report = evaluate(retriever, load_cases())
    except (EmbeddingsError, VectorIndexError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(asdict(report), indent=2))
        return 0

    print(f"Provider / model        : {report.provider} / {report.model}")
    print(f"top_k / threshold       : {report.top_k} / {report.min_score}")
    print(f"In-scope cases          : {report.in_scope_cases}")
    print(f"  hit@1                 : {report.hit_at_1:.0%}")
    print(f"  hit@{report.top_k}                 : {report.hit_at_k:.0%}")
    print(f"  MRR                   : {report.mrr:.3f}")
    print(f"  false negatives       : {report.false_negatives or 'none'}")
    print(f"Out-of-scope cases      : {report.out_of_scope_cases}")
    print(f"  correctly rejected    : {report.out_of_scope_rejection:.0%}")
    print("Threshold calibration")
    print(f"  lowest in-scope top score     : {report.lowest_in_scope_top_score}")
    print(f"  highest out-of-scope top score: {report.highest_out_of_scope_top_score}")
    if report.lowest_in_scope_top_score > report.highest_out_of_scope_top_score:
        midpoint = (report.lowest_in_scope_top_score + report.highest_out_of_scope_top_score) / 2
        print(f"  separable; a threshold near {midpoint:.3f} separates both groups")
    else:
        print("  NOT separable with a single threshold on these cases")
    for miss in report.misses:
        print(f"MISS {miss['id']}: {miss['query']} -> {miss['retrieved']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
