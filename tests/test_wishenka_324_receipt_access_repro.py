"""Failing repro for WISHENKA-324: pass wishlist access into gift-receipt looks.

A look whose hidden slot is empty still opens ``get_wishlist_repository``.
Desired behavior: the look uses the repository it was given, the screens keep
today's status, ``X-Receipt-Refusal`` reason, and fragments, and a successful
keyed save still composes the list on that save.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from typing import Annotated, Any, cast

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.receipt_support import (
    OWNER,
    app_env,
    db_path_of,
    item_received,
    receipt_rows,
)
from tests.receipt_ui_support import (
    REFUSAL_HEADER,
    SENTENCES,
    Wish,
    hx,
    modal_url,
    oob,
    oob_list,
    parse,
    receive,
    run,
    seed_list,
    text_of,
)
from wishenka.web.dependencies import get_wishlist_read_repository, get_wishlist_store
from wishenka.web.routes import receipts_ui
from wishenka.wishlists.exceptions import NothingRemainingError, QuantityAboveRemainingError
from wishenka.wishlists.repo_ops import RepoWishlistOps
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

_TITLE = "Kettle"
_QUANTITY = 4


class HiddenSlotFallback(RuntimeError):
    """The look opened a shared repository because the hidden slot was empty."""


def _refuse_shared_open(*_args: object, **_kwargs: object) -> None:
    """Stand in for ``get_wishlist_repository``; entering it is the defect."""
    raise HiddenSlotFallback(
        "gift-receipt look opened get_wishlist_repository with an empty hidden slot"
    )


@pytest.fixture(autouse=True)
def _block_shared_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        receipts_ui,
        "get_wishlist_repository",
        _refuse_shared_open,
        raising=False,
    )


@pytest.fixture
def env(tmp_path: Any) -> Iterator[tuple[TestClient, Any, FastAPI]]:
    """File SQLite under ``tmp_path`` and a ``TestClient``. No network."""
    with app_env(tmp_path, "wishenka-324.db") as opened:
        yield opened


def _request(app: FastAPI) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
        "app": app,
    }
    return Request(scope)


def _headers(sessions: Any, key: str | None = None) -> dict[str, str]:
    headers = hx(sessions)
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _entry_url(wishlist_id: int, item_id: int, receipt_id: int, action: str) -> str:
    base = f"/web/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}"
    return f"{base}/{action}"


def _record_ops(monkeypatch: pytest.MonkeyPatch, built: list[object]) -> None:
    class _RecordingOps(RepoWishlistOps):
        def __init__(self, repo: WishlistRepository) -> None:
            built.append(repo)
            super().__init__(repo)

    monkeypatch.setattr(receipts_ui, "RepoWishlistOps", _RecordingOps)


class _ComposeSpy:
    """Records list reads and whether each keyed repository sits on the save."""

    def __init__(self) -> None:
        self.reads: list[str] = []
        self.on_save: list[bool] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_state = receipts_ui._read_state
        real_full = receipts_ui._read_full_mutation_state
        spy = self

        class _RecordingRepository(WishlistRepository):
            def __init__(self, conn: AsyncConnection) -> None:
                sync_conn: Any = getattr(conn, "sync_connection", conn)
                options = sync_conn.get_execution_options()
                spy.on_save.append(bool(conn.in_transaction()) and not options.get("read_only"))
                super().__init__(conn)

        async def _state(*args: Any, **kwargs: Any) -> Any:
            spy.reads.append("state")
            return await real_state(*args, **kwargs)

        async def _full(*args: Any, **kwargs: Any) -> Any:
            spy.reads.append("full")
            return await real_full(*args, **kwargs)

        monkeypatch.setattr(receipts_ui, "WishlistRepository", _RecordingRepository)
        monkeypatch.setattr(receipts_ui, "_read_state", _state)
        monkeypatch.setattr(receipts_ui, "_read_full_mutation_state", _full)


def _assert_list_on_save(
    spy: _ComposeSpy, *, reads_before: int, saves_before: int, kind: str
) -> None:
    assert spy.reads[reads_before:] == [kind]
    assert spy.on_save[saves_before:] == [True]


def _assert_unchanged(spy: _ComposeSpy, *, reads_before: int, saves_before: int) -> None:
    assert spy.reads[reads_before:] == []
    assert spy.on_save[saves_before:] == []


@pytest.mark.parametrize("reason", ["quantity_above_remaining", "nothing_remaining"])
def test_quantity_refusal_look_uses_the_given_repository(
    env: tuple[TestClient, Any, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    """Empty slot plus a sentinel: ``RepoWishlistOps`` is built on that sentinel."""
    _client, _sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish(_TITLE, _QUANTITY)])
    if reason == "nothing_remaining":
        receive(app, item_id, _QUANTITY)
        exc: Exception = NothingRemainingError()
    else:
        exc = QuantityAboveRemainingError(_QUANTITY)
    built: list[object] = []
    _record_ops(monkeypatch, built)

    async def paint() -> str | None:
        async with app.state.wishlist_store.read_transaction() as conn:
            sentinel = WishlistRepository(conn)
            html = await receipts_ui._effect_fragments(
                _request(app),
                OWNER,
                (wishlist_id, item_id, OWNER.telegram_id),
                reason,
                exc,
                locale="ru",
                repo=sentinel,
            )
            assert built == [sentinel]
            return html

    body = run(paint())
    assert body is not None
    if reason == "quantity_above_remaining":
        assert f'id="item-card-{item_id}"' in body
        assert 'id="item-receipt-modal"' in body
        assert "Осталось: 4" in body
    else:
        assert 'hx-swap-oob="innerHTML:#items-list"' in body
        assert 'id="gifted-items-section"' in body
        assert _TITLE in body
    assert SENTENCES[reason].format(n=0 if reason == "nothing_remaining" else _QUANTITY) in body


def test_opening_dialogs_use_the_handler_repository(
    env: tuple[TestClient, Any, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET receipt, correction, and cancellation use the read dependency given to them."""
    client, sessions, app = env
    given: list[object] = []
    built: list[object] = []
    _record_ops(monkeypatch, built)
    original = get_wishlist_read_repository

    async def _yield_given(
        store: Annotated[WishlistStore, Depends(get_wishlist_store)],
    ) -> AsyncIterator[WishlistRepository]:
        agen = cast(AsyncGenerator[WishlistRepository, None], original(store))
        try:
            repo = await agen.__anext__()
            given.append(repo)
            yield repo
        finally:
            await agen.aclose()

    app.dependency_overrides[get_wishlist_read_repository] = _yield_given
    try:
        wishlist_id, (open_id, done_id) = seed_list(app, [Wish("Open", _QUANTITY), Wish("Done", 1)])
        receive(app, done_id, 1)
        receipt_id = int(receipt_rows(db_path_of(app))[-1]["id"])
        headers = hx(sessions)

        def _one(path: str) -> Any:
            before_given = len(given)
            before_built = len(built)
            response = client.get(path, headers=headers)
            handed = given[before_given:]
            used = built[before_built:]
            assert len(handed) == 1
            assert used, response.text
            assert all(repo is handed[0] for repo in used)
            return response

        opened = _one(modal_url(wishlist_id, open_id))
        assert opened.status_code == 200, opened.text
        assert REFUSAL_HEADER not in opened.headers
        assert "Осталось: 4" in opened.text
        assert opened.text.count("<form") == 1

        blocked = _one(modal_url(wishlist_id, done_id))
        assert blocked.status_code == 409, blocked.text
        assert blocked.headers.get(REFUSAL_HEADER) == "nothing_remaining"
        soup = parse(blocked.text)
        assert text_of(soup.select_one("#receipt-feedback")) == SENTENCES["nothing_remaining"]
        assert oob_list(soup) is not None
        assert "Done" in text_of(oob(soup, "gifted-items-section"))
        assert soup.select_one("form") is None

        edit = _one(_entry_url(wishlist_id, done_id, receipt_id, "edit"))
        assert edit.status_code == 200, edit.text
        assert "Исправить количество" in edit.text
        assert edit.text.count("<form") == 1

        cancel = _one(_entry_url(wishlist_id, done_id, receipt_id, "cancel"))
        assert cancel.status_code == 200, cancel.text
        assert "Отменить отметку о получении?" in cancel.text
        assert cancel.text.count("<form") == 1
    finally:
        app.dependency_overrides.pop(get_wishlist_read_repository, None)


