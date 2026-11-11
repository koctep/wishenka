# Telegram Mini App Interface and Wishlist Management

## Overview

The Telegram Mini App (TMA) frontend and web layer provide a responsive, accessible interface
for managing personal and collaborative wishlists, administering members, and sharing gift links.

The Mini App runs inside the Telegram WebView and is served directly by FastAPI as a lightweight
server-rendered shell with progressive client-side enhancement. It operates in tandem with the
wishlists domain service and security middleware to satisfy four primary goals:

1. **Frictionless Creation**: Allow immediate creation of active empty wishlists without forced
   upfront metadata forms.
2. **Contextual Settings Management**: Let owners and administrators configure list metadata
   (title, description, event title, event date) with explicit persistence and cancellation.
3. **Collaborative Member Administration**: Provide distinct administrative controls for
   inviting collaborators, promoting/demoting administrators, and removing members.
4. **Secure Link Sharing**: Clearly separate public gift-selection links (`startapp=w_<token>`)
   from collaborator invitation links (`startapp=i_<token>`), protecting the Surprise Invariant
   and preventing accidental elevation of privileges.

---

## Architecture & Components

```
+---------------------------------------------------------------------------------+
|                           Telegram Client (WebView)                             |
|  - window.Telegram.WebApp (initData, openTelegramLink, shareUrl)                |
|  - Accessible HTML shell + static miniapp.js / miniapp.css                      |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
|                       BrowserSecurityMiddleware                                 |
|  - Enforces Origin header matches WISHENKA_APPLICATION_ORIGIN                   |
|  - Validates session-bound CSRF token (X-CSRF-Token) on state-changing requests |
|  - Adds Referrer-Policy: no-referrer, nosniff, and Cache-Control: no-store      |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
|                         FastAPI Web Endpoints                                   |
|  - GET /                               Mini App HTML shell with strict CSP      |
|  - GET /api/auth/csrf                  Session-bound CSRF token provider        |
|  - GET, PATCH /api/wishlists/{id}      Wishlist details & metadata settings     |
|  - /api/wishlists/{id}/members         Member administration & role management  |
|  - /api/wishlists/{id}/invite/reset    Collaborator invite token rotation       |
|  - /api/invitations/preview, accept    Collaborator onboarding flow             |
|  - GET, POST, DELETE /api/favorites    Favorites management & role badges       |
|  - GET, POST, DELETE /api/history      Viewing history tracking (20 bound)      |
|  - /web/wishlists/{id}/items/*         HTMX Quick Add, Preview & Edit Modal UI  |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
|                  WishlistService & SQLite Transactional Store                   |
|  - Contextual RBAC / ABAC policies (WishlistAccessPolicy)                       |
|  - Surprise Invariant projection filters                                        |
|  - Transactional serialization via BEGIN IMMEDIATE in SQLite WAL mode           |
+---------------------------------------------------------------------------------+
```

### Components

- **HTML Shell (`GET /`)**: Defined in
  [`wishenka.web.routes.miniapp`](../../wishenka/web/routes/miniapp.py). Renders an accessible
  skeleton (`#app`, `#status` live region) configured with `data-bot` and `data-miniapp` attributes.
  Applies strict Content-Security-Policy (CSP) headers restricting frames to Telegram.
- **Client Script (`static/miniapp.js`)**: Pure JavaScript application. Parses navigation
  parameters (`startapp`, hash/query), manages views, and performs API calls with session cookies
  and CSRF headers. Uses safe DOM manipulation (`textContent`) rather than HTML string interpolation
  to prevent Cross-Site Scripting (XSS).
- **Security Middleware (`BrowserSecurityMiddleware`)**: Defined in
  [`wishenka.web.security`](../../wishenka/web/security.py). Protects cookie-authenticated mutation
  requests against Cross-Site Request Forgery (CSRF) and Cross-Origin attacks.
- **Wishlist Routes (`wishenka.web.routes.wishlists`)**: Implements authenticated management APIs
  and public read projections.
- **HTMX Wish Item UI Routes (`wishenka.web.routes.items_ui`)**: Defined in
  [`wishenka/web/routes/items_ui.py`](../../wishenka/web/routes/items_ui.py). Serves server-rendered
  Jinja2 + HTMX views and partials for the wishlist detail page, universal quick-add bar, live URL
  preview card, detailed item creation/editing bottom-sheet modal, Reduction Lock enforcement, and
  safe item archiving/restoration.

