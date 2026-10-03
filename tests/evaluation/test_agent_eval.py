"""Agent evaluation against REAL Gemini (CP3 approved targets).

Not part of the normal run. Requires GEMINI_API_KEY, GEMINI_MODEL, a validation
run (scripts/run_validation.py) and the Gemini knowledge index
(scripts/ingest_knowledge.py --provider gemini):

    pytest -m eval -v
"""

import pytest

from app.agent.factory import build_agent
from app.core.config import get_settings
from scripts.evaluate_agent import evaluate

pytestmark = pytest.mark.eval


@pytest.fixture(scope="module")
def report():
    settings = get_settings()
    if not settings.gemini_api_key or not settings.gemini_model:
        pytest.skip("GEMINI_API_KEY and GEMINI_MODEL are required for the real Agent evaluation")
    agent = build_agent(settings, llm_provider="gemini", embeddings_provider="gemini")
    if agent.retriever is None:
        pytest.skip("Gemini knowledge index not found: run scripts/ingest_knowledge.py --provider gemini")
    if not agent.tool.available_periods():
        pytest.skip("No validation run: run scripts/run_validation.py")
    return evaluate(agent, agent.tool.results_dir)


@pytest.mark.parametrize("metric", ["routing_accuracy", "clarify_missing_employee", "out_of_scope",
                                    "agent_engine_consistency", "seeded_auditor_detection"])
def test_agent_target(report, metric):
    target = report["targets"][metric]
    assert target["met"], (metric, target, report["routing_failures"], report["consistency_failures"])


def test_reported_metrics_are_present(report):
    assert 0 <= report["allow_without_rewrite_rate"] <= 1
    assert report["latency_ms_by_route"]
