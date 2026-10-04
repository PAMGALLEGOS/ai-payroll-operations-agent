"""Observability (CP4, spec §15, decisions D11 / D4-08 / D4-09).

    context.py  the current trace_id, carried through a request with a context variable
    events.py   event catalogue and the observer interface the Agent calls
    logger.py   JSON-lines logging to stdout and a rotating file in logs/
    llm.py      LLM client wrapper that records every LLM call (task, duration, ok)

Privacy rule (D4-09): events carry metadata only. Never the user's message,
prompts, answers or credentials — for a message only its length, language and a
truncated SHA-256 hash are recorded.
"""
