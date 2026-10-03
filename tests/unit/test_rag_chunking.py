"""Chunk generation and metadata preservation."""

from app.rag.chunking import chunk_document, chunk_documents
from app.rag.documents import KnowledgeDocument, load_documents

REQUIRED_METADATA = {
    "chunk_id", "chunk_index", "doc_id", "source_document", "document_type",
    "document_title", "document_version", "section", "section_part", "char_count",
}


def _doc(body: str) -> KnowledgeDocument:
    return KnowledgeDocument(
        doc_id="TST-001", title="Test Doc", doc_type="sop", version="1.0",
        source_document="knowledge/sops/test.md", body=body, front_matter={},
    )


def test_one_chunk_per_section_with_heading_as_section():
    body = "# Test Doc\n\n> Synthetic disclaimer.\n\n## Purpose\n\nWhy.\n\n## Steps\n\nDo it.\n"
    chunks = chunk_document(_doc(body))
    assert [c.metadata["section"] for c in chunks] == ["Purpose", "Steps"]
    assert [c.content for c in chunks] == ["Why.", "Do it."]


def test_disclaimer_only_overview_is_skipped_but_real_overview_kept():
    body = "# Test Doc\n\nIntro text that matters.\n\n## A\n\ntext\n"
    chunks = chunk_document(_doc(body))
    assert chunks[0].metadata["section"] == "Overview"
    assert chunks[0].content == "Intro text that matters."


def test_level_three_heading_keeps_parent_path():
    body = "# T\n\n## Parent\n\n### Child\n\nchild text\n"
    chunks = chunk_document(_doc(body))
    assert [c.metadata["section"] for c in chunks] == ["Parent > Child"]  # empty parent skipped


def test_long_section_split_on_paragraphs():
    paragraphs = [f"Paragraph {i} " + "word " * 20 for i in range(6)]
    body = "# T\n\n## Long\n\n" + "\n\n".join(paragraphs) + "\n"
    chunks = chunk_document(_doc(body), max_chars=300)
    assert len(chunks) > 1
    assert all(c.metadata["section"] == "Long" for c in chunks)
    assert [c.metadata["section_part"] for c in chunks] == [f"{i}/{len(chunks)}" for i in range(1, len(chunks) + 1)]
    # No paragraph is cut: every paragraph appears whole in exactly one chunk.
    for paragraph in paragraphs:
        assert sum(paragraph.strip() in c.content for c in chunks) == 1


def test_repository_chunks_have_full_metadata_and_unique_ids():
    chunks = chunk_documents(load_documents())
    assert len(chunks) == 50
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    for chunk in chunks:
        assert REQUIRED_METADATA <= chunk.metadata.keys()
        assert chunk.metadata["chunk_id"] == chunk.chunk_id
        assert chunk.metadata["source_document"].startswith("knowledge/")
        assert chunk.content.strip()
        assert not chunk.content.lstrip().startswith(">")  # disclaimers are not indexed


def test_embedding_text_carries_title_and_section():
    chunk = chunk_document(_doc("# T\n\n## Tolerance\n\n**Tolerance:** 5.00 SYN\n"))[0]
    assert chunk.embedding_text.startswith("Test Doc > Tolerance\n")


def test_chunking_is_deterministic():
    first = [(c.chunk_id, c.content) for c in chunk_documents(load_documents())]
    second = [(c.chunk_id, c.content) for c in chunk_documents(load_documents())]
    assert first == second
