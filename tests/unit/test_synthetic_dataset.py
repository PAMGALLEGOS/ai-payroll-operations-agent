"""The committed synthetic dataset: shape, synthetic-only content, and scenarios.

The scenario manifest is written by the generator from the DESIGNED scenarios,
not from Engine output, so comparing them is an independent check of the Engine.
"""

import csv
import filecmp

import pytest

from app.core.paths import (
    SYNTHETIC_PAYROLL_DIR,
    payroll_inputs_file,
    provider_results_file,
    scenario_manifest_file,
)
from scripts.generate_synthetic_data import EMPLOYEE_COUNT, generate
from tests.helpers import PERIOD

REQUIRED_SCENARIOS = {
    "CLEAN_PASS",
    "INSIDE_TOLERANCE_POSITIVE",
    "INSIDE_TOLERANCE_NEGATIVE",
    "AT_TOLERANCE_GROSS",
    "AT_TOLERANCE_NET_NEGATIVE",
    "JUST_ABOVE_TOLERANCE_GROSS",
    "NET_OUT_OF_TOLERANCE",
    "DEDUCTIONS_UNDERSTATED",
    "GROSS_UNDERPAID",
    "MISSING_RAW_INPUT",
    "MISSING_PROVIDER_VALUE",
    "INVALID_RAW_INPUT",
    "NO_PROVIDER_RECORD",
}


def _rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def manifest():
    return {row["employee_id"]: row for row in _rows(scenario_manifest_file(PERIOD))}


def test_dataset_has_expected_size_and_single_period():
    rows = _rows(payroll_inputs_file(PERIOD))
    assert len(rows) == EMPLOYEE_COUNT == 30
    assert {r["period"] for r in rows} == {PERIOD}
    assert {r["country"] for r in rows} == {"SYNTHETIC"}
    assert {r["currency"] for r in rows} == {"SYN"}


def test_dataset_contains_no_personal_attributes():
    allowed = {
        "employee_id", "country", "currency", "period", "base_salary", "overtime_pay",
        "deduction_tax", "deduction_social_security", "deduction_benefits",
    }
    with payroll_inputs_file(PERIOD).open(encoding="utf-8") as handle:
        header = set(next(csv.reader(handle)))
    assert header == allowed


def test_all_required_scenarios_present(manifest):
    assert REQUIRED_SCENARIOS <= {row["scenario"] for row in manifest.values()}


def test_generator_is_deterministic(tmp_path):
    generate(PERIOD, tmp_path)
    for builder in (payroll_inputs_file, provider_results_file, scenario_manifest_file):
        assert filecmp.cmp(builder(PERIOD, tmp_path), builder(PERIOD, SYNTHETIC_PAYROLL_DIR), shallow=False)


def test_engine_outcomes_match_designed_scenarios(engine, context, rules, manifest):
    from app.validation.data_loader import load_payroll_inputs, load_provider_results

    records = load_payroll_inputs(payroll_inputs_file(PERIOD), PERIOD, rules.raw_input_fields)
    provider = load_provider_results(provider_results_file(PERIOD), PERIOD, rules.provider_fields)

    mismatches = []
    for result in engine.run(records, provider, context):
        designed = manifest[result.employee_id][f"expected_{result.validation_type}"]
        actual = "PASS" if result.status.value == "PASS" else f"FAIL:{result.reason_code.value}"
        if designed != actual:
            mismatches.append((result.employee_id, result.validation_type, designed, actual))
    assert mismatches == []