---

## Security & CSRF Architecture

Because the Mini App operates in an embedded browser environment using cookie authentication
(`SameSite=None`), defense-in-depth protections prevent cross-site request forgery and data leakage.

### 1. Origin Verification

For unsafe HTTP methods (`POST`, `PATCH`, `DELETE`, `PUT`) using cookie sessions and for
`/api/auth/telegram`, `BrowserSecurityMiddleware` checks that the incoming `Origin` header
strictly matches the configured `application_origin`:

```python
if unsafe and request.url.path == "/api/auth/telegram":
    if origin != settings.application_origin:
        return JSONResponse({"detail": "Invalid origin"}, status_code=403)
```

Requests with missing or mismatched `Origin` headers are rejected with `403 Forbidden`.

### 2. Session-Bound CSRF Tokens

CSRF tokens are cryptographically derived from the user's active session cookie using HMAC-SHA256:

```text
token = HMAC-SHA256(csrf_secret_key, "wishenka-csrf-v1:" + session_cookie)
```

- The client retrieves a token via `GET /api/auth/csrf`.
- The token is sent in the `X-CSRF-Token` HTTP header on all mutating requests.
- The middleware computes the expected token for the current session and compares them in constant
  time (`hmac.compare_digest`).
- Tokens cannot be reused across different user sessions or stolen across origins.

### 3. Capability Token Redaction

Sharing tokens (`public_token`) and collaborator invitation tokens (`invite_token`) are bearer
capabilities. The application strictly adheres to the following token safety rules:

- **Header Delivery for Invites**: Invitation verification and acceptance use the `X-Invite-Token`
  request header instead of embedding tokens in API query strings.
- **Log Sanitization**: Raw token values are never written to application logs, audit events, or
  storage traces. Audit records capture only entity IDs (`wishlist_id`, `actor_id`).
- **HTTP Headers**: All responses include `Referrer-Policy: no-referrer`, preventing tokens in
  deep-link URLs from leaking to external websites.

---

## User Workflows & Management Views

### 1. Frictionless Wishlist Creation

- **Trigger**: User opens the Mini App and initiates wishlist creation.
- **API Call**: `POST /api/wishlists` with an empty JSON payload `{}`.
- **Behavior**: The server immediately creates an active personal wishlist with generated tokens.
  Creation does not require a title, description, or event date.
- **UI State**: The client navigates directly to the new wishlist view. If the title is empty,
  the UI presents a localized placeholder (`Мой вишлист`) and displays an entry point to add items.

### 2. Wishlist Settings Management

- **Permissions**: Available only to `Owner` and `Admin` roles.
- **Fields**:
  - `name`: List title (string, 1-255 characters).
  - `description`: Optional text notes.
  - `event_title`: Optional event name (e.g., "День рождения").
  - `event_date`: Optional ISO-8601 UTC timestamp.
- **Nullability**: Sending `null` or empty values clears optional event fields, allowing the list
  to remain ongoing without an event.
- **Client Handling**:
  - The form is pre-populated with current settings from `GET /api/wishlists/{id}`.
  - Submitting sends `PATCH /api/wishlists/{id}` with the updated fields and CSRF header.
  - Cancelling restores the original values without making a network request.
  - If a save fails, user inputs are preserved in the form along with an accessible error message.

### 3. Member Administration

Collaborative wishlists allow multiple users to maintain wish items together.

```
+---------------+-------------------+---------------------------------------------------+
| Role          | Assigned By       | Permissions                                       |
+---------------+-------------------+---------------------------------------------------+
| Owner         | Creator (Fixed)   | Full control: edit settings, invite/remove members|
|               |                   | promote/demote admins, transfer ownership, delete.|
| Admin         | Owner             | Edit settings, invite members, remove members,   |
|               |                   | rotate public & invite tokens. Cannot alter admins|
| Member        | Owner or Admin    | Add and edit wishlist items. Cannot edit settings |
|               |                   | or manage members.                                |
+---------------+-------------------+---------------------------------------------------+
```

#### Endpoints:
- `GET /api/wishlists/{id}/members`: Lists current members with roles and user identifiers.
- `PATCH /api/wishlists/{id}/members/{user_id}/role`: Changes member role (`admin` $\leftrightarrow$
  `member`). Only permitted for the `Owner`.
- `DELETE /api/wishlists/{id}/members/{user_id}`: Removes a collaborator. Owners can remove anyone;
  Admins can remove regular members; members cannot remove managers.

