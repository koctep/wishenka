# WISHENKA-298: Failing repro (Step 3)

N/A — no behavioral change. `20-architecture.md` says the contract already
holds: an anonymous share shows the free remainder, and a missing caller is
logged as `anonymous_gifter` with `is_recipient` false. A new test written
to go red first would be green on the first run, so it would not demonstrate
a defect. No test file was added. Product code and existing tests were not
edited. WISHENKA-356, WISHENKA-357, and WISHENKA-311 stay out of this step.

The two standing checks already live in:

- `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
- `tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability`

## Command

```sh
.venv/bin/pytest tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability -q --tb=line
```

Run from `/home/src`.

## Result

**2 passed, 1 warning in 0.87s** (exit 0). Pytest collected 2 items. Both
nodes passed:

- `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
- `tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability`

The warning is `StarletteDeprecationWarning` from `fastapi/testclient.py`,
not a test failure.
