"""Retrieval evaluation against REAL Gemini embeddings.

Not part of the normal test run. Requires GEMINI_API_KEY and network access:

    pytest -m eval -v

The targets below are provisional acceptance criteria for the PoC, to be
confirmed in the CP2 review.
"""

import pytest

from app.core.config import get_settings
from app.rag.embeddings import create_embedding_provider
from app.rag.ingest import build_index
from app.rag.retriever import Retriever
from scripts.evaluate_retrieval import evaluate, load_cases

pytestmark = pytest.mark.eval

TARGET_HIT_AT_K = 0.90
TARGET_OUT_OF_SCOPE_REJECTION = 0.80


@pytest.fixture(scope="module")
def report():
    settings = get_settings()
    if not settings.gemini_api_key:
        pytest.skip("GEMINI_API_KEY not set: real Gemini evaluation cannot run")
    provider = create_embedding_provider(settings, "gemini")
    retriever = Retriever(build_index(provider), provider, top_k=settings.rag_top_k, min_score=settings.rag_min_score)
    return evaluate(retriever, load_cases())


def test_gemini_hit_at_k(report):
    assert report.hit_at_k >= TARGET_HIT_AT_K, report.misses


def test_gemini_out_of_scope_rejection(report):
    assert report.out_of_scope_rejection >= TARGET_OUT_OF_SCOPE_REJECTION


def test_gemini_no_false_negatives(report):
    assert report.false_negatives == []