### 4. Collaborator Invitation Flow

Collaborator invitations grant editing access and must never be conflated with public gift links.

1. **Invitation Link Generation**:
   - URL format: `https://t.me/<bot_username>/<app_name>?startapp=i_<invite_token>`
   - Managers copy or share the invitation link from the membership panel.
   - Calling `POST /api/wishlists/{id}/invite/reset` revokes the previous token and issues a new
     one with a 7-day TTL.
2. **Invitation Preview**:
   - When opened via `startapp=i_<token>`, the client calls `GET /api/invitations/preview`
     with `X-Invite-Token: <token>`.
   - The server validates that the token is active, unexpired, and belongs to an active wishlist.
   - The UI displays the wishlist name, clearly communicates that the link grants collaborator
     access, and prompts for explicit confirmation. No state mutation occurs on preview.
3. **Invitation Acceptance**:
   - The user clicks the confirm button.
   - The client sends `POST /api/invitations/accept` with `X-Invite-Token: <token>` and CSRF token.
   - The user is added as a `Member`, and the wishlist format transitions to `collaborative`.

### 5. Public Gift-Selection Sharing

Public links allow gift givers to view items and make reservations without collaborator privileges.

- **URL format**: `https://t.me/<bot_username>/<app_name>?startapp=w_<public_token>`
- **Copy Link**: Copies the full URL to the clipboard using `navigator.clipboard.writeText`.
  Status is announced politely via `aria-live`.
- **Telegram Share**: Uses `window.Telegram.WebApp.openTelegramLink` with a `t.me/share/url`
  deep link to open the Telegram chat chooser.
- **Zero Onboarding**: Public viewers do not need to register, complete forms, or authenticate.
- **Surprise Protection**: Reservation counts, buyer names, and gift statuses are strictly
  withheld from recipients in compliance with the Surprise Invariant.

---

### 6. Categorized Home Screen Sections & Role Badges

The Mini App home screen organizes wishlists into three distinct semantic sections (`<section>`
elements with `role="region"` and accessible `aria-label` attributes):

1. **"My wishlists"** (`aria-label="My wishlists"`): Displays wishlists where the authenticated
   user is the owner (`role: "owner"`). If empty, shows "No personal wishlists yet".
2. **"Collaborating"** (`aria-label="Collaborating"`): Displays wishlists where the authenticated
   user is an active collaborator with `role: "admin"` or `role: "member"`. If empty, shows
   "No collaborative wishlists yet".
3. **"Favorites"** (`aria-label="Favorites"`): Displays wishlists saved by the user. If empty,
   shows "No favorites yet". Each card includes an explicit "Remove" button for quick unfavoriting.

#### Role Badges & Precedence Rules

Each wishlist card displays a localized visual badge indicating the user's role on that list:
- `owner` $\rightarrow$ **«Владелец»** (`badge badge-owner`)
- `admin` $\rightarrow$ **«Администратор»** (`badge badge-admin`)
- `member` $\rightarrow$ **«Соавтор»** (`badge badge-member`)
- `favorite` $\rightarrow$ **«Избранное»** (`badge badge-favorite`)

**Role Precedence Rule**:
```text
owner > admin > member > favorite
```
If an active collaborator (`admin` or `member`) also adds that wishlist to their favorites, the
collaborative operational role strictly takes precedence over `favorite` in both the card badge and
the home section placement. The wishlist appears in the "Collaborating" section with their
collaborator badge (`Администратор` or `Соавтор`).

---

### 7. Favorites Management & Zero-Leak Guarantees

The Favorites feature provides quick access to external wishlists of interest without requiring
collaborator membership:

- **Adding to Favorites**: Calling `POST /api/favorites/{wishlist_id}` with session and CSRF
  adds the wishlist. On the wishlist detail screen (`showList`), a toggle button displays
  "Add to favorites" or "Remove from favorites".
- **Self-Favoriting Guard**: Users cannot favorite their own wishlists (`wl.owner_id == user_id`).
  Any self-favoriting attempt raises `ValueError`, returning HTTP 400
  (`Cannot favorite own wishlist`) and emitting a security warning audit event
  (`favorite_own_wishlist_denied`). The Mini App UI hides the favorite button for owned wishlists.
