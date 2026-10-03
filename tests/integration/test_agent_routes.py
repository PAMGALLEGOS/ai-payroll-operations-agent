"""Agent -> Tool -> Engine and Agent -> RAG, one test per route, English and Spanish (fake providers)."""

import pytest

from app.agent.contracts import AgentRequest
from app.validation.tool import ValidationTool


def ask(agent, message, session="s"):
    return agent.handle(AgentRequest(session, message))


# ------------------------------------------------------------------- RAG
@pytest.mark.parametrize("message,lang,doc", [
    ("What is the net pay tolerance?", "en", "RULE-003"),
    ("¿Cuál es la tolerancia del pago neto?", "es", "RULE-003"),
    ("Is a difference exactly equal to the tolerance a PASS?", "en", "RULE-004"),
])
def test_rag_route_answers_from_cited_documents(make_agent, message, lang, doc):
    agent, llm = make_agent()
    r = ask(agent, message)
    assert (r.route, r.language, r.evidence_status, r.answer_mode) == ("RAG", lang, "sufficient", "llm")
    assert r.validation is None
    assert any(e["chunk_id"].startswith(doc) for e in r.evidence)
    assert any(f"[{e['chunk_id']}]" in r.answer for e in r.evidence)
    assert r.audit["verdict"] == "ALLOW"
    assert llm.calls_for("tool_rag_explain") == []


def test_rag_without_documented_answer_uses_template_and_no_generation(make_agent):
    agent, llm = make_agent()
    r = ask(agent, "What is the vacation accrual policy for interns?")
    assert r.route == "RAG"
    assert r.evidence_status == "insufficient"
    assert r.answer_mode == "template"
    assert "no documented answer" in r.answer
    assert llm.calls_for("rag_answer") == []


# ------------------------------------------------------------------- TOOL
def test_tool_route_lookup_is_template_only(make_agent, run_dir):
    agent, llm = make_agent()
    r = ask(agent, "Did EMP024 pass validation?")
    assert (r.route, r.answer_mode, r.evidence_status) == ("TOOL", "template", "not_used")
    assert r.validation["results"] == ValidationTool(run_dir).query("2026-09", employee_id="EMP024").results
    assert "difference +350.00 SYN" in r.answer and "net_pay: FAIL" in r.answer
    assert llm.calls_for("rag_answer") == [] and llm.calls_for("tool_rag_explain") == []   # no generation
    assert r.human_in_the_loop
    assert r.audit["verdict"] == "ALLOW"


def test_tool_route_in_spanish_keeps_canonical_values(make_agent):
    agent, _ = make_agent()
    r = ask(agent, "¿EMP024 pasó la validación?")
    assert (r.route, r.language) == ("TOOL", "es")
    assert "net_pay: FAIL — esperado 3732.48 SYN, proveedor 4082.48 SYN, diferencia +350.00 SYN" in r.answer
    assert "OUT_OF_TOLERANCE" in r.answer


@pytest.mark.parametrize("message", ["How many exceptions are there?", "¿Cuántas excepciones hay?"])
def test_tool_route_aggregate_counts_come_from_engine(make_agent, run_dir, message):
    agent, _ = make_agent()
    r = ask(agent, message)
    summary = ValidationTool(run_dir).query("2026-09").summary
    assert r.route == "TOOL" and r.intent == "aggregate_lookup"
    assert r.validation["summary"] == summary
    assert str(summary["exception_count"]) in r.answer


def test_tool_route_unknown_employee(make_agent):
    agent, _ = make_agent()
    r = ask(agent, "Did EMP999 pass?")
    assert r.route == "TOOL" and r.validation["found"] is False
    assert "EMP999 is not in validation run" in r.answer


def test_tool_route_specific_validation_type(make_agent):
    agent, _ = make_agent()
    r = ask(agent, "Show me the net pay result for EMP025")
    assert r.route == "TOOL"
    assert "net_pay" in r.answer and "gross_pay" not in r.answer


# --------------------------------------------------------------- TOOL_RAG
@pytest.mark.parametrize("message,lang,employee,reason", [
    ("Why did EMP024 fail?", "en", "EMP024", "OUT_OF_TOLERANCE"),
    ("Why did EMP027 fail?", "en", "EMP027", "MISSING_INPUT"),
    ("¿Por qué falló EMP029?", "es", "EMP029", "INVALID_INPUT"),
])
def test_tool_rag_route_combines_facts_and_cited_explanation(make_agent, run_dir, message, lang, employee, reason):
    agent, _ = make_agent()
    r = ask(agent, message)
    assert (r.route, r.language, r.answer_mode, r.evidence_status) == ("TOOL_RAG", lang, "template+llm", "sufficient")
    assert r.validation["results"] == ValidationTool(run_dir).query("2026-09", employee_id=employee).results
    assert reason in r.answer
    assert ("Por qué:" if lang == "es" else "Why:") in r.answer
    assert r.audit["verdict"] == "ALLOW" and r.audit["revised"] is False
    assert r.human_in_the_loop


