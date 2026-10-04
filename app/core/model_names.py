"""Fail-fast check of Gemini model names (QA fix F6b).

A malformed value (for example `GEMINI_MODEL=GEMINI_MODEL=gemini-3.8-flash`, a
stray space or quotes) used to reach Gemini, fail with 400/404 and end in a
silent deterministic fallback. Now the Gemini providers refuse it at start-up
with a clear message. Values are never corrected silently: a wrong
configuration must be visible, not "fixed" behind the user's back.
"""

from __future__ import annotations

import re

MODEL_NAME = re.compile(r"^(models/)?[A-Za-z0-9][A-Za-z0-9._-]*$")


def model_name_problem(variable: str, value: str, example: str) -> str | None:
    """None when the name is well-formed, otherwise a message for the operator."""
    if MODEL_NAME.fullmatch(value):
        return None
    return (f"{variable} has an invalid format: {value!r}. Expected only the model name, "
            f"for example {variable}={example} (check .env and any system/terminal variable "
            f"with the same name, which takes precedence over .env)")
