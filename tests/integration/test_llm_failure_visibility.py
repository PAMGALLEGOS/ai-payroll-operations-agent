"""CP4 QA fixes F1–F3 and the UI warning: a failing LLM must be visible, never hidden.

Regression for the QA finding "RAG generative fallback": Gemini generation failed,
the Agent degraded safely, and neither the log nor the evaluation showed it.
"""

import json

from app.agent.contracts import AgentRequest
from app.agent.fake_handlers import make_fake_llm
from app.observability.redact import redact
from app.web.views import llm_degraded
from scripts.evaluate_agent import evaluate
from tests.helpers import FAKE_KEY, failing_llm


# ---------------------------------------------------------------- F1
def test_redact_masks_keys_and_truncates():
    text = f"boom key={FAKE_KEY} and again {FAKE_KEY} secret-xyz " + "x" * 500
    clean = redact(text, ["secret-xyz"])
    assert FAKE_KEY not in clean and "secret-xyz" not in clean
    assert len(clean) <= 300


def test_llm_error_detail_is_logged_and_redacted(api_factory):
    api = api_factory(llm=failing_llm())
    api.post("/chat", json={"session_id": "s1", "message": "Who approves the payroll?"})
    failed = [e for e in api.observer.events if e["event"] == "llm_called" and not e["ok"]]
    assert failed
    for event in failed:
        assert "404 NOT_FOUND" in event["error"]
        assert len(event["error"]) <= 300
    assert FAKE_KEY not in json.dumps(api.observer.events)


def test_gemini_client_error_message_keeps_reason_and_masks_key():
    from app.llm.client import LLMError
    from app.llm.gemini_client import GeminiLLMClient

    class Models:
        def generate_content(self, **kwargs):
            raise RuntimeError(f"400 INVALID_ARGUMENT temperature (url ...?key={FAKE_KEY})")

    client = type("C", (), {"models": Models()})()
    llm = GeminiLLMClient(FAKE_KEY, "gemini-test", client=client)
    try:
        llm.generate_text(task="rag_answer", system="s", user="u")
    except LLMError as error:
        message = str(error)
    assert "RuntimeError: 400 INVALID_ARGUMENT" in message and FAKE_KEY not in message


# ---------------------------------------------------------------- F2
def test_fallback_events_are_emitted(make_agent):
    from app.observability.events import RecordingObserver

    agent, _ = make_agent(llm=failing_llm())
    agent.observer = observer = RecordingObserver()
    rag = agent.handle(AgentRequest("s1", "Who approves the payroll?"))
    tool_rag = agent.handle(AgentRequest("s2", "Why did EMP024 fail?"))

    tasks = [e["task"] for e in observer.events if e["event"] == "llm_fallback"]
    assert tasks == ["intent", "rag_answer", "intent", "tool_rag_explain"]
    assert rag.versions["llm_degraded"] == ["intent", "rag_answer"]
    assert tool_rag.versions["llm_degraded"] == ["intent", "tool_rag_explain"]
    # Behaviour unchanged: same safe degradation as before the fix (D4-08).
    assert (rag.route, rag.route_source, rag.answer_mode) == ("RAG", "fallback", "safe_fallback")
    assert (tool_rag.route, tool_rag.answer_mode) == ("TOOL_RAG", "template")


def test_no_fallback_event_when_llm_works(make_agent):
    from app.observability.events import RecordingObserver

    agent, _ = make_agent()
    agent.observer = observer = RecordingObserver()
    response = agent.handle(AgentRequest("s1", "Who approves the payroll?"))
    assert "llm_fallback" not in observer.names()
    assert response.versions["llm_degraded"] == []


# ---------------------------------------------------------------- F3
def test_evaluation_flags_llm_failures(make_agent, run_dir):
    agent, _ = make_agent(llm=failing_llm())
    report = evaluate(agent, run_dir)
    assert report["intent_llm_rate"] == 0.0
    assert report["generation_success_rate"] == 0.0
    assert not report["targets"]["intent_llm_rate"]["met"]
    assert not report["targets"]["generation_success_rate"]["met"]
    assert report["llm_fallbacks"]["intent"] > 0
    # The deterministic layer still routes correctly: that is exactly what hid the failure.
    assert report["targets"]["routing_accuracy"]["met"]


def test_allow_without_rewrite_excludes_fallbacks(make_agent, run_dir):
    agent, _ = make_agent(llm=failing_llm())
    report = evaluate(agent, run_dir)
    assert report["generated_answers"] == 0          # before F3 the safe_fallback answers counted here


