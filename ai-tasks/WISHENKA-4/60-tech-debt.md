# WISHENKA-4: Technical Debt Analysis

## Shortcuts Taken

1. **Stateless Session Tokens Without Server-Side Revocation / Blacklist**:
   - The current session architecture issues signed HMAC-SHA256 tokens (`<payload_b64>.<sig_b64>`). `POST /api/auth/logout` clears the client session cookie, but because sessions are stateless, the token remains cryptographically valid until its `exp` timestamp (default 30 days). There is currently no server-side token blacklist or session revocation registry (e.g., in SQLite or memory). If a token is intercepted or leaked, it cannot be invalidated immediately by the server before TTL expiration.
2. **User Profile Database Persistence Deferred**:
   - `POST /api/auth/telegram` verifies Telegram WebApp `initData` and extracts `TelegramUser`, but does not persist the user into the SQLite database. User profile models, database tables, and account linking are deferred to subsequent stories (user management and wishlists). Only essential claims (`telegram_id`, `first_name`, `username`) are serialized into the session token.
3. **Single Static Secret Key Without Key Rotation Support**:
   - `SessionTokenService` uses a single symmetric `secret_key` (`settings.secret_key`). There is no mechanism for key rotation, key version identifiers (e.g. `kid`), or gradual key migration. Changing `secret_key` invalidates all issued session tokens immediately.
4. **Fallback Cookie Names in Dependency Resolution**:
   - `wishenka/auth/dependencies.py` checks `settings.session_cookie_name` and falls back to checking `"session_id"` and `"wishenka_session"`. While convenient for testing and backward-compatibility, cookie resolution should ideally be strictly configured via `settings.session_cookie_name`.

## Code Quality Issues

1. **StarletteDeprecationWarning with TestClient**:
   - Running `pytest` produces `StarletteDeprecationWarning: Using 'httpx' with 'starlette.testclient' is deprecated; install 'httpx2' instead` from `fastapi.testclient`. Tests should be migrated to `httpx.AsyncClient(transport=ASGITransport(app=...))` to align with modern Starlette/FastAPI standards and eliminate the warning.
2. **Per-Request SessionTokenService Instantiation**:
   - `SessionTokenService` is instantiated on every request inside `get_optional_current_user` and `auth_telegram` (`service = SessionTokenService(...)`). While the service is lightweight, providing it as a singleton or application-state dependency would improve code elegance and consistency with FastAPI dependency injection patterns.
3. **Ad-Hoc Cookie SameSite Value Normalization**:
   - In `wishenka/auth/session.py`, `set_session_cookie` and `delete_session_cookie` normalize the `samesite` argument using lowercase string comparison and `# type: ignore[arg-type]`. Using a typed `Literal["lax", "strict", "none"]` or Enum directly in `wishenka.config.Settings` would ensure static type safety without type ignore comments.

## Missing Tests

1. **Unicode, Emojis, and RTL Characters in Telegram User Payloads**:
   - Unit tests currently test standard ASCII names and Cyrillic text ("Vladislav"). Edge cases such as UTF-8 emojis, RTL characters, escaped quotes, or newlines in Telegram user profiles (`first_name`, `last_name`) are not explicitly covered by dedicated test cases.
2. **Future Clock Drift Boundary Tests**:
   - While past expiration is tested (`test_validate_init_data_expired`), the future timestamp rejection boundary (`auth_date > now + clock_drift_seconds`) is not explicitly asserted with a dedicated unit test.
3. **Extremely Long initData Strings / Payload Fuzzing**:
   - Boundary tests for very long query strings (e.g., 50–100 KB payload, extraneous unexpected URL query parameters) have not been added to verify parser robustness against memory exhaustion or parsing delays.
4. **Bearer Header Parsing Variations**:
   - Tests verify valid `Bearer <token>` and invalid token strings, but do not test malformed header formatting such as lowercase `bearer <token>`, extra leading/trailing whitespace, or missing token payload (`Bearer ` with empty string).

> [!NOTE]
> All existing tests in `tests/test_auth.py` declare explicit module timeouts via `pytestmark = pytest.mark.timeout(10)`, satisfying `do-testing` requirements. There are no missing timeout markers.

## Performance Concerns

1. **Repeated Cryptographic Verification on Every Request**:
   - For every protected HTTP request, `get_optional_current_user` executes Base64 decoding, HMAC-SHA256 verification, and JSON payload deserialization. For high-frequency API traffic or HTMX interactions, introducing an in-process LRU cache (or cache-aside) keyed by token hash could bypass redundant signature recalculations for recently verified tokens.
2. **HMAC WebAppData Key Derivation on Every Validation**:
   - `validate_telegram_init_data` computes `secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()` on every incoming login request. While SHA256 is fast, caching the derived secret key per bot token (or computing it once at startup) would avoid repetitive key derivation.

## Follow-up Tasks

1. **[WISHENKA-44](https://pypost.atlassian.net/browse/WISHENKA-44): Persist TelegramUser to Database on Authentication Exchange**:
   - Priority: Medium
   - Story Points: 3
   - Description: Implement database model for users and upsert `TelegramUser` into SQLite on `POST /api/auth/telegram`.
2. **[WISHENKA-45](https://pypost.atlassian.net/browse/WISHENKA-45): Implement Server-Side Session Revocation / Token Blacklist**:
   - Priority: Low
   - Story Points: 2
   - Description: Add session token revocation registry (in-memory or SQLite table) to allow immediate revocation on logout or user ban.
3. **[WISHENKA-41](https://pypost.atlassian.net/browse/WISHENKA-41): Migrate Test Suite to `httpx.AsyncClient`**:
   - Priority: Low
   - Story Points: 1
   - Description: Update `tests/test_auth.py` and other test suites from `fastapi.testclient.TestClient` to `httpx.AsyncClient` with `ASGITransport` to resolve `StarletteDeprecationWarning`.
4. **[WISHENKA-46](https://pypost.atlassian.net/browse/WISHENKA-46): Add Boundary and Unicode Tests for initData Parsing**:
   - Priority: Low
   - Story Points: 2
   - Description: Add test cases for future clock drift rejection, Unicode emojis, and malformed authorization headers.
5. **[WISHENKA-47](https://pypost.atlassian.net/browse/WISHENKA-47): Optimize Session Token Service Dependency and Key Derivation**:
   - Priority: Low
   - Story Points: 2
   - Description: Refactor `SessionTokenService` into an application-state singleton and precompute the `WebAppData` HMAC key.
