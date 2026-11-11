"""API regression for durable, access-controlled wishlist sharing."""

import asyncio
import logging
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


def test_mutation_events_only_follow_success_and_hide_capabilities(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Committed mutations emit safe events; rejected operations do not."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'observability.db'}"
    settings = Settings(database_url=url, secret_key="secret")
    sessions = SessionTokenService(settings.secret_key)
    owner = {"Authorization": f"Bearer {sessions.create_token(101, 'Owner')}"}
    stranger = {"Authorization": f"Bearer {sessions.create_token(202, 'Stranger')}"}
    with (
        caplog.at_level(logging.INFO, logger="wishenka.web.wishlists"),
        TestClient(create_app(settings)) as client,
    ):
        created = client.post("/api/wishlists", json={}, headers=owner).json()
        path = f"/api/wishlists/{created['id']}"
        assert client.post(path + "/share/reset", headers=stranger).status_code == 404
        reset = client.post(path + "/share/reset", headers=owner)
        assert reset.status_code == 200
        assert client.get(f"/api/public/wishlists/{created['share_token']}").status_code == 404
    events = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "wishlist_mutation_committed"
    ]
    assert [record.__dict__["operation"] for record in events] == [
        "create_wishlist",
        "reset_share",
    ]
    for secret in (created["share_token"], reset.json()["share_token"]):
        assert all(
            secret not in str(record.__dict__)
            for record in caplog.records
            if record.name.startswith("wishenka.")
        )


def test_storage_error_traceback_does_not_expose_tokens(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A database failure with secret parameters cannot expose them in server logs."""
    from sqlalchemy.exc import IntegrityError

    url = f"sqlite+aiosqlite:///{tmp_path / 'storage-error.db'}"
    settings = Settings(database_url=url, secret_key="secret")
    sessions = SessionTokenService(settings.secret_key)
    owner = {"Authorization": f"Bearer {sessions.create_token(101, 'Owner')}"}
    app = create_app(settings)
    token = "storage-failure-secret-token"
    monkeypatch.setattr(
        secrets, "token_urlsafe", lambda size: token if size == 16 else token + "-invite"
    )

    async def fail_write(*args: object) -> None:
        raise IntegrityError("INSERT", {"token": token}, ValueError(f"sensitive {token}"))

    monkeypatch.setattr(app.state.wishlist_store, "_write", fail_write)
    with (
        caplog.at_level(logging.ERROR, logger="wishenka.web"),
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        response = client.post("/api/wishlists", json={}, headers=owner)
    assert response.status_code == 500
    errors = [
        record for record in caplog.records if record.name == "wishenka.web" and record.exc_info
    ]
    assert len(errors) == 1
    exc_info = errors[0].exc_info
    assert exc_info is not None
    rendered = logging.Formatter().formatException(exc_info)
    assert "Wishlist storage operation failed" in rendered
    assert token not in rendered
    assert token not in caplog.text


def test_anonymous_public_view_hides_existing_reservation(tmp_path: Path) -> None:
    """A real reservation is hidden when the visitor's recipient status is unknown."""
    service = WishlistService()
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    giver = AuthenticatedUser(telegram_id=202, first_name="Giver", auth_method="session_token")

    async def seed_reserved_wishlist() -> str:
        wishlist = await service.create_wishlist(owner=owner, title="Birthday")
        item = await service.add_wish_item(
            wishlist_id=wishlist.id, actor=owner, title="Board game", quantity=2
        )
        reservation = await service.create_reservation(item_id=item.id, user=giver, quantity=1)
        assert reservation.quantity == 1
        return wishlist.public_token

    token = asyncio.run(seed_reserved_wishlist())
    database = tmp_path / "reserved.db"
    app = create_app(
        Settings(database_url=f"sqlite+aiosqlite:///{database}", sqlite_db_path=str(database))
    )
    app.state.wishlist_service = service
    with TestClient(app) as client:
        response = client.get(f"/api/public/wishlists/{token}")
    assert response.status_code == 200
    public_items = response.json()["items"]
    assert len(public_items) == 1
    public_item = public_items[0]
    assert public_item["title"] == "Board game"
    forbidden_fields = {
        "available_quantity",
        "reserved_quantity",
        "is_fully_reserved",
        "is_reserved_by_me",
        "my_reserved_quantity",
        "my_reservation_status",
        "my_reservation_id",
        "reservations",
    }
    assert forbidden_fields.isdisjoint(public_item)


def test_sharing_is_private_revocable_and_persists_after_restart(tmp_path: Path) -> None:
    """A shared list survives restart without granting private access to strangers."""
    database = tmp_path / "wishlists.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{database}",
        sqlite_db_path=str(database),
        secret_key="test-secret",
    )
    sessions = SessionTokenService(settings.secret_key)
    owner = {"Authorization": f"Bearer {sessions.create_token(101, 'Owner')}"}
    stranger = {"Authorization": f"Bearer {sessions.create_token(202, 'Stranger')}"}

    with TestClient(create_app(settings)) as client:
        created = client.post("/api/wishlists", json={"name": "Birthday"}, headers=owner)
        assert created.status_code == 201
        wishlist = created.json()
        wishlist_id = wishlist["id"]
        token = wishlist["share_token"]

        assert client.get(f"/api/wishlists/{wishlist_id}", headers=stranger).status_code == 404
        public = client.get(f"/api/public/wishlists/{token}")
        assert public.status_code == 200
        assert public.json()["name"] == "Birthday"
        assert "members" not in public.json()
        assert "share_token" not in public.json()

    with TestClient(create_app(settings)) as client:
        restored = client.get(f"/api/wishlists/{wishlist_id}", headers=owner)
        assert restored.status_code == 200
        assert restored.json()["name"] == "Birthday"
        assert client.get(f"/api/public/wishlists/{token}").status_code == 200

        reset = client.post(f"/api/wishlists/{wishlist_id}/share/reset", headers=owner)
        assert reset.status_code == 200
        new_token = reset.json()["share_token"]
        assert new_token != token
        assert client.get(f"/api/public/wishlists/{token}").status_code == 404
        assert client.get(f"/api/public/wishlists/{new_token}").status_code == 200


