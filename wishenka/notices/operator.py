"""Bounded, content-free operator actions for uncertain notification attempts."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.config import Settings
from wishenka.wishlists.store import WishlistStore

_TABLES = {"receipt": "notification_outbox", "reminder": "reminder_outbox"}


async def counts(store: WishlistStore) -> dict[str, dict[str, int]]:
    """Return aggregate queue states without user or message data."""

    async def work(conn: AsyncConnection) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        for name, table in _TABLES.items():
            rows = (
                await conn.execute(
                    text(
                        f"SELECT status,COUNT(*) FROM {table} GROUP BY status"  # noqa: S608
                    )
                )
            ).all()
            result[name] = {str(status): int(count) for status, count in rows}
        return result

    return await store.transaction(work)


async def list_uncertain(
    store: WishlistStore, queue: str, limit: int = 100
) -> list[dict[str, int]]:
    """Return bounded row IDs and attempt counts, without recipients or message data."""
    if queue not in _TABLES or not 1 <= limit <= 100:
        raise ValueError("Invalid queue or limit")
    table = _TABLES[queue]

    async def work(conn: AsyncConnection) -> list[dict[str, int]]:
        rows = (
            await conn.execute(
                text(
                    f"SELECT id,attempts FROM {table} "  # noqa: S608
                    "WHERE status='uncertain' ORDER BY id LIMIT :limit"
                ),
                {"limit": limit},
            )
        ).all()
        return [{"id": int(row[0]), "attempts": int(row[1])} for row in rows]

    return await store.transaction(work)


async def resolve(store: WishlistStore, queue: str, ident: int, action: str, now: int) -> bool:
    """Explicitly retry or fail a single uncertain row; retries may duplicate a delivery."""
    if queue not in _TABLES or action not in ("retry", "fail") or ident <= 0:
        raise ValueError("Invalid resolution")
    table = _TABLES[queue]
    extra = ""
    if queue == "receipt" and action == "retry":
        extra = ",ambiguous=0"
    elif queue == "reminder":
        extra = ",updated_at=:now"

    async def work(conn: AsyncConnection) -> bool:
        result = await conn.execute(
            text(
                f"UPDATE {table} SET status=:status,next_attempt_at=:now{extra} "  # noqa: S608
                "WHERE id=:id AND status='uncertain'"
            ),
            {"status": "pending" if action == "retry" else "failed", "now": now, "id": ident},
        )
        return bool(result.rowcount)

    return await store.transaction(work)


async def _main(args: Any) -> None:
    settings = Settings()
    store = WishlistStore(settings.database_url)
    await store.initialize()
    try:
        if args.action == "counts":
            print(json.dumps(await counts(store), sort_keys=True))  # noqa: T201
        elif args.action == "list":
            print(json.dumps(await list_uncertain(store, args.queue), sort_keys=True))  # noqa: T201
        else:
            result = await resolve(store, args.queue, args.id, args.action, int(time.time()))
            print("resolved" if result else "not found or not uncertain")  # noqa: T201
    finally:
        await store.dispose()


def main() -> None:
    """Inspect aggregate counts or explicitly resolve an uncertain outcome."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("counts", "list", "retry", "fail"))
    parser.add_argument("--queue", choices=tuple(_TABLES), default="receipt")
    parser.add_argument("--id", type=int, default=0)
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
