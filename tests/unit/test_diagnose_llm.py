"""F5: the diagnostic script runs offline with injected fakes and never prints the key."""

from types import SimpleNamespace

from app.core.config import Settings
from app.llm.client import LLMError
from scripts.diagnose_llm import format_report, run_diagnosis
from tests.helpers import FAKE_KEY


class FakeModels:
    def __init__(self, fail_raw=False, empty=False):
        self.fail_raw, self.empty = fail_raw, empty

    def list(self):
        return [SimpleNamespace(name="models/gemini-ok", supported_actions=["generateContent"]),
                SimpleNamespace(name="models/embed", supported_actions=["embedContent"])]

    def generate_content(self, **kwargs):
        if self.fail_raw:
            raise RuntimeError(f"404 NOT_FOUND model not found ?key={FAKE_KEY}")
        if self.empty:
            part = SimpleNamespace(text=None, thought=True, function_call=None)
            return SimpleNamespace(text=None, prompt_feedback=None, candidates=[
                SimpleNamespace(finish_reason="STOP", content=SimpleNamespace(parts=[part]))])
        return SimpleNamespace(text="OK")


class FakeEmbeddings:
    def embed_query(self, text):
        return [0.0] * 768


class FakeLLM:
    def __init__(self, fail=False):
        self.fail = fail

    def generate_text(self, **kwargs):
        if self.fail:
            raise LLMError(f"400 INVALID_ARGUMENT key={FAKE_KEY}")
        return "OK"

    def generate_json(self, *, schema, **kwargs):
        if self.fail:
            raise LLMError("400 INVALID_ARGUMENT")
        return schema(intent="policy_question", retrieval_query="Who approves payroll?", confidence="high")


def _settings(model="gemini-ok"):
    return Settings(_env_file=None, gemini_api_key=FAKE_KEY, gemini_model=model)


def _run(models, llm, model="gemini-ok"):
    return run_diagnosis(_settings(model), genai_client=SimpleNamespace(models=models),
                         llm=llm, embeddings=FakeEmbeddings())


def test_all_checks_pass():
    report = _run(FakeModels(), FakeLLM())
    assert report["ok"], report
    assert report["checks"]["model_available"]["ok"]


def test_failures_are_reported_and_key_never_printed():
    report = _run(FakeModels(fail_raw=True), FakeLLM(fail=True), model="gemini-missing")
    assert not report["ok"]
    assert not report["checks"]["model_available"]["ok"]
    assert "404 NOT_FOUND" in report["checks"]["raw_minimal"]["error"]
    assert "400 INVALID_ARGUMENT" in report["checks"]["text"]["error"]
    text = format_report(report)
    assert FAKE_KEY not in text and FAKE_KEY not in str(report)
    assert "FAIL" in text


def test_empty_response_explains_parts():
    report = _run(FakeModels(empty=True), FakeLLM())
    error = report["checks"]["raw_minimal"]["error"]
    assert "finish_reason=STOP" in error and "thought" in error


def test_missing_key_stops_early():
    report = run_diagnosis(Settings(_env_file=None, gemini_api_key=None, gemini_model=None))
    assert not report["ok"] and report["checks"]["configuration"]["detail"]["GEMINI_API_KEY"] == "MISSING"


def test_malformed_model_name_fails_configuration_with_repr_and_origin(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "GEMINI_MODEL=gemini-ok")
    settings = Settings(_env_file=None, gemini_api_key=FAKE_KEY)
    report = run_diagnosis(settings, genai_client=SimpleNamespace(models=FakeModels()),
                           llm=FakeLLM(), embeddings=FakeEmbeddings())
    config = report["checks"]["configuration"]
    assert not config["ok"] and config["error_type"] == "InvalidModelName"
    assert "'GEMINI_MODEL=gemini-ok'" in config["detail"]["GEMINI_MODEL"]
    assert "system/terminal variable" in config["detail"]["GEMINI_MODEL"]
    assert FAKE_KEY not in format_report(report)


def test_transient_provider_error_gets_a_hint():
    class Busy(FakeLLM):
        def generate_json(self, **kwargs):
            raise LLMError("ServerError: 503 UNAVAILABLE. The model is overloaded. Try again later.")

    report = _run(FakeModels(), Busy())
    assert not report["ok"]
    assert "transient" in report["checks"]["intent_json"]["hint"]
    assert "hint:" in format_report(report)
    assert report["checks"]["configuration"]["ok"]
