"""Document loading: front matter, synthetic guard, folder/type agreement."""

import pytest

from app.rag.documents import DocumentLoadError, load_documents

FRONT = "---\ndoc_id: {id}\ntitle: T\ndoc_type: {type}\nversion: \"1.0\"\nsynthetic: {synthetic}\n---\n"


def _write(root, folder, name, text):
    path = root / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_repository_knowledge_loads():
    docs = load_documents()
    assert len(docs) == 9
    assert {d.doc_type for d in docs} == {"sop", "rule", "blueprint"}
    assert [d.source_document for d in docs] == sorted(d.source_document for d in docs)
    for doc in docs:
        assert doc.front_matter["synthetic"] is True
        assert doc.source_document.startswith("knowledge/")
        assert not doc.body.startswith("---")


def test_counts_by_type():
    docs = load_documents()
    counts = {t: sum(d.doc_type == t for d in docs) for t in ("sop", "rule", "blueprint")}
    assert counts == {"sop": 3, "rule": 5, "blueprint": 1}


def test_non_synthetic_document_is_refused(tmp_path):
    _write(tmp_path, "sops", "x.md", FRONT.format(id="X-1", type="sop", synthetic="false") + "# X\nbody\n")
    with pytest.raises(DocumentLoadError, match="synthetic"):
        load_documents(tmp_path)


def test_missing_front_matter_is_refused(tmp_path):
    _write(tmp_path, "sops", "x.md", "# No front matter\n")
    with pytest.raises(DocumentLoadError, match="front matter"):
        load_documents(tmp_path)


def test_doc_type_must_match_folder(tmp_path):
    _write(tmp_path, "sops", "x.md", FRONT.format(id="X-1", type="rule", synthetic="true") + "# X\nbody\n")
    with pytest.raises(DocumentLoadError, match="does not match folder"):
        load_documents(tmp_path)


def test_unknown_folder_is_refused(tmp_path):
    _write(tmp_path, "misc", "x.md", FRONT.format(id="X-1", type="sop", synthetic="true") + "# X\nbody\n")
    with pytest.raises(DocumentLoadError, match="unknown knowledge folder"):
        load_documents(tmp_path)


def test_duplicate_doc_id_is_refused(tmp_path):
    text = FRONT.format(id="X-1", type="sop", synthetic="true") + "# X\nbody\n"
    _write(tmp_path, "sops", "a.md", text)
    _write(tmp_path, "sops", "b.md", text)
    with pytest.raises(DocumentLoadError, match="Duplicate doc_id"):
        load_documents(tmp_path)


def test_empty_folder_is_refused(tmp_path):
    with pytest.raises(DocumentLoadError, match="No documents"):
        load_documents(tmp_path)


def test_windows_line_endings_are_accepted(tmp_path):
    text = FRONT.format(id="X-1", type="sop", synthetic="true") + "# X\n\n## Purpose\n\nbody\n"
    (tmp_path / "sops").mkdir()
    (tmp_path / "sops" / "x.md").write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    doc = load_documents(tmp_path)[0]
    assert "\r" not in doc.body
