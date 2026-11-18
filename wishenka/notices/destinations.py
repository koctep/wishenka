"""Shared lifecycle helpers for ``bot_destinations`` rows."""

from __future__ import annotations

import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def upsert_bot_destination(
    conn: AsyncConnection,
    user_id: int,
    chat_id: int,
    now: int | None = None,
) -> None:
    """Register or reactivate a bot delivery destination and refresh ``updated_at``."""
    effective_now = int(time.time()) if now is None else now
    await conn.execute(
        text(
            "INSERT INTO bot_destinations(user_id, chat_id, active, updated_at) "
            "VALUES (:id, :chat, 1, :now) "
            "ON CONFLICT(user_id) DO UPDATE SET chat_id=:chat, active=1, updated_at=:now"
        ),
        {"id": user_id, "chat": chat_id, "now": effective_now},
    )


async def deactivate_bot_destination(
    conn: AsyncConnection,
    chat_id: int,
    now: int | None = None,
) -> None:
    """Mark a bot delivery destination inactive and record ``updated_at``."""
    effective_now = int(time.time()) if now is None else now
    await conn.execute(
        text("UPDATE bot_destinations SET active=0, updated_at=:now WHERE chat_id=:chat"),
        {"chat": chat_id, "now": effective_now},
    )
