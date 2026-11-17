# WISHENKA-33: Technical Debt Analysis

## Shortcuts Taken

1. **Partial client-side localization via inline `HOME_I18N` in `wishenka/web/static/miniapp.js`**:
   - Only `showHome()` navigation and home shell labels were localized using an inline `HOME_I18N` dictionary (`wishenka/web/static/miniapp.js`).
   - Other Mini App JS views (`showHistory()`, `showList()`, `sharePanel()`, `roleLabel()`, and error/status messages) still contain hardcoded Russian (e.g. `roleLabel`: `'Владелец'`, `'Администратор'`, `'Соавтор'`, `'Избранное'`) or English strings (e.g. `'Copy link'`, `'Share via Telegram'`, `'Viewing history'`).
   - Ideally, the frontend should consume a single localized JSON dictionary served or embedded from `wishenka/i18n/catalog.py` rather than duplicating translations in JS.

2. **Partial SSR Jinja2 template localization**:
   - `base.html`, `settings.html`, `partials/item_card.html`, `partials/item_edit_modal.html`, and `partials/item_receipt_modal.html` were migrated to `t(..., locale)`.
   - Remaining templates (`wishlist_detail.html`, `share_wishlist.html`, `invite_preview.html`, `reservations_cabinet.html`, and 10 other partials under `wishenka/web/templates/partials/`) were left with hardcoded Russian/English strings (e.g., `Автор:` and `strftime('%d.%m.%Y')` in `wishlist_detail.html` and `share_wishlist.html`).

3. **Duplicated schema migration & backfill SQL between `UserStore.initialize()` and Alembic**:
   - Both `wishenka/users/store.py` (`UserStore.initialize()`) and `wishenka/wishlists/alembic/versions/add_user_locale.py` duplicate `_BACKFILL_ALL_SQL`, `_REPAIR_INVALID_SQL`, and `PRAGMA table_info(users)` column checks so that test/standalone `UserStore` setups without Alembic still receive the `locale` and `locale_source` columns.

4. **Raw SQL query across module boundary in `wishenka/web/routes/profile.py`**:
   - `_find_active_chat_id` queries `bot_destinations` directly via raw SQL (`SELECT chat_id FROM bot_destinations WHERE user_id = :uid AND active = 1`) instead of using a repository method on `NoticeStore`, and only reads the first active row (`row[0]`) rather than syncing all active private chats if multiple exist.

5. **Ephemeral `aiogram.Bot` creation in `PATCH /api/profile/locale`**:
   - `_sync_bot_commands_best_effort` in `wishenka/web/routes/profile.py` instantiates a new `Bot(token=token)` and closes its `aiohttp` session on every explicit locale switch instead of reusing a shared application-scoped `Bot` instance when available.

6. **Flat translation catalog without pluralization or locale-aware date formatting**:
   - `wishenka/i18n/catalog.py` stores all `RU`/`EN` strings in a single 370-line Python dictionary (`CATALOG`) without pluralization helpers (e.g., Russian `1 / 2-4 / 5+` forms) or locale-aware date/number formatting.

## Code Quality Issues

- **Redundant DB query in `GET /settings` (`wishenka/web/routes/profile.py`)**: `settings_page` injects `LocaleDep` (which calls `user_store.get_by_telegram_id(current_user.telegram_id)`) and then calls `user_store.get_by_telegram_id(current_user.telegram_id)` a second time solely to read `locale_source`.
- **Hardcoded `DEFAULT_LOCALE` on 422 error (`wishenka/web/routes/profile.py`)**: `update_profile_locale` returns `detail=t("settings.invalid_locale", DEFAULT_LOCALE)` instead of using the caller's resolved locale.
- **Duplicated `_normalize_row_locale` helper**: `wishenka/notices/store.py` and `wishenka/notices/reminders.py` each define a nearly identical `_normalize_row_locale` helper that normalizes `raw_locale` and emits `notice_locale_resolved`; this can be extracted into a shared helper.
- **Mixed-language UI during `EN` sessions**: Because `roleLabel()` in `wishenka/web/static/miniapp.js` and unmigrated templates still emit Russian strings, an English-locale user sees Russian role badges and headers inside otherwise English views.