- **Removing from Favorites**: Calling `DELETE /api/favorites/{wishlist_id}` removes the entry.
- **Zero-Leak Guarantee (Surprise Invariant)**: Responses from `GET /api/favorites` return clean
  wishlist projections with public metadata (`id`, `name`, `description`, `event_title`,
  `event_date`, `status`, `role`, `is_favorite`). They strictly withhold all reservation entries,
  buyer identities, and item booking counts, ensuring complete privacy for gift surprises.

---

### 8. Viewing History & Automated Tracking

Viewing history allows users to re-access recently visited wishlists:

- **Automatic View Recording**: When an authenticated user opens any wishlist (`showList`), the
  client dispatches an asynchronous background request `POST /api/history/{id}`.
- **History View (`showHistory()`)**:
  - Accessible via the "Viewing history" button in the home top navigation bar.
  - Lists visited wishlists in reverse-chronological order, displaying the list title, relative or
    localized visit timestamp (`Viewed: <date>`), and role badge (if applicable).
  - An accessible "Clear history" button triggers `DELETE /api/history` to erase
    all history entries.
  - When history is empty, an accessible notice "No viewing history yet" is shown.
- **Deduplication**: Re-visiting an already recorded wishlist updates its `viewed_at` timestamp
  rather than appending a duplicate row.
- **20-Entry Bound**: Viewing history is strictly bounded to at most 20 entries per user. When a
  21st entry is added, the oldest entry is automatically pruned from persistence.
- **Zero-Leak Guarantees**: History endpoints (`GET /api/history`) project only sanitized list
  metadata and omit all reservation records and buyer details.

---

### 9. Wish Item Quick-Add Bar, Live Preview & Detailed Edit Sheet (HTMX UI)

The wish item UI in [`wishenka/web/routes/items_ui.py`](../../wishenka/web/routes/items_ui.py)
provides a mobile-first HTMX workflow for adding, previewing, editing, archiving, and restoring
wish items without full-page reloads.

#### 9.1. Wishlist Detail View & Role-Based UI Gating (`wishlist_detail.html`)
- **Endpoint**: `GET /web/wishlists/{wishlist_id}` (`view_wishlist_detail`).
- **Template**: [`wishenka/web/templates/wishlist_detail.html`](../../wishenka/web/templates/wishlist_detail.html).
- **Access Control**: Evaluates `can_edit_wishlist` via
  `WishlistAccessPolicy.can_add_or_edit_item(ctx, wishlist)`.
  - `can_edit_wishlist == True` only for active members (`OWNER`, `ADMIN`, `MEMBER`) when the
    wishlist status is `active`.
  - When `can_edit_wishlist` is false (anonymous guests, external gifters, or archived wishlists),
    both `#quick-add-bar` and the per-card `.btn-edit-item` triggers are omitted from the DOM.
  - All mutating UI endpoints enforce `_ensure_member_and_active`, returning `404 Not Found` for
    non-members and `409 Conflict` if the wishlist is archived.

#### 9.2. Universal Quick Add Bar (`partials/item_quick_add.html`)
- **Template**: [`wishenka/web/templates/partials/item_quick_add.html`](../../wishenka/web/templates/partials/item_quick_add.html).
- **Viewport Positioning**: Pinned to the bottom of the screen via `.quick-add-container` in
  `static/miniapp.css` (`position: fixed; bottom: 0; padding-bottom: max(12px,
  env(safe-area-inset-bottom))`). Interactive controls enforce `min-height: 44px` touch targets.
- **Debounced Live Preview Trigger**: The input `#quick-add-input` (`name="raw_input"`) is bound
  with:
  - `hx-post="/web/wishlists/{{ wishlist.id }}/items/preview"`
  - `hx-trigger="input changed delay:500ms, paste"`
  - `hx-target="#quick-add-preview-target"` and `hx-swap="innerHTML"`
- **Actions**:
  - **«Добавить» (`#btn-quick-add`)**: Submits `#quick-add-form` via
    `hx-post="/web/wishlists/{{ wishlist.id }}/items/quick"` (`quick_add_item`), appending the new
    card to `#items-list` (`hx-swap="beforeend"`).
  - **«Подробнее» (`#btn-quick-details`)**: Opens the creation bottom-sheet modal via
    `hx-get="/web/wishlists/{{ wishlist.id }}/items/new"` (`get_new_item_modal`) with
    `hx-include="#quick-add-form"`, transferring any typed text or previewed metadata into the
    detailed form.

