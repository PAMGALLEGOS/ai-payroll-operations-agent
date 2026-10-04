"""F7d: the predefined stratified case set and the N10 check (evaluation harness only)."""

import pytest
import yaml

from scripts.evaluate_agent import (
    ESTIMATED_LLM_CALLS, EVAL_DIR, TARGETS, evaluate, is_english_rewrite, select_cases,
)

STRATIFIED_IDS = ["EN-R01", "EN-T01", "EN-X01", "EN-C01", "EN-C04", "EN-O01", "EN-O04",
                  "ES-R01", "ES-T01", "ES-X01", "ES-C01", "ES-C04", "ES-O01", "ES-O04"]


@pytest.fixture(scope="module")
def all_cases():
    return yaml.safe_load((EVAL_DIR / "routing_cases.yaml").read_text(encoding="utf-8"))["cases"]


def test_stratified_rule_selects_the_approved_14_cases(all_cases):
    chosen = select_cases(all_cases, "stratified")
    assert [c["id"] for c in chosen] == STRATIFIED_IDS
    # every route and both languages are covered
    assert {c["expected_route"] for c in chosen} == {"RAG", "TOOL", "TOOL_RAG", "CLARIFY", "OUT_OF_SCOPE"}
    assert {(c["category"], c["lang"]) for c in chosen} == {(c["category"], c["lang"]) for c in all_cases}
    # cases are the originals, not copies with edits
    assert all(c is next(o for o in all_cases if o["id"] == c["id"]) for c in chosen)


def test_full_case_set_is_unchanged(all_cases):
    assert select_cases(all_cases, "full") == all_cases
    with pytest.raises(ValueError):
        select_cases(all_cases, "random")


@pytest.mark.parametrize("case_set,cases", [("stratified", 14), ("full", 56)])
def test_estimated_gemini_requests_match_the_real_count(make_agent, run_dir, case_set, cases):
    agent, llm = make_agent()
    report = evaluate(agent, run_dir, case_set=case_set)
    assert report["cases_run"] == cases and report["case_set"] == case_set
    assert len(llm.calls) == ESTIMATED_LLM_CALLS[case_set]
    assert ESTIMATED_LLM_CALLS["stratified"] + 1 <= 20 - 3     # preflight + margin within the daily quota


def test_stratified_run_uses_the_same_targets(make_agent, run_dir):
    agent, _ = make_agent()
    report = evaluate(agent, run_dir, case_set="stratified")
    assert {k: v["target"] for k, v in report["targets"].items()} == TARGETS
    assert report["status"] == "PASS"


def test_n10_check_is_reported_and_detects_a_missing_rewrite(make_agent, run_dir):
    agent, llm = make_agent()
    # Gemini-like intent output with a real English rewrite for the Spanish RAG case
    llm.script("intent", '{"intent": "policy_question", "retrieval_query": "What is the net pay tolerance?", '
                         '"confidence": "high"}')
    report = evaluate(agent, run_dir, case_set="stratified")
    # the first scripted answer goes to EN-R01; ES-R01 then uses the fake handler, whose
    # pseudo-translation keeps Spanish words, so the check must flag it
    es = [c for c in report["n10_check"]["cases"] if c["id"] == "ES-R01"]
    assert es and es[0]["english_rewrite"] is False and report["n10_check"]["passed"] is False


@pytest.mark.parametrize("query,ok", [
    ("What is the net pay tolerance?", True),
    ("¿Cuál es la tolerancia del pago neto?", False),
    ("cual es la tolerancia del pago neto", False),
    ("cual es la tolerance del net pay", False),
])
def test_is_english_rewrite(query, ok):
    assert is_english_rewrite(query, "¿Cuál es la tolerancia del pago neto?") is ok
