"""Rules configuration loading (config/validation_rules.yaml)."""

import copy
from decimal import Decimal

import pytest
import yaml

from app.core.paths import VALIDATION_RULES_FILE
from app.validation.rules_loader import RulesConfigError, load_rules, parse_rules


@pytest.fixture
def raw_rules() -> dict:
    return yaml.safe_load(VALIDATION_RULES_FILE.read_text(encoding="utf-8"))


def test_repository_rules_load(rules):
    assert rules.rules_version
    assert rules.country == "SYNTHETIC"
    assert rules.currency == "SYN"
    assert rules.validation_types == ("gross_pay", "total_deductions", "net_pay")


def test_tolerances_are_decimal_and_per_type(rules):
    for rule in rules.validations:
        assert isinstance(rule.tolerance, Decimal)
        assert rule.tolerance >= 0


def test_raw_inputs_exclude_derived_values(rules):
    assert rules.raw_input_fields == (
        "base_salary",
        "overtime_pay",
        "deduction_tax",
        "deduction_social_security",
        "deduction_benefits",
    )
    assert "gross_pay" not in rules.raw_input_fields


def test_missing_file_raises(tmp_path):
    with pytest.raises(RulesConfigError, match="not found"):
        load_rules(tmp_path / "nope.yaml")


def test_unquoted_tolerance_rejected(raw_rules):
    raw_rules["validations"][0]["tolerance"] = 5.0  # float would bypass Decimal
    with pytest.raises(RulesConfigError, match="quoted string"):
        parse_rules(raw_rules)


def test_negative_tolerance_rejected(raw_rules):
    raw_rules["validations"][0]["tolerance"] = "-1.00"
    with pytest.raises(RulesConfigError, match="non-negative"):
        parse_rules(raw_rules)


def test_unknown_calculation_rejected(raw_rules):
    raw_rules["validations"][0]["calculation"] = "multiply"
    with pytest.raises(RulesConfigError, match="Unsupported calculation"):
        parse_rules(raw_rules)


def test_unsupported_tolerance_rule_rejected(raw_rules):
    raw_rules["tolerance_rule"]["type"] = "percentage"
    with pytest.raises(RulesConfigError, match="Unsupported tolerance_rule"):
        parse_rules(raw_rules)


def test_reference_before_declaration_rejected(raw_rules):
    bad = copy.deepcopy(raw_rules)
    bad["validations"] = [bad["validations"][2], *bad["validations"][:2]]  # net_pay first
    with pytest.raises(RulesConfigError, match="before it is declared"):
        parse_rules(bad)


def test_duplicate_validation_type_rejected(raw_rules):
    raw_rules["validations"].append(copy.deepcopy(raw_rules["validations"][0]))
    with pytest.raises(RulesConfigError, match="Duplicate"):
        parse_rules(raw_rules)


def test_missing_required_key_rejected(raw_rules):
    del raw_rules["rules_version"]
    with pytest.raises(RulesConfigError, match="rules_version"):
        parse_rules(raw_rules)
