"""Test helpers: a hand-checkable synthetic employee and builders."""

from __future__ import annotations

from decimal import Decimal

from app.validation.data_loader import EmployeeRecord

PERIOD = "2026-09"

# A small, hand-checkable employee:
#   gross      = 5000.00 + 250.00                  = 5250.00
#   deductions = 800.00 + 262.50 + 100.00          = 1162.50
#   net        = 5250.00 - 1162.50                 = 4087.50
CLEAN_INPUTS = {
    "base_salary": "5000.00",
    "overtime_pay": "250.00",
    "deduction_tax": "800.00",
    "deduction_social_security": "262.50",
    "deduction_benefits": "100.00",
}
EXPECTED = {
    "gross_pay": Decimal("5250.00"),
    "total_deductions": Decimal("1162.50"),
    "net_pay": Decimal("4087.50"),
}


def make_record(**overrides: str) -> EmployeeRecord:
    fields = {**CLEAN_INPUTS, **overrides}
    return EmployeeRecord(
        employee_id="EMP999", country="SYNTHETIC", currency="SYN", period=PERIOD, fields=fields
    )


def make_provider(**overrides: str) -> dict[str, str]:
    """Provider values equal to EXPECTED unless overridden."""
    values = {
        "provider_gross_pay": str(EXPECTED["gross_pay"]),
        "provider_total_deductions": str(EXPECTED["total_deductions"]),
        "provider_net_pay": str(EXPECTED["net_pay"]),
    }
    values.update(overrides)
    return values


def by_type(results):
    return {r.validation_type: r for r in results}


# ---------------------------------------------------------------- CP4 QA fixes
FAKE_KEY = "AIzaSyFAKE0000000000000000000000000000"   # synthetic, never a real key


def failing_llm(reason: str = "404 NOT_FOUND models/x is not found"):
    """An LLM whose every call fails like a provider error that echoes the key (F1–F3, F7a tests)."""
    from app.llm.client import LLMClient, LLMError

    class AlwaysFailingLLM(LLMClient):
        name, model = "failing", "failing-model"

        def _fail(self, task):
            raise LLMError(f"Gemini task '{task}' failed: {reason} "
                           f"(request https://example.invalid/v1?key={FAKE_KEY})")

        def generate_json(self, *, task, system, user, schema):
            self._fail(task)

        def generate_text(self, *, task, system, user):
            self._fail(task)

    return AlwaysFailingLLM()
