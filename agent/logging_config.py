"""Logging estruturado em JSON — formato amigavel ao Cloud Logging.

O Cloud Logging captura stdout automaticamente. Emitindo JSON com a chave
`severity`, o Cloud Logging classifica o nivel corretamente sem config extra.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from agent.config import get_settings


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "severity": record.levelname,
            "time": datetime.now(timezone.utc).isoformat(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Campos extras passados via logger.info(..., extra={"fields": {...}})
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(get_settings().log_level.upper())
    _configured = True


def get_logger(name: str) -> logging.LoggerAdapter:
    setup_logging()
    return logging.LoggerAdapter(logging.getLogger(name), {})
