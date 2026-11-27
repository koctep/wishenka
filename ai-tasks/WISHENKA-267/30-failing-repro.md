# WISHENKA-267: Failing repro (Step 3)

The red check is the standing test
`tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`.
It waits 5 seconds for `Boolean(window.csrfToken)` with the description
`CSRF token from /api/auth/csrf`. This step does not add a test, does not
edit that test, and does not change product code. The 5 second wait is
unchanged.

## Isolated collection

```text
make test-serial PYTEST_ARGS="tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf"
```

Setup ERROR before the assertion:
`ImportError: cannot import name 'WishlistStore' from partially initialized module 'wishenka.wishlists.store'`.
That cycle is WISHENKA-357. It is left as-is.

## Primed run

Collecting `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
first finishes the import. That node is harness priming only.

```text
make test-serial PYTEST_ARGS="tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf"
```

`test_stale_giver_card_is_neutral` passed. The smoke check failed:

```text
tests.browser_cdp.PageWaitTimeout: timed out after 5s waiting for: CSRF token from /api/auth/csrf
last value: False
```

The page snapshot in that failure records `GET /api/auth/csrf` with status 200.
The predicate stayed `False` for the whole 5 second wait.
