"""Deterministic, scriptable LLM test double.

* `handlers` map a task name to a function (system, user) -> str | dict that
  produces the default answer. The Agent package provides bilingual default
  handlers (app/agent/fake_handlers.py), so this module knows nothing about
  payroll.
* `script(task, *responses)` queues exact responses for the next calls of a task.
  Tests use it to inject wrong answers (an invented number, an approval) and
  check that the guards catch them.
* `fail(task)` makes the next call of a task raise LLMError, to test fallbacks.
* `calls` records every call, so tests can assert the LLM was NOT used.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any, Callable

from pydantic import ValidationError

from app.llm.client import LLMClient, LLMError, SchemaT

Handler = Callable[[str, str], "str | dict[str, Any]"]


class FakeLLMClient(LLMClient):
    name = "fake"
    model = "fake-llm-v1"

    def __init__(self, handlers: dict[str, Handler] | None = None):
        self.handlers = dict(handlers or {})
        self.calls: list[dict[str, str]] = []
        self._scripted: dict[str, deque] = defaultdict(deque)

    # ---------------------------------------------------------------- test API
    def script(self, task: str, *responses: Any) -> None:
        self._scripted[task].extend(responses)

    def fail(self, task: str, times: int = 1) -> None:
        self._scripted[task].extend([LLMError(f"scripted failure for '{task}'")] * times)

    def calls_for(self, task: str) -> list[dict[str, str]]:
        return [c for c in self.calls if c["task"] == task]

    # ------------------------------------------------------------- LLMClient
    def _respond(self, task: str, system: str, user: str) -> Any:
        self.calls.append({"task": task, "system": system, "user": user})
        if self._scripted[task]:
            response = self._scripted[task].popleft()
            if isinstance(response, Exception):
                raise response
            return response
        handler = self.handlers.get(task)
        if handler is None:
            raise LLMError(f"FakeLLMClient has no handler for task '{task}'")
        return handler(system, user)

    def generate_json(self, *, task: str, system: str, user: str, schema: type[SchemaT]) -> SchemaT:
        raw = self._respond(task, system, user)
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return schema.model_validate(data)
        except (ValidationError, json.JSONDecodeError, TypeError) as error:
            raise LLMError(f"Fake response for '{task}' does not match the schema: {error}") from None

    def generate_text(self, *, task: str, system: str, user: str) -> str:
        raw = self._respond(task, system, user)
        if not isinstance(raw, str):
            raise LLMError(f"Fake response for '{task}' is not text")
        return raw
