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

- **`Wishlist`**: The aggregate root entity holding metadata, tokens, member list, and items.
- **`WishlistMember`**: Association between a Telegram user (`user_id`) and a wishlist with an assigned `WishlistRole`.
- **`WishItem`**: An item desired by a recipient (`recipient_user_id` or `recipient_name`), with quantity and price.
- **`Reservation`**: A reservation created by a gifter (`user_id`) holding an active allocation of a `WishItem`'s quantity.

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

---

## Token Schemas & Security

Wishlists use two distinct cryptographic token schemas generated using Python's `secrets.token_urlsafe`:

```
1. Public Sharing Token (Gifter Access)
   - Generation: secrets.token_urlsafe(16)
   - Entropy: 128 bits (~22 URL-safe characters)
   - Scope: Read-only access to wishlist & reservations
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
