"""Observability rules of the gift receipt and notice path (WISHENKA-23, Step 6).

Binding source: ``ai-tasks/WISHENKA-22/50-observability.md`` with the divergences of
``ai-tasks/WISHENKA-23/20-architecture.md`` section 11. The tests read ``caplog`` only; no network.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

import pytest

from tests.notice_support import FakeNoticeSender, send_result
from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OTHER_GIFTER,
    OTHER_GIFTER_ID,
    OWNER,
    OWNER_ID,
    THIRD_GIFTER,
    THIRD_GIFTER_ID,
    app_env,
    bearer,
    open_domain,
    seed_wish,
)
from tests.test_gift_receipt_migration import _create_legacy
from tests.test_receipt_notices import _Env, _store_env
from wishenka.wishlists.exceptions import InventoryBusyError, NothingRemainingError
from wishenka.wishlists.migrations import upgrade_to_head_sync
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(60)

_NOTICE_LOGGER = "wishenka.wishlists.notices"
_ROUTE_LOGGER = "wishenka.web.receipts"
_STANDARD = set(logging.LogRecord("n", 0, "p", 0, "m", (), None).__dict__) | {"message", "asctime"}
_MARKS = ("notification", "outbox", "push")
_PER_ROW_KEYS = {"outbox_id", "attempt", "max_attempts", "error_class"}
_JOIN_KEYS = {"receipt_id", "item_id", "wishlist_id", "event_type", "giver_user_id", "user_id"}
# Booked quantities and names that must not appear anywhere on the owner-side path.
_BOOKED = (37, 41, 53)
_NAMES = ("Greta", "Oleg", "Tina")
_GIVER_IDS = (GIFTER_ID, OTHER_GIFTER_ID, THIRD_GIFTER_ID)


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD}


def _event(record: logging.LogRecord) -> str:
    return str(getattr(record, "event", ""))


def _text(record: logging.LogRecord) -> str:
    return f"{record.getMessage()} {_extras(record)}"


def _events(records: list[logging.LogRecord], name: str) -> list[logging.LogRecord]:
    return [r for r in records if _event(r) == name]


def _receipt_path(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    """Records of the receipt and notice path (own loggers plus ``item_fulfilled``)."""
    return [
        r
        for r in records
        if r.name in {_NOTICE_LOGGER, _ROUTE_LOGGER}
        or _event(r) in {"item_fulfilled", "wish_archived_partial", "wish_restored_partial"}
    ]


class _Clock:
    """Controllable wall clock, safely after the rows were queued with the real clock."""

    def __init__(self) -> None:
        self.now = time.time() + 10

    def __call__(self) -> float:
        return self.now


async def _receipt_and_drain(
    env: _Env, sender: FakeNoticeSender, promises: tuple[Any, ...]
) -> None:
    """Seed booked wishes, record one receipt, drain the worker and flush the window."""
    clock = _Clock()
    await env.seed(200, promises)
    await env.receive(10)
    worker = env.worker(sender, clock)
    await worker.run_once()
    clock.now += 900
    worker.flush_if_due(clock.now)


async def test_receipt_and_worker_run_never_log_giver_or_booking_data(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Never-logged list: no giver, booking number, row-to-receipt join or forbidden word."""
    async with _store_env(tmp_path) as env:
        caplog.set_level(logging.DEBUG)
        await _receipt_and_drain(
            env,
            FakeNoticeSender(),
            ((GIFTER, 37), (OTHER_GIFTER, 41), (THIRD_GIFTER, 53)),
        )

    path = _receipt_path(caplog.records)
    created = _events(path, "receipt_notice_created")
    assert len(created) == 3
    assert [getattr(r, "attempt", None) for r in _events(path, "receipt_notice_sent")] == [1, 1, 1]
    assert [getattr(r, "rows", None) for r in _events(path, "receipt_notice_batch_processed")] == [
        3
    ]
    summary = _events(path, "receipt_notice_window_summary")
    assert len(summary) == 1
    assert summary[0].levelno == logging.INFO
    assert {k: getattr(summary[0], k) for k in ("sent", "retried", "failed_terminal")} == {
        "sent": 3,
        "retried": 0,
        "failed_terminal": 0,
    }
    for record in path:
        text = _text(record)
        for name in _NAMES:
            assert name not in text
        for number in (*_BOOKED, *_GIVER_IDS):
            assert not re.search(rf"\b{number}\b", text), (record.getMessage(), number)
        assert not any(mark in _event(record).lower() for mark in _MARKS)
        assert not any(mark in record.getMessage().lower() for mark in _MARKS)
        keys = set(_extras(record))
        if "outbox_id" in keys:
            assert not keys & _JOIN_KEYS, (_event(record), keys)
        if record.name == _NOTICE_LOGGER:
            assert not keys & _JOIN_KEYS, (_event(record), keys)
        if record.levelno >= logging.INFO and record.name == _NOTICE_LOGGER:
            assert not keys & _PER_ROW_KEYS, (_event(record), keys)


