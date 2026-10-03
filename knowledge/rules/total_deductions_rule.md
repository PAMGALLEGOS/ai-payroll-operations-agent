---
doc_id: RULE-002
title: Total Deductions Validation Rule
doc_type: rule
version: "1.0"
rules_version: "1.0.0"
validation_type: total_deductions
synthetic: true
---

# Total Deductions Validation Rule

> Synthetic rule for an academic proof of concept. The deduction categories and
> percentages are fictional and do not represent any real tax or social security
> regime.

## Definition

Total deductions is the sum of all amounts withheld from the employee's gross pay
in the period.

**Formula:** `total_deductions = deduction_tax + deduction_social_security + deduction_benefits`

## Inputs

- `deduction_tax`: synthetic income tax withholding, in SYN.
- `deduction_social_security`: synthetic social security contribution, in SYN.
- `deduction_benefits`: synthetic benefits contribution, in SYN.

Every deduction must be a non-negative amount with at most two decimals. A
negative deduction is an INVALID_INPUT exception.

The provider value compared against the expected total deductions is
`provider_total_deductions`.

## Tolerance

**Tolerance:** 5.00 SYN

The total deductions validation passes when the absolute difference between the
provider value and the expected value is less than or equal to the tolerance.

## Typical Causes of a Deductions Exception

- A deduction omitted or duplicated by the provider.
- A deduction recorded with a negative sign in the inputs.
- A deduction value missing from the inputs file.

## Effect on Other Validations

Net pay depends on total deductions. When the expected total deductions cannot
be calculated, the net pay validation inherits the same data-quality exception.
