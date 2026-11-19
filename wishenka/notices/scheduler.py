"""Schedule idempotent reminders for explicitly dated occasions."""

from __future__ import annotations

import calendar
import logging
from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.config import Settings
from wishenka.notices.models import TransactionalStore

logger = logging.getLogger("wishenka.notices.scheduler")
PAGE_SIZE = 1000


def utc_event_date(value: str) -> date:
    """Interpret stored datetimes as UTC calendar dates; naive values are UTC."""
    moment = datetime.fromisoformat(value)
    return (moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)).date()


class ReminderScheduler:
    """Scan current dates in UTC and persist one intent per recipient and occurrence."""

    def __init__(self, store: TransactionalStore, settings: Settings) -> None:
        self._store = store
        self._leads = getattr(settings, "notice_reminder_lead_days", (7,))

    async def run_once(self, now: int) -> bool:
        """Persist a bounded page and indicate when another page may remain."""
        today = datetime.fromtimestamp(now, UTC).date()
        leads = tuple(sorted({int(value) for value in self._leads if int(value) > 0}))
        if not leads:
            return False

        async def work(conn: AsyncConnection) -> tuple[int, int, int]:
            inserted = 0
            list_cursor = (
                await conn.scalar(
                    text("SELECT last_id FROM notice_scheduler_cursors WHERE source='lists'")
                )
                or 0
            )
            lists = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,owner_id,event_date FROM wl_lists WHERE status='active' "
                            "AND event_date IS NOT NULL AND id>:cursor ORDER BY id LIMIT :limit"
                        ),
                        {"cursor": list_cursor, "limit": PAGE_SIZE},
                    )
                )
                .mappings()
                .all()
            )
            for wl in lists:
                try:
                    event = utc_event_date(str(wl["event_date"]))
                except ValueError:
                    continue
                remaining = (event - today).days
                if not 0 <= remaining <= leads[-1]:
                    continue
                recipients = (
                    (
                        await conn.execute(
                            text(
                                "SELECT owner_id AS user_id FROM wl_lists WHERE id=:id UNION "
                                "SELECT user_id FROM wl_members WHERE wishlist_id=:id UNION "
                                "SELECT user_id FROM wl_favorites WHERE wishlist_id=:id"
                            ),
                            {"id": wl["id"]},
                        )
                    )
                    .scalars()
                    .all()
                )
                for lead in leads:
                    if 0 <= remaining <= lead:
                        for user in recipients:
                            key = f"list:{wl['id']}:{event}:{lead}:{user}"
                            result = await conn.execute(
                                text(
                                    "INSERT OR IGNORE INTO reminder_outbox "
                                    "(occurrence_key,kind,user_id,list_id,event_dat"
                                    "e,next_attempt_at) "
                                    "VALUES (:key,'list',:user,:list,:date,:now)"
                                ),
                                {
                                    "key": key,
                                    "user": user,
                                    "list": wl["id"],
                                    "date": event.isoformat(),
                                    "now": now,
                                },
                            )
                            inserted += int(bool(result.rowcount))
            await conn.execute(
                text(
                    "INSERT INTO notice_scheduler_cursors VALUES ('lists',:last) "
                    "ON CONFLICT(source) DO UPDATE SET last_id=:last"
                ),
                {"last": int(lists[-1]["id"]) if len(lists) == PAGE_SIZE else 0},
            )
            birthday_cursor = (
                await conn.scalar(
                    text("SELECT last_id FROM notice_scheduler_cursors WHERE source='birthdays'")
                )
                or 0
            )
            birthdays = (
                (
                    await conn.execute(
                        text(
                            "SELECT b.id,b.owner_id,b.month,b.day,b.revision,u.telegram_id "
                            "FROM birthday_entries b JOIN users u ON u.id=b.owner_id "
                            "WHERE b.deleted=0 AND b.id>:cursor ORDER BY b.id LIMIT :limit"
                        ),
                        {"cursor": birthday_cursor, "limit": PAGE_SIZE},
                    )
                )
                .mappings()
                .all()
            )
            for birthday in birthdays:
                for year in (today.year, today.year + 1):
                    month, day = int(birthday["month"]), int(birthday["day"])
                    if month == 2 and day == 29 and not calendar.isleap(year):
                        day = 28
                    event = date(year, month, day)
                    remaining = (event - today).days
                    for lead in leads:
                        if 0 <= remaining <= lead:
                            key = (
                                f"birthday:{birthday['id']}:{birthday['revision']}:"
                                f"{year}:{lead}:{birthday['owner_id']}"
                            )
                            result = await conn.execute(
                                text(
                                    "INSERT OR IGNORE INTO reminder_outbox "
                                    "(occurrence_key,kind,user_id,birthday_id,revision,event_date,"
                                    "next_attempt_at) VALUES "
                                    "(:key,'birthday',:user,:birthday,:revision,"
                                    ":date,:now)"
                                ),
                                {
                                    "key": key,
                                    "user": birthday["telegram_id"],
                                    "birthday": birthday["id"],
                                    "revision": birthday["revision"],
                                    "date": event.isoformat(),
                                    "now": now,
                                },
                            )
                            inserted += int(bool(result.rowcount))

            await conn.execute(
                text(
                    "INSERT INTO notice_scheduler_cursors VALUES ('birthdays',:last) "
                    "ON CONFLICT(source) DO UPDATE SET last_id=:last"
                ),
                {"last": int(birthdays[-1]["id"]) if len(birthdays) == PAGE_SIZE else 0},
            )
            return len(lists), len(birthdays), inserted

        list_count, birthday_count, inserted = await self._store.transaction(work)
        if list_count or birthday_count or inserted:
            logger.debug(
                "Reminder scan completed",
                extra={
                    "event": "reminder_scan_completed",
                    "lists_scanned": list_count,
                    "birthdays_scanned": birthday_count,
                    "intents_created": inserted,
                },
            )
        return list_count == PAGE_SIZE or birthday_count == PAGE_SIZE
