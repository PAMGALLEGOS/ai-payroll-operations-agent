"""Agent -> Auditor, fallbacks and protection of Engine results."""

import json
import shutil

from app.agent.contracts import AgentRequest
from app.audit.checks import extract_numbers
from app.core.paths import KNOWLEDGE_DIR
from app.validation.tool import ValidationTool


def ask(agent, message, session="s"):
    return agent.handle(AgentRequest(session, message))


def _numbers(text):
    return {n for _, n in extract_numbers(text)}


# ------------------------------------------------------- Engine protection
def test_wrong_explanation_is_rewritten_once_then_allowed(make_agent, run_dir):
    agent, llm = make_agent()
    llm.script("tool_rag_explain",
               "EMP024 net_pay passed [RULE-003-C03].",                                   # wrong status
               "For EMP024, net_pay is FAIL with OUT_OF_TOLERANCE [RULE-003-C03].")       # corrected
    r = ask(agent, "Why did EMP024 fail?")
    assert r.audit == {**r.audit, "verdict": "ALLOW", "revised": True}
    assert len(llm.calls_for("tool_rag_explain")) == 2
    # The rewrite request carried the Auditor's feedback.
    assert "status_consistency" in json.loads(llm.calls_for("tool_rag_explain")[1]["user"])["previous_issues"][0]
    assert r.validation["results"] == ValidationTool(run_dir).query("2026-09", employee_id="EMP024").results


def test_explanation_failing_twice_is_blocked_and_facts_are_preserved(make_agent, run_dir):
    agent, llm = make_agent()
    llm.script("tool_rag_explain",
               "The difference was 305.00 SYN [RULE-003-C03].",
               "The difference was 300.00 SYN [RULE-003-C03].")
    r = ask(agent, "Why did EMP024 fail?")
    assert r.audit["verdict"] == "BLOCK" and r.audit["revised"] is True
    assert r.answer_mode == "safe_fallback"
    assert "305.00" not in r.answer and "300.00" not in r.answer
    assert "difference +350.00 SYN" in r.answer                          # facts still delivered
    assert r.validation["results"] == ValidationTool(run_dir).query("2026-09", employee_id="EMP024").results


def test_prohibited_decision_in_explanation_is_blocked_without_rewrite(make_agent):
    agent, llm = make_agent()
    llm.script("tool_rag_explain", "The difference is minor, you can approve the payroll [RULE-003-C03].")
    r = ask(agent, "Why did EMP024 fail?")
    assert r.audit["verdict"] == "BLOCK" and r.audit["revised"] is False
    assert len(llm.calls_for("tool_rag_explain")) == 1
    assert "approve the payroll" not in r.answer.lower()


def test_wrong_rag_answer_blocked_falls_back_to_cited_sources(make_agent):
    agent, llm = make_agent()
    llm.script("rag_answer", "The tolerance is 25.00 SYN [RULE-003-C03].", "It is 30.00 SYN [RULE-003-C03].")
    r = ask(agent, "What is the net pay tolerance?")
    assert r.audit["verdict"] == "BLOCK" and r.answer_mode == "safe_fallback"
    assert "25.00" not in r.answer and "[RULE-003-C03]" in r.answer


def test_every_number_in_answers_comes_from_engine_or_documents(make_agent, run_dir):
    agent, _ = make_agent()
    for message in ["Why did EMP024 fail?", "Did EMP026 pass?", "Why did EMP027 fail?",
                    "How many exceptions are there?", "Is payroll ready for approval?"]:
        r = ask(agent, message, session=message)
        allowed = set()
        for row in (r.validation or {}).get("results", []):
            for value in row.values():
                if isinstance(value, str):
                    allowed |= _numbers(value)
        for value in json.dumps((r.validation or {}).get("summary", {})).split():
            allowed |= _numbers(value)
        for e in r.evidence:
            allowed |= _numbers(e["content"])
        ungrounded = {n for raw, n in extract_numbers(r.answer) if "." in raw and n not in allowed}
        assert not ungrounded, (message, ungrounded)


# --------------------------------------------------------------- fallbacks
def test_intent_llm_failure_uses_keyword_fallback(make_agent):
    agent, llm = make_agent()
    llm.fail("intent")
    r = ask(agent, "Why did EMP024 fail?")
    assert r.route == "TOOL_RAG" and r.route_source == "fallback"


def test_explanation_llm_failure_returns_facts_and_sources(make_agent):
    agent, llm = make_agent()
    llm.fail("tool_rag_explain")
    r = ask(agent, "Why did EMP024 fail?")
    assert r.route == "TOOL_RAG" and r.answer_mode == "template"
    assert "difference +350.00 SYN" in r.answer and "Relevant documentation" in r.answer


def test_rag_llm_failure_returns_sources_only(make_agent):
    agent, llm = make_agent()
    llm.fail("rag_answer")
    r = ask(agent, "What is the net pay tolerance?")
    assert r.answer_mode == "safe_fallback" and "[RULE-003-C03]" in r.answer


def test_stale_index_blocks_rag(make_agent, tmp_path):
    knowledge = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_DIR, knowledge)
    doc = knowledge / "rules" / "net_pay_rule.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nChanged after indexing.\n", encoding="utf-8")
    agent, llm = make_agent(knowledge_dir=knowledge)
    r = ask(agent, "What is the net pay tolerance?")
    assert r.evidence_status == "blocked_stale_index" and r.evidence == []
    assert "out of date" in r.answer
    assert llm.calls_for("rag_answer") == []


def test_stale_index_in_tool_rag_keeps_engine_facts(make_agent, tmp_path):
    knowledge = tmp_path / "knowledge"
    shutil.copytree(KNOWLEDGE_DIR, knowledge)
    doc = knowledge / "rules" / "net_pay_rule.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")
    agent, llm = make_agent(knowledge_dir=knowledge)
    r = ask(agent, "Why did EMP024 fail?")
    assert r.route == "TOOL_RAG" and r.evidence_status == "blocked_stale_index"
    assert "difference +350.00 SYN" in r.answer                      # decision C3-07
    assert llm.calls_for("tool_rag_explain") == []


def test_missing_index_is_reported_not_guessed(make_agent, tmp_path):
    agent, llm = make_agent(index_dir=tmp_path / "no_index")
    r = ask(agent, "What is the net pay tolerance?")
    assert r.evidence_status == "unavailable" and llm.calls_for("rag_answer") == []


def test_no_validation_run(make_agent, tmp_path):
    agent, _ = make_agent(results_dir=tmp_path)
    r = ask(agent, "Did EMP024 pass in 2026-09?")
    assert r.route == "TOOL" and "no validation run" in r.answer.lower()


def test_tampered_run_is_not_shown(make_agent, run_dir, tmp_path):
    folder = tmp_path / "runs"
    shutil.copytree(run_dir, folder)
    pointer = json.loads((folder / "latest_2026-09.json").read_text())
    run_file = folder / pointer["run_file"]
    payload = json.loads(run_file.read_text())
    payload["results"][0]["actual_value"] = "1.00"
    run_file.write_text(json.dumps(payload))
    agent, _ = make_agent(results_dir=folder)
    r = ask(agent, "Did EMP001 pass?")
    assert "integrity check" in r.answer and r.validation is None
