"""Structured (JSON-lines) logging for the UIC Editorial Assistant backend.

CloudWatch strategy
-------------------
The backend runs on AWS Lambda. Lambda forwards everything written to stdout /
stderr to the function's CloudWatch Logs log group automatically, so we do *not*
ship logs with an SDK handler. Instead every record is emitted as a single line
of JSON on stdout. That gives us:

* zero extra latency / IAM permissions in the request path,
* CloudWatch Logs Insights queries over fields, e.g.::

      fields @timestamp, event, backend, latency_ms
      | filter event = "rag_retrieve"
      | stats avg(latency_ms), pct(latency_ms, 95) by backend

* the same output locally (readable enough, and pipeable through ``jq``).

The intended log group name is the ``UIC_LOG_GROUP`` setting
(default ``/uic-editorial/backend``); infrastructure code should create the
Lambda's log group with that name / retention.

Usage::

    from backend.logging_utils import get_logger
    log = get_logger(__name__)
    log.info("retrieved", extra={"event": "rag_retrieve", "latency_ms": 12, "backend": "local"})

Any key passed via ``extra=`` is copied into the JSON object.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from datetime import datetime, timezone

# Attributes present on every LogRecord; anything else came from `extra=`.
_RESERVED = frozenset(
    vars(logging.LogRecord("x", logging.INFO, "x", 0, "x", None, None)).keys()
) | {"message", "asctime", "taskName"}

_HANDLER_FLAG = "_uic_json_handler"
_handler_lock = threading.Lock()  # check-then-add must be atomic (no duplicate handlers)


class JsonFormatter(logging.Formatter):
    """Format a LogRecord as one line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                # Never let an `extra=` key overwrite the core fields (timestamp/level/logger).
                payload[f"extra_{key}" if key in payload else key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Lambda adds aws_request_id when using its runtime logger; keep it if present.
        return json.dumps(payload, default=str, ensure_ascii=False)


class _StdoutHandler(logging.StreamHandler):
    """StreamHandler that always writes to the *current* ``sys.stdout``.

    Resolving the stream at emit time keeps output visible when stdout is
    swapped (pytest's capsys, Lambda runtime redirection).
    """

    def __init__(self) -> None:
        super().__init__(stream=sys.stdout)

    @property  # type: ignore[override]
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, _value) -> None:  # StreamHandler.__init__ assigns it
        pass


def _level() -> int:
    name = os.environ.get("UIC_LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


def _root_app_logger() -> logging.Logger:
    """The shared ``uic`` parent logger that owns the single stdout handler."""
    root = logging.getLogger("uic")
    with _handler_lock:
        if not any(getattr(h, _HANDLER_FLAG, False) for h in root.handlers):
            handler = _StdoutHandler()
            handler.setFormatter(JsonFormatter())
            setattr(handler, _HANDLER_FLAG, True)
            root.addHandler(handler)
            root.setLevel(_level())
            # Don't double-log through the Python root logger (Lambda installs one).
            root.propagate = False
    return root


def get_logger(name: str) -> logging.Logger:
    """Return a logger that emits single-line JSON to stdout.

    Loggers are namespaced under ``uic.`` so they share one handler and can be
    configured together (``UIC_LOG_LEVEL`` env var, default INFO).
    """
    _root_app_logger()
    return logging.getLogger(f"uic.{name}")
