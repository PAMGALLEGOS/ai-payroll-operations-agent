"""Canonical repository paths.

Every component resolves files through these constants instead of building
paths ad hoc, so moving a folder later is a one-line change.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIR = REPO_ROOT / "config"
VALIDATION_RULES_FILE = CONFIG_DIR / "validation_rules.yaml"

DATA_DIR = REPO_ROOT / "data"
SYNTHETIC_PAYROLL_DIR = DATA_DIR / "synthetic_payroll"
VALIDATION_RESULTS_DIR = DATA_DIR / "validation_results"


def payroll_inputs_file(period: str, base_dir: Path = SYNTHETIC_PAYROLL_DIR) -> Path:
    """Raw payroll inputs (what the Engine calculates FROM)."""
    return base_dir / f"payroll_inputs_{period}.csv"


def provider_results_file(period: str, base_dir: Path = SYNTHETIC_PAYROLL_DIR) -> Path:
    """Values reported by the (synthetic) payroll provider (what the Engine compares AGAINST)."""
    return base_dir / f"provider_results_{period}.csv"


def scenario_manifest_file(period: str, base_dir: Path = SYNTHETIC_PAYROLL_DIR) -> Path:
    """Designed scenario per employee — the independent test oracle."""
    return base_dir / f"scenario_manifest_{period}.csv"
