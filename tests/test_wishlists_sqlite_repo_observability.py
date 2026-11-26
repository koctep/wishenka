"""Observability tests for WishlistStore and WishlistRepository structured logging."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

from wishenka.auth.models import AuthenticatedUser
from wishenka.items.models import ItemPriority
from wishenka.wishlists.exceptions import WishlistNotFoundError
from wishenka.wishlists.models import (
    Reservation,
    ReservationStatus,
    ViewHistoryEntry,
    WishItem,
    Wishlist,
    WishlistFavorite,
    WishlistStatus,
)
from wishenka.wishlists.repository import WishlistRepository
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(10)


@pytest.mark.asyncio
async def test_wishlist_store_read_write_structured_logging(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify structured log events on WishlistStore read and write."""
    db_path = tmp_path / "obs_store_read_write.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    owner = AuthenticatedUser(telegram_id=1001, first_name="Bob")
    service = WishlistService(store)
    wishlist = await service.create_wishlist(owner=owner, title="Observability Wishlist")
    await service.add_wish_item(
        wishlist_id=wishlist.id,
        actor=owner,
        title="Observability Item",
    )

    async def snapshot(hydrated: WishlistService) -> None:
        await hydrated.get_user_reservations(owner.telegram_id)

    with caplog.at_level(logging.INFO, logger="wishenka.wishlists.store"):
        await store.execute(snapshot)

    read_records = [r for r in caplog.records if getattr(r, "event", None) == "wishlist_store_read"]
    write_records = [
        r for r in caplog.records if getattr(r, "event", None) == "wishlist_store_write"
    ]

    assert len(read_records) >= 1, "Expected at least one wishlist_store_read event"
    assert len(write_records) >= 1, "Expected at least one wishlist_store_write event"

    read_rec = read_records[0]
    assert getattr(read_rec, "scoped", None) is False
    assert getattr(read_rec, "wishlist_id", "missing") is None

    write_rec = write_records[0]
    assert getattr(write_rec, "scoped", None) is False
    assert getattr(write_rec, "wishlist_id", "missing") is None
    assert getattr(write_rec, "wishlists_count", None) == 1
    assert getattr(write_rec, "members_count", None) == 0
    assert getattr(write_rec, "items_count", None) == 1

    await store.engine.dispose()


