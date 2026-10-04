"""Evaluation-only pacing and provider-error classification (QA fix F7a).

Used ONLY by the evaluation harness (scripts/evaluate_agent.py and the
`pytest -m eval` tests). The production Agent, its Gemini client and the
deterministic fallback are not changed.

* Pacing: every Gemini `generate_content` request waits until at least
  `min_interval` seconds have passed since the previous request started.
  It paces HTTP requests, so the client's own retry is paced too. One pacer is
  shared per process, so all eval tests in one pytest run share the budget.
  Default 0 = no pacing (unchanged behaviour).
* Classification: provider quota / availability errors (429, 503, timeouts)
  are told apart from real defects, so a rate-limited run is reported as
  INCONCLUSIVE instead of an Agent quality failure.

Free-tier example: 5 requests/minute -> --min-interval 13 (60/5 = 12, plus margin).

F7c (quota guard, also evaluation-only):
* Preflight: one paced request before the evaluation; a quota / availability
  error stops the run before any case is spent.
* Early stop: after QUOTA_STOP_AFTER consecutive 429 responses the guard trips;
  later requests are refused locally (no HTTP call), and the harness stops.
* Error samples: the first full provider message of each category is kept,
  masked (API key never stored), up to 2000 characters, so the `quotaId`
  (PerMinute / PerDay) is visible in the report.
"""

from __future__ import annotations

import os
import threading
import time
from collections import Counter
from typing import Any, Callable, Iterable

from app.observability.redact import redact

ENV_MIN_INTERVAL = "EVAL_LLM_MIN_INTERVAL_SECONDS"
QUOTA_STOP_AFTER = 3
SAMPLE_LENGTH = 2000

TRANSIENT_MARKERS = {
    "quota_429": ("429", "RESOURCE_EXHAUSTED"),
    "unavailable_503": ("503", "UNAVAILABLE"),
    "timeout": ("DEADLINE_EXCEEDED", "timed out", "Timeout", "ReadTimeout"),
}


def min_interval_from_env(default: float = 0.0) -> float:
    value = os.environ.get(ENV_MIN_INTERVAL, "").strip()
    if not value:
        return default
    seconds = float(value)
    if seconds < 0:
        raise ValueError(f"{ENV_MIN_INTERVAL} must be >= 0, got {value!r}")
    return seconds


class Pacer:
    """Keeps request starts at least `min_interval` seconds apart."""

    def __init__(self, min_interval: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.min_interval = min_interval
        self._clock, self._sleep = clock, sleep
        self._last: float | None = None
        self._lock = threading.Lock()
        self.waited_seconds = 0.0
        self.requests = 0

    def wait(self) -> None:
        with self._lock:
            if self.min_interval > 0 and self._last is not None:
                remaining = self._last + self.min_interval - self._clock()
                if remaining > 0:
                    self._sleep(remaining)
                    self.waited_seconds += remaining
            self._last = self._clock()
            self.requests += 1


_SHARED: dict[float, Pacer] = {}


def shared_pacer(min_interval: float) -> Pacer:
    """One pacer per interval per process: every eval client shares the request budget."""
    if min_interval not in _SHARED:
        _SHARED[min_interval] = Pacer(min_interval)
    return _SHARED[min_interval]


class QuotaExhausted(RuntimeError):
    """Raised locally, without an HTTP call, once the guard has tripped."""


class QuotaGuard:
    """Watches every Gemini response of the evaluation (F7c)."""

    def __init__(self, stop_after: int = QUOTA_STOP_AFTER, secrets: Iterable[str | None] = ()):
        self.stop_after = stop_after
        self.secrets = [s for s in secrets if s]
        self.consecutive_quota = 0
        self.tripped = False
        self.reason: str | None = None
        self.samples: dict[str, str] = {}
        self.refused = 0

    def check(self) -> None:
        if self.tripped:
            self.refused += 1
            # Worded so it is classified as quota_429 (no HTTP request was sent).
            raise QuotaExhausted(f"429 RESOURCE_EXHAUSTED refused locally by the evaluation quota guard "
                                 f"({self.reason}); no request sent")

    def record_success(self) -> None:
        self.consecutive_quota = 0

    def record_error(self, error: BaseException) -> None:
        message = redact(f"{type(error).__name__}: {error}", self.secrets, SAMPLE_LENGTH)
        category = classify_provider_error(message)
        self.samples.setdefault(category, message)
        if category == "quota_429":
            self.consecutive_quota += 1
            if self.consecutive_quota >= self.stop_after and not self.tripped:
                self.tripped = True
                self.reason = f"{self.consecutive_quota} consecutive quota_429 responses"
        else:
            self.consecutive_quota = 0

    def summary(self) -> dict[str, Any]:
        return {"tripped": self.tripped, "reason": self.reason, "refused_requests": self.refused,
                "error_samples": dict(sorted(self.samples.items()))}


_GUARD: QuotaGuard | None = None


def shared_guard(secrets: Iterable[str | None] = ()) -> QuotaGuard:
    """One guard per process, shared by every evaluation client (like the pacer)."""
    global _GUARD
    if _GUARD is None:
        _GUARD = QuotaGuard(secrets=secrets)
    else:
        _GUARD.secrets.extend(s for s in secrets if s and s not in _GUARD.secrets)
    return _GUARD


class _PacedModels:
    def __init__(self, models: Any, pacer: Pacer, guard: QuotaGuard | None = None):
        self._models, self._pacer, self._guard = models, pacer, guard

    def generate_content(self, **kwargs: Any) -> Any:
        if self._guard:
            self._guard.check()                      # tripped: refuse before pacing or HTTP
        self._pacer.wait()
        try:
            response = self._models.generate_content(**kwargs)
        except Exception as error:
            if self._guard:
                self._guard.record_error(error)
            raise
        if self._guard:
            self._guard.record_success()
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._models, name)


