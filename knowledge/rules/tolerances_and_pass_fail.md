---
doc_id: RULE-004
title: Tolerances and PASS / FAIL Criteria
doc_type: rule
version: "1.0"
rules_version: "1.0.0"
synthetic: true
---

# Tolerances and PASS / FAIL Criteria

> Synthetic rule for an academic proof of concept.

## Difference

For every validation the Engine calculates the difference as:

`difference = actual_value - expected_value`

The actual value is the value reported by the provider. The expected value is
the value calculated by the Validation Engine from the raw inputs. The sign is
preserved: a positive difference means the provider value is higher than
expected, and a negative difference means it is lower.

## Tolerance Type

Tolerances are absolute amounts in SYN, defined separately for each validation
type. Percentage tolerances are not used.

| validation_type | Formula | Tolerance |
|---|---|---|
| gross_pay | `gross_pay = base_salary + overtime_pay` | 5.00 SYN |
| total_deductions | `total_deductions = deduction_tax + deduction_social_security + deduction_benefits` | 5.00 SYN |
| net_pay | `net_pay = gross_pay - total_deductions` | 10.00 SYN |

## PASS / FAIL Criteria

A validation is **PASS** when `abs(difference) <= tolerance`.

A validation is **FAIL** when `abs(difference) > tolerance`.

The boundary is inclusive: a difference exactly equal to the tolerance, positive
or negative, is PASS. For example, with a tolerance of 5.00 SYN, a difference of
5.00 or -5.00 is PASS, and a difference of 5.01 is FAIL.

## Exceptions

Every FAIL result is an exception. A data-quality problem also produces a FAIL
result, because a validation that could not be performed cannot be considered
passed. The reason code distinguishes the type of exception.

## Monetary Precision

All amounts are handled as exact decimal numbers with two decimals. Amounts are
never converted to binary floating point, so a difference exactly at the
tolerance is always evaluated correctly.
