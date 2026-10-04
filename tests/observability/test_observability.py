"""Observability: event sequences per route, one trace_id, privacy of logs, KPI report."""

import json

import pytest

from app.agent.contracts import AgentRequest
from app.agent.factory import build_agent
from app.agent.fake_handlers import make_fake_llm
from app.core.config import Settings
from app.observability.events import FanOutObserver, RecordingObserver, message_fingerprint
from app.observability.logger import JsonEventLogger, configure_event_logging
from scripts.metrics_report import compute_kpis, read_events


@pytest.fixture
def observed(run_dir, fake_index_dir):
    def _make(observer, llm=None):
        return build_agent(Settings(_env_file=None), llm=llm or make_fake_llm(), embeddings_provider="fake",
                           results_dir=run_dir, index_dir=fake_index_dir, observer=observer)
    return _make


@pytest.mark.parametrize("message,expected", [
    ("Why did EMP024 fail?",
     ["request_received", "llm_called", "intent_identified", "tool_called", "engine_result", "rag_retrieved",
      "llm_called", "auditor_result", "route_decided", "response_completed"]),
    ("Did EMP024 pass?",
     ["request_received", "llm_called", "intent_identified", "tool_called", "engine_result", "auditor_result",
      "route_decided", "response_completed"]),
    ("What is the net pay tolerance?",
     ["request_received", "llm_called", "intent_identified", "rag_retrieved", "llm_called", "auditor_result",
      "route_decided", "response_completed"]),
    ("Approve the payroll",
     ["request_received", "auditor_result", "route_decided", "response_completed"]),
])
def test_event_sequence_per_route(observed, message, expected):
    recorder = RecordingObserver()
    response = observed(recorder).handle(AgentRequest("s", message))
    assert recorder.names(response.trace_id) == expected
    assert {e["trace_id"] for e in recorder.events} == {response.trace_id}


def test_generation_llm_not_called_for_template_routes(observed):
    recorder = RecordingObserver()
    agent = observed(recorder)
    for message in ["Did EMP024 pass?", "Why did the employee fail?", "Approve the payroll"]:
        agent.handle(AgentRequest(message, message))
    tasks = [e["task"] for e in recorder.events if e["event"] == "llm_called"]
    assert "rag_answer" not in tasks and "tool_rag_explain" not in tasks


def test_fallback_and_rewrite_are_visible(observed):
    recorder = RecordingObserver()
    llm = make_fake_llm()
    llm.fail("intent")
    llm.script("tool_rag_explain", "EMP024 net_pay passed [RULE-003-C03].",
               "For EMP024, net_pay is FAIL with OUT_OF_TOLERANCE [RULE-003-C03].")
    observed(recorder, llm).handle(AgentRequest("s", "Why did EMP024 fail?"))
    intent = next(e for e in recorder.events if e["event"] == "intent_identified")
    assert intent["source"] == "fallback"
    llm_events = [e for e in recorder.events if e["event"] == "llm_called"]
    assert llm_events[0] == {**llm_events[0], "task": "intent", "ok": False}
    audits = [e for e in recorder.events if e["event"] == "auditor_result"]
    assert [a["verdict"] for a in audits] == ["REVISE", "ALLOW"]
    assert audits[0]["failed_checks"] == ["status_consistency"]
    done = next(e for e in recorder.events if e["event"] == "response_completed")
    assert done["revised"] is True


def test_observers_never_change_answers(observed, make_agent):
    plain, _ = make_agent()
    watched = observed(RecordingObserver())
    for message in ["Why did EMP024 fail?", "¿Cuántas excepciones hay?", "What is the net pay tolerance?"]:
        a = plain.handle(AgentRequest("x", message)).to_dict()
        b = watched.handle(AgentRequest("x", message)).to_dict()
        for key in ("route", "answer", "validation", "evidence", "audit"):
            assert a[key] == b[key]


# ---------------------------------------------------------------- privacy
def test_log_file_has_json_lines_and_no_content(observed, tmp_path):
    log = tmp_path / "agent.jsonl"
    logger = configure_event_logging(log, to_stdout=False)
    agent = observed(JsonEventLogger(logger))
    secret_question = "Why did EMP024 fail? my-private-note-xyz"
    response = agent.handle(AgentRequest("s", secret_question))
    agent.handle(AgentRequest("s", "¿Quién aprueba la nómina?"))
    for handler in logger.handlers:
        handler.flush()

    text = log.read_text(encoding="utf-8")
    events = [json.loads(line) for line in text.splitlines()]
    assert all({"ts", "trace_id", "event"} <= e.keys() for e in events)
    assert "my-private-note-xyz" not in text and "Quién aprueba" not in text   # no user text
    assert response.answer.splitlines()[0] not in text                          # no answers
    assert "SYNTHETIC proof of concept" not in text                             # no prompts
    received = next(e for e in events if e["event"] == "request_received")
    assert received["message_hash"] == message_fingerprint(secret_question)
    assert received["message_length"] == len(secret_question)


def test_fan_out_observer():
    a, b = RecordingObserver(), RecordingObserver()
    FanOutObserver(a, b).emit("error", component="x", error_type="Y")
    assert a.names() == b.names() == ["error"]


# ---------------------------------------------------------------- KPIs
def test_metrics_report_from_real_log(observed, tmp_path):
    log = tmp_path / "agent.jsonl"
    logger = configure_event_logging(log, to_stdout=False)
    agent = observed(JsonEventLogger(logger))
    for message in ["Why did EMP024 fail?", "What was the difference?", "What is the net pay tolerance?",
                    "Approve the payroll", "What is the vacation accrual policy for interns?"]:
        agent.handle(AgentRequest("kpi", message))
    for handler in logger.handlers:
        handler.flush()

    kpis = compute_kpis(read_events(log))
    assert kpis["interactions"] == kpis["traces"] == 5
    assert kpis["by_route"] == {"TOOL_RAG": 1, "TOOL": 1, "RAG": 2, "OUT_OF_SCOPE": 1}
    assert set(kpis["latency_ms_by_route"]) == {"TOOL_RAG", "TOOL", "RAG", "OUT_OF_SCOPE"}
    assert kpis["auditor_final_verdicts"] == {"ALLOW": 5}
    assert kpis["retrieval"] == {"sufficient": 2, "insufficient": 1}
    assert kpis["tool_calls"] == 2
    assert kpis["llm_calls"]["intent"]["calls"] == 4
    assert kpis["errors"] == {}


def test_metrics_report_ignores_non_json_lines(tmp_path):
    log = tmp_path / "agent.jsonl"
    log.write_text('INFO server started\n{"event": "response_completed", "route": "TOOL", "trace_id": "T1", '
                   '"latency_ms": 5, "answer_mode": "template", "verdict": "ALLOW"}\n', encoding="utf-8")
    assert compute_kpis(read_events(log))["interactions"] == 1
