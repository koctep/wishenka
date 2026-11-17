"""Failing repro tests for WISHENKA-35 (Step 3, red before Step 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.receipt_support import (
    CO_AUTHOR_ID,
    GIFTER,
    GIFTER_ID,
    OTHER_GIFTER_ID,
    OWNER,
    OWNER_ID,
    app_env,
    bearer,
    db_path_of,
    new_symbol,
    open_store,
    outbox_rows,
    sql_exec,
    sql_rows,
)
from wishenka.auth.models import TelegramUser
from wishenka.wishlists.models import WishlistRole

pytestmark = pytest.mark.timeout(60)


async def test_deletion_preview_and_confirm_api_contract(tmp_path: Path) -> None:
    """Preview and delete endpoints enforce auth, confirmation, and clear session cookies."""
    with app_env(tmp_path, "del-api.db") as (client, sessions, app):
        # Unauthenticated requests must be rejected
        assert client.get("/api/profile/deletion-preview").status_code == 401
        assert client.post("/api/profile/delete", json={"confirm": True}).status_code == 401

        user_store = app.state.user_store
        owner_profile = await user_store.upsert_user(
            TelegramUser(id=OWNER_ID, first_name="Alice", language_code="ru")
        )
        await user_store.upsert_user(
            TelegramUser(id=CO_AUTHOR_ID, first_name="Carl", language_code="ru")
        )
        await user_store.upsert_user(
            TelegramUser(id=GIFTER_ID, first_name="Greta", language_code="ru")
        )

        db = Path(db_path_of(app))
        async with open_store(db) as store:
            # 1. Personal list with wish + another user's reservation (must NOT count in preview)
            personal_wl = await store.execute(
                lambda svc: svc.create_wishlist(owner=OWNER, title="Personal")
            )
            personal_item = await store.execute(
                lambda svc: svc.add_wish_item(wishlist_id=personal_wl.id, actor=OWNER, title="Book")
            )
            await store.execute(
                lambda svc: svc.create_reservation(
                    item_id=personal_item.id, user=GIFTER, quantity=1
                )
            )

            # 2. Collaborative list with another member (will transfer)
            collab_wl = await store.execute(
                lambda svc: svc.create_wishlist(owner=OWNER, title="Shared")
            )
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=collab_wl.id,
                    actor=OWNER,
                    user_id=CO_AUTHOR_ID,
                    role=WishlistRole.ADMIN,
                )
            )

            # 3. Own reservation in GIFTER's list
            gifter_wl = await store.execute(
                lambda svc: svc.create_wishlist(owner=GIFTER, title="Greta List")
            )
            gifter_item = await store.execute(
                lambda svc: svc.add_wish_item(wishlist_id=gifter_wl.id, actor=GIFTER, title="Mug")
            )
            await store.execute(
                lambda svc: svc.create_reservation(item_id=gifter_item.id, user=OWNER, quantity=1)
            )

        owner_headers = bearer(sessions, OWNER_ID, "Alice")
        preview_resp = client.get("/api/profile/deletion-preview", headers=owner_headers)
        assert preview_resp.status_code == 200
        preview = preview_resp.json()
        assert preview["personal_lists_count"] == 1
        assert preview["collaborative_transferred_count"] == 1
        assert preview["collaborative_deleted_count"] == 0
        assert preview["reservations_count"] == 1

        # Cookie + CSRF flow: confirm=false returns 422, confirm=true deletes and clears cookie
        owner_cookie_token = sessions.create_token(OWNER_ID, "Alice", user_id=owner_profile.id)
        client.cookies.set(app.state.settings.session_cookie_name, owner_cookie_token)
        csrf_token = client.get("/api/auth/csrf").json()["csrf_token"]
        csrf_headers = {"Origin": "http://testserver", "X-CSRF-Token": csrf_token}

        bad_resp = client.post(
            "/api/profile/delete",
            headers=csrf_headers,
            json={"confirm": False},
        )
        assert bad_resp.status_code == 422

        del_resp = client.post(
            "/api/profile/delete",
            headers=csrf_headers,
            json={"confirm": True},
        )
        assert del_resp.status_code == 200
        del_data = del_resp.json()
        assert del_data["already_deleted"] is False
        assert del_data["deleted_lists"] == 1
        assert del_data["transferred_lists"] == 1
        assert del_data["cancelled_reservations"] == 1
        set_cookie = del_resp.headers.get("set-cookie", "").lower()
        assert app.state.settings.session_cookie_name.lower() in set_cookie


async def test_account_deletion_e2e_cascade_ownership_privacy_and_revocation(
    tmp_path: Path,
) -> None:
    """Full deletion cascade: personal, collab transfer, reservation cancel, PII & token revoke."""
    account_deletion_cls = new_symbol("wishenka.wishlists.deletion", "AccountDeletionService")

    with app_env(tmp_path, "del-e2e.db") as (client, sessions, app):
        user_store = app.state.user_store
        owner_profile = await user_store.upsert_user(
            TelegramUser(id=OWNER_ID, first_name="Alice", username="alice", language_code="ru")
        )
        await user_store.upsert_user(
            TelegramUser(id=OTHER_GIFTER_ID, first_name="Oleg", language_code="ru")
        )
        await user_store.upsert_user(
            TelegramUser(id=CO_AUTHOR_ID, first_name="Carl", language_code="ru")
        )
        await user_store.upsert_user(
            TelegramUser(id=GIFTER_ID, first_name="Greta", language_code="ru")
        )

        db = Path(db_path_of(app))
        async with open_store(db) as store:
            # Seed PII & bot state for OWNER
            sql_exec(
                db,
                "INSERT OR REPLACE INTO bot_destinations (user_id, chat_id, active) "
                "VALUES (?, ?, 1)",
                (owner_profile.id, OWNER_ID),
            )
            sql_exec(
                db,
                "INSERT INTO birthday_entries (id, owner_id, label, month, day, revision, deleted) "
                "VALUES (1, ?, 'Mom', 5, 20, 1, 0)",
                (owner_profile.id,),
            )
            sql_exec(
                db,
                "INSERT OR REPLACE INTO user_notification_settings "
                "(user_id, event_type, enabled, updated_at) "
                "VALUES (?, 'birthday_reminders', 1, '2026-01-01T00:00:00Z')",
                (OWNER_ID,),
            )

            # 1. Personal list with wish + GIFTER's reservation
            personal_wl = await store.execute(
                lambda svc: svc.create_wishlist(owner=OWNER, title="Alice Personal")
            )
            personal_item = await store.execute(
                lambda svc: svc.add_wish_item(
                    wishlist_id=personal_wl.id, actor=OWNER, title="Private Lamp"
                )
            )
            await store.execute(
                lambda svc: svc.create_reservation(
                    item_id=personal_item.id, user=GIFTER, quantity=1
                )
            )

            # 2. Collaborative list: OTHER_GIFTER is member, CO_AUTHOR is admin -> CO_AUTHOR wins
            collab_wl = await store.execute(
                lambda svc: svc.create_wishlist(owner=OWNER, title="Family List")
            )
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=collab_wl.id,
                    actor=OWNER,
                    user_id=OTHER_GIFTER_ID,
                    role=WishlistRole.MEMBER,
                )
            )
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=collab_wl.id,
                    actor=OWNER,
                    user_id=CO_AUTHOR_ID,
                    role=WishlistRole.ADMIN,
                )
            )
            collab_item = await store.execute(
                lambda svc: svc.add_wish_item(
                    wishlist_id=collab_wl.id,
                    actor=OWNER,
                    title="Coffee Maker",
                    recipient_name="Alice",
                )
            )
            await store.execute(
                lambda svc: svc.create_reservation(item_id=collab_item.id, user=GIFTER, quantity=1)
            )

            # 3. GIFTER's list where OWNER reserved 1 of 2 units
            gifter_wl = await store.execute(
                lambda svc: svc.create_wishlist(owner=GIFTER, title="Greta Wishes")
            )
            gifter_item = await store.execute(
                lambda svc: svc.add_wish_item(
                    wishlist_id=gifter_wl.id, actor=GIFTER, title="Teacup", quantity=2
                )
            )
            await store.execute(
                lambda svc: svc.create_reservation(item_id=gifter_item.id, user=OWNER, quantity=1)
            )

            # Clear outbox before deletion so we can assert no reservation notice is emitted
            sql_exec(db, "DELETE FROM notification_outbox")

            # Issue both token variants before deletion
            token_with_uid = sessions.create_token(OWNER_ID, "Alice", user_id=owner_profile.id)
            token_without_uid = sessions.create_token(OWNER_ID, "Alice", user_id=None)

            svc = account_deletion_cls(store)
            result = await svc.delete_account(
                OWNER_ID,
                secret_key=app.state.settings.secret_key,
                session_ttl_seconds=app.state.settings.session_ttl_seconds,
            )
            assert result.already_deleted is False
            assert result.deleted_lists == 1
            assert result.transferred_lists == 1
            assert result.cancelled_reservations == 1
            assert result.anonymized_items == 1

            # Idempotent repeat call
            repeat = await svc.delete_account(
                OWNER_ID,
                secret_key=app.state.settings.secret_key,
                session_ttl_seconds=app.state.settings.session_ttl_seconds,
            )
            assert repeat.already_deleted is True
            assert repeat.deleted_lists == 0
            assert repeat.transferred_lists == 0
            assert repeat.cancelled_reservations == 0

        # Personal list & its wish/reservation are gone
        assert sql_rows(db, "SELECT id FROM wl_lists WHERE id = ?", (personal_wl.id,)) == []
        assert sql_rows(db, "SELECT id FROM wl_items WHERE id = ?", (personal_item.id,)) == []

        # Collaborative list transferred to CO_AUTHOR with is_collaborative=1
        collab_rows = sql_rows(
            db, "SELECT owner_id, is_collaborative FROM wl_lists WHERE id = ?", (collab_wl.id,)
        )
        assert collab_rows == [{"owner_id": CO_AUTHOR_ID, "is_collaborative": 1}]

        # Collaborative item anonymized, GIFTER's reservation preserved
        collab_item_rows = sql_rows(
            db,
            "SELECT recipient_user_id, recipient_name FROM wl_items WHERE id = ?",
            (collab_item.id,),
        )
        assert collab_item_rows == [{"recipient_user_id": None, "recipient_name": None}]
        collab_res_rows = sql_rows(
            db,
            "SELECT user_id, status FROM wl_reservations WHERE wish_item_id = ?",
            (collab_item.id,),
        )
        assert collab_res_rows == [{"user_id": GIFTER_ID, "status": "active"}]

        # OWNER's reservation on GIFTER's item removed without notifying GIFTER
        assert (
            sql_rows(
                db,
                "SELECT id FROM wl_reservations WHERE wish_item_id = ? AND user_id = ?",
                (gifter_item.id, OWNER_ID),
            )
            == []
        )
        assert outbox_rows(db) == []

        # PII & bot state deleted
        assert sql_rows(db, "SELECT id FROM users WHERE telegram_id = ?", (OWNER_ID,)) == []
        assert (
            sql_rows(
                db, "SELECT user_id FROM bot_destinations WHERE user_id = ?", (owner_profile.id,)
            )
            == []
        )
        assert (
            sql_rows(db, "SELECT id FROM birthday_entries WHERE owner_id = ?", (owner_profile.id,))
            == []
        )
        assert (
            sql_rows(
                db,
                "SELECT user_id FROM user_notification_settings WHERE user_id = ?",
                (OWNER_ID,),
            )
            == []
        )

        # Previously issued tokens must be rejected with 401
        assert (
            client.get(
                "/api/profile/preferences",
                headers={"Authorization": f"Bearer {token_with_uid}"},
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/profile/preferences",
                headers={"Authorization": f"Bearer {token_without_uid}"},
            ).status_code
            == 401
        )

        # Re-registering with a clean slate gets a new users.id and does NOT revive old tokens
        new_profile = await user_store.upsert_user(
            TelegramUser(id=OWNER_ID, first_name="Alice", language_code="ru")
        )
        assert new_profile.id > owner_profile.id
        assert (
            client.get(
                "/api/profile/preferences",
                headers={"Authorization": f"Bearer {token_with_uid}"},
            ).status_code
            == 401
        )
        assert (
            client.get(
                "/api/profile/preferences",
                headers={"Authorization": f"Bearer {token_without_uid}"},
            ).status_code
            == 401
        )
