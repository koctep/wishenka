"""Contract for the unavailable-page render event (WISHENKA-294)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from tests.receipt_support import app_env
from wishenka.logging import JsonFormatter

pytestmark = pytest.mark.timeout(30)

EVENT = "unavailable_page_rendered"
HTML = {"Accept": "text/html"}
SECRET_TOKEN = "SecretShareTokenValue123"
SECRET_ID = "987654"


def _extra(record: logging.LogRecord) -> dict[str, object]:
    extra: dict[str, object] = json.loads(JsonFormatter().format(record))["extra"]
    return extra


def _events(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) == EVENT]


def test_html_unavailable_pages_log_one_safe_event(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Each HTML render emits one INFO event with kind/status/locale and no identifiers."""
    with (
        app_env(tmp_path, "unavailable-obs.db") as (client, _sessions, _app),
        caplog.at_level(logging.INFO, logger="wishenka.web"),
    ):
        calls = [
            client.get(f"/share/{SECRET_TOKEN}", headers=HTML),
            client.get(f"/web/wishlists/{SECRET_ID}", headers=HTML),
            client.get("/web/reservations", headers=HTML),
        ]
    assert [c.status_code for c in calls] == [404, 404, 401]
    records = _events(caplog)
    assert [(_extra(r)["route_kind"], _extra(r)["status_code"]) for r in records] == [
        ("share", 404),
        ("wishlist", 404),
        ("reservations", 401),
    ]
    formatter = JsonFormatter()
    for record in records:
        assert record.levelno == logging.INFO
        line = formatter.format(record)
        assert json.loads(line)["extra"]["event"] == EVENT
        assert SECRET_TOKEN not in line
        assert SECRET_ID not in line


def test_json_clients_do_not_emit_the_event(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """JSON, wildcard and htmx clients keep the plain error without the render event."""
    with (
        app_env(tmp_path, "unavailable-obs-json.db") as (client, _sessions, _app),
        caplog.at_level(logging.INFO, logger="wishenka.web"),
    ):
        calls = [
            client.get(f"/share/{SECRET_TOKEN}", headers={"Accept": "application/json"}),
            client.get(f"/share/{SECRET_TOKEN}"),
            client.get("/web/reservations", headers={**HTML, "HX-Request": "true"}),
            client.get("/api/profile", headers=HTML),
        ]
    assert all(c.status_code in (401, 404) for c in calls)
    assert _events(caplog) == []
