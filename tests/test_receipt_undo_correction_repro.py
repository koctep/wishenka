"""Red failing repro tests for WISHENKA-153 (undo and correction of gift receipt).

Covers the five repro groups from ai-tasks/WISHENKA-153/20-architecture.md:
1. Cancel & active list / archive / over-booking / edit-quantity lock / cabinet marker.
2. Correction invariants (date & approximate flag preservation, no-op, validation).
3. Guards & concurrency (archived list, non-member, concurrent double cancel).
4. Notifications (receipt_reverted on cancel/downward, receipt_increased on upward,
   privacy, settings, cancelled promises, delivery failure resilience).
5. JSON API (DELETE / PATCH) & UI routes (edit/cancel modals, OOB updates,
   X-Receipt-Refusal, read-only gifted section on archived lists).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup

from tests.notice_support import FakeNoticeSender, send_result
from tests.receipt_support import (
    CO_AUTHOR,
    GIFTER,
    GIFTER_ID,
    OTHER_GIFTER,
    OWNER,
    OWNER_ID,
    STRANGER,
    STRANGER_ID,
    app_env,
    attr_of,
    bearer,
    exc_class,
    item_received,
    open_store,
    receipt_rows,
    seed_wish,
    sql_exec,
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
from tests.test_receipt_notices import _Env
from wishenka.wishlists.exceptions import (
    PermissionDeniedError,
    QuantityAboveRemainingError,
    QuantityInvalidError,
    WishlistArchivedError,
)
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(20)


# ---------------------------------------------------------------------------
# 1. Cancel & active list / archive / over-booking / cabinet marker
# ---------------------------------------------------------------------------


async def test_cancel_receipt_restores_active_list_ends_overbooking_and_keeps_archive(
    tmp_path: Path,
) -> None:
    db = tmp_path / "cancel_state.db"
    async with open_store(db) as store:
        # 1a. Fully received wish (5/5) with an open promise of 3 and another of 4 (over-booked).
        async def setup(service: WishlistService) -> tuple[int, int]:
            wishlist_id, item_id = await seed_wish(service, quantity=5, title="Espresso")
            await service.create_reservation(item_id, GIFTER, quantity=3, wishlist_id=wishlist_id)
            await service.record_item_fulfillment(item_id, OWNER, 5, wishlist_id=wishlist_id)
            return wishlist_id, item_id

        wishlist_id, item_id = await store.execute(setup)
        receipt_id = receipt_rows(db)[-1]["id"]
        assert item_received(db, item_id) == 5
        assert len(receipt_rows(db)) == 1

        # Cabinet marker is currently True because item is fully received.
        async def check_cabinet_before(service: WishlistService) -> bool:
            res = await service.get_user_reservations(GIFTER_ID)
            return res[0].is_fully_received

        assert await store.execute(check_cabinet_before) is True

        # Cancel the receipt.
        async def do_cancel(service: WishlistService) -> Any:
            cancel_fn = attr_of(service, "cancel_item_receipt")
            return await cancel_fn(item_id, receipt_id, OWNER, wishlist_id=wishlist_id)

        updated = await store.execute_wish(
            do_cancel, item_id=item_id, operation_name="cancel_item_receipt"
        )
        assert updated.received_quantity == 0
        assert updated.remaining_quantity == 5
        assert updated.is_active is True
        assert updated.is_fully_received is False
        assert updated.available_quantity == 2  # 5 - 0 - 3 = 2 (over-booking ended)
        assert item_received(db, item_id) == 0
        assert receipt_rows(db) == []

        # Removed from list_gifted_items when received_quantity == 0.
        async def check_after(service: WishlistService) -> tuple[list[Any], bool]:
            gifted = await service.list_gifted_items(wishlist_id, OWNER)
            res = await service.get_user_reservations(GIFTER_ID)
            # Edit-quantity lock lowered: can reduce requested quantity from 5 to 3 (= occupied).
            edited = await service.update_wish_item(item_id, OWNER, quantity=3)
            return gifted, res[0].is_fully_received and edited.quantity == 3

        gifted, cabinet_still_received = await store.execute(check_after)
        assert gifted == []
        assert cabinet_still_received is False

        # 1b. Wish with archived unreceived remainder stays in archive on cancel.
        async def setup_archived_remainder(service: WishlistService) -> int:
            item2 = await service.add_wish_item(
                wishlist_id=wishlist_id, actor=OWNER, title="Grinder", quantity=5
            )
            await service.record_item_fulfillment(item2.id, OWNER, 2, wishlist_id=wishlist_id)
            await service.archive_wish_item(wishlist_id, item2.id, OWNER)
            return item2.id

        item2_id = await store.execute(setup_archived_remainder)
        r2_id = receipt_rows(db)[-1]["id"]

        async def cancel_archived_remainder(service: WishlistService) -> Any:
            cancel_fn = attr_of(service, "cancel_item_receipt")
            return await cancel_fn(item2_id, r2_id, OWNER, wishlist_id=wishlist_id)

        item2_after = await store.execute_wish(
            cancel_archived_remainder, item_id=item2_id, operation_name="cancel_item_receipt"
        )
        assert item2_after.received_quantity == 0
        assert item2_after.remaining_quantity == 5
        assert item2_after.is_archived is True
        assert item2_after.is_in_archive is True
        assert item2_after.is_active is False


# ---------------------------------------------------------------------------
# 2. Correction & invariants
# ---------------------------------------------------------------------------


async def test_correct_receipt_preserves_date_and_approximate_and_validates(
    tmp_path: Path,
) -> None:
    db = tmp_path / "correct.db"
    async with open_store(db) as store:

        async def setup(service: WishlistService) -> tuple[int, int]:
            wishlist_id, item_id = await seed_wish(service, quantity=5, title="Teapot")
            await service.create_reservation(item_id, GIFTER, quantity=4, wishlist_id=wishlist_id)
            await service.record_item_fulfillment(item_id, OWNER, 4, wishlist_id=wishlist_id)
            return wishlist_id, item_id

        wishlist_id, item_id = await store.execute(setup)
        receipt_id = receipt_rows(db)[-1]["id"]
        # Mark receipt as legacy approximate with a fixed historical timestamp.
        orig_ts = "2023-05-01T12:00:00+00:00"
        sql_exec(
            db,
            "UPDATE wl_receipts SET received_at = ?, is_approximate = 1 WHERE id = ?",
            (orig_ts, receipt_id),
        )

        # Downward correction 4 -> 1 ends over-booking (1 + 4 == 5, free == 0).
        # Let's correct 4 -> 1 (occupied=4 -> 1+4=5, not overbooked) then check date/approx.
        async def correct_to(qty: int) -> Any:
            async def act(service: WishlistService) -> Any:
                correct_fn = attr_of(service, "correct_item_receipt")
                return await correct_fn(item_id, receipt_id, OWNER, qty, wishlist_id=wishlist_id)

            return await store.execute_wish(
                act, item_id=item_id, operation_name="correct_item_receipt"
            )

        down = await correct_to(1)
        assert down.received_quantity == 1
        assert down.remaining_quantity == 4
        assert down.receipts[0].received_at.isoformat().startswith("2023-05-01T12:00:00")
        assert down.receipts[0].is_approximate is True

        # Same-quantity correction is a no-op (updated_at unchanged).
        before_updated = down.updated_at
        noop = await correct_to(1)
        assert noop.updated_at == before_updated

        # Upward correction 1 -> 3 preserves date & approximate.
        up = await correct_to(3)
        assert up.received_quantity == 3
        assert up.remaining_quantity == 2
        assert up.receipts[0].received_at.isoformat().startswith("2023-05-01T12:00:00")
        assert up.receipts[0].is_approximate is True

        # Invalid quantities: <= 0 raises QuantityInvalidError; > 5 raises above-remaining.
        with pytest.raises(QuantityInvalidError):
            await correct_to(0)
        with pytest.raises(QuantityInvalidError):
            await correct_to(-2)
        with pytest.raises(QuantityAboveRemainingError) as exc_info:
            await correct_to(6)
        assert exc_info.value.remaining_quantity == 5
        assert "4" not in str(exc_info.value)  # must not leak occupied=4


# ---------------------------------------------------------------------------
# 3. Guards & concurrency
# ---------------------------------------------------------------------------


async def test_guards_and_concurrent_double_cancel(tmp_path: Path) -> None:
    db = tmp_path / "guards.db"
    async with open_store(db) as store:

        async def setup(service: WishlistService) -> tuple[int, int]:
            wishlist_id, item_id = await seed_wish(service, quantity=3, title="Mug")
            await service.record_item_fulfillment(item_id, OWNER, 2, wishlist_id=wishlist_id)
            return wishlist_id, item_id

        wishlist_id, item_id = await store.execute(setup)
        receipt_id = receipt_rows(db)[-1]["id"]

        # Non-member cannot cancel or correct.
        async def stranger_cancel(service: WishlistService) -> None:
            cancel_fn = attr_of(service, "cancel_item_receipt")
            await cancel_fn(item_id, receipt_id, STRANGER, wishlist_id=wishlist_id)

        with pytest.raises(PermissionDeniedError):
            await store.execute_wish(stranger_cancel, item_id=item_id)

        # Concurrent double cancel: first succeeds, second raises ReceiptNotFoundError.
        receipt_not_found_cls = exc_class("ReceiptNotFoundError")

        async def cancel_once() -> str:
            async def act(service: WishlistService) -> None:
                cancel_fn = attr_of(service, "cancel_item_receipt")
                await cancel_fn(item_id, receipt_id, OWNER, wishlist_id=wishlist_id)

            try:
                await store.execute_wish(act, item_id=item_id, operation_name="cancel_item_receipt")
                return "ok"
            except receipt_not_found_cls:
                return "not_found"

        results = await asyncio.gather(cancel_once(), cancel_once())
        assert sorted(results) == ["not_found", "ok"]

        # Re-record and archive the wishlist -> cancel/correct must raise WishlistArchivedError.
        async def record_and_archive(service: WishlistService) -> None:
            await service.record_item_fulfillment(item_id, OWNER, 1, wishlist_id=wishlist_id)
            await service.archive_wishlist(wishlist_id, OWNER)

        await store.execute(record_and_archive)
        r2_id = receipt_rows(db)[-1]["id"]

        async def archived_cancel(service: WishlistService) -> None:
            cancel_fn = attr_of(service, "cancel_item_receipt")
            await cancel_fn(item_id, r2_id, OWNER, wishlist_id=wishlist_id)

        with pytest.raises(WishlistArchivedError):
            await store.execute_wish(archived_cancel, item_id=item_id)


# ---------------------------------------------------------------------------
# 4. Notifications (without live Telegram)
# ---------------------------------------------------------------------------


async def test_undo_and_correction_notifications_and_resilience(tmp_path: Path) -> None:
    db = tmp_path / "notices.db"
    async with open_store(db) as store:
        env = _Env(store, db, verify_destinations=True)
        await env.seed(
            quantity=5,
            promises=((GIFTER, 2), (OTHER_GIFTER, 1)),
            title="Camera",
            list_title="Trip",
        )
        wishlist_id, item_id = env.wishlist_id, env.item_id

        # OTHER_GIFTER cancels their promise before receipt; GIFTER keeps theirs.
        await env.cancel(OTHER_GIFTER)

        async def record_initial(service: WishlistService) -> None:
            await service.record_item_fulfillment(item_id, OWNER, 3, wishlist_id=wishlist_id)

        await store.execute(record_initial)
        receipt_id = receipt_rows(db)[-1]["id"]
        sender = FakeNoticeSender()
        worker = env.worker(sender)
        now = int(time.time()) + 10
        await worker.run_once(now)
        assert len(sender.calls) == 1
        assert sender.calls[0][0] == GIFTER_ID

        # Upward correction 3 -> 4 delivers standard gift_received notice.
        async def correct_up(service: WishlistService) -> None:
            correct_fn = attr_of(service, "correct_item_receipt")
            await correct_fn(item_id, receipt_id, OWNER, 4, wishlist_id=wishlist_id)

        await store.execute_wish(correct_up, item_id=item_id, operation_name="correct_item_receipt")
        await worker.run_once(now + 1)
        assert len(sender.calls) == 2
        assert sender.calls[1][0] == GIFTER_ID
        assert "Camera" in sender.calls[1][1]

        # Downward correction 4 -> 2 delivers receipt_reverted notice (no quantities/names).
        async def correct_down(service: WishlistService) -> None:
            correct_fn = attr_of(service, "correct_item_receipt")
            await correct_fn(item_id, receipt_id, OWNER, 2, wishlist_id=wishlist_id)

        await store.execute_wish(
            correct_down, item_id=item_id, operation_name="correct_item_receipt"
        )
        await worker.run_once(now + 2)
        assert len(sender.calls) == 3
        chat_id, text = sender.calls[2]
        assert chat_id == GIFTER_ID
        assert "Camera" in text and "Trip" in text
        assert not any(digit in text for digit in ("2", "4", "5"))
        assert "Oleg" not in text

        # Cancel with a failing sender does not roll back the receipt cancellation.
        failing_sender = FakeNoticeSender([send_result("rejected")])
        failing_worker = env.worker(failing_sender)

        async def do_cancel(service: WishlistService) -> None:
            cancel_fn = attr_of(service, "cancel_item_receipt")
            await cancel_fn(item_id, receipt_id, OWNER, wishlist_id=wishlist_id)

        await store.execute_wish(do_cancel, item_id=item_id, operation_name="cancel_item_receipt")
        await failing_worker.run_once(now + 3)
        assert item_received(db, item_id) == 0
        assert receipt_rows(db) == []
        assert len(failing_sender.calls) == 1

        # Disabled gift_received setting suppresses receipt_reverted notice.
        env.settings_user(GIFTER_ID, False)

        async def record_again(service: WishlistService) -> None:
            await service.record_item_fulfillment(item_id, OWNER, 1, wishlist_id=wishlist_id)

        await store.execute(record_again)
        r2_id = receipt_rows(db)[-1]["id"]
        suppressed_sender = FakeNoticeSender()
        suppressed_worker = env.worker(suppressed_sender)
        await suppressed_worker.run_once(now + 4)

        async def cancel_again(service: WishlistService) -> None:
            cancel_fn = attr_of(service, "cancel_item_receipt")
            await cancel_fn(item_id, r2_id, OWNER, wishlist_id=wishlist_id)

        await store.execute_wish(
            cancel_again, item_id=item_id, operation_name="cancel_item_receipt"
        )
        await suppressed_worker.run_once(now + 5)
        assert suppressed_sender.calls == []


# ---------------------------------------------------------------------------
# 5. JSON API & UI routes
# ---------------------------------------------------------------------------


def test_json_and_ui_routes_for_undo_and_correction(tmp_path: Path) -> None:
    with app_env(tmp_path) as env:
        client, sessions, app = env
        svc = domain(app)
        wishlist_id, item_ids = seed_list(
            app,
            [Wish(title="Lamp", quantity=5)],
            members=(CO_AUTHOR,),
        )
        item_id = item_ids[0]
        run(svc.create_reservation(item_id, GIFTER, quantity=2, wishlist_id=wishlist_id))
        run(svc.create_reservation(item_id, OTHER_GIFTER, quantity=1, wishlist_id=wishlist_id))

        # Record 5 units (fully received) via existing JSON endpoint.
        resp = client.post(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts",
            json={"quantity": 5},
            headers=bearer(sessions, OWNER_ID, "Alice"),
        )
        assert resp.status_code == 201

        gifted = client.get(
            f"/api/wishlists/{wishlist_id}/gifted",
            headers=bearer(sessions, OWNER_ID, "Alice"),
        )
        assert gifted.status_code == 200
        receipt_id = gifted.json()[0]["receipts"][0]["id"]
        assert receipt_id > 0

        # PATCH JSON: correct 5 -> 2.
        patch_resp = client.patch(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}",
            json={"quantity": 2},
            headers={**bearer(sessions, OWNER_ID, "Alice"), "Idempotency-Key": "patch-1"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["received_now"] == 2
        assert patch_resp.json()["received_quantity"] == 2
        assert patch_resp.json()["remaining_quantity"] == 3

        # UI GET edit modal & POST edit 2 -> 3.
        edit_url = f"/web/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}/edit"
        edit_modal = client.get(edit_url, headers=hx(sessions, OWNER_ID))
        assert edit_modal.status_code == 200
        assert 'name="quantity"' in edit_modal.text
        assert_no_booking_leak(edit_modal.text)

        edit_post = client.post(edit_url, data={"quantity": "3"}, headers=hx(sessions, OWNER_ID))
        assert edit_post.status_code == 200
        edit_soup = BeautifulSoup(edit_post.text, "html.parser")
        assert_all_top_level_oob(edit_soup, edit_post.text)
        assert edit_soup.find("div", attrs={"hx-swap-oob": "innerHTML:#items-list"}) is not None
        for elem_id in (
            "item-modal-container",
            "list-notice",
            "gifted-items-section",
            "archived-items-section",
        ):
            assert edit_soup.find(id=elem_id) is not None
        assert_no_booking_leak(str(edit_soup.find(id="list-notice")))
        assert_no_booking_leak(str(edit_soup.find(id="gifted-items-section")))
        for name in GIVER_NAMES:
            assert name not in edit_post.text.lower()

        # UI GET cancel confirmation modal & POST cancel.
        cancel_url = f"/web/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}/cancel"
        cancel_modal = client.get(cancel_url, headers=hx(sessions, OWNER_ID))
        assert cancel_modal.status_code == 200
        assert cancel_url in cancel_modal.text
        assert_no_booking_leak(cancel_modal.text)

        # Stranger cannot cancel via UI (403 + X-Receipt-Refusal).
        stranger_cancel = client.post(cancel_url, headers=hx(sessions, STRANGER_ID, "Sven"))
        assert stranger_cancel.status_code == 403
        assert stranger_cancel.headers.get(REFUSAL_HEADER) == "forbidden"

        # Owner cancels via UI.
        cancel_post = client.post(cancel_url, headers=hx(sessions, OWNER_ID))
        assert cancel_post.status_code == 200
        soup = BeautifulSoup(cancel_post.text, "html.parser")
        assert_no_booking_leak(str(soup.find(id="list-notice")))
        gifted_sec = soup.find(id="gifted-items-section")
        assert_no_booking_leak(str(gifted_sec))
        for name in GIVER_NAMES:
            assert name not in cancel_post.text.lower()
        assert gifted_sec is not None
        assert "Lamp" not in gifted_sec.get_text()

        # Re-record and test DELETE JSON endpoint.
        resp2 = client.post(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts",
            json={"quantity": 2},
            headers=bearer(sessions, OWNER_ID, "Alice"),
        )
        assert resp2.status_code == 201
        r2_id = client.get(
            f"/api/wishlists/{wishlist_id}/gifted",
            headers=bearer(sessions, OWNER_ID, "Alice"),
        ).json()[0]["receipts"][0]["id"]

        del_resp = client.delete(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts/{r2_id}",
            headers={**bearer(sessions, OWNER_ID, "Alice"), "Idempotency-Key": "del-1"},
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["received_now"] == 0
        assert del_resp.json()["received_quantity"] == 0

        # Re-record and archive list -> «Подаренные» on detail page has no edit/cancel controls.
        client.post(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts",
            json={"quantity": 1},
            headers=bearer(sessions, OWNER_ID, "Alice"),
        )
        run(svc.archive_wishlist(wishlist_id, OWNER))
        detail = client.get(f"/web/wishlists/{wishlist_id}", headers=hx(sessions, OWNER_ID))
        assert detail.status_code == 200
        assert "/receipts/" not in detail.text
        detail_soup = BeautifulSoup(detail.text, "html.parser")
        detail_gifted = detail_soup.find(id="gifted-items-section")
        assert detail_gifted is not None
        assert_no_booking_leak(str(detail_gifted))
        for name in GIVER_NAMES:
            assert name not in detail.text.lower()
