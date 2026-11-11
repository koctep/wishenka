# Wishlists Domain: Roles, Permissions, Lifecycle, and Sharing

## Overview

The `wishenka.wishlists` module implements the core domain logic for wishlists in the
**Wishlist Service («Вишенка»)** Telegram Mini App.

It manages personal and collaborative wishlists, enforces role-based access control
(Contextual RBAC/ABAC), coordinates lifecycle transitions, protects the crucial
**Surprise Invariant** (zero-leak projections of reservations), and provides cryptographically
secure sharing tokens.

```
+-----------------------------------------------------------------------------------------+
|                                Wishlist Aggregate Root                                  |
|  - id, owner_id, title, status (ACTIVE | ARCHIVED | DELETED)                            |
|  - format: PERSONAL | COLLABORATIVE  - time_type: ONGOING | EVENT                       |
|  - public_token (16B urlsafe)        - invite_token (24B urlsafe + TTL)                 |
+-----------------------------------------------------------------------------------------+
                    |                                                |
                    v 1..*                                           v 0..*
+---------------------------------------+       +-----------------------------------------+
|              WishItem                 |       |             WishlistMember              |
|  - id, wishlist_id, title, link       |       |  - user_id, role (OWNER|ADMIN|MEMBER)   |
|  - quantity, recipient_user_id        |       |  - joined_at                            |
+---------------------------------------+       +-----------------------------------------+
                    | 0..*
                    v
+---------------------------------------+
|             Reservation               |
|  - wish_item_id, user_id, quantity    |
|  - status: ACTIVE|COMPLETED|CANCELLED |
+---------------------------------------+
```

### Key Capabilities

1. **Contextual Role-Based Access Control**: Combines static wishlist roles (`Owner`, `Admin`,
   `Member`) with dynamic item-level recipient checks.
2. **Surprise Invariant (Zero-Leak Projection)**: Gift recipients are strictly prevented from
   viewing reservation counts, status, or gifter identities.
3. **Dual Sharing Token Architecture**: Separate, cryptographically secure tokens for public
   viewing (`public_token`) and collaborative onboarding (`invite_token`).
4. **Lifecycle Management**: Explicit state machine (`ACTIVE` <-> `ARCHIVED` -> `DELETED`)
   preventing mutation or reservation on archived and deleted wishlists.
5. **Structured Audit Logging**: Comprehensive security and operational event logging with
   zero leakage of sensitive raw tokens.

---

## HTTP API and persistent storage

The FastAPI wishlist routes in
[`wishenka.web.routes.wishlists`](../../wishenka/web/routes/wishlists.py) use the session
authentication described in [Authentication](auth.md). Authenticated routes require an active
session; the public route also accepts anonymous callers. A request with an invalid session may be
rejected by the optional authentication dependency.

- `POST /api/wishlists`: Authenticated user creates a list; returns 201.

- `GET /api/wishlists`: Lists the caller's active memberships. Set `include_archived=true` to
  include archived lists.

- `GET /api/wishlists/{id}`: Reads a list for a member, including archived lists.

- `PATCH /api/wishlists/{id}`: Owner or admin updates an active list.

- `POST /api/wishlists/{id}/archive`: Owner or admin archives an active list.

- `POST /api/wishlists/{id}/restore`: Owner or admin restores an archived list.

- `POST /api/wishlists/{id}/share/reset`: Owner or admin rotates the public link on an active list.

- `POST /api/wishlists/{id}/invite/reset`: Owner or admin rotates the collaborator invite token.

- `GET /api/wishlists/{id}/members`: Lists active members and their roles.

- `PATCH /api/wishlists/{id}/members/{user_id}/role`: Owner promotes or demotes a member.

- `DELETE /api/wishlists/{id}/members/{user_id}`: Owner or admin removes a member.

- `GET /api/invitations/preview`: Previews invitation details via `X-Invite-Token` header.

- `POST /api/invitations/accept`: Authenticated user joins wishlist via `X-Invite-Token` header.

- `GET /api/public/wishlists/{token}`: Reads the public projection, including archived lists.

- `GET /api/favorites`: Lists the caller's favorited wishlists in reverse-chronological order.

- `POST /api/favorites/{id}`: Adds a wishlist to caller's favorites (rejects self-favoriting).

- `DELETE /api/favorites/{id}`: Removes a wishlist from caller's favorites.

- `GET /api/history`: Lists up to 20 recently viewed wishlists in reverse-chronological order.

- `POST /api/history/{id}`: Records or updates a wishlist view event for caller.

- `DELETE /api/history`: Clears all viewing history for caller.

Create and patch accept a JSON object with optional `name`, `description`, `event_title`, and
`event_date`. The HTTP representation includes list details and items; member responses include
`role` and `members`, and owner/admin responses also include `share_token` and `invite_token`.
The public projection uses an explicit allowlist and omits membership, tokens and
reservation-derived fields. It is returned even when an authenticated caller uses the public URL.
Projections for `/api/favorites` and `/api/history` strictly enforce the Surprise Invariant: they
return sanitized list metadata with roles and omit all reservation records, item availability
counts, and buyer details.
Unknown, deleted or inaccessible lists return 404; operations incompatible with the archived
state return 409. Archive is read-only until restored. State-changing requests from browser
sessions are protected by CSRF tokens and origin validation — see [miniapp.md](miniapp.md).
There is no HTTP delete route in this API; domain soft deletion remains a separate operation.

