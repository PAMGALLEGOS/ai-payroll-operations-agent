---
doc_id: RULE-003
title: Net Pay Validation Rule
doc_type: rule
version: "1.0"
rules_version: "1.0.0"
validation_type: net_pay
synthetic: true
---

# Net Pay Validation Rule

> Synthetic rule for an academic proof of concept.

## Definition

Net pay is the amount the employee actually receives: gross pay minus total
deductions.

**Formula:** `net_pay = gross_pay - total_deductions`

## Inputs

Net pay does not read raw inputs directly. It uses the expected gross pay and the
expected total deductions calculated by the Validation Engine from the raw
inputs. It never uses the provider's gross pay or deductions to calculate the
expected net pay, so a provider error in gross pay cannot hide itself in net pay.

The provider value compared against the expected net pay is `provider_net_pay`.

## Tolerance

**Tolerance:** 10.00 SYN

The net pay tolerance is wider than the gross pay and deductions tolerances
because net pay accumulates the differences of both components. The net pay
validation passes when the absolute difference between the provider value and the
expected value is less than or equal to the tolerance.

## Interpreting a Net Pay Exception

- A positive difference means the provider would pay the employee more than
  expected (potential overpayment).
- A negative difference means the provider would pay the employee less than
  expected (potential underpayment).
- When gross pay or total deductions has a data-quality exception, net pay
  inherits it, and the detail message names the upstream validation.
