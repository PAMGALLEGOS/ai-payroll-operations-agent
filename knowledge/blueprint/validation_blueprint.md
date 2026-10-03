---
doc_id: BP-001
title: Payroll Validation Engine Blueprint
doc_type: blueprint
version: "1.0"
rules_version: "1.0.0"
synthetic: true
---

# Payroll Validation Engine Blueprint

> Synthetic blueprint for an academic proof of concept. It does not describe any
> real organization or system.

## Purpose

The Payroll Validation Engine validates payroll before approval by comparing the
values reported by the payroll provider with values calculated independently from
the raw payroll inputs. It is deterministic: the same inputs, the same rules
version and the same engine version always produce the same results.

## Deterministic Source of Truth

The Validation Engine is the authoritative source of truth for expected values,
differences, tolerances, PASS / FAIL results, exceptions and summary counts. The
documentation explains these results; it does not produce them. The AI assistant
explains results and procedures but never calculates authoritative values, never
overrides a validation result and never approves payroll.

## Validation Flow

1. Raw payroll inputs are read for every employee.
2. The Engine calculates the expected value for each validation type.
3. The provider value for the same validation type is read.
4. The difference is calculated as `difference = actual_value - expected_value`.
5. The tolerance is evaluated: PASS when `abs(difference) <= tolerance`, otherwise FAIL.
6. Data-quality problems produce a FAIL result with a data-quality reason code.
7. A structured validation result is produced and stored in the run file.

## Rules Reference

| validation_type | Formula | Tolerance |
|---|---|---|
| gross_pay | `gross_pay = base_salary + overtime_pay` | 5.00 SYN |
| total_deductions | `total_deductions = deduction_tax + deduction_social_security + deduction_benefits` | 5.00 SYN |
| net_pay | `net_pay = gross_pay - total_deductions` | 10.00 SYN |

Validations run in this order because net pay uses the expected gross pay and the
expected total deductions.

## Reason Codes

| Reason code | Status | Meaning |
|---|---|---|
| WITHIN_TOLERANCE | PASS | The absolute difference is less than or equal to the tolerance. |
| OUT_OF_TOLERANCE | FAIL | The absolute difference is greater than the tolerance. |
| MISSING_INPUT | FAIL | A required input or provider value is empty or absent. |
| INVALID_INPUT | FAIL | A value is non-numeric, negative or has more than two decimals. |

## Structured Validation Result

Each result contains: employee_id, country, currency, period, validation_type,
expected_value, actual_value, difference, tolerance, status, exception,
reason_code, detail, engine_version, rules_version, run_id and run_timestamp.

The exception flag is true for every FAIL result. The reason code tells whether
the exception comes from a difference outside tolerance or from a data-quality
problem. Monetary values are stored as exact decimal text with two decimals.

## Run Evidence

Each validation batch produces an immutable run file containing the run
identifier, the engine version, the rules version, SHA-256 fingerprints of the
rules and input files, a fingerprint of the results, summary counts and every
validation result. Run files are never overwritten; a correction produces a new
run.

## Versioning

Any change to a formula or a tolerance changes the rules version. The
documentation and the rules configuration are checked automatically for
consistency, so a rule cannot change without its documentation changing too.
