"""Run the Payroll Validation Engine in batch for one period and persist the results.

Usage:
    python scripts/run_validation.py [--period 2026-09]

Output:
    data/validation_results/validation_run_<period>-<timestamp>.json   immutable run file
    data/validation_results/latest_<period>.json                      pointer to the latest run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.validation.batch import run_batch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Payroll Validation Engine in batch.")
    parser.add_argument("--period", default="2026-09", help="Payroll period YYYY-MM")
    args = parser.parse_args()

    outcome = run_batch(args.period)
    run, summary = outcome.payload["run"], outcome.payload["summary"]

    print(f"Run ID            : {run['run_id']}")
    print(f"Engine / rules    : {run['engine_version']} / {run['rules_version']}")
    print(f"Employees         : {summary['employees_validated']}")
    print(f"Validations       : {summary['total_validations']}")
    print(f"PASS / FAIL       : {summary['pass_count']} / {summary['fail_count']}")
    print(f"Exceptions        : {summary['exception_count']}")
    print(f"By reason code    : {summary['by_reason_code']}")
    print(f"Fingerprint       : {run['results_fingerprint']}")
    print(f"Run file          : {outcome.run_file}")
    print(f"Latest pointer    : {outcome.pointer_file}")


if __name__ == "__main__":
    main()
