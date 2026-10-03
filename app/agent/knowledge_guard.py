"""Knowledge guard: the Agent refuses to retrieve from a stale or missing index (N9).

Recomputing the knowledge fingerprint means reading every document, so the
guard only recomputes it when a file in knowledge/ changed (or was added or
removed) since the last check.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from app.core.paths import KNOWLEDGE_DIR
from app.rag.documents import DocumentLoadError
from app.rag.ingest import is_index_stale
from app.rag.vector_index import VectorIndex

IndexStatus = Literal["ok", "stale", "missing"]


class KnowledgeGuard:
    def __init__(self, index: VectorIndex | None, knowledge_dir: Path = KNOWLEDGE_DIR):
        self.index = index
        self.knowledge_dir = knowledge_dir
        self._signature: tuple | None = None
        self._status: IndexStatus = "missing" if index is None else "ok"

    def _current_signature(self) -> tuple:
        files = sorted(self.knowledge_dir.glob("*/*.md"))
        return tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for f in files)

    def status(self) -> IndexStatus:
        if self.index is None:
            return "missing"
        signature = self._current_signature()
        if signature != self._signature:
            try:
                self._status = "stale" if is_index_stale(self.index, self.knowledge_dir) else "ok"
            except DocumentLoadError:
                self._status = "stale"
            self._signature = signature
        return self._status
