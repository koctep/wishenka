# WISHENKA-311: Technical Debt Analysis

No new technical debt. No follow-up. Nothing in this change blocks close.

The change is test-only. The busy quick-add check and the viewing-history
open check poll the same predicates they already used, up to the existing
45 second module budget. A primed parallel run passed 81 items. Product
code was not edited.

Reviewed: the two named checks, `10-requirements.md`,
`20-architecture.md`, `30-failing-repro.md`, `40-code-cleanup.md`, and
`50-observability.md`.

## Shortcuts Taken

None. The request stays held until the busy-form check releases it.
Both checks then settle on a condition they can see. `WAIT` stays 3.0
seconds. The 5 second driver default, `LOAD_TIMEOUT`, and
`pytest.mark.timeout(45)` stay as they are. Shared helpers keep today's
defaults. A failed history read is retried inside this check's poll.
That retry does not raise the client's own 10 second call.

## Code Quality Issues

None. The literal `45` passed into these two checks is the module mark
already on both files. It is not a new constant, and it is not a longer
copy of `WAIT`. Other checks in the same files still use the short
defaults. `_older_list_is_first` returns `bool`, so the poll predicate
is a real bool. No edit under `wishenka/`.

## Missing Tests

No `do-testing` blocker. No new test was added. Both modules already
declare `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`.
The two named checks have no function-level timeout override. Every
poll they pass a deadline into has that deadline. The module mark
covers:

- `tests/test_cross_screen_comfort_browser.py::test_htmx_pending_request_marks_the_form_busy`
- `tests/test_history_screen_browser.py::test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works`

The primed parallel run (`TEST_WALL_LIMIT=1800`, `PYTEST_JOBS=2`,
`test_stale_giver_card_is_neutral` plus both browser modules) recorded
in Step 4 was `2 workers [81 items]`, `81 passed` in 33.98 s. Both
named checks passed.

## Performance Concerns

None in the product. No query, client loop, or server path was added.
The polls are bounded by the 45 second mark the modules already have.
That mark was not raised.

## Follow-up Tasks

No new follow-up. The items below already have tickets. Do not file
them again. Neither blocks close of WISHENKA-311.

### Pre-existing test failures (`NON-BLOCKER — pre-existing`)

Unprimed two-module run. Jira:
[WISHENKA-357](https://pypost.atlassian.net/browse/WISHENKA-357).

`PYTEST_JOBS=2` on the two browser modules alone, without the priming
node. Step 3 recorded `2 workers [80 items]`, `80 errors` in 5.00 s.
Every item dies in `migrated_db_template` on `ImportError`: cannot
import `WishlistStore` from the partially initialized module
`wishenka.wishlists.store`. No page opened. The two named checks are
in that set:

- `tests/test_cross_screen_comfort_browser.py::test_htmx_pending_request_marks_the_form_busy`
  — `NON-BLOCKER — pre-existing`
- `tests/test_history_screen_browser.py::test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works`
  — `NON-BLOCKER — pre-existing`

Full-suite hang. Jira:
[WISHENKA-285](https://pypost.atlassian.net/browse/WISHENKA-285).

A full `make test` that stops at 600 seconds was not run and is not
this task's proof. `NON-BLOCKER — pre-existing`. No node id: the
failure is the wall limit, not an assertion in these two checks.

User documentation under `doc/` was left unchanged. Developer docs
still belong to Step 8.
