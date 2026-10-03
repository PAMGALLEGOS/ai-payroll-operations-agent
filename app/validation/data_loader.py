"""Read the synthetic payroll CSV files into plain records.

The loader only checks STRUCTURE (columns present, one row per employee, one
period). It does not judge values: deciding whether a value is missing or
invalid is a validation outcome, so it belongs to the Engine and must appear
in the results as an exception with a reason_code — not as a crash.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


class DataLoadError(ValueError):
    """A file is missing or structurally broken; the batch cannot run."""


@dataclass(frozen=True)
class EmployeeRecord:
    employee_id: str
    country: str
    currency: str
    period: str
    fields: dict[str, str]  # raw text values, exactly as read


def _read_csv(path: Path, required_columns: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.exists():
        raise DataLoadError(f"File not found: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = [c for c in required_columns if c not in columns]
        if missing:
            raise DataLoadError(f"{path.name} is missing columns: {missing}")
        return [dict(row) for row in reader]


def _index_by_employee(rows: list[dict[str, str]], path: Path) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        employee_id = (row.get("employee_id") or "").strip()
        if not employee_id:
            raise DataLoadError(f"{path.name} has a row without employee_id")
        if employee_id in indexed:
            raise DataLoadError(f"{path.name} has duplicate employee_id {employee_id}")
        indexed[employee_id] = row
    return indexed


def _check_single_period(rows: list[dict[str, str]], period: str, path: Path) -> None:
    periods = {(row.get("period") or "").strip() for row in rows}
    if periods != {period}:
        raise DataLoadError(f"{path.name} must contain only period {period}, found {sorted(periods)}")


def load_payroll_inputs(
    path: Path, period: str, raw_input_fields: tuple[str, ...]
) -> list[EmployeeRecord]:
    """Raw payroll inputs, one record per employee, in file order."""
    required = ("employee_id", "country", "currency", "period", *raw_input_fields)
    rows = _read_csv(path, required)
    _check_single_period(rows, period, path)
    _index_by_employee(rows, path)  # duplicate / blank id check
    return [
        EmployeeRecord(
            employee_id=row["employee_id"].strip(),
            country=row["country"].strip(),
            currency=row["currency"].strip(),
            period=row["period"].strip(),
            fields={name: row[name] for name in raw_input_fields},
        )
        for row in rows
    ]


def load_provider_results(
    path: Path, period: str, provider_fields: tuple[str, ...]
) -> dict[str, dict[str, str]]:
    """Provider-reported values keyed by employee_id."""
    required = ("employee_id", "period", *provider_fields)
    rows = _read_csv(path, required)
    if rows:
        _check_single_period(rows, period, path)
    indexed = _index_by_employee(rows, path)
    return {emp: {name: row[name] for name in provider_fields} for emp, row in indexed.items()}
