# AI Payroll Operations & Validation Agent — Academic PoC

> **Synthetic data only.** No real employees, payroll data, corporate documents,
> production systems or credentials are used anywhere in this repository.

**Current status: CP1 — deterministic validation core.** The RAG pipeline, Agent,
Auditor, API, web app and GCP deployment are added in later checkpoints, only
after each checkpoint is approved. The full README (architecture, deployment,
example questions) is written in Phase 14.

## Core principle

The **Payroll Validation Engine is the authoritative source of truth**. It
calculates expected values, differences, tolerances, PASS/FAIL, exceptions and
summary counts. The LLM (later checkpoints) only interprets and explains those
persisted results — it never recalculates or overrides them.

## What CP1 contains

| Component | Path | What it does |
|---|---|---|
| Validation rules | `config/validation_rules.yaml` | Single source of truth: formulas, field mappings, tolerances |
| Rules loader | `app/validation/rules_loader.py` | Reads and strictly validates the rules file |
| Money parsing | `app/validation/money.py` | Exact `Decimal` amounts; flags missing/invalid values |
| Data loader | `app/validation/data_loader.py` | Reads the synthetic CSVs (structure checks only) |
| Engine | `app/validation/engine.py` | Expected → provider value → difference → tolerance → PASS/FAIL → result |
| Batch run | `app/validation/batch.py` | Runs the Engine, adds summary counts, persists a versioned run file |
| Contracts | `app/core/contracts.py` | `ValidationResult`, status and reason codes |
| Dataset generator | `scripts/generate_synthetic_data.py` | Deterministic 30-employee synthetic dataset |
| Batch entry point | `scripts/run_validation.py` | Command to run a validation batch |
| Tests | `tests/unit/` | 86 deterministic unit tests |

## Run CP1 locally

Requires **Python 3.11**.

```bash
cd ai-payroll-agent

# 1. Create and activate the virtual environment
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install pinned dependencies
pip install -r requirements.txt

# 3. Run the unit tests
python -m pytest -v

# 4. Run a validation batch for the synthetic period
python scripts/run_validation.py --period 2026-09

# (Optional) Regenerate the synthetic dataset — produces byte-identical files
python scripts/generate_synthetic_data.py --period 2026-09
```

No API keys are needed for CP1. `.env.example` lists placeholders for later checkpoints.

## Outputs

`data/validation_results/validation_run_<period>-<timestamp>.json` — an immutable
run file with a header (run id, engine and rules versions, SHA-256 of the inputs,
results fingerprint), deterministic summary counts and one result per employee
and validation type. `latest_<period>.json` points to the most recent run.
Run files are generated locally and are not committed.
