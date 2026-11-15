"""Worker of the gift notice path: claims due rows, sends the fixed text, settles the outcome."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable

from wishenka.config import Settings
from wishenka.notices.sender import NoticeSender, SendOutcome, SendResult
from wishenka.notices.store import ClaimedNotice, NoticeStore

logger = logging.getLogger("wishenka.wishlists.notices")

TITLE_LIMIT = 100
MAX_ERROR_BACKOFF_SECONDS = 60.0
_TEXT = (
    "Желание «{wish}» из списка «{wishlist}» отмечено как полученное.\n"
    "Проверьте свою бронь и при необходимости измените или отмените её."
)


def notice_text(wish_title: str, list_title: str) -> str:
    """Fixed template with the two titles cut to ``TITLE_LIMIT``; no quantity, no other giver."""
    return _TEXT.format(wish=wish_title[:TITLE_LIMIT], wishlist=list_title[:TITLE_LIMIT])


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
        self._send_timeout = settings.receipt_notice_request_timeout_seconds + 5
        self._poll = settings.receipt_notice_poll_interval_seconds
        self._clock = clock
        self._window = settings.receipt_notice_summary_window_seconds
        self._window_start = self._window_floor(clock())
        self._counts = {"sent": 0, "retried": 0, "failed_terminal": 0}

    async def run(self, stop: asyncio.Event) -> None:
        """Poll until ``stop`` is set or the task is cancelled (a cancelled send stays ``sending``).

        An idle tick writes no record. A failing tick logs one ERROR per failure streak and
        backs off up to ``MAX_ERROR_BACKOFF_SECONDS``.
        """
        failures = 0
        while not stop.is_set():
            try:
                await self.run_once()
                self.flush_if_due(self._clock())
                failures = 0
            except Exception as error:
                if failures == 0:
                    logger.error(
                        "Notice worker tick failed",
                        extra={
                            "event": "receipt_notice_worker_error",
                            "error_class": type(error).__name__,
                        },
                    )
                failures += 1
            delay = self._poll if failures == 0 else self._error_delay(failures)
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
        self._window_start = start
        if any(counts.values()):
            logger.info(
                "Notice window summary",
                extra={
                    "event": "receipt_notice_window_summary",
                    "window_seconds": self._window,
                    **counts,
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
            result = await self._send(claim)
            await self._settle(claim, result, self._time(now))
            rows += 1
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
        text = notice_text(claim.wish_title, claim.list_title)
        try:
            return await asyncio.wait_for(
                self._sender.send(claim.giver_user_id, text), timeout=self._send_timeout
            )
        except Exception as error:  # a cancellation is not an Exception and passes through
            return SendResult(SendOutcome.AMBIGUOUS, error_class=type(error).__name__)

    async def _settle(self, claim: ClaimedNotice, result: SendResult, now: int) -> None:
        """Record the outcome with the guarded write of the attempt table (design 7)."""
        outcome = result.outcome
        if outcome is SendOutcome.DELIVERED:
            if await self._store.complete(claim, now):
                self._counts["sent"] += 1
            self._debug("receipt_notice_sent", "Notice sent", claim)
            return
        self._debug("receipt_notice_send_failed", "Notice send failed", claim, result)
        give_up = (
            outcome is SendOutcome.REJECTED
            or claim.attempt >= self._max_attempts
            or (outcome is SendOutcome.AMBIGUOUS and claim.ambiguous)
        )
        if give_up:
            if await self._store.fail(
                claim, now, result.error_class, ambiguous=outcome is SendOutcome.AMBIGUOUS
            ):
                self._counts["failed_terminal"] += 1
            self._debug("receipt_notice_failed_terminal", "Notice failed for good", claim, result)
            return
        if await self._store.reschedule(
            claim,
            now,
            error_class=result.error_class,
            retry_after=result.retry_after,
            ambiguous=outcome is SendOutcome.AMBIGUOUS,
        ):
            self._counts["retried"] += 1
        self._debug("receipt_notice_retry_scheduled", "Notice retry scheduled", claim, result)

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
        if result is not None:
            extra["error_class"] = result.error_class
        logger.debug(message, extra=extra)
