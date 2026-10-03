"""Cosine similarity, ordering and index persistence."""

import json

import pytest

from app.rag.vector_index import (
    INDEX_FORMAT_VERSION,
    IndexEntry,
    IndexInfo,
    VectorIndex,
    VectorIndexError,
    cosine_similarity,
)


def _index(vectors: dict[str, list[float]]) -> VectorIndex:
    dims = len(next(iter(vectors.values())))
    entries = [IndexEntry(cid, f"content {cid}", {"chunk_id": cid}, v) for cid, v in vectors.items()]
    info = IndexInfo(INDEX_FORMAT_VERSION, "fake", "m", dims, "hash", len(entries), "2026-10-03T00:00:00Z")
    return VectorIndex(info, entries)


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ([1, 0], [1, 0], 1.0),
        ([1, 0], [0, 1], 0.0),
        ([1, 0], [-1, 0], -1.0),
        ([3, 4], [6, 8], 1.0),       # same direction, different length
        ([0, 0], [1, 0], 0.0),       # zero vector defined as 0, not an error
    ],
)
def test_cosine_similarity(a, b, expected):
    assert cosine_similarity(a, b) == pytest.approx(expected)


def test_cosine_rejects_different_sizes():
    with pytest.raises(ValueError):
        cosine_similarity([1, 0], [1, 0, 0])


def test_search_orders_by_score_descending():
    index = _index({"A": [1, 0], "B": [0.6, 0.8], "C": [0, 1]})
    ids = [e.chunk_id for e, _ in index.search([1, 0], top_k=3)]
    assert ids == ["A", "B", "C"]


def test_search_breaks_ties_by_chunk_id():
    index = _index({"Z": [1, 0], "A": [1, 0], "M": [1, 0]})
    assert [e.chunk_id for e, _ in index.search([1, 0], top_k=3)] == ["A", "M", "Z"]


def test_search_respects_top_k():
    index = _index({"A": [1, 0], "B": [0, 1], "C": [1, 1]})
    assert len(index.search([1, 0], top_k=2)) == 2


def test_save_and_load_roundtrip(tmp_path):
    index = _index({"A": [1.0, 0.0], "B": [0.0, 1.0]})
    path = tmp_path / "fake" / "index.json"
    index.save(path)
    loaded = VectorIndex.load(path)
    assert loaded.info == index.info
    assert loaded.entries == index.entries
    # Human-readable: plain JSON with the metadata at the top.
    assert json.loads(path.read_text())["index"]["embeddings_provider"] == "fake"


def test_load_missing_index_explains_how_to_build_it(tmp_path):
    with pytest.raises(VectorIndexError, match="ingest_knowledge"):
        VectorIndex.load(tmp_path / "missing.json")


def test_load_malformed_index(tmp_path):
    path = tmp_path / "index.json"
    path.write_text('{"index": {}}')
    with pytest.raises(VectorIndexError, match="malformed"):
        VectorIndex.load(path)


def test_vector_size_must_match_index_dimensions():
    info = IndexInfo(INDEX_FORMAT_VERSION, "fake", "m", 3, "h", 1, "t")
    with pytest.raises(VectorIndexError, match="wrong size"):
        VectorIndex(info, [IndexEntry("A", "c", {}, [1.0, 0.0])])
