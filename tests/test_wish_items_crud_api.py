"""Failing reproduction test suite for WISHENKA-13.

Covers CRUD REST API for wishlist items with multi-quantity accounting,
Reduction Lock invariant, Surprise Invariant zero-leak projections,
reordering permutation integrity, and safe archiving & restore lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wishenka.auth.models import AuthenticatedUser
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.exceptions import WishlistArchivedError
from wishenka.wishlists.models import WishlistRole
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


def make_user(telegram_id: int, first_name: str, username: str | None = None) -> AuthenticatedUser:
    """Create test AuthenticatedUser instance."""
    return AuthenticatedUser(
        telegram_id=telegram_id,
        first_name=first_name,
        username=username,
        auth_method="session_token",
    )


def auth_header(sessions: SessionTokenService, user_id: int, name: str = "User") -> dict[str, str]:
    """Generate Authorization header with valid session bearer token."""
    return {"Authorization": f"Bearer {sessions.create_token(user_id, name)}"}


@pytest.fixture
def test_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Initialize TestClient and SessionTokenService with an isolated database."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'wish_items_crud.db'}",
        secret_key="wish-items-crud-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


# ============================================================================
# 1. Creation & Display Order (POST /api/wishlists/{wishlist_id}/items)
# ============================================================================


def test_create_wish_item_success_auto_display_order(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """POST /api/wishlists/{wishlist_id}/items creates items with
    auto-incrementing display_order.
    """
    client, sessions, _ = test_app
    owner_headers = auth_header(sessions, 101, "Alice")

    # 1. Create a wishlist
    resp_wl = client.post(
        "/api/wishlists", json={"name": "Alice's Wishlist"}, headers=owner_headers
    )
    assert resp_wl.status_code == 201
    wl_id = resp_wl.json()["id"]

    # 2. Create first item
    item1_payload = {
        "title": "Sony WH-1000XM5",
        "description": "Silver color preferred",
        "link": "https://example.com/headphones",
        "price": 32000,
        "currency": "RUB",
        "quantity": 1,
        "priority": "high",
        "category": "Electronics",
    }
    resp_item1 = client.post(
        f"/api/wishlists/{wl_id}/items", json=item1_payload, headers=owner_headers
    )
    assert resp_item1.status_code == 201
    data1 = resp_item1.json()
    assert data1["title"] == "Sony WH-1000XM5"
    assert data1["price"] == 32000
    assert data1["quantity"] == 1
    assert data1["display_order"] == 0
    assert data1["is_archived"] is False
    assert data1["is_recipient"] is True

    # 3. Create second item (multi-quantity)
    item2_payload = {
        "title": "Ceramic Plates",
        "description": "Dinner set",
        "price": 6000,
        "quantity": 6,
        "priority": "medium",
    }
    resp_item2 = client.post(
        f"/api/wishlists/{wl_id}/items", json=item2_payload, headers=owner_headers
    )
    assert resp_item2.status_code == 201
    data2 = resp_item2.json()
    assert data2["title"] == "Ceramic Plates"
    assert data2["quantity"] == 6
    assert data2["display_order"] == 1
    assert data2["is_archived"] is False


def test_create_wish_item_with_collaborator_recipient(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """POST item in collaborative wishlist allows targeting a member or external recipient name."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice")
    member_headers = auth_header(sessions, 102, "Bob")

    # Create wishlist and add Bob as member
    resp_wl = client.post("/api/wishlists", json={"name": "Family Wishlist"}, headers=owner_headers)
    assert resp_wl.status_code == 201
    wl_id = resp_wl.json()["id"]

    asyncio.run(
        service.add_member(wishlist_id=wl_id, actor=owner, user_id=102, role=WishlistRole.MEMBER)
    )

    # Bob creates item addressed to himself
    payload_bob = {
        "title": "Running Shoes",
        "quantity": 1,
        "recipient_user_id": 102,
    }
    resp_bob = client.post(
        f"/api/wishlists/{wl_id}/items", json=payload_bob, headers=member_headers
    )
    assert resp_bob.status_code == 201
    assert resp_bob.json()["recipient_user_id"] == 102

    # Alice creates item addressed to external recipient
    payload_grandma = {
        "title": "Warm Scarf",
        "quantity": 1,
        "recipient_name": "Grandma Nina",
    }
    resp_grandma = client.post(
        f"/api/wishlists/{wl_id}/items", json=payload_grandma, headers=owner_headers
    )
    assert resp_grandma.status_code == 201
    assert resp_grandma.json()["recipient_name"] == "Grandma Nina"

    # Attempting to assign recipient_user_id of non-member fails with 400
    payload_invalid = {
        "title": "Mystery Gift",
        "quantity": 1,
        "recipient_user_id": 99999,
    }
    resp_invalid = client.post(
        f"/api/wishlists/{wl_id}/items", json=payload_invalid, headers=owner_headers
    )
    assert resp_invalid.status_code == 400


