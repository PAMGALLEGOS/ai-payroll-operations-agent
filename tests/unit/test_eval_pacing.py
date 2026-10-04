"""F7a: evaluation-only pacing and INCONCLUSIVE classification (offline)."""

from types import SimpleNamespace

import pytest

from scripts.eval_pacing import (
    ENV_MIN_INTERVAL, PacedGenaiClient, Pacer, classify_provider_error, min_interval_from_env, paced_gemini_llm,
    provider_errors,
)
from scripts.evaluate_agent import overall_status
from tests.helpers import FAKE_KEY


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_default_interval_never_waits():
    clock = FakeClock()
    pacer = Pacer(0, clock=clock, sleep=clock.sleep)
    for _ in range(10):
        pacer.wait()
    assert clock.slept == [] and pacer.requests == 10


def test_pacing_keeps_any_minute_within_five_requests():
    clock = FakeClock()
    pacer = Pacer(13, clock=clock, sleep=clock.sleep)
    starts = []
    for _ in range(30):
        pacer.wait()
        starts.append(clock.now)
        clock.now += 2.0                       # simulated request latency
    assert max(sum(1 for s in starts if t <= s < t + 60) for t in starts) <= 5


def test_paced_client_paces_generate_content_and_delegates_the_rest():
    clock = FakeClock()
    calls = []
    models = SimpleNamespace(generate_content=lambda **kw: calls.append(clock.now) or "r",
                             list=lambda: ["m"])
    client = PacedGenaiClient(SimpleNamespace(models=models, other="x"), Pacer(13, clock=clock, sleep=clock.sleep))
    client.models.generate_content(model="m")
    client.models.generate_content(model="m")
    assert calls[1] - calls[0] == 13
    assert client.models.list() == ["m"] and client.other == "x"


def test_client_retry_is_paced_too(monkeypatch):
    """The Gemini client's own retry is a second HTTP request: it must wait as well."""
    import scripts.eval_pacing as pacing

    clock = FakeClock()
    monkeypatch.setattr(pacing, "_SHARED", {13.0: Pacer(13, clock=clock, sleep=clock.sleep)})
    attempts = []

    def generate_content(**kwargs):
        attempts.append(clock.now)
        if len(attempts) == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return SimpleNamespace(text="OK")

    settings = SimpleNamespace(gemini_api_key=SimpleNamespace(get_secret_value=lambda: FAKE_KEY),
                               gemini_model="gemini-3.8-flash", llm_timeout_seconds=30)
    llm = paced_gemini_llm(settings, 13.0, genai_client=SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)))
    assert llm.generate_text(task="t", system="s", user="u") == "OK"
    assert attempts[1] - attempts[0] == 13


def test_min_interval_from_env(monkeypatch):
    monkeypatch.delenv(ENV_MIN_INTERVAL, raising=False)
    assert min_interval_from_env() == 0
    monkeypatch.setenv(ENV_MIN_INTERVAL, "13")
    assert min_interval_from_env() == 13
    monkeypatch.setenv(ENV_MIN_INTERVAL, "-1")
    with pytest.raises(ValueError):
        min_interval_from_env()


@pytest.mark.parametrize("message,category", [
    ("ClientError: 429 RESOURCE_EXHAUSTED quotaId ...PerMinute...", "quota_429"),
    ("ServerError: 503 UNAVAILABLE high demand", "unavailable_503"),
    ("ReadTimeout: timed out", "timeout"),
    ("ClientError: 400 INVALID_ARGUMENT", "other"),
    ("ClientError: 404 NOT_FOUND", "other"),
])
def test_classify_provider_error(message, category):
    assert classify_provider_error(message) == category


def test_provider_errors_counts_only_failed_llm_calls():
    events = [{"event": "llm_called", "ok": True},
              {"event": "llm_called", "ok": False, "error": "429 RESOURCE_EXHAUSTED"},
              {"event": "llm_called", "ok": False, "error": "400 INVALID_ARGUMENT"},
              {"event": "tool_called"}]
    assert provider_errors(events) == {"other": 1, "quota_429": 1}


