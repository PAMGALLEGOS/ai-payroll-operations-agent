"""Split knowledge documents into retrievable chunks.

Strategy: one chunk per Markdown section.

  * A section starts at a `##` or `###` heading and runs until the next heading.
  * The `#` heading is the document title; text before the first `##` becomes an
    "Overview" chunk.
  * A section longer than `max_chars` is split on paragraph boundaries (blank
    lines), never in the middle of a sentence. A single paragraph longer than
    `max_chars` is kept whole rather than cut.
  * Empty sections (a heading followed directly by a sub-heading) produce no chunk.
  * An Overview made only of a `>` blockquote is the synthetic-data disclaimer
    every document carries; it is skipped because it holds no payroll knowledge
    and would only add near-identical noise chunks to every search.

Why sections: the synthetic documents are written so each section answers one
question ("Tolerance", "Approval Prerequisites"...). Section chunks keep a rule
and its explanation together, and the section heading becomes traceable
metadata the Agent and Auditor can cite later.

Each chunk is embedded together with its document title and section path
(`embedding_text`), so a short section like "Tolerance" still carries the
context of which rule it belongs to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.rag.documents import KnowledgeDocument

DEFAULT_MAX_CHARS = 1200
OVERVIEW_SECTION = "Overview"
_HEADING = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    content: str
    metadata: dict[str, Any]

    @property
    def embedding_text(self) -> str:
        return f"{self.metadata['document_title']} > {self.metadata['section']}\n{self.content}"


def _sections(body: str) -> list[tuple[str, str]]:
    """Return (section_path, text) pairs in document order."""
    sections: list[tuple[str, list[str]]] = [(OVERVIEW_SECTION, [])]
    h2: str | None = None

    for line in body.splitlines():
        match = _HEADING.match(line)
        if match:
            level, heading = len(match.group(1)), match.group(2)
            if level == 1:
                continue  # document title, already in metadata
            if level == 2:
                h2 = heading
                sections.append((heading, []))
            else:  # level 3
                sections.append((f"{h2} > {heading}" if h2 else heading, []))
            continue
        sections[-1][1].append(line)

    return [(path, "\n".join(lines).strip()) for path, lines in sections]


def _split_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def chunk_document(document: KnowledgeDocument, max_chars: int = DEFAULT_MAX_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section, text in _sections(document.body):
        if not text:
            continue
        if section == OVERVIEW_SECTION and all(
            line.startswith(">") for line in text.splitlines() if line.strip()
        ):
            continue
        pieces = _split_long(text, max_chars)
        for part_number, piece in enumerate(pieces, start=1):
            index = len(chunks)
            chunks.append(
                Chunk(
                    chunk_id=f"{document.doc_id}-C{index + 1:02d}",
                    doc_id=document.doc_id,
                    content=piece,
                    metadata={
                        "chunk_id": f"{document.doc_id}-C{index + 1:02d}",
                        "chunk_index": index,
                        "doc_id": document.doc_id,
                        "source_document": document.source_document,
                        "document_type": document.doc_type,
                        "document_title": document.title,
                        "document_version": document.version,
                        "section": section,
                        "section_part": f"{part_number}/{len(pieces)}",
                        "char_count": len(piece),
                    },
                )
            )
    return chunks


def chunk_documents(
    documents: list[KnowledgeDocument], max_chars: int = DEFAULT_MAX_CHARS
) -> list[Chunk]:
    return [chunk for doc in documents for chunk in chunk_document(doc, max_chars)]
