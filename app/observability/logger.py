"""JSON-lines event logging to stdout and a rotating file (decision D11).

One line per event:

    {"ts": "2026-10-03T21:30:05.120Z", "trace_id": "TRACE-3f9a2c1e", "event": "route_decided",
     "route": "TOOL_RAG", "intent": "validation_explanation", "route_source": "llm_intent"}

stdout is what Cloud Logging collects in GCP (CP5); the file in logs/ is what
`scripts/metrics_report.py` reads locally.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.observability.context import current_trace_id

LOGGER_NAME = "payroll_agent.events"
MAX_BYTES = 5 * 1024 * 1024
BACKUPS = 3


class _JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()


def configure_event_logging(log_file: Path | None, level: str = "INFO", to_stdout: bool = True) -> logging.Logger:
    """(Re)configure the event logger. Safe to call more than once."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(level.upper())
    logger.propagate = False

    if to_stdout:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(_JsonLineFormatter())
        logger.addHandler(stream)
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        rotating = RotatingFileHandler(log_file, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
        rotating.setFormatter(_JsonLineFormatter())
        logger.addHandler(rotating)
    return logger


class JsonEventLogger:
    """AgentObserver that writes each event as one JSON line."""

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(LOGGER_NAME)

    def emit(self, event: str, **fields: Any) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "trace_id": fields.pop("trace_id", None) or current_trace_id(),
            "event": event,
            **fields,
        }
        self.logger.info(json.dumps(record, ensure_ascii=False, default=str))
