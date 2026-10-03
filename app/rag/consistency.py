"""Documentation <-> config/validation_rules.yaml consistency check (decision D16).

The YAML is the single source of truth for the Engine. The knowledge documents
explain the same rules in prose. This check makes sure they cannot drift apart:
changing a formula or a tolerance in the YAML without updating the documents
(or the reverse) produces a list of issues, and the test suite fails.

What is checked:
  1. rules_version   — every rule/blueprint document declares the YAML rules_version.
  2. Rule documents  — one per validation_type; its `**Formula:**` line and its
                       single `**Tolerance:**` line equal the YAML.
  3. Tables          — every `| validation_type | `formula` | X SYN |` row in any
                       document equals the YAML; the Blueprint lists every type.
  4. Boundary        — the Blueprint and the tolerances document state
                       `abs(difference) <= tolerance` and the difference
                       definition; no document states a strict `<` PASS boundary.
  5. Reason codes    — the Blueprint lists every reason code the Engine emits.

The documents are written with these canonical lines on purpose: a checkable
format is what makes the governance control automatic.
"""

from __future__ import annotations

import re

from app.core.contracts import ReasonCode
from app.rag.documents import KnowledgeDocument
from app.validation.rules_loader import ValidationRules

# The Blueprint and this rules document must state the PASS boundary explicitly.
TOLERANCES_DOC_ID = "RULE-004"
PASS_BOUNDARY = "abs(difference) <= tolerance"
DIFFERENCE_DEFINITION = "difference = actual_value - expected_value"
_STRICT_BOUNDARY = re.compile(r"abs\(difference\)\s*<\s*tolerance")  # "<" not followed by "="
_FORMULA_LINE = re.compile(r"\*\*Formula:\*\*\s*`([^`]+)`")
_TOLERANCE_LINE = re.compile(r"\*\*Tolerance:\*\*\s*([0-9.]+)\s+([A-Z]+)")
_TABLE_ROW = re.compile(r"^\|\s*([a-z_]+)\s*\|\s*`([^`]+)`\s*\|\s*([0-9.]+)\s+([A-Z]+)\s*\|\s*$", re.M)


def check_documentation_consistency(
    rules: ValidationRules, documents: list[KnowledgeDocument]
) -> list[str]:
    """Return a list of human-readable inconsistencies (empty list = consistent)."""
    issues: list[str] = []
    rule_types = set(rules.validation_types)

    def expect_tolerance(where: str, vtype: str, amount: str, currency: str) -> None:
        rule = rules.get(vtype)
        if amount != str(rule.tolerance) or currency != rules.currency:
            issues.append(
                f"{where}: {vtype} tolerance documented as {amount} {currency}, "
                f"rules say {rule.tolerance} {rules.currency}"
            )

    # 1. rules_version on every rule and blueprint document
    for doc in documents:
        if doc.doc_type in ("rule", "blueprint"):
            documented = str(doc.front_matter.get("rules_version", ""))
            if documented != rules.rules_version:
                issues.append(
                    f"{doc.source_document}: rules_version {documented or '(missing)'} "
                    f"!= {rules.rules_version}"
                )

    # 2. One rule document per validation_type, with matching formula and tolerance
    rule_docs = {
        str(doc.front_matter["validation_type"]): doc
        for doc in documents
        if doc.doc_type == "rule" and "validation_type" in doc.front_matter
    }
    for vtype in rule_docs.keys() - rule_types:
        issues.append(f"{rule_docs[vtype].source_document}: documents unknown validation_type '{vtype}'")
    for vtype in rules.validation_types:
        doc = rule_docs.get(vtype)
        if doc is None:
            issues.append(f"No rule document for validation_type '{vtype}'")
            continue
        formulas = _FORMULA_LINE.findall(doc.body)
        if formulas != [rules.get(vtype).formula]:
            issues.append(
                f"{doc.source_document}: formula documented as {formulas}, "
                f"rules say '{rules.get(vtype).formula}'"
            )
        tolerances = _TOLERANCE_LINE.findall(doc.body)
        if len(tolerances) != 1:
            issues.append(f"{doc.source_document}: expected exactly one **Tolerance:** line, found {len(tolerances)}")
        for amount, currency in tolerances:
            expect_tolerance(doc.source_document, vtype, amount, currency)

    # 3. Table rows anywhere; the Blueprint must list every validation type
    for doc in documents:
        listed: set[str] = set()
        for vtype, formula, amount, currency in _TABLE_ROW.findall(doc.body):
            if vtype not in rule_types:
                issues.append(f"{doc.source_document}: table lists unknown validation_type '{vtype}'")
                continue
            listed.add(vtype)
            if formula != rules.get(vtype).formula:
                issues.append(
                    f"{doc.source_document}: table formula for {vtype} is '{formula}', "
                    f"rules say '{rules.get(vtype).formula}'"
                )
            expect_tolerance(f"{doc.source_document} (table)", vtype, amount, currency)
        if doc.doc_type == "blueprint" and listed != rule_types:
            issues.append(
                f"{doc.source_document}: Rules Reference table is missing {sorted(rule_types - listed)}"
            )

    # 4. PASS / FAIL boundary and difference definition
    boundary_docs = [
        d for d in documents
        if d.doc_type == "blueprint" or d.doc_id == TOLERANCES_DOC_ID
    ]
    if not boundary_docs:
        issues.append("No blueprint or tolerances document found to state the PASS boundary")
    for doc in boundary_docs:
        if PASS_BOUNDARY not in doc.body:
            issues.append(f"{doc.source_document}: does not state the PASS boundary '{PASS_BOUNDARY}'")
        if DIFFERENCE_DEFINITION not in doc.body:
            issues.append(f"{doc.source_document}: does not state '{DIFFERENCE_DEFINITION}'")
    for doc in documents:
        if _STRICT_BOUNDARY.search(doc.body.replace("<=", "≤")):
            issues.append(f"{doc.source_document}: states a strict '<' PASS boundary; rules use '<='")

    # 5. Reason codes in the Blueprint
    for doc in documents:
        if doc.doc_type == "blueprint":
            missing = [code.value for code in ReasonCode if code.value not in doc.body]
            if missing:
                issues.append(f"{doc.source_document}: reason codes not documented: {missing}")

    return issues
