"""Default bilingual answers for the fake LLM (tests and offline demos).

They behave like a well-behaved LLM: they classify with the same bilingual
keyword rules as the fallback, rewrite Spanish questions into English search
queries with a small glossary, and write short, cited explanations that only
reuse text from the facts and chunks they receive. Tests that need a
misbehaving LLM use FakeLLMClient.script(...) instead.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.keywords import glossary_to_english, keyword_intent
from app.agent.language import detect_language
from app.llm.fake_client import FakeLLMClient

_FIRST_SENTENCE = re.compile(r"^(.+?(?<!\d)[.!?])(?:\s|$)", re.S)


def _first_sentence(content: str) -> str:
    text = " ".join(content.replace("**", "").replace("`", "").split())
    match = _FIRST_SENTENCE.match(text)
    return (match.group(1) if match else text)[:300]


def _cited(chunks: list[dict[str, Any]], language: str, limit: int = 2) -> str:
    lead = "Según la documentación" if language == "es" else "According to the documentation"
    return " ".join(f"{lead} [{c['chunk_id']}]: {_first_sentence(c['content'])}" for c in chunks[:limit])


def intent_handler(system: str, user: str) -> dict[str, Any]:
    payload = json.loads(user)
    message = payload["message"]
    session = payload.get("session") or {}
    intent = keyword_intent(
        message,
        has_employee_in_message=bool(payload["entities"]["employee_ids"]),
        has_employee_in_session=session.get("employee_in_context") is not None,
        last_intent=session.get("last_intent"),
    )
    query = glossary_to_english(message) if detect_language(message) == "es" else message
    return {"intent": intent, "retrieval_query": query, "confidence": "high"}


def rag_answer_handler(system: str, user: str) -> str:
    payload = json.loads(user)
    return _cited(payload["chunks"], payload["language"])


def tool_rag_explain_handler(system: str, user: str) -> str:
    payload = json.loads(user)
    language, facts = payload["language"], payload["facts"]
    sentences = []
    for row in facts.get("results", []):
        if row["status"] != "FAIL":
            continue
        if language == "es":
            sentences.append(f"{row['employee_id']}: {row['validation_type']} tiene estado FAIL "
                             f"con código de motivo {row['reason_code']}.")
        else:
            sentences.append(f"For {row['employee_id']}, {row['validation_type']} is FAIL "
                             f"with reason code {row['reason_code']}.")
    sentences.append(_cited(payload["chunks"], language))
    return " ".join(sentences)


def default_handlers() -> dict[str, Any]:
    return {
        "intent": intent_handler,
        "rag_answer": rag_answer_handler,
        "tool_rag_explain": tool_rag_explain_handler,
    }


def make_fake_llm() -> FakeLLMClient:
    return FakeLLMClient(default_handlers())