class PacedGenaiClient:
    """Wraps a google-genai client; only `models.generate_content` is paced."""

    def __init__(self, client: Any, pacer: Pacer, guard: QuotaGuard | None = None):
        self._client = client
        self.models = _PacedModels(client.models, pacer, guard)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def paced_gemini_llm(settings, min_interval: float, genai_client: Any | None = None,
                     guard: QuotaGuard | None = None):
    """A GeminiLLMClient whose requests are paced and guarded. Same model, prompts and configuration."""
    from app.llm.client import LLMConfigError
    from app.llm.gemini_client import GeminiLLMClient

    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    if not key:
        raise LLMConfigError("The Gemini LLM needs GEMINI_API_KEY.")
    if genai_client is None:
        from google import genai

        genai_client = genai.Client(api_key=key)
    guard = guard or shared_guard([key])
    return GeminiLLMClient(key, settings.gemini_model, settings.llm_timeout_seconds,
                           client=PacedGenaiClient(genai_client, shared_pacer(min_interval), guard))


def preflight(llm) -> dict[str, Any]:
    """One request through the evaluation client, without the client's own retry (F7c).

    `llm` is the client from `paced_gemini_llm`; its raw (paced, guarded) SDK client
    sends exactly one `generate_content` request.
    """
    try:
        response = llm._client.models.generate_content(model=llm.model, contents="Reply with OK.")
    except Exception as error:   # the guard already stored the masked sample
        message = redact(f"{type(error).__name__}: {error}", [getattr(llm, "_api_key", None)], SAMPLE_LENGTH)
        category = classify_provider_error(message)
        return {"ok": False, "category": category, "transient": category in TRANSIENT_MARKERS, "error": message}
    text = (getattr(response, "text", None) or "").strip()
    return {"ok": bool(text), "category": None if text else "other", "transient": False,
            "error": None if text else "empty response"}


def classify_provider_error(message: str) -> str:
    for category, markers in TRANSIENT_MARKERS.items():
        if any(marker in message for marker in markers):
            return category
    return "other"


def provider_errors(events: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Count failed LLM calls by category, from the `llm_called` events (F1)."""
    counts = Counter(classify_provider_error(e.get("error", ""))
                     for e in events if e.get("event") == "llm_called" and not e.get("ok", True))
    return dict(sorted(counts.items()))


def is_transient(categories: dict[str, int]) -> bool:
    return any(categories.get(c) for c in TRANSIENT_MARKERS)
