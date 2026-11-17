# WISHENKA-86: Technical Debt Analysis

**Blocker summary:** No `blocker` items found. All tests in `tests/test_wishlist_deleted_restore.py` declare `pytestmark = pytest.mark.timeout(30)` (compliant with `do-testing`), and `make analyze` / `make test` (`1097 passed`) pass cleanly. All items below are `NON-BLOCKER` follow-ups.

## Shortcuts Taken

1. **Silent error suppression when fetching deleted wishlists in Mini App (`wishenka/web/static/miniapp.js:211`)** — `medium` (`NON-BLOCKER`)
   - `api('/api/wishlists/deleted').catch(() => [])` swallows all network and HTTP 5xx errors in `showHome()`, causing the "Recently deleted" section to silently disappear instead of surfacing a non-blocking warning or retry cue.
2. **Duplicated `retention_days` settings lookup in HTTP routes (`wishenka/web/routes/wishlists.py:229-231, 507-509`)** — `low` (`NON-BLOCKER`)
   - Both `list_deleted_wishlists` and `restore_deleted_wishlist` inline `getattr(getattr(request.app.state, "settings", None), "wishlist_retention_days", 30)` instead of sharing a helper or FastAPI dependency.
3. **Inline `deleted-section` / `deleted-wishlist-card` / `deleted-meta` CSS classes without dedicated styles (`wishenka/web/static/miniapp.js:280-289`)** — `low` (`NON-BLOCKER`)
   - The new UI reuses `.wishlist-section`, `.wishlist-card`, and `.history-time` classes; `wishenka/web/static/miniapp.css` was not updated with dedicated styling for `.deleted-section` or `.deleted-wishlist-card` (e.g., muted card treatment or spacing for the restore button).

## Code Quality Issues

1. **Duplicated timezone-normalization and token-rotation boilerplate in `WishlistService` (`wishenka/wishlists/service.py:951-955, 1009-1011, 1027-1041`)** — `low` (`NON-BLOCKER`)
   - `list_deleted_wishlists` and `restore_deleted_wishlist` both repeat naive-vs-aware `wl.updated_at` UTC normalization.
   - `restore_deleted_wishlist` duplicates the 4-attempt `secrets.token_urlsafe` collision-avoidance loop for `public_token` and `invite_token` instead of extracting a small helper.
2. **Untyped tuple return from `WishlistService.list_deleted_wishlists` (`wishenka/wishlists/service.py:940`)** — `low` (`NON-BLOCKER`)
   - Returning `list[tuple[Wishlist, datetime, int]]` is less self-documenting than a frozen dataclass (e.g., `DeletedWishlistEntry(wishlist, expires_at, days_remaining)`).
3. **Duplicate INFO log emission per request across service and route layers (`wishenka/wishlists/service.py:963-973, 1048-1060` and `wishenka/web/routes/wishlists.py:235-244, 517-527`)** — `low` (`NON-BLOCKER`)
   - Both `wishenka.wishlists` and `wishenka.web.wishlists` emit `wishlist_deleted_listed` and `wishlist_restored_from_deleted` for the same request (in addition to `wishlist_mutation_committed` in `execute()`), increasing log volume.

## Missing Tests

1. **No DOM/browser behavioral tests for Mini App deleted-list UI (`wishenka/web/static/miniapp.js:274-312`, `tests/test_wishlist_deleted_restore.py:316-337`)** — `medium` (`NON-BLOCKER`)
   - `test_deleted_i18n_keys_and_miniapp_ui_wiring` only performs static substring assertions on `miniapp.js`. Button disabling during in-flight requests, `410 Gone` handling (calling `showHome()` and displaying `miniapp.deleted.expired`), and generic failure recovery (`restoreBtn.disabled = false`) are not executed in a JS/DOM test harness.
2. **Missing exact-boundary retention test (`elapsed == retention_days`) and token-stability assertion on idempotent restore (`tests/test_wishlist_deleted_restore.py:185-194, 196-240`)** — `low` (`NON-BLOCKER`)
   - Tests cover `29d 23h` (inside window) and `31d` (expired), but not the exact `deleted_at == effective_now - timedelta(days=retention_days)` boundary (`<= threshold`).
   - The idempotency test verifies `200 OK` and `status == "active"` on the second `POST /restore-deleted` call, but does not assert that `share_token` and `invite_token` remain unchanged on the second call.

## Performance Concerns

1. **In-memory linear scan over all wishlists in `list_deleted_wishlists` (`wishenka/wishlists/service.py:945-961`)** — `low` (`NON-BLOCKER`)
   - `list_deleted_wishlists` iterates over `self._wishlists.values()` (`O(N)` across all users' wishlists). This matches the existing `WishlistStore` / `WishlistService.list_wishlists` in-memory snapshot architecture, so it is acceptable at current scale, but would benefit from an owner/status index if the dataset grows significantly.

## Follow-up Tasks

- **[`medium` | `NON-BLOCKER`] Surface `GET /api/wishlists/deleted` load failures and add DOM tests for Mini App deleted-wishlist UI** (`wishenka/web/static/miniapp.js`, `wishenka/web/static/miniapp.css`, `tests/test_wishlist_deleted_restore.py`) -> [WISHENKA-203](https://pypost.atlassian.net/browse/WISHENKA-203):
  - Replace silent `.catch(() => [])` with graceful fallback notice or retry state, add dedicated `.deleted-section` / `.deleted-wishlist-card` styles, and cover `410`/failure/disable states in a JS/DOM test.
- **[`low` | `NON-BLOCKER`] Refactor `WishlistService` / route helpers for deleted-wishlist restore and add exact-boundary/idempotent-token tests** (`wishenka/wishlists/service.py`, `wishenka/web/routes/wishlists.py`, `tests/test_wishlist_deleted_restore.py`) -> [WISHENKA-204](https://pypost.atlassian.net/browse/WISHENKA-204):
  - Extract shared `retention_days` helper in `wishlists.py`, UTC-normalization / token-generation helpers and a typed `DeletedWishlistEntry` dataclass in `service.py`, and add tests for the exact `retention_days` boundary and unchanged tokens on idempotent `restore-deleted`.
- **[`low` | `NON-BLOCKER — pre-existing`] Stabilize timestamp collision in `tests/test_bot_support_repro.py::test_privacy_surprise_protection_and_capability_redaction`** -> [WISHENKA-205](https://pypost.atlassian.net/browse/WISHENKA-205):
  - Observed once during Step 5 (`40-code-cleanup.md`) when `caplog` record metadata (`record.__dict__`) contained `"101"` in its timestamp; passed on subsequent `make test` runs.
