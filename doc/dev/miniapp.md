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

## HTTP Endpoints Reference

| Endpoint | Method | Auth | CSRF | Description |
| :--- | :---: | :---: | :---: | :--- |
| `/` | `GET` | No | No | Returns the Telegram Mini App HTML shell. |
| `/api/auth/csrf` | `GET` | Yes | No | Issues session-bound CSRF token for forms. |
| `/api/wishlists/{id}/members` | `GET` | Yes | No | Returns list of members and roles. |
| `/api/wishlists/{id}/members/{uid}/role` | `PATCH` | Yes | Yes | Updates role (Owner only). |
| `/api/wishlists/{id}/members/{uid}` | `DELETE` | Yes | Yes | Removes member from wishlist. |
| `/api/wishlists/{id}/invite/reset` | `POST` | Yes | Yes | Rotates collaborator invite token. |
| `/api/invitations/preview` | `GET` | No | No | Previews invitation details via header. |
| `/api/invitations/accept` | `POST` | Yes | Yes | Accepts invite and joins wishlist. |

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
