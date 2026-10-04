"""Gemini text generation through the google-genai SDK (decision C3-08).

* Model comes from GEMINI_MODEL; there is no hard-coded default.
* temperature=0 to reduce variability. The design never ASSUMES the LLM is
  deterministic: routing, facts and guards are deterministic code.
* Structured output: response_mime_type="application/json" plus the JSON
  schema of the expected pydantic model. The reply is validated again here.
* One retry on any failure (network error, invalid JSON, schema mismatch).

`client` can be injected so tests check the requests without network access.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.core.model_names import model_name_problem
from app.llm.client import LLMClient, LLMConfigError, LLMError, SchemaT
from app.observability.redact import redact

MAX_ATTEMPTS = 2


class GeminiLLMClient(LLMClient):
    name = "gemini"

    def __init__(self, api_key: str, model: str | None, timeout_seconds: int = 30, client: Any | None = None):
        if not api_key:
            raise LLMConfigError("GEMINI_API_KEY is empty")
        if not model:
            raise LLMConfigError(
                "GEMINI_MODEL is not set. Choose the Gemini text model explicitly in .env "
                "(decision C3-08: the model is confirmed against the real API, never assumed)."
            )
        problem = model_name_problem("GEMINI_MODEL", model, "gemini-3.8-flash")
        if problem:
            raise LLMConfigError(problem)   # F6b: fail fast, never a silent fallback
        self.model = model
        self.timeout_ms = timeout_seconds * 1000
        self._api_key = api_key   # only used to mask itself in error messages (F1)
        if client is None:
            from google import genai  # lazy: tests never need the SDK

            client = genai.Client(api_key=api_key)
        self._client = client

    def _config(self, system: str, schema: dict | None):
        from google.genai import types

        kwargs: dict[str, Any] = {
            "system_instruction": system,
            "temperature": 0,
            "http_options": types.HttpOptions(timeout=self.timeout_ms),
        }
        if schema is not None:
            kwargs["response_mime_type"] = "application/json"
            kwargs["response_json_schema"] = schema
        return types.GenerateContentConfig(**kwargs)

    def _call(self, task: str, system: str, user: str, schema: dict | None) -> str:
        response = self._client.models.generate_content(
            model=self.model, contents=user, config=self._config(system, schema)
        )
        text = getattr(response, "text", None)
        if not text or not text.strip():
            raise LLMError(f"Gemini returned an empty response for task '{task}'")
        return text

    def generate_json(self, *, task: str, system: str, user: str, schema: type[SchemaT]) -> SchemaT:
        last_error: Exception | None = None
        for _ in range(MAX_ATTEMPTS):
            try:
                text = self._call(task, system, user, schema.model_json_schema())
                return schema.model_validate(json.loads(text))
            except (LLMError, ValidationError, json.JSONDecodeError) as error:
                last_error = error
            except Exception as error:  # SDK / network errors
                last_error = error
        raise LLMError(self._failure(task, last_error))

    def _failure(self, task: str, error: Exception | None) -> str:
        """Readable, redacted reason: error class + provider message (F1)."""
        detail = f"{type(error).__name__}: {error}" if error else "unknown error"
        # Long limit here so diagnostics see the whole provider message; the event log
        # truncates again to 300 characters (ObservedLLMClient).
        return redact(f"Gemini task '{task}' failed after {MAX_ATTEMPTS} attempts: {detail}", [self._api_key],
                      max_length=2000)

    def generate_text(self, *, task: str, system: str, user: str) -> str:
        last_error: Exception | None = None
        for _ in range(MAX_ATTEMPTS):
            try:
                return self._call(task, system, user, None).strip()
            except Exception as error:
                last_error = error
        raise LLMError(self._failure(task, last_error))
