"""Claim and settle private occasion reminders."""

from __future__ import annotations

import logging
import secrets
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES, resolve_telegram_locale, t
from wishenka.notices.destinations import deactivate_bot_destination
from wishenka.notices.models import TransactionalStore
from wishenka.notices.rate import block_until, reserve_permit
from wishenka.notices.scheduler import utc_event_date

logger = logging.getLogger("wishenka.wishlists.notices")
locale_logger = logging.getLogger("wishenka.notices.reminders")


@dataclass(frozen=True)
class Reminder:
    """A fenced reminder with a freshly checked destination and text."""

    ident: int
    claimed_at: int
    chat_id: int
    body: str
    attempt: int
    claim_token: str


def _event_category(kind: object) -> str:
    if kind in ("list", "birthday"):
        return "reminders"
    if kind in ("reservation_changed", "reservation_confirmation"):
        return "reservation_changes"
    if kind in ("receipt_reverted", "receipt_increased"):
        return "gift_received"
    return "wishlist_changes"


def _render(kind: str, title: str, item: str | None, date: str, language: str | None) -> str:
    locale = resolve_telegram_locale(language)
    safe = title[:100]
    if kind == "receipt_reverted":
        return t("notices.receipt_reverted", locale, wish=(item or "")[:100], wishlist=safe)
    if kind == "receipt_increased":
        return t("notices.gift_received", locale, wish=(item or "")[:100], wishlist=safe)
    if kind == "item_quantity_overbooked":
        return t("notices.item_quantity_overbooked", locale, wish=(item or "")[:100], wishlist=safe)
    if kind not in ("list", "birthday"):
        subject = f"{item[:100]} — {safe}" if item else safe
        return t(f"notices.reminder.{kind}", locale, subject=subject)
    return t("notices.reminder.occasion", locale, title=safe, date=date)


def _normalize_row_locale(raw_locale: object, *, channel: str) -> str:
    fallback_used = raw_locale not in SUPPORTED_LOCALES
    locale = str(raw_locale) if not fallback_used else DEFAULT_LOCALE
    locale_logger.debug(
        "Reminder recipient locale resolved: locale=%s",
        locale,
        extra={
            "event": "notice_locale_resolved",
            "channel": channel,
            "locale": locale,
            "fallback_used": fallback_used,
        },
    )
    return locale


