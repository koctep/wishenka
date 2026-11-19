"""Red failing-repro tests for wishlist migration rollback policy (WISHENKA-128)."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.test_wishlist_alembic_migrations import _create_legacy_database
from wishenka.wishlists.migrations import _configured, upgrade_to_head_sync
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(10)

_MIGRATIONS_LOGGER = "wishenka.wishlists.migrations"
_EXPECTED_ONE_WAY = {
    "base_normalized",
    "add_warn_on_delete_reserved",
    "add_display_order",
    "add_gift_receipts",
}


def _alembic_config(db_path: Path) -> Config:
    """Build an Alembic Config targeting ``db_path``."""
    return _configured(f"sqlite+aiosqlite:///{db_path}")


def test_all_revisions_declare_valid_rollback_policy() -> None:
    """Every revision in ScriptDirectory must declare a valid ROLLBACK_POLICY."""
    scripts = ScriptDirectory.from_config(_configured("sqlite+aiosqlite:///:memory:"))
    revisions = list(scripts.walk_revisions())
    assert revisions, "Expected at least one Alembic revision"

    policies: dict[str, str | None] = {}
    for rev in revisions:
        policy = getattr(rev.module, "ROLLBACK_POLICY", None)
        assert policy in {"reversible", "one-way"}, (
            f"Revision {rev.revision} must define ROLLBACK_POLICY in {{'reversible', 'one-way'}}, "
            f"got {policy!r}"
        )
        policies[rev.revision] = policy

    for rev_id in _EXPECTED_ONE_WAY:
        assert policies.get(rev_id) == "one-way"


def test_baseline_downgrade_is_guarded_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Downgrading base_normalized without opt-in refuses and preserves core data."""
    monkeypatch.delenv("WISHENKA_ALLOW_DESTRUCTIVE_BASELINE_DOWNGRADE", raising=False)
    db_path = tmp_path / "baseline.db"
    cfg = _alembic_config(db_path)

    command.upgrade(cfg, "base_normalized")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO wl_lists (id, owner_id, title, public_token, invite_token, created_at, "
            "updated_at) VALUES (1, 42, 'Protected list', 'pub-1', 'inv-1', 'now', 'now')"
        )
        conn.commit()
    finally:
        conn.close()

    with (
        caplog.at_level(logging.WARNING, logger=_MIGRATIONS_LOGGER),
        pytest.raises(NotImplementedError, match="(?i)backup"),
    ):
        command.downgrade(cfg, "base")

    assert any(
        getattr(r, "event", None) == "wishlist_migration_downgrade_refused"
        and getattr(r, "revision", None) == "base_normalized"
        and r.levelno == logging.WARNING
        for r in caplog.records
    )

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT id, title FROM wl_lists").fetchall()
    finally:
        conn.close()
    assert rows == [(1, "Protected list")]


def test_baseline_downgrade_succeeds_with_explicit_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Downgrading base_normalized with opt-in env var drops baseline tables."""
    monkeypatch.setenv("WISHENKA_ALLOW_DESTRUCTIVE_BASELINE_DOWNGRADE", "1")
    db_path = tmp_path / "baseline_opt_in.db"
    cfg = _alembic_config(db_path)

    command.upgrade(cfg, "base_normalized")
    with caplog.at_level(logging.WARNING, logger=_MIGRATIONS_LOGGER):
        command.downgrade(cfg, "base")

    assert any(
        getattr(r, "event", None) == "wishlist_migration_destructive_baseline_downgrade"
        for r in caplog.records
    )
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    finally:
        conn.close()
    assert "wl_lists" not in tables


@pytest.mark.parametrize(
    ("revision", "target_down"),
    [
        ("add_warn_on_delete_reserved", "base_normalized"),
        ("add_display_order", "add_warn_on_delete_reserved"),
        ("add_gift_receipts", "add_item_order_index"),
    ],
)
def test_one_way_revisions_refuse_downgrade_with_backup_guidance(
    tmp_path: Path, revision: str, target_down: str, caplog: pytest.LogCaptureFixture
) -> None:
    """One-way revisions refuse downgrade with a clear backup-restoration message."""
    db_path = tmp_path / f"{revision}.db"
    cfg = _alembic_config(db_path)
    command.upgrade(cfg, revision)

    with (
        caplog.at_level(logging.WARNING, logger=_MIGRATIONS_LOGGER),
        pytest.raises(NotImplementedError, match="(?i)backup"),
    ):
        command.downgrade(cfg, target_down)

    assert any(
        getattr(r, "event", None) == "wishlist_migration_downgrade_refused"
        and getattr(r, "revision", None) == revision
        and r.levelno == logging.WARNING
        for r in caplog.records
    )


def test_reversible_tail_downgrades_cleanly_to_gift_receipts(tmp_path: Path) -> None:
    """All reversible revisions from head down to add_gift_receipts downgrade cleanly."""
    db_path = tmp_path / "reversible_tail.db"
    cfg = _alembic_config(db_path)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, "add_gift_receipts")

    conn = sqlite3.connect(db_path)
    try:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        conn.close()
    assert version == ("add_gift_receipts",)


def test_repeated_startup_is_idempotent(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Second upgrade_to_head_sync on a legacy DB is a no-op and does not re-adopt."""
    db_path = tmp_path / "legacy_idempotent.db"
    _create_legacy_database(db_path)
    url = f"sqlite+aiosqlite:///{db_path}"

    with caplog.at_level(logging.INFO, logger=_MIGRATIONS_LOGGER):
        upgrade_to_head_sync(url)
        upgrade_to_head_sync(url)

    adopted_events = [
        r
        for r in caplog.records
        if getattr(r, "event", None) == "wishlist_migration_legacy_schema_adopted"
    ]
    assert len(adopted_events) == 1

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT id, title FROM wl_lists").fetchall()
    finally:
        conn.close()
    assert rows == [(1, "Legacy wishes")]


@pytest.mark.parametrize(
    "bad_url",
    [
        "postgresql+asyncpg://user:pass@localhost/wishenka",
        "mysql+aiomysql://localhost/wishenka",
    ],
)
def test_non_sqlite_urls_are_rejected(bad_url: str) -> None:
    """Both WishlistStore and upgrade_to_head_sync reject non-SQLite URLs."""
    with pytest.raises(ValueError, match="SQLite"):
        WishlistStore(bad_url)

    with pytest.raises(ValueError, match="SQLite"):
        upgrade_to_head_sync(bad_url)


def test_offline_sql_generation_emits_ddl_without_creating_db(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Offline mode emits CREATE TABLE DDL to stdout without touching a database file."""
    db_path = tmp_path / "should_not_exist.db"
    cfg = _alembic_config(db_path)

    command.upgrade(cfg, "head", sql=True)

    sql_output = capsys.readouterr().out
    assert "CREATE TABLE wl_lists" in sql_output
    assert "wl_receipts" in sql_output
    assert not db_path.exists()
