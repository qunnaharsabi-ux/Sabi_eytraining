"""
monitoring/logger.py
--------------------
structlog-based structured logging.

  * JSON lines (machine-parseable by Loki / Datadog / CloudWatch)
  * run_id bound via contextvars -> every line carries it automatically
  * secrets (api_key / token / secret) redacted before write
  * per-run file logs/run_<id>.jsonl + global logs/fiaa.jsonl
  * coloured console renderer in dev, pure JSON in prod
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import structlog

from configs.settings import settings

_REDACT_KEYS = ("api_key", "apikey", "token", "secret", "password", "authorization")
_REDACTED = "***REDACTED***"


def _redact_secrets(_logger, _method, event: Dict[str, Any]) -> Dict[str, Any]:
    for k in list(event.keys()):
        lk = k.lower()
        if any(s in lk for s in _REDACT_KEYS) and isinstance(event[k], str):
            event[k] = _REDACTED
    return event


def _configure() -> None:
    Path(settings.logs_dir).mkdir(parents=True, exist_ok=True)
    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _redact_secrets,
    ]
    if settings.env == "prod":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


_configure()

# A second, file-only JSON logger used to persist every event to disk.
_file_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    _redact_secrets,
    structlog.processors.JSONRenderer(),
]


def get_logger(name: str = "fiaa"):
    return structlog.get_logger(name)


def bind_run(run_id: str, **extra) -> None:
    """Bind a run_id (and optional fields) to every subsequent log line."""
    structlog.contextvars.bind_contextvars(run_id=run_id, **extra)


def clear_run() -> None:
    structlog.contextvars.clear_contextvars()


def write_run_event(run_id: str, event: Dict[str, Any]) -> None:
    """Append one JSON line to both the per-run file and the global file."""
    import json
    import datetime as _dt

    record = {"timestamp": _dt.datetime.utcnow().isoformat() + "Z", "run_id": run_id, **event}
    for k in list(record.keys()):
        if any(s in k.lower() for s in _REDACT_KEYS) and isinstance(record[k], str):
            record[k] = _REDACTED
    line = json.dumps(record, default=str)
    logs = Path(settings.logs_dir)
    try:
        with open(logs / f"run_{run_id}.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
        with open(logs / "fiaa.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


log = get_logger()