async def _fetch_first_with_locale_fallback(
    conn: AsyncConnection,
    sql_with_locale: str,
    sql_without_locale: str,
    params: dict[str, Any],
) -> tuple[Any, object]:
    """Fetch a row with ``u.locale``, defaulting to ``None`` if legacy column is absent."""
    try:
        row = (await conn.execute(text(sql_with_locale), params)).mappings().first()
    except (OperationalError, sqlite3.OperationalError) as exc:
        if "no such column" not in str(exc).lower():
            raise
        row = (await conn.execute(text(sql_without_locale), params)).mappings().first()
        return row, None
    return row, (row["locale"] if row is not None else None)


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
    if data["kind"] == "item_quantity_overbooked":
        allowed = await conn.scalar(
            text(
                "SELECT 1 FROM wl_items i JOIN wl_lists l ON l.id=i.wishlist_id "
                "JOIN wl_reservations r ON r.wish_item_id=i.id AND r.user_id=:user "
                "WHERE i.id=:item AND l.id=:list AND l.status IN ('active','archived') "
                "AND r.status IN ('active','purchased') "
                "AND (i.recipient_user_id IS NULL OR i.recipient_user_id<>:user) "
                "AND (l.is_collaborative=1 OR l.owner_id<>:user) "
                "AND (i.received_quantity + COALESCE("
                "(SELECT SUM(r2.quantity) FROM wl_reservations r2 "
                "WHERE r2.wish_item_id=i.id AND r2.status IN ('active','purchased')), 0)) "
                "> i.quantity LIMIT 1"
            ),
            {"user": data["user_id"], "item": data["item_id"], "list": data["list_id"]},
        )
        if not allowed:
            return False
    if data["kind"] in ("receipt_reverted", "receipt_increased"):
        extra = "AND i.received_quantity > 0 " if data["kind"] == "receipt_increased" else ""
        allowed = await conn.scalar(
            text(
                "SELECT 1 FROM wl_items i JOIN wl_lists l ON l.id=i.wishlist_id "
                "JOIN wl_reservations r ON r.wish_item_id=i.id AND r.user_id=:user "
                "WHERE i.id=:item AND l.id=:list AND l.status IN ('active','archived') "
                "AND r.status IN ('active','purchased') "
                "AND (i.recipient_user_id IS NULL OR i.recipient_user_id<>:user) "
                f"{extra}"
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
            text(
                "SELECT 1 FROM wl_lists l WHERE l.id=:list AND (l.owner_id=:user "
                "OR EXISTS (SELECT 1 FROM wl_members m "
                "WHERE m.wishlist_id=l.id AND m.user_id=:user))"
            ),
            params,
        )
        if not member:
            return False
    return True


async def _read_user_setting(
    conn: AsyncConnection, user_id: object, kind: object, category: str
) -> object:
    """Read user notification setting; for birthday reminders prefer birthday_reminders."""
    if kind == "birthday":
        return await conn.scalar(
            text(
                "SELECT COALESCE("
                "(SELECT enabled FROM user_notification_settings "
                "WHERE user_id=:user AND event_type='birthday_reminders'), "
                "(SELECT enabled FROM user_notification_settings "
                "WHERE user_id=:user AND event_type='reminders')"
                ")"
            ),
            {"user": user_id},
        )
    return await conn.scalar(
        text(
            "SELECT enabled FROM user_notification_settings WHERE user_id=:user "
            "AND event_type=:category"
        ),
        {"user": user_id, "category": category},
    )


async def claim_reminder(
    store: TransactionalStore, now: int, lease: int, global_limit: int, chat_interval: int
) -> Reminder | None:
    """Claim a due row after checking its current access, settings and date."""
    skipped: list[tuple[int, str, str]] = []

    async def work(conn: AsyncConnection) -> Reminder | None:
        skipped.clear()
        await conn.execute(
            text(
                "UPDATE reminder_outbox SET status='uncertain',claimed_at=NULL,claim_token=NULL,"
                "updated_at=:now WHERE status='sending' AND claimed_at<=:stale"
            ),
            {"now": now, "stale": now - lease},
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
            category = _event_category(row["kind"])
            if not await _event_authorized(conn, row):
                await conn.execute(
                    text(
                        "UPDATE reminder_outbox SET status='skipped',next_attempt_at=:now,"
                        "updated_at=:now WHERE id=:id"
                    ),
                    {"id": row["id"], "now": now},
                )
                skipped.append((int(row["id"]), str(row["kind"]), "unauthorized"))
                continue
            dest, raw_dest_locale = await _fetch_first_with_locale_fallback(
                conn,
                "SELECT d.chat_id,u.locale FROM bot_destinations d JOIN users u "
                "ON d.user_id=u.telegram_id WHERE u.telegram_id=:user AND d.active=1",
                "SELECT d.chat_id FROM bot_destinations d JOIN users u "
                "ON d.user_id=u.telegram_id WHERE u.telegram_id=:user AND d.active=1",
                {"user": row["user_id"]},
            )
            setting = await _read_user_setting(conn, row["user_id"], row["kind"], category)
            title = None
            item_title = None
            if row["kind"] == "birthday":
                birthday = (
                    (
                        await conn.execute(
                            text(
                                "SELECT b.label FROM birthday_entries b JOIN users u ON "
                                "u.telegram_id=b.owner_id "
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
                                "AND (:item=ri.id OR (:item IS NULL AND "
                                ":kind IN ('list_archived','list_restored','list_updated'))) "
                                "AND r.user_id=:user AND (r.status IN ('active','purchased') "
                                "OR :kind='reservation_confirmation') "
                                "AND (ri.recipient_user_id IS NULL OR ri.recipient_user_id<>:user) "
                                "AND (l.is_collaborative=1 OR l.owner_id<>:user)))"
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
                    text(
                        "UPDATE reminder_outbox SET status='skipped',next_attempt_at=:now,"
                        "updated_at=:now WHERE id=:id"
                    ),
                    {"id": row["id"], "now": now},
                )
                skipped.append((int(row["id"]), str(row["kind"]), "ineligible"))
                continue
            if not await reserve_permit(
                conn, int(dest["chat_id"]), now, global_limit, chat_interval
            ):
                await conn.execute(
                    text(
                        "UPDATE reminder_outbox SET next_attempt_at=:next,updated_at=:now "
                        "WHERE id=:id AND status='pending'"
                    ),
                    {"next": now + 1, "now": now, "id": row["id"]},
                )
                continue
            token = secrets.token_urlsafe(18)
            await conn.execute(
                text(
                    "UPDATE reminder_outbox SET "
                    "status='sending',claimed_at=:now,claim_token=:token,attempts=attempts+1,"
                    "updated_at=:now WHERE id=:id AND status='pending'"
                ),
                {"now": now, "id": row["id"], "token": token},
            )
            resolved_locale = _normalize_row_locale(raw_dest_locale, channel="reminder_claim")
            body = _render(row["kind"], str(title), item_title, row["event_date"], resolved_locale)
            return Reminder(
                int(row["id"]), now, int(dest["chat_id"]), body, int(row["attempts"]) + 1, token
            )
        return None

    claimed = await store.transaction(work)
    for reminder_id, kind, reason in skipped:
        logger.debug(
            "Service notice skipped: kind=%s reason=%s",
            kind,
            reason,
            extra={
                "event": "service_notice_skipped",
                "outbox_id": reminder_id,
                "kind": kind,
                "reason": reason,
            },
        )
    return claimed


async def refresh_reminder(store: TransactionalStore, claim: Reminder, now: int) -> Reminder | None:
    """Recheck consent and refresh authorized text immediately before sending."""

    async def work(conn: AsyncConnection) -> Reminder | None:
        row, raw_row_locale = await _fetch_first_with_locale_fallback(
            conn,
            "SELECT q.*,d.chat_id,u.locale FROM reminder_outbox q "
            "JOIN users u ON u.telegram_id=q.user_id "
            "JOIN bot_destinations d ON d.user_id=u.telegram_id AND d.active=1 "
            "WHERE q.id=:id AND q.status='sending' AND q.claim_token=:token",
            "SELECT q.*,d.chat_id FROM reminder_outbox q "
            "JOIN users u ON u.telegram_id=q.user_id "
            "JOIN bot_destinations d ON d.user_id=u.telegram_id AND d.active=1 "
            "WHERE q.id=:id AND q.status='sending' AND q.claim_token=:token",
            {"id": claim.ident, "token": claim.claim_token},
        )
        if row is None or row["chat_id"] != claim.chat_id:
            return None
        if not await _event_authorized(conn, row):
            return None
        category = _event_category(row["kind"])
        enabled = await _read_user_setting(conn, row["user_id"], row["kind"], category)
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
                    "SELECT b.label FROM birthday_entries b "
                    "JOIN users u ON u.telegram_id=b.owner_id "
                    "WHERE b.id=:id AND b.revision=:revision AND "
                    "b.deleted=0 AND u.telegram_id=:user"
                ),
                {"id": row["birthday_id"], "revision": row["revision"], "user": row["user_id"]},
            )
            if title is None:
                return None
            resolved_locale = _normalize_row_locale(raw_row_locale, channel="reminder_refresh")
            return replace(
                claim,
                body=_render(row["kind"], str(title), None, row["event_date"], resolved_locale),
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
                        "AND (:item=ri.id OR (:item IS NULL AND "
                        ":kind IN ('list_archived','list_restored','list_updated'))) "
                        "AND r.user_id=:user AND (r.status IN ('active','purchased') "
                        "OR :kind='reservation_confirmation') "
                        "AND (ri.recipient_user_id IS NULL OR ri.recipient_user_id<>:user) "
                        "AND (l.is_collaborative=1 OR l.owner_id<>:user)))"
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
        resolved_locale = _normalize_row_locale(raw_row_locale, channel="reminder_refresh")
        return replace(
            claim,
            body=_render(
                row["kind"],
                str(result["title"]),
                result["item_title"],
                row["event_date"],
                resolved_locale,
            ),
        )

    return await store.transaction(work)


async def settle_reminder(
    store: TransactionalStore,
    claim: Reminder,
    status: str,
    next_attempt: int,
    error_class: str | None = None,
    throttle_until: int | None = None,
    updated_at: int | None = None,
) -> bool:
    """Settle only the current fenced claim."""
    effective_updated = next_attempt if updated_at is None else updated_at

    async def work(conn: AsyncConnection) -> bool:
        result = await conn.execute(
            text(
                "UPDATE reminder_outbox SET status=:status,next_attempt_at=:next,"
                "claimed_at=NULL,claim_token=NULL,updated_at=:updated_at "
                "WHERE id=:id AND status='sending' AND claim_token=:token"
            ),
            {
                "status": status,
                "next": next_attempt,
                "updated_at": effective_updated,
                "id": claim.ident,
                "token": claim.claim_token,
            },
        )
        if result.rowcount and error_class in ("TelegramForbiddenError", "TelegramNotFound"):
            await deactivate_bot_destination(conn, claim.chat_id)
        if result.rowcount and throttle_until is not None:
            await block_until(conn, throttle_until)
        if result.rowcount:
            statement = (
                "UPDATE receipt_delivery_fence SET state='uncertain'"
                if status == "uncertain"
                else "DELETE FROM receipt_delivery_fence"
            )
            await conn.execute(
                text(statement + " WHERE queue='reminder' AND row_id=:id AND attempt_id=:token"),
                {"id": claim.ident, "token": claim.claim_token},
            )
        return bool(result.rowcount)

    return await store.transaction(work)