@pytest.mark.parametrize("reason", ["quantity_above_remaining", "nothing_remaining"])
def test_refused_record_with_repeat_key_does_not_open_shared_repository(
    env: tuple[TestClient, Any, FastAPI],
    reason: str,
) -> None:
    """A refused record that still carries the repeat key paints from passed access."""
    client, sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish(_TITLE, _QUANTITY)])
    db = db_path_of(app)
    if reason == "nothing_remaining":
        receive(app, item_id, _QUANTITY)
        quantity = "1"
    else:
        quantity = "9"
    before = item_received(db, item_id)

    response = client.post(
        modal_url(wishlist_id, item_id),
        data={"quantity": quantity},
        headers=_headers(sessions, f"refuse-{reason}"),
    )

    assert response.status_code == 409, response.text
    assert response.headers.get(REFUSAL_HEADER) == reason
    soup = parse(response.text)
    remaining = 0 if reason == "nothing_remaining" else _QUANTITY
    assert SENTENCES[reason].format(n=remaining) in response.text
    if reason == "quantity_above_remaining":
        assert f"item-card-{item_id}" in response.text
        dialog = oob(soup, "item-receipt-modal")
        assert "Осталось: 4" in text_of(dialog)
    else:
        assert oob_list(soup) is not None
        assert _TITLE in text_of(oob(soup, "gifted-items-section"))
    assert item_received(db, item_id) == before


