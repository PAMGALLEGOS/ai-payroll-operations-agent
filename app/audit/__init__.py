"""Audit & Guardrails (CP3, Phase 8).

    checks.py   deterministic checks over a proposed answer
    auditor.py  ALLOW / REVISE / BLOCK verdict (decision D9)

Every critical control is deterministic (decision C3-10). An optional semantic
LLM check is available behind a flag and is OFF by default.
"""
