# WISHENKA-128: Technical Debt Analysis

## Shortcuts Taken

1. **Inlined one-way refusal logic instead of a shared helper**: `20-architecture.md` proposed a shared helper for one-way revisions, whereas the implementation inlined `logger.warning(..., extra={"event": "wishlist_migration_downgrade_refused", "revision": revision})` and `raise NotImplementedError(...)` directly in each of the four one-way revisions (`base_normalized.py`, `add_warn_on_delete_reserved.py`, `add_display_order.py`, `add_gift_receipts.py`).
2. **Offline-mode branch simplifications in `add_user_locale.py` and `add_notice_retention_columns.py`**:
   - In `add_user_locale.py`, when `context.is_offline_mode()` is true, `upgrade()` emits `CREATE TABLE IF NOT EXISTS users (...)`, indexes, and `_REPAIR_INVALID_SQL`, skipping the `PRAGMA table_info(users)` inspection and conditional `ALTER TABLE users ADD COLUMN locale / locale_source` statements.
   - In `add_notice_retention_columns.py`, `_columns()` returns `set()` in offline mode, causing `upgrade()` to unconditionally emit `ALTER TABLE ... ADD COLUMN` statements (safe for fresh schemas, but not idempotent if applied to a pre-existing table that already has some retention columns).

## Code Quality Issues

1. **Duplicated refusal boilerplate across one-way revisions**: The four one-way revision files (`base_normalized.py`, `add_warn_on_delete_reserved.py`, `add_display_order.py`, `add_gift_receipts.py`) repeat the same logger setup (`logging.getLogger("wishenka.wishlists.migrations")`), `logger.warning(...)`, and `NotImplementedError` backup-restoration message pattern. Extracting a small helper (e.g., `refuse_one_way_downgrade(revision, reason)`) would centralize the contract and prevent drift in future one-way revisions.
2. **Stale module docstring in `tests/test_wishlist_migration_rollback_policy.py`**: Line 1 still reads `"Red failing-repro tests for wishlist migration rollback policy (WISHENKA-128)."` from Step 3, even though the file is now the permanent regression suite for the finalized policy.

## Missing Tests

1. **Offline downgrade SQL generation (`sql=True`)**: `test_offline_sql_generation_emits_ddl_without_creating_db` covers `command.upgrade(cfg, "head", sql=True)`, but offline `command.downgrade(cfg, "add_gift_receipts", sql=True)` across reversible revisions is not tested.
2. **Per-revision schema/data assertions on reversible tail downgrade**: `test_reversible_tail_downgrades_cleanly_to_gift_receipts` verifies that `command.downgrade(cfg, "add_gift_receipts")` updates `alembic_version` to `("add_gift_receipts",)` without error, but does not assert that core wishlist tables/rows (`wl_lists`, `wl_items`, `wl_receipts`) remain intact or that the downgraded feature tables/columns were removed.
3. **Timeout markers check**: All tests in `tests/test_wishlist_migration_rollback_policy.py` have `pytestmark = pytest.mark.timeout(10)` (no blocker).

## Performance Concerns

None. `ROLLBACK_POLICY` is a module-level string constant with zero runtime cost, and `base_normalized.downgrade()` only reads `os.environ` when an explicit downgrade to `base` is invoked.

## Follow-up Tasks

- **NON-BLOCKER — Refactor**: Extract a shared `refuse_one_way_downgrade(revision, reason)` helper for one-way Alembic revisions to eliminate duplicated warning logging and `NotImplementedError` message boilerplate across `base_normalized.py`, `add_warn_on_delete_reserved.py`, `add_display_order.py`, and `add_gift_receipts.py`. Jira: [WISHENKA-233](https://pypost.atlassian.net/browse/WISHENKA-233)
- **NON-BLOCKER — Tests**: Update the module docstring in `tests/test_wishlist_migration_rollback_policy.py`, add offline `downgrade(..., sql=True)` coverage for reversible revisions, and add core-data-preservation assertions to `test_reversible_tail_downgrades_cleanly_to_gift_receipts`. Jira: [WISHENKA-234](https://pypost.atlassian.net/browse/WISHENKA-234)
- NON-BLOCKER — pre-existing: tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable — Jira: [WISHENKA-232](https://pypost.atlassian.net/browse/WISHENKA-232)
