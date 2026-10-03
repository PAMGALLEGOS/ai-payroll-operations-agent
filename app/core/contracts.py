"""Structured contracts produced by the Validation Engine.

These are the shapes that every later component (Custom Tool, Agent, Auditor,
Dashboard, tests) will consume. They are plain frozen dataclasses on purpose:
the Engine stays independent of any web framework, and a frozen object cannot
be modified after the Engine produced it.

Serialization rule: monetary values are written as STRINGS ("5350.00"), never
as JSON floats, so the exact Decimal value survives persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class ReasonCode(str, Enum):
    # Normal outcomes
    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"   # PASS: abs(difference) <= tolerance
    OUT_OF_TOLERANCE = "OUT_OF_TOLERANCE"   # FAIL: abs(difference) > tolerance
    # Data-quality outcomes (validation could not be performed normally)
    MISSING_INPUT = "MISSING_INPUT"         # a required input or provider value is absent
    INVALID_INPUT = "INVALID_INPUT"         # a value is non-numeric, negative or has too many decimals


@dataclass(frozen=True)
class RunContext:
    """Identity of one batch execution. Injected so the Engine never reads the clock."""

    run_id: str
    run_timestamp: str  # ISO-8601 UTC, e.g. "2026-10-03T21:20:00Z"


@dataclass(frozen=True)
class ValidationResult:
    """One validation of one employee for one validation_type."""

    employee_id: str
    country: str
    currency: str
    period: str
    validation_type: str
    expected_value: Decimal | None   # None when inputs prevented the calculation
    actual_value: Decimal | None     # None when the provider value is missing/invalid
    difference: Decimal | None       # actual - expected (sign preserved); None if not computable
    tolerance: Decimal
    status: ValidationStatus
    exception: bool
    reason_code: ReasonCode
    detail: str                      # human-readable explanation of the reason_code
    engine_version: str
    rules_version: str
    run_id: str
    run_timestamp: str

    def to_dict(self) -> dict[str, Any]:
        def money(value: Decimal | None) -> str | None:
            return None if value is None else str(value)

        return {
            "employee_id": self.employee_id,
            "country": self.country,
            "currency": self.currency,
            "period": self.period,
            "validation_type": self.validation_type,
            "expected_value": money(self.expected_value),
            "actual_value": money(self.actual_value),
            "difference": money(self.difference),
            "tolerance": money(self.tolerance),
            "status": self.status.value,
            "exception": self.exception,
            "reason_code": self.reason_code.value,
            "detail": self.detail,
            "engine_version": self.engine_version,
            "rules_version": self.rules_version,
            "run_id": self.run_id,
            "run_timestamp": self.run_timestamp,
        }
