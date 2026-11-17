"""Claim and settle private occasion reminders."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.notices.rate import block_until, reserve_permit
from wishenka.notices.scheduler import utc_event_date
from wishenka.wishlists.store import WishlistStore


@dataclass(frozen=True)
class Reminder:
    """A fenced reminder with a freshly checked destination and text."""

    ident: int
    claimed_at: int
    chat_id: int
    body: str
    attempt: int
    claim_token: str


def _render(kind: str, title: str, item: str | None, date: str, language: str | None) -> str:
    en = (language or "").lower().startswith("en")
    safe = title[:100]
    if kind not in ("list", "birthday"):
        subject = f"{item[:100]} — {safe}" if item else safe
        labels = {
            "item_created": ("Wish added", "Желание добавлено"),
            "item_updated": ("Wish updated", "Желание изменено"),
            "item_archived": ("Wish archived", "Желание архивировано"),
            "item_restored": ("Wish restored", "Желание восстановлено"),
            "list_updated": ("Wishlist updated", "Список изменён"),
            "list_archived": ("Wishlist archived", "Список архивирован"),
            "list_restored": ("Wishlist restored", "Список восстановлен"),
            "membership_changed": ("Wishlist membership changed", "Изменился состав списка"),
            "reservation_confirmation": (
                "Your reservation was updated",
                "Ваше бронирование изменено",
            ),
        }
        label = labels[kind][0 if en else 1]
        return f"{label}: {subject}."
    return (
        f"Upcoming occasion: {safe} ({date})." if en else f"Приближается событие: {safe} ({date})."
    )


async def _event_authorized(conn: AsyncConnection, row: Any) -> bool:
    """Recheck event-time membership and recipient status for private events."""
    data = row  # SQLAlchemy mapping
    # Legacy or mixed-version producers might have queued these. Their timing exposes
    # another giver's activity even if the body is neutral, so they must never be sent.
    if data["kind"] == "reservation_changed":
        return False
    if data["kind"] == "reservation_confirmation":
        allowed = await conn.scalar(
            text(
                "SELECT 1 FROM wl_items i JOIN wl_lists l ON l.id=i.wishlist_id "
                "JOIN wl_reservations r ON r.wish_item_id=i.id AND r.user_id=:user "
                "WHERE i.id=:item AND l.id=:list AND l.status='active' "
                "AND (i.recipient_user_id IS NULL OR i.recipient_user_id<>:user) "
                "AND (l.is_collaborative=1 OR l.owner_id<>:user) LIMIT 1"
            ),
            {"user": data["user_id"], "item": data["item_id"], "list": data["list_id"]},
        )
        if not allowed:
            return False
    if data["list_id"] is None or data["kind"] in ("list", "birthday"):
        return True
    params = {"list": data["list_id"], "user": data["user_id"], "item": data["item_id"]}
    if data["requires_membership"]:
        member = await conn.scalar(
            text("SELECT 1 FROM wl_members WHERE wishlist_id=:list AND user_id=:user"), params
        )
        if not member:
            return False
    return True


async def claim_reminder(
    store: WishlistStore, now: int, lease: int, global_limit: int, chat_interval: int
) -> Reminder | None:
    """Claim a due row after checking its current access, settings and date."""

    async def work(conn: AsyncConnection) -> Reminder | None:
        await conn.execute(
            text(
                "UPDATE reminder_outbox SET status='uncertain',claimed_at=NULL,claim_token=NULL "
                "WHERE status='sending' AND claimed_at<=:stale"
            ),
            {"stale": now - lease},
        )
        has_users = await conn.scalar(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'")
        )
        if not has_users:
            return None
        rows = (
            (
                await conn.execute(
                    text(
                        "SELECT * FROM reminder_outbox WHERE status='pending' AND "
                        "next_attempt_at<=:now "
                        "ORDER BY id LIMIT 100"
                    ),
                    {"now": now},
                )
            )
            .mappings()
            .all()
        )
        for row in rows:
            is_change = row["kind"] not in ("list", "birthday")
            category = (
                "reservation_changes"
                if row["kind"] in ("reservation_changed", "reservation_confirmation")
                else "wishlist_changes"
                if is_change
                else "reminders"
            )
            if not await _event_authorized(conn, row):
                await conn.execute(
                    text("UPDATE reminder_outbox SET status='skipped' WHERE id=:id"),
                    {"id": row["id"]},
                )
                continue
            dest = (
                (
                    await conn.execute(
                        text(
                            "SELECT d.chat_id,u.language_code FROM bot_destinations d JOIN users u "
                            "ON d.user_id=u.id WHERE u.telegram_id=:user AND d.active=1"
                        ),
                        {"user": row["user_id"]},
                    )
                )
                .mappings()
                .first()
            )
            setting = await conn.scalar(
                text(
                    "SELECT enabled FROM user_notification_settings WHERE user_id=:user "
                    "AND event_type=:category"
                ),
                {"user": row["user_id"], "category": category},
            )
            title = None
            item_title = None
            if row["kind"] == "birthday":
                birthday = (
                    (
                        await conn.execute(
                            text(
                                "SELECT b.label FROM birthday_entries b JOIN users u ON "
                                "u.id=b.owner_id "
                                "WHERE b.id=:id AND b.revision=:revision AND b.deleted=0 "
                                "AND u.telegram_id=:user"
                            ),
                            {
                                "id": row["birthday_id"],
                                "revision": row["revision"],
                                "user": row["user_id"],
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                title = birthday["label"] if birthday else None
            elif is_change:
                item = (
                    (
                        await conn.execute(
                            text(
                                "SELECT l.title AS list_title,i.title AS "
                                "item_title FROM wl_lists l "
                                "LEFT JOIN wl_items i ON i.wishlist_id=l.id AND i.id=:item "
                                "WHERE l.id=:list AND l.status IN ('active','archived') "
                                "AND (:item IS NULL OR i.id IS NOT NULL) "
                                "AND (l.owner_id=:user OR EXISTS (SELECT 1 FROM wl_members m "
                                "WHERE m.wishlist_id=l.id AND m.user_id=:user) OR "
                                "EXISTS (SELECT 1 FROM wl_reservations r JOIN wl_items ri "
                                "ON ri.id=r.wish_item_id WHERE ri.wishlist_id=l.id "
                                "AND (:item=ri.id OR (:item IS NULL AND :kind='list_archived')) "
                                "AND r.user_id=:user AND (r.status IN ('active','purchased') "
                                "OR :kind='reservation_confirmation')))"
                            ),
                            {
                                "list": row["list_id"],
                                "item": row["item_id"],
                                "user": row["user_id"],
                                "kind": row["kind"],
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                title = item["list_title"] if item else None
                item_title = item["item_title"] if item else None
            else:
                wl = (
                    (
                        await conn.execute(
                            text(
                                "SELECT l.title,l.event_date FROM wl_lists l WHERE "
                                "l.id=:id AND l.status='active' "
                                "AND (l.owner_id=:user OR EXISTS "
                                "(SELECT 1 FROM wl_members m WHERE m.wishlist_id=l.id AND "
                                "m.user_id=:user) OR EXISTS "
                                "(SELECT 1 FROM wl_favorites f WHERE f.wishlist_id=l.id "
                                "AND f.user_id=:user))"
                            ),
                            {
                                "id": row["list_id"],
                                "date": row["event_date"],
                                "user": row["user_id"],
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                try:
                    date_matches = bool(
                        wl
                        and utc_event_date(str(wl["event_date"])).isoformat() == row["event_date"]
                    )
                except ValueError:
                    date_matches = False
                title = wl["title"] if date_matches and wl else None
            if row["list_id"] is not None:
                override = await conn.scalar(
                    text(
                        "SELECT enabled FROM wl_list_notification_settings WHERE user_id=:user "
                        "AND wishlist_id=:list AND event_type=:category"
                    ),
                    {"user": row["user_id"], "list": row["list_id"], "category": category},
                )
                if override is not None:
                    setting = override
            if (
                not dest
                or setting == 0
                or title is None
                or (row["kind"] == "reservation_confirmation" and setting != 1)
            ):
                await conn.execute(
                    text("UPDATE reminder_outbox SET status='skipped' WHERE id=:id"),
                    {"id": row["id"]},
                )
                continue
            if not await reserve_permit(
                conn, int(dest["chat_id"]), now, global_limit, chat_interval
            ):
                await conn.execute(
                    text(
                        "UPDATE reminder_outbox SET next_attempt_at=:next "
                        "WHERE id=:id AND status='pending'"
                    ),
                    {"next": now + 1, "id": row["id"]},
                )
                continue
            token = secrets.token_urlsafe(18)
            await conn.execute(
                text(
                    "UPDATE reminder_outbox SET "
                    "status='sending',claimed_at=:now,claim_token=:token,attempts=attempts+1 "
                    "WHERE id=:id AND status='pending'"
                ),
                {"now": now, "id": row["id"], "token": token},
            )
            body = _render(
                row["kind"], str(title), item_title, row["event_date"], dest["language_code"]
            )
            return Reminder(
                int(row["id"]), now, int(dest["chat_id"]), body, int(row["attempts"]) + 1, token
            )
        return None

    return await store.transaction(work)


async def refresh_reminder(store: WishlistStore, claim: Reminder, now: int) -> Reminder | None:
    """Recheck consent and refresh authorized text immediately before sending."""

    async def work(conn: AsyncConnection) -> Reminder | None:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT q.*,d.chat_id,u.language_code FROM reminder_outbox q "
                        "JOIN users u ON u.telegram_id=q.user_id "
                        "JOIN bot_destinations d ON d.user_id=u.id AND d.active=1 "
                        "WHERE q.id=:id AND q.status='sending' AND q.claim_token=:token"
                    ),
                    {"id": claim.ident, "token": claim.claim_token},
                )
            )
            .mappings()
            .first()
        )
        if row is None or row["chat_id"] != claim.chat_id:
            return None
        if not await _event_authorized(conn, row):
            return None
        category = (
            "reminders"
            if row["kind"] in ("list", "birthday")
            else "reservation_changes"
            if row["kind"] in ("reservation_changed", "reservation_confirmation")
            else "wishlist_changes"
        )
        enabled = await conn.scalar(
            text(
                "SELECT enabled FROM "
                "user_notification_settings WHERE user_id=:user AND event_type=:kind"
            ),
            {"user": row["user_id"], "kind": category},
        )
        if row["list_id"] is not None:
            override = await conn.scalar(
                text(
                    "SELECT enabled FROM wl_list_notification_settings "
                    "WHERE user_id=:user AND wishlist_id=:list AND event_type=:kind"
                ),
                {"user": row["user_id"], "list": row["list_id"], "kind": category},
            )
            if override is not None:
                enabled = override
        if enabled == 0 or (row["kind"] == "reservation_confirmation" and enabled != 1):
            return None
        if category == "reminders" and row["event_date"] < (
            datetime.fromtimestamp(now, UTC).date().isoformat()
        ):
            return None
        if row["kind"] == "birthday":
            title = await conn.scalar(
                text(
                    "SELECT b.label FROM birthday_entries b JOIN users u ON u.id=b.owner_id "
                    "WHERE b.id=:id AND b.revision=:revision AND "
                    "b.deleted=0 AND u.telegram_id=:user"
                ),
                {"id": row["birthday_id"], "revision": row["revision"], "user": row["user_id"]},
            )
            if title is None:
                return None
            return replace(
                claim,
                body=_render(
                    row["kind"], str(title), None, row["event_date"], row["language_code"]
                ),
            )
        result = (
            (
                await conn.execute(
                    text(
                        "SELECT l.title,l.status,l.event_date,i.id AS item_id,"
                        "i.title AS item_title "
                        "FROM wl_lists l "
                        "LEFT JOIN wl_items i ON i.id=:item AND i.wishlist_id=l.id "
                        "WHERE l.id=:list AND l.status IN ('active','archived') "
                        "AND (l.owner_id=:user OR EXISTS (SELECT 1 FROM wl_members m "
                        "WHERE m.wishlist_id=l.id AND m.user_id=:user) OR "
                        "(:kind='list' AND EXISTS (SELECT 1 FROM wl_favorites f "
                        "WHERE f.wishlist_id=l.id AND f.user_id=:user)) OR "
                        "EXISTS (SELECT 1 FROM wl_reservations r JOIN wl_items ri "
                        "ON ri.id=r.wish_item_id WHERE ri.wishlist_id=l.id "
                        "AND (:item=ri.id OR (:item IS NULL AND :kind='list_archived')) "
                        "AND r.user_id=:user AND (r.status IN ('active','purchased') "
                        "OR :kind='reservation_confirmation')))"
                    ),
                    {
                        "item": row["item_id"],
                        "list": row["list_id"],
                        "user": row["user_id"],
                        "kind": row["kind"],
                    },
                )
            )
            .mappings()
            .first()
        )
        if result is None or (row["item_id"] is not None and result["item_id"] is None):
            return None
        if row["kind"] == "list":
            if result["status"] != "active":
                return None
            try:
                if utc_event_date(str(result["event_date"])).isoformat() != row["event_date"]:
                    return None
            except ValueError:
                return None
        return replace(
            claim,
            body=_render(
                row["kind"],
                str(result["title"]),
                result["item_title"],
                row["event_date"],
                row["language_code"],
            ),
        )

    return await store.transaction(work)


async def settle_reminder(
    store: WishlistStore,
    claim: Reminder,
    status: str,
    next_attempt: int,
    error_class: str | None = None,
    throttle_until: int | None = None,
) -> bool:
    """Settle only the current fenced claim."""

    async def work(conn: AsyncConnection) -> bool:
        result = await conn.execute(
            text(
                "UPDATE reminder_outbox SET status=:status,next_attempt_at=:next,"
                "claimed_at=NULL,claim_token=NULL "
                "WHERE id=:id AND status='sending' AND claim_token=:token"
            ),
            {"status": status, "next": next_attempt, "id": claim.ident, "token": claim.claim_token},
        )
        if result.rowcount and error_class in ("TelegramForbiddenError", "TelegramNotFound"):
            await conn.execute(
                text("UPDATE bot_destinations SET active=0 WHERE chat_id=:chat"),
                {"chat": claim.chat_id},
            )
        if result.rowcount and throttle_until is not None:
            await block_until(conn, throttle_until)
        return bool(result.rowcount)

    return await store.transaction(work)