def test_management_authorization_lifecycle_and_log_redaction(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Managers control lifecycle; public access never leaks the capability in app logs."""
    database = tmp_path / "management.db"
    settings = Settings(database_url=f"sqlite+aiosqlite:///{database}", secret_key="secret")
    sessions = SessionTokenService(settings.secret_key)
    owner = {"Authorization": f"Bearer {sessions.create_token(101, 'Owner')}"}
    stranger = {"Authorization": f"Bearer {sessions.create_token(202, 'Stranger')}"}
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/wishlists", json={}).status_code == 401
        created = client.post("/api/wishlists", json={}, headers=owner).json()
        ident, token = created["id"], created["share_token"]
        path = f"/api/wishlists/{ident}"
        assert client.patch(path, json={"name": "No"}, headers=stranger).status_code == 404
        assert client.post(path + "/share/reset", headers=stranger).status_code == 404
        assert client.patch(path, json={"name": "New"}, headers=owner).json()["name"] == "New"
        assert client.post(path + "/archive", headers=owner).status_code == 200
        assert client.get("/api/wishlists", headers=owner).json() == []
        assert client.patch(path, json={"name": "No"}, headers=owner).status_code == 409
        assert client.get(f"/api/public/wishlists/{token}").json()["status"] == "archived"
        assert client.post(path + "/restore", headers=owner).status_code == 200
        assert len(client.get("/api/wishlists", headers=owner).json()) == 1
    assert all(
        token not in record.getMessage()
        for record in caplog.records
        if record.name == "wishenka.web"
    )


@pytest.mark.asyncio
async def test_store_persists_domain_items_and_reservations_across_instances(
    tmp_path: Path,
) -> None:
    """All domain operations can share one persistent aggregate after restart."""
    from wishenka.wishlists.store import WishlistStore

    database = tmp_path / "domain.db"
    url = f"sqlite+aiosqlite:///{database}"
    first, second = WishlistStore(url), WishlistStore(url)
    await first.initialize()
    await second.initialize()
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    giver = AuthenticatedUser(telegram_id=202, first_name="Giver", auth_method="session_token")

    async def seed(service: WishlistService) -> tuple[int, int]:
        wl = await service.create_wishlist(owner=owner, title="Event")
        item = await service.add_wish_item(wishlist_id=wl.id, actor=owner, title="Gift", quantity=2)
        await service.create_reservation(item_id=item.id, user=giver, quantity=1)
        return wl.id, item.id

    wishlist_id, item_id = await first.execute(seed)

    async def inspect(service: WishlistService) -> None:
        wl = await service.get_wishlist_by_id(wishlist_id)
        assert wl.items[0].id == item_id
        assert wl.items[0].reservations[0].quantity == 1
        await service.archive_wishlist(wishlist_id, owner)

    await second.execute(inspect)

    async def inspect_archive(service: WishlistService) -> None:
        wl = await service.get_wishlist_by_id(wishlist_id)
        assert wl.status.value == "archived"
        assert wl.items[0].reservations[0].user_id == giver.telegram_id

    await first.execute(inspect_archive)
    await first.engine.dispose()
    await second.engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_instances_allocate_distinct_ids(tmp_path: Path) -> None:
    """Two workers serialize creation against the same SQLite file."""
    from wishenka.wishlists.store import WishlistStore

    url = f"sqlite+aiosqlite:///{tmp_path / 'concurrent.db'}"
    first, second = WishlistStore(url), WishlistStore(url)
    await first.initialize()
    await second.initialize()
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def create(service: WishlistService) -> int:
        return (await service.create_wishlist(owner=owner)).id

    ids = await asyncio.gather(first.execute(create), second.execute(create))
    assert sorted(ids) == [1, 2]
    await first.engine.dispose()
    await second.engine.dispose()


def test_share_token_collision_retries_and_never_revives_revoked_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A revoked capability cannot be issued again, even across a restart."""
    tokens = iter(["old", "invite1", "new", "old", "invite2", "unique", "invite3"])
    monkeypatch.setattr(secrets, "token_urlsafe", lambda _: next(tokens))
    url = f"sqlite+aiosqlite:///{tmp_path / 'collision.db'}"
    settings = Settings(database_url=url, secret_key="secret")
    sessions = SessionTokenService(settings.secret_key)
    owner = {"Authorization": f"Bearer {sessions.create_token(101, 'Owner')}"}
    with TestClient(create_app(settings)) as client:
        first = client.post("/api/wishlists", json={}, headers=owner).json()
        assert first["share_token"] == "old"
        reset = client.post(f"/api/wishlists/{first['id']}/share/reset", headers=owner)
        assert reset.json()["share_token"] == "new"
    with TestClient(create_app(settings)) as client:
        second = client.post("/api/wishlists", json={}, headers=owner)
        assert second.status_code == 201
        assert second.json()["share_token"] == "unique"
        assert client.get("/api/public/wishlists/old").status_code == 404


def test_members_can_view_but_only_managers_can_change_settings(tmp_path: Path) -> None:
    """Membership is resolved from the server-side aggregate, not client input."""
    from wishenka.wishlists.models import WishlistRole

    service = WishlistService()
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")

    async def seed() -> int:
        wl = await service.create_wishlist(owner=owner, title="Shared")
        await service.add_member(wl.id, owner, 202, WishlistRole.MEMBER)
        await service.add_member(wl.id, owner, 303, WishlistRole.ADMIN)
        return wl.id

    ident = asyncio.run(seed())
    url = f"sqlite+aiosqlite:///{tmp_path / 'membership.db'}"
    settings = Settings(database_url=url, secret_key="secret")
    sessions = SessionTokenService(settings.secret_key)
    member = {"Authorization": f"Bearer {sessions.create_token(202, 'Member')}"}
    admin = {"Authorization": f"Bearer {sessions.create_token(303, 'Admin')}"}
    app = create_app(settings)
    app.state.wishlist_service = service
    with TestClient(app) as client:
        path = f"/api/wishlists/{ident}"
        assert client.get(path, headers=member).status_code == 200
        assert "share_token" not in client.get(path, headers=member).json()
        assert client.patch(path, json={"name": "Denied"}, headers=member).status_code == 404
        assert client.post(path + "/share/reset", headers=member).status_code == 404
        assert client.patch(path, json={"name": "Allowed"}, headers=admin).status_code == 200
        assert client.post(path + "/share/reset", headers=admin).status_code == 200


def test_server_access_log_filter_redacts_public_token() -> None:
    """Uvicorn access messages must not disclose public capability tokens."""
    import logging

    from wishenka.web.app import ShareTokenAccessFilter

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %s',
        ("client", "GET", "/api/public/wishlists/private-token?x=y", "1.1", 200),
        None,
    )
    assert ShareTokenAccessFilter().filter(record)
    assert "private-token" not in record.getMessage()


