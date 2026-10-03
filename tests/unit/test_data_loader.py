"""Structural checks on input files. Value problems are NOT errors here — the Engine reports them."""

import pytest

from app.validation.data_loader import DataLoadError, load_payroll_inputs, load_provider_results
from tests.helpers import PERIOD

FIELDS = ("base_salary",)


def _write(tmp_path, text):
    path = tmp_path / "f.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file(tmp_path):
    with pytest.raises(DataLoadError, match="not found"):
        load_payroll_inputs(tmp_path / "x.csv", PERIOD, FIELDS)


def test_missing_column(tmp_path):
    path = _write(tmp_path, "employee_id,country,currency,period\nEMP001,SYNTHETIC,SYN,2026-09\n")
    with pytest.raises(DataLoadError, match="missing columns"):
        load_payroll_inputs(path, PERIOD, FIELDS)


def test_duplicate_employee(tmp_path):
    path = _write(
        tmp_path,
        "employee_id,country,currency,period,base_salary\n"
        "EMP001,SYNTHETIC,SYN,2026-09,1.00\nEMP001,SYNTHETIC,SYN,2026-09,2.00\n",
    )
    with pytest.raises(DataLoadError, match="duplicate"):
        load_payroll_inputs(path, PERIOD, FIELDS)


def test_mixed_periods_rejected(tmp_path):
    path = _write(
        tmp_path,
        "employee_id,country,currency,period,base_salary\n"
        "EMP001,SYNTHETIC,SYN,2026-09,1.00\nEMP002,SYNTHETIC,SYN,2026-08,2.00\n",
    )
    with pytest.raises(DataLoadError, match="only period"):
        load_payroll_inputs(path, PERIOD, FIELDS)


def test_blank_value_is_loaded_not_rejected(tmp_path):
    path = _write(tmp_path, "employee_id,country,currency,period,base_salary\nEMP001,SYNTHETIC,SYN,2026-09,\n")
    records = load_payroll_inputs(path, PERIOD, FIELDS)
    assert records[0].fields["base_salary"] == ""


def test_provider_indexed_by_employee(tmp_path):
    path = _write(tmp_path, "employee_id,period,provider_gross_pay\nEMP001,2026-09,10.00\n")
    assert load_provider_results(path, PERIOD, ("provider_gross_pay",)) == {
        "EMP001": {"provider_gross_pay": "10.00"}
    }
