"""Logging configuration and formatters for Wishenka application."""

import json
import logging
import sys
from typing import Any

_STANDARD_LOG_RECORD_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
        "taskName",
    }
)


def _extract_extras(record: logging.LogRecord) -> dict[str, Any]:
    """Extract non-standard structured extra fields from a log record."""
    return {
        k: v
        for k, v in record.__dict__.items()
        if k not in _STANDARD_LOG_RECORD_FIELDS and not k.startswith("_")
    }


class JsonFormatter(logging.Formatter):
    """Structured JSON log formatter for production observability."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a structured JSON string."""
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        extras = _extract_extras(record)
        if extras:
            log_data["extra"] = extras

        return json.dumps(log_data, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable text log formatter that preserves structured extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as text, appending structured extra key=value pairs."""
        rendered = super().format(record)
        extras = _extract_extras(record)
        if not extras:
            return rendered

        extra_pairs = " ".join(f"{key}={value}" for key, value in extras.items())
        if "\n" in rendered:
            first_line, rest = rendered.split("\n", 1)
            return f"{first_line} {extra_pairs}\n{rest}"
        return f"{rendered} {extra_pairs}"


def configure_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """Configure application logging handlers and formatters.

    Args:
        log_level: Desired log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_logs: Whether to format logs as JSON lines.
    """
    normalized_level = getattr(logging, log_level.upper(), logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    if json_logs:
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = TextFormatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    for existing_handler in list(root_logger.handlers):
        if type(existing_handler) is logging.StreamHandler:
            root_logger.removeHandler(existing_handler)

    root_logger.addHandler(console_handler)
    root_logger.setLevel(normalized_level)
