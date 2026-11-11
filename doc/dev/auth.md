# Authentication and Session Management

## Overview

The `wishenka.auth` module provides end-to-end authentication and stateless session management for the **Wishlist Service («Вишенка»)** Telegram Mini App (TMA).

Because the application runs inside Telegram WebView and serves dynamic interfaces using **FastAPI + Jinja2 + HTMX**, the authentication architecture satisfies three key goals:
1. **Cryptographic verification**: Validate the initial Telegram WebApp `initData` using HMAC-SHA256 and the Telegram Bot API token.
2. **Stateless signed sessions**: Issue lightweight HMAC-SHA256 signed session tokens that require no database lookups or external cache on subsequent requests ($O(1)$ memory verification).
3. **Dual-mode credentials**: Support native browser cookie transmission for HTMX requests while simultaneously accepting `Authorization: Bearer <token>` headers for REST API clients and test suites.

```
+-----------------------------------------------------------------------------------+
|                              Telegram Client / Mini App                           |
| 1. Launch TMA -> window.Telegram.WebApp.initData                                  |
| 2. POST /api/auth/telegram {"init_data": "..."}                                   |
+-----------------------------------------------------------------------------------+
                                        |
                                        v
+-----------------------------------------------------------------------------------+
|                                FastAPI Backend                                    |
| 1. validate_telegram_init_data(...)                                               |
|    - Verify HMAC-SHA256 signature using bot_token                                 |
|    - Check auth_date expiration & clock drift                                     |
|    - Parse TelegramUser payload                                                   |
| 2. SessionTokenService.create_token(...)                                          |
|    - Pack SessionClaims (telegram_id, username, exp, iat)                         |
|    - Sign token (<payload_b64>.<sig_b64>) with secret_key                         |
| 3. Set-Cookie: session_id=<token>; HttpOnly; Secure; SameSite=None                |
|    Return JSON: {"token": "...", "user": {...}}                                   |
+-----------------------------------------------------------------------------------+
                                        |
                                        v
+-----------------------------------------------------------------------------------+
|                        Subsequent HTMX / API Requests                             |
| - HTMX sends Cookie: session_id=<token>                                           |
| - API clients send Authorization: Bearer <token>                                  |
| - Depends(get_current_user) verifies signature & expiry -> AuthenticatedUser      |
+-----------------------------------------------------------------------------------+
```

---

## Architecture & Components

The authentication subsystem is organized into modular components under `wishenka.auth` and `wishenka.web.routes.auth`:

```
wishenka/
├── auth/
│   ├── __init__.py           # Public exports
│   ├── models.py             # DTOs, schemas, and exception hierarchy
│   ├── init_data.py          # Telegram initData cryptographic validation
│   ├── session.py           # Signed session tokens and cookie helpers
│   └── dependencies.py      # FastAPI security dependencies
└── web/
    ├── routes/
    │   └── auth.py          # Endpoints: /api/auth/telegram, /logout, /me, /csrf
    └── security.py          # CSRF and Origin verification (see doc/dev/miniapp.md)
```

### 1. `wishenka.auth.init_data`
Provides cryptographic parsing and verification for Telegram WebApp initialization data:
- `validate_telegram_init_data(init_data_raw, bot_token, max_age_seconds, clock_drift_seconds)`: Parses query parameters, verifies HMAC-SHA256 signature against `bot_token`, enforces timestamp freshness, and returns a validated `TelegramUser`.
- `parse_telegram_init_data(init_data_raw)`: Parses query string into `TelegramInitData` DTO without cryptographic verification.
- `TelegramInitDataValidator`: Stateful validator class encapsulating `bot_token` and TTL settings.

### 2. `wishenka.auth.session`
Handles stateless session token issuance, signature verification, and HTTP cookie lifecycle:
- `SessionTokenService`: Generates and verifies URL-safe signed tokens in `<payload_b64>.<sig_b64>` format using HMAC-SHA256.
- `SessionClaims`: Pydantic model representing claims embedded inside the token payload (`telegram_id`, `first_name`, `username`, `iat`, `exp`).
- `set_session_cookie(response, token, settings)`: Sets the `HttpOnly`, `SameSite=None`, `Secure` session cookie on outgoing responses.
- `delete_session_cookie(response, settings)`: Clears the session cookie on logout.