def test_generation_failure_alone_is_detected(make_agent, run_dir):
    llm = make_fake_llm()
    llm.fail("rag_answer", times=1000)
    llm.fail("tool_rag_explain", times=1000)
    agent, _ = make_agent(llm=llm)
    report = evaluate(agent, run_dir)
    assert report["intent_llm_rate"] == 1.0
    assert report["generation_success_rate"] == 0.0 and report["generation_expected"] > 0


# ---------------------------------------------------------------- UI warning
def test_llm_degraded_helper():
    assert llm_degraded({"versions": {"llm_degraded": ["intent"]}})
    assert llm_degraded({"route_source": "fallback", "versions": {}})
    assert llm_degraded({"route": "TOOL_RAG", "evidence_status": "sufficient", "answer_mode": "template"})
    assert not llm_degraded({"route": "TOOL", "route_source": "llm_intent", "answer_mode": "template",
                             "versions": {"llm_degraded": []}})
    # An Auditor BLOCK is not "LLM unavailable": the LLM did answer.
    assert not llm_degraded({"route": "RAG", "route_source": "llm_intent", "answer_mode": "safe_fallback",
                             "evidence_status": "sufficient", "versions": {"llm_degraded": []}})


# ---------------------------------------------------------------- F7a
def _evaluate_with(llm, run_dir, fake_index_dir):
    from app.agent.factory import build_agent
    from app.core.config import Settings
    from app.observability.events import RecordingObserver

    observer = RecordingObserver()
    agent = build_agent(Settings(_env_file=None), llm=llm, embeddings_provider="fake",
                        results_dir=run_dir, index_dir=fake_index_dir, observer=observer)
    return evaluate(agent, run_dir, observer)


def test_quota_exhaustion_is_inconclusive_not_a_quality_failure(run_dir, fake_index_dir):
    report = _evaluate_with(failing_llm("ClientError: 429 RESOURCE_EXHAUSTED"), run_dir, fake_index_dir)
    assert report["status"] == "INCONCLUSIVE"
    assert report["provider_errors"]["quota_429"] > 0
    assert not report["targets"]["intent_llm_rate"]["met"]          # still reported as not met


def test_non_transient_llm_failure_is_fail(run_dir, fake_index_dir):
    report = _evaluate_with(failing_llm("ClientError: 400 INVALID_ARGUMENT"), run_dir, fake_index_dir)
    assert report["status"] == "FAIL" and report["provider_errors"] == {"other": report["provider_errors"]["other"]}


def test_working_llm_passes_with_status(run_dir, fake_index_dir):
    report = _evaluate_with(make_fake_llm(), run_dir, fake_index_dir)
    assert report["status"] == "PASS" and report["provider_errors"] == {}


# ---------------------------------------------------------------- F7c
def test_evaluation_stops_early_when_the_daily_quota_is_exhausted(run_dir, fake_index_dir):
    """Quota gone mid-run: the harness stops after 3 consecutive 429s instead of spending ~150 requests."""
    from types import SimpleNamespace

    from app.agent.factory import build_agent
    from app.core.config import Settings
    from app.observability.events import RecordingObserver
    from scripts.eval_pacing import QuotaGuard, paced_gemini_llm

    sent = []

    def generate_content(**kwargs):
        sent.append(1)
        if len(sent) <= 4:                      # the first requests still succeed …
            return SimpleNamespace(text='{"intent": "policy_question", "retrieval_query": "Who approves payroll?", '
                                        '"confidence": "high"}')
        raise RuntimeError("429 RESOURCE_EXHAUSTED quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier")

    settings = Settings(_env_file=None, gemini_api_key="AIzaSyFAKE0000000000000000000000000000",
                        gemini_model="gemini-3.8-flash")
    guard = QuotaGuard(secrets=["AIzaSyFAKE0000000000000000000000000000"])
    llm = paced_gemini_llm(settings, 0, genai_client=SimpleNamespace(models=SimpleNamespace(
        generate_content=generate_content)), guard=guard)
    observer = RecordingObserver()
    agent = build_agent(settings, llm=llm, embeddings_provider="fake", results_dir=run_dir,
                        index_dir=fake_index_dir, observer=observer)
    report = evaluate(agent, run_dir, observer, guard)

    assert report["status"] == "INCONCLUSIVE"
    assert report["quota_guard"]["tripped"] and report["cases_run"] < report["cases"]
    assert len(sent) == 4 + 3                    # 4 answered + 3 refused by Google, then nothing more
    assert "PerDay" in report["quota_guard"]["error_samples"]["quota_429"]
    assert "AIzaSyFAKE" not in str(report)
