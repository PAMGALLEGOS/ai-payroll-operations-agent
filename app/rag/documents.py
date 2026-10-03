"""Load the synthetic knowledge documents (parsing step of ingestion).

Each document is a Markdown file with a small YAML front matter block:

    ---
    doc_id: SOP-001
    title: Payroll Validation Process
    doc_type: sop
    version: "1.0"
    synthetic: true
    ---

`synthetic: true` is mandatory. It is a governance guard: a document without it
is refused, so a real corporate document dropped into knowledge/ by mistake can
never be indexed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.core.paths import KNOWLEDGE_DIR

# Folder -> document type. The front matter must agree with the folder.
FOLDER_TYPES = {"sops": "sop", "rules": "rule", "blueprint": "blueprint"}
REQUIRED_KEYS = ("doc_id", "title", "doc_type", "version", "synthetic")


class DocumentLoadError(ValueError):
    """A knowledge document is malformed or not allowed."""


@dataclass(frozen=True)
class KnowledgeDocument:
    doc_id: str
    title: str
    doc_type: str
    version: str
    source_document: str          # e.g. knowledge/rules/net_pay_rule.md
    body: str                     # Markdown without the front matter
    front_matter: dict[str, Any] = field(default_factory=dict)


def _split_front_matter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise DocumentLoadError(f"{path.name}: missing front matter block")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise DocumentLoadError(f"{path.name}: front matter is not closed with ---")
    try:
        meta = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as error:
        raise DocumentLoadError(f"{path.name}: invalid front matter: {error}") from None
    if not isinstance(meta, dict):
        raise DocumentLoadError(f"{path.name}: front matter must be a mapping")
    return meta, text[end + len("\n---\n"):]


def _relative(path: Path) -> str:
    """Portable source path: '<knowledge folder>/<type folder>/<file>', e.g. knowledge/rules/net_pay_rule.md.

    Built from the last three path parts (not the absolute path) so the same
    document has the same source and fingerprint on any machine.
    """
    return "/".join(path.parts[-3:])


def load_document(path: Path) -> KnowledgeDocument:
    # Normalise Windows line endings so parsing and fingerprints are identical on every OS.
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    meta, body = _split_front_matter(text, path)

    missing = [k for k in REQUIRED_KEYS if k not in meta]
    if missing:
        raise DocumentLoadError(f"{path.name}: front matter missing {missing}")
    if meta["synthetic"] is not True:
        raise DocumentLoadError(f"{path.name}: only documents marked 'synthetic: true' may be indexed")

    expected_type = FOLDER_TYPES.get(path.parent.name)
    if expected_type is None:
        raise DocumentLoadError(f"{path.name}: unknown knowledge folder '{path.parent.name}'")
    if meta["doc_type"] != expected_type:
        raise DocumentLoadError(
            f"{path.name}: doc_type '{meta['doc_type']}' does not match folder '{path.parent.name}'"
        )
    if not body.strip():
        raise DocumentLoadError(f"{path.name}: document body is empty")

    return KnowledgeDocument(
        doc_id=str(meta["doc_id"]),
        title=str(meta["title"]),
        doc_type=str(meta["doc_type"]),
        version=str(meta["version"]),
        source_document=_relative(path),
        body=body,
        front_matter=meta,
    )


def load_documents(knowledge_dir: Path = KNOWLEDGE_DIR) -> list[KnowledgeDocument]:
    """All documents under knowledge/, in a stable (sorted path) order."""
    if not knowledge_dir.exists():
        raise DocumentLoadError(f"Knowledge folder not found: {knowledge_dir}")
    documents = [load_document(p) for p in sorted(knowledge_dir.glob("*/*.md"))]
    if not documents:
        raise DocumentLoadError(f"No documents found in {knowledge_dir}")

    seen: dict[str, str] = {}
    for doc in documents:
        if doc.doc_id in seen:
            raise DocumentLoadError(
                f"Duplicate doc_id {doc.doc_id} in {doc.source_document} and {seen[doc.doc_id]}"
            )
        seen[doc.doc_id] = doc.source_document
    return documents
