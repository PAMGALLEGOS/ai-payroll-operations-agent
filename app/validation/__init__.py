"""Payroll Validation Engine — the deterministic, authoritative source of truth.

Pipeline (decision 2.2 of the CP1 authorization):

    Raw Synthetic Payroll Inputs
    -> Deterministic Expected Calculation      (engine.calculate_expected)
    -> Synthetic Provider Result               (engine.read_provider_value)
    -> Comparison / Difference                 (engine.compare)
    -> Tolerance Evaluation -> PASS / FAIL     (engine.evaluate_tolerance)
    -> Exception / Reason Code
    -> Structured Validation Result            (app.core.contracts.ValidationResult)

No module in this package calls an LLM or reads the system clock.
"""

# Bump when Engine logic changes (independently of rules_version, which tracks
# config/validation_rules.yaml). Both are stamped on every result.
ENGINE_VERSION = "0.1.0"
