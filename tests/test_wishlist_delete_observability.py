"""Pin production logs of the owner wishlist delete flow (WISHENKA-295, Step 6, D-7).

Every path of ``DELETE /api/wishlists/{id}`` must leave a diagnosable server-side signal without
leaking the list title, tokens, reservation data or the gifter, and without making a non-owner
attempt look different to the client than an unknown id.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.test_wishlist_delete_api import (
    ADMIN_ID,
    GIFTER_ID,
    OWNER,
    OWNER_ID,
    STRANGER_ID,
    UNKNOWN_ID,
    Env,
    _add_item,
    _create,
    _delete,
    _open_app,
    _reserve,
    _run_shared,
    _share,
)
from wishenka.logging import JsonFormatter
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

TITLE = "ZzSecretTitleQq"
ITEM_TITLE = "ZzSecretItemQq"
GIFTER_NAME = "Giver"
DELETE_EVENTS = {
    "wishlist_deleted_by_owner",
    "wishlist_delete_not_found",
    "wishlist_delete_denied",
    "wishlist_status_changed",
    "wishlist_mutation_committed",
    "wishlist_permission_denied",
    "wishlist_retention_expired",
    "wishlist_archived_mutation_blocked",
}
FORBIDDEN_FIELDS = {
    "title",
    "share_token",
    "invite_token",
    "reservation_id",
    "reservations",
    "gifter_id",
    "item_id",
}


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    """Application on its own database with the delete-flow users."""
    with _open_app(tmp_path / "delete-observability.db") as opened:
        yield opened


def _events(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) in DELETE_EVENTS]


def _named(caplog: pytest.LogCaptureFixture, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event", None) == event]


def _assert_none(caplog: pytest.LogCaptureFixture, *events: str) -> None:
    """Events that must not appear on this path."""
    for event in events:
        assert not _named(caplog, event), event


def _scan(value: object) -> Iterator[object]:
    """Yield every leaf of a nested JSON value."""
    if isinstance(value, dict):
        for item in value.values():
            yield from _scan(item)
    elif isinstance(value, list):
        for item in value:
            yield from _scan(item)
    else:
        yield value


def _assert_no_leak(caplog: pytest.LogCaptureFixture, env: Env, wishlist: dict[str, str]) -> None:
    """No captured record (message, extras, JSON line) carries titles, tokens or the gifter."""
    secrets = [TITLE, ITEM_TITLE, GIFTER_NAME, wishlist["share_token"], wishlist["invite_token"]]
    formatter = JsonFormatter()
    for record in caplog.records:
        line = formatter.format(record)
        rendered = f"{record.getMessage()} {line} {vars(record)}"
        for secret in secrets:
            assert secret not in rendered, f"{record.getMessage()!r} leaks {secret!r}"
        assert not (FORBIDDEN_FIELDS & set(vars(record))), record.getMessage()
        payload = json.loads(line)
        extra = {k: v for k, v in payload.get("extra", {}).items() if k != "status_code"}
        for leaf in _scan(extra):
            assert not (isinstance(leaf, int) and leaf == GIFTER_ID), record.getMessage()
        assert GIFTER_ID not in [a for a in (record.args or ()) if isinstance(a, int)]
        assert not re.search(rf"(?<![\d.,:-]){GIFTER_ID}(?![\d.,:-])", record.getMessage())


def test_success_logs_committed_status_change_and_owner_event(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    created = _create(env, TITLE)
    _reserve(env, _add_item(env, created["id"], ITEM_TITLE), purchased=True)

    with caplog.at_level(logging.INFO, logger="wishenka"):
        caplog.clear()
        assert _delete(env, created["id"]).status_code == 200

    owner_events = _named(caplog, "wishlist_deleted_by_owner")
    assert len(owner_events) == 1
    record = owner_events[0]
    assert record.levelno == logging.INFO
    assert record.__dict__["wishlist_id"] == created["id"]
    assert record.__dict__["user_id"] == OWNER_ID
    assert record.__dict__["retention_days"] == 30
    assert record.__dict__["outcome"] == "deleted"
    changed = _named(caplog, "wishlist_status_changed")
    assert [(r.__dict__["from_status"], r.__dict__["to_status"]) for r in changed] == [
        ("active", "deleted")
    ]
    assert changed[0].__dict__["actor_id"] == OWNER_ID
    committed = _named(caplog, "wishlist_mutation_committed")
    assert [r.__dict__["operation"] for r in committed] == ["delete_wishlist"]
    assert not _named(caplog, "wishlist_delete_denied")
    assert not _named(caplog, "wishlist_delete_not_found")
    assert all(r.levelno < logging.WARNING for r in _events(caplog))
    _assert_no_leak(caplog, env, created)


def test_repeat_delete_logs_already_deleted_without_second_status_change(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    created = _create(env, TITLE)
    assert _delete(env, created["id"]).status_code == 200

    with caplog.at_level(logging.INFO, logger="wishenka"):
        caplog.clear()
        assert _delete(env, created["id"]).status_code == 200

    owner_events = _named(caplog, "wishlist_deleted_by_owner")
    _assert_none(caplog, "wishlist_delete_denied", "wishlist_delete_not_found")
    assert [r.__dict__["outcome"] for r in owner_events] == ["already_deleted"]
    assert owner_events[0].levelno == logging.INFO
    assert not _named(caplog, "wishlist_status_changed")
    _assert_no_leak(caplog, env, created)


def test_unknown_id_logs_not_found_warning_with_ids_only(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    created = _create(env, TITLE)

    with caplog.at_level(logging.INFO, logger="wishenka"):
        caplog.clear()
        assert _delete(env, UNKNOWN_ID).status_code == 404

    found = _named(caplog, "wishlist_delete_not_found")
    assert len(found) == 1
    assert found[0].levelno == logging.WARNING
    assert found[0].__dict__["wishlist_id"] == UNKNOWN_ID
    assert found[0].__dict__["user_id"] == OWNER_ID
    assert not _named(caplog, "wishlist_deleted_by_owner")
    _assert_none(caplog, "wishlist_delete_denied")
    assert not _named(caplog, "wishlist_mutation_committed")
    _assert_no_leak(caplog, env, created)


@pytest.mark.parametrize("caller", [ADMIN_ID, STRANGER_ID])
def test_non_owner_attempt_is_logged_server_side_but_looks_unknown_to_client(
    env: Env, caplog: pytest.LogCaptureFixture, caller: int
) -> None:
    created = _create(env, TITLE)
    _share(env, created)
    _reserve(env, _add_item(env, created["id"], ITEM_TITLE), purchased=False)

    with caplog.at_level(logging.INFO, logger="wishenka"):
        caplog.clear()
        denied = _delete(env, created["id"], caller)
        unknown = _delete(env, UNKNOWN_ID, caller)

    assert denied.status_code == unknown.status_code == 404
    assert denied.content == unknown.content
    assert dict(denied.headers).keys() == dict(unknown.headers).keys()
    rejected = _named(caplog, "wishlist_delete_denied")
    assert len(rejected) == 1
    assert rejected[0].levelno == logging.WARNING
    assert rejected[0].__dict__["wishlist_id"] == created["id"]
    assert rejected[0].__dict__["user_id"] == caller
    permission = _named(caplog, "wishlist_permission_denied")
    assert [r.__dict__["operation"] for r in permission] == ["delete_wishlist"]
    assert permission[0].levelno == logging.WARNING
    # Nothing mutated, nothing reported as deleted.
    assert not _named(caplog, "wishlist_deleted_by_owner")
    assert [r.__dict__["wishlist_id"] for r in _named(caplog, "wishlist_delete_not_found")] == [
        UNKNOWN_ID
    ]
    assert not _named(caplog, "wishlist_status_changed")
    assert not _named(caplog, "wishlist_mutation_committed")
    _assert_no_leak(caplog, env, created)


def test_archived_list_logs_blocked_warning_and_no_success_events(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    created = _create(env, TITLE)

    async def archive(service: WishlistService) -> None:
        await service.archive_wishlist(created["id"], OWNER)

    _run_shared(env, archive)

    with caplog.at_level(logging.INFO, logger="wishenka"):
        caplog.clear()
        assert _delete(env, created["id"]).status_code == 409

    blocked = _named(caplog, "wishlist_archived_mutation_blocked")
    assert [r.__dict__["operation"] for r in blocked] == ["delete_wishlist"]
    assert blocked[0].levelno == logging.WARNING
    assert not _named(caplog, "wishlist_deleted_by_owner")
    _assert_none(caplog, "wishlist_delete_denied", "wishlist_delete_not_found")
    assert not _named(caplog, "wishlist_status_changed")
    assert not _named(caplog, "wishlist_mutation_committed")
    _assert_no_leak(caplog, env, created)


def test_expired_retention_logs_warning_and_no_success_events(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db_path = tmp_path / "observability-window.db"
    with _open_app(db_path) as first:
        created = _create(first, TITLE)

        async def delete(service: WishlistService) -> None:
            await service.delete_wishlist(created["id"], OWNER)

        _run_shared(first, delete)
    expired = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE wl_lists SET updated_at = ? WHERE id = ?", (expired, created["id"]))
        conn.commit()

    with _open_app(db_path) as second, caplog.at_level(logging.INFO, logger="wishenka"):
        caplog.clear()
        assert _delete(second, created["id"]).status_code == 410

        gone = _named(caplog, "wishlist_retention_expired")
        assert [r.__dict__["operation"] for r in gone] == ["delete_wishlist"]
        assert gone[0].levelno == logging.WARNING
        assert not _named(caplog, "wishlist_deleted_by_owner")
        _assert_none(caplog, "wishlist_delete_denied", "wishlist_delete_not_found")
        assert not _named(caplog, "wishlist_status_changed")
        assert not _named(caplog, "wishlist_mutation_committed")
        _assert_no_leak(caplog, second, created)


def test_unexpected_error_is_logged_by_request_middleware_without_title(
    env: Env, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _create(env, TITLE)

    async def boom(self: WishlistService, wishlist_id: int, actor: object) -> None:
        raise RuntimeError("storage failure")

    from wishenka.wishlists.repo_ops import RepoWishlistOps

    monkeypatch.setattr(WishlistService, "delete_wishlist", boom)
    monkeypatch.setattr(RepoWishlistOps, "delete_wishlist", boom)

    with caplog.at_level(logging.INFO, logger="wishenka"):
        caplog.clear()
        with pytest.raises(RuntimeError, match="storage failure"):
            _delete(env, created["id"])

    failed = [r for r in caplog.records if "unhandled exception" in r.getMessage()]
    assert len(failed) == 1
    assert failed[0].levelno == logging.ERROR
    assert failed[0].__dict__["path"] == f"/api/wishlists/{created['id']}"
    assert not _named(caplog, "wishlist_deleted_by_owner")
    _assert_none(caplog, "wishlist_delete_denied", "wishlist_delete_not_found")
    assert not _named(caplog, "wishlist_mutation_committed")
    for record in caplog.records:
        assert TITLE not in f"{record.getMessage()} {JsonFormatter().format(record)}"
