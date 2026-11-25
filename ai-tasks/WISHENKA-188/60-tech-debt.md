# WISHENKA-188: Technical Debt Analysis

## Shortcuts Taken

1. **Cross-package migration coupling in `UserStore.initialize()`** (`wishenka/users/store.py`):
   - `UserStore.initialize()` delegates schema creation to `wishenka.wishlists.migrations.upgrade_to_head(self.database_url)`. This removes duplicate `users` DDL, but couples the core `users` package to `wishenka.wishlists.migrations` and runs all wishlist/notices/bot migrations whenever `UserStore` initializes.
   - Additionally, when an external `AsyncEngine` is passed to `UserStore(..., engine=...)`, `initialize()` still invokes `upgrade_to_head(self.database_url)` instead of migrating the provided engine.
2. **Orphaned row filtering without quarantine during `unify_user_keys_and_cascades` upgrade** (`wishenka/wishlists/alembic/versions/unify_user_keys_and_cascades.py`):
   - `_rebuild()` drops orphaned rows (rows whose legacy `users.id` or `wishlist_id` no longer resolves) via `INNER JOIN` / `WHERE ... IN (...)` and logs only aggregate counts (`unify_user_keys_orphans_cleaned`). No quarantine/backup table is written before deletion.
3. **Remaining tables without `users(telegram_id)` `ON DELETE CASCADE` FKs** (`wishenka/wishlists/alembic/versions/` & `wishenka/wishlists/deletion.py`):
   - `bot_drafts`, `bot_capture_order`, `user_notification_settings`, `wl_list_notification_settings` (on `user_id`), `notification_outbox`, `notice_receipt_keys`, and `wl_idempotency_records` still rely on manual `DELETE`s in `AccountDeletionService.delete_account()` rather than database-level `ON DELETE CASCADE` FKs.

## Code Quality Issues

1. **Mixed `users.id` vs `users.telegram_id` identifiers in structured logs and legacy `get_by_id`** (`wishenka/users/store.py`, `wishenka/bot/entry.py`, `wishenka/web/routes/auth.py`):
   - `UserStore` still exposes `get_by_id(user_id)` and logs `"user_id": record.id` in `upsert_user`, `set_locale`, `set_birthdate`, `clear_birthdate`, `wishenka/bot/entry.py`, and `wishenka/web/routes/auth.py`, while all foreign keys and downstream modules now key on `telegram_id`.
2. **Redundant manual `DELETE` statements in `AccountDeletionService.delete_account()`** (`wishenka/wishlists/deletion.py`):
   - `delete_account()` still runs explicit `_delete_if_table_exists` queries for `birthday_entries`, `bot_destinations`, `support_tickets`, and `reminder_outbox` (plus `birthday_input`/`support_input` where `owner_id` now cascades, though `chat_id = :uid` fallback remains), even though `DELETE FROM users WHERE telegram_id = :uid` now cascades to those tables automatically when `PRAGMA foreign_keys = ON`.
3. **Per-mutation defensive `wl_invite_tokens` backfill in `WishlistStore._mutate`** (`wishenka/wishlists/store.py`):
   - `WishlistStore._mutate` still executes `INSERT OR IGNORE INTO wl_invite_tokens (token, wishlist_id)` for all existing `prior_invites` on every wishlist mutation, which is unnecessary once `unify_user_keys_and_cascades` backfills `wl_invite_tokens.wishlist_id`.

## Missing Tests

1. **No automated test for `unify_user_keys_and_cascades` `downgrade()`**:
   - `tests/test_wishenka_188_user_key_unification_repro.py` thoroughly tests `upgrade()` (including legacy `users.id != users.telegram_id` mapping, orphan cleanup logging, and cascade deletes), but `downgrade()` (restoring `users.id` mappings and dropping `wl_invite_tokens.wishlist_id` / FKs) is not exercised by any test.
2. **No automated test for `UserStore(..., engine=...)` initialization path**:
   - All tests pass `database_url` only; behavior when an external `AsyncEngine` is supplied is untested.
3. **Timeout markers check**:
   - `tests/test_wishenka_188_user_key_unification_repro.py` sets `pytestmark = pytest.mark.timeout(30)` and all other modified test files retain explicit timeout markers (no `do-testing` blocker).

## Performance Concerns

1. **Extra writes in `WishlistStore._mutate`** (`wishenka/wishlists/store.py`):
   - Looping `INSERT OR IGNORE INTO wl_invite_tokens` over all `prior_invites` on every mutation adds `O(number_of_wishlists)` SQL statements per write transaction.
2. **Redundant `DELETE` statements in `AccountDeletionService.delete_account()`** (`wishenka/wishlists/deletion.py`):
   - Issuing `_table_exists` + `DELETE` for tables already covered by `ON DELETE CASCADE` adds unnecessary SQLite round-trips inside the account-deletion `BEGIN IMMEDIATE` transaction.

## Follow-up Tasks

| ID | Priority | Area | Description | Impact / Remediation | Jira |
| --- | --- | --- | --- | --- | --- |
| TD-1 | Medium | Migrations / Tests | Add automated `downgrade()` test for `unify_user_keys_and_cascades` | Verifies reversibility of `users.id` ↔ `users.telegram_id` mapping and `wl_invite_tokens` / `support_tickets` schema restoration in `tests/test_wishenka_188_user_key_unification_repro.py`. | [WISHENKA-334](https://pypost.atlassian.net/browse/WISHENKA-334) |
| TD-2 | Low | Architecture (`users` / `wishlists`) | Extract shared Alembic migration runner out of `wishenka.wishlists.migrations` into a neutral `wishenka.db.migrations` module | Eliminates `wishenka.users.store` → `wishenka.wishlists.migrations` cross-domain import coupling. | [WISHENKA-335](https://pypost.atlassian.net/browse/WISHENKA-335) |
| TD-3 | Low | Observability / `users` | Audit and unify `"user_id"` structured log fields (`record.id` vs `record.telegram_id`) across `users/store.py`, `bot/entry.py`, and `web/routes/auth.py`, and deprecate `UserStore.get_by_id` if unused | Prevents log correlation ambiguity between internal `users.id` PK and `telegram_id`. | [WISHENKA-336](https://pypost.atlassian.net/browse/WISHENKA-336) |
| TD-4 | Low | Wishlists / Deletion | Remove redundant per-mutation `wl_invite_tokens` `INSERT OR IGNORE` backfill in `WishlistStore._mutate` and redundant manual `DELETE`s in `AccountDeletionService.delete_account()` for FK-cascaded tables | Reduces write-transaction overhead while preserving `chat_id = :uid` cleanup where needed. | [WISHENKA-337](https://pypost.atlassian.net/browse/WISHENKA-337) |
