# WISHENKA-34: Technical Debt Analysis

## Shortcuts Taken

1. **Per-request instantiation of `NotificationPreferencesStore` (`wishenka/web/routes/profile.py`):**
   - `_get_preferences_store(request, user_store)` creates a new `NotificationPreferencesStore(engine)` on every HTTP request and falls back to `user_store.engine` when `request.app.state.wishlist_store` is absent, instead of registering a dedicated `preferences_store` on `app.state` with a FastAPI dependency (`Depends(get_preferences_store)`).
   - **Impact:** Minor object allocation per request; in non-standard setups where `user_store` and `wishlist_store` use separate SQLite files, the fallback would query `user_store.engine` where `wl_lists` does not exist.

2. **Schema evolution via `ALTER TABLE` in `UserStore.initialize()` (`wishenka/users/store.py`):**
   - Columns `birth_day`, `birth_month`, `birth_year`, `birthdate_source` are added idempotently via `PRAGMA table_info(users)` + `ALTER TABLE users ADD COLUMN ...` inside `UserStore.initialize()`, following the existing `locale` / `locale_source` pattern rather than an Alembic migration.
   - **Impact:** Keeps `UserStore` self-contained for isolated tests, but schema history for `users` remains outside Alembic.

3. **Static effective badges in `settings.html` after global toggle (`wishenka/web/templates/settings.html`):**
   - `updateGlobalNotification(...)` updates the global setting via `PUT /api/profile/notifications/global` and shows a saved message, but does not dynamically recalculate `[data-effective-for="..."]` badges in the per-wishlist section for wishlists using `"inherit"` until the page is reloaded.

4. **Inline `<script>` in `wishenka/web/templates/settings.html`:**
   - Client-side handlers (`saveBirthdate`, `clearBirthdate`, `updateGlobalNotification`, `updateWishlistOverride`) are embedded inline in the Jinja2 template rather than extracted into a static JS module.

## Code Quality Issues

1. **Duplicate wishlist access predicate in `NotificationPreferencesStore` (`wishenka/notices/preferences.py`):**
   - The SQL access filter (`l.status IN ('active', 'archived') AND (l.owner_id = :uid OR EXISTS(wl_members) OR EXISTS(wl_favorites))`) and role resolution (`"owner"` / `"member"` / `"favorite"`) are duplicated between `_fetch_accessible_wishlist_meta` (lines 104–133) and `list_accessible_wishlists_with_preferences` (lines 222–263).
   - **Recommended refactor:** Extract a shared SQL fragment/helper for accessible wishlist selection and role mapping.

2. **Duplicate invalid-payload error handling in `wishenka/web/routes/profile.py`:**
   - `update_profile_birthdate`, `update_global_notifications`, and `update_wishlist_notifications` repeat similar `logger.warning(...)` + `HTTPException(422, ...)` blocks when validating request dicts.

3. **Explicit `pytest.mark.timeout` compliance (`do-testing`):**
   - Verified clean: `tests/test_wishenka_34_repro.py` (`pytestmark = pytest.mark.timeout(60)`), `tests/test_wishenka_34_preferences.py` (`pytestmark = pytest.mark.timeout(30)`), and `tests/test_receipt_notices.py` (`pytestmark = pytest.mark.timeout(60)`) all declare explicit module-level timeouts. No blocker.

## Missing Tests

1. **Client-side JS / browser E2E tests for `wishenka/web/templates/settings.html`:**
   - Server-side HTML rendering (`GET /settings`) and all JSON API endpoints (`/api/profile/preferences`, `/api/profile/birthdate`, `/api/profile/notifications/global`, `/api/profile/notifications/wishlists/{id}`) are covered by `tests/test_wishenka_34_repro.py` and `tests/test_wishenka_34_preferences.py`, but the inline JavaScript handlers (`saveBirthdate`, `clearBirthdate`, `updateGlobalNotification`, `updateWishlistOverride`) have no automated Playwright/DOM tests.

2. **`UserStore.upsert_from_bot` birthdate preservation test (`wishenka/users/store.py`):**
   - `upsert_user` is explicitly tested not to overwrite `birthdate_source = 'explicit'`, while `upsert_from_bot` (which delegates to `upsert_user`) is not separately exercised in `tests/test_wishenka_34_preferences.py`.

3. **Fallback test for `birthday_reminders` unset with `reminders = 0` (`wishenka/notices/reminders.py`):**
   - `tests/test_wishenka_34_repro.py` and `tests/test_wishenka_34_preferences.py` verify explicit `birthday_reminders = False` and `birthday_reminders = True` overriding `reminders = False`, but do not explicitly test the fallback branch when `birthday_reminders` is absent and `reminders = False` suppresses a `birthday` reminder.

## Performance Concerns

1. **N+1 query in `NotificationPreferencesStore.list_accessible_wishlists_with_preferences` (`wishenka/notices/preferences.py`, lines 222–263):**
   - After fetching all accessible wishlists in one query (`wl_rows`), the method calls `_build_wishlist_summary` in a loop for each wishlist, issuing one `SELECT event_type, enabled FROM wl_list_notification_settings WHERE user_id = :uid AND wishlist_id = :wl_id` per wishlist.
   - **Impact:** Negligible for typical users (1–10 wishlists), but scales as `O(N)` queries per `/settings` or `/api/profile/preferences` request for power users with many wishlists. Can be eliminated with a single `SELECT wishlist_id, event_type, enabled FROM wl_list_notification_settings WHERE user_id = :uid` grouped in memory.

2. **Per-key SQL statements on batch updates (`wishenka/notices/preferences.py`):**
   - `update_global_settings` and `update_wishlist_overrides` execute one `INSERT`/`DELETE` per category in a loop inside a single transaction. With at most 4–5 categories, overhead is minimal.

## Follow-up Tasks

- **Batch per-wishlist override query in `NotificationPreferencesStore.list_accessible_wishlists_with_preferences`** (`Priority: Low`): Replace the N+1 `wl_list_notification_settings` queries with a single bulk `SELECT` grouped by `wishlist_id`, and deduplicate the accessible-wishlist SQL/role helper. Jira: [WISHENKA-194](https://pypost.atlassian.net/browse/WISHENKA-194)
- **Wire `NotificationPreferencesStore` via FastAPI dependency / `app.state`** (`Priority: Low`): Remove per-request instantiation and `user_store.engine` fallback in `wishenka/web/routes/profile.py` (`_get_preferences_store`). Jira: [WISHENKA-195](https://pypost.atlassian.net/browse/WISHENKA-195)
- **Refresh inherited effective badges in `settings.html` on global toggle + add DOM/E2E coverage** (`Priority: Low`): Update `[data-effective-for]` badges when `updateGlobalNotification` succeeds and add automated browser/JS tests for `settings.html` controls plus `reminders = False` fallback test for `birthday` reminders. Jira: [WISHENKA-196](https://pypost.atlassian.net/browse/WISHENKA-196)
