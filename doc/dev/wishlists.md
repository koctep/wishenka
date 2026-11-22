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

- `GET /api/wishlists/deleted`: Lists the caller's own soft-deleted wishlists that are still
  within the retention window (`wishlist_retention_days`, default `30` days), sorted by
  `updated_at` descending with `deleted_at`, `expires_at`, and `days_remaining`.

- `GET /api/wishlists/{id}`: Reads a list for a member, including archived lists.

- `PATCH /api/wishlists/{id}`: Owner or admin updates an active list.

- `POST /api/wishlists/{id}/archive`: Owner or admin archives an active list.

- `POST /api/wishlists/{id}/restore`: Owner or admin restores an archived list.

- `POST /api/wishlists/{id}/restore-deleted`: Owner restores a soft-deleted list within the
  retention window back to `active`, rotating `public_token` and `invite_token` (with a fresh
  `invite_token_expires_at`). Returns `410 Gone` (`code: "retention_expired"`) if the retention
  window has expired.

- `POST /api/wishlists/{id}/share/reset`: Owner or admin rotates the public link on an active list.

- `POST /api/wishlists/{id}/invite/reset`: Owner or admin rotates the collaborator invite token.

- `GET /api/wishlists/{id}/members`: Lists active members and their roles.

- `PATCH /api/wishlists/{id}/members/{user_id}/role`: Owner promotes or demotes a member.

- `DELETE /api/wishlists/{id}/members/{user_id}`: Owner or admin removes a member.

- `GET /api/invitations/preview`: Previews invitation details via `X-Invite-Token` header.

- `POST /api/invitations/accept`: Authenticated user joins wishlist via `X-Invite-Token` header.

- `GET /api/public/wishlists/{token}`: Reads the anonymous-safe public projection, including archived lists.

- `GET /api/public/wishlists/{token}/view`: Reads the role-specific public projection (`anonymous_safe` for unauthenticated callers, `recipient_safe` for recipients, `gifter` for authenticated non-recipients) without membership or invite secrets.

- `GET /api/favorites`: Lists the caller's favorited wishlists in reverse-chronological order.

- `POST /api/favorites/{id}`: Adds a wishlist to caller's favorites (rejects self-favoriting).

- `DELETE /api/favorites/{id}`: Removes a wishlist from caller's favorites.

- `GET /api/history`: Lists up to 20 recently viewed wishlists in reverse-chronological order.

- `POST /api/history/{id}`: Records or updates a wishlist view event for caller.

- `DELETE /api/history`: Clears all viewing history for caller.

- `Wish Items API` (`/api/wishlists/{wishlist_id}/items`): Full REST CRUD lifecycle suite for wish items, including atomic reordering (`PUT /reorder`), safe archiving (`POST /{item_id}/archive`), end-of-list restore (`POST /{item_id}/restore`), piece accounting ($1 \le Q \le 1000$), Reduction Lock invariant, collaborative member addressing, and zero-leak Surprise Invariant projections. Detailed specification, request/response models, and telemetry events are documented in [Items Domain Documentation](items.md).

Create and patch accept a JSON object with optional `name`, `description`, `event_title`, and
`event_date`. The HTTP representation includes list details and items; member responses include
`role` and `members`, and owner/admin responses also include `share_token` and `invite_token`.
The public projection uses an explicit allowlist and omits membership, tokens and
reservation-derived fields. It is returned even when an authenticated caller uses the public URL.
Projections for `/api/favorites` and `/api/history` strictly enforce the Surprise Invariant: they
return sanitized list metadata with roles and omit all reservation records, item availability
counts, and buyer details.
Unknown, deleted or inaccessible lists return 404; operations incompatible with the archived
state return 409; attempting to restore a soft-deleted list past its retention window via
`POST /api/wishlists/{id}/restore-deleted` returns 410 (`code: "retention_expired"`). Archive is
read-only until restored. State-changing requests from browser
sessions are protected by CSRF tokens and origin validation — see [miniapp.md](miniapp.md).
There is no HTTP delete route in this API; domain soft deletion remains a separate operation.

A sharing token is a bearer capability. Rotation invalidates the old public link, and the persistent
issued-token registry prevents reuse. Do not put tokens in application logs, issue reports or
analytics. The application redacts public paths in request and Uvicorn access logs and sanitizes
storage exceptions. Configure reverse proxies and other infrastructure separately to avoid logging
capability URLs.

All public-link entry points — `GET /share/{public_token}`, `GET /api/public/wishlists/{token}`, and
`GET /api/public/wishlists/{token}/view` — resolve through `WishlistService.get_wishlist_by_public_token`.
At the domain layer, `project_wish_item(item, None)` delegates directly to `recipient_view(item)`,
returning `WishItemRecipientViewDTO` so anonymous callers never receive reservation or giver fields.
Authenticated non-recipient callers receive `WishItemGifterViewDTO`, while recipients (personal
owners or collaborative item recipients) continue to receive `WishItemRecipientViewDTO`.

### Storage and configuration

The application factory creates one `WishlistStore` and exposes a store-backed `WishlistService` as
`app.state.domain_service`. Use that service for application domain operations. `WishlistService.__init__`
enforces an explicit persistent `WishlistStore` boundary: passing `store=None` (or calling bare
`WishlistService()`) logs `wishlist_service_store_required` and raises `ValueError`. For isolated
unit tests or transient `WishlistStore` hydration, construct the service explicitly via
`WishlistService.in_memory()`. The HTTP router uses the same store. For tests only,
`app.state.wishlist_service` can override the router's service.

