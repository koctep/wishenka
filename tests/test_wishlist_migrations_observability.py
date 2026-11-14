"""Observability tests for wishlist migration structured logging."""

import logging
import sqlite3
from pathlib import Path

import pytest

from tests.test_wishlist_alembic_migrations import _create_legacy_database
from wishenka.wishlists.migrations import upgrade_to_head_sync

pytestmark = pytest.mark.timeout(30)

LOGGER = "wishenka.wishlists.migrations"
EVENTS = {
    "wishlist_migration_started",
    "wishlist_migration_completed",
    "wishlist_migration_failed",
    "wishlist_migration_legacy_schema_adopted",
}


def _events(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) in EVENTS]


def _assert_no_sensitive_data(records: list[logging.LogRecord], db_path: Path) -> None:
    for record in records:
        rendered = " ".join(
            [record.getMessage(), *(str(v) for k, v in vars(record).items() if k == "event")]
        )
        extras = {
            k: v
            for k, v in vars(record).items()
            if k in {"event", "revision", "duration_ms", "db_path", "path", "database_url"}
        }
        assert str(db_path) not in rendered
        assert db_path.name not in rendered
        assert str(db_path) not in str(extras)
        assert "db_path" not in extras and "path" not in extras and "database_url" not in extras
        assert "Seeded legacy wish" not in rendered


def test_fresh_database_logs_started_and_completed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db_path = tmp_path / "fresh.db"
    with caplog.at_level(logging.INFO, logger=LOGGER):
        upgrade_to_head_sync(f"sqlite+aiosqlite:///{db_path}")

    records = _events(caplog)
    names = [r.event for r in records]  # type: ignore[attr-defined]
    assert names == ["wishlist_migration_started", "wishlist_migration_completed"]
    completed = records[1]
    duration = completed.duration_ms  # type: ignore[attr-defined]
    assert isinstance(duration, int)
    assert duration >= 0
    assert all(r.levelno == logging.INFO for r in records)
    _assert_no_sensitive_data(records, db_path)


def test_legacy_database_logs_adoption_with_revision(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db_path = tmp_path / "legacy.db"
    _create_legacy_database(db_path)
    with caplog.at_level(logging.INFO, logger=LOGGER):
        upgrade_to_head_sync(f"sqlite+aiosqlite:///{db_path}")

    records = _events(caplog)
    adopted = [r for r in records if r.event == "wishlist_migration_legacy_schema_adopted"]  # type: ignore[attr-defined]
    assert len(adopted) == 1
    revision = adopted[0].revision  # type: ignore[attr-defined]
    assert revision in {
        "base_normalized",
        "add_warn_on_delete_reserved",
        "add_display_order",
        "add_item_order_index",
    }
    assert revision in adopted[0].getMessage()
    assert [r.event for r in records][0] == "wishlist_migration_started"  # type: ignore[attr-defined]
    assert [r.event for r in records][-1] == "wishlist_migration_completed"  # type: ignore[attr-defined]
    _assert_no_sensitive_data(records, db_path)


def test_unsupported_schema_logs_failure_and_reraises(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db_path = tmp_path / "unsupported.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE wl_lists (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()

    with (
        caplog.at_level(logging.INFO, logger=LOGGER),
        pytest.raises(RuntimeError, match="Unsupported wishlist database schema"),
    ):
        upgrade_to_head_sync(f"sqlite+aiosqlite:///{db_path}")

    records = _events(caplog)
    names = [r.event for r in records]  # type: ignore[attr-defined]
    assert names == ["wishlist_migration_started", "wishlist_migration_failed"]
    failed = records[1]
    assert failed.levelno == logging.ERROR
    assert failed.exc_info is not None
    assert failed.exc_info[0] is RuntimeError
    assert "wishlist_migration_legacy_schema_adopted" not in names
    assert "wishlist_migration_completed" not in names
    _assert_no_sensitive_data(records, db_path)