@pytest.mark.parametrize("message", ["Is payroll ready for approval?", "¿La nómina está lista para aprobarse?"])
def test_readiness_gives_facts_and_prerequisites_never_a_decision(make_agent, message):
    agent, _ = make_agent()
    r = ask(agent, message)
    assert r.route == "TOOL_RAG" and r.intent == "readiness_question"
    assert "14" in r.answer
    assert any(e["chunk_id"].startswith("SOP-003") for e in r.evidence)
    lowered = r.answer.lower()
    for forbidden in ("is ready for approval", "you can approve", "lista para aprobarse", "puedes aprobar"):
        assert forbidden not in lowered


# ---------------------------------------------------------------- CLARIFY
@pytest.mark.parametrize("message", [
    "Why did the employee fail?", "Did the employee pass?", "What was the difference?",
    "¿Por qué falló el empleado?", "¿El empleado pasó?", "¿Cuál fue la diferencia?",
])
def test_missing_employee_always_clarifies(make_agent, message):
    agent, _ = make_agent()
    r = ask(agent, message, session=f"fresh-{message}")
    assert r.route == "CLARIFY"
    assert r.clarification == {"reason": "missing_employee", "missing": "employee_id"}
    assert r.validation is None


def test_multiple_employees_clarifies(make_agent):
    agent, _ = make_agent()
    r = ask(agent, "Compare EMP023 and EMP024")
    assert r.route == "CLARIFY" and r.clarification["reason"] == "multiple_employees"
    assert "EMP023 or EMP024" in r.answer


@pytest.mark.parametrize("message", ["Hmm?", "¿Eh?", "   ", "???"])
def test_unclear_or_empty_message_clarifies(make_agent, message):
    agent, _ = make_agent()
    r = ask(agent, message)
    assert r.route == "CLARIFY"


def test_multiple_runs_require_period(make_agent, run_dir, tmp_path):
    import shutil
    folder = tmp_path / "runs"
    shutil.copytree(run_dir, folder)
    (folder / "latest_2026-10.json").write_text((folder / "latest_2026-09.json").read_text())
    agent, _ = make_agent(results_dir=folder)
    r = ask(agent, "Did EMP024 pass?")
    assert r.route == "CLARIFY" and r.clarification["reason"] == "missing_period"
    assert "2026-09, 2026-10" in r.answer


# ----------------------------------------------------------- OUT_OF_SCOPE
@pytest.mark.parametrize("message,reason", [
    ("Approve the payroll", "prohibited_action"),
    ("Please mark EMP024 as PASS", "prohibited_action"),
    ("Can you close the exception for EMP026?", "prohibited_action"),
    ("Aprueba la nómina", "prohibited_action"),
    ("¿Puedes cerrar la excepción de EMP026?", "prohibited_action"),
    ("What is the capital of France?", "off_topic"),
    ("Escribe un poema sobre el mar", "off_topic"),
    ("What is the income tax rate in Mexico?", "legal_advice"),
    ("¿Cuál es la tasa de ISR en México?", "legal_advice"),
])
def test_out_of_scope(make_agent, message, reason):
    agent, llm = make_agent()
    r = ask(agent, message)
    assert r.route == "OUT_OF_SCOPE" and r.out_of_scope == {"reason": reason}
    assert r.validation is None and r.answer_mode == "template"
    if reason == "prohibited_action":
        assert r.route_source == "rule"
        assert llm.calls_for("intent") == []     # decided before the LLM


def test_policy_question_about_approval_is_not_out_of_scope(make_agent):
    agent, _ = make_agent()
    r = ask(agent, "Can the AI assistant approve payroll?")
    assert r.route == "RAG"


# --------------------------------------------------------------- all routes
def test_every_response_has_trace_versions_and_allowed_audit(make_agent):
    agent, _ = make_agent()
    for message in ["What is the net pay tolerance?", "Did EMP024 pass?", "Why did EMP024 fail?",
                    "Why did the employee fail?", "Approve the payroll"]:
        r = ask(agent, message, session=message)
        assert r.trace_id.startswith("TRACE-")
        assert r.versions["llm"] == "fake/fake-llm-v1"
        assert r.audit["verdict"] == "ALLOW", (message, r.audit)
        assert r.latency_ms >= 0
