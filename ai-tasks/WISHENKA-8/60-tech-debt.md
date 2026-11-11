# WISHENKA-8: Technical Debt Analysis

## Shortcuts Taken

- **Direct private attribute access in route layer**: In `wishenka/web/routes/wishlists.py`, `find_invitation()` searches `service._wishlists.values()` directly instead of invoking an explicit query method on `WishlistService` (such as `get_wishlist_by_invite(token)`). This bypassed defining a public query interface in domain service for speed of delivery.
- **Client-side vanilla DOM construction**: `wishenka/web/static/miniapp.js` constructs UI dynamically using procedural vanilla JS (`document.createElement`, `replaceChildren`) and inline status notifications rather than integrating HTMX or a declarative template renderer.
- **Global logger suppression for SQL parameter redaction**: In `wishenka/wishlists/store.py`, `aiosqlite` logging is clamped to `WARNING` via `logging.getLogger("aiosqlite").setLevel(logging.WARNING)` to prevent capabilities and tokens in raw SQL bind parameters from leaking into debug logs. A dedicated sanitizing log filter or engine-level scrubber would be cleaner.
- **Embedded inline HTML shell**: In `wishenka/web/routes/miniapp.py`, the shell document is generated via an inline Python format string rather than leveraging a Jinja2 template under `wishenka/web/templates/`.
- **Placeholder for wish items**: As wish creation and item manipulation are scoped for WISHENKA-9, the Mini App list view renders a temporary static notice ("Adding wishes will be available in a future update") beneath existing items.

## Code Quality Issues

- **Encapsulation leak in `find_invitation`**: `wishenka/web/routes/wishlists.py` relies on `service._wishlists` internals; refactoring is needed to add `WishlistService.get_wishlist_by_invite(token: str) -> Wishlist` with appropriate domain error handling.
- **Ad-hoc table migration in `WishlistStore`**: Schema tables (`wl_tokens`, `wl_invite_tokens`, `wl_counters`, etc.) are declared with raw `CREATE TABLE IF NOT EXISTS` inside `WishlistStore._init_db()` rather than managed through formal Alembic database migrations.
- **Generic frontend error feedback**: In `wishenka/web/static/miniapp.js`, API failure catch blocks report general status strings ("Could not save settings", "Could not remove member") instead of extracting and displaying structured backend validation or business rejection messages (`response.detail`).
- **Date timezone parsing assumption**: `settingsForm` in `miniapp.js` formats UTC timestamps to local inputs using `.slice(0, 16)` and appends `Z` upon saving, which can lead to timezone discrepancies on non-UTC browser locales.

## Missing Tests

- **Concurrent invite acceptance race conditions**: While storage and token uniqueness collision logic are tested (`test_domain_token_collisions_retry_and_exhaustion_hides_token`), concurrent acceptance of the same invite token by multiple distinct users in parallel is not covered in an explicit concurrency test.
- **Invite expiration boundary in browser UI**: Tests verify API responses for expired tokens, but the client-side UI error presentation when a user attempts to join via an expired link during active browser session is not verified via automated browser test.
- **Network interruption / offline behavior in Mini App**: Tests assume persistent HTTP connectivity; intermittent network dropouts or retry behavior on mobile connections are not tested.
- **WebKit clipboard gesture constraints**: Verification uses standard `navigator.clipboard.writeText` mock in headless browser; Safari/iOS WebKit strict user gesture activation requirements for async clipboard writing are not tested against real WebKit engines.

## Performance Concerns

- **Full dataset in-memory loading and serialization**: `WishlistStore._read` and `_write` load all stored wishlists, items, and members into memory and re-serialize them on each transaction. As list volume increases, memory overhead and I/O latency will scale linearly O(N), becoming a bottleneck.
- **Linear in-memory search for invitation tokens**: Resolving an invitation token (`find_invitation`) iterates sequentially through all cached wishlists (`next((w for w in service._wishlists.values() ...))`) rather than using an indexed SQL lookup (`SELECT wishlist_id FROM wl_invite_tokens WHERE token = :token`).
- **Uncached static asset delivery**: Static assets (`miniapp.js`, `miniapp.css`) are served directly without HTTP cache headers or versioned cache busting, and `BrowserSecurityMiddleware` injects `Cache-Control: no-store` on matching requests.

## Follow-up Tasks

- **DEBT-WISHENKA-8-1**: Implement `WishlistService.get_wishlist_by_invite(token: str)` domain method to remove direct access to `_wishlists` in `wishenka/web/routes/wishlists.py`.
  - Jira: [WISHENKA-65](https://pypost.atlassian.net/browse/WISHENKA-65) (2 SP, Medium)
- **DEBT-WISHENKA-8-2**: Migrate `WishlistStore` ad-hoc SQLite schema definitions (`wl_tokens`, `wl_invite_tokens`, `wl_members`) to standard Alembic migrations.
  - Jira: [WISHENKA-66](https://pypost.atlassian.net/browse/WISHENKA-66) (5 SP, Low)
- **DEBT-WISHENKA-8-3**: Refactor Mini App HTML shell generation in `wishenka/web/routes/miniapp.py` to use a Jinja2 template.
  - Jira: [WISHENKA-69](https://pypost.atlassian.net/browse/WISHENKA-69) (2 SP, Low)
- **DEBT-WISHENKA-8-4**: Optimize `WishlistStore` with granular SQL queries and indexes for token lookups (`find_invitation`) to eliminate whole-store deserialization.
  - Jira: [WISHENKA-67](https://pypost.atlassian.net/browse/WISHENKA-67) (3 SP, Medium)
- **DEBT-WISHENKA-8-5**: Improve client-side date/time handling in `miniapp.js` to correctly handle browser timezone offsets and format errors from API `detail` fields.
  - Jira: [WISHENKA-68](https://pypost.atlassian.net/browse/WISHENKA-68) (2 SP, Low)

*(No pre-existing test failures were found during test execution; 133/133 tests passing).*