## Missing Tests

- **Explicit timeout markers**: Verified — all new and modified test files (`tests/test_i18n_sync.py`, `tests/test_i18n_unit.py`, `tests/test_bot_support.py`, `tests/test_notice_delivery_repro.py`, `tests/test_notice_wishlist_events.py`) declare `pytestmark = pytest.mark.timeout(...)` (no blocker).
- **Alembic `downgrade()` coverage**: `tests/test_i18n_unit.py` verifies `add_user_locale.py` `upgrade()`, backfill, and invalid-row repair, but does not test `downgrade()` dropping `locale_source` and `locale`.
- **Non-home Mini App JS views**: `showHistory()`, `showList()`, `sharePanel()`, and `roleLabel()` in `wishenka/web/static/miniapp.js` lack automated DOM/Playwright tests for `RU`/`EN` switching.
- **Remaining SSR templates**: `wishlist_detail.html`, `share_wishlist.html`, `invite_preview.html`, `reservations_cabinet.html`, and the unmigrated `partials/*.html` lack `RU`/`EN` rendering assertions.
- **Concurrent `upsert_user` vs `set_locale` test**: No concurrency test exercises simultaneous `auto` upsert and `explicit` locale switch to verify `locale_source='explicit'` cannot be overwritten under contention.

## Performance Concerns

- **Extra SQLite read on localized web requests**: `get_request_locale` (`wishenka/i18n/dependencies.py`) queries `users` by `telegram_id` on every authenticated request using `LocaleDep` (and twice on `GET /settings`). Under SQLite WAL this is sub-millisecond, but caching the resolved `UserRecord` on `request.state` would eliminate duplicate lookups.
- **Per-request `Bot` session in background task**: Creating and closing a `Bot` (`aiohttp.ClientSession`) per `PATCH /api/profile/locale` request is offloaded to FastAPI `BackgroundTasks` with a `2.0s` timeout so it does not block HTTP latency, though rapid repeated toggles create transient HTTP sessions.

## Follow-up Tasks

1. **Localize remaining Mini App JS views (`wishenka/web/static/miniapp.js`)**: Replace hardcoded strings in `showHistory()`, `showList()`, `sharePanel()`, and `roleLabel()` and serve/embed translations from `wishenka/i18n/catalog.py` instead of duplicating `HOME_I18N`. Jira: [WISHENKA-73](https://pypost.atlassian.net/browse/WISHENKA-73) (existing sprint Debt issue)
2. **Localize remaining SSR Jinja2 templates**: Migrate `wishlist_detail.html`, `share_wishlist.html`, `invite_preview.html`, `reservations_cabinet.html`, and remaining `wishenka/web/templates/partials/*.html` to `t(..., locale)` with locale-aware date formatting and EN/RU rendering tests. Jira: [WISHENKA-89](https://pypost.atlassian.net/browse/WISHENKA-89) (existing sprint Debt issue)
3. **Clean up profile locale endpoint & DB lookup duplication**: Attach `UserRecord` on `request.state` in `get_request_locale` to avoid double `get_by_telegram_id` on `GET /settings`, localize the `422` error detail in `PATCH /api/profile/locale`, and move `_find_active_chat_id` into a repository method. Jira: [WISHENKA-192](https://pypost.atlassian.net/browse/WISHENKA-192)
4. **Consolidate notice locale normalization & add migration/concurrency tests**: Extract shared `_normalize_row_locale` for `wishenka/notices/store.py` and `wishenka/notices/reminders.py`, and add tests for `add_user_locale.py` `downgrade()` and concurrent `upsert_user` / `set_locale`. Jira: [WISHENKA-193](https://pypost.atlassian.net/browse/WISHENKA-193)
