"""Persistent rate reservations shared across worker processes."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def reserve_permit(
    conn: AsyncConnection, chat: int, now: int, global_limit: int, chat_interval: int
) -> bool:
    """Reserve a global and per-chat slot in the caller's immediate transaction."""
    await conn.execute(
        text("DELETE FROM notice_rate_slots WHERE bucket!='global' AND second<:threshold"),
        {"threshold": now - max(chat_interval, 3600)},
    )
    user_bucket = f"chat:{chat}"
    blocked = await conn.scalar(text("SELECT second FROM notice_rate_slots WHERE bucket='blocked'"))
    if blocked is not None and now < blocked:
        return False
    global_slot = (
        await conn.execute(text("SELECT second,count FROM notice_rate_slots WHERE bucket='global'"))
    ).first()
    chat_slot = (
        await conn.execute(
            text("SELECT second,count FROM notice_rate_slots WHERE bucket=:bucket"),
            {"bucket": user_bucket},
        )
    ).first()
    if global_slot and (
        global_slot[0] > now or (global_slot[0] == now and global_slot[1] >= global_limit)
    ):
        return False
    if chat_slot and chat_slot[0] + chat_interval > now:
        return False
    await conn.execute(
        text(
            "INSERT INTO notice_rate_slots(bucket,second,count) VALUES ('global',:now,1) "
            "ON CONFLICT(bucket) DO UPDATE SET count=CASE WHEN second=:now "
            "THEN count+1 ELSE 1 END, "
            "second=:now"
        ),
        {"now": now},
    )
    await conn.execute(
        text(
            "INSERT INTO notice_rate_slots(bucket,second,count) VALUES (:bucket,:now,1) "
            "ON CONFLICT(bucket) DO UPDATE SET second=:now,count=1"
        ),
        {"bucket": user_bucket, "now": now},
    )
    return True


async def block_until(conn: AsyncConnection, deadline: int) -> None:
    """Persist a provider throttle so every worker honors it."""
    await conn.execute(
        text(
            "INSERT INTO notice_rate_slots(bucket,second,count) VALUES ('blocked',:deadline,0) "
            "ON CONFLICT(bucket) DO UPDATE SET second=MAX(second,:deadline)"
        ),
        {"deadline": deadline},
    )
