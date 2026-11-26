# WISHENKA-305: Technical Debt Analysis

No blockers. No new debt. WISHENKA-292 follow-up item 3 is addressed.
Each success event is written once by the domain operation. The history
route does not repeat it. A deleted-wishlist refusal on `record_view`
stays `view_history_deleted_wishlist_denied`.
`favorite_deleted_wishlist_denied` stays on adding a favorite.
`tests/test_wishenka_305_history_log_once.py` has
`pytestmark = pytest.mark.timeout(30)`. The full suite was not run.

Reviewed: `WishlistService.record_view` and `get_history`,
`RepoWishlistOps.record_view` and `get_history`, `GET /api/history` and
`POST /api/history/{wishlist_id}` in `wishenka/web/routes/wishlists.py`,
and `tests/test_wishenka_305_history_log_once.py`.

## Source debt from WISHENKA-292

Follow-up item 3 of `ai-tasks/WISHENKA-292/60-tech-debt.md` is this task.
Jira: [WISHENKA-305](https://pypost.atlassian.net/browse/WISHENKA-305).
Done in this task. Not an open follow-up.

- **Item 3.** Addressed. `view_history_recorded` is one INFO line on
  `record_view` in `WishlistService` and in `RepoWishlistOps`, logger
  `wishenka.wishlists`. `view_history_listed` is one INFO line on
  `get_history` in both adapters, same logger, with `count`. A request
  uses one adapter, so one action writes each success name once. The
  history route does not write either name.
- **Denial names.** Addressed. A deleted wishlist on `record_view` writes
  `view_history_deleted_wishlist_denied` and does not write
  `favorite_deleted_wishlist_denied`. That favorites denial stays on
  `add_favorite` in both adapters.

## Shortcuts Taken

None. The history route stays a thin adapter. Both domain adapters own
the same events because a normal request uses `RepoWishlistOps` and an
injected `WishlistService` does not. That split is the one already used
for `view_history_cleared`.

## Code Quality Issues

None new. Each adapter has one call site for a success event. Those
sites do not both run for one request. The route has no second copy.

## Missing Tests

No acceptance gap. `tests/test_wishenka_305_history_log_once.py` has
`pytestmark = pytest.mark.timeout(30)`. It counts one recorded event and
one listed event on `wishenka.wishlists` for the in-memory service and
for `RepoWishlistOps`. It keeps the history denial name on `record_view`
and the favorites denial name on `add_favorite`.

## Performance Concerns

None. The change moves log calls. Listing stays capped at 20.

## Follow-up Tasks

No new follow-up. Follow-up count: 0.

No new ticket.

### Pre-existing test failures

The full suite was not run. Already-filed suite failures are not
repeated here.

User documentation under `doc/` was left unchanged. Developer docs that
still say the history route writes these events belong to Step 8.
