"""Ingestion and semantic retrieval with the deterministic fake provider.

The fake provider measures word overlap, so these tests prove the pipeline
(embed once -> index -> embed question -> rank -> metadata) works. Real
semantic quality is measured separately with Gemini (pytest -m eval).
"""

import shutil
from datetime import datetime, timezone

import pytest

from app.core.paths import KNOWLEDGE_DIR
from app.rag.embeddings import FakeEmbeddingProvider
from app.rag.ingest import build_index, index_path, ingest, is_index_stale
from app.rag.retriever import DEFAULT_MIN_SCORE, Retriever
from app.rag.vector_index import VectorIndex, VectorIndexError
from scripts.evaluate_retrieval import evaluate, load_cases


class CountingProvider(FakeEmbeddingProvider):
    """Fake provider that counts calls, to prove documents are embedded only once."""

    def __init__(self):
        super().__init__()
        self.document_calls = 0
        self.query_calls = 0

    def embed_documents(self, texts):
        self.document_calls += 1
        return super().embed_documents(texts)

    def embed_query(self, text):
        self.query_calls += 1
        return super().embed_query(text)


def _fixed_clock():
    return datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def index() -> VectorIndex:
    return build_index(FakeEmbeddingProvider(), clock=_fixed_clock)


@pytest.fixture
def retriever(index) -> Retriever:
    return Retriever(index, FakeEmbeddingProvider(), top_k=4)


# ------------------------------------------------------------- ingestion
def test_index_contains_every_chunk_with_metadata(index):
    assert index.info.chunk_count == len(index.entries) == 50
    assert index.info.embeddings_provider == "fake"
    for entry in index.entries:
        assert entry.metadata["source_document"].startswith("knowledge/")
        assert entry.metadata["document_type"] in {"sop", "rule", "blueprint"}
        assert entry.metadata["section"]
        assert len(entry.vector) == index.info.dimensions


def test_indexing_is_deterministic(index):
    again = build_index(FakeEmbeddingProvider(), clock=_fixed_clock)
    assert again.info == index.info
    assert [(e.chunk_id, e.vector) for e in again.entries] == [(e.chunk_id, e.vector) for e in index.entries]


def test_documents_embedded_once_queries_do_not_reembed(tmp_path):
    provider = CountingProvider()
    built, path = ingest(provider, index_dir=tmp_path)
    assert provider.document_calls == 1
    assert path == index_path("fake", tmp_path)

    retriever = Retriever(VectorIndex.load(path), provider)
    retriever.search("What is the net pay tolerance?")
    retriever.search("Who approves the payroll?")
    assert provider.document_calls == 1   # unchanged by queries
    assert provider.query_calls == 2


def test_stale_index_detected_when_knowledge_changes(tmp_path, index):
    copy = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_DIR, copy)
    assert not is_index_stale(index, copy)
    doc = copy / "rules" / "net_pay_rule.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nExtra sentence.\n", encoding="utf-8")
    assert is_index_stale(index, copy)


def test_index_from_another_provider_or_model_is_refused(index):
    class OtherModel(FakeEmbeddingProvider):
        model = "fake-hashing-v2"

    with pytest.raises(VectorIndexError, match="Rebuild the index"):
        Retriever(index, OtherModel())


# ------------------------------------------------------------- retrieval
@pytest.mark.parametrize(
    "query,expected_doc",
    [
        ("What is the net pay tolerance?", "RULE-003"),
        ("Is a difference exactly equal to the tolerance a PASS?", "RULE-004"),
        ("Which deductions are included in total deductions?", "RULE-002"),
        ("Can the preparer approve their own payroll?", "SOP-003"),
        ("What evidence does a validation run produce?", "SOP-001"),
        ("What happens when an input value is missing?", "RULE-005"),
    ],
)
def test_relevant_document_is_retrieved(retriever, query, expected_doc):
    response = retriever.search(query)
    assert response.sufficient_evidence
    assert expected_doc in [c.metadata["doc_id"] for c in response.results]


def test_results_are_ordered_and_carry_content_score_and_metadata(retriever):
    response = retriever.search("What is the net pay tolerance?")
    scores = [c.score for c in response.results]
    assert scores == sorted(scores, reverse=True)
    top = response.results[0]
    assert top.content and top.chunk_id
    assert {"source_document", "document_type", "section", "chunk_id"} <= top.metadata.keys()
    data = response.to_dict()
    assert data["results"][0]["metadata"]["source_document"] == top.metadata["source_document"]


@pytest.mark.parametrize("query", ["What is the capital of France?", "Recommend a good pasta recipe"])
def test_unrelated_query_reports_insufficient_evidence(retriever, query):
    response = retriever.search(query)
    assert response.sufficient_evidence is False
    assert response.results == []
    assert response.top_score < response.min_score


def test_threshold_defaults_per_provider(index):
    assert Retriever(index, FakeEmbeddingProvider()).min_score == DEFAULT_MIN_SCORE["fake"]
    assert Retriever(index, FakeEmbeddingProvider(), min_score=0.5).min_score == 0.5


def test_empty_query_is_rejected(retriever):
    with pytest.raises(ValueError):
        retriever.search("   ")


def test_retrieval_never_returns_validation_results(retriever):
    # RAG returns documentary chunks only: no employee results, no PASS/FAIL decision.
    data = retriever.search("Did EMP024 pass validation?").to_dict()
    assert set(data) == {
        "query", "sufficient_evidence", "top_score", "min_score",
        "embeddings_provider", "embeddings_model", "results",
    }
    for result in data["results"]:
        assert result["metadata"]["source_document"].startswith("knowledge/")


def test_evaluation_script_runs_on_fake_provider(retriever):
    report = evaluate(retriever, load_cases())
    assert report.in_scope_cases == 16 and report.out_of_scope_cases == 5
    assert report.hit_at_k == 1.0
    assert report.out_of_scope_rejection == 1.0
