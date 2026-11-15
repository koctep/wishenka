"""Log contract of the receipt UI path (WISHENKA-24, Step 6; caplog contract C1-C5).

One full flow (open, partial receipt, refusals, busy, stale archive and restore, stale reorder)
with three promised givers. Every record of the flow is scanned: closed field sets per event, one
record per outcome, no giver, booking number, title, exception text or notice word. No network.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.receipt_support import (
    GIFTER,
    OTHER_GIFTER,
    OWNER_ID,
    STRANGER_ID,
    THIRD_GIFTER,
    AppEnv,
    app_env,
    db_path_of,
    sql_exec,
)
from tests.receipt_ui_support import (
    GENERIC_FAILURE,
    SENTENCES,
    Wish,
    hx,
    modal_url,
    promise,
    receive,
    seed_list,
)
from tests.test_receipt_ui_routes import _busy_execute, _patch_execute
from wishenka.web.routes.receipts import _REFUSALS

pytestmark = pytest.mark.timeout(60)

_UI = "wishenka.web.receipts_ui"
_STANDARD = set(logging.LogRecord("n", 0, "p", 0, "m", (), None).__dict__) | {"message", "asctime"}
_IDS = {"wishlist_id", "item_id", "actor_id"}
_REFUSED = _IDS | {"reason", "http_status"}
_NOTICE_WORDS = ("notification", "outbox", "push")
_BOOKED = (37, 41, 53)
_NAMES = ("Greta", "Oleg", "Tina")
_TITLES = ("Kettle", "Mug", "Cup")
_RECEIPT_KEYS = {"receipt_id", "item_id", "wishlist_id", "reason", "http_status", "actor_id"}


@pytest.fixture
def env(tmp_path: Path) -> Iterator[AppEnv]:
    """Open create_app on an isolated SQLite file with bearer sessions."""
    with app_env(tmp_path) as opened:
        yield opened


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD}


def _ours(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name.startswith("wishenka")]


def _ui(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == _UI]


def test_full_ui_flow_log_contract(
    env: AppEnv, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C1-C5: exact field sets, one UI record per outcome, nothing private in any record."""
    client, sessions, app = env
    wishlist_id, (wish, full, archived, mug) = seed_list(
        app, [Wish("Kettle", 300), Wish("Mug", 2), Wish("Cup", 2), Wish("Mug", 4)]
    )
    for giver, count in zip((GIFTER, OTHER_GIFTER, THIRD_GIFTER), _BOOKED, strict=True):
        promise(app, wish, giver, count)
    receive(app, wish, 200)
    receive(app, full, 2)
    receive(app, archived, 2)
    sql_exec(db_path_of(app), "UPDATE wl_items SET is_archived = 1 WHERE id = ?", (archived,))
    headers = hx(sessions)
    caplog.set_level(logging.DEBUG)
    steps: list[tuple[str, int, list[logging.LogRecord], list[logging.LogRecord]]] = []

    def step(label: str, expected: int, response: Any) -> None:
        assert response.status_code == expected, f"{label}: {response.status_code} {response.text}"
        steps.append((label, expected, _ui(caplog), _ours(caplog)))
        caplog.clear()

    def post(item: int, quantity: str, user_id: int = OWNER_ID) -> Any:
        return client.post(
            modal_url(wishlist_id, item), data={"quantity": quantity}, headers=hx(sessions, user_id)
        )

    caplog.clear()
    step("open", 200, client.get(modal_url(wishlist_id, wish), headers=headers))
    step("accepted", 201, post(wish, "7"))
    step("above", 409, post(wish, "999"))
    step("invalid", 400, post(wish, "abc"))
    step("forbidden", 403, post(wish, "1", STRANGER_ID))
    step("not_found", 404, post(9999, "1"))
    step("wish_archived", 409, post(archived, "1"))
    step("nothing", 409, post(full, "1"))
    step("stale open", 409, client.get(modal_url(wishlist_id, full), headers=headers))
    base = f"/web/wishlists/{wishlist_id}/items"
    step("stale archive", 409, client.post(f"{base}/{full}/archive", headers=headers))
    sql_exec(db_path_of(app), "UPDATE wl_items SET is_archived = 1 WHERE id = ?", (full,))
    step("stale restore", 409, client.post(f"{base}/{full}/restore", headers=headers))
    step(
        "stale reorder",
        400,
        client.post(f"{base}/reorder", data={"item_ids": [str(mug)]}, headers=headers),
    )
    _patch_execute(monkeypatch, _busy_execute)
    step("busy", 503, post(wish, "1"))
    step("busy open", 503, client.get(modal_url(wishlist_id, wish), headers=headers))

    # (event, level, extra key set, reason) of the single UI record of each UI outcome.
    ui_expected: dict[str, tuple[str, int, set[str], str | None]] = {
        "open": ("ui_receipt_form_opened", logging.INFO, _IDS, None),
        "accepted": ("receipt_recorded_http", logging.INFO, _IDS, None),
        "above": (
            "receipt_refused",
            logging.WARNING,
            _REFUSED | {"remaining_quantity"},
            "quantity_above_remaining",
        ),
        "invalid": ("receipt_refused", logging.WARNING, _REFUSED, "quantity_invalid"),
        "forbidden": ("receipt_refused", logging.WARNING, _REFUSED, "forbidden"),
        "not_found": ("receipt_refused", logging.WARNING, _REFUSED, "not_found"),
        "wish_archived": ("receipt_refused", logging.WARNING, _REFUSED, "wish_archived"),
        "nothing": (
            "receipt_refused",
            logging.WARNING,
            _REFUSED | {"remaining_quantity"},
            "nothing_remaining",
        ),
        "stale open": (
            "ui_receipt_form_refused",
            logging.WARNING,
            _REFUSED | {"remaining_quantity"},
            "nothing_remaining",
        ),
        "busy": ("receipt_inventory_busy", logging.WARNING, _IDS, None),
        "busy open": ("ui_receipt_form_refused", logging.WARNING, _REFUSED, "busy"),
    }
    for label, status_code, ui_records, _all in steps:
        if label not in ui_expected:
            # Stale archive, restore and reorder write nothing on the receipt UI logger.
            assert ui_records == [], f"{label}: unexpected UI records"
            continue
        event, level, keys, reason = ui_expected[label]
        assert len(ui_records) == 1, f"{label}: {len(ui_records)} UI records"
        record = ui_records[0]
        extras = _extras(record)
        assert extras.pop("event") == event, label
        assert record.levelno == level, label
        assert set(extras) == keys, f"{label}: {sorted(extras)}"
        assert extras["wishlist_id"] == wishlist_id and extras["actor_id"] in (
            OWNER_ID,
            STRANGER_ID,
        )
        if reason:
            assert extras["reason"] == reason and extras["http_status"] == status_code, label
        if "remaining_quantity" in extras:
            assert extras["remaining_quantity"] == (
                93 if reason == "quantity_above_remaining" else 0
            )

    by_label = {label: all_records for label, _status, _ui_records, all_records in steps}
    # Stale archive and restore: the service writes the one existing refusal record (no route log).
    for label in ("stale archive", "stale restore"):
        refused = [r for r in by_label[label] if getattr(r, "event", "") == "wish_archive_refused"]
        assert len(refused) == 1, label
        assert set(_extras(refused[0])) == {"event", *_IDS, "reason"}, label
        assert refused[0].levelno == logging.WARNING and refused[0].name != _UI
    # Stale reorder: the existing items_ui record, no receipt keys, no quantities.
    rejected = [
        r
        for r in by_label["stale reorder"]
        if r.__dict__.get("event") == "ui_items_reorder_rejected"
    ]
    assert len(rejected) == 1 and rejected[0].name == "wishenka.web.items_ui"
    assert _extras(rejected[0])["reason"] == "invalid_permutation"
    # The same event names of the JSON route come from another logger only (not used here).
    assert {r.name for _l, _s, ui_records, _a in steps for r in ui_records} <= {_UI}

    every = [record for _l, _s, _u, records in steps for record in records]
    assert every, "no records captured"
    ui_all = [record for _l, _s, records, _a in steps for record in records]
    english = [message for _t, _s, _r, message in _REFUSALS]
    texts = (*SENTENCES.values(), GENERIC_FAILURE)
    for record in every:
        event = str(getattr(record, "event", ""))
        head = f"{event} {record.getMessage()}".lower()
        for word in _NOTICE_WORDS:
            assert word not in head, f"{word!r} in {head!r}"
        blob = f"{record.getMessage()} {_extras(record)}"
        for name in (*_NAMES, *_TITLES, "Traceback", *english, *texts):
            assert name not in blob, f"{name!r} logged: {blob}"
        assert record.exc_info is None and record.exc_text is None, blob
        extras = _extras(record)
        # An outbox key never shares a record with a receipt key (22: no notice-receipt link).
        if "outbox_id" in extras:
            assert not (_RECEIPT_KEYS & set(extras)), blob
    for record in ui_all:
        blob = f"{record.getMessage()} {_extras(record)}"
        assert {"operation", "user_id", "outbox_id", "quantity", "title"}.isdisjoint(
            _extras(record)
        )
        for number in (*_BOOKED, 7, 999, 200, 300):
            assert re.search(rf"(?<![\w.]){number}(?!\d)", blob) is None, f"{number} in {blob}"
    # Fixed messages: no id or text is interpolated into a UI record.
    assert {r.getMessage() for r in ui_all} == {
        "Receipt dialog opened",
        "Receipt recorded",
        "Receipt refused",
        "Receipt busy",
    }
