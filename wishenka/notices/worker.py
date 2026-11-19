"""Worker of the gift notice path: claims due rows, sends the fixed text, settles the outcome."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from collections.abc import Callable

from wishenka.config import Settings
from wishenka.i18n import DEFAULT_LOCALE, resolve_telegram_locale, t
from wishenka.notices.fence import (
    begin_attempt,
    claim_key,
    defer_claim,
    delivery_lock,
    finish_attempt,
)
from wishenka.notices.scheduler import ReminderScheduler
from wishenka.notices.sender import NoticeSender, SendOutcome, SendResult
from wishenka.notices.store import ClaimedNotice, NoticeStore

logger = logging.getLogger("wishenka.wishlists.notices")

TITLE_LIMIT = 100
MAX_ERROR_BACKOFF_SECONDS = 60.0


def notice_text(wish_title: str, list_title: str, locale: str = DEFAULT_LOCALE) -> str:
    """Localized notice template with titles cut to ``TITLE_LIMIT``; no quantity or other giver."""
    resolved = resolve_telegram_locale(locale)
    return t(
        "notices.gift_received",
        resolved,
        wish=wish_title[:TITLE_LIMIT],
        wishlist=list_title[:TITLE_LIMIT],
    )


class NoticeWorker:
    """Sends queued gift notices; the attempt rules live in ``NoticeStore`` and ``settings``."""

    def __init__(
        self,
        store: NoticeStore,
        sender: NoticeSender,
        settings: Settings,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Keep the queue store, the sender, the limits from ``settings`` and the wall clock."""
        self._store = store
        self._sender = sender
        self._max_attempts = settings.receipt_notice_max_attempts
        self._scheduler = (
            ReminderScheduler(store, settings) if isinstance(store, NoticeStore) else None
        )
        self._next_schedule = 0.0
        self._send_timeout = settings.receipt_notice_request_timeout_seconds + 5
        self._poll = settings.receipt_notice_poll_interval_seconds
        self._clock = clock
        self._window = settings.receipt_notice_summary_window_seconds
        self._window_start = self._window_floor(clock())
        self._counts = {"sent": 0, "retried": 0, "failed_terminal": 0, "uncertain": 0}
        self._reminder_counts = dict.fromkeys(
            ("sent", "retried", "failed_terminal", "uncertain", "skipped"), 0
        )

    async def run(self, stop: asyncio.Event) -> None:
        """Poll until ``stop`` is set or the task is cancelled (a cancelled send stays ``sending``).

        An idle tick writes no record. Queue and scheduler failures back off independently.
        """
        failures = 0
        scheduler_failures = 0
        while not stop.is_set():
            if self._scheduler is not None and self._clock() >= self._next_schedule:
                try:
                    more_pages = await self._scheduler.run_once(int(self._clock()))
                except Exception as error:
                    if scheduler_failures == 0:
                        logger.error(
                            "Reminder scheduler failed: error_class=%s",
                            type(error).__name__,
                            extra={
                                "event": "reminder_scheduler_error",
                                "error_class": type(error).__name__,
                            },
                        )
                    scheduler_failures += 1
                    self._next_schedule = self._clock() + self._error_delay(scheduler_failures)
                else:
                    scheduler_failures = 0
                    self._next_schedule = self._clock() if more_pages else self._clock() + 3600
            try:
                await self.run_once()
                self.flush_if_due(self._clock())
                failures = 0
            except Exception as error:
                if failures == 0:
                    logger.error(
                        "Notice worker tick failed: error_class=%s",
                        type(error).__name__,
                        extra={
                            "event": "receipt_notice_worker_error",
                            "error_class": type(error).__name__,
                        },
                    )
                failures += 1
            delay = self._poll if failures == 0 else self._error_delay(failures)
            if failures == 0 and self._scheduler is not None:
                delay = min(delay, max(0.05, self._next_schedule - self._clock()))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=delay)

    def _error_delay(self, failures: int) -> float:
        """Poll interval doubled per consecutive failure, capped at one minute."""
        return float(min(self._poll * 2 ** min(failures, 16), MAX_ERROR_BACKOFF_SECONDS))

    def _window_floor(self, now: float) -> int:
        return int(now // self._window) * self._window

    def flush_if_due(self, now: float) -> None:
        """Emit the aggregate of a closed window if it processed rows (fixed wall-clock grid)."""
        start = self._window_floor(now)
        if start <= self._window_start:
            return
        counts, self._counts = self._counts, dict.fromkeys(self._counts, 0)
        reminder_counts, self._reminder_counts = (
            self._reminder_counts,
            dict.fromkeys(self._reminder_counts, 0),
        )
        self._window_start = start
        if any(counts.values()):
            logger.info(
                "Notice window summary: window_seconds=%s sent=%s retried=%s "
                "failed_terminal=%s uncertain=%s",
                self._window,
                counts["sent"],
                counts["retried"],
                counts["failed_terminal"],
                counts["uncertain"],
                extra={
                    "event": "receipt_notice_window_summary",
                    "window_seconds": self._window,
                    **counts,
                },
            )
        if any(reminder_counts.values()):
            logger.info(
                "Service delivery window summary: window_seconds=%s sent=%s retried=%s "
                "failed_terminal=%s uncertain=%s skipped=%s",
                self._window,
                reminder_counts["sent"],
                reminder_counts["retried"],
                reminder_counts["failed_terminal"],
                reminder_counts["uncertain"],
                reminder_counts["skipped"],
                extra={
                    "event": "service_delivery_window_summary",
                    "window_seconds": self._window,
                    **reminder_counts,
                },
            )

    async def run_once(self, now: int | None = None) -> int:
        """Drain every row that is due; return how many rows were sent or settled.

        Each claim and each settle reads the clock afresh, so ``claimed_at`` and the retry times
        follow the real time of a long drain (design 7, lease rule). ``now`` is a test override:
        when given, it is the time of every claim and settle of this call.
        """
        rows = 0
        while (claim := await self._store.claim_next(self._time(now))) is not None:
            store = self._store.transactional_store
            key = await claim_key(store, "gift", claim.outbox_id, claim.claim_token)
            if key is None:
                continue
            attempt_started = False
            try:
                async with delivery_lock(store.database_url, *key):
                    refreshed = await self._store.refresh_claim(claim)
                    if refreshed is None:
                        if await self._store.skip_claim(claim, self._time(now)):
                            self._debug(
                                "receipt_notice_skipped_ineligible",
                                "Notice queue row skipped as ineligible",
                                claim,
                            )
                        rows += 1
                        continue
                    if not await begin_attempt(
                        store, key, "gift", claim.outbox_id, claim.claim_token
                    ):
                        await defer_claim(
                            store, "gift", claim.outbox_id, claim.claim_token, self._time(now)
                        )
                        logger.debug(
                            "Receipt notice claim deferred: active delivery fence",
                            extra={
                                "event": "receipt_notice_deferred",
                                "outbox_id": claim.outbox_id,
                                "reason": "fence_active",
                            },
                        )
                        break
                    attempt_started = True
                    result = await self._send(refreshed)
                    settled = await self._settle(refreshed, result, self._time(now))
                    await finish_attempt(
                        store,
                        key,
                        claim.claim_token,
                        settled and result.outcome is not SendOutcome.AMBIGUOUS,
                    )
                    rows += 1
            except OSError:
                if not attempt_started:
                    await defer_claim(
                        store, "gift", claim.outbox_id, claim.claim_token, self._time(now)
                    )
                    logger.debug(
                        "Receipt notice claim deferred: delivery lock busy",
                        extra={
                            "event": "receipt_notice_deferred",
                            "outbox_id": claim.outbox_id,
                            "reason": "lock_busy",
                        },
                    )
                break
        while (reminder := await self._store.claim_reminder(self._time(now))) is not None:
            store = self._store.transactional_store
            key = await claim_key(store, "reminder", reminder.ident, reminder.claim_token)
            attempt_started = False
            try:
                async with contextlib.AsyncExitStack() as locks:
                    if key is not None:
                        await locks.enter_async_context(delivery_lock(store.database_url, *key))
                    refreshed_reminder = await self._store.refresh_reminder(
                        reminder, self._time(now)
                    )
                    if refreshed_reminder is None:
                        if await self._store.settle_reminder(reminder, "skipped", self._time(now)):
                            self._reminder_counts["skipped"] += 1
                            logger.debug(
                                "Service notice skipped: reason=refresh_ineligible",
                                extra={
                                    "event": "service_notice_skipped",
                                    "outbox_id": reminder.ident,
                                    "reason": "refresh_ineligible",
                                },
                            )
                        rows += 1
                        continue
                    reminder = refreshed_reminder
                    if key is not None and not await begin_attempt(
                        store, key, "reminder", reminder.ident, reminder.claim_token
                    ):
                        await defer_claim(
                            store, "reminder", reminder.ident, reminder.claim_token, self._time(now)
                        )
                        logger.debug(
                            "Service notice claim deferred: active delivery fence",
                            extra={
                                "event": "service_notice_deferred",
                                "outbox_id": reminder.ident,
                                "reason": "fence_active",
                            },
                        )
                        break
                    attempt_started = True
                    try:
                        result = await asyncio.wait_for(
                            self._sender.send(reminder.chat_id, reminder.body),
                            timeout=self._send_timeout,
                        )
                    except Exception:
                        result = SendResult(SendOutcome.AMBIGUOUS)
                    if result.outcome is SendOutcome.DELIVERED:
                        status = "sent"
                    elif result.outcome is SendOutcome.AMBIGUOUS:
                        status = "uncertain"
                    elif (
                        result.outcome is SendOutcome.REJECTED
                        or reminder.attempt >= self._max_attempts
                    ):
                        status = "failed"
                    else:
                        status = "pending"
                    delay = (
                        max(
                            self._store.backoff_seconds(reminder.attempt),
                            math.ceil(result.retry_after or 0),
                        )
                        if status == "pending"
                        else 0
                    )
                    settled_at = self._time(now)
                    settled = await self._store.settle_reminder(
                        reminder,
                        status,
                        settled_at + delay,
                        result.error_class,
                        settled_at + math.ceil(result.retry_after) if result.retry_after else None,
                        updated_at=settled_at,
                    )
                    if key is not None:
                        await finish_attempt(
                            store, key, reminder.claim_token, settled and status != "uncertain"
                        )
                    if settled:
                        counter = {"pending": "retried", "failed": "failed_terminal"}.get(
                            status, status
                        )
                        self._reminder_counts[counter] += 1
                    rows += 1
            except OSError:
                if not attempt_started:
                    await defer_claim(
                        store, "reminder", reminder.ident, reminder.claim_token, self._time(now)
                    )
                    logger.debug(
                        "Service notice claim deferred: delivery lock busy",
                        extra={
                            "event": "service_notice_deferred",
                            "outbox_id": reminder.ident,
                            "reason": "lock_busy",
                        },
                    )
                break
        if rows:
            logger.debug(
                "Notice batch processed",
                extra={"event": "receipt_notice_batch_processed", "rows": rows},
            )
        return rows

    def _time(self, override: int | None) -> int:
        """The override when given, otherwise a fresh read of the clock in whole seconds."""
        return override if override is not None else int(self._clock())

    async def _send(self, claim: ClaimedNotice) -> SendResult:
        """Send one notice; a timeout or any unexpected error is ``AMBIGUOUS``."""
        text = notice_text(claim.wish_title, claim.list_title, claim.language)
        try:
            return await asyncio.wait_for(
                self._sender.send(claim.giver_user_id, text), timeout=self._send_timeout
            )
        except Exception as error:  # a cancellation is not an Exception and passes through
            return SendResult(SendOutcome.AMBIGUOUS, error_class=type(error).__name__)

    async def _settle(self, claim: ClaimedNotice, result: SendResult, now: int) -> bool:
        """Record the outcome with the guarded write of the attempt table (design 7)."""
        outcome = result.outcome
        if outcome is SendOutcome.DELIVERED:
            settled = await self._store.complete(claim, now)
            if settled:
                self._counts["sent"] += 1
            self._debug("receipt_notice_sent", "Notice sent", claim)
            return settled
        if outcome is SendOutcome.AMBIGUOUS:
            self._debug("receipt_notice_send_failed", "Notice send failed", claim, result)
            settled = await self._store.uncertain(claim, now, result.error_class)
            if settled:
                self._counts["uncertain"] += 1
            self._debug("receipt_notice_uncertain", "Notice delivery uncertain", claim, result)
            return settled
        self._debug("receipt_notice_send_failed", "Notice send failed", claim, result)
        give_up = outcome is SendOutcome.REJECTED or claim.attempt >= self._max_attempts
        if give_up:
            settled = await self._store.fail(
                claim, now, result.error_class, retry_after=result.retry_after
            )
            if settled:
                self._counts["failed_terminal"] += 1
            self._debug("receipt_notice_failed_terminal", "Notice failed for good", claim, result)
            return settled
        settled = await self._store.reschedule(
            claim,
            now,
            error_class=result.error_class,
            retry_after=result.retry_after,
        )
        if settled:
            self._counts["retried"] += 1
        self._debug("receipt_notice_retry_scheduled", "Notice retry scheduled", claim, result)
        return settled

    def _debug(
        self,
        event: str,
        message: str,
        claim: ClaimedNotice,
        result: SendResult | None = None,
    ) -> None:
        extra: dict[str, object] = {
            "event": event,
            "outbox_id": claim.outbox_id,
            "attempt": claim.attempt,
        }
        if event == "receipt_notice_retry_scheduled":
            extra["max_attempts"] = self._max_attempts
        if result is not None:
            extra["error_class"] = result.error_class
        logger.debug(message, extra=extra)
