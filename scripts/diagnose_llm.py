"""Diagnose the Gemini configuration (QA fix F5). Read-only: changes nothing.

    python scripts/diagnose_llm.py            # readable report
    python scripts/diagnose_llm.py --json     # same report as JSON

Checks, in order:
  1. configuration   GEMINI_MODEL / GEMINI_EMBEDDING_MODEL / timeout / key present (never the key)
  2. models          models this key can use with generateContent, and whether GEMINI_MODEL is one
  3. embeddings      one query embedding (proves key + network, like the RAG index)
  4. raw_minimal     generate_content with NO config: isolates the model from our parameters
  5. text            GeminiLLMClient.generate_text with the production configuration
  6. intent_json     GeminiLLMClient.generate_json(IntentOutput) with the production intent prompt

Reading the result:
  configuration fails           -> a model name is malformed (value shown with repr and its origin)
  503 / 429 with a "hint" line  -> provider availability or quota, transient: retry later
  raw_minimal fails             -> model / key / quota problem (see the error code: 404, 403, 429)
  raw_minimal ok, text fails    -> a parameter of our configuration is rejected (400)
  text ok, intent_json fails    -> structured output / schema problem
  empty response                -> the reply has no text part (finish_reason and part types are shown)

Every error is printed in full (up to 2000 characters) with the API key masked.
Exit code: 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import prompts  # noqa: E402
from app.agent.contracts import IntentOutput  # noqa: E402
from app.agent.entities import extract_entities  # noqa: E402
from app.agent.intent import build_intent_payload  # noqa: E402
from app.agent.session import SessionState  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.core.model_names import model_name_problem  # noqa: E402
from app.observability.redact import redact  # noqa: E402

ERROR_LENGTH = 2000
TRANSIENT = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED", "timed out")
PROBE_QUESTION = "Who approves the payroll?"


# ------------------------------------------------------------------ probes (also used by the canary test)
def probe_text(llm) -> str:
    """Production text path: same client and configuration as rag_answer / tool_rag_explain."""
    return llm.generate_text(task="diagnose_text", system="Reply with the single word OK.", user="ping")


def probe_intent(llm, message: str = PROBE_QUESTION) -> IntentOutput:
    """Production intent path: real intent prompt, payload and IntentOutput schema."""
    session = SessionState(session_id="diagnose")
    return llm.generate_json(task="intent", system=prompts.load_prompt(prompts.INTENT),
                             user=build_intent_payload(message, extract_entities(message), session),
                             schema=IntentOutput)


def _normalise(model: str | None) -> str:
    return model if not model or model.startswith("models/") else f"models/{model}"


def list_generation_models(client) -> list[str]:
    names = []
    for model in client.models.list():
        actions = getattr(model, "supported_actions", None) or []
        if "generateContent" in actions:
            names.append(model.name)
    return sorted(names)


def describe_empty(response: Any) -> str:
    """When a reply has no text, show why: finish reason and the kinds of parts returned."""
    details = []
    for candidate in getattr(response, "candidates", None) or []:
        parts = getattr(getattr(candidate, "content", None), "parts", None) or []
        kinds = sorted({k for p in parts for k in ("text", "thought", "function_call")
                        if getattr(p, k, None)})
        details.append(f"finish_reason={getattr(candidate, 'finish_reason', None)} parts={kinds or 'none'}")
    feedback = getattr(response, "prompt_feedback", None)
    if feedback:
        details.append(f"prompt_feedback={feedback}")
    return "; ".join(details) or "no candidates returned"


# ------------------------------------------------------------------ runner
def run_diagnosis(settings: Settings, *, genai_client=None, llm=None, embeddings=None) -> dict[str, Any]:
    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    secrets = [key]
    checks: dict[str, dict[str, Any]] = {}

    def check(name: str, action: Callable[[], Any]) -> Any:
        try:
            value = action()
        except Exception as error:  # report every failure, never stop the diagnosis
            message = redact(str(error), secrets, ERROR_LENGTH)
            checks[name] = {"ok": False, "error_type": type(error).__name__, "error": message}
            if any(marker in message for marker in TRANSIENT):
                checks[name]["hint"] = ("provider availability or quota (transient): retry later; "
                                        "this is not a configuration error")
            return None
        checks[name] = {"ok": True, "detail": redact(str(value), secrets, ERROR_LENGTH)}
        return value

    def origin(variable: str) -> str:
        return "system/terminal variable (overrides .env)" if variable in os.environ else ".env or default"

    # F6b: values shown with repr (reveals quotes, spaces, duplicated names) and their origin.
    problems = [p for p in (
        model_name_problem("GEMINI_MODEL", settings.gemini_model, "gemini-3.8-flash")
        if settings.gemini_model else None,
        model_name_problem("GEMINI_EMBEDDING_MODEL", settings.gemini_embedding_model,
                           "models/gemini-embedding-001"),
    ) if p]
    checks["configuration"] = {
        "ok": bool(key and settings.gemini_model) and not problems,
        "detail": {
            "GEMINI_API_KEY": f"set ({origin('GEMINI_API_KEY')})" if key else "MISSING",
            "GEMINI_MODEL": (f"{settings.gemini_model!r} ({origin('GEMINI_MODEL')})"
                             if settings.gemini_model else "MISSING"),
            "GEMINI_EMBEDDING_MODEL": (f"{settings.gemini_embedding_model!r} "
                                       f"({origin('GEMINI_EMBEDDING_MODEL')})"),
            "LLM_TIMEOUT_SECONDS": settings.llm_timeout_seconds,
        },
    }
    if problems:
        checks["configuration"]["error_type"] = "InvalidModelName"
        checks["configuration"]["error"] = " | ".join(problems)
    if not key:
        return {"ok": False, "checks": checks}

    if genai_client is None:
        from google import genai

        genai_client = genai.Client(api_key=key)

    models = check("models", lambda: list_generation_models(genai_client))
    if models is not None:
        checks["models"]["detail"] = models
        wanted = _normalise(settings.gemini_model)
        checks["model_available"] = {
            "ok": wanted in models,
            "detail": f"{wanted} {'is' if wanted in models else 'is NOT'} in the list for this key",
        }

    if embeddings is None:
        from app.rag.embeddings import GeminiEmbeddingProvider

        embeddings = check("embeddings_client", lambda: GeminiEmbeddingProvider(
            key, settings.gemini_embedding_model, settings.gemini_embedding_dimensions, client=genai_client))
    if embeddings is not None:
        check("embeddings", lambda: f"{len(embeddings.embed_query(PROBE_QUESTION))} dimensions")

    if settings.gemini_model:
        def raw_minimal() -> str:
            response = genai_client.models.generate_content(model=settings.gemini_model, contents="Reply with OK.")
            text = getattr(response, "text", None)
            if not text or not text.strip():
                raise RuntimeError(f"empty response: {describe_empty(response)}")
            return text.strip()

        check("raw_minimal", raw_minimal)

        if llm is None:
            from app.llm.gemini_client import GeminiLLMClient

            llm = check("llm_client", lambda: GeminiLLMClient(key, settings.gemini_model,
                                                              settings.llm_timeout_seconds, client=genai_client))
        if llm is not None:
            check("text", lambda: probe_text(llm))
            check("intent_json", lambda: probe_intent(llm).model_dump())

    return {"ok": all(c["ok"] for c in checks.values()), "checks": checks}


def format_report(report: dict[str, Any]) -> str:
    lines = ["Gemini diagnosis (API key never shown)", ""]
    for name, result in report["checks"].items():
        status = "OK  " if result["ok"] else "FAIL"
        lines.append(f"[{status}] {name}")
        if "detail" in result:
            detail = result["detail"]
            if isinstance(detail, dict):
                lines += [f"         {k}: {v}" for k, v in detail.items()]
            elif isinstance(detail, list):
                lines += [f"         {item}" for item in detail] or ["         (none)"]
            else:
                lines.append(f"         {detail}")
        if "error" in result:
            lines.append(f"         {result['error_type']}: {result['error']}")
        if "hint" in result:
            lines.append(f"         hint: {result['hint']}")
    lines += ["", "RESULT: " + ("all checks passed" if report["ok"] else "at least one check FAILED")]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose the Gemini configuration (read-only).")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args()
    report = run_diagnosis(get_settings())
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str) if args.json else format_report(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
