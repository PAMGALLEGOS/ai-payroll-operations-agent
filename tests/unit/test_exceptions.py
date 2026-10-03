"""Data-quality exceptions and reason codes (decision D4)."""

from app.core.contracts import ReasonCode, ValidationStatus
from tests.helpers import EXPECTED, by_type, make_provider, make_record


def test_missing_raw_input_is_missing_input_exception(engine, context):
    results = by_type(engine.validate_employee(make_record(overtime_pay=""), make_provider(), context))
    gross = results["gross_pay"]
    assert gross.status is ValidationStatus.FAIL
    assert gross.exception is True
    assert gross.reason_code is ReasonCode.MISSING_INPUT
    assert gross.expected_value is None
    assert gross.difference is None
    assert "overtime_pay" in gross.detail


def test_missing_input_propagates_to_dependent_validation(engine, context):
    results = by_type(engine.validate_employee(make_record(overtime_pay=""), make_provider(), context))
    net = results["net_pay"]
    assert net.reason_code is ReasonCode.MISSING_INPUT
    assert "upstream gross_pay" in net.detail
    # An unrelated validation is still performed normally.
    assert results["total_deductions"].status is ValidationStatus.PASS


def test_invalid_raw_input_is_invalid_input_exception(engine, context):
    results = by_type(
        engine.validate_employee(make_record(deduction_benefits="-75.00"), make_provider(), context)
    )
    assert results["total_deductions"].reason_code is ReasonCode.INVALID_INPUT
    assert results["net_pay"].reason_code is ReasonCode.INVALID_INPUT
    assert results["gross_pay"].status is ValidationStatus.PASS


def test_non_numeric_input_is_invalid_input(engine, context):
    results = by_type(engine.validate_employee(make_record(base_salary="abc"), make_provider(), context))
    assert results["gross_pay"].reason_code is ReasonCode.INVALID_INPUT


def test_invalid_wins_over_missing(engine, context):
    record = make_record(deduction_tax="", deduction_benefits="-1.00")
    deductions = by_type(engine.validate_employee(record, make_provider(), context))["total_deductions"]
    assert deductions.reason_code is ReasonCode.INVALID_INPUT
    assert "deduction_tax" in deductions.detail and "deduction_benefits" in deductions.detail


def test_missing_provider_value(engine, context):
    results = by_type(engine.validate_employee(make_record(), make_provider(provider_net_pay=""), context))
    net = results["net_pay"]
    assert net.reason_code is ReasonCode.MISSING_INPUT
    assert net.expected_value == EXPECTED["net_pay"]  # expected is still reported
    assert net.actual_value is None
    assert net.difference is None


def test_no_provider_record_fails_every_validation(engine, context):
    results = engine.validate_employee(make_record(), None, context)
    assert len(results) == 3
    for result in results:
        assert result.status is ValidationStatus.FAIL
        assert result.reason_code is ReasonCode.MISSING_INPUT
        assert "no provider record" in result.detail


def test_exception_flag_matches_fail(engine, context):
    record = make_record(overtime_pay="")
    provider = make_provider(provider_total_deductions="1.00")
    for result in engine.validate_employee(record, provider, context):
        assert result.exception is (result.status is ValidationStatus.FAIL)


def test_pass_results_use_within_tolerance_reason(engine, context):
    for result in engine.validate_employee(make_record(), make_provider(), context):
        assert result.reason_code is ReasonCode.WITHIN_TOLERANCE
