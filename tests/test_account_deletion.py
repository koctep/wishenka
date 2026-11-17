"""Comprehensive unit and integration tests for WISHENKA-35 account deletion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
    open_store,
    outbox_rows,
    sql_exec,
    sql_rows,
)
from wishenka.auth.models import TelegramUser
from wishenka.auth.session import compute_revocation_subject_hash
from wishenka.wishlists.cleanup import run_cleanup_cycle
from wishenka.wishlists.deletion import AccountDeletionService
from wishenka.wishlists.models import WishlistRole

pytestmark = pytest.mark.timeout(60)


async def test_ownership_transfer_deterministic_tie_breakers(tmp_path: Path) -> None:
    """Successor selection follows role -> joined_at -> user created_at -> telegram_id."""
    with app_env(tmp_path, "del-tiebreak.db") as (_, _, app):
        user_store = app.state.user_store
        await user_store.upsert_user(TelegramUser(id=OWNER_ID, first_name="Owner"))
        await user_store.upsert_user(TelegramUser(id=201, first_name="U201"))
        await user_store.upsert_user(TelegramUser(id=202, first_name="U202"))
        await user_store.upsert_user(TelegramUser(id=203, first_name="U203"))

        db = Path(db_path_of(app))
        # Normalize created_at: 202 earlier than 203; 201 same as 202
        sql_exec(db, "UPDATE users SET created_at = '2026-01-01T00:00:00Z' WHERE telegram_id = 201")
        sql_exec(db, "UPDATE users SET created_at = '2026-01-01T00:00:00Z' WHERE telegram_id = 202")
        sql_exec(db, "UPDATE users SET created_at = '2026-01-05T00:00:00Z' WHERE telegram_id = 203")

        async with open_store(db) as store:
            # Case A: admin beats member even if member joined earlier
            wl_a = await store.execute(lambda svc: svc.create_wishlist(owner=OWNER, title="List A"))
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=wl_a.id, actor=OWNER, user_id=203, role=WishlistRole.MEMBER
                )
            )
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=wl_a.id, actor=OWNER, user_id=202, role=WishlistRole.ADMIN
                )
            )
            sql_exec(
                db,
                "UPDATE wl_members SET joined_at = '2026-02-02T00:00:00Z' "
                "WHERE wishlist_id = ? AND user_id = 202",
                (wl_a.id,),
            )
            sql_exec(
                db,
                "UPDATE wl_members SET joined_at = '2026-02-01T00:00:00Z' "
                "WHERE wishlist_id = ? AND user_id = 203",
                (wl_a.id,),
            )

            # Case B: equal role, joined_at, created_at -> lowest telegram_id (201 < 202)
            wl_b = await store.execute(lambda svc: svc.create_wishlist(owner=OWNER, title="List B"))
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=wl_b.id, actor=OWNER, user_id=202, role=WishlistRole.ADMIN
                )
            )
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=wl_b.id, actor=OWNER, user_id=201, role=WishlistRole.ADMIN
                )
            )
            sql_exec(
                db,
                "UPDATE wl_members SET joined_at = '2026-02-01T00:00:00Z' WHERE wishlist_id = ?",
                (wl_b.id,),
            )

            # Case C: equal role + equal joined_at -> earlier user created_at (202 before 203)
            wl_c = await store.execute(lambda svc: svc.create_wishlist(owner=OWNER, title="List C"))
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=wl_c.id, actor=OWNER, user_id=203, role=WishlistRole.MEMBER
                )
            )
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=wl_c.id, actor=OWNER, user_id=202, role=WishlistRole.MEMBER
                )
            )
            sql_exec(
                db,
                "UPDATE wl_members SET joined_at = '2026-02-01T00:00:00Z' WHERE wishlist_id = ?",
                (wl_c.id,),
            )

            svc = AccountDeletionService(store)
            res = await svc.delete_account(
                OWNER_ID,
                secret_key=app.state.settings.secret_key,
                session_ttl_seconds=3600,
            )
            assert res.transferred_lists == 3

        assert sql_rows(
            db, "SELECT owner_id, is_collaborative FROM wl_lists WHERE id = ?", (wl_a.id,)
        ) == [{"owner_id": 202, "is_collaborative": 1}]
        assert sql_rows(
            db, "SELECT owner_id, is_collaborative FROM wl_lists WHERE id = ?", (wl_b.id,)
        ) == [{"owner_id": 201, "is_collaborative": 1}]
        assert sql_rows(
            db, "SELECT owner_id, is_collaborative FROM wl_lists WHERE id = ?", (wl_c.id,)
        ) == [{"owner_id": 202, "is_collaborative": 1}]


async def test_solo_collaborative_and_foreign_membership_and_purchased_booking(
    tmp_path: Path,
) -> None:
    """Solo collab is deleted; leaving foreign list keeps items; purchased booking cancels."""
    with app_env(tmp_path, "del-solo-foreign.db") as (_, _, app):
        user_store = app.state.user_store
        await user_store.upsert_user(TelegramUser(id=OWNER_ID, first_name="Alice"))
        await user_store.upsert_user(TelegramUser(id=GIFTER_ID, first_name="Greta"))
        await user_store.upsert_user(TelegramUser(id=CO_AUTHOR_ID, first_name="Carl"))

        db = Path(db_path_of(app))
        async with open_store(db) as store:
            # 1. Solo collaborative list (no other members) -> must be deleted
            solo_wl = await store.execute(
                lambda svc: svc.create_wishlist(owner=OWNER, title="Solo Collab")
            )
            sql_exec(db, "UPDATE wl_lists SET is_collaborative = 1 WHERE id = ?", (solo_wl.id,))
            solo_item = await store.execute(
                lambda svc: svc.add_wish_item(wishlist_id=solo_wl.id, actor=OWNER, title="Lamp")
            )
            await store.execute(
                lambda svc: svc.create_reservation(item_id=solo_item.id, user=GIFTER, quantity=1)
            )

            # 2. Foreign collaborative list where OWNER is a member and authored an item
            foreign_wl = await store.execute(
                lambda svc: svc.create_wishlist(owner=GIFTER, title="Greta Shared")
            )
            await store.execute(
                lambda svc: svc.add_member(
                    wishlist_id=foreign_wl.id,
                    actor=GIFTER,
                    user_id=OWNER_ID,
                    role=WishlistRole.MEMBER,
                )
            )
            authored_item = await store.execute(
                lambda svc: svc.add_wish_item(
                    wishlist_id=foreign_wl.id,
                    actor=OWNER,
                    title="Tea Set",
                    recipient_user_id=OWNER_ID,
                    recipient_name="Alice",
                )
            )
            other_item = await store.execute(
                lambda svc: svc.add_wish_item(
                    wishlist_id=foreign_wl.id,
                    actor=GIFTER,
                    title="Coffee Grinder",
                    recipient_user_id=GIFTER_ID,
                    recipient_name="Greta",
                )
            )
            await store.execute(
                lambda svc: svc.create_reservation(item_id=other_item.id, user=OWNER, quantity=1)
            )
            # Mark OWNER's reservation as purchased
            sql_exec(
                db,
                "UPDATE wl_reservations SET status = 'purchased' "
                "WHERE wish_item_id = ? AND user_id = ?",
                (other_item.id, OWNER_ID),
            )

            sql_exec(db, "DELETE FROM notification_outbox")

            svc = AccountDeletionService(store)
            preview = await svc.preview_account_deletion(OWNER_ID)
            assert preview.personal_lists_count == 0
            assert preview.collaborative_transferred_count == 0
            assert preview.collaborative_deleted_count == 1
            assert preview.reservations_count == 1

            result = await svc.delete_account(
                OWNER_ID,
                secret_key=app.state.settings.secret_key,
                session_ttl_seconds=3600,
            )
            assert result.already_deleted is False
            assert result.deleted_lists == 1
            assert result.cancelled_reservations == 1
            assert result.anonymized_items == 1

        assert sql_rows(db, "SELECT id FROM wl_lists WHERE id = ?", (solo_wl.id,)) == []
        assert (
            sql_rows(db, "SELECT token FROM wl_tokens WHERE wishlist_id = ?", (solo_wl.id,)) == []
        )
        assert (
            sql_rows(
                db,
                "SELECT id FROM wl_members WHERE wishlist_id = ? AND user_id = ?",
                (foreign_wl.id, OWNER_ID),
            )
            == []
        )
        assert sql_rows(
            db,
            "SELECT recipient_user_id, recipient_name FROM wl_items WHERE id = ?",
            (authored_item.id,),
        ) == [{"recipient_user_id": None, "recipient_name": None}]
        assert (
            sql_rows(
                db,
                "SELECT id FROM wl_reservations WHERE user_id = ?",
                (OWNER_ID,),
            )
            == []
        )
        assert outbox_rows(db) == []


async def test_pending_notices_cancelled_and_revocation_cleanup_cycle(tmp_path: Path) -> None:
    """Deletion removes queued notices; cleanup cycle purges only expired revocations."""
    with app_env(tmp_path, "del-cleanup.db") as (_, _, app):
        user_store = app.state.user_store
        await user_store.upsert_user(TelegramUser(id=OWNER_ID, first_name="Alice"))
        await user_store.upsert_user(TelegramUser(id=OTHER_GIFTER_ID, first_name="Oleg"))

        db = Path(db_path_of(app))
        sql_exec(
            db,
            "INSERT INTO reminder_outbox "
            "(occurrence_key, kind, user_id, event_date, next_attempt_at) "
            "VALUES ('occ-1', 'birthday_reminder', ?, '2026-12-01', 100)",
            (OWNER_ID,),
        )
        async with open_store(db) as store:
            wl = await store.execute(lambda svc: svc.create_wishlist(owner=OWNER, title="N"))
            item = await store.execute(
                lambda svc: svc.add_wish_item(wishlist_id=wl.id, actor=OWNER, title="Cup")
            )
            sql_exec(
                db,
                "INSERT INTO wl_receipts (id, wish_item_id, quantity, received_at) "
                "VALUES (1, ?, 1, '2026-01-01T00:00:00Z')",
                (item.id,),
            )
            sql_exec(
                db,
                "INSERT INTO notification_outbox "
                "(event_type, receipt_id, wishlist_id, wish_item_id, giver_user_id, status, "
                "next_attempt_at, created_at, updated_at) "
                "VALUES ('receipt', 1, ?, ?, ?, 'pending', 100, '2026-01-01T00:00:00Z', "
                "'2026-01-01T00:00:00Z')",
                (wl.id, item.id, OWNER_ID),
            )

        now = datetime(2026, 11, 17, 22, 0, tzinfo=UTC)
        async with open_store(db) as store:
            svc = AccountDeletionService(store)
            await svc.delete_account(
                OWNER_ID,
                secret_key=app.state.settings.secret_key,
                session_ttl_seconds=600,
                now=now,
            )

            assert (
                sql_rows(db, "SELECT id FROM reminder_outbox WHERE user_id = ?", (OWNER_ID,)) == []
            )
            assert (
                sql_rows(
                    db, "SELECT id FROM notification_outbox WHERE giver_user_id = ?", (OWNER_ID,)
                )
                == []
            )

            # Before expiration: marker remains
            stats_before = await run_cleanup_cycle(
                store, app.state.settings, now=now + timedelta(seconds=300)
            )
            assert stats_before.session_revocations_cleaned == 0
            subj = compute_revocation_subject_hash(OWNER_ID, app.state.settings.secret_key)
            assert (
                len(
                    sql_rows(
                        db,
                        "SELECT subject_hash FROM deleted_session_revocations "
                        "WHERE subject_hash = ?",
                        (subj,),
                    )
                )
                == 1
            )

            # After expiration: marker is purged
            stats_after = await run_cleanup_cycle(
                store, app.state.settings, now=now + timedelta(seconds=601)
            )
            assert stats_after.session_revocations_cleaned == 1
            assert (
                sql_rows(
                    db,
                    "SELECT subject_hash FROM deleted_session_revocations WHERE subject_hash = ?",
                    (subj,),
                )
                == []
            )


async def test_settings_ui_renders_bilingual_delete_section_and_validation(tmp_path: Path) -> None:
    """Settings page renders RU/EN delete controls and /api/profile/delete validates payload."""
    with app_env(tmp_path, "del-ui.db") as (client, sessions, app):
        user_store = app.state.user_store
        await user_store.upsert_user(
            TelegramUser(id=OWNER_ID, first_name="Alice", language_code="ru")
        )
        headers = bearer(sessions, OWNER_ID, "Alice")

        ru_resp = client.get("/settings", headers=headers)
        assert ru_resp.status_code == 200
        assert "delete-account-start-btn" in ru_resp.text
        assert "delete-account-confirm-panel" in ru_resp.text
        assert "Удаление аккаунта" in ru_resp.text

        await user_store.set_explicit_locale(OWNER_ID, "en")
        en_resp = client.get("/settings", headers=headers)
        assert en_resp.status_code == 200
        assert "Delete account" in en_resp.text
        assert "Confirm permanent deletion" in en_resp.text

        # Missing confirm / non-boolean confirm / invalid JSON -> 422
        assert client.post("/api/profile/delete", headers=headers, json={}).status_code == 422
        assert (
            client.post("/api/profile/delete", headers=headers, json={"confirm": "yes"}).status_code
            == 422
        )
        assert (
            client.post(
                "/api/profile/delete",
                headers={**headers, "Content-Type": "application/json"},
                content="not-json",
            ).status_code
            == 422
        )


async def test_account_deletion_structured_logging_has_no_pii(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Account deletion and revocation logs use structured JSON fields without PII."""
    import json
    import logging

    from wishenka.logging import JsonFormatter

    with app_env(tmp_path, "del-logs.db") as (client, sessions, app):
        user_store = app.state.user_store
        await user_store.upsert_user(
            TelegramUser(id=OWNER_ID, first_name="SecretAlice", username="secret_alice_handle")
        )
        headers = bearer(sessions, OWNER_ID, "SecretAlice")
        raw_token = headers["Authorization"].removeprefix("Bearer ")

        with caplog.at_level(logging.INFO):
            caplog.clear()
            # 1. Missing confirmation -> WARNING account_deletion_rejected
            rej = client.post("/api/profile/delete", headers=headers, json={})
            assert rej.status_code == 422

            # 2. Valid deletion -> INFO account_deleted
            ok = client.post("/api/profile/delete", headers=headers, json={"confirm": True})
            assert ok.status_code == 200

            # 3. Revoked session reuse -> WARNING session_rejected_revoked_or_deleted
            revoked = client.get("/api/profile/deletion-preview", headers=headers)
            assert revoked.status_code == 401

            # 4. Idempotent direct service call -> INFO account_deletion_already_deleted
            async with open_store(Path(db_path_of(app))) as store:
                svc = AccountDeletionService(store)
                await svc.delete_account(
                    OWNER_ID,
                    secret_key=app.state.settings.secret_key,
                    session_ttl_seconds=app.state.settings.session_ttl_seconds,
                )

        formatter = JsonFormatter()
        loggers = {
            "wishenka.wishlists.deletion",
            "wishenka.web.profile",
            "wishenka.auth",
        }
        relevant = [json.loads(formatter.format(r)) for r in caplog.records if r.name in loggers]
        events = {entry.get("extra", {}).get("event") for entry in relevant}
        assert {
            "account_deletion_rejected",
            "account_deleted",
            "session_rejected_revoked_or_deleted",
            "account_deletion_already_deleted",
        }.issubset(events)

        serialized = json.dumps(relevant)
        assert str(OWNER_ID) not in serialized
        assert "SecretAlice" not in serialized
        assert "secret_alice_handle" not in serialized
        assert raw_token not in serialized
