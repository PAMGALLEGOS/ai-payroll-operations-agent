"""POST /chat — the five routes over HTTP, sessions, trace ids and input validation."""

import pytest

from app.agent.contracts import AgentRequest


@pytest.mark.parametrize("message,route,lang", [
    ("What is the net pay tolerance?", "RAG", "en"),
    ("¿EMP024 pasó la validación?", "TOOL", "es"),
    ("Why did EMP024 fail?", "TOOL_RAG", "en"),
    ("¿Por qué falló el empleado?", "CLARIFY", "es"),
    ("Approve the payroll", "OUT_OF_SCOPE", "en"),
])
def test_routes_over_http(api, message, route, lang):
    r = api.post("/chat", json={"message": message})
    assert r.status_code == 200
    body = r.json()
    assert (body["route"], body["language"]) == (route, lang)
    assert body["trace_id"] == r.headers["X-Trace-Id"]


def test_session_id_is_generated_and_reused_for_follow_ups(api):
    first = api.post("/chat", json={"message": "Why did EMP024 fail?"}).json()
    assert first["session_id"].startswith("S-")
    second = api.post("/chat", json={"message": "What was the difference?", "session_id": first["session_id"]}).json()
    assert second["route"] == "TOOL" and second["entities"]["employee_id"] == "EMP024"
    assert "difference +350.00 SYN" in second["answer"]


def test_without_session_id_conversations_are_independent(api):
    api.post("/chat", json={"message": "Why did EMP024 fail?"})
    r = api.post("/chat", json={"message": "What was the difference?"}).json()
    assert r["route"] == "CLARIFY"


def test_api_response_equals_agent_response(api, api_factory):
    via_api = api.post("/chat", json={"message": "Did EMP026 pass?", "session_id": "same"}).json()
    other = api_factory()
    direct = other.agent.handle(AgentRequest("same", "Did EMP026 pass?")).to_dict()
    for key in ("route", "intent", "answer", "validation", "evidence_status", "answer_mode"):
        assert via_api[key] == direct[key]


@pytest.mark.parametrize("payload", [
    {"message": ""},
    {"message": "x" * 1001},
    {},
    {"message": "hi", "session_id": "bad id with spaces"},
])
def test_invalid_input_is_422_without_echo(api, payload):
    r = api.post("/chat", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "invalid_request" and body["trace_id"]
    assert "x" * 50 not in body["message"]


def test_money_values_stay_strings(api):
    body = api.post("/chat", json={"message": "Did EMP024 pass?"}).json()
    for row in body["validation"]["results"]:
        assert isinstance(row["expected_value"], str) and isinstance(row["tolerance"], str)