def test_create_wish_item_validation_errors(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """POST /api/wishlists/{wishlist_id}/items rejects invalid inputs with 422."""
    client, sessions, _ = test_app
    owner_headers = auth_header(sessions, 101, "Alice")

    resp_wl = client.post(
        "/api/wishlists", json={"name": "Validation Test List"}, headers=owner_headers
    )
    wl_id = resp_wl.json()["id"]

    # 1. Empty title
    assert (
        client.post(
            f"/api/wishlists/{wl_id}/items", json={"title": ""}, headers=owner_headers
        ).status_code
        == 422
    )

    # 2. Whitespace-only title
    assert (
        client.post(
            f"/api/wishlists/{wl_id}/items", json={"title": "   "}, headers=owner_headers
        ).status_code
        == 422
    )

    # 3. Quantity zero
    assert (
        client.post(
            f"/api/wishlists/{wl_id}/items",
            json={"title": "Item", "quantity": 0},
            headers=owner_headers,
        ).status_code
        == 422
    )

    # 4. Quantity negative
    assert (
        client.post(
            f"/api/wishlists/{wl_id}/items",
            json={"title": "Item", "quantity": -3},
            headers=owner_headers,
        ).status_code
        == 422
    )

    # 5. Quantity above max 1000
    assert (
        client.post(
            f"/api/wishlists/{wl_id}/items",
            json={"title": "Item", "quantity": 1001},
            headers=owner_headers,
        ).status_code
        == 422
    )

    # 6. Price negative
    assert (
        client.post(
            f"/api/wishlists/{wl_id}/items",
            json={"title": "Item", "price": -100},
            headers=owner_headers,
        ).status_code
        == 422
    )


def test_create_wish_item_access_control(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Non-members and unauthenticated requests cannot add items (returns 401/403/404)."""
    client, sessions, _ = test_app
    owner_headers = auth_header(sessions, 101, "Alice")
    stranger_headers = auth_header(sessions, 202, "Charlie")

    resp_wl = client.post("/api/wishlists", json={"name": "Private List"}, headers=owner_headers)
    wl_id = resp_wl.json()["id"]

    # Stranger attempt
    resp_stranger = client.post(
        f"/api/wishlists/{wl_id}/items",
        json={"title": "Intrusion Gift"},
        headers=stranger_headers,
    )
    assert resp_stranger.status_code in {403, 404}

    # Unauthenticated attempt
    resp_unauth = client.post(f"/api/wishlists/{wl_id}/items", json={"title": "No Auth"})
    assert resp_unauth.status_code in {401, 403, 404}


# ============================================================================
# 2. Parent Wishlist State Invariant (Archived: 409, Deleted: 404)
# ============================================================================


def test_mutations_on_archived_wishlist_return_409(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """All item mutations on an archived wishlist must be rejected with HTTP 409."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice")

    # 1. Create list and seed an item
    resp_wl = client.post("/api/wishlists", json={"name": "To Archive List"}, headers=owner_headers)
    wl_id = resp_wl.json()["id"]

    item = asyncio.run(
        service.add_wish_item(
            wishlist_id=wl_id,
            actor=owner,
            title="Pre-existing Item",
            quantity=2,
        )
    )

    # 2. Archive the wishlist
    resp_arch = client.post(f"/api/wishlists/{wl_id}/archive", headers=owner_headers)
    assert resp_arch.status_code == 200

    # 3. Attempt CREATE item -> 409 Conflict
    resp_create = client.post(
        f"/api/wishlists/{wl_id}/items",
        json={"title": "New Item"},
        headers=owner_headers,
    )
    assert resp_create.status_code == 409

    # 4. Attempt UPDATE item -> 409 Conflict
    resp_patch = client.patch(
        f"/api/wishlists/{wl_id}/items/{item.id}",
        json={"title": "Modified Title"},
        headers=owner_headers,
    )
    assert resp_patch.status_code == 409

    # 5. Attempt REORDER items -> 409 Conflict
    resp_reorder = client.put(
        f"/api/wishlists/{wl_id}/items/reorder",
        json={"item_ids": [item.id]},
        headers=owner_headers,
    )
    assert resp_reorder.status_code == 409

    # 6. Attempt ARCHIVE item -> 409 Conflict
    resp_archive = client.post(
        f"/api/wishlists/{wl_id}/items/{item.id}/archive",
        headers=owner_headers,
    )
    assert resp_archive.status_code == 409

    # 7. Attempt RESTORE item -> 409 Conflict
    resp_restore = client.post(
        f"/api/wishlists/{wl_id}/items/{item.id}/restore",
        headers=owner_headers,
    )
    assert resp_restore.status_code == 409


def test_mutations_on_deleted_wishlist_return_404(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Mutations on a deleted wishlist return HTTP 404."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice")

    resp_wl = client.post("/api/wishlists", json={"name": "To Delete List"}, headers=owner_headers)
    wl_id = resp_wl.json()["id"]

    item = asyncio.run(
        service.add_wish_item(
            wishlist_id=wl_id,
            actor=owner,
            title="Item to be deleted",
        )
    )

    # Delete wishlist
    asyncio.run(service.delete_wishlist(wishlist_id=wl_id, actor=owner))

    # All mutations should return 404
    assert (
        client.post(
            f"/api/wishlists/{wl_id}/items",
            json={"title": "Should Fail"},
            headers=owner_headers,
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/wishlists/{wl_id}/items/{item.id}",
            json={"title": "Should Fail"},
            headers=owner_headers,
        ).status_code
        == 404
    )


# ============================================================================
# 3. Retrieval & Projection: Surprise Invariant
# ============================================================================


def test_get_items_and_single_item_surprise_invariant(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Surprise Invariant: Recipient view hides availability & reservations;
    Gifter view exposes them.
    """
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    gifter = make_user(303, "Dana")
    owner_headers = auth_header(sessions, 101, "Alice")
    gifter_headers = auth_header(sessions, 303, "Dana")

    resp_wl = client.post(
        "/api/wishlists", json={"name": "Alice's Secret Wishlist"}, headers=owner_headers
    )
    wl_id = resp_wl.json()["id"]

    # Add item with quantity 4
    item = asyncio.run(
        service.add_wish_item(
            wishlist_id=wl_id,
            actor=owner,
            title="Special Coffee Beans",
            quantity=4,
        )
    )

    # Gifter reserves 2 units
    asyncio.run(service.create_reservation(item_id=item.id, user=gifter, quantity=2))

    # 1. Recipient (Alice) fetches items list
    resp_owner_list = client.get(f"/api/wishlists/{wl_id}/items", headers=owner_headers)
    assert resp_owner_list.status_code == 200
    items_owner = resp_owner_list.json()
    assert len(items_owner) == 1
    item_owner_view = items_owner[0]
    assert item_owner_view["id"] == item.id
    assert item_owner_view["quantity"] == 4
    assert item_owner_view["is_recipient"] is True
    # Zero-leak check: recipient view MUST NOT expose booking data
    assert (
        "available_quantity" not in item_owner_view
        or item_owner_view.get("available_quantity") is None
    )
    assert (
        "my_reserved_quantity" not in item_owner_view
        or item_owner_view.get("my_reserved_quantity") is None
    )

    # Recipient fetches single item
    resp_owner_single = client.get(f"/api/wishlists/{wl_id}/items/{item.id}", headers=owner_headers)
    assert resp_owner_single.status_code == 200
    single_owner_view = resp_owner_single.json()
    assert single_owner_view["is_recipient"] is True
    assert (
        "available_quantity" not in single_owner_view
        or single_owner_view.get("available_quantity") is None
    )

    # 2. Gifter (Dana) fetches items list
    resp_gifter_list = client.get(f"/api/wishlists/{wl_id}/items", headers=gifter_headers)
    assert resp_gifter_list.status_code == 200
    items_gifter = resp_gifter_list.json()
    assert len(items_gifter) == 1
    item_gifter_view = items_gifter[0]
    assert item_gifter_view["id"] == item.id
    assert item_gifter_view["quantity"] == 4
    assert item_gifter_view["is_recipient"] is False
    assert item_gifter_view["available_quantity"] == 2
    assert item_gifter_view["is_reserved_by_me"] is True
    assert item_gifter_view["my_reserved_quantity"] == 2

    # Gifter fetches single item
    resp_gifter_single = client.get(
        f"/api/wishlists/{wl_id}/items/{item.id}", headers=gifter_headers
    )
    assert resp_gifter_single.status_code == 200
    single_gifter_view = resp_gifter_single.json()
    assert single_gifter_view["is_recipient"] is False
    assert single_gifter_view["available_quantity"] == 2
    assert single_gifter_view["is_reserved_by_me"] is True


def test_get_items_collaborative_addressing_surprise_invariant(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """In collaborative wishlists, Surprise Invariant only hides reservation data
    from the designated recipient.
    """
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    alice = make_user(101, "Alice")
    bob = make_user(102, "Bob")
    charlie = make_user(103, "Charlie")

    alice_headers = auth_header(sessions, 101, "Alice")
    bob_headers = auth_header(sessions, 102, "Bob")

    resp_wl = client.post("/api/wishlists", json={"name": "Family Gifts"}, headers=alice_headers)
    wl_id = resp_wl.json()["id"]

    # Add Bob and Charlie as members
    asyncio.run(
        service.add_member(wishlist_id=wl_id, actor=alice, user_id=102, role=WishlistRole.MEMBER)
    )
    asyncio.run(
        service.add_member(wishlist_id=wl_id, actor=alice, user_id=103, role=WishlistRole.MEMBER)
    )

    # Item 1: Addressed to Bob (recipient_user_id = 102)
    item_for_bob = asyncio.run(
        service.add_wish_item(
            wishlist_id=wl_id,
            actor=alice,
            title="Bob's Surprise Guitar",
            quantity=1,
            recipient_user_id=102,
        )
    )
    # Charlie reserves Bob's guitar
    asyncio.run(service.create_reservation(item_id=item_for_bob.id, user=charlie, quantity=1))

    # Item 2: Addressed to Alice (recipient_user_id = 101)
    item_for_alice = asyncio.run(
        service.add_wish_item(
            wishlist_id=wl_id,
            actor=bob,
            title="Alice's Surprise Painting",
            quantity=1,
            recipient_user_id=101,
        )
    )

    # Bob views items:
    # - Bob is recipient of Item 1 -> must NOT see reservation info
    # - Bob is NOT recipient of Item 2 -> CAN see reservation info
    resp_bob = client.get(f"/api/wishlists/{wl_id}/items", headers=bob_headers)
    assert resp_bob.status_code == 200
    bob_items = {it["id"]: it for it in resp_bob.json()}

    assert bob_items[item_for_bob.id]["is_recipient"] is True
    assert (
        "available_quantity" not in bob_items[item_for_bob.id]
        or bob_items[item_for_bob.id].get("available_quantity") is None
    )

    assert bob_items[item_for_alice.id]["is_recipient"] is False
    assert bob_items[item_for_alice.id]["available_quantity"] == 1

    # Alice views items:
    # - Alice is NOT recipient of Item 1 -> CAN see reservation info (0 available)
    # - Alice is recipient of Item 2 -> must NOT see reservation info
    resp_alice = client.get(f"/api/wishlists/{wl_id}/items", headers=alice_headers)
    assert resp_alice.status_code == 200
    alice_items = {it["id"]: it for it in resp_alice.json()}

    assert alice_items[item_for_bob.id]["is_recipient"] is False
    assert alice_items[item_for_bob.id]["available_quantity"] == 0

    assert alice_items[item_for_alice.id]["is_recipient"] is True
    assert (
        "available_quantity" not in alice_items[item_for_alice.id]
        or alice_items[item_for_alice.id].get("available_quantity") is None
    )


# ============================================================================
# 4. Update & Reduction Lock Invariant (PATCH /api/wishlists/{wishlist_id}/items/{item_id})
# ============================================================================


def test_update_wish_item_valid_fields(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """PATCH /api/wishlists/{wishlist_id}/items/{item_id} updates allowed fields."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice")

    resp_wl = client.post("/api/wishlists", json={"name": "Alice's List"}, headers=owner_headers)
    wl_id = resp_wl.json()["id"]

    item = asyncio.run(
        service.add_wish_item(
            wishlist_id=wl_id,
            actor=owner,
            title="Initial Title",
            quantity=2,
            price=1000,
        )
    )

    patch_payload = {
        "title": "Updated Title",
        "price": 2500,
        "quantity": 5,
        "description": "Updated description",
    }
    resp_patch = client.patch(
        f"/api/wishlists/{wl_id}/items/{item.id}",
        json=patch_payload,
        headers=owner_headers,
    )
    assert resp_patch.status_code == 200
    data = resp_patch.json()
    assert data["title"] == "Updated Title"
    assert data["price"] == 2500
    assert data["quantity"] == 5
    assert data["description"] == "Updated description"


def test_update_wish_item_reduction_lock_violation(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Reduction Lock Invariant: Cannot reduce quantity below locked
    (reserved + received) amount.
    """
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    gifter = make_user(303, "Dana")
    owner_headers = auth_header(sessions, 101, "Alice")

    resp_wl = client.post("/api/wishlists", json={"name": "Party List"}, headers=owner_headers)
    wl_id = resp_wl.json()["id"]

    # Create item with quantity 5
    item = asyncio.run(
        service.add_wish_item(
            wishlist_id=wl_id,
            actor=owner,
            title="Wine Glasses",
            quantity=5,
        )
    )

    # Gifter reserves 3 units
    asyncio.run(service.create_reservation(item_id=item.id, user=gifter, quantity=3))

    # Owner attempts to reduce quantity to 2 (below 3 locked) -> 409 Conflict
    resp_fail = client.patch(
        f"/api/wishlists/{wl_id}/items/{item.id}",
        json={"quantity": 2},
        headers=owner_headers,
    )
    assert resp_fail.status_code == 409

    # Owner sets quantity to exactly 3 -> succeeds (200 OK)
    resp_ok_boundary = client.patch(
        f"/api/wishlists/{wl_id}/items/{item.id}",
        json={"quantity": 3},
        headers=owner_headers,
    )
    assert resp_ok_boundary.status_code == 200
    assert resp_ok_boundary.json()["quantity"] == 3

    # Owner increases quantity to 10 -> succeeds (200 OK)
    resp_ok_increase = client.patch(
        f"/api/wishlists/{wl_id}/items/{item.id}",
        json={"quantity": 10},
        headers=owner_headers,
    )
    assert resp_ok_increase.status_code == 200
    assert resp_ok_increase.json()["quantity"] == 10


# ============================================================================
# 5. Reordering Permutation Integrity (PUT /api/wishlists/{wishlist_id}/items/reorder)
# ============================================================================


def test_reorder_items_success(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """PUT /api/wishlists/{wishlist_id}/items/reorder updates display_order for all active items."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice")

    resp_wl = client.post("/api/wishlists", json={"name": "Reorder List"}, headers=owner_headers)
    wl_id = resp_wl.json()["id"]

    item1 = asyncio.run(service.add_wish_item(wishlist_id=wl_id, actor=owner, title="Item 1"))
    item2 = asyncio.run(service.add_wish_item(wishlist_id=wl_id, actor=owner, title="Item 2"))
    item3 = asyncio.run(service.add_wish_item(wishlist_id=wl_id, actor=owner, title="Item 3"))

    # Initial order is [item1, item2, item3]
    # Reorder to [item3, item1, item2]
    new_order = [item3.id, item1.id, item2.id]
    resp_reorder = client.put(
        f"/api/wishlists/{wl_id}/items/reorder",
        json={"item_ids": new_order},
        headers=owner_headers,
    )
    assert resp_reorder.status_code == 200

    # Subsequent GET returns items in the newly specified order
    resp_get = client.get(f"/api/wishlists/{wl_id}/items", headers=owner_headers)
    assert resp_get.status_code == 200
    returned_ids = [it["id"] for it in resp_get.json()]
    assert returned_ids == new_order
    returned_orders = [it["display_order"] for it in resp_get.json()]
    assert returned_orders == [0, 1, 2]


def test_reorder_items_validation_errors(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Reordering rejects incomplete list, duplicate IDs, or IDs from other wishlists with 400."""
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice")

    # List 1
    resp_wl1 = client.post("/api/wishlists", json={"name": "List 1"}, headers=owner_headers)
    wl1_id = resp_wl1.json()["id"]
    item_a = asyncio.run(service.add_wish_item(wishlist_id=wl1_id, actor=owner, title="Item A"))
    item_b = asyncio.run(service.add_wish_item(wishlist_id=wl1_id, actor=owner, title="Item B"))
    _item_c = asyncio.run(service.add_wish_item(wishlist_id=wl1_id, actor=owner, title="Item C"))

    # List 2
    resp_wl2 = client.post("/api/wishlists", json={"name": "List 2"}, headers=owner_headers)
    wl2_id = resp_wl2.json()["id"]
    foreign_item = asyncio.run(
        service.add_wish_item(wishlist_id=wl2_id, actor=owner, title="Foreign Item")
    )

    # 1. Incomplete list (missing item_c) -> 400 Bad Request
    resp_incomplete = client.put(
        f"/api/wishlists/{wl1_id}/items/reorder",
        json={"item_ids": [item_a.id, item_b.id]},
        headers=owner_headers,
    )
    assert resp_incomplete.status_code == 400

    # 2. Duplicate IDs -> 400 or 422
    resp_dup = client.put(
        f"/api/wishlists/{wl1_id}/items/reorder",
        json={"item_ids": [item_a.id, item_a.id, item_b.id]},
        headers=owner_headers,
    )
    assert resp_dup.status_code in {400, 422}

    # 3. Foreign item ID belonging to another wishlist -> 400 Bad Request
    resp_foreign = client.put(
        f"/api/wishlists/{wl1_id}/items/reorder",
        json={"item_ids": [item_a.id, item_b.id, foreign_item.id]},
        headers=owner_headers,
    )
    assert resp_foreign.status_code == 400

    # 4. Non-existent item ID -> 400 Bad Request
    resp_nonexistent = client.put(
        f"/api/wishlists/{wl1_id}/items/reorder",
        json={"item_ids": [item_a.id, item_b.id, 999999]},
        headers=owner_headers,
    )
    assert resp_nonexistent.status_code == 400


# ============================================================================
# 6. Safe Archiving & Restore Lifecycle
# ============================================================================


def test_safe_archive_preserves_reservations_and_hides_from_active_list(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Safe Archive Invariant: Archiving hides item from active GET,
    preserves active reservations, blocks new reservations.
    """
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    gifter = make_user(303, "Dana")
    owner_headers = auth_header(sessions, 101, "Alice")

    resp_wl = client.post(
        "/api/wishlists", json={"name": "Archive Test List"}, headers=owner_headers
    )
    wl_id = resp_wl.json()["id"]

    # Create item with quantity 2
    item = asyncio.run(
        service.add_wish_item(
            wishlist_id=wl_id,
            actor=owner,
            title="Collectible Watch",
            quantity=2,
        )
    )

    # Dana reserves 1 unit
    asyncio.run(service.create_reservation(item_id=item.id, user=gifter, quantity=1))

    # Archive the item
    resp_archive = client.post(
        f"/api/wishlists/{wl_id}/items/{item.id}/archive",
        headers=owner_headers,
    )
    assert resp_archive.status_code == 200
    assert resp_archive.json()["is_archived"] is True

    # 1. Active items list does NOT include archived item
    resp_active = client.get(f"/api/wishlists/{wl_id}/items", headers=owner_headers)
    assert resp_active.status_code == 200
    active_ids = [it["id"] for it in resp_active.json()]
    assert item.id not in active_ids

    # 2. Querying with include_archived=true DOES include archived item
    resp_all = client.get(
        f"/api/wishlists/{wl_id}/items?include_archived=true", headers=owner_headers
    )
    assert resp_all.status_code == 200
    all_ids = [it["id"] for it in resp_all.json()]
    assert item.id in all_ids

    # 3. Gifter's reservation is preserved in domain service
    summary = asyncio.run(service.get_user_reservations(user_id=303))
    assert len(summary) >= 1
    assert any(r.wish_item_id == item.id for r in summary)

    # 4. Attempting to create new reservation on archived item is blocked
    with pytest.raises(WishlistArchivedError):
        asyncio.run(service.create_reservation(item_id=item.id, user=gifter, quantity=1))


def test_restore_item_appends_to_end_of_active_order(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
) -> None:
    """Restoring an archived item brings it back with display_order placed
    at the end of active items.
    """
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner = make_user(101, "Alice")
    owner_headers = auth_header(sessions, 101, "Alice")

    resp_wl = client.post(
        "/api/wishlists", json={"name": "Restore Test List"}, headers=owner_headers
    )
    wl_id = resp_wl.json()["id"]

    # Create item A and item B
    item_a = asyncio.run(service.add_wish_item(wishlist_id=wl_id, actor=owner, title="Item A"))
    item_b = asyncio.run(service.add_wish_item(wishlist_id=wl_id, actor=owner, title="Item B"))

    # Archive item A
    resp_arch = client.post(
        f"/api/wishlists/{wl_id}/items/{item_a.id}/archive",
        headers=owner_headers,
    )
    assert resp_arch.status_code == 200

    # Create item C while item A is archived
    item_c = asyncio.run(service.add_wish_item(wishlist_id=wl_id, actor=owner, title="Item C"))

    # Restore item A
    resp_restore = client.post(
        f"/api/wishlists/{wl_id}/items/{item_a.id}/restore",
        headers=owner_headers,
    )
    assert resp_restore.status_code == 200
    assert resp_restore.json()["is_archived"] is False

    # Check active list order: item B, item C, and restored item A at the end
    resp_active = client.get(f"/api/wishlists/{wl_id}/items", headers=owner_headers)
    assert resp_active.status_code == 200
    active_items = resp_active.json()
    active_ids = [it["id"] for it in active_items]
    assert active_ids == [item_b.id, item_c.id, item_a.id]


# ============================================================================
# 8. Observability & Structured Logging
# ============================================================================


def test_item_lifecycle_observability_events(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify structured logging for item_created, item_updated, items_reordered,
    item_archived, and item_restored.
    """
    client, sessions, _ = test_app
    owner_headers = auth_header(sessions, 501, "ObsOwner")

    # Create wishlist
    resp_wl = client.post("/api/wishlists", json={"name": "Obs List"}, headers=owner_headers)
    assert resp_wl.status_code == 201
    wl_id = resp_wl.json()["id"]

    # 1. item_created: wishlist_id, item_id, actor_id, quantity, display_order, has_recipient
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        caplog.clear()
        resp_item1 = client.post(
            f"/api/wishlists/{wl_id}/items",
            json={"title": "Item 1", "quantity": 2},
            headers=owner_headers,
        )
        assert resp_item1.status_code == 201
        item1_id = resp_item1.json()["id"]

    created_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "item_created"
    ]
    assert len(created_records) == 1
    rec1 = created_records[0]
    assert getattr(rec1, "wishlist_id", None) == wl_id
    assert getattr(rec1, "item_id", None) == item1_id
    assert getattr(rec1, "actor_id", None) == 501
    assert getattr(rec1, "quantity", None) == 2
    assert getattr(rec1, "display_order", None) == 0
    assert getattr(rec1, "has_recipient", None) is False

    # Create item 2 with recipient_name
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        caplog.clear()
        resp_item2 = client.post(
            f"/api/wishlists/{wl_id}/items",
            json={"title": "Item 2", "quantity": 1, "recipient_name": "Friend"},
            headers=owner_headers,
        )
        assert resp_item2.status_code == 201
        item2_id = resp_item2.json()["id"]

    rec2 = [
        r
        for r in caplog.records
        if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "item_created"
    ][0]
    assert getattr(rec2, "has_recipient", None) is True

    # 2. item_updated: wishlist_id, item_id, actor_id, updated_fields
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        caplog.clear()
        resp_up = client.patch(
            f"/api/wishlists/{wl_id}/items/{item1_id}",
            json={"title": "Updated Item 1", "price": 1000},
            headers=owner_headers,
        )
        assert resp_up.status_code == 200

    updated_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "item_updated"
    ]
    assert len(updated_records) == 1
    rec_up = updated_records[0]
    assert getattr(rec_up, "wishlist_id", None) == wl_id
    assert getattr(rec_up, "item_id", None) == item1_id
    assert getattr(rec_up, "actor_id", None) == 501
    assert "price" in getattr(rec_up, "updated_fields", [])
    assert "title" in getattr(rec_up, "updated_fields", [])

    # 3. items_reordered: wishlist_id, actor_id, item_count
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        caplog.clear()
        resp_reorder = client.put(
            f"/api/wishlists/{wl_id}/items/reorder",
            json={"item_ids": [item2_id, item1_id]},
            headers=owner_headers,
        )
        assert resp_reorder.status_code == 200

    reorder_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "items_reordered"
    ]
    assert len(reorder_records) == 1
    rec_reorder = reorder_records[0]
    assert getattr(rec_reorder, "wishlist_id", None) == wl_id
    assert getattr(rec_reorder, "actor_id", None) == 501
    assert getattr(rec_reorder, "item_count", None) == 2

    # 4. item_archived: wishlist_id, item_id, actor_id, active_reservations_count
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        caplog.clear()
        resp_arch = client.post(
            f"/api/wishlists/{wl_id}/items/{item1_id}/archive",
            headers=owner_headers,
        )
        assert resp_arch.status_code == 200

    arch_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "item_archived"
    ]
    assert len(arch_records) == 1
    rec_arch = arch_records[0]
    assert getattr(rec_arch, "wishlist_id", None) == wl_id
    assert getattr(rec_arch, "item_id", None) == item1_id
    assert getattr(rec_arch, "actor_id", None) == 501
    assert getattr(rec_arch, "active_reservations_count", None) == 0

    # 5. item_restored: wishlist_id, item_id, actor_id, display_order
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists"):
        caplog.clear()
        resp_res = client.post(
            f"/api/wishlists/{wl_id}/items/{item1_id}/restore",
            headers=owner_headers,
        )
        assert resp_res.status_code == 200

    res_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "item_restored"
    ]
    assert len(res_records) == 1
    rec_res = res_records[0]
    assert getattr(rec_res, "wishlist_id", None) == wl_id
    assert getattr(rec_res, "item_id", None) == item1_id
    assert getattr(rec_res, "actor_id", None) == 501
    assert getattr(rec_res, "display_order", None) is not None


def test_item_rejection_and_access_denied_observability_events(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify structured logging for item_quantity_reduction_rejected,
    item_reorder_invalid, and item_access_denied.
    """
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner_headers = auth_header(sessions, 601, "Alice")
    stranger_headers = auth_header(sessions, 701, "Stranger")
    gifter = make_user(801, "Gifter")

    resp_wl = client.post("/api/wishlists", json={"name": "Rejections List"}, headers=owner_headers)
    wl_id = resp_wl.json()["id"]

    resp_item = client.post(
        f"/api/wishlists/{wl_id}/items",
        json={"title": "Widget", "quantity": 5},
        headers=owner_headers,
    )
    item_id = resp_item.json()["id"]

    # Lock 3 units via reservation
    asyncio.run(service.create_reservation(item_id=item_id, user=gifter, quantity=3))

    # 1. item_quantity_reduction_rejected:
    # wishlist_id, item_id, actor_id, requested_quantity, locked_quantity, reason
    with caplog.at_level(logging.WARNING, logger="wishenka.wishlists"):
        caplog.clear()
        resp_red = client.patch(
            f"/api/wishlists/{wl_id}/items/{item_id}",
            json={"quantity": 2},
            headers=owner_headers,
        )
        assert resp_red.status_code == 409

    red_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.wishlists"
        and getattr(r, "event", None) == "item_quantity_reduction_rejected"
    ]
    assert len(red_records) == 1
    rec_red = red_records[0]
    assert getattr(rec_red, "wishlist_id", None) == wl_id
    assert getattr(rec_red, "item_id", None) == item_id
    assert getattr(rec_red, "actor_id", None) == 601
    assert getattr(rec_red, "requested_quantity", None) == 2
    assert getattr(rec_red, "locked_quantity", None) == 3
    assert getattr(rec_red, "reason", None) is not None

    # 2. item_reorder_invalid: wishlist_id, actor_id, reason
    with caplog.at_level(logging.WARNING, logger="wishenka.wishlists"):
        caplog.clear()
        resp_reord = client.put(
            f"/api/wishlists/{wl_id}/items/reorder",
            json={"item_ids": [item_id, item_id]},  # duplicate
            headers=owner_headers,
        )
        assert resp_reord.status_code == 400

    reord_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "item_reorder_invalid"
    ]
    assert len(reord_records) == 1
    rec_reord = reord_records[0]
    assert getattr(rec_reord, "wishlist_id", None) == wl_id
    assert getattr(rec_reord, "actor_id", None) == 601
    assert "Duplicate" in getattr(rec_reord, "reason", "")

    # 3. item_access_denied: wishlist_id, actor_id, action, role
    with caplog.at_level(logging.WARNING, logger="wishenka.wishlists"):
        caplog.clear()
        resp_denied = client.post(
            f"/api/wishlists/{wl_id}/items",
            json={"title": "Hacked Item"},
            headers=stranger_headers,
        )
        assert resp_denied.status_code == 403

    denied_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.wishlists" and getattr(r, "event", None) == "item_access_denied"
    ]
    assert len(denied_records) == 1
    rec_denied = denied_records[0]
    assert getattr(rec_denied, "wishlist_id", None) == wl_id
    assert getattr(rec_denied, "actor_id", None) == 701
    assert getattr(rec_denied, "action", None) == "add_item"
    assert getattr(rec_denied, "role", None) is None


