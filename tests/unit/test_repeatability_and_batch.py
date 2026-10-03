"""Deterministic repeatability and persisted, versioned batch runs (decision D7)."""

import json
from datetime import datetime, timezone

import pytest

from app.core.contracts import RunContext
from app.validation import ENGINE_VERSION
from app.validation.batch import load_latest_run, results_fingerprint, run_batch
from app.validation.data_loader import load_payroll_inputs, load_provider_results
from app.core.paths import payroll_inputs_file, provider_results_file
from tests.helpers import PERIOD


def _clock(*stamps):
    values = iter(datetime(2026, 10, 3, 12, 0, s, tzinfo=timezone.utc) for s in stamps)
    return lambda: next(values)


@pytest.fixture
def dataset(rules):
    records = load_payroll_inputs(payroll_inputs_file(PERIOD), PERIOD, rules.raw_input_fields)
    provider = load_provider_results(provider_results_file(PERIOD), PERIOD, rules.provider_fields)
    return records, provider


def test_same_inputs_same_context_identical_results(engine, context, dataset):
    records, provider = dataset
    first = [r.to_dict() for r in engine.run(records, provider, context)]
    second = [r.to_dict() for r in engine.run(records, provider, context)]
    assert first == second


def test_fingerprint_ignores_run_identity_only(engine, dataset):
    records, provider = dataset
    a = engine.run(records, provider, RunContext("RUN-A", "2026-10-03T10:00:00Z"))
    b = engine.run(records, provider, RunContext("RUN-B", "2026-10-04T10:00:00Z"))
    assert results_fingerprint(a) == results_fingerprint(b)


def test_fingerprint_detects_a_changed_outcome(engine, dataset):
    records, provider = dataset
    baseline = engine.run(records, provider, RunContext("RUN-A", "t"))
    tampered = dict(provider)
    tampered["EMP001"] = {**provider["EMP001"], "provider_net_pay": "1.00"}
    changed = engine.run(records, tampered, RunContext("RUN-A", "t"))
    assert results_fingerprint(baseline) != results_fingerprint(changed)


def test_results_are_ordered_by_employee_then_rule(engine, context, dataset, rules):
    records, provider = dataset
    results = engine.run(list(reversed(records)), provider, context)
    keys = [(r.employee_id, rules.validation_types.index(r.validation_type)) for r in results]
    assert keys == sorted(keys)


def test_batch_persists_versioned_run_and_pointer(tmp_path):
    outcome = run_batch(PERIOD, output_dir=tmp_path, clock=_clock(0))
    data = json.loads(outcome.run_file.read_text(encoding="utf-8"))

    run = data["run"]
    assert run["engine_version"] == ENGINE_VERSION
    assert run["rules_version"]
    assert run["run_id"] == "RUN-2026-09-20261003T120000Z"
    assert run["run_timestamp"] == "2026-10-03T12:00:00Z"
    for key in ("rules_file_sha256", "payroll_inputs_sha256", "provider_results_sha256", "results_fingerprint"):
        assert len(run[key]) == 64

    assert all(r["run_id"] == run["run_id"] for r in data["results"])
    assert load_latest_run(PERIOD, tmp_path) == data


def test_two_batch_runs_are_separate_files_with_same_fingerprint(tmp_path):
    clock = _clock(0, 30)
    first = run_batch(PERIOD, output_dir=tmp_path, clock=clock)
    second = run_batch(PERIOD, output_dir=tmp_path, clock=clock)
    assert first.run_file != second.run_file
    assert first.run_file.exists() and second.run_file.exists()
    assert first.payload["run"]["results_fingerprint"] == second.payload["run"]["results_fingerprint"]
    # Pointer now names the latest run.
    assert load_latest_run(PERIOD, tmp_path)["run"]["run_id"] == second.payload["run"]["run_id"]


def test_run_files_are_never_overwritten(tmp_path):
    run_batch(PERIOD, output_dir=tmp_path, clock=_clock(0))
    with pytest.raises(FileExistsError):
        run_batch(PERIOD, output_dir=tmp_path, clock=_clock(0))


def test_summary_counts_are_consistent(tmp_path):
    payload = run_batch(PERIOD, output_dir=tmp_path, clock=_clock(0)).payload
    summary, results = payload["summary"], payload["results"]
    assert summary["total_validations"] == len(results)
    assert summary["pass_count"] + summary["fail_count"] == len(results)
    assert summary["exception_count"] == sum(r["exception"] for r in results)
    assert sum(summary["by_reason_code"].values()) == len(results)
