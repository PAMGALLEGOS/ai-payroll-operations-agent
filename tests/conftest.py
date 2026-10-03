"""Shared fixtures.

CP1: tolerances are read from config/validation_rules.yaml instead of being
hard-coded, so changing a tolerance keeps the boundary tests meaningful.

CP3: Agent tests run against a validation run and a fake knowledge index built
in temporary folders, so they never depend on (or modify) local data files,
the network or credentials.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.contracts import RunContext
from app.core.paths import KNOWLEDGE_DIR
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


# ---------------------------------------------------------------- CP3 agent
@pytest.fixture(scope="session")
def run_dir(tmp_path_factory) -> Path:
    from app.validation.batch import run_batch

    folder = tmp_path_factory.mktemp("validation_results")
    run_batch("2026-09", output_dir=folder,
              clock=lambda: datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc))
    return folder


@pytest.fixture(scope="session")
def fake_index_dir(tmp_path_factory) -> Path:
    from app.rag.embeddings import FakeEmbeddingProvider
    from app.rag.ingest import ingest

    folder = tmp_path_factory.mktemp("vector_index")
    ingest(FakeEmbeddingProvider(), index_dir=folder)
    return folder


@pytest.fixture
def make_agent(run_dir, fake_index_dir):
    """Build an Agent with fake providers. Returns (agent, fake_llm)."""
    from app.agent.factory import build_agent
    from app.agent.fake_handlers import make_fake_llm
    from app.core.config import Settings

    def _make(knowledge_dir: Path = KNOWLEDGE_DIR, index_dir: Path | None = None,
              results_dir: Path | None = None, llm=None):
        llm = llm or make_fake_llm()
        agent = build_agent(
            Settings(_env_file=None), llm=llm, embeddings_provider="fake",
            results_dir=results_dir or run_dir, index_dir=index_dir or fake_index_dir,
            knowledge_dir=knowledge_dir,
        )
        return agent, llm

    return _make
