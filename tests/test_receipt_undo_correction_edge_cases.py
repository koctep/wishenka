"""Edge-case verification tests for WISHENKA-217 (gift receipt cancel & correction).

Covers the four edge-case groups from ai-tasks/WISHENKA-217/20-architecture.md:
1. Idempotency replay and conflict detection on DELETE/PATCH JSON and UI edit/cancel.
2. Cross-item and cross-wishlist receipt_id isolation on JSON and UI routes.
3. No-op quantity correction on PATCH JSON and UI edit (state & outbox unchanged).
4. Refusal responses on GET .../edit and GET .../cancel (missing receipt, archived list).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OWNER,
    OWNER_ID,
    app_env,
    bearer,
    db_path_of,
    item_received,
    receipt_rows,
    seed_users,
    sql_exec,
    sql_rows,
    table_rows,
)
from tests.receipt_ui_support import (
    GIVER_NAMES,
    REFUSAL_HEADER,
    Wish,
    assert_all_top_level_oob,
    assert_no_booking_leak,
    domain,
    hx,
    run,
    seed_list,
)
from wishenka.auth.session import SessionTokenService

pytestmark = pytest.mark.timeout(20)


def _seed_deliverable_gifter(db: Path | str, telegram_id: int) -> None:
    """Seed a user and active bot destination so receipt-change notices queue in reminder_outbox."""
    seed_users(db, telegram_id)
    rows = sql_rows(db, "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
    user_pk = int(rows[0]["id"])
    sql_exec(
        db,
        "INSERT OR IGNORE INTO bot_destinations(user_id, chat_id, active) VALUES (?, ?, 1)",
        (user_pk, telegram_id),
    )


def _record_and_get_receipt_id(
    client: TestClient,
    sessions: SessionTokenService,
    wishlist_id: int,
    item_id: int,
    quantity: int,
) -> int:
    """Record a receipt via JSON API and return the newly created receipt_id."""
    resp = client.post(
        f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts",
        json={"quantity": quantity},
        headers=bearer(sessions, OWNER_ID, "Alice"),
    )
    assert resp.status_code == 201
    gifted = client.get(
        f"/api/wishlists/{wishlist_id}/gifted",
        headers=bearer(sessions, OWNER_ID, "Alice"),
    )
    assert gifted.status_code == 200
    for entry in gifted.json():
        if entry["id"] == item_id:
            return int(entry["receipts"][-1]["id"])
    raise AssertionError(f"Receipt not found in gifted response for item {item_id}")


# ---------------------------------------------------------------------------
# 1. Idempotency replay and conflict detection (FR-1)
# ---------------------------------------------------------------------------


def test_json_patch_idempotency_replay_and_conflict(tmp_path: Path) -> None:
    """PATCH replay returns cached response with no duplicate outbox; conflict returns 409."""
    with app_env(tmp_path) as (client, sessions, app):
        db = db_path_of(app)
        _seed_deliverable_gifter(db, GIFTER_ID)
        wishlist_id, item_ids = seed_list(app, [Wish(title="Kettle", quantity=5)])
        item_id = item_ids[0]
        run(domain(app).create_reservation(item_id, GIFTER, quantity=3, wishlist_id=wishlist_id))

        receipt_id = _record_and_get_receipt_id(client, sessions, wishlist_id, item_id, 4)
        outbox_before = len(table_rows(db, "reminder_outbox"))

        url = f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}"
        headers = {**bearer(sessions, OWNER_ID, "Alice"), "Idempotency-Key": "patch-key-1"}

        first = client.patch(url, json={"quantity": 2}, headers=headers)
        assert first.status_code == 200
        assert first.json()["received_now"] == 2
        assert first.json()["received_quantity"] == 2
        assert first.json()["remaining_quantity"] == 3
        assert item_received(db, item_id) == 2

        outbox_after_first = len(table_rows(db, "reminder_outbox"))
        assert outbox_after_first == outbox_before + 1

        # Exact replay returns identical JSON without mutating DB or adding an outbox row.
        replay = client.patch(url, json={"quantity": 2}, headers=headers)
        assert replay.status_code == 200
        assert replay.json() == first.json()
        assert item_received(db, item_id) == 2
        assert receipt_rows(db)[0]["quantity"] == 2
        assert len(table_rows(db, "reminder_outbox")) == outbox_after_first

        # Reusing key with a different quantity returns 409 idempotency_conflict.
        conflict_qty = client.patch(url, json={"quantity": 1}, headers=headers)
        assert conflict_qty.status_code == 409
        assert conflict_qty.json()["detail"]["reason"] == "idempotency_conflict"
        assert item_received(db, item_id) == 2
        assert receipt_rows(db)[0]["quantity"] == 2
        assert len(table_rows(db, "reminder_outbox")) == outbox_after_first

        # Reusing key for DELETE on the same receipt also returns 409 idempotency_conflict.
        conflict_op = client.delete(url, headers=headers)
        assert conflict_op.status_code == 409
        assert conflict_op.json()["detail"]["reason"] == "idempotency_conflict"
        assert len(receipt_rows(db)) == 1
        assert item_received(db, item_id) == 2


def test_json_delete_idempotency_replay_and_conflict(tmp_path: Path) -> None:
    """DELETE replay returns cached response with no duplicate outbox; conflict returns 409."""
    with app_env(tmp_path) as (client, sessions, app):
        db = db_path_of(app)
        _seed_deliverable_gifter(db, GIFTER_ID)
        wishlist_id, item_ids = seed_list(app, [Wish(title="Toaster", quantity=5)])
        item_id = item_ids[0]
        run(domain(app).create_reservation(item_id, GIFTER, quantity=2, wishlist_id=wishlist_id))

        r1_id = _record_and_get_receipt_id(client, sessions, wishlist_id, item_id, 2)
        r2_id = _record_and_get_receipt_id(client, sessions, wishlist_id, item_id, 1)
        outbox_before = len(table_rows(db, "reminder_outbox"))

        url_r1 = f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts/{r1_id}"
        url_r2 = f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts/{r2_id}"
        headers = {**bearer(sessions, OWNER_ID, "Alice"), "Idempotency-Key": "del-key-1"}

        first = client.delete(url_r1, headers=headers)
        assert first.status_code == 200
        assert first.json()["received_now"] == 0
        assert first.json()["received_quantity"] == 1
        assert first.json()["remaining_quantity"] == 4
        assert item_received(db, item_id) == 1

        outbox_after_first = len(table_rows(db, "reminder_outbox"))
        assert outbox_after_first == outbox_before + 1

        # Exact replay returns identical JSON and leaves remaining receipt + outbox untouched.
        replay = client.delete(url_r1, headers=headers)
        assert replay.status_code == 200
        assert replay.json() == first.json()
        assert item_received(db, item_id) == 1
        assert [row["id"] for row in receipt_rows(db)] == [r2_id]
        assert len(table_rows(db, "reminder_outbox")) == outbox_after_first

        # Reusing key against a different receipt_id returns 409 idempotency_conflict.
        conflict = client.delete(url_r2, headers=headers)
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["reason"] == "idempotency_conflict"
        assert [row["id"] for row in receipt_rows(db)] == [r2_id]
        assert item_received(db, item_id) == 1
        assert len(table_rows(db, "reminder_outbox")) == outbox_after_first


def test_ui_edit_and_cancel_idempotency_replay_and_conflict(tmp_path: Path) -> None:
    """UI POST .../edit and .../cancel support Idempotency-Key replay and 409 conflict."""
    with app_env(tmp_path) as (client, sessions, app):
        db = db_path_of(app)
        _seed_deliverable_gifter(db, GIFTER_ID)
        wishlist_id, item_ids = seed_list(app, [Wish(title="Lamp", quantity=5)])
        item_id = item_ids[0]
        run(domain(app).create_reservation(item_id, GIFTER, quantity=3, wishlist_id=wishlist_id))

        r1_id = _record_and_get_receipt_id(client, sessions, wishlist_id, item_id, 2)
        r2_id = _record_and_get_receipt_id(client, sessions, wishlist_id, item_id, 1)
        outbox_before = len(table_rows(db, "reminder_outbox"))

        edit_url_r1 = f"/web/wishlists/{wishlist_id}/items/{item_id}/receipts/{r1_id}/edit"
        cancel_url_r1 = f"/web/wishlists/{wishlist_id}/items/{item_id}/receipts/{r1_id}/cancel"
        cancel_url_r2 = f"/web/wishlists/{wishlist_id}/items/{item_id}/receipts/{r2_id}/cancel"

        edit_headers = {**hx(sessions, OWNER_ID), "Idempotency-Key": "ui-edit-key-1"}
        first_edit = client.post(edit_url_r1, data={"quantity": "4"}, headers=edit_headers)
        assert first_edit.status_code == 200
        soup = BeautifulSoup(first_edit.text, "html.parser")
        assert_all_top_level_oob(soup, first_edit.text)
        assert_no_booking_leak(first_edit.text)
        assert item_received(db, item_id) == 5

        outbox_after_edit = len(table_rows(db, "reminder_outbox"))
        assert outbox_after_edit == outbox_before + 1

        # UI edit replay returns identical OOB HTML with no duplicate outbox row.
        replay_edit = client.post(edit_url_r1, data={"quantity": "4"}, headers=edit_headers)
        assert replay_edit.status_code == 200
        assert replay_edit.text == first_edit.text
        assert item_received(db, item_id) == 5
        assert len(table_rows(db, "reminder_outbox")) == outbox_after_edit

        # Conflicting quantity with same key returns 409 + X-Receipt-Refusal: idempotency_conflict.
        conflict_qty = client.post(edit_url_r1, data={"quantity": "3"}, headers=edit_headers)
        assert conflict_qty.status_code == 409
        assert conflict_qty.headers.get(REFUSAL_HEADER) == "idempotency_conflict"
        assert item_received(db, item_id) == 5

        # Conflicting operation (cancel with edit key) also returns 409.
        conflict_op = client.post(cancel_url_r1, headers=edit_headers)
        assert conflict_op.status_code == 409
        assert conflict_op.headers.get(REFUSAL_HEADER) == "idempotency_conflict"
        assert item_received(db, item_id) == 5

        # UI cancel replay & conflict.
        cancel_headers = {**hx(sessions, OWNER_ID), "Idempotency-Key": "ui-cancel-key-1"}
        first_cancel = client.post(cancel_url_r1, headers=cancel_headers)
        assert first_cancel.status_code == 200
        cancel_soup = BeautifulSoup(first_cancel.text, "html.parser")
        assert_all_top_level_oob(cancel_soup, first_cancel.text)
        assert_no_booking_leak(first_cancel.text)
        assert item_received(db, item_id) == 1

        outbox_after_cancel = len(table_rows(db, "reminder_outbox"))
        assert outbox_after_cancel == outbox_after_edit + 1

        replay_cancel = client.post(cancel_url_r1, headers=cancel_headers)
        assert replay_cancel.status_code == 200
        assert replay_cancel.text == first_cancel.text
        assert item_received(db, item_id) == 1
        assert len(table_rows(db, "reminder_outbox")) == outbox_after_cancel

        conflict_cancel = client.post(cancel_url_r2, headers=cancel_headers)
        assert conflict_cancel.status_code == 409
        assert conflict_cancel.headers.get(REFUSAL_HEADER) == "idempotency_conflict"
        assert [row["id"] for row in receipt_rows(db)] == [r2_id]
        assert item_received(db, item_id) == 1


# ---------------------------------------------------------------------------
# 2. Cross-item and cross-wishlist receipt_id isolation (FR-2)
# ---------------------------------------------------------------------------


def test_cross_item_and_cross_wishlist_receipt_isolation(tmp_path: Path) -> None:
    """Mismatched item_id or wishlist_id refuses with 404 and leaves target receipt intact."""
    with app_env(tmp_path) as (client, sessions, app):
        db = db_path_of(app)
        wl1_id, wl1_items = seed_list(
            app,
            [Wish(title="Item One", quantity=5), Wish(title="Item Two", quantity=5)],
        )
        item1_id, item2_id = wl1_items
        wl2_id, wl2_items = seed_list(app, [Wish(title="Other List Item", quantity=5)])
        item3_id = wl2_items[0]

        r1_id = _record_and_get_receipt_id(client, sessions, wl1_id, item1_id, 3)
        _record_and_get_receipt_id(client, sessions, wl1_id, item2_id, 2)
        _record_and_get_receipt_id(client, sessions, wl2_id, item3_id, 1)

        api_headers = bearer(sessions, OWNER_ID, "Alice")
        ui_headers = hx(sessions, OWNER_ID)

        # Cross-item (same wishlist, wrong item_id) and cross-wishlist (other wishlist + its item)
        # both resolve the target item and refuse because r1_id does not belong to that item.
        wrong_receipt_targets = [
            (wl1_id, item2_id, "receipt_not_found"),
            (wl2_id, item3_id, "receipt_not_found"),
            # Cross-wishlist with item1_id (belongs to wl1, not wl2) -> item not found in wl2.
            (wl2_id, item1_id, "not_found"),
        ]

        for target_wl, target_item, expected_reason in wrong_receipt_targets:
            json_url = f"/api/wishlists/{target_wl}/items/{target_item}/receipts/{r1_id}"
            patch_resp = client.patch(json_url, json={"quantity": 1}, headers=api_headers)
            assert patch_resp.status_code == 404
            assert patch_resp.json()["detail"]["reason"] == expected_reason

            del_resp = client.delete(json_url, headers=api_headers)
            assert del_resp.status_code == 404
            assert del_resp.json()["detail"]["reason"] == expected_reason

            ui_edit = client.post(
                f"/web/wishlists/{target_wl}/items/{target_item}/receipts/{r1_id}/edit",
                data={"quantity": "1"},
                headers=ui_headers,
            )
            assert ui_edit.status_code == 404
            assert ui_edit.headers.get(REFUSAL_HEADER) == expected_reason

            ui_cancel = client.post(
                f"/web/wishlists/{target_wl}/items/{target_item}/receipts/{r1_id}/cancel",
                headers=ui_headers,
            )
            assert ui_cancel.status_code == 404
            assert ui_cancel.headers.get(REFUSAL_HEADER) == expected_reason

        # Verify r1_id and all items remain completely untouched.
        assert item_received(db, item1_id) == 3
        assert item_received(db, item2_id) == 2
        assert item_received(db, item3_id) == 1
        r1_rows = [row for row in receipt_rows(db) if row["id"] == r1_id]
        assert len(r1_rows) == 1
        assert r1_rows[0]["quantity"] == 3
        assert r1_rows[0]["wish_item_id"] == item1_id


# ---------------------------------------------------------------------------
# 3. No-op quantity correction (FR-3)
# ---------------------------------------------------------------------------


def test_noop_quantity_correction_json_and_ui_leaves_state_and_outbox_unchanged(
    tmp_path: Path,
) -> None:
    """Submitting the existing quantity on PATCH or UI edit succeeds without outbox side effects."""
    with app_env(tmp_path) as (client, sessions, app):
        db = db_path_of(app)
        _seed_deliverable_gifter(db, GIFTER_ID)
        wishlist_id, item_ids = seed_list(app, [Wish(title="Mug", quantity=5)])
        item_id = item_ids[0]
        run(domain(app).create_reservation(item_id, GIFTER, quantity=3, wishlist_id=wishlist_id))

        receipt_id = _record_and_get_receipt_id(client, sessions, wishlist_id, item_id, 2)
        rows_before = receipt_rows(db)
        outbox_before = len(table_rows(db, "reminder_outbox"))

        # No-op PATCH JSON.
        patch_resp = client.patch(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}",
            json={"quantity": 2},
            headers=bearer(sessions, OWNER_ID, "Alice"),
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["received_now"] == 2
        assert patch_resp.json()["received_quantity"] == 2
        assert patch_resp.json()["remaining_quantity"] == 3
        assert item_received(db, item_id) == 2
        assert receipt_rows(db) == rows_before
        assert len(table_rows(db, "reminder_outbox")) == outbox_before

        # No-op UI POST .../edit.
        ui_resp = client.post(
            f"/web/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}/edit",
            data={"quantity": "2"},
            headers=hx(sessions, OWNER_ID),
        )
        assert ui_resp.status_code == 200
        soup = BeautifulSoup(ui_resp.text, "html.parser")
        assert_all_top_level_oob(soup, ui_resp.text)
        assert_no_booking_leak(ui_resp.text)
        for name in GIVER_NAMES:
            assert name.lower() not in ui_resp.text.lower()
        assert item_received(db, item_id) == 2
        assert receipt_rows(db) == rows_before
        assert len(table_rows(db, "reminder_outbox")) == outbox_before


# ---------------------------------------------------------------------------
# 4. Refusal responses on GET .../edit and GET .../cancel (FR-4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["edit", "cancel"])
def test_get_edit_and_cancel_modal_refusal_for_missing_receipt(tmp_path: Path, action: str) -> None:
    """GET .../edit|cancel for a missing or deleted receipt returns 404 receipt_not_found."""
    with app_env(tmp_path) as (client, sessions, app):
        wishlist_id, item_ids = seed_list(app, [Wish(title="Book", quantity=3)])
        item_id = item_ids[0]
        receipt_id = _record_and_get_receipt_id(client, sessions, wishlist_id, item_id, 1)

        # Concurrently cancel the receipt first.
        del_resp = client.delete(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}",
            headers=bearer(sessions, OWNER_ID, "Alice"),
        )
        assert del_resp.status_code == 200

        for missing_id in (receipt_id, 999_999):
            resp = client.get(
                f"/web/wishlists/{wishlist_id}/items/{item_id}/receipts/{missing_id}/{action}",
                headers=hx(sessions, OWNER_ID),
            )
            assert resp.status_code == 404
            assert resp.headers.get(REFUSAL_HEADER) == "receipt_not_found"
            soup = BeautifulSoup(resp.text, "html.parser")
            assert soup.find("form") is None
            feedback = soup.find(id="receipt-feedback")
            assert feedback is not None
            assert feedback.get_text(strip=True) != ""


@pytest.mark.parametrize("action", ["edit", "cancel"])
def test_get_edit_and_cancel_modal_refusal_for_archived_wishlist(
    tmp_path: Path, action: str
) -> None:
    """GET .../edit|cancel on an archived wishlist returns 409 wishlist_not_active (blocked)."""
    with app_env(tmp_path) as (client, sessions, app):
        wishlist_id, item_ids = seed_list(app, [Wish(title="Watch", quantity=2)])
        item_id = item_ids[0]
        receipt_id = _record_and_get_receipt_id(client, sessions, wishlist_id, item_id, 1)
        run(domain(app).archive_wishlist(wishlist_id, OWNER))

        resp = client.get(
            f"/web/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}/{action}",
            headers=hx(sessions, OWNER_ID),
        )
        assert resp.status_code == 409
        assert resp.headers.get(REFUSAL_HEADER) == "wishlist_not_active"
        soup = BeautifulSoup(resp.text, "html.parser")
        assert soup.find("form") is None
        feedback = soup.find(id="receipt-feedback")
        assert feedback is not None
        assert feedback.get_text(strip=True) != ""