#### 9.3. Live URL Preview Card & Graceful Fallback (`partials/item_preview_card.html`)
- **Endpoint**: `POST /web/wishlists/{wishlist_id}/items/preview` (`preview_item_input`).
- **Template**: [`wishenka/web/templates/partials/item_preview_card.html`](../../wishenka/web/templates/partials/item_preview_card.html).
- **Plain Text Fast-Path**: When `UniversalInputClassifier.classify(raw_input)` returns
  `InputType.PLAIN_TEXT`, the endpoint immediately returns an empty `200 OK` HTML response without
  making outbound network requests.
- **Rich URL Preview**: For `EXPLICIT_URL`, `IMPLICIT_URL`, and `COMPOSITE_SHARE`,
  `ItemPreviewService.fetch_preview` extracts metadata and renders `#item-preview-card` with:
  - Product thumbnail (`preview.image_url`), store badge (`preview.store_name`), cleaned title
    (`preview.title`), and price (`preview.price`, `preview.currency`).
  - Hidden `<input type="hidden">` fields (`link`, `price`, `currency`, `image_url`, `store_name`,
    `title`) inside `#quick-add-form` so clicking «Добавить» persists all scraped fields in one tap,
    and clicking «Подробнее» carries them into the creation modal.
  - Dismiss button (`✕`, `.btn-preview-dismiss`) clearing `#quick-add-preview-target`.
- **Graceful Fallback (`preview.is_fallback` or missing title)**: When scraping hits anti-bot
  protection, timeouts, or SSRF restrictions, the preview card displays the sanitized URL and
  store badge alongside an inline `<input type="text" name="title">` prompting the user to enter
  the gift title manually or open «Подробнее».

#### 9.4. Quick-Add Submission & HTMX Out-of-Band (`hx-swap-oob`) Updates
- **Endpoint**: `POST /web/wishlists/{wishlist_id}/items/quick` (`quick_add_item`, quick-add route).
- **Behavior**: Creates the wish item via `WishlistService.add_wish_item` (preferring explicit
  `title` from preview/modal over `raw_input`, defaulting to `quantity=1` and `currency="RUB"`).
- **Response (`201 Created`)**:
  - Primary payload: Rendered [`partials/item_card.html`](../../wishenka/web/templates/partials/item_card.html)
    appended to `#items-list`.
  - Out-of-Band (`hx-swap-oob`) fragments in the same response:
    1. `<div id="quick-add-preview-target" hx-swap-oob="innerHTML"></div>` — clears the preview
       card.
    2. `<input type="text" id="quick-add-input" ... value="" hx-swap-oob="true" />` — resets the
       quick-add input field while preserving its HTMX attributes.
    3. `<div id="empty-items-placeholder" hx-swap-oob="delete"></div>` — removes the empty-list
       placeholder if present.
    4. `<div id="item-modal-container" hx-swap-oob="innerHTML"></div>` — closes the creation modal
       when submitted from `#item-detailed-form`.

#### 9.5. Detailed Creation & Edit Bottom-Sheet Modal (`partials/item_edit_modal.html`)
- **Template**: [`wishenka/web/templates/partials/item_edit_modal.html`](../../wishenka/web/templates/partials/item_edit_modal.html).
- **Creation Mode (`is_edit=False`)**:
  - Loaded via `GET /web/wishlists/{wishlist_id}/items/new` (`get_new_item_modal`, new-modal route).
  - Prepopulates `title`, `link`, `price`, `currency`, and `image_url` from query parameters or
    classifies `raw_input` via `UniversalInputClassifier`.
  - Submits to `POST /web/wishlists/{wishlist_id}/items/quick`.
- **Edit Mode (`is_edit=True`)**:
  - Loaded via `GET /web/wishlists/{wishlist_id}/items/{item_id}/edit` (`get_edit_item_modal`).
  - Submits to `POST /web/wishlists/{wishlist_id}/items/{item_id}/edit` (`submit_edit_item`),
    replacing `#item-card-{item_id}` (`hx-swap="outerHTML"`) and closing `#item-modal-container`
    via `hx-swap-oob="innerHTML"`.
- **Supported Fields**: `title` (required, 1..255 chars), `link`, `price`, `currency` (`RUB`,
  `USD`, `EUR`, `KZT`, `BYN`), `quantity` (1..1000 stepper), collaborative recipient targeting
  (`recipient_user_id` dropdown and `recipient_name` input rendered only when
  `is_collaborative=True`), `description` (up to 4000 chars), `image_url` (with live thumbnail),
  `priority` (`low`, `medium`, `high`), and `category`.

