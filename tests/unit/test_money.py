"""Decimal money parsing: exact values, no silent rounding, clear data issues."""

from decimal import Decimal

import pytest

from app.validation.money import InvalidValueError, MissingValueError, parse_money

KW = {"field": "base_salary", "decimal_places": 2, "allow_negative": False}


def test_parses_exact_decimal_from_text():
    assert parse_money("5350.00", **KW) == Decimal("5350.00")


def test_normalises_to_two_decimals_without_rounding():
    assert str(parse_money("100", **KW)) == "100.00"
    assert str(parse_money("100.5", **KW)) == "100.50"


def test_decimal_avoids_float_error():
    # With floats 0.1 + 0.2 != 0.3; the Engine must not suffer from this.
    a, b = parse_money("0.10", **KW), parse_money("0.20", **KW)
    assert a + b == Decimal("0.30")


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_blank_value_is_missing(raw):
    with pytest.raises(MissingValueError):
        parse_money(raw, **KW)


@pytest.mark.parametrize("raw", ["abc", "12,50", "NaN", "Infinity"])
def test_non_numeric_value_is_invalid(raw):
    with pytest.raises(InvalidValueError):
        parse_money(raw, **KW)


def test_negative_value_is_invalid_when_not_allowed():
    with pytest.raises(InvalidValueError):
        parse_money("-75.00", **KW)


def test_negative_value_accepted_when_allowed():
    assert parse_money("-75.00", field="x", decimal_places=2, allow_negative=True) == Decimal("-75.00")


def test_too_many_decimals_is_invalid_not_rounded():
    with pytest.raises(InvalidValueError):
        parse_money("10.005", **KW)
