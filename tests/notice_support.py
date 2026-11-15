"""Fake notice sender for the WISHENKA-23 tests. It never contacts Telegram."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any

from tests.receipt_support import new_symbol


def send_result(
    outcome: str, *, retry_after: float | None = None, error_class: str | None = None
) -> Any:
    """Build a ``SendResult`` of the intended new sender module."""
    outcome_enum = new_symbol("wishenka.notices.sender", "SendOutcome")
    result_class = new_symbol("wishenka.notices.sender", "SendResult")
    return result_class(
        outcome=outcome_enum(outcome),
        retry_after=retry_after,
        error_class=error_class,
    )


class FakeNoticeSender:
    """Records every call and replays scripted results (``delivered`` when the script is empty).

    ``block_first`` makes the first call wait on an event (bounded), so a test can keep one
    send in flight while another worker acts.
    """

    def __init__(
        self,
        script: list[Any] | None = None,
        *,
        block_first: asyncio.Event | None = None,
        sleep: float | None = None,
    ) -> None:
        self.calls: list[tuple[int, str]] = []
        self.closed = False
        self._script: deque[Any] = deque(script or [])
        self._block_first = block_first
        self._sleep = sleep

    async def send(self, chat_id: int, text: str) -> Any:
        """Record the call, optionally wait, then return or raise the next scripted value."""
        self.calls.append((chat_id, text))
        if self._block_first is not None and len(self.calls) == 1:
            await asyncio.wait_for(self._block_first.wait(), timeout=20)
        if self._sleep is not None:
            await asyncio.sleep(self._sleep)
        item = self._script.popleft() if self._script else send_result("delivered")
        if isinstance(item, BaseException):
            raise item
        return item

    async def close(self) -> None:
        """Mark the sender closed."""
        self.closed = True
