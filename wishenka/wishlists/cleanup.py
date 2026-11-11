"""Background cleanup runner for expired invite tokens and purged wishlists."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from wishenka.config import Settings
from wishenka.wishlists.store import WishlistStore

logger = logging.getLogger(__name__)


@dataclass
class CleanupStats:
    """Statistics captured during a single execution of run_cleanup_cycle."""

    expired_tokens_cleaned: int = 0
    wishlists_purged: int = 0
    duration_ms: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime = field(default_factory=lambda: datetime.now(UTC))


async def run_cleanup_cycle(
    store: WishlistStore,
    settings: Settings,
    now: datetime | None = None,
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

        duration_sec = time.perf_counter() - start_perf
        duration_ms = duration_sec * 1000.0
        finished_at = started_at + timedelta(seconds=duration_sec)

        logger.info(
            "Background cleanup cycle completed successfully: "
            "cleaned %s tokens, purged %s wishlists in %.2fms",
            expired_count,
            purged_count,
            duration_ms,
            extra={
                "event": "background_cleanup_completed",
                "expired_tokens_cleaned": expired_count,
                "wishlists_purged": purged_count,
                "duration_ms": duration_ms,
            },
        )
        return CleanupStats(
            expired_tokens_cleaned=expired_count,
            wishlists_purged=purged_count,
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
                await run_cleanup_cycle(store, settings)
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
