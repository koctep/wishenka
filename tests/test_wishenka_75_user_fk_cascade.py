"""Failing reproduction tests for WISHENKA-75 user FK constraints and cascade cleanup."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest
from alembic import command

from tests.receipt_support import (
    GIFTER,
    GIFTER_ID,
    OWNER,
    OWNER_ID,
    app_env,
    db_path_of,
    make_user,
    open_store,
    sql_rows,
)
from wishenka.auth.models import TelegramUser
from wishenka.users.store import UserStore
from wishenka.wishlists.deletion import AccountDeletionService
from wishenka.wishlists.migrations import _configured, upgrade_to_head_sync
from wishenka.wishlists.models import WishlistRole

pytestmark = pytest.mark.timeout(30)

NONEXISTENT_USER_ID = 999_999
MEMBER_A_ID = 404
MEMBER_B_ID = 505


async def test_rejects_wishlist_user_links_for_nonexistent_user(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Inserting favorite, view history, or member for missing user_id must raise IntegrityError."""
    with app_env(tmp_path, "fk-reject.db") as (_, _, app):
        user_store = app.state.user_store
        await user_store.upsert_user(TelegramUser(id=OWNER_ID, first_name="Owner"))

        db = Path(db_path_of(app))
        ghost_user = make_user(NONEXISTENT_USER_ID, "Ghost")

        async with open_store(db) as store:
            wl = await store.execute(
                lambda svc: svc.create_wishlist(owner=OWNER, title="Collab List")
            )

            caplog.clear()
            with caplog.at_level(logging.ERROR, logger="wishenka.wishlists.store"):
                with pytest.raises(RuntimeError, match="Wishlist storage operation failed"):
                    await store.execute(
                        lambda svc: svc.add_favorite(user=ghost_user, wishlist_id=wl.id)
                    )

                with pytest.raises(RuntimeError, match="Wishlist storage operation failed"):
                    await store.execute(
                        lambda svc: svc.record_view(user=ghost_user, wishlist_id=wl.id)
                    )

                with pytest.raises(RuntimeError, match="Wishlist storage operation failed"):
                    await store.execute(
                        lambda svc: svc.add_member(
                            wishlist_id=wl.id,
                            actor=OWNER,
                            user_id=NONEXISTENT_USER_ID,
                            role=WishlistRole.MEMBER,
                        )
                    )

        integrity_logs = [
            rec
            for rec in caplog.records
            if getattr(rec, "event", None) == "wishlist_store_integrity_error"
        ]
        assert len(integrity_logs) == 3
        assert all(rec.levelno == logging.ERROR for rec in integrity_logs)
        assert str(NONEXISTENT_USER_ID) not in caplog.text
        assert "Ghost" not in caplog.text

        now = "2026-01-01T00:00:00+00:00"
        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO wl_favorites(user_id, wishlist_id, created_at) VALUES (?, ?, ?)",
                    (NONEXISTENT_USER_ID, wl.id, now),
                )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO wl_view_history(user_id, wishlist_id, viewed_at) VALUES (?, ?, ?)",
                    (NONEXISTENT_USER_ID, wl.id, now),
                )
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO wl_members(wishlist_id, user_id, role, joined_at) "
                    "VALUES (?, ?, 'member', ?)",
                    (wl.id, NONEXISTENT_USER_ID, now),
                )


