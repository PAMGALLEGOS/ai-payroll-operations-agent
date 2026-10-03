"""The evaluation harness itself, run offline with the fake providers.

This proves the script computes every approved metric. The fake LLM shares the
keyword rules with the fallback, so these numbers measure the deterministic
layer, not Gemini; the real measurement is `pytest -m eval`.
"""

from scripts.evaluate_agent import TARGETS, evaluate


def test_harness_reports_all_targets_with_fake_providers(make_agent, run_dir):
    agent, _ = make_agent()
    report = evaluate(agent, run_dir)

    assert report["cases"] == 56
    assert set(report["routing_accuracy_by_language"]) == {"en", "es"}
    assert set(report["targets"]) == set(TARGETS)
    assert all(t["met"] for t in report["targets"].values()), (report["routing_failures"], report["targets"])
    assert report["seeded_missed"] == [] and report["control_false_positives"] == []
    assert report["language_match"] == 1.0
    assert report["agent_engine_responses_checked"] > 0
    assert set(report["latency_ms_by_route"]) == {"RAG", "TOOL", "TOOL_RAG", "CLARIFY", "OUT_OF_SCOPE"}
