"""Intent classification: the LLM first, a deterministic keyword fallback second.

The LLM only returns an intent label (plus an English search query). It never
returns a route, an entity or a number. If the LLM fails or returns output that
does not match the schema (after the client's own retry), the bilingual keyword
classifier decides, and the response records `route_source = "fallback"`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.agent import prompts
from app.agent.contracts import IntentOutput
from app.agent.entities import Entities
from app.agent.keywords import keyword_intent
from app.agent.session import SessionState
from app.llm.client import LLMClient, LLMError


@dataclass(frozen=True)
class IntentDecision:
    intent: str
    retrieval_query: str
    source: str            # "llm_intent" | "fallback"
    error: str | None = None


def build_intent_payload(message: str, entities: Entities, session: SessionState) -> str:
    return json.dumps(
        {
            "message": message,
            "entities": {
                "employee_ids": entities.employee_ids,
                "period": entities.period,
                "validation_type": entities.validation_type,
            },
            "session": session.summary_for_llm(),
        },
        ensure_ascii=False,
    )


class IntentClassifier:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def classify(self, message: str, entities: Entities, session: SessionState) -> IntentDecision:
        try:
            output = self.llm.generate_json(
                task="intent",
                system=prompts.load_prompt(prompts.INTENT),
                user=build_intent_payload(message, entities, session),
                schema=IntentOutput,
            )
            return IntentDecision(output.intent, output.retrieval_query.strip(), "llm_intent")
        except LLMError as error:
            intent = keyword_intent(
                message,
                has_employee_in_message=bool(entities.employee_ids),
                has_employee_in_session=session.employee_id is not None,
                last_intent=session.last_intent,
            )
            return IntentDecision(intent, "", "fallback", error=str(error))
