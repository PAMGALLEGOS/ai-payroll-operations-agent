"""Versioned prompts (decision C3-11). The file name carries the version.

Changing a prompt means adding a new file (e.g. intent_v2.md) and pointing the
constant below to it, so every response records exactly which prompt produced it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

INTENT = "intent_v1"
RAG_ANSWER = "rag_answer_v1"
TOOL_RAG_EXPLAIN = "tool_rag_explain_v1"


@lru_cache
def load_prompt(version: str) -> str:
    return (PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8")
