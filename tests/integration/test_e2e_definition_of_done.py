"""Spec §22 Definition of Done, scenarios 2–10, in order, through the HTTP API (fake providers).

Scenario 1 (open the web app) is covered by tests/web/test_streamlit_app.py,
11 by running this suite, 12 by scripts/run_demo.py and 13 belongs to CP5.
"""


def test_definition_of_done_scenarios(api):
    # 2. View synthetic payroll validation results
    dashboard = api.get("/validation").json()
    assert dashboard["summary"]["total_validations"] == 90 and dashboard["summary"]["exception_count"] == 14

    # 3. Procedural question -> RAG-grounded answer with sources
    rag = api.post("/chat", json={"message": "Who approves the payroll?"}).json()
    assert rag["route"] == "RAG" and rag["evidence"] and rag["audit"]["verdict"] == "ALLOW"
    session = rag["session_id"]

    def ask(message):
        return api.post("/chat", json={"message": message, "session_id": session}).json()

    # 4. Employee result -> deterministic Engine result
    tool = ask("Did EMP024 pass validation?")
    assert tool["route"] == "TOOL" and tool["answer_mode"] == "template"
    assert tool["validation"]["results"] == api.get("/validation", params={"employee_id": "EMP024"}).json()["results"]

    # 5. Why did it fail -> Engine + RAG
    why = ask("Why did EMP024 fail?")
    assert why["route"] == "TOOL_RAG" and why["evidence"] and "OUT_OF_TOLERANCE" in why["answer"]

    # 6. Multi-turn follow-up resolved from session context
    follow = ask("What was the difference?")
    assert follow["entities"]["employee_id"] == "EMP024" and "+350.00" in follow["answer"]

    # 7. Ambiguous question -> clarification (new conversation, no employee in context)
    clarify = api.post("/chat", json={"message": "Why did the employee fail?"}).json()
    assert clarify["route"] == "CLARIFY" and clarify["clarification"]["reason"] == "missing_employee"

    # 8. Out-of-scope question -> controlled response
    oos = ask("Approve the payroll")
    assert oos["route"] == "OUT_OF_SCOPE" and oos["human_in_the_loop"]

    # 9. Unsupported / contradictory answer detected by Audit & Guardrails
    api.llm.script("tool_rag_explain", "EMP024 net_pay passed [RULE-003-C03].", "EMP024 net_pay passed [RULE-003-C03].")
    blocked = ask("Why did EMP024 fail?")
    assert blocked["audit"]["verdict"] == "BLOCK" and blocked["answer_mode"] == "safe_fallback"
    assert "difference +350.00 SYN" in blocked["answer"]          # Engine facts survive

    # 10. Trace an interaction through the events by trace_id
    events = [e["event"] for e in api.observer.events if e["trace_id"] == why["trace_id"]]
    assert events[0] == "request_received" and "response_completed" in events and events[-1] == "api_request"