def test_public_api_shows_persisted_wish_without_reservation_details(tmp_path: Path) -> None:
    """Real stored reservations remain hidden through the public HTTP API after restart."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'public.db'}"
    settings = Settings(database_url=url)
    app = create_app(settings)
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    giver = AuthenticatedUser(telegram_id=202, first_name="Giver", auth_method="session_token")

    async def seed(service: WishlistService) -> str:
        wishlist = await service.create_wishlist(owner=owner, title="Event")
        item = await service.add_wish_item(wishlist.id, owner, title="Gift", quantity=2)
        await service.create_reservation(item_id=item.id, user=giver, quantity=1)
        return wishlist.public_token

    with TestClient(app):
        token = asyncio.run(app.state.wishlist_store.execute(seed))
    with TestClient(create_app(settings)) as client:
        response = client.get(f"/api/public/wishlists/{token}")
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["title"] == "Gift"
        assert "available_quantity" not in item
        assert "reservations" not in item


def test_persistent_domain_service_is_shared_with_api_after_restart(tmp_path: Path) -> None:
    """The app's public domain service and HTTP routes share one durable unit of work."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'shared-domain.db'}"
    settings = Settings(database_url=url, secret_key="secret")
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    giver = AuthenticatedUser(telegram_id=202, first_name="Giver", auth_method="session_token")
    sessions = SessionTokenService(settings.secret_key)
    credentials = {"Authorization": f"Bearer {sessions.create_token(101, 'Owner')}"}
    app = create_app(settings)

    async def create_domain_list() -> tuple[int, int]:
        service = app.state.domain_service
        wishlist = await service.create_wishlist(owner=owner, title="Stored domain list")
        item = await service.add_wish_item(wishlist.id, owner, title="Gift", quantity=3)
        reservation = await service.create_reservation(item.id, giver, 1)
        return wishlist.id, reservation.id

    with TestClient(app) as client:
        wishlist_id, reservation_id = asyncio.run(create_domain_list())
        response = client.get(f"/api/wishlists/{wishlist_id}", headers=credentials)
        assert response.status_code == 200
        assert response.json()["items"][0]["title"] == "Gift"
    restarted = create_app(settings)
    with TestClient(restarted) as client:
        assert client.get(f"/api/wishlists/{wishlist_id}", headers=credentials).status_code == 200
        status = asyncio.run(restarted.state.domain_service.get_reservation_status(reservation_id))
        assert status.value == "active"