### 3. `wishenka.auth.dependencies`
FastAPI dependency injection utilities for protecting route handlers:
- `get_current_user`: Enforces valid authentication. Returns `AuthenticatedUser` or raises `HTTPException(401)`.
- `get_optional_current_user`: Resolves `AuthenticatedUser` if valid credentials exist, or returns `None` for public/guest requests.
- `get_settings`: Resolves `Settings` instance from `request.app.state` or instantiates default settings.

### 4. `wishenka.auth.models`
Defines domain models, request/response schemas, and exception types:
- `AuthenticatedUser`: Request caller identity (`telegram_id`, `first_name`, `username`, `auth_method`).
- `TelegramUser`: Telegram user profile extracted from `initData` (`id`, `first_name`, `last_name`, `username`, `language_code`, `is_premium`).
- `TelegramInitData`: Parsed representation of raw initData query parameters.
- `TelegramAuthRequest`: Request schema for `POST /api/auth/telegram` containing `init_data: str`.
- `AuthResponse`: Response schema containing `token: str` and `user: TelegramUser`.
- Exception hierarchy:
  - `AuthValidationError`: Base exception for all authentication failures.
  - `InvalidSignatureError`: Raised when HMAC signature does not match.
  - `ExpiredInitDataError`: Raised when `auth_date` is expired or too far in the future.
  - `MalformedInitDataError`: Raised when the query string is empty, missing required keys (`hash`, `auth_date`, `user`), or contains invalid JSON.

### 5. `wishenka.web.routes.auth`
FastAPI APIRouter mounted at `/api/auth`:
- `POST /api/auth/telegram`: Exchanges raw `initData` for a signed session token and sets the session cookie.
- `POST /api/auth/logout`: Clears the session cookie and logs audit event.
- `GET /api/auth/me`: Returns identity attributes of current caller.

---

## Cryptographic Validation Protocol

Telegram Mini Apps sign initialization query strings with the bot token. The backend verifies this signature before trusting any data.

### Step-by-Step Verification Algorithm

1. **Parse Query String**:
   The raw query string (e.g. `auth_date=1700000000&user=...&hash=...`) is parsed into key-value pairs using `urllib.parse.parse_qsl(keep_blank_values=True)`.

2. **Extract and Isolate Hash**:
   The `hash` parameter is removed from the dictionary and kept as `received_hash`. If `hash` is missing, validation fails with `MalformedInitDataError`.

3. **Construct Data Check String**:
   All remaining key-value pairs are sorted alphabetically by key and concatenated with newline characters `\n`:
   ```python
   data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
   ```

4. **Derive Secret Key**:
   A secret key is derived using HMAC-SHA256 with the constant string `"WebAppData"` as key, and the bot token as message:
   $$\text{secret\_key} = \text{HMAC-SHA256}(\text{key} = b\text{"WebAppData"}, \text{msg} = \text{bot\_token.encode("utf-8")}).\text{digest}()$$

5. **Compute Expected Hash**:
   The signature is computed over `data_check_string` using `secret_key`:
   $$\text{expected\_hash} = \text{HMAC-SHA256}(\text{key} = \text{secret\_key}, \text{msg} = \text{data\_check\_string.encode("utf-8")}).\text{hexdigest}()$$

6. **Constant-Time Comparison**:
   The received hash is verified against the expected hash using `hmac.compare_digest` to prevent timing attacks:
   ```python
   if not hmac.compare_digest(expected_hash, received_hash):
       raise InvalidSignatureError("Telegram initData signature verification failed")
   ```

7. **Timestamp Freshness & Clock Drift Checks**:
   The `auth_date` parameter (Unix timestamp) is validated against the server clock:
   - **Future drift**: If `auth_date > now + clock_drift_seconds` (default 60s), reject with `ExpiredInitDataError`.
   - **Replay / age check**: If `now - auth_date > max_age_seconds` (default 86400s / 24 hours), reject with `ExpiredInitDataError`.

8. **User Deserialization**:
   The `user` JSON string is parsed and validated against `TelegramUser`.

---

