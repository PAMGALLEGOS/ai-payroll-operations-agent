"""Shared fixtures for CP1 unit tests.

Tests read tolerances from config/validation_rules.yaml instead of hard-coding
them, so changing a tolerance keeps the boundary tests meaningful.
"""

from __future__ import annotations

import pytest

from app.core.contracts import RunContext
from app.validation.engine import ValidationEngine
from app.validation.rules_loader import ValidationRules, load_rules


@pytest.fixture(scope="session")
def rules() -> ValidationRules:
    return load_rules()


@pytest.fixture
def engine(rules: ValidationRules) -> ValidationEngine:
    return ValidationEngine(rules)


@pytest.fixture
def context() -> RunContext:
    return RunContext(run_id="RUN-TEST-0001", run_timestamp="2026-10-03T00:00:00Z")