@pytest.mark.parametrize("operation", ["purchase", "revert", "cancel", "quantity"])
def test_archived_list_blocks_existing_reservation_mutations(
    tmp_path: Path, operation: str
) -> None:
    """All reservation changes reload and respect persisted archived lifecycle state."""
    from wishenka.wishlists.exceptions import WishlistArchivedError

    url = f"sqlite+aiosqlite:///{tmp_path / 'archived.db'}"
    app = create_app(Settings(database_url=url))
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    giver = AuthenticatedUser(telegram_id=202, first_name="Giver", auth_method="session_token")

    async def exercise() -> None:
        service = app.state.domain_service
        wishlist = await service.create_wishlist(owner=owner)
        item = await service.add_wish_item(wishlist.id, owner, title="Gift", quantity=4)
        reservation = await service.create_reservation(item.id, giver, 1)
        if operation == "revert":
            await service.mark_reservation_purchased(reservation.id, giver)
        await service.archive_wishlist(wishlist.id, owner)
        with pytest.raises(WishlistArchivedError):
            if operation == "purchase":
                await service.mark_reservation_purchased(reservation.id, giver)
            elif operation == "revert":
                await service.revert_reservation_to_active(reservation.id, giver)
            elif operation == "cancel":
                await service.cancel_reservation(reservation.id, giver)
            else:
                await service.update_reservation_quantity(reservation.id, giver, 2)

    with TestClient(app):
        asyncio.run(exercise())


@pytest.mark.asyncio
async def test_storage_enforces_unique_membership(tmp_path: Path) -> None:
    """The database independently enforces one membership per person and list."""
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from wishenka.wishlists.store import WishlistStore

    store = WishlistStore(f"sqlite+aiosqlite:///{tmp_path / 'members.db'}")
    await store.initialize()
    async with store.engine.begin() as conn:
        await conn.execute(text("INSERT INTO wl_lists VALUES (1, '{}')"))
        await conn.execute(
            text("INSERT INTO wl_members VALUES (1, 1, :body)"),
            {"body": '{"user_id": 7}'},
        )
        with pytest.raises(IntegrityError):
            await conn.execute(
                text("INSERT INTO wl_members VALUES (2, 1, :body)"),
                {"body": '{"user_id": 7}'},
            )
    await store.engine.dispose()


