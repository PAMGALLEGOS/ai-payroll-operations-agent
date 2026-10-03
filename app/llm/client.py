"""LLM client interface.

Every call names a `task` ("intent", "rag_answer", "tool_rag_explain"). The task
does not change how a real provider behaves; it lets the fake client answer
each job differently and lets tests and traces see which job was performed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMError(RuntimeError):
    """The LLM call failed or returned output that does not satisfy the contract."""


class LLMConfigError(LLMError):
    """The LLM client cannot be created with the current settings."""


class LLMClient(ABC):
    name: str
    model: str

    @abstractmethod
    def generate_json(self, *, task: str, system: str, user: str, schema: type[SchemaT]) -> SchemaT:
        """Return output validated against `schema`, or raise LLMError."""

    @abstractmethod
    def generate_text(self, *, task: str, system: str, user: str) -> str:
        """Return free text, or raise LLMError."""
