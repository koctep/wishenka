"""Cross-process exclusion for a wish/giver's receipt deliveries."""

from __future__ import annotations

import asyncio
import errno
import fcntl
import hashlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING
from weakref import WeakKeyDictionary

from sqlalchemy.ext.asyncio import AsyncConnection

if TYPE_CHECKING:
    from wishenka.wishlists.store import WishlistStore

logger = logging.getLogger("wishenka.notices.fence")

_LOCAL_LOCKS: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[Path, asyncio.Lock]] = (
    WeakKeyDictionary()
)


def _lock_path(database_url: str, item_id: int, user_id: int) -> Path:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        raise OSError("Receipt delivery requires a shared SQLite lock namespace")
    database = Path(database_url[len(prefix) :]).resolve()
    directory = database.parent / (database.name + ".receipt-locks")
    directory.mkdir(mode=0o700, exist_ok=True)
    if (
        directory.is_symlink()
        or not directory.is_dir()
        or directory.stat().st_uid != os.geteuid()
        or directory.stat().st_mode & 0o077
    ):
        raise OSError("Invalid receipt delivery lock namespace")
    key = hashlib.sha256(f"{item_id}:{user_id}".encode()).hexdigest()
    return directory / key


class _DeliveryLock:
    """Nonblocking per-(item, user) lock across both asyncio tasks and OS processes."""

    def __init__(self, database_url: str, item_id: int, user_id: int) -> None:
        self._database_url = database_url
        self._item_id = item_id
        self._user_id = user_id
        self._descriptor: int | None = None
        self._local_lock: asyncio.Lock | None = None
        self._local_key: Path | None = None
        self._loop_locks: dict[Path, asyncio.Lock] | None = None

    def _acquire_file_lock(self, lock_path: Path) -> None:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(descriptor)
            raise
        self._descriptor = descriptor

    def _release_file_lock(self) -> None:
        if self._descriptor is not None:
            try:
                os.close(self._descriptor)
            finally:
                self._descriptor = None

    def _release_local_lock(self) -> None:
        if self._local_lock is not None:
            try:
                self._local_lock.release()
            finally:
                if (
                    self._loop_locks is not None
                    and self._local_key is not None
                    and not self._local_lock.locked()
                    and self._loop_locks.get(self._local_key) is self._local_lock
                ):
                    self._loop_locks.pop(self._local_key, None)
                self._local_lock = None
                self._local_key = None
                self._loop_locks = None

    def __enter__(self) -> None:
        lock_path = _lock_path(self._database_url, self._item_id, self._user_id)
        self._acquire_file_lock(lock_path)

    def __exit__(self, *_: object) -> None:
        self._release_file_lock()

    async def __aenter__(self) -> None:
        lock_path = _lock_path(self._database_url, self._item_id, self._user_id)
        loop = asyncio.get_running_loop()
        loop_locks = _LOCAL_LOCKS.setdefault(loop, {})
        local_lock = loop_locks.get(lock_path)
        if local_lock is None:
            local_lock = asyncio.Lock()
            loop_locks[lock_path] = local_lock
        if local_lock.locked():
            raise BlockingIOError(errno.EAGAIN, "Receipt delivery lock is busy")
        await local_lock.acquire()
        self._local_lock = local_lock
        self._local_key = lock_path
        self._loop_locks = loop_locks
        try:
            self._acquire_file_lock(lock_path)
        except BaseException:
            self._release_local_lock()
            raise

    async def __aexit__(self, *_: object) -> None:
        try:
            self._release_file_lock()
        finally:
            self._release_local_lock()


def delivery_lock(database_url: str, item_id: int, user_id: int) -> _DeliveryLock:
    """Acquire a nonblocking stable lock shared by all tasks and processes using this database."""
    return _DeliveryLock(database_url, item_id, user_id)


async def claim_key(
    store: WishlistStore, queue: str, row_id: int, token: str
) -> tuple[int, int] | None:
    """Return the still-current receipt claim's coordination key."""
    from sqlalchemy import text

    async def work(conn: AsyncConnection) -> tuple[int, int] | None:
        if queue == "gift":
            query = (
                "SELECT wish_item_id, giver_user_id FROM notification_outbox "
                "WHERE id=:id AND status='sending' AND claim_token=:token"
            )
        else:
            query = (
                "SELECT item_id, user_id FROM reminder_outbox "
                "WHERE id=:id AND status='sending' AND claim_token=:token "
                "AND kind IN ('receipt_increased', 'receipt_reverted')"
            )
        row = (await conn.execute(text(query), {"id": row_id, "token": token})).first()
        return (int(row[0]), int(row[1])) if row and row[0] is not None else None

    return await store.transaction(work)


