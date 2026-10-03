"""Deterministic Payroll Validation Engine.

Each step of the approved validation pattern is its own small function so the
flow can be read top to bottom and unit-tested in isolation:

    calculate_expected  -> expected value from raw inputs (or a data issue)
    read_provider_value -> provider-reported value (or a data issue)
    compare             -> difference = actual - expected (sign preserved)
    evaluate_tolerance  -> PASS / FAIL and reason_code
    build_result        -> structured ValidationResult

Determinism: the Engine has no randomness, never reads the clock (run identity
is injected through RunContext) and processes employees and validations in a
fixed order. Same inputs + same rules + same context => identical results.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.contracts import ReasonCode, RunContext, ValidationResult, ValidationStatus
from app.validation import ENGINE_VERSION
from app.validation.data_loader import EmployeeRecord
from app.validation.money import InputIssue, InvalidValueError, parse_money
from app.validation.rules_loader import ValidationRule, ValidationRules


@dataclass(frozen=True)
class DataIssue:
    """Why a value could not be obtained. Carried instead of a number."""

    reason_code: ReasonCode   # MISSING_INPUT or INVALID_INPUT
    detail: str               # full explanation shown in the result
    cause: str = ""           # root cause only, reused when the issue propagates


# A step either produces an exact Decimal or a DataIssue explaining why not.
Outcome = Decimal | DataIssue


def _issue_from(issues: list[InputIssue | DataIssue], prefix: str) -> DataIssue:
    """Collapse several problems into one DataIssue.

    INVALID_INPUT wins over MISSING_INPUT: a wrong value is the more severe
    finding and the one a reviewer must correct first.
    """
    codes: list[ReasonCode] = []
    messages: list[str] = []
    for issue in issues:
        if isinstance(issue, DataIssue):
            codes.append(issue.reason_code)
            messages.append(issue.cause or issue.detail)
        else:
            codes.append(
                ReasonCode.INVALID_INPUT
                if isinstance(issue, InvalidValueError)
                else ReasonCode.MISSING_INPUT
            )
            messages.append(f"{issue.field} {issue.message}")
    code = ReasonCode.INVALID_INPUT if ReasonCode.INVALID_INPUT in codes else ReasonCode.MISSING_INPUT
    cause = "; ".join(messages)
    return DataIssue(code, f"{prefix}: {cause}", cause)


class ValidationEngine:
    def __init__(self, rules: ValidationRules):
        self.rules = rules

    # ------------------------------------------------------------------ parsing
    def _money(self, raw: str | None, field: str) -> Decimal:
        return parse_money(
            raw,
            field=field,
            decimal_places=self.rules.decimal_places,
            allow_negative=self.rules.allow_negative_inputs,
        )

    # ------------------------------------------------- step 1: expected value
    def calculate_expected(
        self,
        rule: ValidationRule,
        raw_fields: dict[str, str],
        derived: dict[str, Outcome],
    ) -> Outcome:
        """Calculate the expected value declared by `rule`.

        `derived` holds outcomes of validations already processed for the same
        employee (net_pay reads gross_pay and total_deductions from here).
        """
        values: list[Decimal] = []
        issues: list[InputIssue | DataIssue] = []

        for name in rule.inputs:
            if name in derived:
                upstream = derived[name]
                if isinstance(upstream, DataIssue):
                    reason = f"upstream {name} not calculable ({upstream.cause})"
                    issues.append(DataIssue(upstream.reason_code, reason, reason))
                else:
                    values.append(upstream)
                continue
            try:
                values.append(self._money(raw_fields.get(name), name))
            except InputIssue as issue:
                issues.append(issue)

        if issues:
            return _issue_from(issues, "Expected value not calculated")

        if rule.calculation == "sum":
            return sum(values, Decimal("0"))
        if rule.calculation == "subtract":
            return values[0] - values[1]
        raise AssertionError(f"Unsupported calculation {rule.calculation}")  # guarded by loader

    # ------------------------------------------------- step 2: provider value
    def read_provider_value(
        self, rule: ValidationRule, provider_fields: dict[str, str] | None
    ) -> Outcome:
        if provider_fields is None:
            cause = "no provider record for this employee"
            return DataIssue(ReasonCode.MISSING_INPUT, f"Provider value not available: {cause}", cause)
        try:
            return self._money(provider_fields.get(rule.provider_field), rule.provider_field)
        except InputIssue as issue:
            return _issue_from([issue], "Provider value not usable")

    # ------------------------------------------------- step 3: comparison
    @staticmethod
    def compare(expected: Decimal, actual: Decimal) -> Decimal:
        """difference = actual - expected. Positive: provider paid MORE than expected."""
        return actual - expected

    # ------------------------------------------------- step 4: tolerance
    @staticmethod
    def evaluate_tolerance(difference: Decimal, tolerance: Decimal) -> tuple[ValidationStatus, ReasonCode]:
        """abs(difference) <= tolerance -> PASS (the boundary itself is PASS)."""
        if abs(difference) <= tolerance:
            return ValidationStatus.PASS, ReasonCode.WITHIN_TOLERANCE
        return ValidationStatus.FAIL, ReasonCode.OUT_OF_TOLERANCE

    # ------------------------------------------------- step 5: result
    def validate_employee(
        self,
        record: EmployeeRecord,
        provider_fields: dict[str, str] | None,
        context: RunContext,
    ) -> list[ValidationResult]:
        derived: dict[str, Outcome] = {}
        results: list[ValidationResult] = []

        for rule in self.rules.validations:
            expected = self.calculate_expected(rule, record.fields, derived)
            derived[rule.validation_type] = expected
            actual = self.read_provider_value(rule, provider_fields)

            issues = [o for o in (expected, actual) if isinstance(o, DataIssue)]
            if issues:
                issue = _issue_from(issues, "Data-quality exception") if len(issues) > 1 else issues[0]
                difference = None
                status, reason, detail = ValidationStatus.FAIL, issue.reason_code, issue.detail
            else:
                difference = self.compare(expected, actual)
                status, reason = self.evaluate_tolerance(difference, rule.tolerance)
                detail = (
                    f"abs(difference) {abs(difference)} "
                    f"{'<=' if status is ValidationStatus.PASS else '>'} tolerance {rule.tolerance}"
                )

            results.append(
                ValidationResult(
                    employee_id=record.employee_id,
                    country=record.country,
                    currency=record.currency,
                    period=record.period,
                    validation_type=rule.validation_type,
                    expected_value=None if isinstance(expected, DataIssue) else expected,
                    actual_value=None if isinstance(actual, DataIssue) else actual,
                    difference=difference,
                    tolerance=rule.tolerance,
                    status=status,
                    # Decision D4: exception = FAIL or data-quality issue.
                    # Data issues always yield FAIL, so this equals status == FAIL.
                    exception=status is ValidationStatus.FAIL,
                    reason_code=reason,
                    detail=detail,
                    engine_version=ENGINE_VERSION,
                    rules_version=self.rules.rules_version,
                    run_id=context.run_id,
                    run_timestamp=context.run_timestamp,
                )
            )
        return results

    def run(
        self,
        records: list[EmployeeRecord],
        provider: dict[str, dict[str, str]],
        context: RunContext,
    ) -> list[ValidationResult]:
        """Validate every employee. Output order: employee_id, then rule order."""
        results: list[ValidationResult] = []
        for record in sorted(records, key=lambda r: r.employee_id):
            results.extend(self.validate_employee(record, provider.get(record.employee_id), context))
        return results