#### 9.6. Reduction Lock UI, HTTP 409 Recovery & Surprise Invariant
- **Reduction Lock Calculation**:
  $$\text{locked\_quantity} = \text{reserved\_quantity} + \text{received\_quantity}$$
  $$\text{min\_quantity} = \max(1, \text{locked\_quantity})$$
- **Client-Side Stepper & Banner**:
  - `#item-quantity-input` sets `min="{{ min_quantity }}"` and the decrement button (`-`) stops at
    `min_quantity`.
  - When `locked_quantity > 0`, an amber informational banner is rendered:
    `ℹ️ Забронировано дарителями: {locked_quantity} шт. Нельзя указать меньше забронированного объема.`
- **Server-Side HTTP 409 Conflict Recovery**:
  - If `POST /web/wishlists/{wishlist_id}/items/{item_id}/edit` catches
    `CannotReduceQuantityBelowReservedError` (e.g., a gifter reserved units while the modal was
    open, or the user manually typed a lower value), the server returns HTTP `409 Conflict` with
    `partials/item_edit_modal.html`.
  - The modal displays a `role="alert"` error message (`error_message`) and preserves all
    user-submitted form values (`submitted_form`) without data loss.
- **Surprise Invariant & XSS Protection**:
  - Neither `get_edit_item_modal` nor `partials/item_card.html` ever exposes individual
    `item.reservations` or gifter identities (`user_id`, `username`, `first_name`) to the
    recipient; only the aggregate `locked_quantity` bound is surfaced.
  - All templates rely on Jinja2 auto-escaping (`{{ item.title }}`, `{{ item.description }}`)
    without `|safe` filters, preventing XSS injection from scraped or user-supplied strings.

#### 9.7. Safe Item Archiving & Restoration via HTMX
- **Archive**: `POST /web/wishlists/{wishlist_id}/items/{item_id}/archive` (`archive_item_ui`),
  triggered from the edit modal with `hx-confirm`. Calls `WishlistService.archive_wish_item`
  (preserving existing gifter reservations) and returns `200 OK` with OOB swaps deleting
  `#item-card-{item_id}` (`hx-swap-oob="delete"`) and emptying `#item-modal-container`.
- **Restore**: `POST /web/wishlists/{wishlist_id}/items/{item_id}/restore` (`restore_item_ui`).
  Calls `WishlistService.restore_wish_item` (appending the item to the tail of active items while
  retaining reservations) and returns `200 OK` with the rendered `partials/item_card.html`.

#### 9.8. Vertical Items List: Compact/Expanded Cards, Manual Order, Archived Section (WISHENKA-15)
- **Layout**: `wishlist_detail.html` renders `#items-list` from `partials/items_list.html`, which
  includes `partials/item_card.html` per item (`is_first`/`is_last` drive disabled move buttons).
  Archived items render below via `partials/archived_items_section.html` (owner/editor only).
- **Compact/expanded**: each card is a `<details>`; the summary row is the compact state and
  `toggleWishCard(event, summary)` (in `base.html`) toggles it. Clicks on `a, button, input, select,
  textarea` or any `[data-no-toggle]` element do not toggle the card.
- **Manual order** (editors only):
  - Buttons: `POST /web/wishlists/{id}/items/{item_id}/move?direction=up|down` (`move_item_ui`).
  - Drag-and-drop: inline JS in `base.html` handles native HTML5 `dragstart/dragover/drop` on
    `.item-card[draggable="true"]` inside `#items-list`, then posts the full order to
    `POST /web/wishlists/{id}/items/reorder` with repeated form field `item_ids` (`reorder_items_ui`).
  - Both return the re-rendered `partials/items_list.html` (`hx-target="#items-list"`). The submitted
    ids must be an exact permutation of the active items, otherwise `400`.
- **Archive flow**: `GET .../items/{item_id}/archive-confirm` (`archive_confirm_ui`) opens
  `partials/item_archive_modal.html`; it warns about active reservations when the wishlist flag
  `warn_on_delete_reserved` is true (default `1`; column added to `wl_lists` by the store migration).
  `POST .../archive` and `.../restore` also refresh `#archived-items-section` via an OOB swap.

---

## HTTP Endpoints Reference

