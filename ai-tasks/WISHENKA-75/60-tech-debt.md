# WISHENKA-75: Technical Debt Analysis

## Shortcuts Taken

1. **Minimal `UserRefRow` stub in `wishenka/wishlists/db_models.py`:**
   - `UserRefRow` declares only `id` and `telegram_id` so SQLAlchemy metadata can resolve `ForeignKey("users.telegram_id", ondelete="CASCADE")` on `WishlistMemberRow`, `WishlistFavoriteRow`, and `ViewHistoryRow`, rather than mirroring the full `users` table schema from `wishenka/users/store.py` (`first_name`, `last_name`, `username`, `language_code`, `locale`, `locale_source`, `is_premium`, `created_at`, `updated_at`).
   - Safe while schema creation/evolution is driven by Alembic migrations and `UserStore`, but `Base.metadata.create_all()` on an empty database would create an incomplete `users` table.

2. **Duplicated `users` DDL in `wishenka/wishlists/alembic/versions/add_user_fk_cascades.py`:**
   - `_ENSURE_USERS_SQL` duplicates the `CREATE TABLE IF NOT EXISTS users (...)` definition from `UserStore._USERS_TABLE_DDL` / `add_user_locale` to guarantee the target table exists before rebuilding `wl_members`, `wl_favorites`, and `wl_view_history`. Future column additions to `users` would not automatically update this historical migration's fallback DDL.

3. **Remaining user-linked tables outside WISHENKA-75 scope:**
   - `WishlistRow.owner_id` (`wl_lists.owner_id`), `WishItemRow.recipient_user_id` (`wl_items.recipient_user_id`), and `ReservationRow.user_id` (`wl_reservations.user_id`) remain integer columns without `ForeignKey("users.telegram_id")` constraints. These were intentionally left out of WISHENKA-75 scope (as `AccountDeletionService` handles ownership transfer and `recipient_user_id` anonymization), but remain candidates for future referential integrity hardening.

## Code Quality Issues

1. **Generic `RuntimeError` wrapping in `WishlistStore.execute` (`wishenka/wishlists/store.py`):**
   - `WishlistStore.execute` catches `IntegrityError` (lines 1569–1577) and raises a generic `RuntimeError("Wishlist storage operation failed")`. Callers cannot distinguish a missing-user FK violation from other integrity errors without inspecting logs.
2. **Row-count calculation in `_rebuild_table` (`wishenka/wishlists/alembic/versions/add_user_fk_cascades.py`):**
   - `kept_rows` is computed from `inserted.rowcount` rather than a `SELECT COUNT(*) FROM {spec.name}` query. While SQLite/SQLAlchemy populates `rowcount` for `INSERT ... SELECT` and `max(0, int(inserted.rowcount or 0))` guards against `None`, an explicit `COUNT(*)` would be independent of DBAPI driver `rowcount` behavior.

## Missing Tests

- All 5 tests in `tests/test_wishenka_75_user_fk_cascade.py` have explicit timeout markers (`pytestmark = pytest.mark.timeout(30)`) — no timeout-marker blockers.
- **Collaborative owner deletion + FK cascade combined scenario:** `test_account_deletion_service_end_to_end_cascade` verifies `AccountDeletionService.delete_account()` for a member (`MEMBER_A_ID`) who owns a personal list and is a member/viewer/favoriter of a shared list. A combined test in `test_wishenka_75_user_fk_cascade.py` specifically exercising collaborative *owner* deletion (ownership transfer to another member before `DELETE FROM users` cascades `wl_members`) is not explicitly duplicated in this file.
- **Orphaned `wishlist_id` filtering during migration:** `test_migration_adds_user_fk_cascades_and_cleans_orphans` verifies orphan cleanup for nonexistent `user_id`, whereas the `AND wishlist_id IN (SELECT id FROM wl_lists)` branch of `_rebuild_table` is not separately exercised.

## Performance Concerns

- **Table rebuild during Alembic `upgrade()` / `downgrade()`:** `_rebuild_table` performs a full table copy (`INSERT INTO ... SELECT ... WHERE user_id IN (SELECT telegram_id FROM users) AND wishlist_id IN (SELECT id FROM wl_lists)`) for `wl_members`, `wl_favorites`, and `wl_view_history`, and drops/recreates their indexes. On very large SQLite databases this acquires an exclusive write lock for the duration of the migration, though for the expected SQLite workload this is a one-time operation and the only mechanism SQLite supports for adding `FOREIGN KEY` constraints.
- **Index coverage:** All three FK `user_id` columns retain dedicated indexes (`idx_wl_members_user`, `idx_wl_favorites_user`, `wl_view_history_user_wl` / `idx_wl_view_history_user_time`), so `ON DELETE CASCADE` lookups on `DELETE FROM users` are indexed.

## Follow-up Tasks

1. **Consolidate or align `UserRefRow` / `users` schema metadata** (low priority, Jira: [WISHENKA-227](https://pypost.atlassian.net/browse/WISHENKA-227)):
   - Keep `UserRefRow` in `wishenka/wishlists/db_models.py` synchronized with `UserStore._USERS_TABLE_DDL` or share a single SQLAlchemy `Table`/model definition if `Base.metadata.create_all()` is ever used.
2. **Evaluate `FOREIGN KEY` constraints for remaining user-linked columns** (low priority, Jira: [WISHENKA-227](https://pypost.atlassian.net/browse/WISHENKA-227)):
   - Assess adding `ForeignKey("users.telegram_id", ondelete="SET NULL")` on `wl_items.recipient_user_id` and `ForeignKey("users.telegram_id", ...)` on `wl_lists.owner_id` / `wl_reservations.user_id` in a dedicated future task.
3. **Pre-existing test failures observed during full-suite validation (`NON-BLOCKER — pre-existing`):**
   - `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable` (`NON-BLOCKER — pre-existing`, Jira: [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212))
   - `tests/test_items_ui_error_mapping.py` (8 failures, `NON-BLOCKER — pre-existing`, Jira: [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212))
   - `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads` (`NON-BLOCKER — pre-existing`, Jira: [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220))
   - `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge` (`NON-BLOCKER — pre-existing`, Jira: [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212))
   - `tests/test_receipt_static_script.py::test_inline_script_is_unchanged_and_free_of_receipt_code` (`NON-BLOCKER — pre-existing`, Jira: [WISHENKA-214](https://pypost.atlassian.net/browse/WISHENKA-214))
   - `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account` (`NON-BLOCKER — pre-existing`, Jira: [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212))
   - `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control` (`NON-BLOCKER — pre-existing`, Jira: [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212))
   - `tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast[dark]` (`NON-BLOCKER — pre-existing`, Jira: [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212))
   - `tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability` (`NON-BLOCKER — pre-existing`, Jira: [WISHENKA-212](https://pypost.atlassian.net/browse/WISHENKA-212))
