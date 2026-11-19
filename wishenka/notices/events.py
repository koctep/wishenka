"""Transaction-scoped, idempotent production of safe shared-list notifications."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

SAFE_SHARED_EVENTS = frozenset(
    {
        "item_created",
        "item_updated",
        "item_archived",
        "item_restored",
        "list_updated",
        "list_archived",
        "list_restored",
        "membership_changed",
        "reservation_confirmation",
        "receipt_reverted",
        "receipt_increased",
    }
)


@dataclass(frozen=True)
class SharedEvent:
    """Minimal event reference and audience captured at mutation time."""

    kind: str
    wishlist_id: int
    item_id: int | None
    event_id: str
    recipients: tuple[int, ...]
    member_recipients: frozenset[int] = frozenset()


class EventProducer:
    """Persist candidate intents in the caller's existing domain transaction."""

    async def record(self, conn: AsyncConnection, event: SharedEvent, now: int) -> int:
        """Create one stable, content-free intent per eligible verified destination."""
        if event.kind not in SAFE_SHARED_EVENTS:
            raise ValueError("Unsupported shared notification event")
        users_exist = await conn.scalar(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'")
        )
        if not users_exist:
            return 0
        queued = 0
        for user in event.recipients:
            if event.kind == "reservation_confirmation":
                # Confirmations of the actor's action require explicit opt-in.
                enabled = await conn.scalar(
                    text(
                        "SELECT COALESCE((SELECT enabled FROM wl_list_notification_settings "
                        "WHERE user_id=:user AND wishlist_id=:list AND "
                        "event_type='reservation_changes'), "
                        "(SELECT enabled FROM user_notification_settings WHERE user_id=:user "
                        "AND event_type='reservation_changes'),0)"
                    ),
                    {"user": user, "list": event.wishlist_id},
                )
                if enabled != 1:
                    continue
            deliverable = await conn.scalar(
                text(
                    "SELECT 1 FROM users u JOIN bot_destinations d ON d.user_id=u.id "
                    "WHERE u.telegram_id=:user AND d.active=1"
                ),
                {"user": user},
            )
            if not deliverable:
                continue
            result = await conn.execute(
                text(
                    "INSERT OR IGNORE INTO reminder_outbox "
                    "(occurrence_key,kind,user_id,list_id,item_id,event_date,next_attempt_at,"
                    "updated_at,requires_membership) "
                    "VALUES (:key,:kind,:user,:list,:item,'',:now,:now,:member)"
                ),
                {
                    "key": f"{event.event_id}:{user}",
                    "kind": event.kind,
                    "user": user,
                    "list": event.wishlist_id,
                    "item": event.item_id,
                    "now": now,
                    "member": int(user in event.member_recipients),
                },
            )
            queued += int(result.rowcount or 0)
        return queued
