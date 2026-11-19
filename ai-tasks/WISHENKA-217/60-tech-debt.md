# WISHENKA-217: Technical Debt Analysis

## Shortcuts Taken

No production shortcuts or workarounds were introduced; WISHENKA-217 is a test-coverage-only task adding `tests/test_receipt_undo_correction_edge_cases.py` with no changes to production code.

Minor test-helper trade-offs in `tests/test_receipt_undo_correction_edge_cases.py`:
- `_seed_deliverable_gifter` inserts directly into `bot_destinations` via `sql_exec` (reusing `tests/receipt_support.py`) so that `reminder_outbox` rows are emitted during notification-suppression checks.
- `_record_and_get_receipt_id` issues `POST /api/wishlists/{wishlist_id}/items/{item_id}/receipts` followed by `GET /api/wishlists/{wishlist_id}/gifted` to obtain the created `receipt_id` because the `POST` response returns `ReceiptResultDTO` aggregate counts rather than the new receipt's ID.

## Code Quality Issues

None. `tests/test_receipt_undo_correction_edge_cases.py` (430 lines):
- Declares module-level `pytestmark = pytest.mark.timeout(20)` (no missing timeout markers; no `do-testing` blockers).
- Reuses `tests/receipt_support.py` and `tests/receipt_ui_support.py` helpers (`app_env`, `bearer`, `hx`, `seed_list`, `item_received`, `receipt_rows`, `table_rows`, `assert_all_top_level_oob`, `assert_no_booking_leak`) without duplicating setup or assertion logic.
- Passes `ruff check`, `ruff format --check`, and `mypy` with zero issues (per `40-code-cleanup.md`).

Minor observation vs. `ai-tasks/WISHENKA-217/20-architecture.md`:
- `20-architecture.md` anticipated `X-Receipt-Refusal: wishlist_archived` for archived-wishlist `GET .../edit|cancel` refusals and `receipt_not_found` for all cross-wishlist targets. In actual production routes, archived-wishlist refusal returns `409` with `X-Receipt-Refusal: wishlist_not_active`, and cross-wishlist requests targeting an `item_id` from another list return `404` with `reason: "not_found"` (while targeting an item belonging to the other list returns `receipt_not_found`). The tests accurately assert the real production contracts.

## Missing Tests

All in-scope requirements (`FR-1` through `FR-4` and `NFR-1`/`NFR-2` in `ai-tasks/WISHENKA-217/10-requirements.md`) are covered by the 9 tests in `tests/test_receipt_undo_correction_edge_cases.py` (all 9 passing).

Remaining items explicitly out of scope for WISHENKA-217:
- Client-side JavaScript DOM/event handling tests for `receipt.js` (excluded in `10-requirements.md` Out of scope).

## Performance Concerns

None. All 9 tests in `tests/test_receipt_undo_correction_edge_cases.py` run against isolated `tmp_path` SQLite WAL databases via `app_env` and complete in ~2.8s total, well within the 20s per-test timeout.

## Follow-up Tasks

No new technical-debt follow-up tasks are required for WISHENKA-217.

Pre-existing unrelated failures observed in full `make test` runs (documented in `40-code-cleanup.md`):
- `NON-BLOCKER — pre-existing`: `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable` (tracked in `WISHENKA-232`) and other unrelated pre-existing suite failures tracked in Jira (`WISHENKA-245`, `WISHENKA-235`, `WISHENKA-220`, `WISHENKA-214`, `WISHENKA-212`).
