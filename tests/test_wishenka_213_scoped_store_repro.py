"""Failing repro for WISHENKA-213: single-wishlist mutations must scope WishlistStore hydration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.users.store import UserStore
from wishenka.wishlists.service import WishlistNotFoundError, WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(30)

BACKGROUND_WISHLIST_COUNT = 30


@pytest.mark.asyncio
async def test_single_wishlist_mutations_scope_store_hydration(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Single-wishlist WishlistService mutations must hydrate only the target wishlist."""
    db_path = tmp_path / "wishenka_213_repro.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"
    store = WishlistStore(db_url)
    await store.initialize()
    user_store = UserStore(db_url)

    try:
        for uid, name in (
            (1001, "Owner"),
            (2001, "OtherOwner"),
            (3001, "Gifter"),
            (4001, "Collab"),
            (5001, "ExtraMember"),
        ):
            await user_store.upsert_user(TelegramUser(id=uid, first_name=name))

        owner = AuthenticatedUser(telegram_id=1001, first_name="Owner")
        other_owner = AuthenticatedUser(telegram_id=2001, first_name="OtherOwner")
        gifter = AuthenticatedUser(telegram_id=3001, first_name="Gifter")
        collaborator = AuthenticatedUser(telegram_id=4001, first_name="Collab")
        extra_member = AuthenticatedUser(telegram_id=5001, first_name="ExtraMember")

        service = WishlistService(store=store)

        for idx in range(BACKGROUND_WISHLIST_COUNT):
            bg_wl = await service.create_wishlist(
                owner=other_owner,
                title=f"Background Wishlist {idx}",
            )
            bg_item = await service.add_wish_item(
                wishlist_id=bg_wl.id,
                actor=other_owner,
                title=f"Background Item {idx}",
            )
            await service.add_member(
                wishlist_id=bg_wl.id,
                actor=other_owner,
                user_id=collaborator.telegram_id,
            )
            await service.create_reservation(
                item_id=bg_item.id,
                user=gifter,
                quantity=1,
            )
            await service.get_wishlist_by_public_token(bg_wl.public_token, gifter)
            await service.add_favorite(user=gifter, wishlist_id=bg_wl.id)
            await service.record_view(user=gifter, wishlist_id=bg_wl.id)

        target_wl = await service.create_wishlist(owner=owner, title="Target Wishlist")
        target_wishlist_id = target_wl.id
        item_1 = await service.add_wish_item(
            wishlist_id=target_wishlist_id,
            actor=owner,
            title="Target Item 1",
        )
        item_2 = await service.add_wish_item(
            wishlist_id=target_wishlist_id,
            actor=owner,
            title="Target Item 2",
        )
        item_1_id = item_1.id
        item_2_id = item_2.id
        await service.create_reservation(
            item_id=item_1_id,
            user=gifter,
            quantity=1,
        )

        mutations: list[tuple[str, Callable[[], Awaitable[Any]]]] = [
            (
                "reorder_wish_items",
                lambda: service.reorder_wish_items(
                    target_wishlist_id, owner, [item_2_id, item_1_id]
                ),
            ),
            (
                "add_wish_item",
                lambda: service.add_wish_item(target_wishlist_id, owner, "Target Item 3"),
            ),
            (
                "archive_wish_item",
                lambda: service.archive_wish_item(target_wishlist_id, item_2_id, owner),
            ),
            (
                "update_wishlist_settings",
                lambda: service.update_wishlist_settings(
                    target_wishlist_id,
                    owner,
                    title="Updated Target Wishlist",
                ),
            ),
            (
                "add_member",
                lambda: service.add_member(
                    target_wishlist_id,
                    owner,
                    extra_member.telegram_id,
                ),
            ),
            (
                "regenerate_public_token",
                lambda: service.regenerate_public_token(target_wishlist_id, owner),
            ),
            (
                "add_favorite",
                lambda: service.add_favorite(user=extra_member, wishlist_id=target_wishlist_id),
            ),
        ]

        for op_name, op_call in mutations:
            caplog.clear()
            with caplog.at_level(logging.INFO, logger="wishenka.wishlists.store"):
                await op_call()

            read_records = [
                r for r in caplog.records if getattr(r, "event", None) == "wishlist_store_read"
            ]
            assert len(read_records) == 1, (
                f"{op_name}: expected 1 wishlist_store_read, got {len(read_records)}"
            )
            rec = read_records[0]
            assert getattr(rec, "scoped", None) is True, (
                f"{op_name}: expected scoped=True, got {getattr(rec, 'scoped', None)}"
            )
            assert getattr(rec, "wishlist_id", None) == target_wishlist_id, (
                f"{op_name}: expected wishlist_id={target_wishlist_id}, "
                f"got {getattr(rec, 'wishlist_id', None)}"
            )
            assert getattr(rec, "wishlists_count", None) == 1, (
                f"{op_name}: expected wishlists_count=1, "
                f"got {getattr(rec, 'wishlists_count', None)}"
            )
            assert getattr(rec, "items_count", 0) <= 3, (
                f"{op_name}: expected target-only items_count <= 3, "
                f"got {getattr(rec, 'items_count', None)}"
            )
            assert getattr(rec, "members_count", 0) <= 1, (
                f"{op_name}: expected target-only members_count <= 1, "
                f"got {getattr(rec, 'members_count', None)}"
            )
            assert getattr(rec, "reservations_count", None) == 1, (
                f"{op_name}: expected target-only reservations_count=1, "
                f"got {getattr(rec, 'reservations_count', None)}"
            )
            assert getattr(rec, "history_count", None) == 0, (
                f"{op_name}: expected history_count=0 in scoped mode, "
                f"got {getattr(rec, 'history_count', None)}"
            )
            write_records = [
                r for r in caplog.records if getattr(r, "event", None) == "wishlist_store_write"
            ]
            assert len(write_records) == 1, (
                f"{op_name}: expected 1 wishlist_store_write, got {len(write_records)}"
            )
            wrec = write_records[0]
            assert getattr(wrec, "scoped", None) is True, (
                f"{op_name}: expected write scoped=True, got {getattr(wrec, 'scoped', None)}"
            )
            assert getattr(wrec, "wishlist_id", None) == target_wishlist_id, (
                f"{op_name}: expected write wishlist_id={target_wishlist_id}, "
                f"got {getattr(wrec, 'wishlist_id', None)}"
            )

        async with store.engine.connect() as conn:
            total_lists = (await conn.execute(text("SELECT COUNT(*) FROM wl_lists"))).scalar_one()
            bg_items = (
                await conn.execute(
                    text("SELECT COUNT(*) FROM wl_items WHERE wishlist_id != :wid"),
                    {"wid": target_wishlist_id},
                )
            ).scalar_one()
            bg_members = (
                await conn.execute(
                    text("SELECT COUNT(*) FROM wl_members WHERE wishlist_id != :wid"),
                    {"wid": target_wishlist_id},
                )
            ).scalar_one()
            bg_favs = (
                await conn.execute(
                    text("SELECT COUNT(*) FROM wl_favorites WHERE wishlist_id != :wid"),
                    {"wid": target_wishlist_id},
                )
            ).scalar_one()
            history_rows = (
                await conn.execute(text("SELECT COUNT(*) FROM wl_view_history"))
            ).scalar_one()

        assert total_lists == BACKGROUND_WISHLIST_COUNT + 1
        assert bg_items == BACKGROUND_WISHLIST_COUNT
        assert bg_members == BACKGROUND_WISHLIST_COUNT
        assert bg_favs == BACKGROUND_WISHLIST_COUNT
        assert history_rows > 0
    finally:
        await user_store.engine.dispose()
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_scoped_store_handles_nonexistent_wishlist_id(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scoped reads/writes for a missing wishlist_id must hydrate 0 lists and not touch others."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'wishenka_213_missing.db'}"
    store = WishlistStore(db_url)
    await store.initialize()
    user_store = UserStore(db_url)

    try:
        await user_store.upsert_user(TelegramUser(id=1001, first_name="Owner"))
        owner = AuthenticatedUser(telegram_id=1001, first_name="Owner")
        service = WishlistService(store=store)
        existing = await service.create_wishlist(owner=owner, title="Existing")
        await service.add_wish_item(wishlist_id=existing.id, actor=owner, title="Item 1")

        caplog.clear()
        with (
            caplog.at_level(logging.INFO, logger="wishenka.wishlists.store"),
            pytest.raises(WishlistNotFoundError),
        ):
            await service.get_wishlist_by_id(999999)

        read_records = [
            r for r in caplog.records if getattr(r, "event", None) == "wishlist_store_read"
        ]
        assert len(read_records) == 1
        assert getattr(read_records[0], "wishlists_count", None) == 0
        assert getattr(read_records[0], "history_count", None) == 0

        loaded = await service.get_wishlist_by_id(existing.id)
        assert loaded.title == "Existing"
        assert len(loaded.items) == 1
    finally:
        await user_store.engine.dispose()
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_scoped_token_regeneration_retries_on_cross_wishlist_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scoped token regenerations must retry on global collisions."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'wishenka_213_tokens.db'}"
    store = WishlistStore(db_url)
    await store.initialize()
    user_store = UserStore(db_url)

    try:
        await user_store.upsert_user(TelegramUser(id=1001, first_name="Owner"))
        await user_store.upsert_user(TelegramUser(id=2001, first_name="Other"))
        owner = AuthenticatedUser(telegram_id=1001, first_name="Owner")
        other = AuthenticatedUser(telegram_id=2001, first_name="Other")
        service = WishlistService(store=store)

        wl1 = await service.create_wishlist(owner=owner, title="Target")
        wl2 = await service.create_wishlist(owner=other, title="Other")

        pub_tokens = iter([wl2.public_token, "unique_public_token_213"])
        monkeypatch.setattr(
            "wishenka.wishlists.service.secrets.token_urlsafe",
            lambda _n=16: next(pub_tokens),
        )
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="wishenka.wishlists.store"):
            new_pub = await service.regenerate_public_token(wl1.id, owner)

        assert new_pub == "unique_public_token_213"
        assert any(
            getattr(r, "event", None) == "wishlist_token_collision_retry" for r in caplog.records
        )
        read_records = [
            r for r in caplog.records if getattr(r, "event", None) == "wishlist_store_read"
        ]
        assert all(getattr(r, "wishlists_count", None) == 1 for r in read_records)

        inv_tokens = iter([wl2.invite_token, "unique_invite_token_213"])
        monkeypatch.setattr(
            "wishenka.wishlists.service.secrets.token_urlsafe",
            lambda _n=16: next(inv_tokens),
        )
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="wishenka.wishlists.store"):
            new_inv = await service.regenerate_invite_token(wl1.id, owner)

        assert new_inv == "unique_invite_token_213"
        assert any(
            getattr(r, "event", None) == "wishlist_token_collision_retry" for r in caplog.records
        )
    finally:
        await user_store.engine.dispose()
        await store.engine.dispose()


