"""Agent & orchestration (CP3).

    contracts.py      request / response / intent contracts
    language.py       deterministic EN/ES detection
    keywords.py       bilingual vocabulary: keyword intent fallback, prohibited actions, glossary
    entities.py       deterministic entity extraction (EMP###, period, validation type)
    session.py        in-memory session store with TTL
    intent.py         intent classification: LLM first, keyword fallback
    router.py         deterministic matrix: intent + entities + session -> route
    responses.py      deterministic bilingual templates (facts, CLARIFY, OUT_OF_SCOPE, fallbacks)
    explainer.py      LLM explanations from given evidence only
    fake_handlers.py  default answers for the fake LLM (tests and offline demos)
    orchestrator.py   Agent.handle(request) -> AgentResponse
    factory.py        builds a ready-to-use Agent from settings

Principle: the LLM classifies intent and writes explanations. Routes, entities,
Engine facts, numbers and statuses are always decided by deterministic code.
"""