@pytest.mark.asyncio
async def test_domain_token_collisions_retry_and_exhaustion_hides_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Direct domain calls retry old tokens and never log a token after exhaustion."""
    import logging
    import traceback

    from wishenka.wishlists.store import WishlistStore

    tokens = iter(
        [
            "private-old",
            "invite1",
            "private-taken",
            "invite2",
            "private-taken",
            "private-new",
            "private-old",
            "invite3",
            "private-unique",
            "invite4",
            *[value for _ in range(5) for value in ("private-old", "invite")],
        ]
    )
    monkeypatch.setattr(secrets, "token_urlsafe", lambda _: next(tokens))
    store = WishlistStore(f"sqlite+aiosqlite:///{tmp_path / 'domain-collision.db'}")
    await store.initialize()
    service = WishlistService(store=store)
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    first = await service.create_wishlist(owner=owner)
    await service.create_wishlist(owner=owner)
    assert await service.regenerate_public_token(first.id, owner) == "private-new"
    third = await service.create_wishlist(owner=owner)
    assert third.public_token == "private-unique"
    with (
        caplog.at_level(logging.ERROR, logger="wishenka.test"),
        pytest.raises(RuntimeError) as failure,
    ):
        try:
            await service.create_wishlist(owner=owner)
        except RuntimeError:
            logging.getLogger("wishenka.test").exception("Expected collision exhaustion")
            raise
    rendered = "".join(traceback.format_exception(failure.value))
    assert "private-old" not in rendered
    assert "private-old" not in caplog.text
    assert "Unable to allocate a unique public token" in rendered
    await store.engine.dispose()


@pytest.mark.asyncio
async def test_domain_reset_retries_current_token_before_revoking_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A generated copy of the current token never makes reset succeed unchanged."""
    from wishenka.wishlists.exceptions import WishlistNotFoundError
    from wishenka.wishlists.store import WishlistStore

    tokens = iter(["old", "invite", "old", "old", "new"])
    monkeypatch.setattr(secrets, "token_urlsafe", lambda _: next(tokens))
    store = WishlistStore(f"sqlite+aiosqlite:///{tmp_path / 'reset-current.db'}")
    await store.initialize()
    service = WishlistService(store=store)
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    wishlist = await service.create_wishlist(owner=owner)
    assert await service.regenerate_public_token(wishlist.id, owner) == "new"
    with pytest.raises(WishlistNotFoundError):
        await service.get_wishlist_by_public_token("old")
    assert (await service.get_wishlist_by_public_token("new")).id == wishlist.id
    await store.engine.dispose()


@pytest.mark.parametrize(
    "operation", ["join", "leave", "reset_public", "reset_invite", "delete", "archive"]
)
def test_archived_list_rejects_other_domain_mutations(tmp_path: Path, operation: str) -> None:
    """Archived state is read-only except restoration, including membership and tokens."""
    from wishenka.wishlists.exceptions import WishlistArchivedError

    url = f"sqlite+aiosqlite:///{tmp_path / 'archived-domain.db'}"
    app = create_app(Settings(database_url=url))
    owner = AuthenticatedUser(telegram_id=101, first_name="Owner", auth_method="session_token")
    member = AuthenticatedUser(telegram_id=202, first_name="Member", auth_method="session_token")
    guest = AuthenticatedUser(telegram_id=303, first_name="Guest", auth_method="session_token")

    async def exercise() -> None:
        service = app.state.domain_service
        wishlist = await service.create_wishlist(owner=owner)
        await service.add_member(wishlist.id, owner, member.telegram_id)
        await service.archive_wishlist(wishlist.id, owner)
        before = await service.get_wishlist_by_id(wishlist.id)
        with pytest.raises(WishlistArchivedError):
            if operation == "join":
                await service.join_by_invite(before.invite_token, guest)
            elif operation == "leave":
                await service.remove_member(wishlist.id, member, member.telegram_id)
            elif operation == "reset_public":
                await service.regenerate_public_token(wishlist.id, owner)
            elif operation == "reset_invite":
                await service.regenerate_invite_token(wishlist.id, owner)
            elif operation == "delete":
                await service.delete_wishlist(wishlist.id, owner)
            else:
                await service.archive_wishlist(wishlist.id, owner)
        after = await service.get_wishlist_by_id(wishlist.id)
        assert after.status.value == "archived"
        assert after.public_token == before.public_token
        assert after.invite_token == before.invite_token
        assert [record.user_id for record in after.members] == [member.telegram_id]
        await service.unarchive_wishlist(wishlist.id, owner)
        assert (await service.get_wishlist_by_id(wishlist.id)).status.value == "active"

    with TestClient(app):
        asyncio.run(exercise())
