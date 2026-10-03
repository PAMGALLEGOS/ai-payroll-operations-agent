"""Deterministic checks over a proposed answer (bilingual EN / ES).

Each check receives the answer text and the AuditContext (Engine facts, the
retrieved chunks, the user's message) and returns a CheckResult. None of these
checks calls an LLM.

| check                | catches                                                            |
|----------------------|--------------------------------------------------------------------|
| numeric_grounding    | numbers not present in the Engine facts, the chunks or the question |
| status_consistency   | "net_pay passed" when the Engine says FAIL (and the reverse)       |
| employee_consistency | employees that were not part of the question or the facts          |
| prohibited_decision  | approving payroll, accepting / closing exceptions, overriding      |
| citation_validity    | citations of chunk ids that were not retrieved                     |
| citation_required    | a documentary answer with no citation at all                       |
| scope                | real countries, real laws and agencies                             |
| no_arithmetic        | the answer recalculating values ("4082.48 - 3732.48 = ...")        |

Known limitation (documented in the CP3 review): integers below 10 are not
checked by numeric_grounding, because they appear naturally in prose
("2 validations", "step 3"). All amounts with decimals and all integers >= 10
are checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from app.agent.keywords import normalize

# ------------------------------------------------------------------ context
@dataclass
class AuditContext:
    route: str
    language: str
    question: str
    facts: list[dict[str, Any]] = field(default_factory=list)       # Engine result rows
    summary: dict[str, Any] | None = None                           # Engine counts
    chunks: list[dict[str, Any]] = field(default_factory=list)      # {"chunk_id", "content"}
    allowed_employee_ids: set[str] = field(default_factory=set)
    requires_citation: bool = False


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "details": self.details}


# ------------------------------------------------------------------ numbers
_IDENTIFIERS = re.compile(
    r"\b(?:EMP[\s\-_]?\d{3}|[A-Z]{2,5}-\d{3}(?:-C\d{2})?|RUN-[\w\-]+|TRACE-[\w]+|"
    r"20\d{2}-(?:0[1-9]|1[0-2])(?:-\d{2})?|\d{8}T\d{6}Z|\d+\.\d+\.\d+|[0-9a-f]{12,})\b",
    re.IGNORECASE,
)
_THOUSANDS_EN = re.compile(r"\b(\d{1,3}(?:,\d{3})+)(\.\d+)?\b")
_THOUSANDS_ES = re.compile(r"\b(\d{1,3}(?:\.\d{3})+),(\d+)\b")
_DECIMAL_COMMA = re.compile(r"\b(\d+),(\d{1,2})\b")
_NUMBER = re.compile(r"(?<![\w.])[-+−]?\d+(?:\.\d+)?(?![\w])")


def extract_numbers(text: str) -> list[tuple[str, Decimal]]:
    """Return (raw, absolute Decimal) for every number in the text, identifiers excluded."""
    cleaned = _IDENTIFIERS.sub(" ", text)
    cleaned = _THOUSANDS_ES.sub(lambda m: m.group(1).replace(".", "") + "." + m.group(2), cleaned)
    cleaned = _THOUSANDS_EN.sub(lambda m: m.group(1).replace(",", "") + (m.group(2) or ""), cleaned)
    cleaned = _DECIMAL_COMMA.sub(r"\1.\2", cleaned)
    numbers: list[tuple[str, Decimal]] = []
    for raw in _NUMBER.findall(cleaned):
        try:
            numbers.append((raw, abs(Decimal(raw.replace("−", "-")))))
        except InvalidOperation:
            continue
    return numbers


def _values(obj: Any) -> Iterable[Any]:
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _values(value)
    elif isinstance(obj, (list, tuple, set)):
        for value in obj:
            yield from _values(value)
    else:
        yield obj


def allowed_numbers(ctx: AuditContext) -> set[Decimal]:
    allowed: set[Decimal] = set()
    for value in _values([ctx.facts, ctx.summary or {}]):
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            allowed.add(abs(Decimal(str(value))))
        elif isinstance(value, str):
            allowed.update(n for _, n in extract_numbers(value))
            try:
                allowed.add(abs(Decimal(value)))
            except InvalidOperation:
                pass
    for chunk in ctx.chunks:
        allowed.update(n for _, n in extract_numbers(chunk.get("content", "")))
    allowed.update(n for _, n in extract_numbers(ctx.question))
    return allowed


def check_numeric_grounding(text: str, ctx: AuditContext) -> CheckResult:
    allowed = allowed_numbers(ctx)
    ungrounded = []
    for raw, value in extract_numbers(text):
        is_amount = "." in raw
        if not is_amount and value < 10:
            continue  # small integers: see module docstring
        if value not in allowed:
            ungrounded.append(raw)
    return CheckResult("numeric_grounding", not ungrounded,
                       f"numbers not found in facts or evidence: {ungrounded}" if ungrounded else "")


# ------------------------------------------------------------------ statuses
_TYPE_ALIASES = {
    "gross_pay": (" gross_pay ", " gross pay ", " gross ", " bruto ", " pago bruto ", " salario bruto "),
    "total_deductions": (" total_deductions ", " total deductions ", " deductions ", " deducciones "),
    "net_pay": (" net_pay ", " net pay ", " neto ", " pago neto "),
}
_NEGATED_PASS = (" did not pass ", " didn t pass ", " does not pass ", " doesn t pass ", " not within ",
                 " no paso ", " no esta dentro ", " no quedo dentro ")
_NEGATED_FAIL = (" did not fail ", " didn t fail ", " does not fail ", " no fallo ")
_PASS_CLAIMS = (" pass ", " passed ", " passes ", " within tolerance ", " within the tolerance ",
                " paso ", " aprobo la validacion ", " dentro de la tolerancia ", " dentro de tolerancia ")
_FAIL_CLAIMS = (" fail ", " failed ", " fails ", " out of tolerance ", " outside the tolerance ",
                " outside tolerance ", " exceeds the tolerance ", " exceeded the tolerance ",
                " fallo ", " fuera de la tolerancia ", " fuera de tolerancia ", " excede ")
_SENTENCES = re.compile(r"(?<!\d)[.!?](?!\d)|\n|;")
# General rules are not claims about this employee: "a validation passes when the
# difference is within the tolerance", "pasa cuando...". Everything from a
# conditional word onwards is a condition, and the verb right before it is part
# of the rule, so both are ignored.
_CONDITION_START = re.compile(r" (?:only )?(?:when|if|unless|cuando|si|solo si|solo cuando) ")
_RULE_VERB = re.compile(r" (?:is )?(?:pass|passes|fail|fails|pasa|falla)\s*$")


def _drop_conditions(sentence: str) -> str:
    match = _CONDITION_START.search(sentence)
    if not match:
        return sentence
    return _RULE_VERB.sub(" ", sentence[:match.start()]) + " "


def check_status_consistency(text: str, ctx: AuditContext) -> CheckResult:
    status_by_type: dict[str, set[str]] = {}
    for row in ctx.facts:
        status_by_type.setdefault(row["validation_type"], set()).add(row["status"])

    problems = []
    for sentence in _SENTENCES.split(text):
        s = _drop_conditions(normalize(sentence))
        for phrase in _NEGATED_PASS:
            s = s.replace(phrase, " failed ")
        for phrase in _NEGATED_FAIL:
            s = s.replace(phrase, " passed ")
        claims_pass = any(c in s for c in _PASS_CLAIMS)
        claims_fail = any(c in s for c in _FAIL_CLAIMS)
        if claims_pass == claims_fail:
            continue  # no claim, or ambiguous sentence mentioning both
        for vtype, aliases in _TYPE_ALIASES.items():
            statuses = status_by_type.get(vtype)
            if not statuses or len(statuses) != 1 or not any(a in s for a in aliases):
                continue
            actual = next(iter(statuses))
            if (claims_pass and actual == "FAIL") or (claims_fail and actual == "PASS"):
                problems.append(f"{vtype} is {actual} but the answer says otherwise: '{sentence.strip()[:120]}'")
    return CheckResult("status_consistency", not problems, "; ".join(problems))


# ------------------------------------------------------------------ employees
_EMPLOYEE = re.compile(r"\bEMP[\s\-_]?(\d{3})\b", re.IGNORECASE)


def check_employee_consistency(text: str, ctx: AuditContext) -> CheckResult:
    mentioned = {f"EMP{m}" for m in _EMPLOYEE.findall(text)}
    unexpected = sorted(mentioned - ctx.allowed_employee_ids)
    return CheckResult("employee_consistency", not unexpected,
                       f"employees not in the question or facts: {unexpected}" if unexpected else "")


# ------------------------------------------------------------------ decisions
PROHIBITED_PHRASES = (
    # English
    "payroll is approved", "payroll has been approved", "i approved", "i have approved", "i approve",
    "approved the payroll", "is ready for approval", "is ready to be approved", "ready to approve",
    "you can approve", "you may approve", "you can now approve", "go ahead and approve",
    "safe to approve", "recommend approving", "recommend approval", "should be approved",
    "can be approved now", "exception is accepted", "exception has been accepted",
    "accept the exception", "accepted the exception", "exception is closed", "close the exception",
    "closed the exception", "exception is resolved", "exception has been resolved",
    "mark it as pass", "marked as pass", "mark as pass", "override the result", "overridden",
    "change the status to pass", "no action is needed", "can be ignored", "ignore the exception",
    # Spanish (accents removed by normalize)
    "nomina esta aprobada", "nomina fue aprobada", "nomina aprobada", "aprobe la nomina", "apruebo",
    "esta lista para aprobar", "esta lista para aprobarse", "esta lista para su aprobacion",
    "lista para aprobacion", "puedes aprobar", "puede aprobarse ya", "se puede aprobar",
    "recomiendo aprobar", "recomiendo la aprobacion", "deberia aprobarse", "acepta la excepcion",
    "excepcion aceptada", "excepcion fue aceptada", "cierra la excepcion", "excepcion cerrada",
    "excepcion resuelta", "marcala como pass", "marcar como pass", "anula el resultado",
    "se puede ignorar", "no requiere accion",
)


def check_prohibited_decision(text: str, ctx: AuditContext) -> CheckResult:
    normalized = normalize(text)
    found = [p for p in PROHIBITED_PHRASES if f" {p} " in normalized]
    return CheckResult("prohibited_decision", not found,
                       f"decision language not allowed: {found}" if found else "")


# ------------------------------------------------------------------ citations
_CITATION = re.compile(r"\[([A-Z]{2,5}-\d{3}-C\d{2})\]")
_CHUNK_ID = re.compile(r"\b([A-Z]{2,5}-\d{3}-C\d{2})\b")


def check_citation_validity(text: str, ctx: AuditContext) -> CheckResult:
    retrieved = {c["chunk_id"] for c in ctx.chunks}
    invalid = sorted({cid for cid in _CHUNK_ID.findall(text) if cid not in retrieved})
    return CheckResult("citation_validity", not invalid,
                       f"cited chunks that were not retrieved: {invalid}" if invalid else "")


def check_citation_required(text: str, ctx: AuditContext) -> CheckResult:
    if not ctx.requires_citation:
        return CheckResult("citation_required", True, "not required")
    cited = _CITATION.findall(text)
    return CheckResult("citation_required", bool(cited), "" if cited else "no [chunk_id] citation found")


# ------------------------------------------------------------------ scope
SCOPE_TERMS = (
    "mexico", "colombia", "chile", "peru", "argentina", "brazil", "brasil", "spain", "espana",
    "united states", "estados unidos", "isr", "imss", "infonavit", "sat", "dian", "sunat", "afp",
    "labor law", "labour law", "ley federal", "codigo sustantivo", "legislation", "legislacion",
)


def check_scope(text: str, ctx: AuditContext) -> CheckResult:
    normalized = normalize(text)
    found = [term for term in SCOPE_TERMS if f" {term} " in normalized]
    return CheckResult("scope", not found, f"real-world references not allowed: {found}" if found else "")


# ------------------------------------------------------------------ arithmetic
_ARITHMETIC = re.compile(r"\d[\d.,]*\s*[-+−×x*/]\s*\d[\d.,]*\s*=")


def check_no_arithmetic(text: str, ctx: AuditContext) -> CheckResult:
    cleaned = _IDENTIFIERS.sub(" ", text)
    found = _ARITHMETIC.findall(cleaned)
    return CheckResult("no_arithmetic", not found, f"recalculation found: {found}" if found else "")


ALL_CHECKS = (
    check_numeric_grounding,
    check_status_consistency,
    check_employee_consistency,
    check_prohibited_decision,
    check_citation_validity,
    check_citation_required,
    check_scope,
    check_no_arithmetic,
)
