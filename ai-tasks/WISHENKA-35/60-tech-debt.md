# WISHENKA-35: Technical Debt Analysis

## Shortcuts Taken

1. **Runtime `sqlite_master` table existence checks in `AccountDeletionService` (`wishenka/wishlists/deletion.py`)**:
   - `_table_exists`, `_delete_if_table_exists`, and `_delete_if_table_exists_in` query `sqlite_master` dynamically before deleting from ~14 optional tables (`wl_favorites`, `wl_view_history`, `user_notification_settings`, `wl_list_notification_settings`, `notification_outbox`, `notice_receipt_keys`, `reminder_outbox`, `wl_idempotency_records`, `birthday_entries`, `birthday_input`, `bot_destinations`, `support_input`, `support_tickets`, `bot_drafts`, `bot_capture_order`, `users`, `deleted_session_revocations`).
   - This avoids failures on partial test schemas, but couples `AccountDeletionService` to an explicit hardcoded list of tables across all modules instead of a schema-level cascade or modular cleanup registry.
2. **Partial revocation fallback in `_is_session_active` (`wishenka/auth/dependencies.py:50-61`)**:
   - When `claims.user_id is not None` and the `users` table does not exist (e.g., minimal test fixtures), `_is_session_active` returns `True` immediately instead of falling through to check `deleted_session_revocations`.
3. **No in-memory/TTL cache for session liveness checks (`wishenka/auth/dependencies.py`)**:
   - Every authenticated HTTP request executes a fresh SQLite query against `sqlite_master` and `users` / `deleted_session_revocations` rather than caching active-user/revocation state with a short TTL or invalidation hook.

## Code Quality Issues

1. **Oversized `AccountDeletionService.delete_account` method (`wishenka/wishlists/deletion.py:160-562`)**:
   - The inner `work(conn)` coroutine spans ~345 lines and combines 6 distinct responsibilities (user/list discovery, collaborative ownership transfer, hard-deletion of personal/solo lists, foreign membership removal + item anonymization, reservation cancellation, PII/bot-state cleanup, revocation recording, and event emission).
   - Extracting focused private helpers (e.g., `_transfer_or_collect_owned_lists`, `_delete_owned_lists`, `_remove_from_foreign_lists`, `_cleanup_user_pii_and_bot_state`, `_record_session_revocation`) would improve readability and maintainability.
2. **Duplicated `sqlite_master` table-check SQL (`wishenka/auth/dependencies.py:52-68` vs `wishenka/wishlists/deletion.py:70-76`)**:
   - Both modules independently issue `SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ...` instead of sharing a small DB schema helper.

## Missing Tests

1. **Client-side JS E2E coverage for `wishenka/web/templates/settings.html`**:
   - Server-side endpoints (`GET /api/profile/deletion-preview`, `POST /api/profile/delete`) and template rendering are tested, but the browser JS flow in `settings.html` (opening the modal, fetching preview counts, requiring explicit confirmation, and handling `Telegram.WebApp.close()` / redirect) has no automated Playwright/browser test.
2. **Failure-path structured logging test (`account_deletion_failed`)**:
   - `wishenka/wishlists/deletion.py:525-537` logs `account_deletion_failed` at `ERROR` level when the deletion transaction raises, but there is no dedicated unit test asserting this error-path log record via `caplog`.
3. **Full optional bot-table cleanup coverage**:
   - `tests/test_account_deletion.py` and `tests/test_account_deletion_repro.py` both declare `pytestmark = pytest.mark.timeout(60)` (no timeout-marker blocker) and cover core wishlist/user/revocation tables, but do not exercise every optional bot/support table (`support_tickets`, `support_input`, `bot_capture_order`, `birthday_input`) in a single full-schema migration test.

## Performance Concerns

1. **N+1 queries in `preview_account_deletion` and `delete_account` (`wishenka/wishlists/deletion.py`)**:
   - `preview_account_deletion` (`lines 111-128`) runs a separate `SELECT 1 FROM wl_members ... LIMIT 1` query per collaborative wishlist owned by the user.
   - `delete_account` (`lines 241-325`, `356-399`) executes per-wishlist queries for transfer candidates, item anonymization, and remaining member notifications in loops. For typical users this is fast in SQLite WAL, but for users with many collaborative lists it could be batched.
2. **Per-request `sqlite_master` + liveness query in `_is_session_active` (`wishenka/auth/dependencies.py:40-80`)**:
   - Adds 1–2 SQLite queries to every authenticated request; under high concurrency this could be optimized with a small TTL cache or by removing the `sqlite_master` check once migrations are guaranteed.

## Follow-up Tasks

- **Refactoring (`AccountDeletionService` decomposition & shared schema helper)**: Split `AccountDeletionService.delete_account` into focused phase helpers and extract a shared `table_exists` helper used by both `wishenka/wishlists/deletion.py` and `wishenka/auth/dependencies.py`. (Non-blocker; suggested Jira type: `Debt`, priority: Low) Jira: [WISHENKA-197](https://pypost.atlassian.net/browse/WISHENKA-197)
- **Test coverage (Account deletion error-path `caplog` & full bot-table cleanup + `settings.html` JS flow)**: Add unit test for `account_deletion_failed` structured error logging, full-migration bot-table cleanup test, and browser/JS test for the `settings.html` deletion modal. (Non-blocker; suggested Jira type: `Debt`, priority: Low) Jira: [WISHENKA-198](https://pypost.atlassian.net/browse/WISHENKA-198)
- **Performance (Batch queries in `AccountDeletionService` & session liveness check optimization)**: Replace per-list N+1 queries in `preview_account_deletion`/`delete_account` with batched SQL queries and evaluate removing runtime `sqlite_master` checks or adding a short-lived revocation cache in `wishenka/auth/dependencies.py`. (Non-blocker; suggested Jira type: `Debt`, priority: Low) Jira: [WISHENKA-199](https://pypost.atlassian.net/browse/WISHENKA-199)
