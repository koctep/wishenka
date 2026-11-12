# WISHENKA-57: Technical Debt Analysis

## Shortcuts Taken

Wish inventory writes take SQLite's reserved lock with `BEGIN IMMEDIATE` on the
wishlist engine (`wishenka/wishlists/store.py`, `_configure_immediate_transactions`
and `WishlistStore._immediate`). SQLite still has one writer for the file, so a
change to an unrelated wish waits on that same lock. When the wait exceeds
`busy_timeout` (5000 ms), the waiting attempt rolls back, raises
`InventoryBusyError`, and leaves its rows unchanged.
`tests/test_shared_inventory_multiprocess.py::test_different_wishes_both_succeed`
shows both wishes commit when each transaction finishes inside that wait. The
accepted architecture records this queue: a busy wish must not refuse another
wish for a shortage and must not rewrite the other wish's rows. A timeout is a
retryable refusal. **NON-BLOCKER — Low.** The quantity formulas are the outcome
this task delivered and are not listed as debt.

`UserStore` (`wishenka/users/store.py`) opens the same `settings.database_url`
as `WishlistStore` (`wishenka/web/app.py`) and runs `engine.begin()` without
`isolation_level = None` and without a `BEGIN IMMEDIATE` listener. User writes
stay deferred transactions on the shared file. A user upsert can upgrade a read
transaction after an inventory commit, or hold the single writer while a wish
change waits. Inventory copies still take the reserved lock before they read a
wish, so this path does not let two copies commit the same free units.
**NON-BLOCKER — Medium.**

## Code Quality Issues

The edit modal in `wishenka/web/templates/partials/item_edit_modal.html` is
Russian (`Редактировать желание`, `Закрыть`). The quantity-lock error in
`wishenka/web/routes/items_ui.py` is the Russian sentence about a quantity
below the booked amount. The busy path in that same handler sets
`error_message` to the English sentence `The wish was busy, the edit was not
saved, and it can be submitted again.` The API detail on
`InventoryBusyError` (`The wish was busy and the attempt changed nothing`)
matches the other HTTP details in `wishenka/web/routes/items.py`. The modal
sentence is the mismatch a person sees. It names no gifter.
**NON-BLOCKER — Low.**

`PRAGMA busy_timeout=5000` is repeated in the wishlist connect listener, the
begin listener, the cleanup helpers, and `UserStore`. That is the timeout the
architecture requires. It has no separate follow-up.

Wishlist routes (`wishenka/web/routes/wishlists.py`) and the non-edit UI helper
`_execute` let `InventoryBusyError` leave the handler, so those requests still
become HTTP 500. Item saves are the routes specified as HTTP 503. That split
has no separate follow-up.

`execute_wish` loads the parent wishlist and its members, resolves a
reservation id inside the open transaction, and persists the item, changed
reservations, and the reservation counter. It does not call `_write`.

## Missing Tests

`tests/test_shared_inventory_multiprocess.py` sets
`pytestmark = pytest.mark.timeout(60)`. Every other collected module under
`tests/` declares `pytest.mark.timeout` at module or function scope.
`tests/test_preview_resource_reuse.py` also overrides one test at 120 seconds.
Timeout markers are present on every collected test. This check does not block
closing the task.

The module covers the quantity races, a lock held past `busy_timeout`
(`InventoryBusyError`, an unchanged balance, and `wishlist_inventory_busy`),
and the commit, domain-refusal, `ValueError`, and storage-rollback logs. Those
store tests use `caplog.at_level` on `wishenka.wishlists.store`.

No test calls the item routes. `wishenka/web/routes/items.py` `execute` maps
`InventoryBusyError` to HTTP 503 with `detail` equal to the busy message.
`submit_edit_item` returns HTTP 503 and `partials/item_edit_modal.html` with
the busy sentence. A search of `tests/` finds `InventoryBusyError` only in
`tests/test_shared_inventory_multiprocess.py`. **NON-BLOCKER — Medium.** The
handlers are in place. The HTTP status and the modal body are untested.

This step found no failing-test follow-up. The roadmap records `make test` at
396 passed (step 5) and this module at 13 passed (step 6).

## Performance Concerns

One SQLite writer serializes wish changes that do not share rows, including
creates that also update the shared `reservation` counter. The wait is bounded:
after 5000 ms the attempt becomes `InventoryBusyError` and writes nothing.
This task adds no new latency target. Commit duration is not measured. Step 6
left metrics unset because the service has no exporter. **NON-BLOCKER — Low.**
This is the same file-lock limit as Shortcuts Taken.

## Follow-up Tasks

No follow-up below blocks closing WISHENKA-57. Each one is deferred work. The
shared quantity outcome stays on this task and is not a follow-up.
WISHENKA-49 already owns locking and race stress tests; none of these items
reopens that suite.

- **NON-BLOCKER — Low: Unrelated wishes share one SQLite writer.** A wish that
  holds the file lock longer than `busy_timeout` makes another wish return
  `InventoryBusyError` even though that wish's rows were not in conflict. The
  architecture allows the wait and the retryable refusal, and
  `test_different_wishes_both_succeed` covers the short case. A later change
  can move inventory commits onto a store that commits different wishes
  concurrently, without reopening the quantity formulas.
  Jira: [WISHENKA-118](https://pypost.atlassian.net/browse/WISHENKA-118)
- **NON-BLOCKER — Low: Russian busy sentence in the edit modal.** Replace the
  English `error_message` in `submit_edit_item` with a Russian sentence that
  states the wish was busy, the edit was not saved, and the form can be
  submitted again, and that names no gifter. Keep the modal open at HTTP 503.
  The API detail can stay the English `InventoryBusyError` message.
  Jira: [WISHENKA-119](https://pypost.atlassian.net/browse/WISHENKA-119)
- **NON-BLOCKER — Medium: HTTP 503 route coverage.** Add tests that `items.py`
  `execute` returns HTTP 503 with the busy detail and no gifter id, and that
  `submit_edit_item` returns HTTP 503 with `partials/item_edit_modal.html`,
  the submitted fields, and the busy sentence. Give those tests an explicit
  `pytest.mark.timeout`.
  Jira: [WISHENKA-120](https://pypost.atlassian.net/browse/WISHENKA-120)
- **NON-BLOCKER — Medium: UserStore deferred transactions on the shared file.**
  Start `UserStore` writes with the same `BEGIN IMMEDIATE` contract as the
  wishlist engine, or use one shared engine, so a user upsert does not upgrade
  a deferred transaction across an inventory commit on `settings.database_url`.
  Map a timed-out lock to a retryable error.
  Jira: [WISHENKA-121](https://pypost.atlassian.net/browse/WISHENKA-121)
