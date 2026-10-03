---
doc_id: RULE-001
title: Gross Pay Validation Rule
doc_type: rule
version: "1.0"
rules_version: "1.0.0"
validation_type: gross_pay
synthetic: true
---

# Gross Pay Validation Rule

> Synthetic rule for an academic proof of concept. It does not reflect the
> legislation of any real country.

## Definition

Gross pay is the total amount earned by the employee in the period before any
deduction. In this proof of concept gross pay has two components: the base
salary and the overtime pay.

**Formula:** `gross_pay = base_salary + overtime_pay`

## Inputs

- `base_salary`: fixed monthly salary in SYN.
- `overtime_pay`: overtime earned in the period, in SYN. It is 0.00 when the
  employee worked no overtime; an empty value is a missing input, not zero.

The provider value compared against the expected gross pay is
`provider_gross_pay`.

## Tolerance

**Tolerance:** 5.00 SYN

The gross pay validation passes when the absolute difference between the provider
value and the expected value is less than or equal to the tolerance.

## Typical Causes of a Gross Pay Exception

- Overtime recorded by the provider but missing from the inputs, or the reverse.
- A salary change applied by the provider but not reflected in the inputs.
- An empty `overtime_pay` value, which produces a MISSING_INPUT exception.

## Effect on Other Validations

Net pay depends on gross pay. When the expected gross pay cannot be calculated,
the net pay validation inherits the same data-quality exception.
