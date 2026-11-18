"""Observability tests for WISHENKA-160 (modal error structured logging)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.receipt_support import (
    OWNER,
    OWNER_ID,
    AppEnv,
    app_env,
    bearer,
    seed_wish,
)
from wishenka.wishlists.exceptions import InventoryBusyError

pytestmark = pytest.mark.timeout(30)

_LOGGER_NAME = "wishenka.web.items_ui"


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[AppEnv]:
    """Provide an isolated application with a real SQLite store."""
    with app_env(tmp_path) as env:
        yield env


def _events(caplog: pytest.LogCaptureFixture, event_name: str) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.name == _LOGGER_NAME and getattr(r, "event", None) == event_name
    ]


def test_edit_validation_error_logs_structured_warning_without_payload(
    test_app: AppEnv,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Edit 400 validation failure logs ui_item_edit_validation_error without user strings."""
    client, sessions, app = test_app
    wishlist_id, item_id = asyncio.run(seed_wish(app.state.domain_service, quantity=2))
    secret_price = "not-a-number-secret-999"

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        resp = client.post(
            f"/web/wishlists/{wishlist_id}/items/{item_id}/edit",
            headers=bearer(sessions, OWNER_ID),
            data={"title": "Valid Title", "price": secret_price, "quantity": "2"},
        )

    assert resp.status_code == 400
    records = _events(caplog, "ui_item_edit_validation_error")
    assert len(records) == 1
    rec = records[0]
    assert rec.levelno == logging.WARNING
    assert getattr(rec, "stage", None) == "form"
    assert getattr(rec, "status_code", None) == 400
    assert getattr(rec, "wishlist_id", None) == wishlist_id
    assert getattr(rec, "item_id", None) == item_id
    assert getattr(rec, "actor_id", None) == OWNER_ID
    assert secret_price not in caplog.text
    assert "Valid Title" not in caplog.text


def test_quick_add_validation_error_logs_structured_warning(
    test_app: AppEnv,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Quick-add 400 validation failure logs ui_item_quick_add_validation_error."""
    client, sessions, app = test_app
    wishlist_id, _ = asyncio.run(seed_wish(app.state.domain_service, quantity=1))

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        resp = client.post(
            f"/web/wishlists/{wishlist_id}/items/quick",
            headers=bearer(sessions, OWNER_ID),
            data={"raw_input": "   "},
        )

    assert resp.status_code == 400
    records = _events(caplog, "ui_item_quick_add_validation_error")
    assert len(records) == 1
    rec = records[0]
    assert rec.levelno == logging.WARNING
    assert getattr(rec, "reason", None) == "empty_title"
    assert getattr(rec, "status_code", None) == 400
    assert getattr(rec, "wishlist_id", None) == wishlist_id
    assert getattr(rec, "actor_id", None) == OWNER_ID


def test_modal_domain_errors_log_structured_warning(
    test_app: AppEnv,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Archived (409) and missing-item (404) modal actions log ui_modal_domain_error."""
    client, sessions, app = test_app
    wishlist_id, item_id = asyncio.run(seed_wish(app.state.domain_service, quantity=1))

    # 404 on missing item
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        resp_404 = client.post(
            f"/web/wishlists/{wishlist_id}/items/999999/archive",
            headers=bearer(sessions, OWNER_ID),
        )
    assert resp_404.status_code == 404
    recs_404 = _events(caplog, "ui_modal_domain_error")
    assert len(recs_404) == 1
    assert getattr(recs_404[0], "operation", None) == "archive_item"
    assert getattr(recs_404[0], "error_type", None) == "ItemNotFoundError"
    assert getattr(recs_404[0], "status_code", None) == 404
    assert getattr(recs_404[0], "wishlist_id", None) == wishlist_id
    assert getattr(recs_404[0], "item_id", None) == 999999
    assert getattr(recs_404[0], "actor_id", None) == OWNER_ID

    # Archive wishlist -> 409 on edit submit
    asyncio.run(app.state.domain_service.archive_wishlist(wishlist_id, OWNER))
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        resp_409 = client.post(
            f"/web/wishlists/{wishlist_id}/items/{item_id}/edit",
            headers=bearer(sessions, OWNER_ID),
            data={"title": "Updated", "quantity": "1"},
        )
    assert resp_409.status_code == 409
    recs_409 = _events(caplog, "ui_modal_domain_error")
    assert len(recs_409) == 1
    assert getattr(recs_409[0], "operation", None) == "submit_edit_item"
    assert getattr(recs_409[0], "error_type", None) == "WishlistArchivedError"
    assert getattr(recs_409[0], "status_code", None) == 409
    assert getattr(recs_409[0], "wishlist_id", None) == wishlist_id
    assert getattr(recs_409[0], "item_id", None) == item_id


def test_edit_busy_logs_structured_warning(
    test_app: AppEnv,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """InventoryBusyError (503) on edit submit logs ui_item_edit_busy."""
    client, sessions, app = test_app
    wishlist_id, item_id = asyncio.run(seed_wish(app.state.domain_service, quantity=1))

    async def busy(*_args: object, **_kwargs: object) -> None:
        raise InventoryBusyError()

    monkeypatch.setattr(app.state.wishlist_store, "execute_wish", busy)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        resp = client.post(
            f"/web/wishlists/{wishlist_id}/items/{item_id}/edit",
            headers=bearer(sessions, OWNER_ID),
            data={"title": "Updated", "quantity": "1"},
        )

    assert resp.status_code == 503
    records = _events(caplog, "ui_item_edit_busy")
    assert len(records) == 1
    assert getattr(records[0], "wishlist_id", None) == wishlist_id
    assert getattr(records[0], "item_id", None) == item_id
