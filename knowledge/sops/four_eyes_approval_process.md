---
doc_id: SOP-003
title: Four-Eyes Payroll Approval Process
doc_type: sop
version: "1.0"
synthetic: true
---

# Four-Eyes Payroll Approval Process

> Synthetic procedure written for an academic proof of concept.

## Purpose

The Four-Eyes principle requires that payroll is prepared by one person and
approved by a different person. No single individual can both prepare and approve
the same payroll period. This control reduces the risk of errors and fraud.

## Segregation of Duties

- The **Preparer** (Payroll Analyst) runs the validation, investigates
  exceptions and submits the period for approval.
- The **Approver** (Payroll Lead) reviews the evidence and approves or rejects
  the period.
- The Preparer and the Approver must be different people. An approval recorded
  by the same person who prepared the period is invalid.

## Approval Prerequisites

The Approver may approve a payroll period only when all of the following are
true:

1. A validation run file exists for the period and it is the latest run.
2. Every exception has been resolved or has a documented acceptance.
3. The run summary has been reviewed: employees validated, PASS count, FAIL count
   and exception count.
4. The engine version and rules version in the run file are the approved
   versions.

## Approval Steps

1. The Preparer submits the period with the run identifier of the latest
   validation run.
2. The Approver reviews the run summary and the list of exceptions.
3. The Approver confirms that each exception has a resolution or an accepted
   justification.
4. The Approver records the decision: approved or rejected. A rejection returns
   the period to the Preparer with comments.

## Role of the AI Assistant

The AI assistant may summarize the validation status and list the open
exceptions to help the Approver prepare the review. The AI assistant never
approves payroll, never records an approval decision and never states that a
payroll period is approved. The final approval decision is always made by the
human Approver.
