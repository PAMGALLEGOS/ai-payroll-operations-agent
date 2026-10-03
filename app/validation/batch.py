"""Batch execution and persistence of validation runs (decision D7).

A batch run:
  1. loads rules and synthetic files,
  2. runs the Engine,
  3. computes deterministic summary counts (decision D14),
  4. writes ONE immutable, versioned run file, and
  5. updates a small pointer file naming the latest run for the period.

Every later consumer (Custom Tool, Dashboard, Agent, Auditor) reads the run
file; none of them recalculates validation outcomes.

Audit fields in the run header:
  - SHA-256 of the rules file and both input files: proves which exact inputs
    produced the run.
  - results_fingerprint: SHA-256 of the results WITHOUT run_id/run_timestamp.
    Two runs over the same inputs, rules and engine version must have the same
    fingerprint — that is the repeatability evidence.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.core.contracts import RunContext, ValidationResult, ValidationStatus
from app.core.paths import (
    SYNTHETIC_PAYROLL_DIR,
    VALIDATION_RESULTS_DIR,
    VALIDATION_RULES_FILE,
    payroll_inputs_file,
    provider_results_file,
)
from app.validation import ENGINE_VERSION
from app.validation.data_loader import load_payroll_inputs, load_provider_results
from app.validation.engine import ValidationEngine
from app.validation.rules_loader import load_rules

RUN_METADATA_FIELDS = ("run_id", "run_timestamp")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_run_context(period: str, now: datetime) -> RunContext:
    stamp = now.astimezone(timezone.utc).replace(microsecond=0)
    return RunContext(
        run_id=f"RUN-{period}-{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        run_timestamp=stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint_result_dicts(results: list[dict[str, Any]]) -> str:
    """Hash of serialized results' business content, excluding run identity fields.

    Works on the persisted dictionaries, so a reader (the Validation Tool) can
    recompute it from a run file and detect any edit made after the run.
    """
    content = [{k: v for k, v in r.items() if k not in RUN_METADATA_FIELDS} for r in results]
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def results_fingerprint(results: list[ValidationResult]) -> str:
    """Hash of the results' business content, excluding run identity fields."""
    return fingerprint_result_dicts([r.to_dict() for r in results])


def summarize(
    results: list[ValidationResult], orphan_provider_records: list[str]
) -> dict[str, Any]:
    """Deterministic counts. The LLM will read these, never compute them (D14)."""
    by_type: dict[str, dict[str, int]] = {}
    for r in results:
        bucket = by_type.setdefault(r.validation_type, {"PASS": 0, "FAIL": 0})
        bucket[r.status.value] += 1

    employees = sorted({r.employee_id for r in results})
    with_exceptions = sorted({r.employee_id for r in results if r.exception})
    reasons = Counter(r.reason_code.value for r in results)

    return {
        "employees_validated": len(employees),
        "total_validations": len(results),
        "pass_count": sum(1 for r in results if r.status is ValidationStatus.PASS),
        "fail_count": sum(1 for r in results if r.status is ValidationStatus.FAIL),
        "exception_count": sum(1 for r in results if r.exception),
        "employees_with_exceptions": with_exceptions,
        "by_reason_code": dict(sorted(reasons.items())),
        "by_validation_type": by_type,
        "provider_records_without_inputs": orphan_provider_records,
    }


@dataclass(frozen=True)
class BatchOutcome:
    run_file: Path
    pointer_file: Path
    payload: dict[str, Any]


def run_batch(
    period: str,
    *,
    rules_file: Path = VALIDATION_RULES_FILE,
    input_dir: Path = SYNTHETIC_PAYROLL_DIR,
    output_dir: Path = VALIDATION_RESULTS_DIR,
    clock: Callable[[], datetime] = utc_now,
) -> BatchOutcome:
    rules = load_rules(rules_file)
    inputs_path = payroll_inputs_file(period, input_dir)
    provider_path = provider_results_file(period, input_dir)

    records = load_payroll_inputs(inputs_path, period, rules.raw_input_fields)
    provider = load_provider_results(provider_path, period, rules.provider_fields)

    context = build_run_context(period, clock())
    results = ValidationEngine(rules).run(records, provider, context)

    input_ids = {r.employee_id for r in records}
    orphans = sorted(emp for emp in provider if emp not in input_ids)

    payload: dict[str, Any] = {
        "run": {
            "run_id": context.run_id,
            "run_timestamp": context.run_timestamp,
            "period": period,
            "country": rules.country,
            "currency": rules.currency,
            "engine_version": ENGINE_VERSION,
            "rules_version": rules.rules_version,
            "rules_file_sha256": sha256_file(rules_file),
            "payroll_inputs_file": inputs_path.name,
            "payroll_inputs_sha256": sha256_file(inputs_path),
            "provider_results_file": provider_path.name,
            "provider_results_sha256": sha256_file(provider_path),
            "results_fingerprint": results_fingerprint(results),
        },
        "summary": summarize(results, orphans),
        "results": [r.to_dict() for r in results],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    run_file = output_dir / f"validation_run_{context.run_id.removeprefix('RUN-')}.json"
    if run_file.exists():
        # Run files are immutable evidence; never overwrite one.
        raise FileExistsError(f"Run file already exists: {run_file}")
    run_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    pointer_file = output_dir / f"latest_{period}.json"
    pointer_file.write_text(
        json.dumps(
            {
                "period": period,
                "run_id": context.run_id,
                "run_file": run_file.name,
                "results_fingerprint": payload["run"]["results_fingerprint"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return BatchOutcome(run_file=run_file, pointer_file=pointer_file, payload=payload)


def load_latest_run(period: str, output_dir: Path = VALIDATION_RESULTS_DIR) -> dict[str, Any]:
    """Read the latest persisted run for a period (the shared source for later CPs)."""
    pointer = json.loads((output_dir / f"latest_{period}.json").read_text(encoding="utf-8"))
    return json.loads((output_dir / pointer["run_file"]).read_text(encoding="utf-8"))
