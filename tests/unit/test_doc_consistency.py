"""Documentation <-> config/validation_rules.yaml consistency (decision D16).

The first test is the governance control. The others prove it actually fails
when the Engine configuration and the documentation drift apart.
"""

import copy
from dataclasses import replace

import pytest
import yaml

from app.core.paths import VALIDATION_RULES_FILE
from app.rag.consistency import check_documentation_consistency
from app.rag.documents import load_documents
from app.validation.rules_loader import parse_rules


@pytest.fixture(scope="module")
def documents():
    return load_documents()


@pytest.fixture
def raw_rules():
    return yaml.safe_load(VALIDATION_RULES_FILE.read_text(encoding="utf-8"))


def _edit_body(documents, doc_id, old, new):
    edited = []
    for doc in documents:
        if doc.doc_id == doc_id:
            assert old in doc.body, f"test setup: '{old}' not in {doc_id}"
            doc = replace(doc, body=doc.body.replace(old, new))
        edited.append(doc)
    return edited


def test_documentation_is_consistent_with_engine_rules(rules, documents):
    assert check_documentation_consistency(rules, documents) == []


def test_tolerance_changed_in_yaml_only_is_detected(raw_rules, documents):
    raw_rules["validations"][2]["tolerance"] = "15.00"   # net_pay
    issues = check_documentation_consistency(parse_rules(raw_rules), documents)
    assert any("net_pay tolerance documented as 10.00 SYN, rules say 15.00" in i for i in issues)
    # Detected in the rule doc, the tolerances table and the blueprint table.
    assert len([i for i in issues if "net_pay tolerance" in i]) == 3


def test_formula_changed_in_yaml_only_is_detected(raw_rules, documents):
    raw_rules["validations"][0]["formula"] = "gross_pay = base_salary + overtime_pay + bonus"
    issues = check_documentation_consistency(parse_rules(raw_rules), documents)
    assert any("gross_pay_rule.md: formula" in i for i in issues)
    assert any("table formula for gross_pay" in i for i in issues)


def test_rules_version_bump_without_documentation_is_detected(raw_rules, documents):
    raw_rules["rules_version"] = "1.1.0"
    issues = check_documentation_consistency(parse_rules(raw_rules), documents)
    assert len([i for i in issues if "rules_version 1.0.0 != 1.1.0" in i]) == 6   # 5 rules + blueprint


def test_documentation_changed_without_yaml_is_detected(rules, documents):
    edited = _edit_body(documents, "RULE-001", "**Tolerance:** 5.00 SYN", "**Tolerance:** 7.50 SYN")
    issues = check_documentation_consistency(rules, edited)
    assert any("gross_pay_rule.md: gross_pay tolerance documented as 7.50" in i for i in issues)


def test_strict_pass_boundary_in_documentation_is_detected(rules, documents):
    edited = _edit_body(
        documents, "RULE-004",
        "A validation is **PASS** when `abs(difference) <= tolerance`.",
        "A validation is **PASS** when `abs(difference) < tolerance`.",
    )
    issues = check_documentation_consistency(rules, edited)
    assert any("strict '<' PASS boundary" in i for i in issues)


def test_missing_boundary_statement_is_detected(rules, documents):
    edited = _edit_body(documents, "BP-001", "PASS when `abs(difference) <= tolerance`", "PASS when the difference is small")
    issues = check_documentation_consistency(rules, edited)
    assert any("validation_blueprint.md: does not state the PASS boundary" in i for i in issues)


def test_undocumented_reason_code_is_detected(rules, documents):
    edited = _edit_body(documents, "BP-001", "| INVALID_INPUT | FAIL |", "| BAD_DATA | FAIL |")
    issues = check_documentation_consistency(rules, edited)
    assert any("reason codes not documented: ['INVALID_INPUT']" in i for i in issues)


def test_validation_without_rule_document_is_detected(raw_rules, documents):
    new_rule = copy.deepcopy(raw_rules["validations"][0])
    new_rule.update(validation_type="bonus_pay", formula="bonus_pay = base_salary", provider_field="provider_bonus")
    raw_rules["validations"].append(new_rule)
    issues = check_documentation_consistency(parse_rules(raw_rules), documents)
    assert "No rule document for validation_type 'bonus_pay'" in issues
    assert any("Rules Reference table is missing ['bonus_pay']" in i for i in issues)
