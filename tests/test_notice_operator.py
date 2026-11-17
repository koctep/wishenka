"""Operator resolution must be explicit and only act on uncertain claims."""

from pathlib import Path

import pytest

from tests.notice_support import FakeNoticeSender, send_result
from tests.receipt_support import GIFTER, open_store
from tests.test_receipt_notices import _base, _Env
from wishenka.notices.operator import counts, list_uncertain, resolve

pytestmark = pytest.mark.timeout(30)


async def test_explicit_resolution_is_fenced_and_exposes_only_counts(tmp_path: Path) -> None:
    db = tmp_path / "operator.db"
    async with open_store(db) as store:
        env = _Env(store, db, verify_destinations=True)
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)
        now = _base()
        sender = FakeNoticeSender([send_result("ambiguous")])
        worker = env.worker(sender)
        await worker.run_once(now)
        stats = await counts(store)
        assert stats["receipt"] == {"uncertain": 1}
        assert await list_uncertain(store, "receipt") == [
            {"id": env.outbox_one()["id"], "attempts": 1}
        ]
        assert await resolve(store, "receipt", env.outbox_one()["id"], "retry", now + 1)
        assert not await resolve(store, "receipt", env.outbox_one()["id"], "retry", now + 1)
        await worker.run_once(now + 1)
        assert len(sender.calls) == 2
        assert env.outbox_one()["status"] == "sent"


async def test_receipt_dedupe_survives_purging_sent_delivery(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    from tests.receipt_support import GIFTER_ID
    from wishenka.notices.models import NoticeDraft
    from wishenka.wishlists.models import ReceiptRecord
    from wishenka.wishlists.service import WishlistService

    db = tmp_path / "dedupe.db"
    async with open_store(db) as store:
        env = _Env(store, db, verify_destinations=True)
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)
        receipt_id = env.outbox_one()["receipt_id"]
        worker = env.worker(FakeNoticeSender())
        await worker.run_once(_base())
        assert await worker._store.purge_finished(datetime.now(UTC) + timedelta(days=1)) == 1

        async def replay(service: WishlistService) -> None:
            service._new_notices.append(
                NoticeDraft(GIFTER_ID, ReceiptRecord(id=receipt_id, wish_item_id=env.item_id))
            )

        await store.execute(replay)
        from tests.receipt_support import outbox_rows

        assert outbox_rows(db) == []


async def test_receipt_settlement_requires_exact_claim_token(tmp_path: Path) -> None:
    from dataclasses import replace

    db = tmp_path / "fenced.db"
    async with open_store(db) as store:
        env = _Env(store, db, verify_destinations=True)
        await env.seed(5, ((GIFTER, 1),))
        await env.receive(1)
        notice_store = env.worker(FakeNoticeSender())._store
        now = _base()
        claim = await notice_store.claim_next(now)
        assert claim is not None
        assert not await notice_store.complete(replace(claim, claim_token="wrong"), now)
        assert env.outbox_one()["status"] == "sending"
        assert await notice_store.complete(claim, now)
        assert env.outbox_one()["status"] == "sent"
