"""Validation Tool: read-only, identical to the persisted run, integrity-checked (C3-09)."""

import json
import shutil

import pytest

from app.validation.batch import load_latest_run
from app.validation.tool import ToolError, ValidationTool

PERIOD = "2026-09"


@pytest.fixture
def tool(run_dir):
    return ValidationTool(run_dir)


def test_available_periods(tool):
    assert tool.available_periods() == [PERIOD]


def test_results_identical_to_run_file(tool, run_dir):
    persisted = load_latest_run(PERIOD, run_dir)
    result = tool.query(PERIOD)
    assert result.results == persisted["results"]
    assert result.run["run_id"] == persisted["run"]["run_id"]


def test_summary_matches_engine_summary(tool, run_dir):
    persisted = load_latest_run(PERIOD, run_dir)["summary"]
    assert tool.query(PERIOD).summary == persisted


def test_employee_filter(tool):
    result = tool.query(PERIOD, employee_id="EMP024")
    assert result.found
    assert {r["employee_id"] for r in result.results} == {"EMP024"}
    assert len(result.results) == 3
    assert result.summary["fail_count"] == 1


def test_combined_filters(tool):
    result = tool.query(PERIOD, validation_type="net_pay", status="FAIL")
    assert result.summary["total_validations"] == 7
    assert all(r["validation_type"] == "net_pay" and r["status"] == "FAIL" for r in result.results)


def test_unknown_employee_is_not_found(tool):
    result = tool.query(PERIOD, employee_id="EMP999")
    assert not result.found and result.results == []
    assert "EMP999" not in result.employee_ids


def test_missing_period_raises(tool):
    with pytest.raises(ToolError, match="No validation run"):
        tool.query("2026-08")


def test_returned_results_cannot_modify_the_run(tool):
    first = tool.query(PERIOD, employee_id="EMP024")
    first.results[2]["status"] = "PASS"          # a caller tampering with what it received
    again = tool.query(PERIOD, employee_id="EMP024")
    assert [r["status"] for r in again.results] == ["PASS", "PASS", "FAIL"]


def test_tampered_run_file_is_refused(tmp_path, run_dir):
    shutil.copytree(run_dir, tmp_path / "runs")
    folder = tmp_path / "runs"
    pointer = json.loads((folder / f"latest_{PERIOD}.json").read_text())
    run_file = folder / pointer["run_file"]
    payload = json.loads(run_file.read_text())
    for row in payload["results"]:
        if row["employee_id"] == "EMP024" and row["validation_type"] == "net_pay":
            row["status"], row["exception"], row["reason_code"] = "PASS", False, "WITHIN_TOLERANCE"
    run_file.write_text(json.dumps(payload))
    with pytest.raises(ToolError, match="integrity check"):
        ValidationTool(folder).query(PERIOD)


def test_tool_never_runs_the_engine(tmp_path):
    # An empty results folder means "no run": the tool must not create one.
    tool = ValidationTool(tmp_path)
    with pytest.raises(ToolError):
        tool.query(PERIOD)
    assert list(tmp_path.iterdir()) == []
