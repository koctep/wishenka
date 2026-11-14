# WISHENKA-112: Technical Debt Analysis

Scope: `wishenka/web/routes/items_ui.py` (`_DOMAIN_ERRORS`, `_reordered_response` callback, `move_item_ui`,
`reorder_items_ui`), `wishenka/wishlists/store.py` (3 probes removed), `wishenka/wishlists/repository.py`
(2 probes removed), `tests/test_wishenka_112_structure.py` (3 tests), `tests/test_items_ui_error_mapping.py`
(24 tests). Compared against `10-requirements.md`, `20-architecture.md`, `40-code-cleanup.md`,
`50-observability.md`. The change is a behaviour-preserving refactor; no new runtime logic was added.

Timeout markers: `tests/test_wishenka_112_structure.py:28` and `tests/test_items_ui_error_mapping.py:27` both
declare `pytestmark = pytest.mark.timeout(30)`. No timeout-marker BLOCKER.

Pre-existing failures: none (Step 5: 616 passed, 0 failed). The untracked `core` file is already ticketed as
WISHENKA-126 and is not duplicated here; `td-99-commit` must stage by explicit path.

No BLOCKER debt. All items below are NON-BLOCKER and not yet ticketed.

## Shortcuts Taken

- **No log at the 404/409 mapping.** `_raise_http` (`items_ui.py:796`) translates every domain error into
  404 `Resource not found` (or 409 for archived) and logs nothing. The only trace is the HTTP middleware
  access line (method, path, status, duration), so a 404 triage cannot tell wishlist-not-found from
  item-not-found from permission-denied. Left as is on purpose in Step 6 (behaviour-preserving, no detail
  leak to the client). A server-side DEBUG/INFO line with the exception class would help without changing
  the response.
- **Missing-column failure is deliberately loud but untested.** After removing the probes, a missing
  `warn_on_delete_reserved`/`display_order` column raises `AttributeError` and becomes a 500 via the
  middleware. This is intended (see `50-observability.md`), but no test pins it, so a later "defensive"
  edit could silently bring the defaults back. The structure test only guards against the probes in the
  two files, not against the behaviour.

## Code Quality Issues

- **`_DOMAIN_ERRORS` and `_raise_http` are two separate sources of truth.** The tuple lists the five
  exceptions; `_raise_http` special-cases only `WishlistArchivedError` and sends everything else to 404.
  A new domain exception added to the tuple gets 404 by default (possibly wrong), and one added only to
  `_raise_http` is never caught. A single mapping (exception class -> status/detail) used by both the
  `except` clauses and the translation would remove the coupling. The comment added above the tuple only
  documents it.
- **The `try/except _DOMAIN_ERRORS as exc: _raise_http(exc)` block is repeated** in `_reordered_response`,
  `archive_confirm_ui`, `archive_item_ui`, `restore_item_ui` (4 sites). A small
  wrapper (for example an `_execute_mapped` helper) would remove the repetition. Closely related to the
  mapping item above; propose doing both in one task.

## Missing Tests

- **Log fields are not pinned.** `tests/test_items_ui_error_mapping.py` checks event names, levels,
  `reason`, `direction`, `item_id`, `item_count`, but not `actor_id`, `user_id` or `wishlist_id` in
  `ui_items_reordered`, `ui_item_moved`, `ui_items_reorder_rejected`. A regression that logs the wrong id
  or drops a field would pass. Assert these `extra` values in the existing caplog tests.
- **No test for the absence of a log at the 404/409 mapping.** Needed together with the log decision
  above: either assert that nothing is logged (current contract) or assert the new line.
- **Reorder with an unknown id answers 400, not 404, and that is only characterised, not specified.**
  The 24 characterization tests record 400 `Invalid item order` for an unknown id in `item_ids`, while
  move/archive/restore answer 404 for an unknown item. The difference is inherited behaviour; if it is not
  intended, it is an API inconsistency (product decision, then change plus tests).

## Test Quality Issues

- **Structure tests pin code shape.** `tests/test_wishenka_112_structure.py` asserts that a private name
  (`_NOT_FOUND_ERRORS`) does not exist, that `_DOMAIN_ERRORS` is exactly five named classes, that the
  `reorder` type hint is `Callable[[list[int]], list[int]]`, and (AST scan) that no
  `hasattr`/`getattr` of two column names appears in two files. They served as the red repro for the
  refactor, but long term they fail on legitimate changes (adding a domain error, renaming the helper,
  changing the callback signature) and say nothing about behaviour; the AST test covers only two named
  columns and two files, so the same pattern elsewhere is not caught. Propose: remove the first two and
  keep at most the AST guard, or replace it with a ruff/lint rule or a short note in `doc/dev`. Same
  family as the "guard that breaks on rename" note in WISHENKA-137 (marker declaration check); this is a
  different file, so a separate item.
