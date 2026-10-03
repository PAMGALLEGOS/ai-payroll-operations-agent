"""Generate the synthetic payroll dataset for one period.

Produces three files in data/synthetic_payroll/:

  payroll_inputs_<period>.csv     raw inputs the Engine calculates FROM
  provider_results_<period>.csv   values a (synthetic) provider reported
  scenario_manifest_<period>.csv  the designed outcome per employee — an
                                  independent oracle the tests check against

Design:
  * 30 fictional employees (EMP001..EMP030). No names or personal attributes:
    an ID is all the validation needs.
  * Amounts come from a seeded random generator -> rerunning the script
    always produces byte-identical files.
  * Most employees are "clean" (provider == expected). A defined set of
    employees carries deliberate deltas or data defects so every required
    scenario exists exactly where the manifest says.

Tolerances are NOT hard-coded: boundary scenarios ("exactly at tolerance",
"just above tolerance") are derived from config/validation_rules.yaml.

Usage:
    python scripts/generate_synthetic_data.py [--period 2026-09]
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import (  # noqa: E402
    SYNTHETIC_PAYROLL_DIR,
    payroll_inputs_file,
    provider_results_file,
    scenario_manifest_file,
)
from app.validation.rules_loader import ValidationRules, load_rules  # noqa: E402

SEED = 2026
EMPLOYEE_COUNT = 30
DEFAULT_PERIOD = "2026-09"
CENT = Decimal("0.01")

GROSS, DEDUCTIONS, NET = "gross_pay", "total_deductions", "net_pay"


@dataclass
class Scenario:
    """Deliberate deviation for one employee. Deltas are provider - expected."""

    name: str
    description: str
    deltas: dict[str, Decimal] = field(default_factory=dict)
    blank_inputs: tuple[str, ...] = ()            # raw input fields left empty
    blank_provider: tuple[str, ...] = ()          # provider fields left empty
    override_inputs: dict[str, str] = field(default_factory=dict)  # invalid raw values
    no_provider_record: bool = False
    expected: dict[str, str] = field(default_factory=dict)  # designed outcome per validation_type


def _cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def design_scenarios(rules: ValidationRules) -> dict[str, Scenario]:
    """Special-case employees. Everyone else is a clean PASS."""
    tol_gross = rules.get(GROSS).tolerance
    tol_ded = rules.get(DEDUCTIONS).tolerance
    tol_net = rules.get(NET).tolerance
    over = CENT  # smallest amount above a tolerance

    P, F_OOT = "PASS", "FAIL:OUT_OF_TOLERANCE"
    F_MISS, F_INV = "FAIL:MISSING_INPUT", "FAIL:INVALID_INPUT"

    def half(t: Decimal) -> Decimal:
        return _cents(t / 2)

    return {
        "EMP019": Scenario(
            "INSIDE_TOLERANCE_POSITIVE",
            "Provider gross (and net) slightly above expected, inside tolerance",
            deltas={GROSS: half(tol_gross), NET: half(tol_gross)},
            expected={GROSS: P, DEDUCTIONS: P, NET: P},
        ),
        "EMP020": Scenario(
            "INSIDE_TOLERANCE_NEGATIVE",
            "Provider deductions slightly below expected, inside tolerance",
            deltas={DEDUCTIONS: -(tol_ded - over), NET: tol_ded - over},
            expected={GROSS: P, DEDUCTIONS: P, NET: P},
        ),
        "EMP021": Scenario(
            "AT_TOLERANCE_GROSS",
            "Provider gross differs by exactly the gross tolerance (boundary = PASS)",
            deltas={GROSS: tol_gross, NET: tol_gross},
            expected={GROSS: P, DEDUCTIONS: P, NET: P},
        ),
        "EMP022": Scenario(
            "AT_TOLERANCE_NET_NEGATIVE",
            "Provider net differs by exactly minus the net tolerance (boundary = PASS)",
            deltas={NET: -tol_net},
            expected={GROSS: P, DEDUCTIONS: P, NET: P},
        ),
        "EMP023": Scenario(
            "JUST_ABOVE_TOLERANCE_GROSS",
            "Provider gross exceeds tolerance by one cent; net still inside its tolerance",
            deltas={GROSS: tol_gross + over, NET: tol_gross + over},
            expected={GROSS: F_OOT, DEDUCTIONS: P, NET: P},
        ),
        "EMP024": Scenario(
            "NET_OUT_OF_TOLERANCE",
            "Provider net pay 350.00 above expected (overpayment)",
            deltas={NET: Decimal("350.00")},
            expected={GROSS: P, DEDUCTIONS: P, NET: F_OOT},
        ),
        "EMP025": Scenario(
            "DEDUCTIONS_UNDERSTATED",
            "Provider deductions 120.00 below expected, so net is 120.00 above",
            deltas={DEDUCTIONS: Decimal("-120.00"), NET: Decimal("120.00")},
            expected={GROSS: P, DEDUCTIONS: F_OOT, NET: F_OOT},
        ),
        "EMP026": Scenario(
            "GROSS_UNDERPAID",
            "Provider gross 250.00 below expected (negative difference), net follows",
            deltas={GROSS: Decimal("-250.00"), NET: Decimal("-250.00")},
            expected={GROSS: F_OOT, DEDUCTIONS: P, NET: F_OOT},
        ),
        "EMP027": Scenario(
            "MISSING_RAW_INPUT",
            "overtime_pay is blank: gross cannot be calculated, net inherits the issue",
            blank_inputs=("overtime_pay",),
            expected={GROSS: F_MISS, DEDUCTIONS: P, NET: F_MISS},
        ),
        "EMP028": Scenario(
            "MISSING_PROVIDER_VALUE",
            "Provider did not report net pay",
            blank_provider=("provider_net_pay",),
            expected={GROSS: P, DEDUCTIONS: P, NET: F_MISS},
        ),
        "EMP029": Scenario(
            "INVALID_RAW_INPUT",
            "deduction_benefits is negative: deductions invalid, net inherits the issue",
            override_inputs={"deduction_benefits": "-75.00"},
            expected={GROSS: P, DEDUCTIONS: F_INV, NET: F_INV},
        ),
        "EMP030": Scenario(
            "NO_PROVIDER_RECORD",
            "Employee exists in inputs but the provider file has no record",
            no_provider_record=True,
            expected={GROSS: F_MISS, DEDUCTIONS: F_MISS, NET: F_MISS},
        ),
    }


def _random_amount(rng: random.Random, low_cents: int, high_cents: int) -> Decimal:
    return Decimal(rng.randint(low_cents, high_cents)) * CENT


def generate(period: str = DEFAULT_PERIOD, output_dir: Path = SYNTHETIC_PAYROLL_DIR) -> None:
    rules = load_rules()
    scenarios = design_scenarios(rules)
    rng = random.Random(SEED)

    inputs_rows, provider_rows, manifest_rows = [], [], []

    for n in range(1, EMPLOYEE_COUNT + 1):
        emp = f"EMP{n:03d}"

        base = _random_amount(rng, 300_000, 900_000)                       # 3,000.00 – 9,000.00
        overtime = _random_amount(rng, 0, 80_000) if rng.random() < 0.6 else Decimal("0.00")
        gross = base + overtime
        tax = _cents(gross * Decimal(rng.randint(10, 20)) / 100)            # 10–20 % (synthetic)
        social = _cents(gross * Decimal(rng.randint(4, 6)) / 100)           # 4–6 %  (synthetic)
        benefits = _random_amount(rng, 5_000, 20_000)                       # 50.00 – 200.00
        deductions = tax + social + benefits
        net = gross - deductions

        scenario = scenarios.get(emp) or Scenario(
            "CLEAN_PASS",
            "Provider values equal expected values",
            expected={GROSS: "PASS", DEDUCTIONS: "PASS", NET: "PASS"},
        )

        raw_inputs = {
            "base_salary": str(base),
            "overtime_pay": str(overtime),
            "deduction_tax": str(tax),
            "deduction_social_security": str(social),
            "deduction_benefits": str(benefits),
        }
        for name in scenario.blank_inputs:
            raw_inputs[name] = ""
        raw_inputs.update(scenario.override_inputs)

        inputs_rows.append(
            {"employee_id": emp, "country": rules.country, "currency": rules.currency, "period": period, **raw_inputs}
        )

        if not scenario.no_provider_record:
            reported = {
                "provider_gross_pay": gross + scenario.deltas.get(GROSS, Decimal("0")),
                "provider_total_deductions": deductions + scenario.deltas.get(DEDUCTIONS, Decimal("0")),
                "provider_net_pay": net + scenario.deltas.get(NET, Decimal("0")),
            }
            provider = {k: str(v) for k, v in reported.items()}
            for name in scenario.blank_provider:
                provider[name] = ""
            provider_rows.append({"employee_id": emp, "period": period, **provider})

        manifest_rows.append(
            {
                "employee_id": emp,
                "scenario": scenario.name,
                "description": scenario.description,
                "expected_gross_pay": scenario.expected[GROSS],
                "expected_total_deductions": scenario.expected[DEDUCTIONS],
                "expected_net_pay": scenario.expected[NET],
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    _write(payroll_inputs_file(period, output_dir), inputs_rows)
    _write(provider_results_file(period, output_dir), provider_rows)
    _write(scenario_manifest_file(period, output_dir), manifest_rows)


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--period", default=DEFAULT_PERIOD, help="Payroll period YYYY-MM")
    args = parser.parse_args()
    generate(args.period)
    print(f"Synthetic dataset for {args.period} written to {SYNTHETIC_PAYROLL_DIR}")


if __name__ == "__main__":
    main()
