"""Bounded, content-free operator actions for uncertain notification attempts."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from wishenka.config import Settings
from wishenka.notices.fence import delivery_lock
from wishenka.wishlists.store import WishlistStore

logger = logging.getLogger("wishenka.notices.operator")

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


async def resolve(
    store: WishlistStore,
    queue: str,
    ident: int,
    action: str,
    now: int,
    *,
    operator: str = "",
    evidence: str = "",
) -> bool:
    """Explicitly retry or fail a single uncertain row; retries may duplicate a delivery."""
    if queue not in _TABLES or action not in ("retry", "fail") or ident <= 0:
        raise ValueError("Invalid resolution")
    table = _TABLES[queue]
    extra = ""
    if queue == "receipt" and action == "retry":
        extra = ",ambiguous=0"
    elif queue == "reminder":
        extra = ",updated_at=:now"

    fence_queue = "gift" if queue == "receipt" else queue

    async def find_key(conn: AsyncConnection) -> tuple[int, int] | None:
        row = (
            await conn.execute(
                text(
                    "SELECT wish_item_id,user_id FROM receipt_delivery_fence "
                    "WHERE queue=:queue AND row_id=:id"
                ),
                {"queue": fence_queue, "id": ident},
            )
        ).first()
        return (int(row[0]), int(row[1])) if row else None

    async def work(conn: AsyncConnection) -> bool:
        result = await conn.execute(
            text(
                f"UPDATE {table} SET status=:status,next_attempt_at=:now{extra} "  # noqa: S608
                "WHERE id=:id AND status='uncertain'"
            ),
            {"status": "pending" if action == "retry" else "failed", "now": now, "id": ident},
        )
        if result.rowcount and key is not None:
            params = {"queue": fence_queue, "id": ident, "operator": operator, "evidence": evidence}
            await conn.execute(
                text(
                    "INSERT INTO receipt_delivery_fence_audit "
                    "(wish_item_id,user_id,attempt_id,operator,evidence) "
                    "SELECT wish_item_id,user_id,attempt_id,:operator,:evidence "
                    "FROM receipt_delivery_fence WHERE queue=:queue AND row_id=:id"
                ),
                params,
            )
            await conn.execute(
                text("DELETE FROM receipt_delivery_fence WHERE queue=:queue AND row_id=:id"),
                params,
            )
        return bool(result.rowcount)

    key = await store.transaction(find_key)
    if key is not None:
        if not operator.strip() or not evidence.strip():
            raise ValueError("Operator and evidence are required to resolve a delivery fence")
        async with delivery_lock(store.database_url, *key):
            resolved = await store.transaction(work)
    else:
        resolved = await store.transaction(work)
    if resolved:
        logger.info(
            "Operator resolved uncertain notice",
            extra={
                "event": "operator_notice_resolved",
                "queue": queue,
                "row_id": ident,
                "action": action,
                "has_fence": key is not None,
                "operator": operator or None,
            },
        )
    else:
        logger.warning(
            "Operator resolve found no matching uncertain notice",
            extra={
                "event": "operator_notice_resolve_noop",
                "queue": queue,
                "row_id": ident,
                "action": action,
            },
        )
    return resolved


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
            result = await resolve(
                store,
                args.queue,
                args.id,
                args.action,
                int(time.time()),
                operator=args.operator,
                evidence=args.evidence,
            )
            print("resolved" if result else "not found or not uncertain")  # noqa: T201
    finally:
        await store.dispose()


def main() -> None:
    """Inspect aggregate counts or explicitly resolve an uncertain outcome."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("counts", "list", "retry", "fail"))
    parser.add_argument("--queue", choices=tuple(_TABLES), default="receipt")
    parser.add_argument("--id", type=int, default=0)
    parser.add_argument("--operator", default="")
    parser.add_argument("--evidence", default="")
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
