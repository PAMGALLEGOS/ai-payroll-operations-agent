"""LLM explanations built ONLY from the evidence they are given (C3-04).

Two jobs:
  * answer_from_documents — RAG route: answer a procedural question from chunks.
  * explain_results       — TOOL_RAG route: explain Engine facts with chunks.

The facts are passed as read-only JSON. The explainer's text is never the
channel through which Engine numbers reach the user: those come from the
deterministic templates. `previous_issues` carries the Auditor's feedback for
the single allowed rewrite (D9).
"""

from __future__ import annotations

import json
from typing import Any

from app.agent import prompts
from app.llm.client import LLMClient


def _chunks_payload(chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"chunk_id": c["chunk_id"], "content": c["content"]} for c in chunks]


class Explainer:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def answer_from_documents(self, question: str, chunks: list[dict[str, Any]], language: str,
                              previous_issues: list[str] | None = None) -> str:
        payload = {"question": question, "language": language, "chunks": _chunks_payload(chunks),
                   "previous_issues": previous_issues or []}
        return self.llm.generate_text(
            task="rag_answer",
            system=prompts.load_prompt(prompts.RAG_ANSWER),
            user=json.dumps(payload, ensure_ascii=False),
        )

    def explain_results(self, question: str, facts: dict[str, Any], chunks: list[dict[str, Any]],
                        language: str, previous_issues: list[str] | None = None) -> str:
        payload = {"question": question, "language": language, "facts": facts,
                   "chunks": _chunks_payload(chunks), "previous_issues": previous_issues or []}
        return self.llm.generate_text(
            task="tool_rag_explain",
            system=prompts.load_prompt(prompts.TOOL_RAG_EXPLAIN),
            user=json.dumps(payload, ensure_ascii=False),
        )