async def begin_attempt(
    store: WishlistStore, key: tuple[int, int], queue: str, row_id: int, token: str
) -> bool:
    """Persist a fence only while the queue token is still current."""
    from sqlalchemy import text

    async def work(conn: AsyncConnection) -> bool:
        table = "notification_outbox" if queue == "gift" else "reminder_outbox"
        valid = await conn.scalar(
            text(f"SELECT 1 FROM {table} WHERE id=:id AND status='sending' AND claim_token=:token"),
            {"id": row_id, "token": token},
        )
        if not valid:
            logger.debug(
                "Receipt fence skipped: stale claim",
                extra={
                    "event": "receipt_fence_stale_claim",
                    "queue": queue,
                    "row_id": row_id,
                    "item_id": key[0],
                    "user_id": key[1],
                },
            )
            return False
        open_promise = await conn.scalar(
            text(
                "SELECT 1 FROM wl_reservations WHERE wish_item_id=:item AND user_id=:user "
                "AND status IN ('active','purchased') LIMIT 1"
            ),
            {"item": key[0], "user": key[1]},
        )
        if not open_promise:
            logger.debug(
                "Receipt fence skipped: no open promise",
                extra={
                    "event": "receipt_fence_no_open_promise",
                    "queue": queue,
                    "row_id": row_id,
                    "item_id": key[0],
                    "user_id": key[1],
                },
            )
            return False
        result = await conn.execute(
            text(
                "INSERT OR IGNORE INTO receipt_delivery_fence "
                "(wish_item_id,user_id,attempt_id,queue,row_id,state) "
                "VALUES (:item,:user,:token,:queue,:row,'in_flight')"
            ),
            {"item": key[0], "user": key[1], "token": token, "queue": queue, "row": row_id},
        )
        if result.rowcount == 1:
            logger.debug(
                "Receipt delivery fence recorded",
                extra={
                    "event": "receipt_fence_recorded",
                    "queue": queue,
                    "row_id": row_id,
                    "item_id": key[0],
                    "user_id": key[1],
                },
            )
            return True
        logger.warning(
            "Receipt delivery fence already active",
            extra={
                "event": "receipt_fence_busy",
                "queue": queue,
                "row_id": row_id,
                "item_id": key[0],
                "user_id": key[1],
            },
        )
        return False

    return await store.transaction(work)


async def defer_claim(store: WishlistStore, queue: str, row_id: int, token: str, now: int) -> bool:
    """Release a claim when no external send was started, without consuming an attempt."""
    from sqlalchemy import text

    async def work(conn: AsyncConnection) -> bool:
        table = "notification_outbox" if queue == "gift" else "reminder_outbox"
        result = await conn.execute(
            text(
                f"UPDATE {table} SET status='pending', claimed_at=NULL, claim_token=NULL, "
                "attempts=MAX(0, attempts-1), next_attempt_at=:next "
                "WHERE id=:id AND status='sending' AND claim_token=:token"
            ),
            {"next": now + 1, "id": row_id, "token": token},
        )
        if result.rowcount:
            logger.info(
                "Receipt delivery claim deferred",
                extra={
                    "event": "receipt_claim_deferred",
                    "queue": queue,
                    "row_id": row_id,
                },
            )
        return bool(result.rowcount)

    return await store.transaction(work)


async def finish_attempt(
    store: WishlistStore, key: tuple[int, int], token: str, definitive: bool
) -> None:
    """Retain uncertain attempts; clear a definitively settled attempt only."""
    from sqlalchemy import text

    async def work(conn: AsyncConnection) -> None:
        action = (
            "DELETE FROM receipt_delivery_fence"
            if definitive
            else "UPDATE receipt_delivery_fence SET state='uncertain'"
        )
        await conn.execute(
            text(action + " WHERE wish_item_id=:item AND user_id=:user AND attempt_id=:token"),
            {"item": key[0], "user": key[1], "token": token},
        )
        if definitive:
            logger.debug(
                "Receipt delivery fence cleared",
                extra={"event": "receipt_fence_cleared", "item_id": key[0], "user_id": key[1]},
            )
        else:
            logger.warning(
                "Receipt delivery fence marked uncertain",
                extra={"event": "receipt_fence_uncertain", "item_id": key[0], "user_id": key[1]},
            )

    await store.transaction(work)


async def has_fence(store: WishlistStore, item_id: int, user_id: int) -> bool:
    """Check for an unresolved attempt while the key lock is held."""
    from sqlalchemy import text

    async def work(conn: AsyncConnection) -> bool:
        return bool(
            await conn.scalar(
                text(
                    "SELECT 1 FROM receipt_delivery_fence "
                    "WHERE wish_item_id=:item AND user_id=:user"
                ),
                {"item": item_id, "user": user_id},
            )
        )

    return await store.transaction(work)


async def resolve_attempt(
    store: WishlistStore, item_id: int, user_id: int, *, operator: str, evidence: str
) -> bool:
    """Resolve a reconciled attempt with an auditable operator and evidence statement.

    The operator must establish that the prior sender cannot resume and the remote
    outcome is final; the per-key lock rules out a live cooperating sender.
    """
    from sqlalchemy import text

    if not operator.strip() or not evidence.strip():
        raise ValueError("Operator and evidence are required")
    async with delivery_lock(store.database_url, item_id, user_id):

        async def work(conn: AsyncConnection) -> bool:
            params = {"item": item_id, "user": user_id, "operator": operator, "evidence": evidence}
            result = await conn.execute(
                text(
                    "INSERT INTO receipt_delivery_fence_audit "
                    "(wish_item_id,user_id,attempt_id,operator,evidence) "
                    "SELECT wish_item_id,user_id,attempt_id,:operator,:evidence "
                    "FROM receipt_delivery_fence WHERE wish_item_id=:item AND user_id=:user"
                ),
                params,
            )
            if result.rowcount:
                await conn.execute(
                    text(
                        "DELETE FROM receipt_delivery_fence "
                        "WHERE wish_item_id=:item AND user_id=:user"
                    ),
                    params,
                )
                logger.info(
                    "Receipt delivery fence resolved",
                    extra={
                        "event": "receipt_fence_resolved",
                        "item_id": item_id,
                        "user_id": user_id,
                        "operator": operator,
                        "resolved_rows": result.rowcount,
                    },
                )
            else:
                logger.debug(
                    "No receipt delivery fence found to resolve",
                    extra={
                        "event": "receipt_fence_resolve_noop",
                        "item_id": item_id,
                        "user_id": user_id,
                        "operator": operator,
                    },
                )
            return bool(result.rowcount)

        return await store.transaction(work)
