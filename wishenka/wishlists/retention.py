"""One restorability rule for a deleted wishlist.

Call sites must look up ``is_retention_expired`` on this module at call time so
one patch covers the route and both backends.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from math import ceil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wishenka.config import Settings

DEFAULT_WISHLIST_RETENTION_DAYS: int = 30


class OwnerDeleteKind(StrEnum):
    """Owner-delete classification. The route maps each kind to the existing HTTP result."""

    MISSING = "missing"
    FORBIDDEN = "forbidden"
    EXPIRED = "expired"
    REPEAT = "repeat"
    APPLY = "apply"


@dataclass(frozen=True)
class OwnerDeleteDecision:
    """Silent classification of an owner delete. ``retention_days`` is the int the route passed."""

    kind: OwnerDeleteKind
    retention_days: int


def wishlist_retention_days(settings: Settings) -> int:
    """Configured period. The usual length is Settings' field default."""
    return settings.wishlist_retention_days


def deletion_moment(updated_at: datetime) -> datetime:
    """UTC deletion moment. Naive ``updated_at`` is UTC, as the route did before this module."""
    if updated_at.tzinfo is None:
        return updated_at.replace(tzinfo=UTC)
    return updated_at


def purge_threshold(now: datetime, retention_days: int) -> datetime:
    """Cutoff purge already uses: ``now - timedelta(days=retention_days)``."""
    return now - timedelta(days=retention_days)


def is_retention_expired(updated_at: datetime, retention_days: int, now: datetime) -> bool:
    """True when the deletion moment is on or before the purge cutoff."""
    return deletion_moment(updated_at) <= purge_threshold(now, retention_days)


def days_remaining(updated_at: datetime, retention_days: int, now: datetime) -> int:
    """Days left for a list still inside the window, at least 1."""
    deleted_at = deletion_moment(updated_at)
    expires_at = deleted_at + timedelta(days=retention_days)
    remaining_seconds = (expires_at - now).total_seconds()
    return max(1, ceil(remaining_seconds / 86400))