def _targets(**missed):
    names = ["routing_accuracy", "clarify_missing_employee", "out_of_scope", "agent_engine_consistency",
             "seeded_auditor_detection", "intent_llm_rate", "generation_success_rate"]
    return {n: {"met": n not in missed} for n in names}


def test_overall_status():
    assert overall_status(_targets(), {}) == "PASS"
    assert overall_status(_targets(intent_llm_rate=1), {"quota_429": 40}) == "INCONCLUSIVE"
    assert overall_status(_targets(intent_llm_rate=1), {}) == "FAIL"
    assert overall_status(_targets(intent_llm_rate=1), {"other": 3}) == "FAIL"
    # Deterministic targets are never excused by provider errors.
    assert overall_status(_targets(agent_engine_consistency=1), {"quota_429": 40}) == "FAIL"


# ---------------------------------------------------------------- F7c quota guard
from scripts.eval_pacing import QuotaExhausted, QuotaGuard, preflight  # noqa: E402

QUOTA_MSG = ("429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'details': [{'violations': [{'quotaId': "
             "'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaValue': '20'}]}]}} key=" + FAKE_KEY)


class ScriptedModels:
    """Fake SDK models: replies from a script; counts real (HTTP) requests."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = 0

    def generate_content(self, **kwargs):
        self.requests += 1
        outcome = self.outcomes.pop(0) if self.outcomes else "ok"
        if outcome == "ok":
            return SimpleNamespace(text="OK")
        raise RuntimeError(outcome)


def _guarded_client(models, guard):
    return PacedGenaiClient(SimpleNamespace(models=models), Pacer(0), guard)


def test_guard_trips_after_three_consecutive_quota_errors_and_stops_http():
    models = ScriptedModels(QUOTA_MSG, QUOTA_MSG, QUOTA_MSG, "ok")
    guard = QuotaGuard(secrets=[FAKE_KEY])
    client = _guarded_client(models, guard)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            client.models.generate_content(model="m")
    assert guard.tripped and "3 consecutive" in guard.reason
    with pytest.raises(QuotaExhausted) as refused:
        client.models.generate_content(model="m")
    assert models.requests == 3                       # the 4th call never reached the provider
    assert classify_provider_error(str(refused.value)) == "quota_429"


def test_success_or_other_error_resets_the_counter():
    models = ScriptedModels(QUOTA_MSG, QUOTA_MSG, "ok", QUOTA_MSG, "500 INTERNAL", QUOTA_MSG)
    guard = QuotaGuard()
    client = _guarded_client(models, guard)
    for _ in range(6):
        try:
            client.models.generate_content(model="m")
        except RuntimeError:
            pass
    assert not guard.tripped


def test_error_sample_keeps_quota_id_and_masks_the_key():
    guard = QuotaGuard(secrets=[FAKE_KEY])
    guard.record_error(RuntimeError(QUOTA_MSG))
    sample = guard.summary()["error_samples"]["quota_429"]
    assert "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in sample
    assert FAKE_KEY not in sample and len(sample) <= 2000


def _llm(models, guard):
    from app.llm.gemini_client import GeminiLLMClient
    return GeminiLLMClient(FAKE_KEY, "gemini-3.8-flash", client=_guarded_client(models, guard))


def test_preflight_sends_one_request_and_reports_quota():
    models = ScriptedModels(QUOTA_MSG)
    result = preflight(_llm(models, QuotaGuard(secrets=[FAKE_KEY])))
    assert models.requests == 1                        # no client retry in the preflight
    assert not result["ok"] and result["transient"] and result["category"] == "quota_429"
    assert "PerDay" in result["error"] and FAKE_KEY not in result["error"]


def test_preflight_ok_and_non_transient_error():
    assert preflight(_llm(ScriptedModels("ok"), QuotaGuard()))["ok"]
    bad = preflight(_llm(ScriptedModels("400 INVALID_ARGUMENT model name"), QuotaGuard()))
    assert not bad["ok"] and not bad["transient"] and bad["category"] == "other"