def test_keyed_save_composes_the_list_on_the_save(
    env: tuple[TestClient, Any, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Record, correction, and cancellation with a repeat key compose on the save.

    A second POST with the same key and body returns the stored answer and does
    not read the list again.
    """
    client, sessions, app = env
    spy = _ComposeSpy()
    spy.install(monkeypatch)
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish(_TITLE, 2)])
    db = db_path_of(app)
    record_headers = _headers(sessions, "record-key")

    reads, saves = len(spy.reads), len(spy.on_save)
    recorded = client.post(
        modal_url(wishlist_id, item_id),
        data={"quantity": "2"},
        headers=record_headers,
    )
    assert recorded.status_code == 201, recorded.text
    assert 'hx-swap-oob="innerHTML:#items-list"' in recorded.text
    assert 'id="gifted-items-section"' in recorded.text
    assert "Отмечено получено: 2 шт. («Kettle»)" in recorded.text
    _assert_list_on_save(spy, reads_before=reads, saves_before=saves, kind="state")
    assert item_received(db, item_id) == 2

    reads, saves = len(spy.reads), len(spy.on_save)
    replay = client.post(
        modal_url(wishlist_id, item_id),
        data={"quantity": "2"},
        headers=record_headers,
    )
    assert replay.status_code == 201, replay.text
    assert replay.text == recorded.text
    _assert_unchanged(spy, reads_before=reads, saves_before=saves)
    assert item_received(db, item_id) == 2

    receipt_id = int(receipt_rows(db)[-1]["id"])
    edit_url = _entry_url(wishlist_id, item_id, receipt_id, "edit")
    edit_headers = _headers(sessions, "edit-key")
    reads, saves = len(spy.reads), len(spy.on_save)
    edited = client.post(edit_url, data={"quantity": "1"}, headers=edit_headers)
    assert edited.status_code == 200, edited.text
    assert oob_list(parse(edited.text)) is not None
    assert "Количество обновлено: 1 шт. («Kettle»)" in edited.text
    _assert_list_on_save(spy, reads_before=reads, saves_before=saves, kind="full")
    assert item_received(db, item_id) == 1

    reads, saves = len(spy.reads), len(spy.on_save)
    edit_replay = client.post(edit_url, data={"quantity": "1"}, headers=edit_headers)
    assert edit_replay.status_code == 200, edit_replay.text
    assert edit_replay.text == edited.text
    _assert_unchanged(spy, reads_before=reads, saves_before=saves)
    assert item_received(db, item_id) == 1

    cancel_url = _entry_url(wishlist_id, item_id, receipt_id, "cancel")
    cancel_headers = _headers(sessions, "cancel-key")
    reads, saves = len(spy.reads), len(spy.on_save)
    cancelled = client.post(cancel_url, headers=cancel_headers)
    assert cancelled.status_code == 200, cancelled.text
    assert oob_list(parse(cancelled.text)) is not None
    assert "Отметка о получении отменена («Kettle»)" in cancelled.text
    _assert_list_on_save(spy, reads_before=reads, saves_before=saves, kind="full")
    assert item_received(db, item_id) == 0

    reads, saves = len(spy.reads), len(spy.on_save)
    cancel_replay = client.post(cancel_url, headers=cancel_headers)
    assert cancel_replay.status_code == 200, cancel_replay.text
    assert cancel_replay.text == cancelled.text
    _assert_unchanged(spy, reads_before=reads, saves_before=saves)
    assert item_received(db, item_id) == 0


def test_unkeyed_save_paints_the_list_without_a_shared_repository(
    env: tuple[TestClient, Any, FastAPI],
) -> None:
    """A successful record, correction, and cancellation with no key stay off the slot."""
    client, sessions, app = env
    wishlist_id, (item_id, *_rest) = seed_list(app, [Wish(_TITLE, 2)])
    db = db_path_of(app)
    headers = hx(sessions)

    recorded = client.post(
        modal_url(wishlist_id, item_id),
        data={"quantity": "2"},
        headers=headers,
    )
    assert recorded.status_code == 201, recorded.text
    assert 'hx-swap-oob="innerHTML:#items-list"' in recorded.text
    assert 'id="gifted-items-section"' in recorded.text
    assert "Отмечено получено: 2 шт. («Kettle»)" in recorded.text
    assert item_received(db, item_id) == 2

    receipt_id = int(receipt_rows(db)[-1]["id"])
    edited = client.post(
        _entry_url(wishlist_id, item_id, receipt_id, "edit"),
        data={"quantity": "1"},
        headers=headers,
    )
    assert edited.status_code == 200, edited.text
    assert oob_list(parse(edited.text)) is not None
    assert "Количество обновлено: 1 шт. («Kettle»)" in edited.text
    assert item_received(db, item_id) == 1

    cancelled = client.post(
        _entry_url(wishlist_id, item_id, receipt_id, "cancel"),
        headers=headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert oob_list(parse(cancelled.text)) is not None
    assert "Отметка о получении отменена («Kettle»)" in cancelled.text
    assert item_received(db, item_id) == 0
