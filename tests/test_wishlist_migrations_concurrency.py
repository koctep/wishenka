"""Cross-process startup race regression tests for WISHENKA-111."""

import multiprocessing
import sqlite3
from pathlib import Path

import pytest

from wishenka.wishlists.alembic.versions import base_normalized
from wishenka.wishlists.migrations import head_revision, upgrade_to_head_sync

pytestmark = pytest.mark.timeout(120)

_PROCESSES = 4
_TRIALS = 3
_HEAD = head_revision()
_SEED_KEY = "legacy-seed"


def _run_upgrade(url: str) -> str:
    try:
        upgrade_to_head_sync(url)
    except Exception as exc:  # reported to the parent for the assertion
        return f"{type(exc).__name__}: {exc}"
    return "ok"


def _create_legacy(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        for statement in base_normalized.DDL:
            connection.execute(statement)
        connection.execute("INSERT INTO wl_counters VALUES (?, 7)", (_SEED_KEY,))
        connection.commit()
    finally:
        connection.close()


@pytest.mark.parametrize("legacy", [False, True], ids=["fresh", "legacy_base_normalized"])
def test_concurrent_startup_on_shared_database(tmp_path: Path, legacy: bool) -> None:
    context = multiprocessing.get_context("spawn")
    for trial in range(_TRIALS):
        path = tmp_path / f"trial-{trial}.db"
        if legacy:
            _create_legacy(path)
        url = f"sqlite+aiosqlite:///{path}"
        with context.Pool(_PROCESSES) as pool:
            results = pool.map_async(_run_upgrade, [url] * _PROCESSES).get(timeout=90)
        assert results == ["ok"] * _PROCESSES
        connection = sqlite3.connect(path)
        try:
            assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [
                (_HEAD,)
            ]
            if legacy:
                assert connection.execute(
                    "SELECT value FROM wl_counters WHERE name = ?", (_SEED_KEY,)
                ).fetchall() == [(7,)]
            assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        finally:
            connection.close()
