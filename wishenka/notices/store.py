"""Queue store of the gift notice path: claim, settle and purge rows of the notice queue."""

from __future__ import annotations

import logging
import math
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.config import Settings
from wishenka.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES
from wishenka.notices import reminders
from wishenka.notices.destinations import deactivate_bot_destination
from wishenka.notices.models import (
    SKIP_TARGET_GONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENDING,
    STATUS_SENT,
    STATUS_SKIPPED,
)
from wishenka.notices.rate import block_until, reserve_permit
from wishenka.wishlists.store import WishlistStore

T = TypeVar("T")

logger = logging.getLogger("wishenka.wishlists.notices")
locale_logger = logging.getLogger("wishenka.notices.store")

CLAIM_BATCH_LIMIT = 50
DEFAULT_PURGE_BATCH_SIZE = 500
STALE_CLAIM_ERROR = "StaleClaim"
_EVENT_MESSAGES = {
    "receipt_notice_retry_scheduled": "Notice queue row retry scheduled",
    "receipt_notice_failed_terminal": "Notice queue row failed for good",
    "receipt_notice_uncertain": "Notice queue row delivery uncertain",
    "receipt_notice_skipped_ineligible": "Notice queue row skipped as ineligible",
}
_Event = tuple[str, int, int]

_DUE_SQL = text(
    "SELECT o.id, o.giver_user_id, o.status, o.attempts, o.ambiguous, "
    "i.title AS wish_title, l.title AS list_title, l.status AS list_status "
    "FROM notification_outbox o "
    "LEFT JOIN wl_items i ON i.id = o.wish_item_id "
    "LEFT JOIN wl_lists l ON l.id = o.wishlist_id "
    "WHERE (o.status = 'pending' AND o.next_attempt_at <= :now) "
    "OR (o.status = 'sending' AND o.claimed_at <= :stale_before) "
    "ORDER BY o.next_attempt_at, o.id LIMIT :limit"
)


@dataclass(frozen=True)
class ClaimedNotice:
    """A row handed to the worker for sending.

    ``attempt`` is the attempt number this claim represents, ``ambiguous`` is the flag before
    the claim, and ``claim_token`` fences every settlement.
    """

    outbox_id: int
    giver_user_id: int
    attempt: int
    ambiguous: bool
    claimed_at: int
    wish_title: str
    list_title: str
    language: str = DEFAULT_LOCALE
    claim_token: str = ""


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat()


