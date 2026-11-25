"""Account deletion preview and atomic cascade service."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.auth.session import compute_revocation_subject_hash
from wishenka.notices.events import EventProducer, SharedEvent
from wishenka.wishlists.store import WishlistStore

logger = logging.getLogger(__name__)

_MAX_DT = datetime.max.replace(tzinfo=UTC)


@dataclass(frozen=True)
class DeletionPreviewDTO:
    """Impact summary shown to a user before confirming account deletion."""

    personal_lists_count: int
    collaborative_transferred_count: int
    collaborative_deleted_count: int
    reservations_count: int


@dataclass(frozen=True)
class DeletionResultDTO:
    """Outcome summary returned after executing account deletion."""

    already_deleted: bool
    deleted_lists: int
    transferred_lists: int
    cancelled_reservations: int
    anonymized_items: int = 0


def _parse_utc_datetime(raw: str | None) -> datetime:
    """Parse an ISO-8601 timestamp to UTC datetime, falling back to max datetime."""
    if not raw:
        return _MAX_DT
    normalized = raw.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return _MAX_DT
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _role_rank(role: str) -> int:
    """Return deterministic priority rank for collaborative ownership transfer."""
    normalized = role.strip().lower()
    if normalized == "admin":
        return 1
    if normalized in {"coauthor", "collaborator"}:
        return 2
    return 3


async def _table_exists(conn: AsyncConnection, table_name: str) -> bool:
    """Check whether a table exists in the current SQLite database."""
    found = await conn.scalar(
        text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :name"),
        {"name": table_name},
    )
    return found is not None


async def _delete_if_table_exists(
    conn: AsyncConnection,
    table_name: str,
    where_sql: str,
    params: dict[str, object],
) -> None:
    """Delete rows from an optional table if it exists in the schema."""
    if await _table_exists(conn, table_name):
        await conn.execute(text(f"DELETE FROM {table_name} WHERE {where_sql}"), params)


class AccountDeletionService:
    """Service for previewing and atomically executing account deletion."""

    def __init__(self, store: WishlistStore) -> None:
        self._store = store

    async def preview_account_deletion(self, telegram_id: int) -> DeletionPreviewDTO:
        """Compute personal impact summary without revealing other users' reservations."""

        async def work(conn: AsyncConnection) -> DeletionPreviewDTO:
            owned_rows = (
                await conn.execute(
                    text("SELECT id, is_collaborative FROM wl_lists WHERE owner_id = :uid"),
                    {"uid": telegram_id},
                )
            ).fetchall()

            personal_lists_count = 0
            collaborative_transferred_count = 0
            collaborative_deleted_count = 0

            for row in owned_rows:
                wl_id = int(row.id)
                is_collab = int(row.is_collaborative or 0) == 1
                if not is_collab:
                    personal_lists_count += 1
                    continue
                other_member = await conn.scalar(
                    text(
                        "SELECT 1 FROM wl_members "
                        "WHERE wishlist_id = :wl_id AND user_id != :uid LIMIT 1"
                    ),
                    {"wl_id": wl_id, "uid": telegram_id},
                )
                if other_member is not None:
                    collaborative_transferred_count += 1
                else:
                    collaborative_deleted_count += 1

            reservations_count = int(
                await conn.scalar(
                    text(
                        "SELECT COUNT(*) FROM wl_reservations "
                        "WHERE user_id = :uid AND status IN ('active', 'purchased')"
                    ),
                    {"uid": telegram_id},
                )
                or 0
            )

            return DeletionPreviewDTO(
                personal_lists_count=personal_lists_count,
                collaborative_transferred_count=collaborative_transferred_count,
                collaborative_deleted_count=collaborative_deleted_count,
                reservations_count=reservations_count,
            )

        preview = await self._store.transaction(work)
        logger.debug(
            "Account deletion preview computed",
            extra={
                "event": "account_deletion_preview_computed",
                "personal_lists_count": preview.personal_lists_count,
                "collaborative_transferred_count": preview.collaborative_transferred_count,
                "collaborative_deleted_count": preview.collaborative_deleted_count,
                "reservations_count": preview.reservations_count,
            },
        )
        return preview

    async def delete_account(
        self,
        telegram_id: int,
        *,
        secret_key: str,
        session_ttl_seconds: int,
        now: datetime | None = None,
    ) -> DeletionResultDTO:
        """Atomically delete user account, transfer/delete lists, cancel bookings, and revoke."""
        effective_now = (now or datetime.now(UTC)).astimezone(UTC)
        now_iso = effective_now.isoformat()
        now_epoch = int(effective_now.timestamp())
        expires_at = now_epoch + max(1, int(session_ttl_seconds))
        subject_hash = compute_revocation_subject_hash(telegram_id, secret_key)

        async def work(conn: AsyncConnection) -> DeletionResultDTO:
            has_users_table = await _table_exists(conn, "users")
            user_exists = (
                await conn.scalar(
                    text("SELECT 1 FROM users WHERE telegram_id = :uid"),
                    {"uid": telegram_id},
                )
                if has_users_table
                else None
            )

            owned_lists = (
                await conn.execute(
                    text(
                        "SELECT id, is_collaborative, invite_token "
                        "FROM wl_lists WHERE owner_id = :uid ORDER BY id ASC"
                    ),
                    {"uid": telegram_id},
                )
            ).fetchall()

            member_rows = (
                await conn.execute(
                    text("SELECT wishlist_id FROM wl_members WHERE user_id = :uid"),
                    {"uid": telegram_id},
                )
            ).fetchall()

            own_reservations_count = int(
                await conn.scalar(
                    text(
                        "SELECT COUNT(*) FROM wl_reservations "
                        "WHERE user_id = :uid AND status IN ('active', 'purchased')"
                    ),
                    {"uid": telegram_id},
                )
                or 0
            )
            any_reservations = await conn.scalar(
                text("SELECT 1 FROM wl_reservations WHERE user_id = :uid LIMIT 1"),
                {"uid": telegram_id},
            )

            if (
                user_exists is None
                and not owned_lists
                and not member_rows
                and any_reservations is None
            ):
                return DeletionResultDTO(
                    already_deleted=True,
                    deleted_lists=0,
                    transferred_lists=0,
                    cancelled_reservations=0,
                    anonymized_items=0,
                )

            deleted_lists = 0
            transferred_lists = 0
            anonymized_items = 0
            lists_to_delete: list[tuple[int, str]] = []
            pending_events: list[SharedEvent] = []

            # 1 & 2. Process owned wishlists (personal or solo collab -> delete; shared -> transfer)
            for wl_row in owned_lists:
                wl_id = int(wl_row.id)
                is_collab = int(wl_row.is_collaborative or 0) == 1
                invite_token = str(wl_row.invite_token)

                if not is_collab:
                    lists_to_delete.append((wl_id, invite_token))
                    continue

                candidates = (
                    await conn.execute(
                        text(
                            "SELECT m.user_id, m.role, m.joined_at, "
                            "u.created_at AS user_created_at, u.first_name AS first_name "
                            "FROM wl_members m "
                            "LEFT JOIN users u ON u.telegram_id = m.user_id "
                            "WHERE m.wishlist_id = :wl_id AND m.user_id != :uid"
                        ),
                        {"wl_id": wl_id, "uid": telegram_id},
                    )
                ).fetchall()

                if not candidates:
                    lists_to_delete.append((wl_id, invite_token))
                    continue

                successor = min(
                    candidates,
                    key=lambda row: (
                        _role_rank(str(row.role)),
                        _parse_utc_datetime(row.joined_at),
                        _parse_utc_datetime(row.user_created_at),
                        int(row.user_id),
                    ),
                )
                new_owner_id = int(successor.user_id)
                new_owner_name = str(successor.first_name or "")

                await conn.execute(
                    text(
                        "UPDATE wl_lists "
                        "SET owner_id = :new_owner_id, owner_name = :new_owner_name, "
                        "is_collaborative = 1, updated_at = :now_iso "
                        "WHERE id = :wl_id"
                    ),
                    {
                        "new_owner_id": new_owner_id,
                        "new_owner_name": new_owner_name,
                        "now_iso": now_iso,
                        "wl_id": wl_id,
                    },
                )
                await conn.execute(
                    text(
                        "DELETE FROM wl_members "
                        "WHERE wishlist_id = :wl_id AND user_id IN (:old_uid, :new_uid)"
                    ),
                    {"wl_id": wl_id, "old_uid": telegram_id, "new_uid": new_owner_id},
                )

                anon_res = await conn.execute(
                    text(
                        "UPDATE wl_items "
                        "SET recipient_user_id = NULL, recipient_name = NULL, "
                        "updated_at = :now_iso "
                        "WHERE wishlist_id = :wl_id "
                        "AND (recipient_user_id = :uid "
                        "OR (recipient_user_id IS NULL AND recipient_name IS NOT NULL))"
                    ),
                    {"wl_id": wl_id, "uid": telegram_id, "now_iso": now_iso},
                )
                anonymized_items += int(anon_res.rowcount or 0)
                transferred_lists += 1

                remaining_ids = tuple(int(c.user_id) for c in candidates)
                pending_events.append(
                    SharedEvent(
                        kind="membership_changed",
                        wishlist_id=wl_id,
                        item_id=None,
                        event_id=f"account_deleted:{wl_id}:{uuid4().hex}",
                        recipients=remaining_ids,
                        member_recipients=frozenset(remaining_ids),
                    )
                )

            # Hard-delete personal and solo collaborative lists (wl_tokens, wl_invite_tokens,
            # and reminder_outbox cascade automatically via FK ON DELETE CASCADE).
            if lists_to_delete:
                delete_ids = [wl_id for wl_id, _ in lists_to_delete]
                await _delete_if_table_exists_in(
                    conn, "wl_list_notification_settings", "wishlist_id", delete_ids
                )
                del_res = await conn.execute(
                    text("DELETE FROM wl_lists WHERE id IN :ids").bindparams(
                        bindparam("ids", expanding=True)
                    ),
                    {"ids": delete_ids},
                )
                deleted_lists = int(del_res.rowcount or 0)

            # 3. Remove from foreign collaborative lists & anonymize authored items
            for m_row in member_rows:
                wl_id = int(m_row.wishlist_id)
                wl_info = (
                    await conn.execute(
                        text("SELECT owner_id FROM wl_lists WHERE id = :wl_id"),
                        {"wl_id": wl_id},
                    )
                ).fetchone()
                if wl_info is None:
                    continue
                anon_res = await conn.execute(
                    text(
                        "UPDATE wl_items "
                        "SET recipient_user_id = NULL, recipient_name = NULL, "
                        "updated_at = :now_iso "
                        "WHERE wishlist_id = :wl_id AND recipient_user_id = :uid"
                    ),
                    {"wl_id": wl_id, "uid": telegram_id, "now_iso": now_iso},
                )
                anonymized_items += int(anon_res.rowcount or 0)
                await conn.execute(
                    text("DELETE FROM wl_members WHERE wishlist_id = :wl_id AND user_id = :uid"),
                    {"wl_id": wl_id, "uid": telegram_id},
                )
                other_members = (
                    await conn.execute(
                        text("SELECT user_id FROM wl_members WHERE wishlist_id = :wl_id"),
                        {"wl_id": wl_id},
                    )
                ).fetchall()
                recipient_ids = tuple(
                    dict.fromkeys([int(wl_info.owner_id), *(int(r.user_id) for r in other_members)])
                )
                if recipient_ids:
                    pending_events.append(
                        SharedEvent(
                            kind="membership_changed",
                            wishlist_id=wl_id,
                            item_id=None,
                            event_id=f"account_deleted:{wl_id}:{uuid4().hex}",
                            recipients=recipient_ids,
                            member_recipients=frozenset(int(r.user_id) for r in other_members),
                        )
                    )

            # 4. Cancel all reservations by deleted user (without notifying recipients)
            await conn.execute(
                text("DELETE FROM wl_reservations WHERE user_id = :uid"),
                {"uid": telegram_id},
            )

            # 5. Clean up PII, preferences, bot state, and queued notifications
            await _delete_if_table_exists(
                conn, "wl_favorites", "user_id = :uid", {"uid": telegram_id}
            )
            await _delete_if_table_exists(
                conn, "wl_share_access", "user_id = :uid", {"uid": telegram_id}
            )
            await _delete_if_table_exists(
                conn, "wl_view_history", "user_id = :uid", {"uid": telegram_id}
            )
            await _delete_if_table_exists(
                conn, "user_notification_settings", "user_id = :uid", {"uid": telegram_id}
            )
            await _delete_if_table_exists(
                conn, "wl_list_notification_settings", "user_id = :uid", {"uid": telegram_id}
            )
            await _delete_if_table_exists(
                conn, "notification_outbox", "giver_user_id = :uid", {"uid": telegram_id}
            )
            await _delete_if_table_exists(
                conn, "notice_receipt_keys", "giver_user_id = :uid", {"uid": telegram_id}
            )
            await _delete_if_table_exists(
                conn, "reminder_outbox", "user_id = :uid", {"uid": telegram_id}
            )
            await _delete_if_table_exists(
                conn, "wl_idempotency_records", "actor_id = :uid", {"uid": telegram_id}
            )

            await _delete_if_table_exists(
                conn, "birthday_entries", "owner_id = :uid", {"uid": telegram_id}
            )
            await _delete_if_table_exists(
                conn,
                "birthday_input",
                "owner_id = :uid OR chat_id = :uid",
                {"uid": telegram_id},
            )
            await _delete_if_table_exists(
                conn, "bot_destinations", "user_id = :uid", {"uid": telegram_id}
            )
            await _delete_if_table_exists(
                conn,
                "support_input",
                "owner_id = :uid OR chat_id = :uid",
                {"uid": telegram_id},
            )
            await _delete_if_table_exists(
                conn,
                "support_tickets",
                "telegram_id = :uid",
                {"uid": telegram_id},
            )

            await _delete_if_table_exists(
                conn,
                "bot_drafts",
                "owner = :uid OR chat = :uid",
                {"uid": telegram_id},
            )
            await _delete_if_table_exists(
                conn,
                "bot_capture_order",
                "owner = :uid OR chat = :uid",
                {"uid": telegram_id},
            )

            if has_users_table:
                await conn.execute(
                    text("DELETE FROM users WHERE telegram_id = :uid"),
                    {"uid": telegram_id},
                )

            # 6. Record stateless token revocation without storing PII
            if await _table_exists(conn, "deleted_session_revocations"):
                await conn.execute(
                    text(
                        "INSERT INTO deleted_session_revocations "
                        "(subject_hash, revoked_before, expires_at) "
                        "VALUES (:subject_hash, :revoked_before, :expires_at) "
                        "ON CONFLICT(subject_hash) DO UPDATE SET "
                        "revoked_before = MAX(deleted_session_revocations.revoked_before, "
                        "excluded.revoked_before), "
                        "expires_at = MAX(deleted_session_revocations.expires_at, "
                        "excluded.expires_at)"
                    ),
                    {
                        "subject_hash": subject_hash,
                        "revoked_before": now_epoch,
                        "expires_at": expires_at,
                    },
                )

            # Emit neutral membership_changed notices for remaining participants
            if pending_events and await _table_exists(conn, "reminder_outbox"):
                producer = EventProducer()
                for event in pending_events:
                    await producer.record(conn, event, now_epoch)

            return DeletionResultDTO(
                already_deleted=False,
                deleted_lists=deleted_lists,
                transferred_lists=transferred_lists,
                cancelled_reservations=own_reservations_count,
                anonymized_items=anonymized_items,
            )

        start_perf = time.perf_counter()
        try:
            result = await self._store.transaction(work)
        except Exception as err:
            duration_ms = round((time.perf_counter() - start_perf) * 1000.0, 2)
            logger.error(
                "Account deletion failed",
                exc_info=True,
                extra={
                    "event": "account_deletion_failed",
                    "subject_hash_prefix": subject_hash[:12],
                    "error_class": type(err).__name__,
                    "duration_ms": duration_ms,
                },
            )
            raise

        duration_ms = round((time.perf_counter() - start_perf) * 1000.0, 2)
        if result.already_deleted:
            logger.info(
                "Account deletion skipped: already deleted",
                extra={
                    "event": "account_deletion_already_deleted",
                    "subject_hash_prefix": subject_hash[:12],
                    "duration_ms": duration_ms,
                },
            )
        else:
            logger.info(
                "Account deleted",
                extra={
                    "event": "account_deleted",
                    "subject_hash_prefix": subject_hash[:12],
                    "deleted_lists": result.deleted_lists,
                    "transferred_lists": result.transferred_lists,
                    "cancelled_reservations": result.cancelled_reservations,
                    "anonymized_items": result.anonymized_items,
                    "duration_ms": duration_ms,
                },
            )
        return result


async def _delete_if_table_exists_in(
    conn: AsyncConnection,
    table_name: str,
    column_name: str,
    ids: list[int],
) -> None:
    """Delete rows matching an integer ID list from an optional table if it exists."""
    if not ids or not await _table_exists(conn, table_name):
        return
    await conn.execute(
        text(f"DELETE FROM {table_name} WHERE {column_name} IN :ids").bindparams(
            bindparam("ids", expanding=True)
        ),
        {"ids": ids},
    )
