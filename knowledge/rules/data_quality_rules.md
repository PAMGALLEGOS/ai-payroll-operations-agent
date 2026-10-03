---
doc_id: RULE-005
title: Data-Quality Rules
doc_type: rule
version: "1.0"
rules_version: "1.0.0"
synthetic: true
---

# Data-Quality Rules

> Synthetic rule for an academic proof of concept.

## Purpose

A validation can only be trusted if its inputs are complete and valid. These
rules define when a value cannot be used and how the Validation Engine reports it.
Data-quality problems are reported as validation results with a reason code;
they never stop the whole validation run.

## Missing Values

A value is missing when it is empty in the inputs file or in the provider file,
or when the provider file has no record for the employee. A missing value produces
the reason code MISSING_INPUT. An empty value is never interpreted as zero.

## Invalid Values

A value is invalid when it is not a number, when it is negative, or when it has
more than two decimals. An invalid value produces the reason code INVALID_INPUT.
Invalid values are never rounded or corrected automatically, so every
authoritative number can be traced back to its source.

## Combined Problems

When a validation has both a missing value and an invalid value, the reason code
is INVALID_INPUT, because an invalid value is the more severe finding and must be
corrected first. The detail message lists every affected field.

## Propagation

Net pay is calculated from gross pay and total deductions. When either of them
cannot be calculated, net pay inherits the data-quality exception, and the detail
message names the upstream validation and its root cause. Validations that do not
depend on the affected value are still performed normally.

## Result of a Data-Quality Problem

A data-quality problem always produces a FAIL result with the exception flag set
to true. When the expected value or the provider value is not available, that
value and the difference are reported as empty (null) instead of being estimated.
