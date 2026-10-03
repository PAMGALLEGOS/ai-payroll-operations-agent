---
doc_id: SOP-001
title: Payroll Validation Process
doc_type: sop
version: "1.0"
synthetic: true
---

# Payroll Validation Process

> Synthetic procedure written for an academic proof of concept. It does not
> describe the process of any real organization.

## Purpose

This procedure describes how a monthly payroll period is validated before it is
submitted for approval. Validation compares the payroll values reported by the
payroll provider against expected values calculated independently by the
Payroll Validation Engine. The goal is to detect overpayments, underpayments and
data-quality problems before any payment is released.

## Scope

The procedure applies to every employee included in the payroll period of the
fictional country SYNTHETIC, with amounts expressed in the fictional currency SYN.
Three validations are performed for each employee: gross pay, total deductions
and net pay.

## Roles

- **Payroll Analyst (Preparer):** loads the period inputs, runs the validation
  batch and reviews the exceptions.
- **Payroll Lead (Reviewer):** reviews the validation evidence and approves or
  rejects the payroll under the Four-Eyes Approval Process.
- **Payroll Validation Engine:** deterministic system that calculates expected
  values and determines PASS or FAIL. It is the authoritative source of truth for
  validation results.
- **AI assistant:** explains validation results and documented procedures. It
  never calculates authoritative values, never changes a validation result and
  never approves payroll.

## Procedure Steps

1. The Payroll Analyst confirms that the payroll inputs file and the provider
   results file for the period are complete and refer to the same period.
2. The Payroll Analyst runs the validation batch. The Engine produces a versioned
   run file that records the engine version, the rules version and a fingerprint
   of the results.
3. The Payroll Analyst reviews the run summary: number of employees validated,
   PASS count, FAIL count and exception count.
4. Every exception is handled through the Exception Review Process.
5. When all exceptions are resolved or formally accepted, the Payroll Analyst
   submits the period to the Payroll Lead under the Four-Eyes Approval Process.

## Evidence

The validation run file is the evidence of the validation. It must not be edited.
If inputs are corrected, the batch is run again and a new run file is produced.
The previous run file is kept, so the history of each correction stays traceable.

## Re-running a Validation

A validation is run again whenever an input file or a provider file is corrected.
Running the same inputs with the same rules and the same engine version produces
the same results fingerprint, which demonstrates that the validation is
repeatable.