async def test_deleting_user_cascades_favorites_history_and_members_preserving_shared_list(
    tmp_path: Path,
) -> None:
    """Direct DELETE FROM users must cascade to wl_favorites, wl_view_history, and wl_members."""
    with app_env(tmp_path, "fk-cascade.db") as (_, _, app):
        user_store = app.state.user_store
        await user_store.upsert_user(TelegramUser(id=OWNER_ID, first_name="Owner"))
        await user_store.upsert_user(TelegramUser(id=MEMBER_A_ID, first_name="MemberA"))
        await user_store.upsert_user(TelegramUser(id=MEMBER_B_ID, first_name="MemberB"))
        await user_store.upsert_user(TelegramUser(id=GIFTER_ID, first_name="Gifter"))

        member_a = make_user(MEMBER_A_ID, "MemberA")
        db = Path(db_path_of(app))

        async with open_store(db) as store:
            wl = await store.execute(
                lambda svc: svc.create_wishlist(owner=OWNER, title="Shared List")
            )
            item = await store.execute(
                lambda svc: svc.add_wish_item(wishlist_id=wl.id, actor=OWNER, title="Tea Pot")
            )
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=wl.id,
                    actor=OWNER,
                    user_id=MEMBER_A_ID,
                    role=WishlistRole.MEMBER,
                )
            )
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=wl.id,
                    actor=OWNER,
                    user_id=MEMBER_B_ID,
                    role=WishlistRole.MEMBER,
                )
            )
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=wl.id,
                    actor=OWNER,
                    user_id=GIFTER_ID,
                    role=WishlistRole.MEMBER,
                )
            )
            await store.execute(lambda svc: svc.add_favorite(user=member_a, wishlist_id=wl.id))
            await store.execute(lambda svc: svc.record_view(user=member_a, wishlist_id=wl.id))
            await store.execute(lambda svc: svc.add_favorite(user=GIFTER, wishlist_id=wl.id))
            await store.execute(lambda svc: svc.record_view(user=GIFTER, wishlist_id=wl.id))
            await store.execute(
                lambda svc: svc.create_reservation(item_id=item.id, user=GIFTER, quantity=1)
            )

        with sqlite3.connect(db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM users WHERE telegram_id = ?", (MEMBER_A_ID,))
            conn.commit()

        assert (
            sql_rows(
                db,
                "SELECT COUNT(*) AS cnt FROM wl_favorites WHERE user_id = ?",
                (MEMBER_A_ID,),
            )[0]["cnt"]
            == 0
        )
        assert (
            sql_rows(
                db,
                "SELECT COUNT(*) AS cnt FROM wl_view_history WHERE user_id = ?",
                (MEMBER_A_ID,),
            )[0]["cnt"]
            == 0
        )
        assert (
            sql_rows(
                db,
                "SELECT COUNT(*) AS cnt FROM wl_members WHERE user_id = ?",
                (MEMBER_A_ID,),
            )[0]["cnt"]
            == 0
        )

        # Shared wishlist, items, other gifter's reservation/favorite/view, and owner remain intact.
        list_rows = sql_rows(db, "SELECT id, owner_id FROM wl_lists WHERE id = ?", (wl.id,))
        assert list_rows and list_rows[0]["owner_id"] == OWNER_ID
        assert sql_rows(db, "SELECT id FROM wl_items WHERE id = ?", (item.id,))
        assert sql_rows(
            db,
            "SELECT id FROM wl_reservations "
            "WHERE wish_item_id = ? AND user_id = ? AND status = 'active'",
            (item.id, GIFTER_ID),
        )
        assert (
            sql_rows(
                db,
                "SELECT COUNT(*) AS cnt FROM wl_favorites WHERE user_id = ?",
                (GIFTER_ID,),
            )[0]["cnt"]
            == 1
        )
        assert (
            sql_rows(
                db,
                "SELECT COUNT(*) AS cnt FROM wl_view_history WHERE user_id = ?",
                (GIFTER_ID,),
            )[0]["cnt"]
            == 1
        )
        assert (
            sql_rows(
                db,
                "SELECT COUNT(*) AS cnt FROM wl_members WHERE wishlist_id = ? AND user_id = ?",
                (wl.id, MEMBER_B_ID),
            )[0]["cnt"]
            == 1
        )


def test_migration_adds_user_fk_cascades_and_cleans_orphans(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Upgrading from add_notice_retention_columns adds user_id CASCADE FKs and drops orphans."""
    db_path = tmp_path / "orphan_mig.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    command.upgrade(_configured(url), "add_notice_retention_columns")

    now = "2026-01-01T00:00:00+00:00"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO users(telegram_id, first_name, created_at, updated_at) "
            "VALUES (?, 'Owner', ?, ?)",
            (OWNER_ID, now, now),
        )
        conn.execute(
            "INSERT INTO users(telegram_id, first_name, created_at, updated_at) "
            "VALUES (?, 'ValidMember', ?, ?)",
            (MEMBER_A_ID, now, now),
        )
        conn.execute(
            "INSERT INTO wl_lists"
            "(id, owner_id, title, public_token, invite_token, created_at, updated_at) "
            "VALUES (1, ?, 'Collab', 'pub-1', 'inv-1', ?, ?)",
            (OWNER_ID, now, now),
        )
        # Valid rows
        conn.execute(
            "INSERT INTO wl_members(wishlist_id, user_id, role, joined_at) "
            "VALUES (1, ?, 'member', ?)",
            (MEMBER_A_ID, now),
        )
        conn.execute(
            "INSERT INTO wl_favorites(user_id, wishlist_id, created_at) VALUES (?, 1, ?)",
            (MEMBER_A_ID, now),
        )
        conn.execute(
            "INSERT INTO wl_view_history(user_id, wishlist_id, viewed_at) VALUES (?, 1, ?)",
            (MEMBER_A_ID, now),
        )
        # Orphaned rows referencing nonexistent user
        conn.execute(
            "INSERT INTO wl_members(wishlist_id, user_id, role, joined_at) "
            "VALUES (1, ?, 'member', ?)",
            (NONEXISTENT_USER_ID, now),
        )
        conn.execute(
            "INSERT INTO wl_favorites(user_id, wishlist_id, created_at) VALUES (?, 1, ?)",
            (NONEXISTENT_USER_ID, now),
        )
        conn.execute(
            "INSERT INTO wl_view_history(user_id, wishlist_id, viewed_at) VALUES (?, 1, ?)",
            (NONEXISTENT_USER_ID, now),
        )
        conn.commit()

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists.migrations"):
        upgrade_to_head_sync(url)

    orphan_logs = {
        getattr(rec, "table", None): rec
        for rec in caplog.records
        if getattr(rec, "event", None) == "user_fk_migration_orphans_cleaned"
    }
    assert set(orphan_logs) == {"wl_members", "wl_favorites", "wl_view_history"}
    for rec in orphan_logs.values():
        assert rec.levelno == logging.WARNING
        assert getattr(rec, "rows_removed", None) == 1
        assert getattr(rec, "rows_kept", None) == 1

    completed_logs = [
        rec
        for rec in caplog.records
        if getattr(rec, "event", None) == "user_fk_migration_completed"
    ]
    assert len(completed_logs) == 1
    assert getattr(completed_logs[0], "total_orphans_removed", None) == 3
    assert getattr(completed_logs[0], "tables", None) == 3
    assert str(NONEXISTENT_USER_ID) not in caplog.text
    assert str(MEMBER_A_ID) not in caplog.text

    with sqlite3.connect(db_path) as conn:
        for table in ("wl_members", "wl_favorites", "wl_view_history"):
            orphan_cnt = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id = ?",
                (NONEXISTENT_USER_ID,),
            ).fetchone()[0]
            valid_cnt = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id = ?",
                (MEMBER_A_ID,),
            ).fetchone()[0]
            assert orphan_cnt == 0, f"Orphan row remained in {table}"
            assert valid_cnt == 1, f"Valid row lost in {table}"

            fk_rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            user_fks = [
                row
                for row in fk_rows
                if row[2] == "users" and row[3] == "user_id" and row[4] == "telegram_id"
            ]
            assert user_fks, f"{table}.user_id missing FK to users(telegram_id)"
            assert user_fks[0][6].upper() == "CASCADE", (
                f"{table}.user_id FK missing ON DELETE CASCADE"
            )


def test_migration_downgrade_removes_user_fks_and_preserves_data_and_indexes(
    tmp_path: Path,
) -> None:
    """Downgrading from add_user_fk_cascades removes user FKs while keeping data and indexes."""
    db_path = tmp_path / "downgrade_mig.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    upgrade_to_head_sync(url)

    now = "2026-01-01T00:00:00+00:00"
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO users(telegram_id, first_name, created_at, updated_at) "
            "VALUES (?, 'Owner', ?, ?)",
            (OWNER_ID, now, now),
        )
        conn.execute(
            "INSERT INTO users(telegram_id, first_name, created_at, updated_at) "
            "VALUES (?, 'ValidMember', ?, ?)",
            (MEMBER_A_ID, now, now),
        )
        conn.execute(
            "INSERT INTO wl_lists"
            "(id, owner_id, title, public_token, invite_token, created_at, updated_at) "
            "VALUES (1, ?, 'Collab', 'pub-1', 'inv-1', ?, ?)",
            (OWNER_ID, now, now),
        )
        conn.execute(
            "INSERT INTO wl_members(wishlist_id, user_id, role, joined_at) "
            "VALUES (1, ?, 'member', ?)",
            (MEMBER_A_ID, now),
        )
        conn.execute(
            "INSERT INTO wl_favorites(user_id, wishlist_id, created_at) VALUES (?, 1, ?)",
            (MEMBER_A_ID, now),
        )
        conn.execute(
            "INSERT INTO wl_view_history(user_id, wishlist_id, viewed_at) VALUES (?, 1, ?)",
            (MEMBER_A_ID, now),
        )
        conn.commit()

    command.downgrade(_configured(url), "add_notice_retention_columns")

    expected_indexes = {
        "wl_members": {"idx_wl_members_unique", "idx_wl_members_user"},
        "wl_favorites": {"idx_wl_favorites_user"},
        "wl_view_history": {"wl_view_history_user_wl", "idx_wl_view_history_user_time"},
    }
    with sqlite3.connect(db_path) as conn:
        for table, idx_names in expected_indexes.items():
            cnt = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE user_id = ?",
                (MEMBER_A_ID,),
            ).fetchone()[0]
            assert cnt == 1, f"Row lost on downgrade in {table}"

            fk_rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            user_fks = [r for r in fk_rows if r[2] == "users" and r[3] == "user_id"]
            assert not user_fks, f"{table}.user_id still has FK to users after downgrade"
            wl_fks = [r for r in fk_rows if r[2] == "wl_lists" and r[3] == "wishlist_id"]
            assert wl_fks, f"{table}.wishlist_id FK missing after downgrade"

            actual_indexes = {
                row[1]
                for row in conn.execute(f"PRAGMA index_list({table})").fetchall()
                if not row[1].startswith("sqlite_autoindex")
            }
            assert idx_names <= actual_indexes, f"Missing indexes in {table}: {actual_indexes}"

    upgrade_to_head_sync(url)
    with sqlite3.connect(db_path) as conn:
        for table in ("wl_members", "wl_favorites", "wl_view_history"):
            fk_rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            user_fks = [
                r
                for r in fk_rows
                if r[2] == "users" and r[3] == "user_id" and r[4] == "telegram_id"
            ]
            assert user_fks and user_fks[0][6].upper() == "CASCADE"


async def test_account_deletion_service_end_to_end_cascade(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AccountDeletionService.delete_account cleans personal links and keeps shared list data."""
    with app_env(tmp_path, "e2e-delete.db") as (_, _, app):
        user_store: UserStore = app.state.user_store
        await user_store.upsert_user(TelegramUser(id=OWNER_ID, first_name="Owner"))
        await user_store.upsert_user(TelegramUser(id=MEMBER_A_ID, first_name="MemberA"))
        await user_store.upsert_user(TelegramUser(id=GIFTER_ID, first_name="Gifter"))

        member_a = make_user(MEMBER_A_ID, "MemberA")
        db = Path(db_path_of(app))

        async with open_store(db) as store:
            shared = await store.execute(
                lambda svc: svc.create_wishlist(owner=OWNER, title="Shared List")
            )
            personal = await store.execute(
                lambda svc: svc.create_wishlist(owner=member_a, title="MemberA Personal")
            )
            item = await store.execute(
                lambda svc: svc.add_wish_item(wishlist_id=shared.id, actor=OWNER, title="Kettle")
            )
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=shared.id,
                    actor=OWNER,
                    user_id=MEMBER_A_ID,
                    role=WishlistRole.MEMBER,
                )
            )
            await store.execute(lambda svc: svc.add_favorite(user=member_a, wishlist_id=shared.id))
            await store.execute(lambda svc: svc.record_view(user=member_a, wishlist_id=shared.id))
            await store.execute(lambda svc: svc.add_favorite(user=GIFTER, wishlist_id=shared.id))
            await store.execute(lambda svc: svc.record_view(user=GIFTER, wishlist_id=shared.id))
            await store.execute(
                lambda svc: svc.create_reservation(item_id=item.id, user=GIFTER, quantity=1)
            )

            caplog.clear()
            with caplog.at_level(logging.INFO, logger="wishenka.wishlists.deletion"):
                result = await AccountDeletionService(store).delete_account(
                    MEMBER_A_ID,
                    secret_key="gift-receipt-test-secret",
                    session_ttl_seconds=3600,
                )
            assert not result.already_deleted
            assert result.deleted_lists == 1

            deletion_logs = [
                rec for rec in caplog.records if getattr(rec, "event", None) == "account_deleted"
            ]
            assert len(deletion_logs) == 1
            assert getattr(deletion_logs[0], "deleted_lists", None) == 1
            assert getattr(deletion_logs[0], "subject_hash_prefix", None)
            assert str(MEMBER_A_ID) not in caplog.text
            assert "MemberA" not in caplog.text

        assert not sql_rows(db, "SELECT id FROM users WHERE telegram_id = ?", (MEMBER_A_ID,))
        assert not sql_rows(db, "SELECT id FROM wl_lists WHERE id = ?", (personal.id,))
        for table in ("wl_members", "wl_favorites", "wl_view_history"):
            assert (
                sql_rows(
                    db,
                    f"SELECT COUNT(*) AS cnt FROM {table} WHERE user_id = ?",
                    (MEMBER_A_ID,),
                )[0]["cnt"]
                == 0
            )
        assert sql_rows(db, "SELECT id FROM wl_lists WHERE id = ?", (shared.id,))
        assert sql_rows(
            db,
            "SELECT id FROM wl_reservations WHERE wish_item_id = ? AND user_id = ?",
            (item.id, GIFTER_ID),
        )
        assert (
            sql_rows(
                db,
                "SELECT COUNT(*) AS cnt FROM wl_favorites WHERE user_id = ?",
                (GIFTER_ID,),
            )[0]["cnt"]
            == 1
        )
