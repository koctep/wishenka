"""Value objects of the notice path shared by the domain, the store and the worker."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, TypeVar

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

    from wishenka.wishlists.models import ReceiptRecord

T = TypeVar("T")


class TransactionalStore(Protocol):
    """Store providing an atomic ``BEGIN IMMEDIATE`` transaction boundary."""

    async def transaction(self, work: Callable[[AsyncConnection], Awaitable[T]]) -> T:
        """Run ``work`` inside one ``BEGIN IMMEDIATE`` transaction."""
        ...


EVENT_GIFT_RECEIVED = "gift_received"

STATUS_PENDING = "pending"
STATUS_SENDING = "sending"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

SKIP_SETTING_LIST = "setting_list"
SKIP_SETTING_USER = "setting_user"
SKIP_TARGET_GONE = "target_gone"


@dataclass(frozen=True)
class NoticeDraft:
    """A notice decided inside the receipt transaction, flushed by the store.

    ``status`` is ``pending`` when the giver wants it, ``skipped`` (with ``skip_reason``) when a
    setting turned it off. The draft holds no quantity, title or text.
    """

    giver_user_id: int
    receipt: ReceiptRecord
    status: str = STATUS_PENDING
    skip_reason: str | None = None


@dataclass
class NoticeSettings:
    """Notice switches loaded in the receipt transaction; absent keys mean enabled.

    ``user`` is keyed by ``(user_id, event_type)``, ``list`` by
    ``(user_id, wishlist_id, event_type)``.
    """

    user: dict[tuple[int, str], bool] = field(default_factory=dict)
    list: dict[tuple[int, int, str], bool] = field(default_factory=dict)


@dataclass(frozen=True)
class FlushedNotice:
    """A notice row the store wrote, reported for the after-commit DEBUG logs."""

    outbox_id: int
    status: str
    gate: str | None = None
