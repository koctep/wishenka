# WISHENKA-267: Technical Debt Analysis

No new technical debt. The change publishes the CSRF string already stored
in the `prepareCsrf` local cache onto `window.csrfToken` in the same
generation-matched branch, and clears `window.csrfToken` in the same place
that clears the local after an `Invalid CSRF token` response
(`wishenka/web/static/app.js`). There is no new follow-up.

Reviewed: those two assignments, `10-requirements.md`,
`20-architecture.md`, `30-failing-repro.md`, `40-code-cleanup.md`, and
`50-observability.md`.

## Shortcuts Taken

None. The architecture already names this pair of assignments. No second
fetch, retry, longer wait, header hook, or move-handler change was added.
The local cache remains the value copied onto `X-CSRF-Token`.

## Code Quality Issues

None. Both writes sit next to the existing local `csrfToken` assignments.
No new hardcoded timeout, status, or secret was introduced.
`CSRF_TIMEOUT_MS` stays 10000.

## Missing Tests

No `do-testing` blocker. No new test was added.
`tests/test_wishlist_htmx_smoke_browser.py` declares
`pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`, which
covers `test_real_htmx_move_button_with_cookie_and_csrf`. That node waits
for `Boolean(window.csrfToken)` and then moves the wish. The module has
no function-level timeout override.

That node passes when collected after
`tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
(2 passed in Step 4). Collected alone, setup ERRORs. That `ImportError`
is existing work, already WISHENKA-357, and is not a gap this task opened.

## Performance Concerns

None. `prepareCsrf` still fetches `GET /api/auth/csrf` once. Publishing
the string is an assignment beside the local cache. No extra request,
poll, or server work was added.

## Follow-up Tasks

None. There is no new follow-up.

The isolated collection error is already WISHENKA-357. It is not a new
follow-up. `NON-BLOCKER — pre-existing`. When
`tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
is collected alone, setup raises `ImportError` and cannot import
`WishlistStore` from the partially initialized module
`wishenka.wishlists.store`. The node id is:

- `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`

User documentation under `doc/` was left unchanged. A signed-in move
still uses the token the page already fetched. Developer docs still
belong to Step 8.
