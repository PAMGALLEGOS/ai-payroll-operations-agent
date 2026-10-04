"""Gemini canary (QA fix F4): the two production LLM calls, called directly.

The Agent degrades safely when Gemini fails, so an Agent-level test can pass
with Gemini broken. These tests call the client without any fallback; when
they fail, the assertion shows the (redacted) provider error.

    pytest -m eval tests/evaluation/test_gemini_canary.py -v

F7a: requests are paced by EVAL_LLM_MIN_INTERVAL_SECONDS, and a provider quota /
availability error (429, 503, timeout) is reported as INCONCLUSIVE (skip), while
any other error (400, 404, schema) still fails.
"""

import pytest

from app.agent.contracts import IntentOutput
from app.core.config import get_settings
from app.llm.client import LLMError
from scripts.diagnose_llm import probe_intent, probe_text
from scripts.eval_pacing import TRANSIENT_MARKERS, classify_provider_error, min_interval_from_env, paced_gemini_llm

pytestmark = pytest.mark.eval


@pytest.fixture(scope="module")
def gemini():
    settings = get_settings()
    if not settings.gemini_api_key or not settings.gemini_model:
        pytest.skip("GEMINI_API_KEY and GEMINI_MODEL are required for the Gemini canary")
    # Evaluation client: pacing (default 0) + quota guard shared with the other eval tests (F7c).
    return paced_gemini_llm(settings, min_interval_from_env())


def _fail_or_inconclusive(call: str, error: LLMError):
    if classify_provider_error(str(error)) in TRANSIENT_MARKERS:
        pytest.skip(f"INCONCLUSIVE — provider quota/availability in {call}: {error}")
    pytest.fail(f"{call} failed: {error}")


def test_gemini_canary_text(gemini):
    try:
        text = probe_text(gemini)
    except LLMError as error:
        _fail_or_inconclusive("generate_text", error)
    assert text.strip()


def test_gemini_canary_json(gemini):
    try:
        output = probe_intent(gemini)
    except LLMError as error:
        _fail_or_inconclusive("generate_json(IntentOutput)", error)
    assert isinstance(output, IntentOutput)
    assert output.intent == "policy_question", output
    assert output.retrieval_query.strip()