async def test_notice_logger_info_records_are_one_summary_for_any_giver_count(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Per-row events are DEBUG: INFO or above holds one summary whatever the number of givers."""
    counts: list[list[str]] = []
    keys: list[set[str]] = []
    for index, promises in enumerate(
        (((GIFTER, 1),), ((GIFTER, 1), (OTHER_GIFTER, 1), (THIRD_GIFTER, 1)))
    ):
        caplog.clear()
        (tmp_path / f"run{index}").mkdir()
        async with _store_env(tmp_path / f"run{index}") as env:
            caplog.set_level(logging.INFO)
            await _receipt_and_drain(env, FakeNoticeSender(), promises)
        loud = [r for r in caplog.records if r.name == _NOTICE_LOGGER]
        counts.append([_event(r) for r in loud])
        keys.append({k for r in loud for k in _extras(r)})
    assert counts == [["receipt_notice_window_summary"]] * 2
    assert keys[0] == keys[1]


async def test_exception_message_never_logged_only_error_class(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A sender failure logs the class name at DEBUG per row; the message and chat id never."""
    async with _store_env(tmp_path) as env:
        caplog.set_level(logging.DEBUG)
        await _receipt_and_drain(
            env,
            FakeNoticeSender([RuntimeError("secret-detail chat 202")]),
            ((GIFTER, 37),),
        )

    assert "secret-detail" not in " ".join(_text(r) for r in caplog.records)
    failed = _events(caplog.records, "receipt_notice_send_failed")
    assert [(r.levelno, getattr(r, "error_class", None)) for r in failed] == [
        (logging.DEBUG, "RuntimeError")
    ]
    uncertain = _events(caplog.records, "receipt_notice_uncertain")
    assert [r.levelno for r in uncertain] == [logging.DEBUG]
    loud = [r for r in caplog.records if r.name == _NOTICE_LOGGER and r.levelno >= logging.INFO]
    assert [(_event(r), getattr(r, "uncertain", None)) for r in loud] == [
        ("receipt_notice_window_summary", 1)
    ]


async def test_rejected_terminal_counts_only_in_summary_at_info(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A terminal failure is DEBUG per row and ``failed_terminal`` in the INFO aggregate."""
    async with _store_env(tmp_path) as env:
        caplog.set_level(logging.DEBUG)
        await _receipt_and_drain(
            env,
            FakeNoticeSender([send_result("rejected", error_class="TelegramForbiddenError")]),
            ((GIFTER, 37),),
        )

    terminal = _events(caplog.records, "receipt_notice_failed_terminal")
    assert [(r.levelno, getattr(r, "error_class", None)) for r in terminal] == [
        (logging.DEBUG, "TelegramForbiddenError")
    ]
    (summary,) = _events(caplog.records, "receipt_notice_window_summary")
    assert (summary.sent, summary.retried, summary.failed_terminal) == (0, 0, 1)  # type: ignore[attr-defined]


async def test_idle_worker_and_empty_window_write_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """No rows: no record at any level from a poll, a flush over several windows, or a stop."""
    async with _store_env(tmp_path) as env:
        clock = _Clock()
        worker = env.worker(FakeNoticeSender(), clock)
        caplog.set_level(logging.DEBUG)
        caplog.clear()

        assert await worker.run_once() == 0
        clock.now += 3600
        worker.flush_if_due(clock.now)

    assert [r for r in caplog.records if r.name == _NOTICE_LOGGER] == []


def test_refusal_and_busy_records_carry_closed_fields_only(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``receipt_refused`` and ``receipt_inventory_busy``: WARNING, ids, closed reason, no count."""
    with app_env(tmp_path) as (client, sessions, app):
        import asyncio

        service: WishlistService = app.state.domain_service
        wishlist_id, item_id = asyncio.run(seed_wish(service, quantity=5))
        asyncio.run(service.create_reservation(item_id=item_id, user=GIFTER, quantity=2))
        url = f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts"
        owner = bearer(sessions, OWNER_ID)
        caplog.set_level(logging.INFO)

        assert client.post(url, json={"quantity": 9}, headers=owner).status_code == 409
        assert client.post(url, json={"quantity": 0}, headers=owner).status_code == 400
        forbidden = client.post(url, json={"quantity": 1}, headers=bearer(sessions, GIFTER_ID))
        assert forbidden.status_code == 403
        assert client.post(url, json={"quantity": 5}, headers=owner).status_code == 201
        assert client.post(url, json={"quantity": 1}, headers=owner).status_code == 409

        async def busy(*_args: object, **_kwargs: object) -> None:
            raise InventoryBusyError()

        monkeypatch.setattr(app.state.wishlist_store, "execute_wish", busy)
        assert client.post(url, json={"quantity": 1}, headers=owner).status_code == 503

    route = [r for r in caplog.records if r.name == _ROUTE_LOGGER]
    refused = _events(route, "receipt_refused")
    assert [r.levelno for r in refused] == [logging.WARNING] * 4
    by_reason = {_extras(r)["reason"]: r for r in refused}
    assert set(by_reason) == {
        "quantity_above_remaining",
        "quantity_invalid",
        "forbidden",
        "nothing_remaining",
    }
    for reason, record in by_reason.items():
        extras = _extras(record)
        assert extras["wishlist_id"] == wishlist_id
        assert extras["item_id"] == item_id
        assert extras["http_status"] in {400, 403, 409}
        has_remaining = reason in {"quantity_above_remaining", "nothing_remaining"}
        expected_keys = {
            "event",
            "operation",
            "wishlist_id",
            "item_id",
            "actor_id",
            "reason",
            "http_status",
        }
        if has_remaining:
            expected_keys.add("remaining_quantity")
        assert set(extras) == expected_keys, (reason, extras)
    assert by_reason["quantity_above_remaining"].remaining_quantity == 5  # type: ignore[attr-defined]
    assert by_reason["nothing_remaining"].remaining_quantity == 0  # type: ignore[attr-defined]
    assert by_reason["forbidden"].actor_id == GIFTER_ID  # type: ignore[attr-defined]
    assert by_reason["quantity_invalid"].actor_id == OWNER_ID  # type: ignore[attr-defined]

    (busy_record,) = _events(route, "receipt_inventory_busy")
    assert busy_record.levelno == logging.WARNING
    assert (busy_record.wishlist_id, busy_record.item_id) == (wishlist_id, item_id)  # type: ignore[attr-defined]
    assert set(_extras(busy_record)) == {
        "event",
        "operation",
        "wishlist_id",
        "item_id",
        "actor_id",
    }

    accepted = _events(route, "receipt_recorded_http")
    assert [(r.levelno, _extras(r)["item_id"]) for r in accepted] == [(logging.INFO, item_id)]
    fulfilled = _events(caplog.records, "item_fulfilled")
    assert [(r.levelno, _extras(r)["fully_received"]) for r in fulfilled] == [(logging.INFO, True)]
    for record in [*refused, busy_record, *accepted, *fulfilled]:
        assert "Greta" not in _text(record)
        assert "outbox_id" not in _extras(record)


async def test_archive_events_for_partly_received_wish(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Repository archive logs item moves and refuses a wish with nothing left to receive."""
    async with open_domain(tmp_path / "archive-events.db") as service:
        wishlist_id, item_id = await seed_wish(service, quantity=5)
        fresh = await service.add_wish_item(
            wishlist_id=wishlist_id, actor=OWNER, title="Fresh", quantity=2
        )
        fresh_id = fresh.id
        caplog.set_level(logging.INFO)

        await service.archive_wish_item(wishlist_id, fresh_id, OWNER)
        await service.record_item_fulfillment(item_id, OWNER, 2)
        await service.archive_wish_item(wishlist_id, item_id, OWNER)
        await service.restore_wish_item(wishlist_id, item_id, OWNER)
        await service.record_item_fulfillment(item_id, OWNER, 3)
        with pytest.raises(NothingRemainingError):
            await service.archive_wish_item(wishlist_id, item_id, OWNER)
        with pytest.raises(NothingRemainingError):
            await service.restore_wish_item(wishlist_id, item_id, OWNER)

    archived = _events(caplog.records, "item_archived")
    restored = _events(caplog.records, "item_restored")
    assert [r.levelno for r in (*archived, *restored)] == [
        logging.INFO,
        logging.INFO,
        logging.INFO,
    ]
    assert [(r.item_id, r.wishlist_id, r.actor_id) for r in archived] == [  # type: ignore[attr-defined]
        (fresh_id, wishlist_id, OWNER_ID),
        (item_id, wishlist_id, OWNER_ID),
    ]
    assert _extras(restored[0])["item_id"] == item_id
    for record in (*archived, *restored):
        assert "active_reservations_count" not in _extras(record)
    refused = _events(caplog.records, "wish_archive_refused")
    assert [r.levelno for r in refused] == [logging.WARNING, logging.WARNING]
    for record in refused:
        assert _extras(record) == {
            "event": "wish_archive_refused",
            "wishlist_id": wishlist_id,
            "item_id": item_id,
            "actor_id": OWNER_ID,
            "reason": "nothing_remaining",
        }


def test_migration_events_are_info_with_counts_only(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Both legacy migration events are INFO records that carry the row count only."""
    url = _create_legacy(tmp_path / "legacy.db")

    with caplog.at_level(logging.INFO):
        upgrade_to_head_sync(url)

    for event, rows in (("legacy_receipts_backfilled", 3), ("legacy_archived_rows_normalised", 1)):
        (record,) = _events(caplog.records, event)
        assert record.name == "wishenka.wishlists.migrations"
        assert record.levelno == logging.INFO
        assert _extras(record) == {"event": event, "rows": rows}


async def test_retry_scheduled_includes_max_attempts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``receipt_notice_retry_scheduled`` DEBUG record includes ``max_attempts``."""
    async with _store_env(tmp_path) as env:
        caplog.set_level(logging.DEBUG)
        await _receipt_and_drain(
            env,
            FakeNoticeSender([send_result("retryable", error_class="TelegramNetworkError")]),
            ((GIFTER, 37),),
        )

    (retry,) = _events(caplog.records, "receipt_notice_retry_scheduled")
    assert retry.levelno == logging.DEBUG
    assert _extras(retry) == {
        "event": "receipt_notice_retry_scheduled",
        "outbox_id": retry.outbox_id,  # type: ignore[attr-defined]
        "attempt": 1,
        "max_attempts": env.settings.receipt_notice_max_attempts,
        "error_class": "TelegramNetworkError",
    }


async def test_item_archived_never_logs_active_reservations_count(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``item_archived`` on the owner stream must not leak ``active_reservations_count``."""
    async with open_domain(tmp_path / "archive-count.db") as service:
        wishlist_id, item_id = await seed_wish(service, quantity=5)
        await service.create_reservation(item_id=item_id, user=GIFTER, quantity=2)
        caplog.set_level(logging.INFO)
        await service.archive_wish_item(wishlist_id, item_id, OWNER)

    (record,) = _events(caplog.records, "item_archived")
    assert record.levelno == logging.INFO
    assert _extras(record) == {
        "event": "item_archived",
        "item_id": item_id,
        "wishlist_id": wishlist_id,
        "actor_id": OWNER_ID,
    }


async def test_enqueue_failure_rolls_back_without_item_fulfilled_and_logs_operator_error(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outbox enqueue failure rolls back, omits ``item_fulfilled``, and logs operator-only ERROR."""
    from sqlalchemy.ext.asyncio import AsyncConnection

    orig_execute = AsyncConnection.execute

    async def fail_outbox(self: AsyncConnection, statement: Any, *args: Any, **kwargs: Any) -> Any:
        if "INSERT INTO notification_outbox" in str(statement):
            raise RuntimeError("outbox down")
        return await orig_execute(self, statement, *args, **kwargs)

    async with _store_env(tmp_path) as env:
        await env.seed(5, ((GIFTER, 2),))
        monkeypatch.setattr(AsyncConnection, "execute", fail_outbox)
        with (
            caplog.at_level(logging.INFO),
            pytest.raises(RuntimeError, match="outbox down"),
        ):
            await env.receive(1)

    assert _events(caplog.records, "item_fulfilled") == []
    (err,) = _events(caplog.records, "receipt_notice_enqueue_failed")
    assert err.name == _NOTICE_LOGGER
    assert err.levelno == logging.ERROR
    assert _extras(err) == {
        "event": "receipt_notice_enqueue_failed",
        "error_class": "RuntimeError",
    }
    assert not set(_extras(err)) & _JOIN_KEYS


def test_worker_stop_logs_info_without_summary_counts(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Stopping the worker emits ``receipt_notice_worker_stopped`` at INFO without summary."""
    from fastapi.testclient import TestClient

    from tests.receipt_support import TEST_BOT_TOKEN
    from wishenka.config import Settings
    from wishenka.web.app import create_app

    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'stop.db'}",
        secret_key="stop",
        telegram_bot_token=TEST_BOT_TOKEN,
        receipt_notice_enabled=True,
    )
    app = create_app(settings, notice_sender=FakeNoticeSender())
    caplog.set_level(logging.INFO)
    with TestClient(app):
        pass

    (stopped,) = _events(caplog.records, "receipt_notice_worker_stopped")
    assert stopped.name == _NOTICE_LOGGER
    assert stopped.levelno == logging.INFO
    assert _extras(stopped) == {"event": "receipt_notice_worker_stopped"}
    assert _events(caplog.records, "receipt_notice_window_summary") == []
