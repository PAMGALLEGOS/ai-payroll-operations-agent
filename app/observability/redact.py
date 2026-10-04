"""Make error messages safe to log or print (F1).

Provider errors can echo request details. Before an error message is written
anywhere, known secrets and anything that looks like a Google API key or a
`key=` parameter are masked, and the message is truncated.
"""

from __future__ import annotations

import re
from typing import Iterable

MAX_LENGTH = 300
_GOOGLE_KEY = re.compile(r"AIza[0-9A-Za-z_\-]{10,}")
_KEY_PARAM = re.compile(r"(?i)\b(key|api_key|apikey|x-goog-api-key|token)\s*[=:]\s*['\"]?[^\s'\"&,;]+")


def redact(text: str, secrets: Iterable[str | None] = (), max_length: int = MAX_LENGTH) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    text = _GOOGLE_KEY.sub("***", text)
    text = _KEY_PARAM.sub(lambda m: f"{m.group(1)}=***", text)
    text = " ".join(text.split())
    return text if len(text) <= max_length else text[: max_length - 1] + "…"
