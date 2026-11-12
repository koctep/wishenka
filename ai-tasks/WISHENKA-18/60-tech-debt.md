# WISHENKA-18: Technical Debt Analysis

## Shortcuts Taken

`create_reservation` raises `ValueError("Reservation quantity must be at least 1")`
before it looks up the wish. On the HTTP path the store runs first.
`WishlistStore.execute_wish` calls `_load_wish`, and `_load_wish` raises
`ItemNotFoundError` or `WishlistNotFoundError` before it calls the route
action. `execute` in `wishenka/web/routes/reservations.py` maps those errors
to HTTP 404 `Resource not found`, and it maps `ValueError` to HTTP 400 with
the quantity sentence. A non-positive create for an item `execute_wish`
cannot load is 404. The quantity floor runs after the wish is resolved. A
loaded wish returns 400. **NON-BLOCKER — Low.** The promise is still refused
and no row is stored. The free-remainder rules from WISHENKA-57 are unchanged
and are not debt.

`_guard_reservation_mutation` checks the path, then the recipient, then
`_ensure_reservation_writable`, and only then does the method compare
`user_id`. On an archived list the guard raises `WishlistArchivedError`
(HTTP 409). On a deleted list it raises `WishlistDeletedError` (HTTP 404
`Resource not found`). A non-holder who is not the recipient gets that list
result. The ownership 403 is not reached. **NON-BLOCKER — accepted by
design.** The architecture refuses every action on an archived list with 409
and on a deleted list with 404. The closed list is checked before the status
check so a deleted list does not surface as a status conflict. The holder is
not named. This order is not a follow-up.

The five routes, `PromiseActionDTO`, and the recipient refusals are the
surface this task delivered. They are not debt.

## Code Quality Issues

The route handlers stay thin: each one calls an existing reservation method
through `execute` and `project_reservation_action`. The fixed details
`Cannot promise this wish`, `Forbidden`, and `Resource not found` are the
censorship contract. No rename, split, or extra abstraction is waiting on
this task.

`ReservationQuantityDTO` leaves `ge` unset so create and resize share the
service sentence. That split is what puts the floor after `_load_wish` on
create. The follow-up below is the place to refuse a non-positive create
before the store resolves the wish.

## Missing Tests

`tests/test_reservation_actions_api.py` sets
`pytestmark = pytest.mark.timeout(30)`. Every other collected module under
`tests/` declares `pytest.mark.timeout` at module or function scope.
`tests/test_preview_resource_reuse.py` also overrides one test at 120
seconds. `tests/__init__.py` collects no tests. Timeout markers are present
on every collected test. This check does not block closing the task.

`test_non_positive_quantity_is_rejected` covers quantity `0` and a negative
quantity for a wish the store can load, for the recipient and the gifter,
and a non-positive resize of a loaded promise. It does not cover a
non-positive create whose item row `_load_wish` cannot find. **NON-BLOCKER —
Low.** That case is the follow-up below.

HTTP 503 on these routes is tested.
`test_busy_promise_logs_warning_without_gifter` raises `InventoryBusyError`
from `execute_wish` on create and expects HTTP 503 and one
`reservation_inventory_busy` warning with no gifter. Cancel, quantity
change, purchase, and undo use the same `execute` handler. The busy mapping
is not a follow-up.

`test_archived_list_refuses_every_action` and
`test_deleted_list_refuses_every_action_and_keeps_the_cancellation` cover
the holder. The list exception is raised in the guard before the ownership
comparison, so a non-holder reaches that same refusal. No separate test
follow-up.

This step found no failing-test follow-up. The roadmap records this module
at 19 passed in step 6.

## Performance Concerns

Each promise action is one `execute_wish` transaction with `BEGIN IMMEDIATE`,
the boundary WISHENKA-57 already uses. This task adds no new latency target
and no new query. The single SQLite writer stays on that task. It is not
reopened here.

## Follow-up Tasks

No follow-up below blocks closing WISHENKA-18. The delivered promise API is
not a follow-up. The WISHENKA-57 quantity rules are not a follow-up. The
HTTP 503 mapping and the closed-list order are not follow-ups.

- **NON-BLOCKER — Low: Non-positive create is 404 when the wish does not
  load.** `execute_wish` resolves the wish before `create_reservation`
  applies the quantity floor. A create with quantity below 1 for an item
  `_load_wish` cannot load returns HTTP 404 `Resource not found`. The same
  request for a loaded wish returns HTTP 400 `Reservation quantity must be
  at least 1`. Refuse a non-positive quantity on
  `POST /api/wishlists/{wishlist_id}/items/{item_id}/reservations` before
  `execute_wish`, with that same detail, and log
  `reservation_validation_error` without a gifter id. Keep the service
  check for other callers. Do not change `execute_wish` or the quantity
  formulas.
  Jira: [WISHENKA-122](https://pypost.atlassian.net/browse/WISHENKA-122)
