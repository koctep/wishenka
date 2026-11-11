# Wishlists Domain: Roles, Permissions, Lifecycle, and Sharing

## Overview

The `wishenka.wishlists` module implements the core domain logic for wishlists in the **Wishlist Service («Вишенка»)** Telegram Mini App.

It manages personal and collaborative wishlists, enforces role-based access control (Contextual RBAC/ABAC), coordinates lifecycle transitions, protects the crucial **Surprise Invariant** (zero-leak projections of reservations), and provides cryptographically secure sharing tokens.

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

1. **Contextual Role-Based Access Control**: Combines static wishlist roles (`Owner`, `Admin`, `Member`) with dynamic item-level recipient checks.
2. **Surprise Invariant (Zero-Leak Projection)**: Gift recipients are strictly prevented from viewing reservation counts, status, or gifter identities.
3. **Dual Sharing Token Architecture**: Separate, cryptographically secure tokens for public viewing (`public_token`) and collaborative onboarding (`invite_token`).
4. **Lifecycle Management**: Explicit state machine (`ACTIVE` $\leftrightarrow$ `ARCHIVED` $\rightarrow$ `DELETED`) preventing mutation or reservation on archived and deleted wishlists.
5. **Structured Audit Logging**: Comprehensive security and operational event logging with zero leakage of sensitive raw tokens.

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
`sqlite+aiosqlite:///data/wishenka.db`. The application initializes the schema and WAL mode during
lifespan startup, creates parent directories for a file database, and disposes the engine at
shutdown. `WISHENKA_SQLITE_DB_PATH` is a separate setting and does not configure this store. All
workers must point to the same database file to share state. The store applies a five-second SQLite
busy timeout and serializes each operation with `BEGIN IMMEDIATE`; it loads and rewrites the
aggregate graph even for reads. This favors correctness over scale and makes reads contend for the
writer lock. The schema currently uses unversioned JSON payloads and application-maintained ID
counters; migrations and more targeted access are tracked in
[WISHENKA-48](https://pypost.atlassian.net/browse/WISHENKA-48). Favorites and viewing history are
persisted in dedicated SQLite tables (`wl_favorites` with primary key `(user_id, wishlist_id)` and
`wl_view_history` with unique index `(user_id, wishlist_id)` for deduplication), both cascading on
wishlist deletion.

If startup reports `Unable to initialize wishlist storage`, verify the database URL, directory
permissions and SQLite availability. A generic `Wishlist storage operation failed` indicates a
sanitized database failure; inspect storage health and contention without logging SQL parameters or
tokens. If a shared link returns 404, check whether it was rotated or the list was deleted; request
a new link from an owner or admin. A 409 on modification indicates an archived list or an invalid
state transition.

## Architecture & Domain Models

The domain models are defined in [`wishenka.wishlists.models`](../../wishenka/wishlists/models.py) and pure access policies in [`wishenka.wishlists.policy`](../../wishenka/wishlists/policy.py).

### Enumerations

| Enum | Values | Description |
| --- | --- | --- |
| `WishlistRole` | `owner`, `admin`, `member` | Roles of collaborators participating in a wishlist. |
| `WishlistStatus` | `active`, `archived`, `deleted` | Lifecycle state of the wishlist aggregate. |
| `WishlistFormat` | `personal`, `collaborative` | Participation format (`personal` if sole owner, `collaborative` when members exist). |
| `WishlistTimeType` | `ongoing`, `event` | Temporal classification (`event` if `event_date` is set, otherwise `ongoing`). |
| `ReservationStatus` | `active`, `completed`, `cancelled` | State of a gifter's item reservation. |

### Domain Models

- **`Wishlist`**: Aggregate root entity holding metadata, tokens, member list, and items.
- **`WishlistMember`**: Association between user (`user_id`) and wishlist with `WishlistRole`.
- **`WishlistFavorite`**: Association tracking a user's favorite (`user_id`, `wishlist_id`).
- **`ViewHistoryEntry`**: Record of a wishlist view event (`id`, `user_id`, `wishlist_id`).
- **`WishItem`**: An item desired by a recipient, with quantity and optional price.
- **`Reservation`**: Active allocation of a `WishItem`'s quantity created by a gifter.

### RBAC Policy: `WishlistAccessPolicy` & `UserWishlistContext`

Access decisions are evaluated purely through `WishlistAccessPolicy.resolve_context(user, wishlist)`, returning a frozen `UserWishlistContext`:

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
| Reserve item (as recipient) | **No** (Forbidden) | **No** (Forbidden) | **No** (Forbidden) | **No** (Forbidden) |

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

The **Surprise Invariant** guarantees that the recipient of a gift can never discover whether an item has been booked, how many units remain, or who reserved it.

#### Enforcement Mechanism

1. **Policy Check**: `WishlistAccessPolicy.is_recipient(user, item)`:
   - Returns `True` if `item.recipient_user_id == user.telegram_id`.
   - On personal wishlists without an explicit item recipient, defaults to the wishlist owner (`wishlist.owner_id == user.telegram_id`).
   - If an item specifies a non-user external recipient (e.g. `recipient_name="Бабушка Нина"`), registered collaborators are not recipients.
2. **DTO Projection**:
   - **`WishItemRecipientViewDTO`**: Returned when `is_recipient` is `True`. All reservation details (`reservations`, `available_quantity`, `is_fully_reserved`, `is_reserved_by_me`, `my_reserved_quantity`) are omitted from the schema.
   - **`WishItemGifterViewDTO`**: Returned when `is_recipient` is `False`. Includes computed availability (`available_quantity`), booking status, and whether the calling user holds an active reservation.
3. **Self-Reservation Guard**: Any attempt by a recipient to invoke `create_reservation` raises `SelfReservationError` and emits a warning audit log.

---

## Usage / API

The `WishlistService` in [`wishenka.wishlists.service`](../../wishenka/wishlists/service.py) provides the primary asynchronous application interface.

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
- **Surprise Invariant**: For each item, selects `WishItemRecipientViewDTO` if the caller is the recipient, or `WishItemGifterViewDTO` otherwise.
- **Token Security**: The `invite_token` is exposed in the DTO only to `Owner` and `Admin` members; public viewers and regular members receive `invite_token = None`.

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

- **Permissions**: `Owner` and `Admin` can add `MEMBER`s. Only `Owner` can assign or change `ADMIN` role (`can_change_member_role`).
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

- **Permissions**: `Owner` can remove any member; `Admin` can remove regular `MEMBER`s; any member can remove themselves.

#### `join_by_invite`

Allows an authenticated user to join a collaborative wishlist using a valid invite token.

```python
async def join_by_invite(
    self,
    invite_token: str,
    user: AuthenticatedUser,
) -> WishlistMember
```

- **Raises**: `InvalidInviteTokenError` if token is non-existent, revoked, or expired (`invite_token_expires_at < now`).
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
- While `ARCHIVED`, adding items, editing metadata, and booking reservations are rejected with `WishlistArchivedError`.

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

- **Surprise Invariant**: Raises `SelfReservationError` if the caller is the item's recipient.
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
- **Validation**: Raises `WishlistNotFoundError` if the wishlist does not exist or has been deleted.
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

## Token Schemas & Security

Wishlists use two distinct cryptographic token schemas generated using Python's `secrets.token_urlsafe`:

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
> **Zero Token Leakage**: Raw token values (`public_token`, `invite_token`) MUST NEVER appear in log messages or log `extra` fields. Auditing captures only resource identifiers (`wishlist_id`, `actor_id`, `user_id`).

### Audit Event Reference

| Event (`event`) | Level | Trigger | Key Extra Attributes |
| --- | :---: | --- | --- |
| `wishlist_created` | `INFO` | New wishlist created | `wishlist_id`, `owner_id`, `format`, `time_type`, `event_date` |
| `wishlist_status_changed` | `INFO` | Archived, unarchived, or deleted | `wishlist_id`, `actor_id`, `from_status`, `to_status` |
| `member_joined` | `INFO` | Collaborator accepted invite | `wishlist_id`, `user_id`, `role` |
| `member_role_assigned` | `INFO` | Member added or role changed | `wishlist_id`, `actor_id`, `user_id`, `role` |
| `member_removed` | `INFO` | Member expelled or departed | `wishlist_id`, `actor_id`, `user_id` |
| `ownership_transferred` | `INFO` | Owner ceded control | `wishlist_id`, `actor_id`, `previous_owner_id`, `new_owner_id` |
| `public_token_regenerated`| `INFO` | Public sharing token rotated | `wishlist_id`, `actor_id` |
| `invite_token_regenerated`| `INFO` | Collaborator invite token rotated | `wishlist_id`, `actor_id`, `expires_at` |
| `reservation_created` | `INFO` | Gifter booked item quantity | `wishlist_id`, `item_id`, `reservation_id`, `gifter_id`, `quantity` |
| `access_denied` | `WARNING` | Unauthorized actor action blocked | `wishlist_id`, `actor_id`, `action` |
| `surprise_invariant_violation_attempt` | `WARNING` | Recipient tried self-reservation | `wishlist_id`, `item_id`, `user_id` |
| `invalid_invite_token` | `WARNING` | Bad or expired invite token | None (raw token withheld) |
| `favorites_listed` | `INFO` | User fetched favorited wishlists | `user_id`, `count` |
| `favorite_added` | `INFO` | Wishlist added to favorites | `wishlist_id`, `user_id` |
| `favorite_removed` | `INFO` | Wishlist removed from favorites | `wishlist_id`, `user_id` |
| `favorite_own_wishlist_denied` | `WARNING` | Self-favorite denied | `wishlist_id`, `user_id` |
| `favorite_deleted_wishlist_denied` | `WARNING` | Deleted list access | `wishlist_id`, `user_id` |
| `view_history_listed` | `INFO` | User fetched viewing history | `user_id`, `count` |
| `view_history_recorded` | `INFO` | Wishlist view recorded/updated | `wishlist_id`, `user_id` |
| `view_history_cleared` | `INFO` | User cleared viewing history | `user_id` |

---

## Troubleshooting & Domain Exceptions

All domain exceptions inherit from `WishlistError` in [`wishenka.wishlists.exceptions`](../../wishenka/wishlists/exceptions.py).

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

| Exception | Root Cause | Resolution |
| --- | --- | --- |
| `PermissionDeniedError` | Actor lacks required role (e.g. `Member` trying to archive wishlist or `Admin` trying to delete). | Verify user role via `WishlistAccessPolicy.resolve_context`. Only `Owner` can delete or reassign admin roles. |
| `SelfReservationError` | Recipient attempted to reserve an item designated for themselves. | Recipient cannot reserve their own gifts. Have another collaborator or external gifter reserve the item. |
| `WishlistArchivedError` | Attempted to add/edit items or create reservations on an archived list. | Unarchive the wishlist via `unarchive_wishlist` prior to mutation. |
| `WishlistDeletedError` | Requested wishlist has been soft-deleted. | Deleted wishlists cannot be viewed or modified. Create a new wishlist. |
| `InvalidInviteTokenError` | The invite link has expired, was rotated via `regenerate_invite_token`, or token is corrupted. | Ask the wishlist `Owner` or `Admin` to share an updated invite link. |
| `InsufficientQuantityError` | Requested reservation units exceed remaining `available_quantity`. | Reduce reservation quantity or select another wish item. |
| `ValueError` | Owner attempted self-favoriting. | Rejected by domain policy. |
