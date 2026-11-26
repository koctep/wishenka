# WISHENKA-323: Code Cleanup Report

## Linter Fixes

Describe fixed linter errors and warnings:

- Fixed: none. `make analyze` reported no Ruff or Mypy issues before or after
  this cleanup.

## Code Formatting

Applied formatting changes:

- [x] Automatic code formatting
- [x] Indentation and alignment fixes
- [x] Line length correction

Ruff format already kept the touched Python at the 100-character limit. The
module docstring in `tests/test_wishenka_323_one_wishlist_rule_set.py` was
rewrapped to that limit and now describes the checks that are in place.

## Code Cleanup

Cleanup actions performed:

- Removed unused imports: 0
- Removed unused variables: 0
- Removed commented-out code: none found in the touched files
- Removed debug prints: none found in the touched files
- Removed dead methods on `WishlistService` after the in-memory shared actions
  lost their callers: `_ensure_wishlist_active`, `_log_partial_move`, and
  `_has_valid_share_access`

`_log_archive_refused` stays. `RepoWishlistOps` still calls it.

## Validation Results

Validation results:

- [ ] All tests passed
- [x] Touched tests have an explicit timeout marker
  (`pytestmark = pytest.mark.timeout(30)` on the task file)
- [x] No merge conflicts
- [x] Syntax is valid
- [x] Types are correct (Mypy, strict, 296 files)

Commands:

- `make analyze` — Ruff check passed, Ruff format check passed, Mypy
  succeeded with no issues in 296 source files.
- `make test PYTEST_ARGS='tests/test_wishenka_323_one_wishlist_rule_set.py'` —
  3 passed.
- `make test` — 39 failed, 2611 passed, 2 skipped, 5 warnings, in 207.25s
  before the shared-action follow-up.
- `make analyze` — Ruff and Mypy clean again after that follow-up.
- `make test` — 16 failed, 2634 passed, 2 skipped, 5 warnings, in 210.56s.

## Notes

`tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable` is the
filed pre-existing failure WISHENKA-232. This step did not change that
migration.

The other 38 failures were not edited in the unused-helper pass. A follow-up
in this same step moved shared actions off the hydrated service and stopped a
missing `users` row from aborting a share or public view.

`make test` after that follow-up: 16 failed, 2634 passed, 2 skipped, 5
warnings, in 210.56s. The 16 that remain are outside this task:

- `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable` —
  WISHENKA-232, `notice_receipt_keys` column count. The migration was not
  changed.
- `tests/test_preview_resource_reuse.py::test_concurrent_responses_do_not_share_cookies`
  — one recorded origin request instead of two. Preview code and this test
  file are untouched by the wishlist-rule change.
- Eight `tests/test_items_ui_error_mapping.py` archive cases — the modal
  returns an HTML body and the test calls `.json()`. The domain status is
  already 409 or 404. That response helper was not part of this change.
- `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
  — `error_class` is `TypeError` because `purge_finished` is called with
  keyword arguments the test double does not accept. `cleanup.py` is unchanged.
- `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
  and
  `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
  — the share page is HTTP 200 and the availability copy is absent.
- `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`,
  `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`,
  and `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
  — browser waits time out. They are not the repository-path or foreign-key
  failures.