`WISHENKA_DATABASE_URL` selects the SQLite database and defaults to
`sqlite+aiosqlite:///data/wishenka.db`. The application initializes the normalized relational
schema during lifespan startup by running Alembic migrations to head (a recognized legacy database
is adopted without data loss; see [migrations.md](migrations.md)), selects WAL mode in that
migration startup, creates parent directories for a file database, and disposes the engine at
shutdown (`WishlistStore.dispose()`). `WISHENKA_SQLITE_DB_PATH` is a separate setting and does not
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
permissions and SQLite availability, then inspect the exception chain and the
`wishlist_migration_failed` log record (unsupported legacy schema, migration lock timeout; see
[migrations.md](migrations.md#troubleshooting)). A generic `Wishlist storage operation failed` indicates a
sanitized database failure; inspect storage health and contention without logging SQL parameters or
tokens. If a shared link returns 404, check whether it was rotated or the list was deleted; request
a new link from an owner or admin. A 409 on modification indicates an archived list or an invalid
state transition.

## HTMX Web Views & Sharing Endpoints

In addition to JSON REST endpoints, the wishlist module provides server-rendered HTML pages
and HTMX partials implemented in
[`wishenka.web.routes.sharing`](../../wishenka/web/routes/sharing.py). These routes power the
browser and Telegram Mini App web views for public gift selection, collaborator onboarding,
member management, and token rotation without client-side JavaScript SPA frameworks.

### Endpoints Reference

#### Public Gifter & Recipient Views

- `GET /share/{public_token}`:
  - **Description**: Renders the complete HTML page (`share_wishlist.html`) for a public wishlist.
  - **Authentication**: Optional session (`get_optional_current_user`). Resolves via
    `WishlistService.get_wishlist_by_public_token(public_token, current_user)`. Unauthenticated
    guests receive `WishItemRecipientViewDTO` (via `project_wish_item(item, None)` -> `recipient_view(item)`),
    concealing reservation status. Authenticated non-recipient callers receive `WishItemGifterViewDTO`
    and can view availability and reservation controls. If accessed by the list recipient or owner,
    the Surprise Invariant strictly conceals all reservations.
  - **Parameters**: `public_token` (str) — 16-byte URL-safe public sharing token.
  - **Responses**:
    - `200 OK`: Full HTML view with wishlist details, owner name, and list of items.
    - `404 Not Found`: Returned when the wishlist does not exist or has been deleted.
  - **Observability**: Logs `wishlist_shared_view` with `wishlist_id`, `is_recipient`, and
    `is_collaborative`. On failure, logs `wishlist_shared_view_failed`. Access logs redact
    the token to `/share/{token}`.

- `GET /wishlists/{wishlist_id}/items/{item_id}/card`:
  - **Description**: Returns an HTMX partial (`partials/item_card.html`) representing a single
    gift item card. After a promise write other than HTTP 503, the giver-control script
    replaces `#item-card-{id}` with this partial. The handler renders the partial and writes
    no reservation event. Mutation logs stay on `wishenka.web.reservations`. See
    [Wish-card giver controls](reservations.md#6-wish-card-giver-controls).
  - **Authentication**: Optional session (`get_optional_current_user`).
  - **Parameters**: `wishlist_id` (int), `item_id` (int), optional `notice` (`shortage` or
    `refused`), `is_first` (bool), `is_last` (bool).
  - **Notice**: `notice` is passed to the template only when the item is
    `WishItemGifterViewDTO`. A recipient card omits it.
  - **Responses**:
    - `200 OK`: HTML fragment `<div class="card item-card" id="item-card-{id}">...</div>`.
    - `404 Not Found`: Wishlist or item not found.

#### Collaborator Invitation Flow

- `GET /invite/{invite_token}`:
  - **Description**: Previews a collaborator invitation before joining.
  - **Authentication**: None required.
  - **Parameters**: `invite_token` (str) — 24-byte URL-safe invite token.
  - **Responses**:
    - `200 OK`: Renders `invite_preview.html`. If the token is valid and active, displays
      wishlist title, owner name, and a "Join" HTMX button. If the token is invalid, expired,
      or associated with a deleted list, returns a friendly error card (`is_valid=False`) with
      HTTP 200 rather than raw JSON errors.
  - **Observability**: Logs `invite_preview_accessed` with status `valid`, `expired`, or
    `not_found`. Access logs redact the token to `/invite/{token}`.

- `POST /invite/{invite_token}/join`:
  - **Description**: Processes acceptance of the invitation by an authenticated user.
  - **Authentication**: Required session (`get_current_user`).
  - **Parameters**: `invite_token` (str).
  - **Responses**:
    - `200 OK`: On success, returns confirmation markup with response header
      `HX-Redirect: /share/{public_token}` triggering client navigation.
    - `200 OK` (Error Card): If token expired or list was deleted concurrently, returns
      the friendly error card template.
    - `429 Too Many Requests`: Returned by `PublicLinkRateLimitMiddleware` if the client exceeds
      the configured sliding-window limit.
  - **Observability**: Logs `invite_joined` with `wishlist_id`, `user_id`, and assigned role,
    or `invite_join_failed` on error. Access logs redact the path to `/invite/{token}/join`.

#### Public Link Rate Limiting

Unauthenticated and public capability routes are protected by
`PublicLinkRateLimitMiddleware` and `SlidingWindowRateLimiter` in
[`wishenka.web.rate_limit`](../../wishenka/web/rate_limit.py) (wired onto
`app.state.public_link_rate_limiter` in [`wishenka.web.app`](../../wishenka/web/app.py)):

- **Protected Routes** (`match_public_link_route`):
  - `GET /share/{token}`
  - `GET /invite/{token}`
  - `POST /invite/{token}/join`
- **Algorithm & Bounds**: `SlidingWindowRateLimiter` maintains an in-memory per-client
  timestamp `deque` inside an `OrderedDict` (`max_requests` within `window_seconds`, bounded by
  `max_clients` with expired-bucket pruning and oldest-client eviction).
- **Client IP Resolution (`resolve_client_ip`)**: Uses `request.client.host` by default.
  `X-Forwarded-For` (leftmost IP) and `X-Real-IP` are consulted only when
  `public_rate_limit_trust_proxy_headers` is `True`.
- **429 Response (`_build_rate_limit_response`)**: Returns `429 Too Many Requests` with a
  `Retry-After` header and a localized RU/EN body (`web.rate_limit.title` and
  `web.rate_limit.message`, resolved via `?lang=` or `Accept-Language`). Returns JSON
  (`{"detail": ..., "retry_after": ...}`) when `Accept` includes `application/json`, or
  HTML-escaped markup otherwise, without echoing any token.

#### Member Administration

- `GET /wishlists/{wishlist_id}/members/partial`:
  - **Description**: Renders collaborator list partial (`partials/member_list.html`).
  - **Authentication**: Required session (`get_current_user`). Caller must be owner, admin, or
    member.
  - **Responses**:
    - `200 OK`: HTML fragment `<div id="member-list">...</div>` listing owner and members
      with role badges. If caller is owner, includes `hx-delete` removal buttons.
    - `403 Forbidden`: Caller lacks permission to view members.
    - `404 Not Found`: Wishlist not found or deleted.

- `DELETE /wishlists/{wishlist_id}/members/{user_id}/partial`:
  - **Description**: Removes a collaborator from the wishlist and returns updated member list.
  - **Authentication**: Required session (`get_current_user`). Only the wishlist owner can
    remove members.
  - **Responses**:
    - `200 OK`: Updated HTML fragment `#member-list` with target member removed.
    - `403 Forbidden`: Caller is not the wishlist owner.
    - `404 Not Found`: Wishlist not found.
  - **Observability**: Logs `member_removed` with `wishlist_id`, `removed_user_id`, and
    `removed_by`.

#### Share Drawer & Token Rotation

- `GET /wishlists/{wishlist_id}/share-modal`:
  - **Description**: Renders the share drawer dialog partial (`partials/share_modal.html`).
  - **Authentication**: Required session (`get_current_user`). Owner-only access.
  - **Responses**:
    - `200 OK`: HTML fragment `<div id="share-modal">...</div>` containing readonly inputs
      for `/share/{public_token}` and `/invite/{invite_token}`, accompanied by explanatory
      copy and a button to revoke/regenerate the invite link.
    - `403 Forbidden`: Caller is not the wishlist owner.
    - `404 Not Found`: Wishlist not found.

- `POST /wishlists/{wishlist_id}/invite/regenerate`:
  - **Description**: Revokes the existing invite token and generates a fresh token, returning
    the re-rendered modal.
  - **Authentication**: Required session (`get_current_user`). Owner-only access.
  - **Responses**:
    - `200 OK`: Updated `#share-modal` partial reflecting the newly generated invite token.
    - `403 Forbidden`: Caller is not the wishlist owner.
  - **Observability**: Logs `invite_regenerated` with `wishlist_id` and `user_id`.

---

### Jinja2 Template Architecture

Template rendering is configured in
[`wishenka.web.templates`](../../wishenka/web/templates.py) using
`fastapi.templating.Jinja2Templates` pointing to `wishenka/web/templates/`. The template
directory structure follows a modular component layout:

```
wishenka/web/templates/
├── base.html             # Master layout with viewport, CSS, Telegram SDK, HTMX, deferred static JS
├── share_wishlist.html   # Full page public view for gifters and recipients
├── invite_preview.html   # Full page collaborator preview and friendly error screen
└── partials/
    ├── item_card.html    # Gift item card partial with Surprise Invariant
    ├── member_list.html  # Collaborator member list with owner removal actions
    └── share_modal.html  # Modal dialog for link sharing and regeneration

wishenka/web/static/
├── app.js                # Global CSRF, HTMX lifecycle, card/cabinet refresh, delegated modal/preview clicks (loaded by base.html)
├── miniapp.css           # Shared styles
├── miniapp.js            # Mini App SPA script (loaded only by the Mini App shell)
├── receipt.js            # Gift receipt dialog and focus trap (loaded by base.html)
├── settings.js           # Profile settings page controller (loaded by settings.html)
└── wishlist.js           # Card toggle, mouse and touch drag-and-drop reorder (loaded by base.html)
```

#### Template Specifications

1. **`base.html`**:
   - Master document providing HTML5 doctype, UTF-8 charset, responsive viewport metadata, and
     zero inline `<script>` blocks.
   - Loads Telegram Web App SDK (`telegram-web-app.js`), HTMX 1.9.12 (`htmx.org@1.9.12`), and
     `json-enc.js`, followed by deferred static scripts in order: `/static/app.js`,
     `/static/wishlist.js`, and `/static/receipt.js`.
   - `static/app.js` owns CSRF token preparation (`window.prepareCsrf`), HTMX reservation/modal
     hooks, `swapWishCard`, and delegated `[data-clear-target]` / `[data-qty-step][data-qty-target]`
     click handlers; `static/wishlist.js` owns the wish-card toggle and drag-and-drop reorder
     (reading `data-wishlist-id` on `#items-list` in `wishlist_detail.html` and `share_wishlist.html`).
     Details: [miniapp.md](miniapp.md#981-client-script-staticwishlistjs-wishenka-108) and
     [miniapp.md](miniapp.md#982-global-app-script-staticappjs-settings-script-staticsettingsjs-and-strict-csp-readiness-wishenka-140).
   - Provides Jinja2 template extension blocks: `{% block title %}` and `{% block content %}`.

2. **`share_wishlist.html`**:
   - Extends `base.html`.
   - Displays wishlist header (title, owner name, description, event title and date).
   - Iterates over `wishlist.items` and includes `partials/item_card.html` for each item;
     the list container is `<section id="items-list" data-wishlist-id="{{ wishlist.id }}">`.
   - Shows empty-state guidance if no items are present.

3. **`invite_preview.html`**:
   - Extends `base.html`.
   - Conditionally renders an invitation card (`is_valid=True`) or friendly error card
     (`is_valid=False`).
   - The valid card features wishlist metadata, inviter attribution, and an HTMX form:
     `<form hx-post="/invite/{{ token }}/join" hx-target="#invite-card" hx-swap="outerHTML">`.
   - The error card displays an explanatory message and a link back to the homepage (`/`).

4. **`partials/item_card.html`**:
   - Encapsulates an individual gift item inside
     `<div class="card item-card" id="item-card-{{ item.id }}">`.
   - The compact row is `.item-card-summary` (`aria-expanded="false"`). The expanded body is
     `.item-card-details`, rendered with `hidden`. The delegated toggle in `static/wishlist.js`
     clears `hidden` to expand the same card (no inline handlers on the card).
   - For owners and editors (`can_edit_wishlist`) the collapsed summary starts with the drag handle
     `.item-drag-handle` (`aria-hidden="true"`, `data-no-toggle`), the touch reorder grip
     (WISHENKA-109, [miniapp.md](miniapp.md#981-client-script-staticwishlistjs-wishenka-108)). The
     move up and move down buttons stay in the details as the keyboard path.
   - Displays item title, optional formatted price with currency, description, quantity, and
     external link (`rel="noopener noreferrer"`).
   - Giver controls are one `.item-giver` block in the summary, guarded by
     `{% if not item.is_recipient %}`. The details do not repeat that block. Editor controls
     stay in the details. The control list, own line, refresh, and CSRF behavior are in
     [Wish-card giver controls](reservations.md#6-wish-card-giver-controls).

5. **`partials/member_list.html`**:
   - Renders container `<div id="member-list" class="member-list space-y-2">`.
   - Lists list owner with `Владелец` badge, followed by collaborators.
   - Displays role badges (`Администратор` or `Участник`).
   - If caller is owner (`is_owner=True`), renders an HTMX delete button:
     `<button hx-delete="..." hx-target="#member-list" hx-swap="outerHTML">`.

6. **`partials/share_modal.html`**:
   - Renders container `<div id="share-modal" class="share-modal">`.
   - Displays readonly input for public URL (`/share/{{ public_token }}`) for gifter access.
   - Displays readonly input for invite URL (`/invite/{{ invite_token }}`) for co-authoring.
   - Contains an HTMX regeneration button:
     `<button hx-post="..." hx-target="#share-modal" hx-swap="outerHTML">`.

---

### Surprise Invariant in Server-Rendered Templates

The Surprise Invariant is enforced at both the domain service layer and the template presentation
layer, providing defense-in-depth against data leakage:

1. **Domain DTO Projection**:
   - When `WishlistService.get_wishlist_by_public_token` or `get_wishlist_view` is called,
     items for which the viewing user is a recipient (`is_recipient == True`) are projected as
     `WishItemRecipientViewDTO`.
   - For gifters (`is_recipient == False`), items are projected as `WishItemGifterViewDTO`.
   - `WishItemRecipientViewDTO` completely lacks reservation fields (`available_quantity`,
     `is_fully_reserved`, `is_reserved_by_me`, `my_reserved_quantity`,
     `my_latest_reservation_quantity`, `my_occupying_reservation_count`, and reservation lists).

2. **Template-Level Conditional Guard**:
   - In `partials/item_card.html`, the giver block is guarded by
     `{% if not item.is_recipient %}` and lives in `.item-card-summary`:
     ```html
     {% if not item.is_recipient %}
     <div class="item-giver mt-2 text-sm" data-no-toggle>
         <!-- availability, «Забронировано вами (N)», and the five promise controls -->
     </div>
     {% endif %}
     ```
   - When `item.is_recipient` is true, `.item-giver` is omitted from the HTML. On a personal
     list that includes the owner of a display-name-only wish. A recipient cannot infer
     reservation activity from HTML attributes, CSS classes, or DOM nodes. Availability and the
     own line are independent: a holder who took the last units still sees
     `Забронировано вами (N)` next to `Забронировано`. ` · Куплено` is added only when the
     latest occupying promise is bought and it is the only one. The full control and refresh
     contract is in [Wish-card giver controls](reservations.md#6-wish-card-giver-controls).

3. **Bearer Token Isolation**:
   - The private collaborator `invite_token` is strictly isolated to owner administrative views
     (`share_modal.html`).
   - Public views (`share_wishlist.html`) and item cards (`item_card.html`) never receive or
     render `invite_token`, preventing accidental elevation of gifters to collaborators.

4. **Access Log and URL Masking**:
   - Both `ShareTokenAccessFilter` (logging filter) and `RequestLoggingMiddleware` redact raw
     sharing and invite tokens in log streams to `/share/{token}` and `/invite/{token}`,
     ensuring bearer tokens are not leaked into disk logs or terminal outputs.

---

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

*Note: Item recipients are strictly prohibited from reserving items designated for themselves. Per `WISHENKA-154` (`FR-1.2`, `FR-4` / Q11), a co-author (`Admin` or `Member`) who is also the recipient of a wish retains full author rights on that wish (edit, archive/restore, record/undo/correct receipt) with strict surprise protection, while acting as a normal gifter on other wishes in the same list.*

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
   - A missing user is not a recipient.
   - On a personal list (`wishlist` is present and `is_collaborative` is false) the owner is
     the recipient of every wish, including a wish that has only a display name
     (`wishlist.owner_id == user.telegram_id`).
   - On a collaborative list the caller is the recipient only when
     `item.recipient_user_id == user.telegram_id`.
   - A display name is never compared to a user. A name alone does not make a recipient.
2. **DTO Projection**:
   - **`WishItemRecipientViewDTO`**: Returned when `is_recipient` is `True`. All reservation
     details (`reservations`, `available_quantity`, `is_fully_reserved`, `is_reserved_by_me`,
     `my_reserved_quantity`, `my_latest_reservation_quantity`,
     `my_occupying_reservation_count`) are omitted from the schema.
   - **`WishItemGifterViewDTO`**: Returned when `is_recipient` is `False`. Includes computed
     availability (`available_quantity`), the combined occupying quantity
     (`my_reserved_quantity`), the latest occupying row (`my_reservation_id`,
     `my_reservation_status`, `my_latest_reservation_quantity`), and
     `my_occupying_reservation_count`.
3. **Self-Reservation Guard**: Any attempt by a recipient to invoke `create_reservation` raises
   `SelfReservationError` and emits a warning audit log.
4. **Template Presentation Guard**: Server-rendered Jinja2 templates (`item_card.html`) wrap
   `.item-giver` in `{% if not item.is_recipient %}`. For recipients, no availability line,
   own line, or promise control exists in the rendered HTML. See
   [Wish-card giver controls](reservations.md#6-wish-card-giver-controls).

### Fail-Closed Parent Wishlist Invariant

Every `WishItem` mutation that depends on parent wishlist lifecycle state or `WishlistAccessPolicy`
authorization must fail closed when `item.wishlist` is absent:

- **Guard Helper**: [`WishlistService._require_item_wishlist(item)`](../../wishenka/wishlists/service.py)
  returns `item.wishlist` as a non-optional `Wishlist`. If `item.wishlist is None`, it emits an
  `ERROR` structured log (`event="item_missing_parent_wishlist"`, `item_id`, `wishlist_id`) and
  raises `WishlistNotFoundError` (mapped to HTTP 404 by web routes) before any state mutation.
- **Guarded Entrypoints**:
  - `update_wish_item`
  - `create_reservation`
  - `record_item_fulfillment`
  - `cancel_item_receipt` (via `_validate_receipt_mutation_access`)
  - `correct_item_receipt` (via `_validate_receipt_mutation_access`)
- **Regression Coverage**: [`tests/test_wishlist_fail_closed_repro.py`](../../tests/test_wishlist_fail_closed_repro.py)
  verifies that detaching `item.wishlist = None` causes all five entrypoints to raise
  `WishlistNotFoundError` with zero state mutation.

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

#### `get_wishlist_by_public_token`

Resolves a wishlist by its capability `public_token` and delegates to `get_wishlist_view`.

```python
async def get_wishlist_by_public_token(
    self,
    public_token: str,
    current_user: AuthenticatedUser | None = None,
) -> WishlistDetailViewDTO
```

- **Raises**: `WishlistNotFoundError`, `WishlistDeletedError`.
- **Consolidated Projection**: Used by `GET /share/{public_token}`, `GET /api/public/wishlists/{token}`,
  and `GET /api/public/wishlists/{token}/view`. Because `project_wish_item(item, None)` returns
  `recipient_view(item)` (`WishItemRecipientViewDTO`), anonymous callers (`current_user=None`)
  never receive reservation or giver fields.
- **Observability**: Emits `public_wishlist_resolved` (`INFO`) with `wishlist_id`, `identified`,
  `user_id`, `projection_mode` (`"anonymous_safe"`, `"recipient_safe"`, or `"gifter"`), and
  `items_count`, without logging `public_token`.

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
- Per `WISHENKA-154` (`FR-3` / Q8), deleting a wishlist permanently removes its «Подаренные» gifted history together with the wishlist and its wishes (no standalone long-term history is retained); archiving a wishlist preserves «Подаренные» in read-only mode.

#### `list_deleted_wishlists` & `restore_deleted_wishlist`

Lists and restores an owner's soft-deleted wishlists while they remain inside the retention
window (`wishlist_retention_days`, default `30` days).

```python
async def list_deleted_wishlists(
    self,
    actor: AuthenticatedUser,
    retention_days: int = 30,
    now: datetime | None = None,
) -> list[tuple[Wishlist, datetime, int]]

async def restore_deleted_wishlist(
    self,
    wishlist_id: int,
    actor: AuthenticatedUser,
    retention_days: int = 30,
    now: datetime | None = None,
) -> Wishlist
```

- **Permissions**: Solely the `Owner` via `WishlistAccessPolicy.can_restore_deleted`. Non-owners
  are excluded from `list_deleted_wishlists` and receive `PermissionDeniedError` (HTTP `404`)
  from `restore_deleted_wishlist`.
- **Retention boundary**: A list is restorable only when
  `deleted_at > effective_now - timedelta(days=retention_days)`. Once `deleted_at <= threshold`,
  `list_deleted_wishlists` omits it and `restore_deleted_wishlist` raises
  `WishlistRetentionExpiredError` (HTTP `410 Gone` with `detail.code = "retention_expired"`).
- **Listing output**: Returns `(wishlist, expires_at, days_remaining)` sorted by `updated_at`
  descending, with `days_remaining = max(1, math.ceil(remaining_seconds / 86400))`.
- **Token rotation & state**: Restoring a `DELETED` list transitions it to `WishlistStatus.ACTIVE`,
  rotates both `public_token` and `invite_token` to fresh values distinct from prior tokens, and
  resets `invite_token_expires_at = effective_now + self._default_invite_ttl`. Calling
  `restore_deleted_wishlist` on an `ACTIVE` list is idempotent; calling it on an `ARCHIVED` list
  raises `WishlistArchivedError` (HTTP `409`).

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
- `clear_history`: Removes all viewing history entries for the authenticated user and logs
  `view_history_cleared` with `user_id` and `removed_count`. This is the only emitter: the
  `DELETE /api/history` route does not log it (WISHENKA-292). Screen:
  [miniapp.md](miniapp.md#8-viewing-history--automated-tracking).

---

## Persistence Architecture: SQLite WAL & Repositories

Wishenka stores wishlist aggregates in a fully normalized relational SQLite schema managed via
the SQLAlchemy 2.0 async engine (`sqlite+aiosqlite`). Prototype JSON blobs and destructive mass
table overwrites (`DELETE FROM <table>`) have been replaced with atomic, row-level persistence,
granular async queries, and relationship cascade deletion.

```
+-----------------------------------------------------------------------------------------+
|                        WishlistStore (Unit of Work Boundary)                           |
|  - Manages SQLite connection lifecycle, foreign keys, and busy timeout (WAL: migrations)|
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
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
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
    display_order INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wl_items_wishlist ON wl_items(wishlist_id);
CREATE INDEX IF NOT EXISTS idx_wl_items_recipient ON wl_items(recipient_user_id);
CREATE INDEX IF NOT EXISTS idx_wl_items_order ON wl_items(wishlist_id, display_order);

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
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    wishlist_id INTEGER NOT NULL REFERENCES wl_lists(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, wishlist_id)
);
CREATE INDEX IF NOT EXISTS idx_wl_favorites_user ON wl_favorites(user_id);

-- 6. User Viewing History
CREATE TABLE IF NOT EXISTS wl_view_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
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
- Deleting a user from `users` cascades (`ON DELETE CASCADE` on `user_id` → `users(telegram_id)`,
  added in Alembic revision `add_user_fk_cascades`; see [migrations.md](migrations.md)) to:
  - All collaborative memberships in `wl_members`.
  - All user bookmark entries in `wl_favorites`.
  - All user viewing history records in `wl_view_history`.
  - Inserting rows into `wl_members`, `wl_favorites`, or `wl_view_history` with a `user_id` not
    present in `users(telegram_id)` fails with `IntegrityError` when `PRAGMA foreign_keys = ON` is
    active.
  - `AccountDeletionService` (`wishenka/wishlists/deletion.py`) executes within `BEGIN IMMEDIATE`
    and `PRAGMA foreign_keys = ON`, transferring/deleting owned lists and deleting the `users` row
    so both explicit cleanup and `ON DELETE CASCADE` remove all user-linked records.
- Deleting a wishlist from `wl_lists` cascades (`ON DELETE CASCADE`) to:
  - All associated members in `wl_members`.
  - All contained items in `wl_items` (and subsequently all reservations in `wl_reservations`).
  - All user bookmark entries in `wl_favorites`.
  - All user viewing history records in `wl_view_history`.
- Deleting a wish item (`wl_items`) cascades to all its reservations (`wl_reservations`), its
  receipt records (`wl_receipts`) and its notice queue rows (`notification_outbox`).
- A soft-deleted list (`status = 'deleted'`) keeps its receipt records and queue rows: the cascade
  fires only when `purge_archived_wishlists` removes the list row. Until then the gifted read
  answers 404 `wishlist_not_active` and the notice worker settles queued rows as `skipped`
  (`target_gone`). The list-level settings table `wl_list_notification_settings` cascades with the
  list too. See [gift-receipt.md](gift-receipt.md).

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
- **`UserRefRow`**: Minimal declarative reference to the `users` table (`id`, `telegram_id`) used
  so SQLAlchemy metadata resolves `ForeignKey("users.telegram_id", ondelete="CASCADE")` on
  user-linked wishlist tables.
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
- **`WishlistMemberRow`**: Represents `wl_members`. References `wl_lists.id` via
  `ForeignKey("wl_lists.id", ondelete="CASCADE")` and `users.telegram_id` via
  `ForeignKey("users.telegram_id", ondelete="CASCADE")`, and back-populates `members`.
- **`WishItemRow`**: Represents `wl_items`. References `wl_lists.id` and configures child cascade:
  ```python
  reservations: Mapped[list["ReservationRow"]] = relationship(
      back_populates="wish_item", cascade="all, delete-orphan"
  )
  ```
- **`ReservationRow`**: Represents `wl_reservations` with `ForeignKey(..., ondelete="CASCADE")`.
- **`WishlistFavoriteRow`**: Represents `wl_favorites` with composite key `(user_id, wishlist_id)`
  and `ForeignKey("users.telegram_id", ondelete="CASCADE")` /
  `ForeignKey("wl_lists.id", ondelete="CASCADE")`.
- **`ViewHistoryRow`**: Represents `wl_view_history` with autoincrement integer primary key `id`,
  `ForeignKey("users.telegram_id", ondelete="CASCADE")`, and
  `ForeignKey("wl_lists.id", ondelete="CASCADE")`.
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

#### Maintenance & Cleanup Methods
- `cleanup_expired_tokens(now: datetime | None = None) -> int`:
  Revokes invite tokens whose expiration timestamp has passed (`invite_token_expires_at <= now`).
  Removes token from `wl_invite_tokens`, prepends `'revoked:'` to `invite_token` in `wl_lists`,
  and sets `invite_token_expires_at = NULL`. Returns the count of cleaned tokens.
- `purge_archived_wishlists(threshold: datetime) -> int`:
  Permanently purges soft-deleted wishlists (`status = 'deleted'`) whose `updated_at <= threshold`.
  Deletes capability tokens from `wl_tokens` and `wl_invite_tokens`, then deletes the rows from
  `wl_lists` with `PRAGMA foreign_keys = ON`. Foreign key cascades automatically remove child
  members (`wl_members`), items (`wl_items`), reservations (`wl_reservations`), receipt records
  (`wl_receipts`), notice queue rows (`notification_outbox`), favorites (`wl_favorites`), and
  history entries (`wl_view_history`). Returns the number of purged wishlists.
- `purge_deleted_wishlists(threshold: datetime) -> int`:
  Semantic alias forwarding directly to `purge_archived_wishlists`.

`WishlistStore` exposes matching async helper methods `cleanup_expired_tokens(now)` and
`purge_archived_wishlists(threshold)` (alias `purge_deleted_wishlists(threshold)`) that execute
repository operations inside dedicated write transactions (`BEGIN IMMEDIATE`) with foreign keys
and busy timeout configured.

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
  with active write transactions without blocking or lock contention. It is persistent file state,
  selected once by the migration startup rather than on each connection.
- **Immediate Write Transactions (`BEGIN IMMEDIATE`)**: State mutations begin with `BEGIN IMMEDIATE`
  to acquire an SQLite write lock at the start of the transaction, eliminating mid-transaction
  upgrade deadlocks (`SQLITE_BUSY`).
- **Bounded Busy Timeout (`PRAGMA busy_timeout = 5000`)**: If SQLite encounters a transient write
  lock, it waits up to 5000 milliseconds before raising an operational error.
- **Capability Collision Retry**: If a concurrent worker or token generation collides with an
  existing capability token in `wl_tokens` or `wl_invite_tokens`, `WishlistStore.execute()` and
  `WishlistStore.execute_with_connection()` catch `TokenCollision` / `IntegrityError` and retry up
  to 5 times with newly generated cryptographic tokens.
- **Public Hybrid Transaction Seam (`WishlistStore.execute_with_connection`)**:
  `execute_with_connection(operation)` accepts `Callable[[WishlistService, AsyncConnection], Awaitable[T]]`
  and runs both hydrated `WishlistService` domain operations and caller-scoped SQL on the same
  `AsyncConnection` inside one `BEGIN IMMEDIATE` transaction (sharing `_read`/`_write` snapshot
  diffing, token-collision retries, error mapping, and post-commit log flushing).
  `WishlistStore.execute()` delegates to `execute_with_connection()`. Callers outside the
  wishlist domain that need atomic cross-table writes alongside domain operations (such as
  `wishenka.bot.capture:mutate` updating `bot_drafts` and `bot_capture_order` with
  `add_wish_item`) use `execute_with_connection()` instead of private `_read`/`_write` hooks.
- **Read-Only Deferred Transactions (`WishlistStore.execute_read`)**:
  `execute_read(work)` accepts `Callable[[AsyncConnection], Awaitable[T]]`, binds
  `execution_options(read_only=True)` on the connection, and runs `work(conn)` inside a deferred
  `BEGIN` transaction (rolling back on exit). `_configure_immediate_transactions` checks
  `conn.get_execution_options().get("read_only")` in the `begin` event listener and emits `BEGIN`
  instead of `BEGIN IMMEDIATE`, allowing read-only paths (such as `wishenka.bot.support`
  rate-limit checks and diagnostic collection) to read without acquiring a SQLite write lock.

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
- **Sanitized Domain Exceptions**: At `WishlistStore.execute()`, `SQLITE_BUSY` after
  `busy_timeout` is translated to `InventoryBusyError` before the generic storage mapping.
  The attempt changes nothing. Any other `SQLAlchemyError` on that path becomes
  `RuntimeError` (`"Wishlist storage operation failed"`). A non-token `IntegrityError` is
  still that same `RuntimeError`; token collisions retry. Internal SQLite table names, SQL
  syntax, and tokens stay out of those messages.

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
   - Expiration: invite_token_expires_at (TTL configured by invite_token_ttl_seconds,
     defaulting to 7 days / 604,800 seconds)
   - URL: https://t.me/WishenkaBot/app?startapp=i_<invite_token>
```

---

## Background Cleanup & Data Retention

The `wishenka.wishlists.cleanup` module implements asynchronous maintenance routines to enforce
collaborator token expirations and retention windows for soft-deleted wishlists without blocking
regular web request handling.

### Architecture & Components

```
+-----------------------------------------------------------------------------------------+
|                  FastAPI Lifespan (wishenka.web.app.create_app)                         |
|  - Checks settings.background_cleanup_enabled                                           |
|  - Spawns background_cleanup_worker task on startup; cancels & awaits on shutdown       |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|            Background Worker Loop: background_cleanup_worker                            |
|  - Runs indefinitely while awaiting stop_event or cancellation                         |
|  - Wakes up every settings.background_cleanup_interval_seconds (default: 3600s)         |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
|                Cleanup Cycle Runner: run_cleanup_cycle                                  |
|  1. store.cleanup_expired_tokens(now) -> revokes expired collaborator invite tokens     |
|  2. cutoff = now - timedelta(days=settings.wishlist_retention_days)                     |
|  3. store.purge_archived_wishlists(cutoff) -> permanently cascades soft-deleted lists   |
|  4. store.cleanup_expired_idempotency_records(now) -> purges expired idempotency keys   |
|  5. store.cleanup_expired_session_revocations(now) -> purges expired revocation markers |
|  6. NoticeStore.purge_finished(now - receipt_notice_retention_days, reminder_threshold=...)  |
|  7. NoticeStore.purge_retention_records(...) -> deleted birthdays, destinations, dedup keys|
|  8. Captures execution duration and returns CleanupStats(duration_ms, ...)              |
+-----------------------------------------------------------------------------------------+
```

### Module Functions & Data Structures

#### `CleanupStats`
Dataclass capturing operational metrics for a single execution cycle:
- `expired_tokens_cleaned: int`: Count of expired collaborator invite tokens revoked.
- `wishlists_purged: int`: Count of soft-deleted wishlists permanently removed past retention.
- `idempotency_records_cleaned: int`: Count of expired `wl_idempotency_records` rows removed.
- `session_revocations_cleaned: int`: Count of expired `deleted_session_revocations` markers purged (`AccountDeletionService` / `WISHENKA-35` — see [users.md](users.md)).
- `birthdays_purged: int`: Count of anonymized `deleted = 1` `birthday_entries` rows physically deleted past `birthday_retention_days` (with no pending/sending/uncertain reminders).
- `bot_destinations_purged: int`: Count of inactive (`active = 0`) `bot_destinations` rows physically deleted past `bot_destination_retention_days`.
- `receipt_keys_purged: int`: Count of `notice_receipt_keys` rows physically deleted past `receipt_dedup_retention_days` (with no remaining `notification_outbox` row).
- `duration_ms: float`: Execution duration of the cycle in milliseconds.
- `started_at: datetime`: UTC timestamp when the cycle began.
- `finished_at: datetime`: UTC timestamp when the cycle completed.

#### `run_cleanup_cycle`
```python
async def run_cleanup_cycle(
    store: WishlistStore,
    settings: Settings,
    now: datetime | None = None,
    notice_store: NoticeStore | None = None,
) -> CleanupStats
```
- Performs a complete cleanup cycle: revokes expired tokens and purges deleted wishlists older
  than `settings.wishlist_retention_days`. When `notice_store` is given (the application always
  passes it) it also deletes finished `notification_outbox` rows older than
  `settings.receipt_notice_retention_days`, finished `reminder_outbox` rows older than
  `settings.reminder_retention_days` (preserving active-cycle `list`/`birthday` reminders), and
  expired retention records (`birthday_entries`, `bot_destinations`, `notice_receipt_keys`) via
  `NoticeStore.purge_retention_records`; a failure there is a WARNING `receipt_notice_purge_failed`
  and does not fail the cycle.
- Traps operational exceptions gracefully to prevent background loop termination, logging
  `background_cleanup_failed` with `exc_info=True`.
- Emits structured audit log `background_cleanup_completed` on success.

#### `background_cleanup_worker`
```python
async def background_cleanup_worker(
    store: WishlistStore,
    settings: Settings,
    stop_event: asyncio.Event | None = None,
) -> None
```
- Continuous background loop executing `run_cleanup_cycle` at the configured interval
  (`settings.background_cleanup_interval_seconds`, default: 3600s / 1h).
- Monitors optional `stop_event` or catches `asyncio.CancelledError` for graceful shutdown.
- Emits `background_worker_started` and `background_worker_stopped` structured logs.

### Application Lifecycle & Testing

#### Lifespan Integration
In `wishenka.web.app.create_app`:
- When `settings.background_cleanup_enabled` is `True`, an `asyncio.create_task` is scheduled
  during lifespan startup and stored on `app.state.background_cleanup_task`
  (and `app.state.cleanup_task`).
- During lifespan shutdown, the background task is cancelled via `task.cancel()` and awaited
  with `asyncio.CancelledError` suppressed.

#### Disabling Background Worker in Tests
In automated test suites and lightweight test environments, the background worker should be
disabled to prevent uncoordinated database mutations or test isolation leaks:

```python
settings = Settings(
    database_url="sqlite+aiosqlite:///:memory:",
    background_cleanup_enabled=False,
)
app = create_app(settings)
```
Or set the environment variable:
```bash
export WISHENKA_BACKGROUND_CLEANUP_ENABLED=false
```
When `background_cleanup_enabled = False`, `app.state.background_cleanup_task` is initialized
to `None`, and no recurring loop is started. Test suites can invoke
`run_cleanup_cycle(store, settings)` directly with custom timestamps (`now=...`) to test
retention and expiration deterministically.

---

## Configuration & Audit Logging

Structured logging is managed under the `wishenka.wishlists` logger namespace.

### Configuration Parameters

Settings in `wishenka.config.Settings` (prefixed with `WISHENKA_` in environment):

- **`invite_token_ttl_seconds`** (`int`, default: `604800` / 7 days):
  Colleague invite token lifetime. Environment: `WISHENKA_INVITE_TOKEN_TTL_SECONDS`.
- **`wishlist_retention_days`** (`int`, default: `30` days):
  Retention window before permanently purging soft-deleted wishlists.
  Environment: `WISHENKA_WISHLIST_RETENTION_DAYS`.
- **`background_cleanup_interval_seconds`** (`int`, default: `3600` / 1 hour):
  Sleep interval between background cleanup runs.
  Environment: `WISHENKA_BACKGROUND_CLEANUP_INTERVAL_SECONDS`.
- **`background_cleanup_enabled`** (`bool`, default: `True`):
  Master flag to spawn cleanup worker in lifespan. Set `False` in test environments.
  Environment: `WISHENKA_BACKGROUND_CLEANUP_ENABLED`.
- **`public_rate_limit_enabled`** (`bool`, default: `True`):
  Enables `PublicLinkRateLimitMiddleware` for public share and invite routes.
  Environment: `WISHENKA_PUBLIC_RATE_LIMIT_ENABLED`.
- **`public_rate_limit_max_requests`** (`int`, default: `30`, range `1..10000`):
  Maximum requests allowed per client within the sliding window.
  Environment: `WISHENKA_PUBLIC_RATE_LIMIT_MAX_REQUESTS`.
- **`public_rate_limit_window_seconds`** (`int`, default: `60`, range `1..86400`):
  Sliding window duration in seconds.
  Environment: `WISHENKA_PUBLIC_RATE_LIMIT_WINDOW_SECONDS`.
- **`public_rate_limit_trust_proxy_headers`** (`bool`, default: `False`):
  When `True`, `resolve_client_ip` reads `X-Forwarded-For` (first IP) or `X-Real-IP` before
  falling back to `request.client.host`. Keep `False` unless behind a trusted reverse proxy.
  Environment: `WISHENKA_PUBLIC_RATE_LIMIT_TRUST_PROXY_HEADERS`.
- **`public_rate_limit_max_clients`** (`int`, default: `10000`, minimum `100`):
  Maximum number of client IP buckets retained in `SlidingWindowRateLimiter` memory.
  Environment: `WISHENKA_PUBLIC_RATE_LIMIT_MAX_CLIENTS`.

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
| `wishlist_shared_view` | `INFO` | Public share rendered | `wishlist_id`, `is_recipient` |
| `wishlist_shared_view_failed` | `WARNING` | Public view failed | None (token withheld) |
| `public_wishlist_resolved` | `INFO` | Public token resolved | `wishlist_id`, `identified`, `user_id`, `projection_mode`, `items_count` |
| `wishlist_service_store_required` | `ERROR` | `WishlistService` created without store | None (`ValueError` raised) |
| `wishlist_service_in_memory_created` | `DEBUG` | `WishlistService.in_memory()` created | None |
| `invite_preview_accessed` | `INFO` | Invite preview rendered | `wishlist_id`, `status` |
| `invite_joined` | `INFO` | Collaborator joined | `wishlist_id`, `user_id`, `role` |
| `invite_join_failed` | `WARNING` | Invite join failed | `user_id` |
| `invite_regenerated` | `INFO` | Invite token rotated | `wishlist_id`, `user_id` |
| `favorites_listed` | `INFO` | Favorites fetched | `user_id`, `count` |
| `favorite_added` | `INFO` | Favorite added | `wishlist_id`, `user_id` |
| `favorite_removed` | `INFO` | Favorite removed | `wishlist_id`, `user_id` |
| `favorite_own_wishlist_denied` | `WARNING` | Self-favorite blocked | `wishlist_id`, `user_id` |
| `favorite_deleted_wishlist_denied` | `WARNING` | Deleted list blocked | `wishlist_id`, `user_id` |
| `view_history_listed` | `INFO` | History fetched | `user_id`, `count` |
| `view_history_recorded` | `INFO` | View recorded | `wishlist_id`, `user_id` |
| `view_history_cleared` | `INFO` | History cleared (once per delete) | `user_id`, `removed_count` |
| `wishlist_store_read` | `INFO` | State read | `wishlists_count` |
| `wishlist_store_write` | `INFO` | Changes committed | `wishlists_count` |
| `wishlist_repo_mutation` | `INFO` | Repo mutation | `entity`, `operation`, `count` |
| `background_worker_started` | `INFO` | Worker loop started | `interval_seconds` |
| `background_worker_stopped` | `INFO` | Worker loop stopped | None |
| `background_cleanup_completed` | `INFO` | Cleanup ok | `expired_tokens_cleaned`, `wishlists_purged`, `idempotency_records_cleaned`, `session_revocations_cleaned`, `birthdays_purged`, `bot_destinations_purged`, `receipt_keys_purged`, `duration_ms` |
| `background_cleanup_failed` | `ERROR` | Cleanup failed | `error`, `duration_ms` |
| `session_revocations_purged` | `INFO` | Expired revocations purged | `purged_count` |
| `account_deleted` | `INFO` | Account deleted (`AccountDeletionService`) | `subject_hash_prefix`, `deleted_lists`, `transferred_lists`, `cancelled_reservations`, `anonymized_items`, `duration_ms` |
| `account_deletion_already_deleted` | `INFO` | Idempotent delete | `subject_hash_prefix`, `duration_ms` |
| `account_deletion_failed` | `ERROR` | Delete rolled back | `subject_hash_prefix`, `error_class`, `duration_ms` |
| `wishlist_deleted_listed` | `INFO` | Deleted wishlists listed | `actor_id` / `user_id`, `count`, `retention_days` |
| `wishlist_restored_from_deleted` | `INFO` | Soft-deleted list restored | `wishlist_id`, `actor_id` / `user_id`, `from_status`, `to_status`, `retention_days` |
| `wishlist_restore_retention_expired` | `WARNING` | Service restore past retention | `wishlist_id`, `actor_id`, `retention_days` |
| `wishlist_retention_expired` | `WARNING` | HTTP 410 retention expired | `operation` |
| `public_link_rate_limited` | `WARNING` | Public share/invite link throttled (`wishenka.web.rate_limit`) | `route` (`/share/{token}`, `/invite/{token}`, `/invite/{token}/join`), `method`, `client_ip`, `retry_after` |
| `item_missing_parent_wishlist` | `ERROR` | `WishItem.wishlist` is `None` in `_require_item_wishlist` | `item_id`, `wishlist_id` |

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
├── WishlistRetentionExpiredError
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

#### `WishlistNotFoundError` (Missing Parent Wishlist Invariant)
- **Root Cause**: A `WishItem` was passed to `update_wish_item`, `create_reservation`,
  `record_item_fulfillment`, `cancel_item_receipt`, or `correct_item_receipt` with
  `item.wishlist is None`, triggering `WishlistService._require_item_wishlist(item)` and logging
  `item_missing_parent_wishlist` at `ERROR` level.
- **Resolution**: Ensure `WishItem` instances are hydrated or constructed with an attached
  `wishlist` reference before invoking mutation methods. Inspect `item_id` and `wishlist_id` in the
  `item_missing_parent_wishlist` log record.

#### `SelfReservationError`
- **Root Cause**: Recipient attempted to reserve an item designated for themselves.
- **Resolution**: Recipients cannot reserve their own gifts. Another collaborator or external gifter
  must reserve the item.

#### `WishlistArchivedError`
- **Root Cause**: Attempted to add/edit items or create reservations on an archived list.
- **Resolution**: Unarchive the wishlist via `unarchive_wishlist` prior to mutation.

#### `WishlistDeletedError`
- **Root Cause**: Requested wishlist has been soft-deleted.
- **Resolution**: Deleted wishlists cannot be viewed or modified. Within
  `WISHENKA_WISHLIST_RETENTION_DAYS`, the `Owner` can restore it via
  `WishlistService.restore_deleted_wishlist` (`POST /api/wishlists/{wishlist_id}/restore-deleted`);
  otherwise create a new wishlist.

#### `WishlistRetentionExpiredError`
- **Root Cause**: Attempted to restore a soft-deleted wishlist after its retention window
  (`WISHENKA_WISHLIST_RETENTION_DAYS`, default `30` days) expired.
- **Resolution**: HTTP routes return `410 Gone` (`code: "retention_expired"`). The list is
  eligible for permanent purge and can no longer be restored; create a new wishlist instead.

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
- **Root Cause**: A locked or busy database is `InventoryBusyError`; any other storage
  failure, including a non-token constraint violation, raises this error.
- **Resolution**: Verify database file permissions and health. Error traces suppress sensitive SQL
  parameters to protect token secrecy.

#### `429 Too Many Requests` on `/share/{token}` or `/invite/{token}`
- **Root Cause**: Client exceeded `WISHENKA_PUBLIC_RATE_LIMIT_MAX_REQUESTS` within
  `WISHENKA_PUBLIC_RATE_LIMIT_WINDOW_SECONDS`. Behind a reverse proxy, if
  `WISHENKA_PUBLIC_RATE_LIMIT_TRUST_PROXY_HEADERS` is `False`, all users may share the proxy's
  peer IP and trip the shared bucket.
- **Resolution**: Wait for the `Retry-After` interval, tune `WISHENKA_PUBLIC_RATE_LIMIT_*`
  settings, or enable `WISHENKA_PUBLIC_RATE_LIMIT_TRUST_PROXY_HEADERS=true` when deployed behind
  a trusted reverse proxy that sets `X-Forwarded-For` or `X-Real-IP`.
