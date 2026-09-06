"""Structured (JSON) logging configuration.

Per docs/architecture/02-non-functional-requirements.md 2.8: structured
logs correlated by a request id. Deliberately dependency-free (a small
custom formatter) rather than pulling in a logging library for something
this small - see engineering rule "do not add unnecessary dependencies".
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime

request_id_ctx_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

_RESERVED_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__)


class JSONLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx_var.get(),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_RECORD_ATTRS
        }
        if extras:
            payload["extra"] = extras
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextLogFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-8s %(name)s [%(request_id)s] %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_ctx_var.get() or "-"
        return super().format(record)


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONLogFormatter() if json_output else TextLogFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # Quiet noisy third-party loggers down to the app's chosen level instead
    # of DEBUG-by-default chatter from libraries.
    for noisy in ("uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(level.upper())