## Session Token and Cookie Architecture

Wishenka uses a **stateless signed token** pattern designed for high-throughput HTMX interactions without database overhead.

### Token Structure

Session tokens are formatted as:
```text
<payload_b64>.<sig_b64>
```

- `<payload_b64>`: URL-safe Base64-encoded JSON representation of `SessionClaims` (without trailing padding `=`).
- `<sig_b64>`: URL-safe Base64-encoded HMAC-SHA256 digest of `<payload_b64>` signed with `settings.secret_key`.

```python
claims = SessionClaims(
    telegram_id=279058397,
    first_name="Vladislav",
    username="vlad",
    iat=1700000000,
    exp=1702592000,
)
```

### Dual-Mode Authentication

FastAPI dependencies check credentials in the following order:
1. **Authorization Header**: `Authorization: Bearer <token>`
   - Detected first.
   - Sets `AuthenticatedUser.auth_method = "bearer"`.
   - Used by API clients, automated scripts, and test cases.
2. **Session Cookie**:
   - Checked if no Bearer header is present.
   - Looks for `settings.session_cookie_name` (default `session_id`), with fallback to `wishenka_session`.
   - Sets `AuthenticatedUser.auth_method = "cookie"`.
   - Used by HTMX and Mini App WebView browsers.

### Cookie Configuration for Telegram Mini Apps

Telegram Mini Apps frequently run in cross-site iframes (e.g. `https://web.telegram.org` embedding `https://your-domain.com`). This requires specific cookie attributes:

| Cookie Attribute | Production Setting | Purpose |
| :--- | :--- | :--- |
| `HttpOnly` | `True` | Prevents JavaScript (`document.cookie`) access, protecting against session theft via XSS. |
| `SameSite` | `None` | Allows browser to attach cookie in cross-site iframe contexts. |
| `Secure` | `True` | Required by browsers when `SameSite=None`. Cookie is sent exclusively over HTTPS. |
| `Path` | `/` | Applies to all application routes and API endpoints. |
| `Max-Age` | `2592000` (30 days) | Provides seamless user experience without frequent re-logins. |
| `Domain` | `None` (or custom) | Restricts or shares cookies across subdomains. |

> [!NOTE]
> In local development environments operating over plain HTTP (`http://localhost`), set `session_cookie_secure: False` and `session_cookie_samesite: "lax"` or `"none"`.

### CSRF Protection for Cookie Sessions

Because `SameSite=None` allows cookies to be sent across origins, all state-changing browser
requests (`POST`, `PATCH`, `DELETE`) are protected by `BrowserSecurityMiddleware` and require:
1. An `Origin` header matching `WISHENKA_APPLICATION_ORIGIN`.
2. A session-bound CSRF token obtained via `GET /api/auth/csrf` and passed in `X-CSRF-Token`.
For full details, see [miniapp.md](miniapp.md).

---

## FastAPI Dependencies Usage

### Enforcing Authentication (`get_current_user`)

Use `get_current_user` for protected endpoints that require an authenticated caller. If the caller is unauthenticated or the session has expired, FastAPI automatically responds with `401 Unauthorized` and `WWW-Authenticate: Bearer`.

```python
from typing import Annotated
from fastapi import APIRouter, Depends
from wishenka.auth import AuthenticatedUser, get_current_user

router = APIRouter()


@router.get("/api/wishlists/my")
async def get_my_wishlists(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    return {
        "user_id": current_user.telegram_id,
        "name": current_user.first_name,
        "auth_method": current_user.auth_method,
    }
```

### Optional Authentication (`get_optional_current_user`)

Use `get_optional_current_user` for endpoints accessible to both guests and authenticated users (e.g. public wishlist view with guest reservations).

```python
from typing import Annotated
from fastapi import APIRouter, Depends
from wishenka.auth import AuthenticatedUser, get_optional_current_user

router = APIRouter()


@router.get("/w/{public_slug}")
async def view_public_wishlist(
    public_slug: str,
    user: Annotated[AuthenticatedUser | None, Depends(get_optional_current_user)],
):
    if user is not None:
        # Authenticated view: show user's existing reservations
        return {"slug": public_slug, "viewer_id": user.telegram_id, "is_guest": False}
    # Guest view: allow reserving with guest prompt
    return {"slug": public_slug, "viewer_id": None, "is_guest": True}
```

