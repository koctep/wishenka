# WISHENKA-324: Technical Debt Analysis

No blockers. Gift-receipt looks take the wishlist repository as an
argument. `_repo_ctx` is gone, and no gift-receipt look opens
`get_wishlist_repository` because a hidden slot is empty. A successful
record, correction, or cancellation that carries the repeat key still
composes the list on that save. A true repeat returns the stored answer.

`tests/test_wishenka_324_receipt_access_repro.py` has
`pytestmark = pytest.mark.timeout(30)`. The updated receipt route tests
keep `pytestmark = pytest.mark.timeout(30)` in
`tests/test_receipt_ui_routes.py`. The updated receipt observability
tests keep `pytestmark = pytest.mark.timeout(60)` in
`tests/test_receipt_ui_observability.py`. Every test in those modules
inherits that mark. This step added no marker and changed no Python.

Reviewed: `wishenka/web/routes/receipts_ui.py` (`_execute`,
`_effect_fragments`, `get_receipt_dialog`, `record_receipt_ui`,
`_open_receipt_entry_modal`, `_execute_receipt_mutation_ui`,
`get_receipt_edit_dialog`, `correct_receipt_ui`,
`get_receipt_cancel_dialog`, `cancel_receipt_ui`),
`tests/test_wishenka_324_receipt_access_repro.py`,
`tests/test_receipt_ui_routes.py`,
`tests/test_receipt_ui_observability.py`, `20-architecture.md`,
`40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

- **The keyed list stays on the save** (accepted). `compose_receipt` and
  `compose_mutation` build `RepoWishlistOps(WishlistRepository(conn))`
  inside `execute_wish_idempotent`, after the wish rows are written and
  before the idempotency row is stored. Replay returns the stored body
  and does not compose again. This task does not hand that list a
  separate repository.
- **An unkeyed save commits, then reads** (accepted). The mutation stays
  `execute_wish`. The list is the next `run_repository_read`. A failed
  list read does not roll back a receipt that already committed. That
  read is not `get_wishlist_repository`.
- **A quantity refusal reads after rollback** (accepted).
  `record_receipt_ui` does not take `WishlistReadRepo` on the route. On
  `QuantityAboveRemainingError` or `NothingRemainingError` it opens
  `run_repository_read` and passes that repository into
  `_effect_fragments`. A `WishlistError` from that open leaves the
  refusal status and sentence unchanged. Correction and cancellation
  refusals stay sentence-only.

## Code Quality Issues

None that need a follow-up.

`_execute` still takes `request` and does not read it. Call sites keep
the same shape as `items_ui._execute`. The repository argument is
required, so a missing repository is a programming error and does not
open a shared repository.

`_execute_receipt_mutation_ui` still accepts `action` and `mutate`.
`correct_receipt_ui` and `cancel_receipt_ui` pass the same coroutine as
both. The branch that runs when `mutate` is absent does not run for
those routes. The live unkeyed path is `execute_wish`, then
`run_repository_read`.

The repro module docstring still describes the empty-slot opening as
the current defect. The assertions describe the shipped behavior.

## Missing Tests

No blocker. Timeout marks are explicit and module-wide:

- `tests/test_wishenka_324_receipt_access_repro.py`:
  `pytestmark = pytest.mark.timeout(30)`.
- `tests/test_receipt_ui_routes.py`:
  `pytestmark = pytest.mark.timeout(30)`.
- `tests/test_receipt_ui_observability.py`:
  `pytestmark = pytest.mark.timeout(60)`.

The repro covers the behavior this change owns.

- The quantity-refusal look builds `RepoWishlistOps` on the sentinel
  repository. A quantity above remaining still shows the wish card.
  Nothing remaining still shows the list and the gifted section.
- Opening the receipt, correction, and cancellation dialogs uses the
  read repository the handler was given, including the
  nothing-remaining refresh.
- A refused record that carries the repeat key stays 409 with the same
  reason and fragments, and the received quantity does not change.
- A keyed record, correction, and cancellation compose on the save
  connection. A second POST with the same key and body returns that
  body and does not read the list again.
- An unkeyed record, correction, and cancellation return the same
  fragments.

The autouse patch sets `receipts_ui.get_wishlist_repository` with
`raising=False`. The module no longer imports that name. The openings,
the sentinel look, and the keyed save are locked by the repository
identity and by the save connection. No follow-up.

## Performance Concerns

None added. A keyed save still holds the write transaction while the
list is composed. That is the compose this task left on the save. An
unkeyed save and a quantity refusal each open one later
`read_transaction`. That read does not take the save lock. This task
does not add a wait, a retry, or a second copy of the wishlist rules.

## Follow-up Tasks

No new follow-up. The hidden slot and the empty-slot opening are gone.
The quantity-refusal look stays and uses the repository it is given. The
successful keyed list stays on the save.

These already have keys and are not re-filed:

- The shared Alembic runner stays on
  [WISHENKA-335](https://pypost.atlassian.net/browse/WISHENKA-335).
- Read-only one-wishlist openings stay on
  [WISHENKA-338](https://pypost.atlassian.net/browse/WISHENKA-338).
  This task did not change `read_transaction` or
  `get_wishlist_read_repository`.
- Unchanged-row writes stay on
  [WISHENKA-339](https://pypost.atlassian.net/browse/WISHENKA-339).
- User-scoped hydration for history, favorites, deleted wishlists, and
  recording a view stays on
  [WISHENKA-340](https://pypost.atlassian.net/browse/WISHENKA-340).
- `UserStore._read` stays on
  [WISHENKA-342](https://pypost.atlassian.net/browse/WISHENKA-342).
- The shared-method set stays on
  [WISHENKA-350](https://pypost.atlassian.net/browse/WISHENKA-350).
- The missing-user history skip stays on
  [WISHENKA-351](https://pypost.atlassian.net/browse/WISHENKA-351).
- Concurrent preview cookies stay on
  [WISHENKA-352](https://pypost.atlassian.net/browse/WISHENKA-352).
- History share-grant batching stays on
  [WISHENKA-353](https://pypost.atlassian.net/browse/WISHENKA-353).

Busy mapping on `get_wishlist_repository` stays on
[WISHENKA-326](https://pypost.atlassian.net/browse/WISHENKA-326). This
task no longer calls that dependency from a gift-receipt look. History
per-entry loads stay on
[WISHENKA-325](https://pypost.atlassian.net/browse/WISHENKA-325). Token
rotation tests stay on
[WISHENKA-327](https://pypost.atlassian.net/browse/WISHENKA-327). This
step did not file those again.

Developer docs still say `receipts_ui._repo_ctx` is unchanged and that
`_execute` with no repository calls `get_wishlist_repository`
(`doc/dev/wishlists.md`, `doc/dev/architecture.md`). Step 8 of
WISHENKA-324 owns `doc/dev/`. No separate key. User-facing docs were
left unchanged. These screens did not add a person-facing sentence.

### Pre-existing test failures

This step did not re-run the suite. Nothing new was observed. The keys
below stay the filed set. They are `NON-BLOCKER — pre-existing`. This
step did not file them again.

- `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-232](https://pypost.atlassian.net/browse/WISHENKA-232).
- `tests/test_wish_card_giver_controls.py`
  `::test_anonymous_share_shows_availability_without_a_book_control`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235).
- `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-298](https://pypost.atlassian.net/browse/WISHENKA-298).
- `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-265](https://pypost.atlassian.net/browse/WISHENKA-265).
- `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220).
- `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-267](https://pypost.atlassian.net/browse/WISHENKA-267).
- `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-245](https://pypost.atlassian.net/browse/WISHENKA-245).
- Eight archive cases in `tests/test_items_ui_error_mapping.py`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264).
- `tests/test_preview_resource_reuse.py::test_concurrent_responses_do_not_share_cookies`
  — NON-BLOCKER — pre-existing. Jira:
  [WISHENKA-352](https://pypost.atlassian.net/browse/WISHENKA-352).
