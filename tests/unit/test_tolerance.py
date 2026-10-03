"""Tolerance boundaries (decision D5): abs(difference) <= tolerance -> PASS.

Tolerances are read from the rules file, so these tests stay valid if a
tolerance changes.
"""

from decimal import Decimal

import pytest

from app.core.contracts import ReasonCode, ValidationStatus
from app.validation.engine import ValidationEngine
from tests.helpers import EXPECTED, by_type, make_provider, make_record

CENT = Decimal("0.01")
PROVIDER_FIELD = {
    "gross_pay": "provider_gross_pay",
    "total_deductions": "provider_total_deductions",
    "net_pay": "provider_net_pay",
}


def _validate(engine, context, vtype: str, delta: Decimal):
    provider = make_provider(**{PROVIDER_FIELD[vtype]: str(EXPECTED[vtype] + delta)})
    return by_type(engine.validate_employee(make_record(), provider, context))[vtype]


@pytest.mark.parametrize("vtype", list(PROVIDER_FIELD))
@pytest.mark.parametrize("sign", [1, -1])
def test_pass_below_tolerance(engine, context, rules, vtype, sign):
    delta = sign * (rules.get(vtype).tolerance - CENT)
    result = _validate(engine, context, vtype, delta)
    assert result.status is ValidationStatus.PASS
    assert result.reason_code is ReasonCode.WITHIN_TOLERANCE
    assert result.exception is False


@pytest.mark.parametrize("vtype", list(PROVIDER_FIELD))
@pytest.mark.parametrize("sign", [1, -1])
def test_pass_exactly_at_tolerance(engine, context, rules, vtype, sign):
    tolerance = rules.get(vtype).tolerance
    result = _validate(engine, context, vtype, sign * tolerance)
    assert abs(result.difference) == tolerance
    assert result.status is ValidationStatus.PASS


@pytest.mark.parametrize("vtype", list(PROVIDER_FIELD))
@pytest.mark.parametrize("sign", [1, -1])
def test_fail_above_tolerance(engine, context, rules, vtype, sign):
    delta = sign * (rules.get(vtype).tolerance + CENT)
    result = _validate(engine, context, vtype, delta)
    assert result.status is ValidationStatus.FAIL
    assert result.reason_code is ReasonCode.OUT_OF_TOLERANCE
    assert result.exception is True


def test_result_reports_the_rule_tolerance(engine, context, rules):
    for result in engine.validate_employee(make_record(), make_provider(), context):
        assert result.tolerance == rules.get(result.validation_type).tolerance


@pytest.mark.parametrize(
    "difference,tolerance,expected",
    [
        ("0.00", "5.00", ValidationStatus.PASS),
        ("4.99", "5.00", ValidationStatus.PASS),
        ("5.00", "5.00", ValidationStatus.PASS),
        ("-5.00", "5.00", ValidationStatus.PASS),
        ("5.01", "5.00", ValidationStatus.FAIL),
        ("-5.01", "5.00", ValidationStatus.FAIL),
        ("0.01", "0.00", ValidationStatus.FAIL),
    ],
)
def test_evaluate_tolerance_function(difference, tolerance, expected):
    status, _ = ValidationEngine.evaluate_tolerance(Decimal(difference), Decimal(tolerance))
    assert status is expected