@pytest.mark.asyncio
async def test_wishlist_repo_mutation_structured_logging(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify structured log events on WishlistRepository mutations."""
    db_path = tmp_path / "obs_repo_mutations.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    now = datetime.now(UTC)
    sample_wl = Wishlist(
        id=50,
        owner_id=2002,
        owner_name="Charlie",
        title="Repo Test List",
        description="Description",
        event_title=None,
        event_date=None,
        is_collaborative=False,
        status=WishlistStatus.ACTIVE,
        public_token="pub_tok_safe_test_50",
        invite_token="inv_tok_safe_test_50",
        invite_token_expires_at=None,
        created_at=now,
        updated_at=now,
        members=[],
        items=[],
    )

    sample_item = WishItem(
        id=70,
        wishlist_id=50,
        recipient_user_id=None,
        recipient_name=None,
        title="Mechanical Keyboard",
        description=None,
        link=None,
        price=15000,
        currency="RUB",
        quantity=1,
        received_quantity=0,
        image_url=None,
        store_name=None,
        store_icon_url=None,
        priority=ItemPriority.HIGH,
        category="Tech",
        is_archived=False,
        created_at=now,
        updated_at=now,
        reservations=[],
    )

    sample_res = Reservation(
        id=90,
        wish_item_id=70,
        user_id=3003,
        quantity=1,
        status=ReservationStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )

    sample_fav = WishlistFavorite(
        user_id=3003,
        wishlist_id=50,
        created_at=now,
    )

    sample_view = ViewHistoryEntry(
        id=0,
        user_id=3003,
        wishlist_id=50,
        viewed_at=now,
    )

    with caplog.at_level(logging.INFO, logger="wishenka.wishlists.repository"):
        async with store.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT OR IGNORE INTO users (telegram_id, first_name, created_at, updated_at) "
                    "VALUES (3003, 'Viewer', :now, :now)"
                ),
                {"now": now},
            )
            repo = WishlistRepository(conn)

            await repo.upsert_wishlist(sample_wl)
            await repo.upsert_item(sample_item)
            await repo.upsert_reservation(sample_res)
            await repo.upsert_favorite(sample_fav)
            await repo.record_view(sample_view)

            await repo.delete_favorite(sample_fav.user_id, sample_fav.wishlist_id)
            await repo.delete_reservation(sample_res.id)
            await repo.delete_item(sample_item.id)
            await repo.delete_wishlist(sample_wl.id)
            await repo.clear_view_history(3003)

    mutations = [r for r in caplog.records if getattr(r, "event", None) == "wishlist_repo_mutation"]

    expected_ops = [
        ("wishlist", "upsert"),
        ("item", "upsert"),
        ("reservation", "upsert"),
        ("favorite", "upsert"),
        ("view_history", "record"),
        ("favorite", "delete"),
        ("reservation", "delete"),
        ("item", "delete"),
        ("wishlist", "delete"),
        ("view_history", "clear"),
    ]

    actual_ops = [(getattr(m, "entity", None), getattr(m, "operation", None)) for m in mutations]

    assert actual_ops == expected_ops

    await store.engine.dispose()


@pytest.mark.asyncio
async def test_token_redaction_in_all_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify secret capability tokens are never leaked into log messages or extras."""
    db_path = tmp_path / "obs_token_redaction.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    secret_public = "SECRET_CAPABILITY_PUB_TOKEN_XYZ999"
    secret_invite = "SECRET_CAPABILITY_INV_TOKEN_ABC888"

    # Capture all logs down to DEBUG from wishenka
    with caplog.at_level(logging.DEBUG, logger="wishenka"):
        async with store.engine.begin() as conn:
            repo = WishlistRepository(conn)
            now = datetime.now(UTC)
            wl = Wishlist(
                id=1,
                owner_id=4004,
                owner_name="Dave",
                title="Super Secret List",
                description=None,
                event_title=None,
                event_date=None,
                is_collaborative=False,
                status=WishlistStatus.ACTIVE,
                public_token=secret_public,
                invite_token=secret_invite,
                invite_token_expires_at=None,
                created_at=now,
                updated_at=now,
                members=[],
                items=[],
            )
            await repo.upsert_wishlist(wl)
            await repo.get_wishlist(1)

        # Also run through store execute
        async def op(service: WishlistService) -> None:
            pass

        await store.execute(op)

    for record in caplog.records:
        message = record.getMessage()
        extras_dump = repr(record.__dict__)

        assert secret_public not in message, f"Secret public token leaked in message: {message}"
        assert secret_invite not in message, f"Secret invite token leaked in message: {message}"
        assert secret_public not in extras_dump, "Secret public token leaked in log extra dict"
        assert secret_invite not in extras_dump, "Secret invite token leaked in log extra dict"

    await store.engine.dispose()


@pytest.mark.asyncio
async def test_token_collision_retry_logging(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A shared create retries a colliding token on the repository path and does not log it."""
    db_path = tmp_path / "obs_collision_retry.db"
    store = WishlistStore(f"sqlite+aiosqlite:///{db_path}")
    await store.initialize()

    owner = AuthenticatedUser(telegram_id=5005, first_name="Eve")

    colliding_tokens = ["COLLIDING_SECRET_TOKEN_111", "COLLIDING_SECRET_TOKEN_222"]
    call_count = 0

    def mock_generate(*_args: object, **_kwargs: object) -> str:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return colliding_tokens[0]
        return f"unique_token_{call_count}"

    with caplog.at_level(logging.WARNING, logger="wishenka.wishlists.store"):
        # Pre-populate wl_invite_tokens with colliding token
        async with store.engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO wl_lists (id, owner_id, title, status, public_token, "
                    "invite_token, created_at, updated_at) "
                    "VALUES (999, 1, 'Other', 'active', 'pub_999', :token, "
                    "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
                ),
                {"token": colliding_tokens[0]},
            )
            await conn.execute(
                text("INSERT INTO wl_invite_tokens (token, wishlist_id) VALUES (:token, 999)"),
                {"token": colliding_tokens[0]},
            )

        with patch("wishenka.wishlists.service.secrets.token_urlsafe", side_effect=mock_generate):
            created = await WishlistService(store).create_wishlist(owner=owner, title="Retry List")

    assert created.title == "Retry List"
    assert call_count > 2

    for r in caplog.records:
        assert colliding_tokens[0] not in r.getMessage()
        assert colliding_tokens[0] not in repr(r.__dict__)

    await store.engine.dispose()


@pytest.mark.asyncio
async def test_in_memory_shared_action_logs_repository_path_required(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An in-memory shared action fails closed and names only the operation."""
    service = WishlistService.in_memory()
    owner = AuthenticatedUser(telegram_id=1, first_name="Ada")
    with caplog.at_level(logging.WARNING, logger="wishenka.wishlists"):
        with pytest.raises(WishlistNotFoundError, match="repository path"):
            await service.record_view(owner, 1)
        with pytest.raises(WishlistNotFoundError, match="repository path"):
            await service.get_wishlist_by_public_token("secret-public-token", owner)

    matches = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "wishlist_repository_path_required"
    ]
    assert [getattr(record, "operation", None) for record in matches] == [
        "record_view",
        "get_wishlist_by_public_token",
    ]
    rendered = " ".join(record.getMessage() + repr(record.__dict__) for record in matches)
    assert "secret-public-token" not in rendered
    assert "Ada" not in rendered
