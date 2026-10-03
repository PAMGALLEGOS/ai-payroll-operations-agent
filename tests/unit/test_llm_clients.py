"""LLMClient implementations: fake (scripting, failures, call log) and Gemini (simulated client)."""

import json
from types import SimpleNamespace

import pytest

from app.agent.contracts import IntentOutput
from app.agent.factory import create_llm_client
from app.core.config import Settings
from app.llm.client import LLMConfigError, LLMError
from app.llm.fake_client import FakeLLMClient
from app.llm.gemini_client import GeminiLLMClient


# ------------------------------------------------------------------ fake
def test_fake_uses_handler_and_records_calls():
    llm = FakeLLMClient({"intent": lambda s, u: {"intent": "policy_question"}})
    out = llm.generate_json(task="intent", system="s", user="u", schema=IntentOutput)
    assert out.intent == "policy_question"
    assert len(llm.calls_for("intent")) == 1


def test_fake_scripted_responses_take_priority_in_order():
    llm = FakeLLMClient({"x": lambda s, u: "default"})
    llm.script("x", "first", "second")
    assert [llm.generate_text(task="x", system="", user="") for _ in range(3)] == ["first", "second", "default"]


def test_fake_scripted_failure():
    llm = FakeLLMClient({"x": lambda s, u: "ok"})
    llm.fail("x")
    with pytest.raises(LLMError):
        llm.generate_text(task="x", system="", user="")
    assert llm.generate_text(task="x", system="", user="") == "ok"


def test_fake_schema_mismatch_is_llm_error():
    llm = FakeLLMClient({"intent": lambda s, u: {"intent": "approve_payroll"}})
    with pytest.raises(LLMError):
        llm.generate_json(task="intent", system="", user="", schema=IntentOutput)


# ---------------------------------------------------------------- gemini
class SimulatedGemini:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply)


def _gemini(replies):
    client = SimulatedGemini(replies)
    return GeminiLLMClient("key", "configured-model", 20, client=client), client


def test_gemini_requires_explicit_model():
    with pytest.raises(LLMConfigError, match="GEMINI_MODEL"):
        GeminiLLMClient("key", None, client=SimulatedGemini([]))


def test_gemini_requires_api_key():
    with pytest.raises(LLMConfigError):
        GeminiLLMClient("", "m", client=SimulatedGemini([]))


def test_gemini_structured_request_uses_schema_and_temperature_zero():
    llm, client = _gemini([json.dumps({"intent": "validation_lookup", "retrieval_query": ""})])
    out = llm.generate_json(task="intent", system="SYS", user="USER", schema=IntentOutput)
    assert out.intent == "validation_lookup"
    call = client.calls[0]
    assert call["model"] == "configured-model"
    assert call["config"].temperature == 0
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_json_schema["properties"]["intent"]
    assert call["config"].system_instruction == "SYS"
    assert call["config"].http_options.timeout == 20_000


def test_gemini_retries_once_on_invalid_json():
    llm, client = _gemini(["not json", json.dumps({"intent": "policy_question"})])
    assert llm.generate_json(task="intent", system="", user="", schema=IntentOutput).intent == "policy_question"
    assert len(client.calls) == 2


def test_gemini_fails_after_two_attempts():
    llm, _ = _gemini([RuntimeError("network"), json.dumps({"intent": "bad"})])
    with pytest.raises(LLMError, match="after 2 attempts"):
        llm.generate_json(task="intent", system="", user="", schema=IntentOutput)


def test_gemini_text_generation_has_no_json_mode():
    llm, client = _gemini(["  An explanation [RULE-003-C03].  "])
    assert llm.generate_text(task="rag_answer", system="", user="") == "An explanation [RULE-003-C03]."
    assert client.calls[0]["config"].response_mime_type is None


def test_factory_without_credentials():
    with pytest.raises(LLMConfigError, match="GEMINI_API_KEY"):
        create_llm_client(Settings(_env_file=None), "gemini")
    assert create_llm_client(Settings(_env_file=None), "fake").name == "fake"


def test_default_settings_have_no_hardcoded_text_model():
    assert Settings(_env_file=None).gemini_model is None
