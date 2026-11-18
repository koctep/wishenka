"""Background cleanup runner for expired invite tokens and purged wishlists."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from wishenka.config import Settings
from wishenka.notices.store import NoticeStore
from wishenka.wishlists.store import WishlistStore

logger = logging.getLogger(__name__)


@dataclass
class CleanupStats:
    """Statistics captured during a single execution of run_cleanup_cycle."""

    expired_tokens_cleaned: int = 0
    wishlists_purged: int = 0
    idempotency_records_cleaned: int = 0
    session_revocations_cleaned: int = 0
    birthdays_purged: int = 0
    bot_destinations_purged: int = 0
    receipt_keys_purged: int = 0
    duration_ms: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime = field(default_factory=lambda: datetime.now(UTC))


async def _purge_notices(
    notice_store: NoticeStore, settings: Settings, now: datetime
) -> tuple[int, int, int]:
    """Delete finished notice and retention rows; a failure is a WARNING, never a cycle error."""
    threshold = now - timedelta(days=settings.receipt_notice_retention_days)
    reminder_threshold = now - timedelta(days=settings.reminder_retention_days)
    try:
        rows = await notice_store.purge_finished(
            threshold,
            now=now,
            reminder_threshold=reminder_threshold,
        )
        retention_counts = await notice_store.purge_retention_records(
            birthday_threshold=now - timedelta(days=settings.birthday_retention_days),
            destination_threshold=now - timedelta(days=settings.bot_destination_retention_days),
            receipt_key_threshold=now - timedelta(days=settings.receipt_dedup_retention_days),
        )
    except Exception as err:
        logger.warning(
            "Purge of finished notice rows failed",
            extra={"event": "receipt_notice_purge_failed", "error_class": type(err).__name__},
        )
        return 0, 0, 0
    if rows > 0:
        logger.info(
            "Finished notice rows purged",
            extra={"event": "receipt_notice_rows_purged", "rows": rows},
        )
    return retention_counts


async def run_cleanup_cycle(
    store: WishlistStore,
    settings: Settings,
    now: datetime | None = None,
    notice_store: NoticeStore | None = None,
) -> CleanupStats:
    """Perform background cleanup of expired invite tokens and deleted wishlists.

    Catches operational exceptions gracefully, records structured error logs,
    and returns a summary statistics object without raising.
    """
    effective_now = now or datetime.now(UTC)
    started_at = effective_now
    start_perf = time.perf_counter()

    try:
        expired_count = await store.cleanup_expired_tokens(effective_now)
        retention_threshold = effective_now - timedelta(days=settings.wishlist_retention_days)
        purged_count = await store.purge_archived_wishlists(retention_threshold)
        idempotency_cleaned = await store.cleanup_expired_idempotency_records(effective_now)
        revocations_cleaned = await store.cleanup_expired_session_revocations(effective_now)
        birthdays_purged = 0
        bot_destinations_purged = 0
        receipt_keys_purged = 0
        if notice_store is not None:
            birthdays_purged, bot_destinations_purged, receipt_keys_purged = await _purge_notices(
                notice_store, settings, effective_now
            )

        duration_sec = time.perf_counter() - start_perf
        duration_ms = duration_sec * 1000.0
        finished_at = started_at + timedelta(seconds=duration_sec)

        logger.info(
            "Background cleanup cycle completed successfully: "
            "cleaned %s tokens, purged %s wishlists, cleaned %s idempotency records, "
            "cleaned %s session revocations in %.2fms",
            expired_count,
            purged_count,
            idempotency_cleaned,
            revocations_cleaned,
            duration_ms,
            extra={
                "event": "background_cleanup_completed",
                "expired_tokens_cleaned": expired_count,
                "wishlists_purged": purged_count,
                "idempotency_records_cleaned": idempotency_cleaned,
                "session_revocations_cleaned": revocations_cleaned,
                "birthdays_purged": birthdays_purged,
                "bot_destinations_purged": bot_destinations_purged,
                "receipt_keys_purged": receipt_keys_purged,
                "duration_ms": duration_ms,
            },
        )
        return CleanupStats(
            expired_tokens_cleaned=expired_count,
            wishlists_purged=purged_count,
            idempotency_records_cleaned=idempotency_cleaned,
            session_revocations_cleaned=revocations_cleaned,
            birthdays_purged=birthdays_purged,
            bot_destinations_purged=bot_destinations_purged,
            receipt_keys_purged=receipt_keys_purged,
            duration_ms=duration_ms,
            started_at=started_at,
            finished_at=finished_at,
        )
    except Exception as err:
        duration_sec = time.perf_counter() - start_perf
        duration_ms = duration_sec * 1000.0
        finished_at = started_at + timedelta(seconds=duration_sec)

        logger.error(
            "background_cleanup_failed: %s",
            err,
            exc_info=True,
            extra={
                "event": "background_cleanup_failed",
                "error": str(err),
                "duration_ms": duration_ms,
            },
        )
        return CleanupStats(
            expired_tokens_cleaned=0,
            wishlists_purged=0,
            duration_ms=duration_ms,
            started_at=started_at,
            finished_at=finished_at,
        )


async def background_cleanup_worker(
    store: WishlistStore,
    settings: Settings,
    stop_event: asyncio.Event | None = None,
    notice_store: NoticeStore | None = None,
) -> None:
    """Long-running background task executing cleanup cycles on schedule."""
    logger.info(
        "Background cleanup worker started (interval=%ds)",
        settings.background_cleanup_interval_seconds,
        extra={
            "event": "background_worker_started",
            "interval_seconds": settings.background_cleanup_interval_seconds,
        },
    )
    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                break
            try:
                if stop_event is not None:
                    try:
                        await asyncio.wait_for(
                            stop_event.wait(),
                            timeout=float(settings.background_cleanup_interval_seconds),
                        )
                        break
                    except TimeoutError:
                        pass
                else:
                    await asyncio.sleep(settings.background_cleanup_interval_seconds)
                await run_cleanup_cycle(store, settings, notice_store=notice_store)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unexpected error in background cleanup loop")
    finally:
        logger.info(
            "Background cleanup worker stopped",
            extra={"event": "background_worker_stopped"},
        )


__all__ = [
    "CleanupStats",
    "background_cleanup_worker",
    "run_cleanup_cycle",
]