| Endpoint | Method | Auth | CSRF | Description |
| :--- | :---: | :---: | :---: | :--- |
| `/` | `GET` | No | No | Returns the Telegram Mini App HTML shell. |
| `/api/auth/csrf` | `GET` | Yes | No | Issues session-bound CSRF token for forms. |
| `/api/wishlists` | `GET` | Yes | No | Lists user's wishlists (owner and member). |
| `/api/wishlists` | `POST` | Yes | Yes | Creates an empty personal wishlist. |
| `/api/wishlists/{id}` | `GET` | Yes | No | Returns wishlist details and item view. |
| `/api/wishlists/{id}` | `PATCH` | Yes | Yes | Updates title, description, or event. |
| `/api/wishlists/{id}/members` | `GET` | Yes | No | Returns list of members and roles. |
| `/api/wishlists/{id}/members/{uid}/role` | `PATCH` | Yes | Yes | Updates role (Owner only). |
| `/api/wishlists/{id}/members/{uid}` | `DELETE` | Yes | Yes | Removes member from wishlist. |
| `/api/wishlists/{id}/invite/reset` | `POST` | Yes | Yes | Rotates collaborator invite token. |
| `/api/invitations/preview` | `GET` | No | No | Previews invitation details via header. |
| `/api/invitations/accept` | `POST` | Yes | Yes | Accepts invite and joins wishlist. |
| `/api/favorites` | `GET` | Yes | No | Lists user's favorited wishlists. |
| `/api/favorites/{id}` | `POST` | Yes | Yes | Adds wishlist to user's favorites. |
| `/api/favorites/{id}` | `DELETE` | Yes | Yes | Removes wishlist from favorites. |
| `/api/history` | `GET` | Yes | No | Lists up to 20 recent wishlists. |
| `/api/history/{id}` | `POST` | Yes | Yes | Records wishlist viewing in history. |
| `/api/history` | `DELETE` | Yes | Yes | Clears viewing history for caller. |
| `/web/wishlists/{wishlist_id}` | `GET` | Optional | No | Renders TMA wishlist detail HTML page. |
| `/web/wishlists/{wishlist_id}/items/preview` | `POST` | Yes | Yes | Classifies input & renders preview card. |
| `/web/wishlists/{wishlist_id}/items/quick` | `POST` | Yes | Yes | Quick-adds item & returns card + OOB reset. |
| `/web/wishlists/{wishlist_id}/items/new` | `GET` | Yes | No | Renders prepopulated item creation modal. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/edit` | `GET` | Yes | No | Renders item edit modal with Reduction Lock. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/edit` | `POST` | Yes | Yes | Saves item edits or returns 409 modal. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/archive` | `POST` | Yes | Yes | Archives item & removes card via OOB swap. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/restore` | `POST` | Yes | Yes | Restores archived item & renders card. |
| `/web/wishlists/{wishlist_id}/items/reorder` | `POST` | Yes | Yes | Persists full manual order (`item_ids`); returns items list. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/move?direction=up\|down` | `POST` | Yes | Yes | Moves item one step; returns items list. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/archive-confirm` | `GET` | Yes | No | Renders archive confirmation modal. |

---

## Structured UI Observability Events

The HTMX wish item UI router (`wishenka.web.items_ui`) emits structured telemetry records via
`extra={...}`:

| Event Name | Level | Context Attributes | Description |
| :--- | :---: | :--- | :--- |
| `ui_item_quick_add_preview` | `INFO` | `wishlist_id`, `actor_id`, `user_id`, `input_type`, `domain`, `store_name`, `is_fallback`, `duration_ms` | Universal input classified and preview or fallback rendered. |
| `ui_item_quick_add_success` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `has_link`, `price`, `quantity` | Wish item created via Quick Add Bar or creation modal. |
| `ui_item_edit_opened` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `mode`, `locked_quantity`, `is_collaborative` | Item modal opened (`mode="create"` or `mode="edit"`). |
| `ui_reduction_lock_rendered` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `locked_quantity` | Edit modal rendered with active Reduction Lock (`locked_quantity > 0`). |
| `ui_reduction_lock_rejected` | `WARNING` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `requested_quantity`, `locked_quantity` | Edit rejected (HTTP 409) due to quantity below locked reservations. |
| `ui_item_edit_saved` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `quantity`, `has_recipient` | Wish item edits persisted via detailed edit modal. |
| `ui_item_archived` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id` | Wish item archived via HTMX UI. |
| `ui_item_restored` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id` | Archived wish item restored via HTMX UI. |

