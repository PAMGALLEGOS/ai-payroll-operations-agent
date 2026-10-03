"""Deterministic entity extraction. The LLM never supplies entities.

  employee_id      "EMP024", "emp024", "EMP-024", "EMP 024"  -> "EMP024"
  period           "2026-09"
  validation_type  gross / bruto -> gross_pay; deduction(s) / deducciones -> total_deductions;
                   net / neto -> net_pay. More than one type mentioned -> None (all types).
  status_filter    failed / fallaron / exceptions -> FAIL; passed / pasaron -> PASS
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.agent.keywords import normalize

_EMPLOYEE = re.compile(r"\bEMP[\s\-_]?(\d{3})\b", re.IGNORECASE)
_PERIOD = re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])\b")

_TYPE_WORDS = {
    "gross_pay": (" gross ", " gross_pay ", " bruto ", " bruta "),
    "total_deductions": (" deduction ", " deductions ", " total_deductions ", " deduccion ", " deducciones "),
    "net_pay": (" net ", " net_pay ", " neto ", " neta "),
}
_FAIL_WORDS = (" failed ", " fail ", " failing ", " exception ", " exceptions ", " fallo ",
               " fallaron ", " fallidos ", " fallidas ", " excepcion ", " excepciones ")
_PASS_WORDS = (" passed ", " pasaron ", " paso ")


@dataclass(frozen=True)
class Entities:
    employee_ids: list[str] = field(default_factory=list)
    period: str | None = None
    validation_type: str | None = None
    status_filter: str | None = None

    @property
    def employee_id(self) -> str | None:
        return self.employee_ids[0] if len(self.employee_ids) == 1 else None


def extract_entities(message: str) -> Entities:
    employees: list[str] = []
    for match in _EMPLOYEE.finditer(message):
        emp = f"EMP{match.group(1)}"
        if emp not in employees:
            employees.append(emp)

    period_match = _PERIOD.search(message)
    text = normalize(message)

    types = [vtype for vtype, words in _TYPE_WORDS.items() if any(w in text for w in words)]
    status = None
    if any(w in text for w in _FAIL_WORDS):
        status = "FAIL"
    elif any(w in text for w in _PASS_WORDS):
        status = "PASS"

    return Entities(
        employee_ids=employees,
        period=period_match.group(0) if period_match else None,
        validation_type=types[0] if len(types) == 1 else None,
        status_filter=status,
    )


def remainder_without_entities(message: str) -> str:
    """Text left after removing employee ids and periods (used to detect bare answers like 'EMP024')."""
    text = _PERIOD.sub(" ", _EMPLOYEE.sub(" ", message))
    return " ".join(normalize(text).split())
