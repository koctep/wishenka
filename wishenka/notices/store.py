"""Queue store of the gift notice path: claim, settle and purge rows of the notice queue."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.config import Settings
from wishenka.notices.models import (
    SKIP_TARGET_GONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENDING,
    STATUS_SENT,
    STATUS_SKIPPED,
)
from wishenka.wishlists.store import WishlistStore

logger = logging.getLogger("wishenka.wishlists.notices")

CLAIM_BATCH_LIMIT = 50
STALE_CLAIM_ERROR = "StaleClaim"
_EVENT_MESSAGES = {
    "receipt_notice_retry_scheduled": "Notice queue row retry scheduled",
    "receipt_notice_failed_terminal": "Notice queue row failed for good",
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
    the claim, ``claimed_at`` is the token the guarded settle writes must match.
    """

    outbox_id: int
    giver_user_id: int
    attempt: int
    ambiguous: bool
    claimed_at: int
    wish_title: str
    list_title: str


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

    def backoff_seconds(self, attempts: int) -> int:
        """Delay after the ``attempts``-th failed attempt: ``min(base * 2**(n-1), max)``."""
        exponent = max(attempts, 1) - 1
        return int(min(self._backoff_base * 2**exponent, self._backoff_max))

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
                if row["list_status"] in (None, "deleted") or row["wish_title"] is None:
                    await self._skip_gone(conn, row["id"], now)
                elif row["status"] == STATUS_SENDING:
                    events.append(await self._settle_stale(conn, row, now))
                else:
                    return await self._claim(conn, row, now)
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

    async def fail(
        self,
        claim: ClaimedNotice,
        now: int,
        error_class: str | None,
        *,
        ambiguous: bool = False,
    ) -> bool:
        """Mark the claimed row ``failed`` (final); ``False`` when the claim was lost.

        ``ambiguous`` stores the flag of an unconfirmed send so the gauge counts the row.
        """
        return await self._settle(claim, now, STATUS_FAILED, error_class, ambiguous=ambiguous)

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
            claim, now, STATUS_PENDING, error_class, next_at=now + delay, ambiguous=ambiguous
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
    ) -> bool:
        """One guarded write: it changes the row only while this claim still owns it."""

        async def work(conn: AsyncConnection) -> bool:
            result = await conn.execute(
                text(
                    "UPDATE notification_outbox SET status = :status, claimed_at = NULL, "
                    "next_attempt_at = COALESCE(:next_at, next_attempt_at), "
                    "ambiguous = CASE WHEN :ambiguous THEN 1 ELSE ambiguous END, "
                    "last_error_class = :error, updated_at = :updated "
                    "WHERE id = :id AND status = 'sending' AND claimed_at = :claimed_at"
                ),
                {
                    "status": status,
                    "next_at": next_at,
                    "ambiguous": int(ambiguous),
                    "error": error_class,
                    "updated": _iso(now),
                    "id": claim.outbox_id,
                    "claimed_at": claim.claimed_at,
                },
            )
            return bool(result.rowcount)

        changed = await self._store.transaction(work)
        if not changed:
            logger.debug(
                "Notice queue row settle ignored, the claim was lost",
                extra={"event": "receipt_notice_late_write_ignored", "outbox_id": claim.outbox_id},
            )
        return changed

    async def purge_finished(self, threshold: datetime) -> int:
        """Delete ``sent``, ``skipped`` and ``failed`` rows last updated at or before threshold."""

        async def work(conn: AsyncConnection) -> int:
            result = await conn.execute(
                text(
                    "DELETE FROM notification_outbox WHERE updated_at <= :threshold "
                    "AND status IN ('sent', 'skipped', 'failed')"
                ),
                {"threshold": threshold.isoformat()},
            )
            return int(result.rowcount)

        return await self._store.transaction(work)

    async def _settle_stale(self, conn: AsyncConnection, row: RowMapping, now: int) -> _Event:
        """Apply the ambiguous transition to a dead ``sending`` row; it is never sent now."""
        attempts = int(row["attempts"])
        terminal = bool(row["ambiguous"]) or attempts >= self._max_attempts
        await conn.execute(
            text(
                "UPDATE notification_outbox SET status = :status, ambiguous = 1, "
                "claimed_at = NULL, next_attempt_at = :next_at, last_error_class = :error, "
                "updated_at = :updated WHERE id = :id"
            ),
            {
                "status": STATUS_FAILED if terminal else STATUS_PENDING,
                "next_at": now + self.backoff_seconds(attempts),
                "error": STALE_CLAIM_ERROR,
                "updated": _iso(now),
                "id": row["id"],
            },
        )
        event = "receipt_notice_failed_terminal" if terminal else "receipt_notice_retry_scheduled"
        return (event, int(row["id"]), attempts)

    async def _skip_gone(self, conn: AsyncConnection, outbox_id: int, now: int) -> None:
        await conn.execute(
            text(
                "UPDATE notification_outbox SET status = :status, skip_reason = :reason, "
                "claimed_at = NULL, updated_at = :updated WHERE id = :id"
            ),
            {
                "status": STATUS_SKIPPED,
                "reason": SKIP_TARGET_GONE,
                "updated": _iso(now),
                "id": outbox_id,
            },
        )

    async def _claim(self, conn: AsyncConnection, row: RowMapping, now: int) -> ClaimedNotice:
        attempt = int(row["attempts"]) + 1
        await conn.execute(
            text(
                "UPDATE notification_outbox SET status = :status, claimed_at = :now, "
                "attempts = :attempt, updated_at = :updated WHERE id = :id"
            ),
            {
                "status": STATUS_SENDING,
                "now": now,
                "attempt": attempt,
                "updated": _iso(now),
                "id": row["id"],
            },
        )
        return ClaimedNotice(
            outbox_id=int(row["id"]),
            giver_user_id=int(row["giver_user_id"]),
            attempt=attempt,
            ambiguous=bool(row["ambiguous"]),
            claimed_at=now,
            wish_title=str(row["wish_title"]),
            list_title=str(row["list_title"]),
        )


__all__ = ["CLAIM_BATCH_LIMIT", "STALE_CLAIM_ERROR", "ClaimedNotice", "NoticeStore"]
