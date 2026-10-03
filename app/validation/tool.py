"""Validation Custom Tool — read-only access to persisted Engine results (C3-09).

The Agent asks this tool; the tool reads the latest persisted run file. It
never runs the Engine, never recalculates a value and never changes a result:

  * results are returned exactly as stored in the run file;
  * before returning anything, the tool recomputes the run's results
    fingerprint and refuses a file that was edited after the run;
  * counts for a filtered view are plain deterministic counting (D14), never
    left to the LLM.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.core.paths import VALIDATION_RESULTS_DIR
from app.validation.batch import fingerprint_result_dicts

RUN_HEADER_FIELDS = ("run_id", "run_timestamp", "period", "country", "currency",
                     "engine_version", "rules_version", "results_fingerprint")


class ToolError(RuntimeError):
    """The requested run is missing or cannot be trusted."""


@dataclass(frozen=True)
class ToolResult:
    found: bool
    period: str
    filters: dict[str, Any]
    run: dict[str, Any]
    results: list[dict[str, Any]]
    summary: dict[str, Any]
    employee_ids: list[str] = field(default_factory=list)   # all employees in the run

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "period": self.period,
            "filters": self.filters,
            "run": self.run,
            "results": self.results,
            "summary": self.summary,
        }


def count_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic counts over a list of persisted results."""
    by_type: dict[str, dict[str, int]] = {}
    for r in results:
        by_type.setdefault(r["validation_type"], {"PASS": 0, "FAIL": 0})[r["status"]] += 1
    return {
        "employees_validated": len({r["employee_id"] for r in results}),
        "total_validations": len(results),
        "pass_count": sum(r["status"] == "PASS" for r in results),
        "fail_count": sum(r["status"] == "FAIL" for r in results),
        "exception_count": sum(bool(r["exception"]) for r in results),
        "employees_with_exceptions": sorted({r["employee_id"] for r in results if r["exception"]}),
        "by_reason_code": dict(sorted(Counter(r["reason_code"] for r in results).items())),
        "by_validation_type": by_type,
    }


class ValidationTool:
    def __init__(self, results_dir: Path = VALIDATION_RESULTS_DIR):
        self.results_dir = results_dir

    def available_periods(self) -> list[str]:
        return sorted(p.stem.removeprefix("latest_") for p in self.results_dir.glob("latest_*.json"))

    def _load_run(self, period: str) -> dict[str, Any]:
        pointer = self.results_dir / f"latest_{period}.json"
        if not pointer.exists():
            raise ToolError(f"No validation run for period {period}")
        try:
            run_file = self.results_dir / json.loads(pointer.read_text(encoding="utf-8"))["run_file"]
            payload = json.loads(run_file.read_text(encoding="utf-8"))
            header, results = payload["run"], payload["results"]
        except (OSError, KeyError, json.JSONDecodeError) as error:
            raise ToolError(f"Validation run for {period} cannot be read: {error}") from None

        if fingerprint_result_dicts(results) != header.get("results_fingerprint"):
            raise ToolError(
                f"Validation run {header.get('run_id')} failed its integrity check: "
                "results were modified after the run"
            )
        return payload

    def query(
        self,
        period: str,
        employee_id: str | None = None,
        validation_type: str | None = None,
        status: Literal["PASS", "FAIL"] | None = None,
    ) -> ToolResult:
        payload = self._load_run(period)
        all_results: list[dict[str, Any]] = payload["results"]

        selected = [
            r for r in all_results
            if (employee_id is None or r["employee_id"] == employee_id)
            and (validation_type is None or r["validation_type"] == validation_type)
            and (status is None or r["status"] == status)
        ]
        filters = {"employee_id": employee_id, "validation_type": validation_type, "status": status}

        # Counts are always derived from the integrity-checked results, never
        # read from the file's summary block, which the fingerprint does not cover.
        summary = count_results(selected)
        if all(v is None for v in filters.values()):
            summary["provider_records_without_inputs"] = list(
                payload["summary"].get("provider_records_without_inputs", [])
            )

        return ToolResult(
            found=bool(selected),
            period=period,
            filters=filters,
            run={k: payload["run"].get(k) for k in RUN_HEADER_FIELDS},
            results=copy.deepcopy(selected),  # callers can never mutate the loaded run
            summary=summary,
            employee_ids=sorted({r["employee_id"] for r in all_results}),
        )
