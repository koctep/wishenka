"""Shared private-bot user resolution and destination activation helper."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from wishenka.bot.i18n import _private_bot_user
from wishenka.notices.destinations import upsert_bot_destination
from wishenka.users.models import UserRecord

if TYPE_CHECKING:
    from wishenka.users.store import UserStore


def _resolve_effective_now(dependencies: Any, now: int | None) -> int | None:
    """Normalize explicit ``now`` or ``dependencies.clock()`` to Unix epoch seconds."""
    if now is not None:
        return int(now)
    clock = getattr(dependencies, "clock", None)
    if not callable(clock):
        return None
    value = clock()
    return int(value.timestamp()) if isinstance(value, datetime) else int(value)


async def ensure_private_bot_user(
    dependencies: Any,
    user: Any,
    chat_id: int,
    *,
    user_record: UserRecord | None = None,
    now: int | None = None,
) -> UserRecord | None:
    """Resolve or create a private-chat bot user and activate their bot destination."""
    users: UserStore | None = getattr(dependencies, "user_store", None)
    if user is None or users is None or chat_id != user.id:
        return None

    record = user_record
    if record is None:
        record = await users.get_by_telegram_id(user.id)
    if record is None:
        token = _private_bot_user.set(True)
        try:
            record = await users.upsert_from_bot(user)
        finally:
            _private_bot_user.reset(token)

    effective_now = _resolve_effective_now(dependencies, now)
    async with users.engine.begin() as conn:
        await upsert_bot_destination(conn, int(record.id), chat_id, effective_now)
    return record
