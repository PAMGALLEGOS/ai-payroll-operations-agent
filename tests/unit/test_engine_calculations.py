"""Expected-value calculations and difference sign."""

from decimal import Decimal

from app.core.contracts import ReasonCode, ValidationStatus
from tests.helpers import EXPECTED, by_type, make_provider, make_record


def test_expected_gross_pay(engine, context):
    results = by_type(engine.validate_employee(make_record(), make_provider(), context))
    assert results["gross_pay"].expected_value == EXPECTED["gross_pay"]  # 5000.00 + 250.00


def test_expected_total_deductions(engine, context):
    results = by_type(engine.validate_employee(make_record(), make_provider(), context))
    assert results["total_deductions"].expected_value == EXPECTED["total_deductions"]


def test_expected_net_pay(engine, context):
    results = by_type(engine.validate_employee(make_record(), make_provider(), context))
    assert results["net_pay"].expected_value == EXPECTED["net_pay"]  # 5250.00 - 1162.50


def test_net_pay_uses_calculated_values_not_provider_values(engine, context):
    # Provider misreports gross; expected net must still come from RAW inputs.
    provider = make_provider(provider_gross_pay="9999.99")
    results = by_type(engine.validate_employee(make_record(), provider, context))
    assert results["net_pay"].expected_value == EXPECTED["net_pay"]


def test_difference_is_actual_minus_expected(engine, context):
    provider = make_provider(provider_net_pay=str(EXPECTED["net_pay"] + Decimal("350.00")))
    net = by_type(engine.validate_employee(make_record(), provider, context))["net_pay"]
    assert net.actual_value - net.expected_value == net.difference == Decimal("350.00")


def test_negative_difference_keeps_its_sign(engine, context):
    provider = make_provider(provider_gross_pay=str(EXPECTED["gross_pay"] - Decimal("250.00")))
    gross = by_type(engine.validate_employee(make_record(), provider, context))["gross_pay"]
    assert gross.difference == Decimal("-250.00")
    assert gross.status is ValidationStatus.FAIL
    assert gross.reason_code is ReasonCode.OUT_OF_TOLERANCE


def test_exact_match_is_pass_with_zero_difference(engine, context):
    for result in engine.validate_employee(make_record(), make_provider(), context):
        assert result.difference == Decimal("0.00")
        assert result.status is ValidationStatus.PASS
        assert result.exception is False


def test_result_contract_contains_required_fields(engine, context):
    required = {
        "employee_id", "country", "currency", "period", "validation_type",
        "expected_value", "actual_value", "difference", "tolerance", "status",
        "exception", "reason_code", "engine_version", "rules_version", "run_timestamp",
    }
    for result in engine.validate_employee(make_record(), make_provider(), context):
        data = result.to_dict()
        assert required <= data.keys()
        # Money serialised as exact strings, never floats.
        for key in ("expected_value", "actual_value", "difference", "tolerance"):
            assert isinstance(data[key], str)
