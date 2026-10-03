"""Auditor: runs every check and returns ALLOW / REVISE / BLOCK (decision D9).

  ALLOW   every check passed
  REVISE  some check failed and the answer may be rewritten once
  BLOCK   a prohibited decision was found (never rewritten), or the answer is
          already a rewrite and still fails

The orchestrator owns the rewrite: it asks the explainer once more with the
failed checks as feedback, audits again, and on a second failure delivers a
deterministic safe answer.

Optional semantic check (decision C3-10): an LLM can judge whether the prose is
supported by the evidence. It is OFF by default and never overrides a
deterministic failure; it can only add one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from app.audit.checks import ALL_CHECKS, AuditContext, CheckResult
from app.llm.client import LLMClient, LLMError

Verdict = Literal["ALLOW", "REVISE", "BLOCK"]
BLOCK_IMMEDIATELY = {"prohibited_decision"}


class SemanticJudgement(BaseModel):
    supported: bool
    reason: str = ""


@dataclass
class AuditReport:
    verdict: Verdict
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    def feedback(self) -> list[str]:
        return [f"{c.name}: {c.details}" for c in self.failed]

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "checks": [c.to_dict() for c in self.checks]}


class Auditor:
    def __init__(self, semantic_llm: LLMClient | None = None):
        self.semantic_llm = semantic_llm   # None = semantic check OFF (default)

    def _semantic(self, text: str, ctx: AuditContext) -> CheckResult:
        payload = json.dumps({"answer": text, "facts": ctx.facts, "chunks": ctx.chunks}, ensure_ascii=False)
        try:
            judgement = self.semantic_llm.generate_json(  # type: ignore[union-attr]
                task="semantic_audit",
                system="Decide whether every claim in 'answer' is supported by 'facts' or 'chunks'. "
                       "Return JSON {\"supported\": bool, \"reason\": str}.",
                user=payload,
                schema=SemanticJudgement,
            )
            return CheckResult("semantic_grounding", judgement.supported, judgement.reason)
        except LLMError as error:
            # An unavailable judge must not silently pass: report it as not passed.
            return CheckResult("semantic_grounding", False, f"semantic check unavailable: {error}")

    def review(self, text: str, ctx: AuditContext, *, is_rewrite: bool = False) -> AuditReport:
        checks = [check(text, ctx) for check in ALL_CHECKS]
        if self.semantic_llm is not None and all(c.passed for c in checks):
            checks.append(self._semantic(text, ctx))

        failed = {c.name for c in checks if not c.passed}
        if not failed:
            verdict: Verdict = "ALLOW"
        elif failed & BLOCK_IMMEDIATELY or is_rewrite:
            verdict = "BLOCK"
        else:
            verdict = "REVISE"
        return AuditReport(verdict, checks)