---

## Configuration Reference

All settings can be configured via environment variables with the `WISHENKA_` prefix or via a `.env` file.

| Setting Name | Environment Variable | Type | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `bot_token` | `WISHENKA_BOT_TOKEN` | `str` | `"dummy_bot_token"` | Telegram Bot API token used to derive HMAC key for `initData` verification. |
| `secret_key` | `WISHENKA_SECRET_KEY` | `str` | `"wishenka_default_secret_key_change_in_prod"` | Secret key used to sign and verify session tokens. |
| `session_secret_key` | `WISHENKA_SESSION_SECRET_KEY` | `str` | `"wishenka_default_secret_key_change_in_prod"` | Dedicated session signing key (falls back to `secret_key`). |
| `session_cookie_name` | `WISHENKA_SESSION_COOKIE_NAME` | `str` | `"session_id"` | Name of the HTTP session cookie. |
| `session_ttl_seconds` | `WISHENKA_SESSION_TTL_SECONDS` | `int` | `2592000` (30 days) | Session token validity duration in seconds. |
| `session_cookie_secure` | `WISHENKA_SESSION_COOKIE_SECURE` | `bool` | `False` | Whether cookie requires HTTPS. Set to `True` in production. |
| `session_cookie_samesite` | `WISHENKA_SESSION_COOKIE_SAMESITE` | `str` | `"none"` | SameSite policy (`"none"`, `"lax"`, or `"strict"`). `"none"` required for TMA iframe. |
| `session_cookie_domain` | `WISHENKA_SESSION_COOKIE_DOMAIN` | `str \| None` | `None` | Optional cookie domain for sharing across subdomains. |
| `telegram_auth_max_age_seconds` | `WISHENKA_TELEGRAM_AUTH_MAX_AGE_SECONDS` | `int` | `86400` (24h) | Maximum allowable age of `initData` `auth_date` before expiration. |

---

## Troubleshooting & Failure Modes

### 1. `401 Invalid initData: Telegram initData signature verification failed`
- **Root Cause**: The computed HMAC-SHA256 signature does not match `hash`.
- **Diagnosis**:
  - Verify that `WISHENKA_BOT_TOKEN` matches the exact bot that launched the Mini App.
  - Ensure the client sends the raw query string without double-decoding or modifying parameter order.
  - Verify that parameters are sorted by key with `\n` separator.

### 2. `401 Invalid initData: initData auth_date has expired`
- **Root Cause**: The `auth_date` timestamp in `initData` is older than `telegram_auth_max_age_seconds` (24 hours).
- **Diagnosis**:
  - Mini App was left open in the background or restored from a stale web cache.
  - Trigger `Telegram.WebApp.close()` or call `initData` refresh on the client.

### 3. `401 Invalid initData: initData auth_date is in the future`
- **Root Cause**: Server clock is out of sync with Telegram servers by more than 60 seconds (`clock_drift_seconds`).
- **Diagnosis**:
  - Verify NTP synchronization on the host (`timedatectl status` or `chrony`).

### 4. Session Cookies Not Saved in Browser / Mini App
- **Root Cause**: Browser rejected the cookie due to SameSite / Secure policy mismatch.
- **Diagnosis**:
  - In modern browsers, `SameSite=None` **must** be paired with `Secure=True` over HTTPS.
  - If developing locally over HTTP, ensure `session_cookie_samesite` is set to `"lax"` or use an HTTPS tunnel (e.g. ngrok / cloudflared).

### 5. `401 Invalid session token: Session token expired`
- **Root Cause**: Client token `exp` timestamp is earlier than current server time.
- **Diagnosis**:
  - The user's 30-day session expired. The frontend should capture 401 on HTMX calls and redirect to the TMA authentication handshake.

### 6. `401 Invalid session token: Session token signature verification failed`
- **Root Cause**: Token was signed with a different `secret_key` or tampered with.
- **Diagnosis**:
  - Ensure `WISHENKA_SECRET_KEY` is persistent across backend restarts and shared among all worker replicas.
