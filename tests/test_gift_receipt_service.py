"""Red tests for the gift receipt domain rules (WISHENKA-23, R-1 to R-5, R-2.1).

They assert the intended behaviour of ``WishlistService`` and ``WishlistStore``. New symbols
are reached lazily, so each test fails on its own with a readable reason today.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.receipt_support import (
    CO_AUTHOR,
    CO_AUTHOR_ID,
    GIFTER,
    OTHER_GIFTER,
    OWNER,
    STRANGER,
    THIRD_GIFTER,
    attr_of,
    exc_class,
    item_of,
    new_symbol,
    open_domain,
    open_store,
    receipt_rows,
    receipts_of,
    seed_wish,
    sql_rows,
)
from wishenka.wishlists.exceptions import (
    CannotReduceQuantityBelowReservedError,
    InsufficientQuantityError,
    PermissionDeniedError,
    WishlistArchivedError,
    WishlistDeletedError,
)
from wishenka.wishlists.models import ReservationStatus, WishlistRole
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)

_NEW_REFUSALS = {"QuantityInvalidError", "QuantityAboveRemainingError", "NothingRemainingError"}


async def _setup(quantity: int | None = 5, **kwargs: Any) -> tuple[WishlistService, int, int]:
    service = WishlistService.in_memory()
    wishlist_id, item_id = await seed_wish(service, quantity=quantity, **kwargs)
    return service, wishlist_id, item_id


async def test_partial_then_full_receipt(tmp_path: Path) -> None:
    """R-1.6, R-2.1: acts add up, the wish leaves the active list after the last one."""
    async with open_domain(tmp_path / "partial.db") as service:
        wishlist_id, item_id = await seed_wish(service, quantity=5)
        item = await service.record_item_fulfillment(item_id, OWNER, 2)
        assert attr_of(item, "remaining_quantity") == 3
        assert attr_of(item, "is_active") is True
        assert [r.quantity for r in receipts_of(item)] == [2]

        item = await service.record_item_fulfillment(item_id, OWNER, 3)
        assert attr_of(item, "remaining_quantity") == 0
        assert attr_of(item, "is_fully_received") is True
        assert attr_of(item, "is_active") is False
        assert attr_of(item, "is_gifted") is True
        assert sum(r.quantity for r in receipts_of(item)) == item.received_quantity == 5

        view = await service.get_wishlist_view(wishlist_id, OWNER)
        assert item_id not in [shown.id for shown in view.items]
        gifted = await service.list_gifted_items(wishlist_id, OWNER)
        assert [entry.id for entry in gifted] == [item_id]


def _scenario_names() -> list[str]:
    return [
        "zero",
        "negative",
        "above_remaining",
        "archived_wish",
        "deleted_list",
        "non_member",
        "gifter",
        "fully_received",
    ]


@asynccontextmanager
async def _refusal_service(
    name: str, tmp_path: Path
) -> AsyncIterator[tuple[WishlistService, int, int]]:
    """Archived and deleted lists are repository outcomes; other refusals stay in memory."""
    if name in {"archived_wish", "deleted_list"}:
        async with open_domain(tmp_path / f"{name}.db") as service:
            wishlist_id, item_id = await seed_wish(service, quantity=5)
            yield service, wishlist_id, item_id
    else:
        yield await _setup(5)


async def _state(service: WishlistService, wishlist_id: int, item_id: int) -> tuple[Any, ...]:
    """Receipt and promise snapshot from the graph, or from the repository when stored."""
    if service._store is None:
        item = item_of(service, item_id)
        receipt_count = len(receipts_of(item))
    else:
        wishlist = await service.get_wishlist_or_none(wishlist_id)
        assert wishlist is not None
        item = next(wish for wish in wishlist.items if wish.id == item_id)

        async def count(conn: Any) -> int:
            value = await conn.scalar(
                text("SELECT COUNT(*) FROM wl_receipts WHERE wish_item_id = :id"),
                {"id": item_id},
            )
            return int(value or 0)

        receipt_count = await service._store.transaction(count)
    return (
        item.received_quantity,
        receipt_count,
        tuple((r.id, r.quantity, r.status) for r in item.reservations),
    )


@pytest.mark.parametrize("name", _scenario_names())
async def test_refusals_closed_reasons(name: str, tmp_path: Path) -> None:
    """R-1.1 to R-1.3, R-1.8: each refusal has its own reason and changes nothing."""
    async with _refusal_service(name, tmp_path) as (service, wishlist_id, item_id):
        await service.create_reservation(item_id=item_id, user=GIFTER, quantity=1)
        actor = OWNER
        quantity = 1
        if name == "zero":
            quantity, expected = 0, "QuantityInvalidError"
        elif name == "negative":
            quantity, expected = -3, "QuantityInvalidError"
        elif name == "above_remaining":
            await service.record_item_fulfillment(item_id, OWNER, 2)
            quantity, expected = 4, "QuantityAboveRemainingError"
        elif name == "archived_wish":
            await service.archive_wish_item(wishlist_id, item_id, OWNER)
            expected = "WishArchivedError"
        elif name == "deleted_list":
            await service.delete_wishlist(wishlist_id, OWNER)
            expected = "WishlistDeletedError"
        elif name == "non_member":
            actor, expected = STRANGER, "PermissionDeniedError"
        elif name == "gifter":
            actor, expected = GIFTER, "PermissionDeniedError"
        else:
            await service.record_item_fulfillment(item_id, OWNER, 5)
            expected = "NothingRemainingError"
        cls = exc_class(expected)
        before = await _state(service, wishlist_id, item_id)

        with pytest.raises(cls) as caught:
            await service.record_item_fulfillment(item_id, actor, quantity)

        assert await _state(service, wishlist_id, item_id) == before
        if expected in _NEW_REFUSALS:
            assert re.search(r"\d", str(caught.value)) is None, "fixed message must hold no numbers"
            assert getattr(cls, "reason", None), "closed refusal must carry a reason"
        if expected == "QuantityAboveRemainingError":
            assert attr_of(caught.value, "remaining_quantity") == 3
        if expected == "NothingRemainingError":
            assert attr_of(caught.value, "remaining_quantity") == 0


async def test_archived_list_owner_gets_list_reason_not_forbidden(tmp_path: Path) -> None:
    """Membership first: the owner of an archived list learns the list state, not 'forbidden'."""
    async with open_domain(tmp_path / "archived-list.db") as service:
        wishlist_id, item_id = await seed_wish(service, quantity=5)
        await service.archive_wishlist(wishlist_id, OWNER)

        with pytest.raises(WishlistArchivedError):
            await service.record_item_fulfillment(item_id, OWNER, 1)
        with pytest.raises(PermissionDeniedError):
            await service.record_item_fulfillment(item_id, STRANGER, 1)


async def test_unpromised_and_unstated_quantity() -> None:
    """R-1.4, R-1.6, corner cases 16, 19: no promise gives a record and no notice."""
    service, _wishlist_id, item_id = await _setup(5)
    await service.record_item_fulfillment(item_id, OWNER, 2)
    assert len(receipts_of(item_of(service, item_id))) == 1
    assert list(attr_of(service, "notice_drafts")) == []

    single_service, _wl, single_id = await _setup(None)
    assert item_of(single_service, single_id).quantity == 1
    await single_service.record_item_fulfillment(single_id, OWNER, 1)
    single = item_of(single_service, single_id)
    assert attr_of(single, "is_fully_received") is True
    assert [r.quantity for r in receipts_of(single)] == [1]
    with pytest.raises(exc_class("NothingRemainingError")):
        await single_service.record_item_fulfillment(single_id, OWNER, 1)


async def test_over_booked_state_and_promise_actions() -> None:
    """R-3.1 to R-3.4, corner cases 2, 3, 13: receipt never touches a promise."""
    service, wishlist_id, item_id = await _setup(5)
    first = await service.create_reservation(item_id=item_id, user=GIFTER, quantity=3)
    second = await service.create_reservation(item_id=item_id, user=OTHER_GIFTER, quantity=2)
    promises_before = [
        (r.id, r.user_id, r.quantity, r.status) for r in item_of(service, item_id).reservations
    ]

    await service.record_item_fulfillment(item_id, OWNER, 2)
    item = item_of(service, item_id)
    assert len(receipts_of(item)) == 1
    promises_after = [(r.id, r.user_id, r.quantity, r.status) for r in item.reservations]
    assert promises_after == promises_before
    assert item.received_quantity + item.reserved_quantity > item.quantity
    assert item.available_quantity == 0

    with pytest.raises(InsufficientQuantityError):
        await service.create_reservation(item_id=item_id, user=THIRD_GIFTER, quantity=1)
    with pytest.raises(InsufficientQuantityError):
        await service.update_reservation_quantity(first.id, GIFTER, 4)

    await service.update_reservation_quantity(first.id, GIFTER, 2)
    await service.mark_reservation_purchased(second.id, OTHER_GIFTER)
    await service.revert_reservation_to_active(second.id, OTHER_GIFTER)
    await service.cancel_reservation(first.id, GIFTER)
    cancelled = service._reservations[first.id]
    assert cancelled.status == ReservationStatus.CANCELLED
    assert service._reservations[second.id].status == ReservationStatus.ACTIVE
    assert wishlist_id


async def test_open_promise_on_fully_received_wish_stays_visible(tmp_path: Path) -> None:
    """R-5.4, corner case 4: the giver keeps the promise, marked as received."""
    async with open_domain(tmp_path / "promise.db") as service:
        wishlist_id, item_id = await seed_wish(service, quantity=2)
        promise = await service.create_reservation(item_id=item_id, user=GIFTER, quantity=2)

        await service.record_item_fulfillment(item_id, OWNER, 2)

        assert await service.get_reservation_status(promise.id) == ReservationStatus.ACTIVE
        cabinet = await service.get_user_reservations(GIFTER.telegram_id)
        assert [row.reservation_id for row in cabinet] == [promise.id]
        assert attr_of(cabinet[0], "is_fully_received") is True
        giver_view = await service.get_wish_item(wishlist_id, item_id, GIFTER)
        assert attr_of(giver_view, "is_fully_received") is True
        assert attr_of(giver_view, "remaining_quantity") == 0
        cancelled = await service.cancel_reservation(promise.id, GIFTER)
        assert cancelled.status == ReservationStatus.CANCELLED


async def test_reduction_lock_after_receipt() -> None:
    """FR-5 / Q12: lowering below received stays refused, while lowering to received succeeds."""
    service, _wishlist_id, item_id = await _setup(5)
    await service.create_reservation(item_id=item_id, user=GIFTER, quantity=2)
    await service.record_item_fulfillment(item_id, OWNER, 2)

    with pytest.raises(CannotReduceQuantityBelowReservedError):
        await service.update_wish_item(item_id, OWNER, quantity=1)
    await service.update_wish_item(item_id, OWNER, quantity=2)
    assert item_of(service, item_id).quantity == 2


async def test_views_share_one_active_predicate(tmp_path: Path) -> None:
    """R-4.1, R-4.6: view, list, reorder, restore tail and projection agree on 'active'."""
    async with open_domain(tmp_path / "views.db") as service:
        await _views_share_one_active_predicate(service)


async def _views_share_one_active_predicate(service: WishlistService) -> None:
    wishlist_id, partly_id = await seed_wish(service, quantity=4, title="Partly")
    plain = await service.add_wish_item(wishlist_id=wishlist_id, actor=OWNER, title="Plain")
    archived = await service.add_wish_item(wishlist_id=wishlist_id, actor=OWNER, title="Archived")
    done = await service.add_wish_item(wishlist_id=wishlist_id, actor=OWNER, title="Done")
    await service.record_item_fulfillment(partly_id, OWNER, 1)
    await service.record_item_fulfillment(done.id, OWNER, 1)
    await service.archive_wish_item(wishlist_id, archived.id, OWNER)

    view = await service.get_wishlist_view(wishlist_id, OWNER)
    assert {i.id for i in view.items} == {partly_id, plain.id}
    assert {i.id for i in view.archived_items} == {archived.id}
    active = await service.list_wish_items(wishlist_id, OWNER)
    assert {i.id for i in active} == {partly_id, plain.id}
    everything = await service.list_wish_items(wishlist_id, OWNER, include_archived=True)
    assert {i.id for i in everything} == {partly_id, plain.id, archived.id, done.id}

    reordered = await service.reorder_wish_items(wishlist_id, OWNER, [plain.id, partly_id])
    assert [i.id for i in reordered] == [plain.id, partly_id]
    await service.restore_wish_item(wishlist_id, archived.id, OWNER)
    wishlist = await service.get_wishlist_by_id(wishlist_id)
    orders = {i.id: i.display_order for i in wishlist.items}
    assert orders[archived.id] == max(orders[plain.id], orders[partly_id]) + 1


async def test_projection_active_flag_and_public_filter(tmp_path: Path) -> None:
    """R-4.6, R-5.1: the JSON projection carries ``is_active`` and ``remaining_quantity``."""
    from wishenka.web.routes.wishlists import projection

    async with open_domain(tmp_path / "projection.db") as service:
        wishlist_id, item_id = await seed_wish(service, quantity=4)
        done = await service.add_wish_item(wishlist_id=wishlist_id, actor=OWNER, title="Done")
        await service.record_item_fulfillment(item_id, OWNER, 1)
        await service.record_item_fulfillment(done.id, OWNER, 1)
        wishlist = await service.get_wishlist_by_id(wishlist_id)

        member = projection(wishlist, OWNER, False)
        by_id = {entry["id"]: entry for entry in member["items"]}
        assert by_id[item_id]["remaining_quantity"] == 3
        assert by_id[item_id]["is_active"] is True
        assert by_id[done.id]["is_active"] is False
        public = projection(wishlist, None, True)
        assert done.id not in [entry["id"] for entry in public["items"]]
        assert item_id in [entry["id"] for entry in public["items"]]


async def _mark_archived(service: WishlistService, item_id: int) -> None:
    """Store a legacy archived row without going through the archive rule."""

    async def write(conn: Any) -> None:
        await conn.execute(
            text("UPDATE wl_items SET is_archived = 1 WHERE id = :id"),
            {"id": item_id},
        )

    store = service._store
    assert store is not None
    await store.transaction(write)


async def test_archive_split_and_restore(tmp_path: Path) -> None:
    """R-4.2 to R-4.4, corner cases 10, 11: only the unreceived part moves."""
    async with open_domain(tmp_path / "archive.db") as service:
        await _archive_split_and_restore(service)


async def _archive_split_and_restore(service: WishlistService) -> None:
    wishlist_id, item_id = await seed_wish(service, quantity=4)
    promise = await service.create_reservation(item_id=item_id, user=GIFTER, quantity=1)
    await service.record_item_fulfillment(item_id, OWNER, 1)

    await service.archive_wish_item(wishlist_id, item_id, OWNER)
    view = await service.get_wishlist_view(wishlist_id, OWNER)
    assert [(i.id, attr_of(i, "remaining_quantity")) for i in view.archived_items] == [(item_id, 3)]
    gifted = await attr_of(service, "list_gifted_items")(wishlist_id, OWNER)
    assert [(g.id, g.received_quantity, g.is_archived) for g in gifted] == [(item_id, 1, True)]
    assert await service.get_reservation_status(promise.id) == ReservationStatus.ACTIVE

    await service.restore_wish_item(wishlist_id, item_id, OWNER)
    view = await service.get_wishlist_view(wishlist_id, OWNER)
    assert [(i.id, attr_of(i, "remaining_quantity")) for i in view.items] == [(item_id, 3)]
    gifted = await attr_of(service, "list_gifted_items")(wishlist_id, OWNER)
    assert [g.id for g in gifted] == [item_id]

    done = await service.add_wish_item(wishlist_id=wishlist_id, actor=OWNER, title="Done")
    await service.record_item_fulfillment(done.id, OWNER, 1)
    nothing_remaining = exc_class("NothingRemainingError")
    with pytest.raises(nothing_remaining):
        await service.archive_wish_item(wishlist_id, done.id, OWNER)
    await _mark_archived(service, done.id)
    with pytest.raises(nothing_remaining):
        await service.restore_wish_item(wishlist_id, done.id, OWNER)


async def test_legacy_rows_in_views(tmp_path: Path) -> None:
    """R-4.5: an archived fully received row is only in the gifted view."""
    async with open_domain(tmp_path / "legacy.db") as service:
        wishlist_id, full_id = await seed_wish(service, quantity=2, title="Full")
        partly = await service.add_wish_item(
            wishlist_id=wishlist_id, actor=OWNER, title="Partly", quantity=4
        )

        async def write(conn: Any) -> None:
            await conn.execute(
                text(
                    "UPDATE wl_items SET received_quantity = :received, is_archived = 1 "
                    "WHERE id = :id"
                ),
                {"received": 2, "id": full_id},
            )
            await conn.execute(
                text(
                    "UPDATE wl_items SET received_quantity = :received, is_archived = 1 "
                    "WHERE id = :id"
                ),
                {"received": 1, "id": partly.id},
            )

        store = service._store
        assert store is not None
        await store.transaction(write)

        view = await service.get_wishlist_view(wishlist_id, OWNER)
        assert [(i.id, attr_of(i, "remaining_quantity")) for i in view.archived_items] == [
            (partly.id, 3)
        ]
        gifted = await service.list_gifted_items(wishlist_id, OWNER)
        assert {g.id for g in gifted} == {full_id, partly.id}


async def test_gifted_read_authors_only_no_giver(tmp_path: Path) -> None:
    """R-5.2, R-2.3, R-2.4: authors read dated receipts, nobody else does."""
    async with open_domain(tmp_path / "gifted.db") as service:
        wishlist_id, item_id = await seed_wish(service, quantity=5)
        await _gifted_read_authors_only_no_giver(service, wishlist_id, item_id)


async def _gifted_read_authors_only_no_giver(
    service: WishlistService, wishlist_id: int, item_id: int
) -> None:
    await service.create_reservation(item_id=item_id, user=GIFTER, quantity=1)
    await service.add_member(wishlist_id, OWNER, CO_AUTHOR_ID, WishlistRole.MEMBER)
    await service.record_item_fulfillment(item_id, OWNER, 2)
    read = attr_of(service, "list_gifted_items")

    for author in (OWNER, CO_AUTHOR):
        entries = await read(wishlist_id, author)
        assert [e.id for e in entries] == [item_id]
        assert [(r.quantity, r.is_approximate) for r in entries[0].receipts] == [(2, False)]
        assert entries[0].receipts[0].received_at is not None
    for outsider in (GIFTER, STRANGER, None):
        with pytest.raises(PermissionDeniedError):
            await read(wishlist_id, outsider)

    await service.archive_wishlist(wishlist_id, OWNER)
    assert [e.id for e in await read(wishlist_id, OWNER)] == [item_id]
    unarchived = await service.unarchive_wishlist(wishlist_id, OWNER)
    assert unarchived.id == wishlist_id
    await service.delete_wishlist(wishlist_id, OWNER)
    with pytest.raises(WishlistDeletedError):
        await read(wishlist_id, OWNER)


def test_gifted_dto_has_no_promise_fields() -> None:
    """R-5.2, R-8.1: no giver, promise, booking or action field in the gifted data."""
    dto = new_symbol("wishenka.wishlists.schemas", "GiftedItemDTO")
    entry = new_symbol("wishenka.wishlists.schemas", "ReceiptEntryDTO")
    forbidden = ("reserv", "giver", "gifter", "promise", "purchase", "available", "href", "action")
    for name in (*dto.model_fields, *entry.model_fields):
        assert not any(mark in name for mark in forbidden), name
    assert set(entry.model_fields) == {"id", "received_at", "quantity", "is_approximate"}
    assert {"remaining_quantity", "received_quantity", "receipts"} <= set(dto.model_fields)


async def test_receipt_flushed_in_both_store_paths(tmp_path: Path) -> None:
    """R-1.8, R-2.1: the record is written with the counter by execute_wish and by execute."""
    async with open_store(tmp_path / "paths.db") as store:

        async def setup(service: WishlistService) -> int:
            _wishlist_id, item_id = await seed_wish(service, quantity=6)
            return item_id

        item_id = await store.execute(setup)

        async def receive_two(service: WishlistService) -> None:
            await service.record_item_fulfillment(item_id, OWNER, 2)

        async def receive_one(service: WishlistService) -> None:
            await service.record_item_fulfillment(item_id, OWNER, 1)

        await store.execute_wish(
            receive_two, item_id=item_id, operation_name="record_item_fulfillment"
        )
        await store.execute(receive_one)

        db = tmp_path / "paths.db"
        rows = receipt_rows(db)
        assert [row["quantity"] for row in rows] == [2, 1]
        counter = sql_rows(db, "SELECT received_quantity FROM wl_items WHERE id = ?", (item_id,))
        assert counter[0]["received_quantity"] == sum(row["quantity"] for row in rows) == 3