- **Per-module helper duplication.** `make_user` / `auth_header` are re-defined in
  `tests/test_items_ui_error_mapping.py`, following the existing convention (`make_user` is defined in 14
  test modules, `auth_header` in 6, nothing shared in `conftest.py`; `grep "def make_user\|def auth_header"
  tests/*.py` finds 22 definitions). The new module adds two more copies. Propose a shared helper
  module or fixtures in `tests/conftest.py` and migration of the existing modules in one pass. No existing
  Debt issue (WISHENKA-125..147) covers test-helper duplication outside the browser tests
  (WISHENKA-146/147 are CDP/browser-specific).
- **Suite duration.** The 24 characterization tests take about 42 s (about 1.7 s per case, each builds a
  user, a wishlist and items through the real app), a share of the 504 s full run. The parametrized
  matrix (5 routes x 404/409 cases) could share a module-scoped app/database. Minor; fold into the
  helper-sharing task above.

## Performance Concerns

None. The probes removed were in-memory attribute checks; the number of queries and of
`reorder_wish_items` calls is unchanged (pinned by the spy test). `_reordered_response` now builds
`current_ids` once instead of twice, a negligible gain.

## Deviations from the Architecture

None found. Architecture assumption about unknown-id reorder (404) was corrected in Step 3 to 400 and is
recorded in `00-roadmap.md`; it is behaviour, not a deviation of the implementation.

## Hardcoded Values

None added. The response details `Wishlist is archived` and `Resource not found` are existing string
literals in `_raise_http` (not shared with the tests, which assert them as literals).

## Follow-up Tasks

All items are NON-BLOCKER and ticketed (items 1+2 = WISHENKA-148, 3 = 149, 4+7 = 150, 5 = 151, 6 = 152). No duplicates
of WISHENKA-125..147 were found; related existing issues are referenced.

1. **NON-BLOCKER, priority Low, about 2 SP: pin the log fields and the 404/409 logging contract.** Assert
   `actor_id`, `user_id`, `wishlist_id` in the caplog tests for `ui_items_reordered`, `ui_item_moved`,
   `ui_items_reorder_rejected`; add a test for the (absence of or new) log at the 404/409 mapping. Covers
   "Log fields are not pinned" and "No test for the absence of a log".
   Jira: https://pypost.atlassian.net/browse/WISHENKA-148 (merged with item 2)

2. **NON-BLOCKER, priority Low, about 2 SP: log the domain exception class server-side at the 404/409
   mapping.** Add a DEBUG/INFO line in `_raise_http` (event name, exception class, status, ids; no client
   response change) so that 404 triage is possible; combine with the test from item 1.
   Jira: https://pypost.atlassian.net/browse/WISHENKA-148 (merged with item 1)

3. **NON-BLOCKER, priority Low, about 3 SP: single mapping for domain errors in `items_ui.py`.** Replace
   `_DOMAIN_ERRORS` plus the `isinstance` special case in `_raise_http` with one exception-to-HTTP table
   and remove the repeated `try/except ... _raise_http` blocks with a helper. Behaviour pinned by the
   existing 24 tests. Do after item 2 (same function).
   Jira: https://pypost.atlassian.net/browse/WISHENKA-149

4. **NON-BLOCKER, priority Low, about 2 SP: prune the structure tests.** Delete
   `test_domain_errors_group_replaces_not_found_errors` and `test_reorder_callback_takes_only_current_ids`
   (they pin names and a type hint), keep or generalise the AST guard against `hasattr`/`getattr` column
   probes (all of `wishenka/wishlists/`, or a lint rule). Relates to WISHENKA-137 in spirit only.
   Jira: https://pypost.atlassian.net/browse/WISHENKA-150 (merged with item 7)

5. **NON-BLOCKER, priority Low, about 5 SP: share test helpers.** Move `make_user` / `auth_header` into
   `tests/conftest.py` (or a `tests/helpers.py`) and migrate the 14 / 6 existing modules; consider a
   module-scoped fixture for the error-mapping matrix to cut its 42 s. Touches many unrelated test
   modules, hence a separate task, not part of WISHENKA-112.
   Jira: https://pypost.atlassian.net/browse/WISHENKA-151

6. **NON-BLOCKER, priority Low, about 1 SP: decide and document the reorder-with-unknown-id status
   (400 vs 404).** Product/API decision; then either document the inconsistency in `doc/dev` or align it
   and update the characterization test. Can be dropped if the team confirms 400 as the contract.
   Jira: https://pypost.atlassian.net/browse/WISHENKA-152

7. **NON-BLOCKER, priority Low, about 1 SP: test for the missing-column failure.** One test that a result
   row without `display_order` / `warn_on_delete_reserved` fails loudly (AttributeError, 500) instead of
   defaulting, so the intended behaviour is pinned. Can be merged into item 4 if that task is taken first.
   Jira: https://pypost.atlassian.net/browse/WISHENKA-150 (merged with item 4)

References only (no ticket): WISHENKA-126 (untracked `core` file), WISHENKA-111 (Alembic migrations that
guarantee the columns), WISHENKA-137 (marker-guard fragility, similar family).
