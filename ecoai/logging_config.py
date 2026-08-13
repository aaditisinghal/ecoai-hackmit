"""Application logging.

Replaces the ``print()`` calls the previous implementation used for errors.
Everything goes to stdout, which is what Heroku, Docker and systemd all
expect; ``LOG_FORMAT=json`` emits one JSON object per line for log shippers.
"""

from __future__ import annotations

import json
import logging
import sys
from logging.config import dictConfig
from typing import Any

_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"asctime", "message", "taskName"}


class JsonFormatter(logging.Formatter):
    """Serialize records as single-line JSON, preserving ``extra`` fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    formatter = (
        {"()": JsonFormatter}
        if fmt == "json"
        else {"format": "%(asctime)s %(levelname)-8s %(name)s: %(message)s"}
    )

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": formatter},
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": sys.stdout,
                }
            },
            "root": {"level": level, "handlers": ["stdout"]},
            "loggers": {
                # Access logs are gunicorn's job; Werkzeug duplicates them.
                "werkzeug": {"level": "WARNING", "handlers": ["stdout"], "propagate": False},
                "ecoai": {"level": level, "handlers": ["stdout"], "propagate": False},
            },
        }
    )