### Telemetry Privacy Invariants
- **Zero Raw URLs Logged**: Only the normalized hostname (`domain`, e.g., `ozon.ru`) and canonical
  `store_name` are recorded; full URLs, paths, and query parameters are never written to logs.
- **Zero Secrets or Capability Tokens**: `public_token`, `invite_token`, and session tokens are
  never logged.
- **Surprise Invariant in Logs**: UI logs record only aggregate `locked_quantity` and never log
  gifter identities (`user_id`, `username`, or `first_name` of gifters).

---

## Configuration Reference

The following settings configure the Mini App and web security layer:

| Setting | Env Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| `application_origin` | `WISHENKA_APPLICATION_ORIGIN` | `http://testserver` | Expected Origin. |
| `csrf_secret_key` | `WISHENKA_CSRF_SECRET_KEY` | `wishenka_csrf...` | CSRF secret key. |
| `telegram_bot_username` | `WISHENKA_TELEGRAM_BOT_USERNAME` | `""` | Bot username for URLs. |
| `telegram_app_short_name`| `WISHENKA_TELEGRAM_APP_SHORT_NAME` | `""` | App name for deep links. |

---

## Troubleshooting & Common Issues

### 1. `403 Invalid origin`
- **Cause**: The `Origin` header sent by the client does not match `WISHENKA_APPLICATION_ORIGIN`.
- **Solution**: Set `WISHENKA_APPLICATION_ORIGIN` to match the actual domain serving the Mini App
  (e.g., `https://app.wishenka.example.com`).

### 2. `403 Invalid CSRF token`
- **Cause**: The request is missing the `X-CSRF-Token` header, or the token was derived from an
  expired or mismatched session cookie.
- **Solution**: Ensure the frontend requests `GET /api/auth/csrf` after session establishment and
  includes the token on all mutating requests.

### 3. `404 Invitation not found`
- **Cause**: The invitation token is expired (default TTL 7 days), malformed, or was rotated via
  `POST /api/wishlists/{id}/invite/reset`.
- **Solution**: Have a wishlist manager generate and share a new invitation link.

### 4. `409 Wishlist is archived`
- **Cause**: Mutation attempt (editing settings, resetting tokens, adding members) on an archived
  wishlist.
- **Solution**: Restore the wishlist via `POST /api/wishlists/{id}/restore` before editing.

### 5. Clipboard Copy Fails in Telegram WebView
- **Cause**: Some mobile WebViews restrict `navigator.clipboard` access without direct user gesture.
- **Solution**: The Mini App provides an explicit fallback input displaying the link so users
  can manually select and copy if the automated API fails.

### 6. `400 Cannot favorite own wishlist`
- **Cause**: An owner attempted to favorite their own wishlist via `POST /api/favorites/{id}`.
- **Solution**: The UI suppresses the favorite button on owned lists. On direct API calls, verify
  that caller does not match `wishlist.owner_id`.

### 7. `404 Wishlist not found` on Favorites or History
- **Cause**: The referenced wishlist does not exist or has been soft-deleted (`DELETED`).
- **Solution**: Deleted wishlists cannot be favorited or viewed in history. Ensure the wishlist ID
  is valid and active.

### 8. `409 Conflict` When Saving Item Quantity in Edit Modal (`ui_reduction_lock_rejected`)
- **Cause**: The requested `quantity` is lower than `reserved_quantity + received_quantity` (e.g., a
  gifter booked additional units while the edit sheet was open).
- **Solution**: The server re-renders `partials/item_edit_modal.html` with HTTP 409, preserving all
  edited fields and updating `min_quantity` to the current `locked_quantity`. Set `quantity` to at
  least `locked_quantity` and submit again.

### 9. Quick Add Bar (`#quick-add-bar`) Not Displayed on Wishlist Page
- **Cause**: The caller is viewing the wishlist as a guest/gifter (not an `OWNER`, `ADMIN`, or
  `MEMBER`), or the wishlist is in `ARCHIVED` status.
- **Solution**: Authenticate as an active wishlist member and ensure the wishlist is `active`.

### 10. Reorder Returns `400` or Drag-and-Drop Does Nothing
- **Cause**: `item_ids` is not an exact permutation of active items (stale page after another
  editor archived/added an item), or the card is not `draggable="true"` (non-editor view).
- **Solution**: Reload the wishlist page and retry; logged as `ui_items_reorder_rejected`.