def test_item_observability_privacy_invariants_no_tokens_or_auth_data(
    test_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify privacy invariants: NO capability tokens (public_token, invite_token)
    and NO session auth data in any log messages or structured extras.
    """
    client, sessions, app = test_app
    service: WishlistService = app.state.domain_service
    owner_headers = auth_header(sessions, 901, "PrivacyOwner")

    # Create wishlist and inspect tokens
    resp_wl = client.post("/api/wishlists", json={"name": "Privacy List"}, headers=owner_headers)
    wl_id = resp_wl.json()["id"]

    wl = asyncio.run(service.get_wishlist_by_id(wl_id))
    public_token = wl.public_token
    invite_token = wl.invite_token
    assert len(public_token) > 0
    assert len(invite_token) > 0

    with caplog.at_level(logging.DEBUG):
        caplog.clear()

        # Execute full CRUD suite
        resp_add = client.post(
            f"/api/wishlists/{wl_id}/items",
            json={"title": "Secret Gift", "quantity": 3},
            headers=owner_headers,
        )
        item_id = resp_add.json()["id"]

        client.patch(
            f"/api/wishlists/{wl_id}/items/{item_id}",
            json={"title": "Renamed Secret Gift"},
            headers=owner_headers,
        )
        client.put(
            f"/api/wishlists/{wl_id}/items/reorder",
            json={"item_ids": [item_id]},
            headers=owner_headers,
        )
        client.post(f"/api/wishlists/{wl_id}/items/{item_id}/archive", headers=owner_headers)
        client.post(f"/api/wishlists/{wl_id}/items/{item_id}/restore", headers=owner_headers)

    # Invariant assertion: neither public_token nor invite_token nor session secret appear
    for record in caplog.records:
        msg = record.getMessage()
        assert public_token not in msg, f"public_token leaked in log: {msg}"
        assert invite_token not in msg, f"invite_token leaked in log: {msg}"
        assert "wish-items-crud-test-secret" not in msg

        # Also inspect record.__dict__
        for key, val in record.__dict__.items():
            if isinstance(val, str):
                assert public_token not in val, f"public_token leaked in record.{key}: {val}"
                assert invite_token not in val, f"invite_token leaked in record.{key}: {val}"
