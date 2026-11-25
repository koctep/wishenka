"""Tests for logging configuration and observability middleware."""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from wishenka.config import Settings
from wishenka.logging import JsonFormatter, TextFormatter, configure_logging
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(10)


def test_json_formatter() -> None:
    """JsonFormatter must output valid JSON with timestamp, level, message, and extras."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test message with extra",
        args=(),
        exc_info=None,
    )
    record.__dict__["request_id"] = "req-12345"

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["logger"] == "test_logger"
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Test message with extra"
    assert "timestamp" in parsed
    assert parsed["extra"]["request_id"] == "req-12345"


def test_configure_logging() -> None:
    """configure_logging must set root logger level and attach handler."""
    configure_logging(log_level="DEBUG", json_logs=False)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) > 0


def test_text_formatter_preserves_extras() -> None:
    """TextFormatter must append structured extra key=value pairs when present."""
    formatter = TextFormatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test message with extra",
        args=(),
        exc_info=None,
    )
    record.__dict__["event"] = "share_access_revoked"
    record.__dict__["wishlist_id"] = 42

    output = formatter.format(record)
    assert "[INFO] test_logger: Test message with extra" in output
    assert "event=share_access_revoked" in output
    assert "wishlist_id=42" in output


def test_request_logging_and_lifespan(caplog: pytest.LogCaptureFixture) -> None:
    """Lifespan events and request logging middleware must emit structured logs."""
    settings = Settings(log_level="DEBUG")
    app = create_app(settings)

    with caplog.at_level(logging.DEBUG), TestClient(app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200

    messages = [r.getMessage() for r in caplog.records]
    assert any("Wishenka web application starting up" in msg for msg in messages)
    assert any("Healthcheck endpoint probed" in msg for msg in messages)
    assert any("HTTP request completed" in msg for msg in messages)
    assert any("Wishenka web application shutting down" in msg for msg in messages)
