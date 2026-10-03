"""Load and validate config/validation_rules.yaml.

The loader is strict on purpose: a malformed rules file must stop the batch
run with a clear error, never produce results with a silently wrong rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from app.core.paths import VALIDATION_RULES_FILE

SUPPORTED_CALCULATIONS = {"sum", "subtract"}

# The only tolerance semantics the Engine implements (decision D5).
SUPPORTED_TOLERANCE_RULE = {
    "type": "absolute",
    "difference": "actual_minus_expected",
    "pass_condition": "abs_difference_lte_tolerance",
}


class RulesConfigError(ValueError):
    """The rules file is missing, malformed or declares something unsupported."""


@dataclass(frozen=True)
class ValidationRule:
    validation_type: str
    description: str
    formula: str
    calculation: str
    inputs: tuple[str, ...]
    provider_field: str
    tolerance: Decimal


@dataclass(frozen=True)
class ValidationRules:
    rules_version: str
    country: str
    currency: str
    period_format: str
    decimal_places: int
    allow_negative_inputs: bool
    validations: tuple[ValidationRule, ...]

    def get(self, validation_type: str) -> ValidationRule:
        for rule in self.validations:
            if rule.validation_type == validation_type:
                return rule
        raise KeyError(validation_type)

    @property
    def validation_types(self) -> tuple[str, ...]:
        return tuple(r.validation_type for r in self.validations)

    @property
    def raw_input_fields(self) -> tuple[str, ...]:
        """Input columns read from the payroll inputs file (excludes derived values)."""
        derived = set(self.validation_types)
        fields: list[str] = []
        for rule in self.validations:
            for name in rule.inputs:
                if name not in derived and name not in fields:
                    fields.append(name)
        return tuple(fields)

    @property
    def provider_fields(self) -> tuple[str, ...]:
        return tuple(r.provider_field for r in self.validations)


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping or mapping[key] in (None, ""):
        raise RulesConfigError(f"Missing required key '{key}' in {where}")
    return mapping[key]


def _parse_tolerance(raw: Any, where: str) -> Decimal:
    # Tolerances must be quoted strings in YAML so they never pass through float.
    if not isinstance(raw, str):
        raise RulesConfigError(
            f"tolerance in {where} must be a quoted string (e.g. \"5.00\"), got {raw!r}"
        )
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise RulesConfigError(f"tolerance in {where} is not a number: {raw!r}") from None
    if not value.is_finite() or value < 0:
        raise RulesConfigError(f"tolerance in {where} must be a non-negative number: {raw!r}")
    return value


def parse_rules(data: Any) -> ValidationRules:
    """Validate an already-loaded YAML structure and return typed rules."""
    if not isinstance(data, dict):
        raise RulesConfigError("Rules file must contain a mapping at the top level")

    rules_version = str(_require(data, "rules_version", "rules file"))
    country = str(_require(data, "country", "rules file"))
    currency = str(_require(data, "currency", "rules file"))
    period_format = str(_require(data, "period_format", "rules file"))
    if period_format != "YYYY-MM":
        raise RulesConfigError(f"Unsupported period_format {period_format!r}; only 'YYYY-MM'")

    money = _require(data, "money", "rules file")
    decimal_places = money.get("decimal_places")
    if not isinstance(decimal_places, int) or decimal_places < 0:
        raise RulesConfigError("money.decimal_places must be a non-negative integer")
    allow_negative = money.get("allow_negative_inputs")
    if not isinstance(allow_negative, bool):
        raise RulesConfigError("money.allow_negative_inputs must be true or false")

    tolerance_rule = _require(data, "tolerance_rule", "rules file")
    if tolerance_rule != SUPPORTED_TOLERANCE_RULE:
        raise RulesConfigError(
            f"Unsupported tolerance_rule {tolerance_rule!r}; "
            f"the Engine implements only {SUPPORTED_TOLERANCE_RULE!r}"
        )

    raw_validations = _require(data, "validations", "rules file")
    if not isinstance(raw_validations, list):
        raise RulesConfigError("'validations' must be a list")

    validations: list[ValidationRule] = []
    seen_types: set[str] = set()
    for index, item in enumerate(raw_validations):
        where = f"validations[{index}]"
        if not isinstance(item, dict):
            raise RulesConfigError(f"{where} must be a mapping")
        vtype = str(_require(item, "validation_type", where))
        where = f"validation '{vtype}'"
        if vtype in seen_types:
            raise RulesConfigError(f"Duplicate validation_type '{vtype}'")

        calculation = str(_require(item, "calculation", where))
        if calculation not in SUPPORTED_CALCULATIONS:
            raise RulesConfigError(
                f"Unsupported calculation '{calculation}' in {where}; "
                f"supported: {sorted(SUPPORTED_CALCULATIONS)}"
            )

        inputs = _require(item, "inputs", where)
        if not isinstance(inputs, list) or not inputs:
            raise RulesConfigError(f"'inputs' in {where} must be a non-empty list")
        if calculation == "subtract" and len(inputs) != 2:
            raise RulesConfigError(f"'subtract' in {where} needs exactly 2 inputs")

        # A reference to another validation must point to one declared ABOVE,
        # so the Engine can always calculate in file order.
        all_types = {str(v.get("validation_type")) for v in raw_validations if isinstance(v, dict)}
        for name in inputs:
            if name in all_types and name not in seen_types:
                raise RulesConfigError(
                    f"{where} uses '{name}' before it is declared; reorder the validations"
                )

        validations.append(
            ValidationRule(
                validation_type=vtype,
                description=str(item.get("description", "")),
                formula=str(_require(item, "formula", where)),
                calculation=calculation,
                inputs=tuple(str(n) for n in inputs),
                provider_field=str(_require(item, "provider_field", where)),
                tolerance=_parse_tolerance(_require(item, "tolerance", where), where),
            )
        )
        seen_types.add(vtype)

    if not validations:
        raise RulesConfigError("At least one validation must be declared")

    return ValidationRules(
        rules_version=rules_version,
        country=country,
        currency=currency,
        period_format=period_format,
        decimal_places=decimal_places,
        allow_negative_inputs=allow_negative,
        validations=tuple(validations),
    )


def load_rules(path: Path = VALIDATION_RULES_FILE) -> ValidationRules:
    """Read the rules file from disk and validate it."""
    if not path.exists():
        raise RulesConfigError(f"Rules file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        try:
            data = yaml.safe_load(handle)
        except yaml.YAMLError as error:
            raise RulesConfigError(f"Rules file is not valid YAML: {error}") from None
    return parse_rules(data)