class NoticeStore:
    """Every method is one ``BEGIN IMMEDIATE`` transaction through ``WishlistStore``."""

    def __init__(self, store: WishlistStore, settings: Settings) -> None:
        """Keep the shared store and the limits (lease, attempts, backoff) from ``settings``."""
        self._store = store
        self._lease = settings.receipt_notice_claim_lease_seconds
        self._max_attempts = settings.receipt_notice_max_attempts
        self._backoff_base = settings.receipt_notice_backoff_base_seconds
        self._backoff_max = settings.receipt_notice_backoff_max_seconds
        self.global_limit = settings.notice_global_per_second
        self.chat_interval = settings.notice_chat_interval_seconds

    def backoff_seconds(self, attempts: int) -> int:
        """Delay after the ``attempts``-th failed attempt: ``min(base * 2**(n-1), max)``."""
        exponent = max(attempts, 1) - 1
        return int(min(self._backoff_base * 2**exponent, self._backoff_max))

    @property
    def transactional_store(self) -> WishlistStore:
        """Expose the shared transaction boundary for delivery coordination."""
        return self._store

    async def transaction(self, work: Callable[[AsyncConnection], Awaitable[T]]) -> T:
        """Run ``work`` in one ``BEGIN IMMEDIATE`` transaction via the underlying store."""
        return await self._store.transaction(work)

    async def claim_reminder(self, now: int) -> reminders.Reminder | None:
        """Claim a due reminder row using this store's lease and rate-limit settings."""
        return await reminders.claim_reminder(
            self, now, self._lease, self.global_limit, self.chat_interval
        )

    async def refresh_reminder(
        self, claim: reminders.Reminder, now: int
    ) -> reminders.Reminder | None:
        """Recheck consent and refresh authorized reminder text before sending."""
        return await reminders.refresh_reminder(self, claim, now)

    async def settle_reminder(
        self,
        claim: reminders.Reminder,
        status: str,
        next_attempt: int,
        error_class: str | None = None,
        throttle_until: int | None = None,
        updated_at: int | None = None,
    ) -> bool:
        """Settle a fenced reminder claim inside one ``BEGIN IMMEDIATE`` transaction."""
        return await reminders.settle_reminder(
            self,
            claim,
            status,
            next_attempt,
            error_class,
            throttle_until,
            updated_at=updated_at,
        )

    async def claim_next(self, now: int) -> ClaimedNotice | None:
        """Claim the oldest due ``pending`` row, settling dead rows on the way (design 7).

        Looks at no more than ``CLAIM_BATCH_LIMIT`` due rows. Returns ``None`` when nothing
        can be sent now.
        """

        events: list[_Event] = []

        async def work(conn: AsyncConnection) -> ClaimedNotice | None:
            events.clear()
            params = {"now": now, "stale_before": now - self._lease, "limit": CLAIM_BATCH_LIMIT}
            rows = (await conn.execute(_DUE_SQL, params)).mappings().all()
            for row in rows:
                if row["status"] == STATUS_SENDING:
                    events.append(await self._settle_stale(conn, row, now))
                elif row["list_status"] in (None, "deleted") or row["wish_title"] is None:
                    await self._skip_gone(conn, row["id"], now)
                    events.append(
                        ("receipt_notice_skipped_ineligible", int(row["id"]), int(row["attempts"]))
                    )
                else:
                    delivery = await self._eligible(conn, int(row["id"]))
                    if delivery is None:
                        await self._skip_gone(conn, row["id"], now)
                        events.append(
                            (
                                "receipt_notice_skipped_ineligible",
                                int(row["id"]),
                                int(row["attempts"]),
                            )
                        )
                        continue
                    if not await reserve_permit(
                        conn, delivery[0], now, self.global_limit, self.chat_interval
                    ):
                        await conn.execute(
                            text(
                                "UPDATE notification_outbox SET next_attempt_at=:next "
                                "WHERE id=:id AND status='pending'"
                            ),
                            {"next": now + 1, "id": row["id"]},
                        )
                        continue
                    return await self._claim(conn, row, now, delivery)
            return None

        claimed = await self._store.transaction(work)
        for event, outbox_id, attempt in events:
            logger.debug(
                _EVENT_MESSAGES[event],
                extra={"event": event, "outbox_id": outbox_id, "attempt": attempt},
            )
        return claimed

    async def complete(self, claim: ClaimedNotice, now: int) -> bool:
        """Mark the claimed row ``sent``; ``False`` when the claim was lost (late write)."""
        return await self._settle(claim, now, STATUS_SENT, None)

    async def uncertain(self, claim: ClaimedNotice, now: int, error_class: str | None) -> bool:
        """Record a send whose external outcome cannot be established."""
        return await self._settle(claim, now, "uncertain", error_class, ambiguous=True)

    async def refresh_claim(self, claim: ClaimedNotice) -> ClaimedNotice | None:
        """Recheck consent and refresh authorized text immediately before delivery."""

        async def work(conn: AsyncConnection) -> ClaimedNotice | None:
            owned = await conn.scalar(
                text(
                    "SELECT 1 FROM notification_outbox WHERE id=:id AND status='sending' "
                    "AND claim_token=:token"
                ),
                {"id": claim.outbox_id, "token": claim.claim_token},
            )
            if not owned:
                return None
            delivery = await self._eligible(conn, claim.outbox_id)
            if not delivery or delivery[0] != claim.giver_user_id:
                return None
            return replace(
                claim, language=delivery[1], wish_title=delivery[2], list_title=delivery[3]
            )

        return await self._store.transaction(work)

    async def skip_claim(self, claim: ClaimedNotice, now: int) -> bool:
        """Fence and skip a claim whose consent or access has changed."""
        return await self._settle(claim, now, STATUS_SKIPPED, None)

    async def fail(
        self,
        claim: ClaimedNotice,
        now: int,
        error_class: str | None,
        *,
        ambiguous: bool = False,
        retry_after: float | None = None,
    ) -> bool:
        """Mark the claimed row ``failed`` (final); ``False`` when the claim was lost.

        ``ambiguous`` stores the flag of an unconfirmed send so the gauge counts the row.
        """
        return await self._settle(
            claim,
            now,
            STATUS_FAILED,
            error_class,
            ambiguous=ambiguous,
            throttle_until=now + math.ceil(retry_after) if retry_after else None,
        )

    async def reschedule(
        self,
        claim: ClaimedNotice,
        now: int,
        *,
        error_class: str | None,
        retry_after: float | None = None,
        ambiguous: bool = False,
    ) -> bool:
        """Return the claimed row to ``pending`` after the backoff (at least ``retry_after``).

        ``ambiguous`` raises the flag that bounds the extra send. ``False`` means the claim was
        lost.
        """
        delay = max(self.backoff_seconds(claim.attempt), math.ceil(retry_after or 0))
        return await self._settle(
            claim,
            now,
            STATUS_PENDING,
            error_class,
            next_at=now + delay,
            ambiguous=ambiguous,
            throttle_until=now + math.ceil(retry_after) if retry_after else None,
        )

    async def _settle(
        self,
        claim: ClaimedNotice,
        now: int,
        status: str,
        error_class: str | None,
        *,
        next_at: int | None = None,
        ambiguous: bool = False,
        throttle_until: int | None = None,
    ) -> bool:
        """One guarded write: it changes the row only while this claim still owns it."""

        async def work(conn: AsyncConnection) -> bool:
            result = await conn.execute(
                text(
                    "UPDATE notification_outbox SET status = :status, claimed_at = NULL, "
                    "claim_token = NULL, "
                    "next_attempt_at = COALESCE(:next_at, next_attempt_at), "
                    "ambiguous = CASE WHEN :ambiguous THEN 1 ELSE ambiguous END, "
                    "last_error_class = :error, updated_at = :updated "
                    "WHERE id = :id AND status = 'sending' AND claim_token = :token"
                ),
                {
                    "status": status,
                    "next_at": next_at,
                    "ambiguous": int(ambiguous),
                    "error": error_class,
                    "updated": _iso(now),
                    "id": claim.outbox_id,
                    "token": claim.claim_token,
                },
            )
            if result.rowcount and error_class in ("TelegramForbiddenError", "TelegramNotFound"):
                await deactivate_bot_destination(conn, claim.giver_user_id, now)
            if result.rowcount and throttle_until is not None:
                await block_until(conn, throttle_until)
            if result.rowcount:
                statement = (
                    "UPDATE receipt_delivery_fence SET state='uncertain'"
                    if status == "uncertain"
                    else "DELETE FROM receipt_delivery_fence"
                )
                await conn.execute(
                    text(statement + " WHERE queue='gift' AND row_id=:id AND attempt_id=:token"),
                    {"id": claim.outbox_id, "token": claim.claim_token},
                )
            return bool(result.rowcount)

        changed = await self._store.transaction(work)
        if not changed:
            logger.debug(
                "Notice queue row settle ignored, the claim was lost",
                extra={"event": "receipt_notice_late_write_ignored", "outbox_id": claim.outbox_id},
            )
        return changed

    async def purge_finished(
        self,
        threshold: datetime,
        *,
        now: datetime | None = None,
        reminder_threshold: datetime | None = None,
        batch_size: int = DEFAULT_PURGE_BATCH_SIZE,
    ) -> int:
        """Delete terminal outbox rows in bounded per-transaction batches."""
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        effective_now = now or datetime.now(UTC)
        today_utc = effective_now.astimezone(UTC).date().isoformat()
        threshold_iso = threshold.isoformat()
        reminder_cutoff = int((reminder_threshold or threshold).timestamp())

        receipt_drained = False
        reminder_drained = False
        receipt_purged = 0
        reminder_purged = 0
        batches = 0

        while not (receipt_drained and reminder_drained):
            r_batch, m_batch = await self._purge_batch(
                threshold_iso=threshold_iso,
                reminder_cutoff=reminder_cutoff,
                today_utc=today_utc,
                batch_size=batch_size,
                purge_receipts=not receipt_drained,
                purge_reminders=not reminder_drained,
            )
            batches += 1
            receipt_purged += r_batch
            reminder_purged += m_batch
            if not receipt_drained and r_batch < batch_size:
                receipt_drained = True
            if not reminder_drained and m_batch < batch_size:
                reminder_drained = True

        total = receipt_purged + reminder_purged
        if total:
            logger.info(
                "Purged finished outbox rows: receipt_purged=%d reminder_purged=%d "
                "batches=%d batch_size=%d",
                receipt_purged,
                reminder_purged,
                batches,
                batch_size,
                extra={
                    "event": "notice_outbox_purged",
                    "receipt_purged": receipt_purged,
                    "reminder_purged": reminder_purged,
                    "total_purged": total,
                    "batches": batches,
                    "batch_size": batch_size,
                },
            )
        return total

    async def _purge_batch(
        self,
        *,
        threshold_iso: str,
        reminder_cutoff: int,
        today_utc: str,
        batch_size: int,
        purge_receipts: bool,
        purge_reminders: bool,
    ) -> tuple[int, int]:
        """Delete at most ``batch_size`` expired terminal rows per queue in one transaction."""

        async def work(conn: AsyncConnection) -> tuple[int, int]:
            r_deleted = 0
            m_deleted = 0
            if purge_receipts:
                receipt_result = await conn.execute(
                    text(
                        "DELETE FROM notification_outbox "
                        "WHERE id IN ("
                        "SELECT id FROM notification_outbox "
                        "WHERE updated_at <= :threshold "
                        "AND status IN ('sent', 'skipped', 'failed') "
                        "ORDER BY id LIMIT :batch_size"
                        ")"
                    ),
                    {"threshold": threshold_iso, "batch_size": batch_size},
                )
                r_deleted = int(receipt_result.rowcount)
            if purge_reminders:
                reminder_result = await conn.execute(
                    text(
                        "DELETE FROM reminder_outbox "
                        "WHERE id IN ("
                        "SELECT id FROM reminder_outbox "
                        "WHERE COALESCE(updated_at, next_attempt_at) <= :threshold_epoch "
                        "AND status IN ('sent', 'skipped', 'failed') "
                        "AND (kind NOT IN ('list', 'birthday') OR event_date < :today_utc) "
                        "ORDER BY id LIMIT :batch_size"
                        ")"
                    ),
                    {
                        "threshold_epoch": reminder_cutoff,
                        "today_utc": today_utc,
                        "batch_size": batch_size,
                    },
                )
                m_deleted = int(reminder_result.rowcount)
            return r_deleted, m_deleted

        return await self._store.transaction(work)

    async def purge_retention_records(
        self,
        *,
        birthday_threshold: datetime,
        destination_threshold: datetime,
        receipt_key_threshold: datetime,
    ) -> tuple[int, int, int]:
        """Physically delete expired deleted birthdays, inactive destinations, and dedup keys."""
        birthday_cutoff = int(birthday_threshold.timestamp())
        destination_cutoff = int(destination_threshold.timestamp())
        receipt_key_cutoff = int(receipt_key_threshold.timestamp())

        async def work(conn: AsyncConnection) -> tuple[int, int, int]:
            birthday_result = await conn.execute(
                text(
                    "DELETE FROM birthday_entries "
                    "WHERE deleted = 1 "
                    "AND (deleted_at IS NULL OR deleted_at <= :birthday_cutoff) "
                    "AND NOT EXISTS ("
                    "    SELECT 1 FROM reminder_outbox r "
                    "    WHERE r.birthday_id = birthday_entries.id "
                    "      AND r.status IN ('pending', 'sending', 'uncertain')"
                    ")"
                ),
                {"birthday_cutoff": birthday_cutoff},
            )
            destination_result = await conn.execute(
                text(
                    "DELETE FROM bot_destinations "
                    "WHERE active = 0 "
                    "AND (updated_at IS NULL OR updated_at <= :destination_cutoff)"
                ),
                {"destination_cutoff": destination_cutoff},
            )
            receipt_key_result = await conn.execute(
                text(
                    "DELETE FROM notice_receipt_keys "
                    "WHERE created_at <= :receipt_key_cutoff "
                    "AND NOT EXISTS ("
                    "    SELECT 1 FROM notification_outbox o "
                    "    WHERE o.event_type = notice_receipt_keys.event_type "
                    "      AND o.receipt_id = notice_receipt_keys.receipt_id "
                    "      AND o.giver_user_id = notice_receipt_keys.giver_user_id"
                    ")"
                ),
                {"receipt_key_cutoff": receipt_key_cutoff},
            )
            return (
                int(birthday_result.rowcount),
                int(destination_result.rowcount),
                int(receipt_key_result.rowcount),
            )

        birthdays_purged, destinations_purged, receipt_keys_purged = await self._store.transaction(
            work
        )
        if birthdays_purged or destinations_purged or receipt_keys_purged:
            logger.info(
                "Purged retention records: birthdays=%d destinations=%d receipt_keys=%d",
                birthdays_purged,
                destinations_purged,
                receipt_keys_purged,
                extra={
                    "event": "notice_retention_records_purged",
                    "birthdays_purged": birthdays_purged,
                    "destinations_purged": destinations_purged,
                    "receipt_keys_purged": receipt_keys_purged,
                },
            )
        return birthdays_purged, destinations_purged, receipt_keys_purged

    async def _settle_stale(self, conn: AsyncConnection, row: RowMapping, now: int) -> _Event:
        """Apply the ambiguous transition to a dead ``sending`` row; it is never sent now."""
        attempts = int(row["attempts"])
        await conn.execute(
            text(
                "UPDATE notification_outbox SET status = :status, ambiguous = 1, "
                "claimed_at = NULL, claim_token = NULL, next_attempt_at = :next_at, "
                "last_error_class = :error, "
                "updated_at = :updated WHERE id = :id"
            ),
            {
                "status": "uncertain",
                "next_at": now + self.backoff_seconds(attempts),
                "error": STALE_CLAIM_ERROR,
                "updated": _iso(now),
                "id": row["id"],
            },
        )
        return ("receipt_notice_uncertain", int(row["id"]), attempts)

    async def _skip_gone(self, conn: AsyncConnection, outbox_id: int, now: int) -> None:
        await conn.execute(
            text(
                "UPDATE notification_outbox SET status = :status, skip_reason = :reason, "
                "claimed_at = NULL, claim_token = NULL, updated_at = :updated WHERE id = :id"
            ),
            {
                "status": STATUS_SKIPPED,
                "reason": SKIP_TARGET_GONE,
                "updated": _iso(now),
                "id": outbox_id,
            },
        )

    async def _eligible(
        self, conn: AsyncConnection, ident: int
    ) -> tuple[int, str, str, str] | None:
        """Fail closed unless current preferences, role and a verified "
        "destination permit delivery."""
        if not await conn.scalar(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'")
        ):
            return None
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT d.chat_id,u.locale,i.title AS wish_title,"
                        "l.title AS list_title FROM notification_outbox o "
                        "JOIN wl_lists l ON l.id=o.wishlist_id JOIN wl_items i ON "
                        "i.id=o.wish_item_id "
                        "JOIN users u ON u.telegram_id=o.giver_user_id "
                        "JOIN bot_destinations d ON d.user_id=u.id AND d.active=1 "
                        "WHERE o.id=:id AND l.status != 'deleted' AND i.received_quantity > 0 "
                        "AND (i.recipient_user_id IS NULL OR "
                        "o.giver_user_id != i.recipient_user_id) "
                        "AND (l.is_collaborative=1 OR o.giver_user_id != l.owner_id) "
                        "AND COALESCE((SELECT enabled FROM wl_list_notification_settings s "
                        "WHERE s.user_id=o.giver_user_id AND s.wishlist_id=o.wishlist_id "
                        "AND s.event_type='gift_received'),(SELECT enabled FROM "
                        "user_notification_settings s "
                        "WHERE s.user_id=o.giver_user_id AND s.event_type='gift_received'),1)=1 "
                        "AND (o.requires_membership=0 OR EXISTS "
                        "(SELECT 1 FROM wl_members m WHERE m.wishlist_id=o.wishlist_id "
                        "AND m.user_id=o.giver_user_id)) "
                        "AND EXISTS (SELECT 1 FROM wl_reservations r WHERE r.wish_item_id=i.id "
                        "AND r.user_id=o.giver_user_id AND r.status IN ('active', 'purchased'))"
                    ),
                    {"id": ident},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        raw_locale = row["locale"]
        fallback_used = raw_locale not in SUPPORTED_LOCALES
        locale = str(raw_locale) if not fallback_used else DEFAULT_LOCALE
        locale_logger.debug(
            "Notice recipient locale resolved: locale=%s",
            locale,
            extra={
                "event": "notice_locale_resolved",
                "channel": "gift_notice",
                "locale": locale,
                "fallback_used": fallback_used,
            },
        )
        return (
            int(row["chat_id"]),
            locale,
            str(row["wish_title"]),
            str(row["list_title"]),
        )

    async def _claim(
        self, conn: AsyncConnection, row: RowMapping, now: int, delivery: tuple[int, str, str, str]
    ) -> ClaimedNotice:
        attempt = int(row["attempts"]) + 1
        token = secrets.token_urlsafe(18)
        await conn.execute(
            text(
                "UPDATE notification_outbox SET status = :status, claimed_at = :now, "
                "claim_token = :token, attempts = :attempt, updated_at = :updated WHERE id = :id"
            ),
            {
                "status": STATUS_SENDING,
                "now": now,
                "attempt": attempt,
                "updated": _iso(now),
                "id": row["id"],
                "token": token,
            },
        )
        return ClaimedNotice(
            outbox_id=int(row["id"]),
            giver_user_id=delivery[0],
            attempt=attempt,
            ambiguous=bool(row["ambiguous"]),
            claimed_at=now,
            wish_title=str(row["wish_title"]),
            list_title=str(row["list_title"]),
            language=delivery[1],
            claim_token=token,
        )


__all__ = [
    "CLAIM_BATCH_LIMIT",
    "DEFAULT_PURGE_BATCH_SIZE",
    "STALE_CLAIM_ERROR",
    "ClaimedNotice",
    "NoticeStore",
]