@pytest.mark.asyncio
async def test_scoped_concurrent_wal_writes(tmp_path: Path) -> None:
    """Concurrent scoped mutations across wishlists must preserve all writes and IDs in WAL mode."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'wishenka_213_wal.db'}"
    store = WishlistStore(db_url)
    await store.initialize()
    user_store = UserStore(db_url)

    try:
        await user_store.upsert_user(TelegramUser(id=1001, first_name="Owner1"))
        await user_store.upsert_user(TelegramUser(id=2001, first_name="Owner2"))
        owner1 = AuthenticatedUser(telegram_id=1001, first_name="Owner1")
        owner2 = AuthenticatedUser(telegram_id=2001, first_name="Owner2")
        service = WishlistService(store=store)

        wl1 = await service.create_wishlist(owner=owner1, title="List 1")
        wl2 = await service.create_wishlist(owner=owner2, title="List 2")

        tasks = [service.add_wish_item(wl1.id, owner1, f"L1 Item {i}") for i in range(6)] + [
            service.add_wish_item(wl2.id, owner2, f"L2 Item {i}") for i in range(6)
        ]
        created = await asyncio.gather(*tasks)

        created_ids = [item.id for item in created]
        assert len(created_ids) == 12
        assert len(set(created_ids)) == 12

        items_1 = await service.list_wish_items(wl1.id, owner1)
        items_2 = await service.list_wish_items(wl2.id, owner2)
        assert len(items_1) == 6
        assert len(items_2) == 6
    finally:
        await user_store.engine.dispose()
        await store.engine.dispose()