A sharing token is a bearer capability. Rotation invalidates the old public link, and the persistent
issued-token registry prevents reuse. Do not put tokens in application logs, issue reports or
analytics. The application redacts public paths in request and Uvicorn access logs and sanitizes
storage exceptions. Configure reverse proxies and other infrastructure separately to avoid logging
capability URLs.

The legacy `WishlistService.get_wishlist_by_public_token` domain projection can expose gifter fields
for an anonymous caller. Use the HTTP public projection for anonymous reads; do not expose that
domain projection directly as a public response. Follow-up work is tracked in
[WISHENKA-63](https://pypost.atlassian.net/browse/WISHENKA-63).

### Storage and configuration

The application factory creates one `WishlistStore` and exposes a store-backed `WishlistService` as
`app.state.domain_service`. Use that service for application domain operations. A bare
`WishlistService()` is in-memory and independent; it is useful in tests but bypasses persistent app
state. The HTTP router uses the same store. For tests only, `app.state.wishlist_service` can
override the router's service.

`WISHENKA_DATABASE_URL` selects the SQLite database and defaults to
`sqlite+aiosqlite:///data/wishenka.db`. The application initializes the normalized relational
schema and WAL mode during lifespan startup, creates parent directories for a file database,
and disposes the engine at shutdown. `WISHENKA_SQLITE_DB_PATH` is a separate setting and does not
configure this store. All workers must point to the same database file to share state. The store
applies a five-second SQLite busy timeout (`busy_timeout = 5000`) and serializes each mutation with
`BEGIN IMMEDIATE`.

As implemented in [WISHENKA-48](https://pypost.atlassian.net/browse/WISHENKA-48), persistence uses
a fully normalized relational schema (`wl_lists`, `wl_members`, `wl_items`, `wl_reservations`,
`wl_favorites`, `wl_view_history`, `wl_tokens`, `wl_invite_tokens`, `wl_counters`) mapped via
SQLAlchemy 2.0 declarative models and queried through `WishlistRepository`. Destructive prototype
mass table truncations (`DELETE FROM <table>`) are replaced with snapshot diffing and row-level
mutations (`UPDATE`, `INSERT`, `DELETE WHERE id = :id`). See
[Persistence Architecture](#persistence-architecture-sqlite-wal--repositories) below for details.

If startup reports `Unable to initialize wishlist storage`, verify the database URL, directory
permissions and SQLite availability. A generic `Wishlist storage operation failed` indicates a
sanitized database failure; inspect storage health and contention without logging SQL parameters or
tokens. If a shared link returns 404, check whether it was rotated or the list was deleted; request
a new link from an owner or admin. A 409 on modification indicates an archived list or an invalid
state transition.

## Architecture & Domain Models

The domain models are defined in [`wishenka.wishlists.models`](../../wishenka/wishlists/models.py)
and pure access policies in [`wishenka.wishlists.policy`](../../wishenka/wishlists/policy.py).

### Enumerations

| Enum | Values | Description |
| --- | --- | --- |
| `WishlistRole` | `owner`, `admin`, `member` | Roles of collaborators in a wishlist. |
| `WishlistStatus` | `active`, `archived`, `deleted` | Lifecycle state of the wishlist aggregate. |
| `WishlistFormat` | `personal`, `collaborative` | Format: single owner vs collaborative members. |
| `WishlistTimeType` | `ongoing`, `event` | Temporal classification (event vs ongoing). |
| `ReservationStatus` | `active`, `completed`, `cancelled` | State of a gifter's item reservation. |

### Domain Models

- **`Wishlist`**: Aggregate root entity holding metadata, tokens, member list, and items.
- **`WishlistMember`**: Association between user (`user_id`) and wishlist with `WishlistRole`.
- **`WishlistFavorite`**: Association tracking a user's favorite (`user_id`, `wishlist_id`).
- **`ViewHistoryEntry`**: Record of a wishlist view event (`id`, `user_id`, `wishlist_id`).
- **`WishItem`**: An item desired by a recipient, with quantity and optional price.
- **`Reservation`**: Active allocation of a `WishItem`'s quantity created by a gifter.

### RBAC Policy: `WishlistAccessPolicy` & `UserWishlistContext`

Access decisions are evaluated purely through
`WishlistAccessPolicy.resolve_context(user, wishlist)`, returning a frozen `UserWishlistContext`:

```python
@dataclass(frozen=True)
class UserWishlistContext:
    is_owner: bool
    is_admin: bool
    is_member: bool
    role: WishlistRole | None
```

#### Privilege Matrix

| Action | Owner | Admin | Member | Gifter / Public Viewer |
| --- | :---: | :---: | :---: | :---: |
| View active wishlist | Yes | Yes | Yes | Yes (via public token) |
| Edit wishlist title / metadata | Yes | Yes | No | No |
| Add / Edit wish items | Yes | Yes | Yes | No |
| Invite / Remove regular members | Yes | Yes | No | No |
| Change member role (promote/demote) | Yes | No | No | No |
| Transfer ownership | Yes | No | No | No |
| Archive / Unarchive wishlist | Yes | Yes | No | No |
| Delete wishlist (soft-delete) | Yes | No | No | No |
| Regenerate sharing tokens | Yes | Yes | No | No |
| Reserve item (non-recipient) | Yes | Yes | Yes | Yes |
| Reserve item (as recipient) | **No** | **No** | **No** | **No** |

*Note: Item recipients are strictly prohibited from reserving items designated for themselves.*

#### Role Precedence & Favorite Evaluation

Role assignment in API projections and UI badge rendering follows a strict four-level precedence:

```text
owner > admin > member > favorite
```

- **Collaborator Precedence**: Active collaborative membership (`owner`, `admin`, `member`)
  strictly takes precedence over `favorite` status. If an admin or member also favorites a wishlist,
  the system retains their operational collaborator role (`admin` or `member`) in all projections.
- **Pure Favorites**: If the user holds no collaborator membership on the wishlist but has
  favorited it, the projection assigns `role: "favorite"` and sets `is_favorite: true`.
- **Policy Rule**: `WishlistAccessPolicy.can_favorite(user, wishlist)` controls favoriting
  eligibility: it requires an authenticated user (`user is not None`), rejects soft-deleted lists,
  and enforces the self-favoriting guard (`wishlist.owner_id != user.telegram_id`).

### Surprise Invariant: Zero-Leak Projection Design

The **Surprise Invariant** guarantees that the recipient of a gift can never discover whether
an item has been booked, how many units remain, or who reserved it.

#### Enforcement Mechanism

1. **Policy Check**: `WishlistAccessPolicy.is_recipient(user, item)`:
   - Returns `True` if `item.recipient_user_id == user.telegram_id`.
   - On personal wishlists without an explicit item recipient, defaults to the wishlist owner
     (`wishlist.owner_id == user.telegram_id`).
   - If an item specifies a non-user external recipient (e.g. `recipient_name="Бабушка Нина"`),
     registered collaborators are not recipients.
2. **DTO Projection**:
   - **`WishItemRecipientViewDTO`**: Returned when `is_recipient` is `True`. All reservation
     details (`reservations`, `available_quantity`, `is_fully_reserved`, `is_reserved_by_me`,
     `my_reserved_quantity`) are omitted from the schema.
   - **`WishItemGifterViewDTO`**: Returned when `is_recipient` is `False`. Includes computed
     availability (`available_quantity`), booking status, and whether calling user holds a booking.
3. **Self-Reservation Guard**: Any attempt by a recipient to invoke `create_reservation` raises
   `SelfReservationError` and emits a warning audit log.

---

## Usage / API

The `WishlistService` in
[`wishenka.wishlists.service`](../../wishenka/wishlists/service.py)
provides the primary asynchronous application interface.

### Service Methods

#### `create_wishlist`

Creates a new personal wishlist with secure random tokens.

```python
async def create_wishlist(
    self,
    owner: AuthenticatedUser,
    title: str,
    description: str | None = None,
    event_title: str | None = None,
    event_date: datetime | None = None,
    invite_token_expires_in: timedelta | None = None,
) -> Wishlist
```

- **Parameters**:
  - `owner`: Authenticated owner user.
  - `title`: Title of the wishlist.
  - `description`: Optional text description.
  - `event_title`: Optional event name (e.g. "День рождения").
  - `event_date`: Optional event timestamp.
  - `invite_token_expires_in`: TTL for the invite token (defaults to 7 days).
- **Returns**: Newly created `Wishlist` aggregate.

#### `get_wishlist_view`

Generates a role-aware projection (`WishlistDetailViewDTO`) tailored to the caller's context.

```python
async def get_wishlist_view(
    self,
    wishlist_id: int,
    user: AuthenticatedUser | None,
) -> WishlistDetailViewDTO
```

- **Raises**: `WishlistNotFoundError`, `WishlistDeletedError`.
- **Surprise Invariant**: For each item, selects `WishItemRecipientViewDTO` if caller is recipient,
  or `WishItemGifterViewDTO` otherwise.
- **Token Security**: The `invite_token` is exposed in the DTO only to `Owner` and `Admin` members;
  public viewers and regular members receive `invite_token = None`.

#### `add_member` / `change_member_role`

Adds a collaborator or updates their role.

```python
async def add_member(
    self,
    wishlist_id: int,
    actor: AuthenticatedUser,
    user_id: int,
    role: WishlistRole = WishlistRole.MEMBER,
) -> WishlistMember
```

- **Permissions**: `Owner` and `Admin` can add `MEMBER`s. Only `Owner` can assign or change `ADMIN`
  role (`can_change_member_role`).
- **Raises**: `PermissionDeniedError`, `WishlistArchivedError`, `WishlistDeletedError`.

#### `remove_member`

Removes a collaborator from the wishlist.

```python
async def remove_member(
    self,
    wishlist_id: int,
    actor: AuthenticatedUser,
    user_id: int,
) -> None
```

- **Permissions**: `Owner` can remove any member; `Admin` can remove regular `MEMBER`s; any member
  can remove themselves.

#### `join_by_invite`

Allows an authenticated user to join a collaborative wishlist using a valid invite token.

```python
async def join_by_invite(
    self,
    invite_token: str,
    user: AuthenticatedUser,
) -> WishlistMember
```

- **Raises**: `InvalidInviteTokenError` if token is non-existent, revoked, or expired.
- Automatically transitions wishlist format to `WishlistFormat.COLLABORATIVE`.

#### `regenerate_public_token` & `regenerate_invite_token`

Rotates sharing tokens when links need to be revoked or re-issued.

```python
async def regenerate_public_token(
    self,
    wishlist_id: int,
    actor: AuthenticatedUser,
) -> str

async def regenerate_invite_token(
    self,
    wishlist_id: int,
    actor: AuthenticatedUser,
    expires_in: timedelta = timedelta(days=7),
) -> str
```

- **Permissions**: `Owner` and `Admin`.
- **Returns**: The new raw token string.

#### `archive_wishlist` & `restore_wishlist` (`unarchive_wishlist`)

Toggles the wishlist between `ACTIVE` and `ARCHIVED` status.

```python
async def archive_wishlist(
    self,
    wishlist_id: int,
    actor: AuthenticatedUser,
) -> Wishlist

async def unarchive_wishlist(  # restore operation
    self,
    wishlist_id: int,
    actor: AuthenticatedUser,
) -> Wishlist
```

- **Permissions**: `Owner` and `Admin`.
- While `ARCHIVED`, adding items, editing metadata, and booking reservations are rejected with
  `WishlistArchivedError`.

#### `delete_wishlist`

Performs a soft delete of the wishlist (`WishlistStatus.DELETED`).

```python
async def delete_wishlist(
    self,
    wishlist_id: int,
    actor: AuthenticatedUser,
) -> Wishlist
```

- **Permissions**: Solely the `Owner`.
- Cancels all active reservations and invalidates tokens.

#### `create_reservation`

Reserves one or more units of an item.

```python
async def create_reservation(
    self,
    item_id: int,
    user: AuthenticatedUser,
    quantity: int = 1,
) -> Reservation
```

- **Surprise Invariant**: Raises `SelfReservationError` if caller is the item's recipient.
- **Overbooking Prevention**: Raises `InsufficientQuantityError` if `quantity > available_quantity`.
- **Status Guards**: Raises `WishlistArchivedError` if wishlist is archived.

#### `add_favorite` & `remove_favorite`

Adds or removes a wishlist from the user's favorites.

```python
async def add_favorite(
    self,
    user: AuthenticatedUser,
    wishlist_id: int,
) -> WishlistFavorite

async def remove_favorite(
    self,
    user: AuthenticatedUser,
    wishlist_id: int,
) -> None
```

- **Self-Favoriting Guard**: Raises `ValueError("Cannot favorite own wishlist")` if
  `wishlist.owner_id == user.telegram_id`.
- **Validation**: Raises `WishlistNotFoundError` if wishlist does not exist or has been deleted.
- **Idempotency**: Adding an existing favorite is an idempotent no-op.
- Synchronous `has_favorite(user_id, wishlist_id)` and async `is_favorite(user, wishlist_id)`
  allow quick lookups.

#### `list_favorites`

Lists favorited wishlists for an authenticated user.

```python
async def list_favorites(
    self,
    user: AuthenticatedUser,
) -> list[Wishlist]
```

- Returns active and archived wishlists favorited by the user, ordered reverse-chronologically by
  when they were added. Soft-deleted lists are automatically filtered out.

#### `record_view`

Records or updates a wishlist visit in the user's viewing history.

```python
async def record_view(
    self,
    user: AuthenticatedUser,
    wishlist_id: int,
) -> ViewHistoryEntry
```

- **Deduplication**: If the user previously viewed this wishlist, updates its `viewed_at` timestamp
  and moves it to the most recent position.
- **20-Entry Bound**: Enforces a strict 20-entry ceiling per user by pruning the oldest records
  whenever a 21st unique entry is recorded.
- **Validation**: Raises `WishlistNotFoundError` if the wishlist is non-existent or soft-deleted.

#### `get_history` & `clear_history`

Retrieves or clears the user's viewing history.

```python
async def get_history(
    self,
    user: AuthenticatedUser,
    limit: int = 20,
) -> list[tuple[Wishlist, datetime]]

async def clear_history(
    self,
    user: AuthenticatedUser,
) -> None
```

- `get_history`: Returns up to `limit` entries as `(Wishlist, datetime)` tuples in reverse
  chronological order of viewing. Excludes soft-deleted wishlists.
- `clear_history`: Removes all viewing history entries for the authenticated user.

---

## Persistence Architecture: SQLite WAL & Repositories

Wishenka stores wishlist aggregates in a fully normalized relational SQLite schema managed via
the SQLAlchemy 2.0 async engine (`sqlite+aiosqlite`). Prototype JSON blobs and destructive mass
table overwrites (`DELETE FROM <table>`) have been replaced with atomic, row-level persistence,
granular async queries, and relationship cascade deletion.

```
+-----------------------------------------------------------------------------------------+
|                        WishlistStore (Unit of Work Boundary)                           |
|  - Manages SQLite connection lifecycle, WAL mode, foreign keys, and busy timeout        |
|  - BEGIN IMMEDIATE write transaction serialization and TokenCollision retries          |
|  - Snapshot diffing: computes row-level INSERT / UPDATE / DELETE sets                   |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                    WishlistRepository (Granular Async SQL Operations)                   |
|  - Targeted queries: get_wishlist, get_by_public_token, get_by_invite_token, etc.      |
|  - Single-row mutations: upsert_wishlist, upsert_item, upsert_reservation, etc.         |
|  - Bidirectional entity converters: _row_to_wishlist, _row_to_member, _row_to_item      |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                   SQLAlchemy 2.0 Declarative Models (db_models.py)                      |
|  - Typed Mapped[...] columns, unique constraints, and foreign key cascades              |
|  - wl_lists, wl_members, wl_items, wl_reservations, wl_favorites, wl_view_history,    |
|    wl_tokens, wl_invite_tokens, wl_counters                                            |
+-----------------------------------------------------------------------------------------+
```

### 1. Normalized Relational Database Schema

The persistence layer organizes domain entities into dedicated relational tables with explicit
data types, foreign keys, unique constraints, and indexes.

#### Schema DDL Specifications

```sql
-- 1. Wishlist Aggregate Root
CREATE TABLE IF NOT EXISTS wl_lists (
    id INTEGER PRIMARY KEY,
    owner_id INTEGER NOT NULL,
    owner_name TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    description TEXT,
    event_title TEXT,
    event_date TEXT,
    is_collaborative INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    public_token TEXT NOT NULL,
    invite_token TEXT NOT NULL,
    invite_token_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wl_lists_owner ON wl_lists(owner_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wl_lists_public_token ON wl_lists(public_token);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wl_lists_invite_token ON wl_lists(invite_token);
CREATE INDEX IF NOT EXISTS idx_wl_lists_status ON wl_lists(status);

-- 2. Collaborative Members
CREATE TABLE IF NOT EXISTS wl_members (
    id INTEGER PRIMARY KEY,
    wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    joined_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wl_members_unique ON wl_members(wishlist_id, user_id);
CREATE INDEX IF NOT EXISTS idx_wl_members_user ON wl_members(user_id);

-- 3. Wishlist Items
CREATE TABLE IF NOT EXISTS wl_items (
    id INTEGER PRIMARY KEY,
    wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
    recipient_user_id INTEGER,
    recipient_name TEXT,
    title TEXT NOT NULL,
    description TEXT,
    link TEXT,
    price INTEGER,
    currency TEXT NOT NULL DEFAULT 'RUB',
    quantity INTEGER NOT NULL DEFAULT 1,
    received_quantity INTEGER NOT NULL DEFAULT 0,
    image_url TEXT,
    store_name TEXT,
    store_icon_url TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',
    category TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wl_items_wishlist ON wl_items(wishlist_id);
CREATE INDEX IF NOT EXISTS idx_wl_items_recipient ON wl_items(recipient_user_id);

-- 4. Item Reservations
CREATE TABLE IF NOT EXISTS wl_reservations (
    id INTEGER PRIMARY KEY,
    wish_item_id INTEGER NOT NULL REFERENCES wl_items(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wl_reservations_item ON wl_reservations(wish_item_id);
CREATE INDEX IF NOT EXISTS idx_wl_reservations_user ON wl_reservations(user_id);
CREATE INDEX IF NOT EXISTS idx_wl_reservations_status ON wl_reservations(status);

-- 5. User Favorites
CREATE TABLE IF NOT EXISTS wl_favorites (
    user_id INTEGER NOT NULL,
    wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, wishlist_id)
);
CREATE INDEX IF NOT EXISTS idx_wl_favorites_user ON wl_favorites(user_id);

-- 6. User Viewing History
CREATE TABLE IF NOT EXISTS wl_view_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
    viewed_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS wl_view_history_user_wl
    ON wl_view_history(user_id, wishlist_id);
CREATE INDEX IF NOT EXISTS idx_wl_view_history_user_time
    ON wl_view_history(user_id, viewed_at DESC);

-- 7. Public Sharing Capability Token Registry
CREATE TABLE IF NOT EXISTS wl_tokens (
    token TEXT PRIMARY KEY,
    wishlist_id INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_wl_tokens_wishlist ON wl_tokens(wishlist_id, active);

-- 8. Collaborator Invite Capability Token Registry
CREATE TABLE IF NOT EXISTS wl_invite_tokens (
    token TEXT PRIMARY KEY
);

-- 9. Monotonic Sequence ID Counters
CREATE TABLE IF NOT EXISTS wl_counters (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
```

#### Foreign Key Constraints & Cascading Deletion
- Foreign key enforcement is enabled on every SQLite connection via `PRAGMA foreign_keys = ON`.
- Deleting a wishlist from `wl_lists` cascades (`ON DELETE CASCADE`) to:
  - All associated members in `wl_members`.
  - All contained items in `wl_items` (and subsequently all reservations in `wl_reservations`).
  - All user bookmark entries in `wl_favorites`.
  - All user viewing history records in `wl_view_history`.
- Deleting a wish item (`wl_items`) cascades to all its reservations (`wl_reservations`).

#### Unique Constraints & Indexing Strategy
- **Unique Indexes**:
  - `idx_wl_lists_public_token`: Prevents duplication across public sharing capability tokens.
  - `idx_wl_lists_invite_token`: Prevents duplication across collaborator invite tokens.
  - `idx_wl_members_unique` on `(wishlist_id, user_id)`: Enforces exactly one membership record
    per user per wishlist.
  - `wl_view_history_user_wl` on `(user_id, wishlist_id)`: Prevents duplicate viewing entries,
    allowing deduplication via:
    `INSERT ... ON CONFLICT DO UPDATE SET viewed_at = excluded.viewed_at`.
  - Primary key `(user_id, wishlist_id)` on `wl_favorites`: Guarantees single bookmark per list.
- **Lookup Indexes**:
  - `idx_wl_lists_owner` and `idx_wl_lists_status`: Accelerate owner dashboards and status filters.
  - `idx_wl_members_user`: Enables fast lookups of all collaborative wishlists for a user.
  - `idx_wl_items_wishlist` and `idx_wl_items_recipient`: Speed up queries by list and recipient.
  - `idx_wl_reservations_item`, `idx_wl_reservations_user`, `idx_wl_reservations_status`: Speed up
    reservation lookups, user reservation queries, and active booking counting.

### 2. SQLAlchemy 2.0 Declarative Models

Declarative models in
[`wishenka.wishlists.db_models`](../../wishenka/wishlists/db_models.py) map relational tables
to typed Python structures using SQLAlchemy 2.0 `Mapped` and `mapped_column` constructs:

- **`Base`**: Subclass of `sqlalchemy.orm.DeclarativeBase`.
- **`WishlistRow`**: Represents `wl_lists`. Configures bidirectional relationships with
  `cascade="all, delete-orphan"`:
  ```python
  members: Mapped[list["WishlistMemberRow"]] = relationship(
      back_populates="wishlist", cascade="all, delete-orphan"
  )
  items: Mapped[list["WishItemRow"]] = relationship(
      back_populates="wishlist", cascade="all, delete-orphan"
  )
  ```
- **`WishlistMemberRow`**: Represents `wl_members`. References `wl_lists.id` via foreign key
  `ForeignKey("wl_lists.id", ondelete="CASCADE")` and back-populates `members`.
- **`WishItemRow`**: Represents `wl_items`. References `wl_lists.id` and configures child cascade:
  ```python
  reservations: Mapped[list["ReservationRow"]] = relationship(
      back_populates="wish_item", cascade="all, delete-orphan"
  )
  ```
- **`ReservationRow`**: Represents `wl_reservations` with `ForeignKey(..., ondelete="CASCADE")`.
- **`WishlistFavoriteRow`**: Represents `wl_favorites` with composite key `(user_id, wishlist_id)`.
- **`ViewHistoryRow`**: Represents `wl_view_history` with autoincrement integer primary key `id`.
- **`WishlistTokenRow`** & **`InviteTokenRow`**: Represent capability registries `wl_tokens` and
  `wl_invite_tokens`.
- **`CounterRow`**: Represents `wl_counters` for monotonic sequence generation.

### 3. WishlistRepository: Granular Async Queries & Mutations

The `WishlistRepository` in
[`wishenka.wishlists.repository`](../../wishenka/wishlists/repository.py) provides isolated,
granular async operations over an active SQLAlchemy `AsyncConnection`.

#### Targeted Query Methods
- `get_wishlist(wishlist_id: int) -> Wishlist | None`: Loads a specific wishlist aggregate
  along with its active members, items, and item reservations in targeted parameter-bound queries
  (`WHERE id = :id` and `WHERE wish_item_id IN (...)`).
- `get_by_public_token(token: str) -> Wishlist | None`: O(1) indexed lookup by public capability.
- `get_by_invite_token(token: str) -> Wishlist | None`: O(1) indexed lookup by invite capability.
- `list_by_owner(owner_id: int) -> list[Wishlist]`: Indexed fetch of wishlists owned by user.
- `list_collaborative(user_id: int) -> list[Wishlist]`: Joined query on `wl_members` returning
  only collaborative lists where caller is an active member.
- `get_item(item_id: int) -> WishItem | None`: Single-item fetch with its reservations.
- `list_user_reservations(user_id: int) -> list[Reservation]`: Fetches active/purchased reservations
  created by the specified user.
- `list_favorites(user_id: int) -> list[WishlistFavorite]`: Ordered bookmarks for caller.
- `list_view_history(user_id: int, limit: int = 20) -> list[ViewHistoryEntry]`: Chronologically
  ordered history entries up to the bounded limit.

#### Row-Level Mutation Methods
- `upsert_wishlist(wishlist: Wishlist)`: Checks existence by ID and executes row-level `UPDATE`
  or `INSERT` without affecting any other wishlist rows.
- `delete_wishlist(wishlist_id: int)`: Executes `DELETE FROM wl_lists WHERE id = :id`. Engine
  foreign key cascade automatically cleans up child members, items, and reservations.
- `upsert_item(item: WishItem)`: Targeted `UPDATE` or `INSERT` for a single wish item row.
- `delete_item(item_id: int)`: Targeted `DELETE FROM wl_items WHERE id = :id`.
- `upsert_reservation(res: Reservation)`: Targeted `UPDATE` or `INSERT` for reservation rows.
- `delete_reservation(res_id: int)`: Targeted `DELETE FROM wl_reservations WHERE id = :id`.
- `upsert_favorite(fav)`: Uses `INSERT ... ON CONFLICT(user_id, wishlist_id) DO NOTHING`.
- `delete_favorite(user_id: int, wishlist_id: int)`: Targeted `DELETE FROM wl_favorites`.
- `record_view(entry)`: Uses `INSERT ... ON CONFLICT DO UPDATE SET viewed_at = excluded.viewed_at`.
- `clear_view_history(user_id: int)`: Deletes viewing history for a single user.

#### Entity Converters
Bidirectional entity converters decouple database row representations from pure domain dataclasses:
- `_row_to_wishlist(row: Row[Any]) -> Wishlist`
- `_row_to_member(row: Row[Any]) -> WishlistMember`
- `_row_to_item(row: Row[Any]) -> WishItem`
- `_row_to_reservation(row: Row[Any]) -> Reservation`
- Datetime conversions parse ISO strings to timezone-aware UTC `datetime` objects via `_parse_dt`
  and serialize them to ISO format via `_format_dt`.

### 4. Concurrency & Transaction Management

#### Elimination of Destructive Bulk Overwrites
The legacy prototype wiped all database tables on every write via `DELETE FROM <table>`. In the
relational architecture, `WishlistStore` coordinates atomic row-level persistence using
**snapshot diffing**:

1. **Snapshot Capture**: At transaction start, `_read()` reads current state and captures a
   lightweight `_StorageSnapshot` containing existing entity ID sets:
   ```python
   @dataclass
   class _StorageSnapshot:
       wishlists: set[int]
       members: set[int]
       items: set[int]
       reservations: set[int]
       favorites: set[tuple[int, int]]
       history_ids: set[int]
   ```
2. **Domain Execution**: The caller's business operation executes against `WishlistService`.
3. **Differential Persistence**: During `_write()`, the store compares post-operation service
   state with the initial snapshot:
   - Entities in service but not in snapshot: executed via single-row `INSERT`.
   - Entities in both snapshot and service: executed via single-row `UPDATE ... WHERE id = :id`.
   - Entities in snapshot but not in service: executed via single-row `DELETE ... WHERE id = :id`.
   - All other rows across unrelated wishlists remain completely untouched.

#### SQLite WAL Mode & Lock Primitives
- **WAL Journaling (`PRAGMA journal_mode = WAL`)**: Allows concurrent reads to proceed concurrently
  with active write transactions without blocking or lock contention.
- **Immediate Write Transactions (`BEGIN IMMEDIATE`)**: State mutations begin with `BEGIN IMMEDIATE`
  to acquire an SQLite write lock at the start of the transaction, eliminating mid-transaction
  upgrade deadlocks (`SQLITE_BUSY`).
- **Bounded Busy Timeout (`PRAGMA busy_timeout = 5000`)**: If SQLite encounters a transient write
  lock, it waits up to 5000 milliseconds before raising an operational error.
- **Capability Collision Retry**: If a concurrent worker or token generation collides with an
  existing capability token in `wl_tokens` or `wl_invite_tokens`, `WishlistStore.execute()`
  catches `TokenCollision` / `IntegrityError` and retries up to 5 times with newly generated
  cryptographic tokens.

### 5. Observability & Security Guarantees

#### Structured Persistence Logging Events
Database operations emit structured audit logs under the `wishenka.wishlists` logger:

| Event (`event`) | Level | Trigger | Key Extra Attributes |
| --- | :---: | --- | --- |
| `wishlist_store_read` | `INFO` | State read into service | `wishlists_count`, `items_count` |
| `wishlist_store_write` | `INFO` | Differential committed | `wishlists_count`, `items_count` |
| `wishlist_repo_mutation` | `INFO` | Repository mutation | `entity`, `operation`, `entity_id` |
| `wishlist_token_collision_retry` | `WARNING` | Collision retry | `attempt` |
| `wishlist_store_error` | `ERROR` | Database error | `event` |
| `wishlist_store_integrity_error` | `ERROR` | Constraint failure | `event` |

#### Zero Parameter & Token Leakage Guarantees
- **SQLAlchemy Parameter Redaction**: Engines are initialized with `hide_parameters=True`,
  ensuring that SQL parameters (including sharing tokens and private IDs) never appear in SQL
  exception traces or debug logs.
- **Driver Logging Redaction**: The low-level `aiosqlite` logger is explicitly configured to
  `logging.WARNING` (`logging.getLogger("aiosqlite").setLevel(logging.WARNING)`), suppressing
  aiosqlite DEBUG output that outputs raw parameter bindings.
- **Sanitized Domain Exceptions**: Database exceptions (`SQLAlchemyError`, `IntegrityError`) are
  caught at the `WishlistStore.execute()` boundary and sanitized into generic `RuntimeError`
  messages (`"Wishlist storage operation failed"`). Internal SQLite table names, SQL syntax,
  and tokens are strictly withheld from exception traces.

---

## Token Schemas & Security

Wishlists use two cryptographic token schemas generated via Python's `secrets.token_urlsafe`:

```
1. Public Sharing Token (Gifter Access)
   - Generation: secrets.token_urlsafe(16)
   - Entropy: 128 bits (~22 URL-safe characters)
   - Scope: Read-only access to the public wishlist projection
   - URL: https://t.me/WishenkaBot/app?startapp=w_<public_token>

2. Invite Token (Collaborator Onboarding)
   - Generation: secrets.token_urlsafe(24)
   - Entropy: 192 bits (~32 URL-safe characters)
   - Scope: Join as co-author with MEMBER role
   - Expiration: invite_token_expires_at (default TTL: 7 days)
   - URL: https://t.me/WishenkaBot/app?startapp=i_<invite_token>
```

---

## Configuration & Audit Logging

Structured logging is managed under the `wishenka.wishlists` logger namespace.

### Security Invariant

> [!IMPORTANT]
> **Zero Token Leakage**: Raw token values (`public_token`, `invite_token`) MUST NEVER appear
> in log messages or log `extra` fields. Auditing captures only resource identifiers
> (`wishlist_id`, `actor_id`, `user_id`).

### Audit Event Reference

| Event (`event`) | Level | Trigger | Key Attributes |
| --- | :---: | --- | --- |
| `wishlist_created` | `INFO` | New wishlist created | `wishlist_id`, `owner_id` |
| `wishlist_status_changed` | `INFO` | Status changed | `wishlist_id`, `to_status` |
| `member_joined` | `INFO` | Collaborator joined | `wishlist_id`, `user_id` |
| `member_role_assigned` | `INFO` | Role updated | `wishlist_id`, `role` |
| `member_removed` | `INFO` | Member removed | `wishlist_id`, `user_id` |
| `ownership_transferred` | `INFO` | Owner ceded control | `wishlist_id`, `new_owner_id` |
| `public_token_regenerated`| `INFO` | Public token rotated | `wishlist_id`, `actor_id` |
| `invite_token_regenerated`| `INFO` | Invite token rotated | `wishlist_id`, `actor_id` |
| `reservation_created` | `INFO` | Item booked | `wishlist_id`, `quantity` |
| `access_denied` | `WARNING` | Action blocked | `wishlist_id`, `action` |
| `surprise_invariant_violation_attempt` | `WARNING` | Self-booking blocked | `item_id` |
| `invalid_invite_token` | `WARNING` | Bad invite token | None (token withheld) |
| `favorites_listed` | `INFO` | Favorites fetched | `user_id`, `count` |
| `favorite_added` | `INFO` | Favorite added | `wishlist_id`, `user_id` |
| `favorite_removed` | `INFO` | Favorite removed | `wishlist_id`, `user_id` |
| `favorite_own_wishlist_denied` | `WARNING` | Self-favorite blocked | `wishlist_id`, `user_id` |
| `favorite_deleted_wishlist_denied` | `WARNING` | Deleted list blocked | `wishlist_id`, `user_id` |
| `view_history_listed` | `INFO` | History fetched | `user_id`, `count` |
| `view_history_recorded` | `INFO` | View recorded | `wishlist_id`, `user_id` |
| `view_history_cleared` | `INFO` | History cleared | `user_id` |
| `wishlist_store_read` | `INFO` | State read | `wishlists_count` |
| `wishlist_store_write` | `INFO` | Changes committed | `wishlists_count` |
| `wishlist_repo_mutation` | `INFO` | Repo mutation | `entity`, `operation` |

---

## Troubleshooting & Domain Exceptions

All domain exceptions inherit from `WishlistError` in
[`wishenka.wishlists.exceptions`](../../wishenka/wishlists/exceptions.py).

```
WishlistError
├── PermissionDeniedError
├── WishlistNotFoundError
├── WishlistArchivedError
├── WishlistDeletedError
├── InvalidInviteTokenError
├── SelfReservationError
├── ItemNotFoundError
└── ReservationError
    └── InsufficientQuantityError
```

### Common Issues and Resolutions

#### `PermissionDeniedError`
- **Root Cause**: Actor lacks required role (e.g. `Member` trying to archive wishlist or `Admin`
  trying to delete).
- **Resolution**: Verify user role via `WishlistAccessPolicy.resolve_context`. Only `Owner` can
  delete wishlists or promote/demote members to `Admin`.

#### `SelfReservationError`
- **Root Cause**: Recipient attempted to reserve an item designated for themselves.
- **Resolution**: Recipients cannot reserve their own gifts. Another collaborator or external gifter
  must reserve the item.

#### `WishlistArchivedError`
- **Root Cause**: Attempted to add/edit items or create reservations on an archived list.
- **Resolution**: Unarchive the wishlist via `unarchive_wishlist` prior to mutation.

#### `WishlistDeletedError`
- **Root Cause**: Requested wishlist has been soft-deleted.
- **Resolution**: Deleted wishlists cannot be viewed or modified. Create a new wishlist.

#### `InvalidInviteTokenError`
- **Root Cause**: Invite link has expired, was rotated via `regenerate_invite_token`, or token is
  corrupted.
- **Resolution**: Ask the wishlist `Owner` or `Admin` to share an updated invite link.

#### `InsufficientQuantityError`
- **Root Cause**: Requested reservation units exceed remaining `available_quantity`.
- **Resolution**: Reduce reservation quantity or select another wish item.

#### `ValueError` ("Cannot favorite own wishlist")
- **Root Cause**: Owner attempted self-favoriting.
- **Resolution**: Rejected by domain policy; owners already have access to their own lists.

#### `RuntimeError` ("Wishlist storage operation failed")
- **Root Cause**: SQLite database error, locked database, or constraint violation.
- **Resolution**: Verify database file permissions and health. Error traces suppress sensitive SQL
  parameters to protect token secrecy.
