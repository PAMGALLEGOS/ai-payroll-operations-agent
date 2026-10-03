---
doc_id: SOP-002
title: Exception Review Process
doc_type: sop
version: "1.0"
synthetic: true
---

# Exception Review Process

> Synthetic procedure written for an academic proof of concept.

## Purpose

This procedure explains how validation exceptions are investigated and resolved
before a payroll period can be approved. An exception is any validation result
marked FAIL, either because a difference exceeds its tolerance or because a
data-quality problem prevented a normal validation.

## Identifying Exceptions

Exceptions are listed in the validation run file. Each exception shows the
employee, the validation type, the expected value, the provider value, the
difference, the tolerance, the reason code and a detail message. The reason code
tells the reviewer which type of investigation is required.

## Investigation by Reason Code

- **OUT_OF_TOLERANCE:** the provider value and the expected value differ by more
  than the tolerance. The analyst compares the raw inputs with the provider
  calculation to find which component explains the difference, for example a
  missing overtime entry or a deduction recorded twice.
- **MISSING_INPUT:** a required input or provider value is absent, so the
  expected value or the comparison could not be produced. The analyst requests
  the missing value from the data owner or from the provider.
- **INVALID_INPUT:** a value is not a valid amount, for example a negative
  deduction or a value with more than two decimals. The analyst requests a
  corrected value. Invalid values are never corrected silently.

## Resolution Options

1. **Correct and re-run:** the source data is corrected and the validation batch
   is run again. This is the preferred resolution.
2. **Provider correction:** the payroll provider corrects its calculation and
   sends an updated provider file, then the batch is run again.
3. **Documented acceptance:** in exceptional cases the Payroll Lead may accept a
   known difference with a written justification. Acceptance does not change the
   validation result; the result stays FAIL and the justification is recorded
   next to it.

## Escalation

An exception that cannot be resolved before the payroll deadline is escalated to
the Payroll Lead, who decides whether the affected employee is paid with a
documented acceptance, paid in a later correction cycle, or excluded from the
current payment run.

## Rules for the AI Assistant

The AI assistant can explain why an exception occurred by quoting the validation
result and this procedure. It cannot resolve, accept or close an exception.
Exception decisions always remain with a human reviewer.
