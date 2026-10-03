"""Multi-turn session behaviour (spec §11) in English and Spanish."""

from app.agent.contracts import AgentRequest


def ask(agent, message, session="s"):
    return agent.handle(AgentRequest(session, message))


def test_four_turn_conversation_english(make_agent):
    agent, _ = make_agent()
    first = ask(agent, "Why did EMP024 fail?")
    assert first.route == "TOOL_RAG" and first.entities["employee_id"] == "EMP024"

    second = ask(agent, "What was the difference?")
    assert second.route == "TOOL"
    assert second.entities["employee_id"] == "EMP024"
    assert second.entities_source["employee_id"] == "session"
    assert second.entities["validation_types"] == ["net_pay"]          # focus on what failed
    assert "difference +350.00 SYN" in second.answer and "gross_pay" not in second.answer

    third = ask(agent, "And EMP026?")
    assert third.entities["employee_id"] == "EMP026"
    assert third.route == "TOOL"            # keeps the kind of the previous question (a lookup)

    fourth = ask(agent, "How many exceptions in total?")
    assert fourth.route == "TOOL" and fourth.validation["summary"]["exception_count"] == 14


def test_four_turn_conversation_spanish(make_agent):
    agent, _ = make_agent()
    assert ask(agent, "¿Por qué falló EMP024?").route == "TOOL_RAG"
    second = ask(agent, "¿Cuál fue la diferencia?")
    assert (second.route, second.language, second.entities["employee_id"]) == ("TOOL", "es", "EMP024")
    assert "diferencia +350.00 SYN" in second.answer
    third = ask(agent, "¿Y EMP026?")
    assert third.entities["employee_id"] == "EMP026" and third.language == "es"
    assert ask(agent, "¿Cuántas excepciones hay en total?").validation["summary"]["exception_count"] == 14


def test_clarification_is_completed_by_the_next_message(make_agent):
    agent, _ = make_agent()
    first = ask(agent, "Why did the employee fail?")
    assert first.route == "CLARIFY"
    second = ask(agent, "EMP024")
    assert second.route == "TOOL_RAG"
    assert second.route_source == "pending_clarification"
    assert second.entities["employee_id"] == "EMP024"


def test_clarification_completed_in_spanish_keeps_language(make_agent):
    agent, _ = make_agent()
    assert ask(agent, "¿Por qué falló el empleado?").route == "CLARIFY"
    second = ask(agent, "EMP027")
    assert (second.route, second.language) == ("TOOL_RAG", "es")
    assert "MISSING_INPUT" in second.answer


def test_unrelated_message_discards_pending_question(make_agent):
    agent, _ = make_agent()
    ask(agent, "Why did the employee fail?")
    r = ask(agent, "What is the net pay tolerance?")
    assert r.route == "RAG"
    assert ask(agent, "EMP024").route_source != "pending_clarification"


def test_explicit_employee_replaces_session_employee(make_agent):
    agent, _ = make_agent()
    ask(agent, "Why did EMP024 fail?")
    r = ask(agent, "Did EMP001 pass?")
    assert r.entities["employee_id"] == "EMP001" and r.entities_source["employee_id"] == "message"
    assert "net_pay: PASS" in r.answer


def test_sessions_are_isolated(make_agent):
    agent, _ = make_agent()
    ask(agent, "Why did EMP024 fail?", session="a")
    r = ask(agent, "What was the difference?", session="b")
    assert r.route == "CLARIFY"


def test_period_resolved_from_single_run(make_agent):
    agent, _ = make_agent()
    r = ask(agent, "Did EMP024 pass?")
    assert r.entities["period"] == "2026-09"
    assert r.entities_source["period"] == "default_single_run"
