"""Monetary parsing with Decimal.

Why Decimal: binary floats cannot represent most cents exactly. With floats,
a difference of exactly 5.00 can come out as 5.000000000000001 and FAIL a
tolerance of 5.00. Decimal built from the original STRING keeps the value exact.

Inputs are never silently rounded: a value with more decimals than the rules
allow is rejected as INVALID_INPUT, so every authoritative number is traceable
to its source.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


class InputIssue(Exception):
    """Base class for a data-quality problem in one field."""

    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


class MissingValueError(InputIssue):
    """The field is absent or blank."""


class InvalidValueError(InputIssue):
    """The field is present but not an acceptable monetary amount."""


def parse_money(
    raw: str | None,
    *,
    field: str,
    decimal_places: int,
    allow_negative: bool,
) -> Decimal:
    """Convert a raw text value into an exact Decimal, or raise an InputIssue."""
    if raw is None or str(raw).strip() == "":
        raise MissingValueError(field, "value is missing")

    text = str(raw).strip()
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise InvalidValueError(field, f"'{text}' is not a number") from None

    if not value.is_finite():
        raise InvalidValueError(field, f"'{text}' is not a finite number")

    if value < 0 and not allow_negative:
        raise InvalidValueError(field, f"negative value {text} is not allowed")

    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and -exponent > decimal_places:
        raise InvalidValueError(
            field, f"{text} has more than {decimal_places} decimal places"
        )

    # Normalise to exactly `decimal_places` decimals ("100" -> "100.00").
    # This only adds trailing zeros; the checks above guarantee no rounding happens.
    return value.quantize(Decimal(1).scaleb(-decimal_places))
