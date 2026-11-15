# Verification matrix for product invariants

## Overview

Checklist for WISHENKA-37. It records which invariant is checked where.
WISHENKA-38 closed rows S5, S6, S8, and A3 with
`tests/test_surprise_role_context.py`. WISHENKA-39 closed row R5 with
the six checks in `tests/test_booking_ceiling_r5.py`.

This file is the developer document for that checklist.
`doc/dev/architecture.md` links it from the subsystem list. The service
does not read the file. There is no configuration for the matrix.

Accepted rules: `ai-tasks/WISHENKA-37/10-requirements.md`.
Design of this index: `ai-tasks/WISHENKA-37/20-architecture.md`.

The service is Python 3.12+. This document adds no product code and no
new tests.

What the matrix indexes is under Modules this matrix indexes: API exits,
logs, the share page, and the tests named on each row. How to use a row
is under How to read a row. Row coverage is under Where the gaps live.
The three families follow those sections.

## How to read a row

Each row has an identifier, the rule, the module that is the exit, the
existing test, and the gap. A gap names the sibling that owns the suite.
The share-link visit that creates no account is closed on A3. Row R5
is closed by the six checks in `tests/test_booking_ceiling_r5.py`.

"Covered" means the named test already asserts that row. A later
end-to-end walk can still be open when the row says the walk is open.

## Running R5 checks

Run the R5 suite from the repository root:

```bash
make test PYTEST=".venv/bin/pytest tests/test_booking_ceiling_r5.py"
```

The suite uses temporary SQLite databases. It exercises the production
`WishlistStore.execute_wish` path both in one process and with one spawned
process per gifter; it does not require a running web server or external
configuration.

## R5 configuration and troubleshooting

R5 intentionally has no runtime setting. Its bounded test inputs live in
`tests/test_booking_ceiling_r5.py`: five gifters, two or three free units,
three repeated contentions, and two load rounds. Its timeout markers and the
barrier, join, queue-drain, and termination limits prevent an unbounded test.

An `InsufficientQuantityError` is an expected losing booking attempt. An
`InventoryBusyError`, a missing worker result, or a non-zero worker exit is a
test failure: inspect the test output and the SQLite transaction settings
(`BEGIN IMMEDIATE` and `busy_timeout`) before changing the product. Further
locking or isolation work belongs to WISHENKA-49, not this verification suite.

Accepted product behavior, repeated on the rows that record it:

- An unidentified opener of the share page sees the free remainder and
  does not see a booking control.
- The public list answer omits the free remainder.
- A recipient exit omits the gifter, the reservation, the booked
  quantity, and the free remainder.

## Modules this matrix indexes

The matrix is not on the request path. A row names the module a
developer would open, and the test that already calls it.

### API exits

- `wishenka/web/routes/items.py` — `list_items`, `get_item`. Logger
  `wishenka.web.items`. Prefix `/api/wishlists/{wishlist_id}/items`.
- `wishenka/web/routes/reservations.py` — promise create, change,
  cancel, purchase, undo. Logger `wishenka.web.reservations`. Prefix
  `/api/wishlists/{wishlist_id}/items/{item_id}/reservations`.
- `wishenka/web/routes/wishlists.py` — `public_wishlist` and
  `projection`. Logger `wishenka.web.wishlists`. Path
  `GET /api/public/wishlists/{token}`.
- `wishenka/wishlists/service.py` — `project_wish_item`. Logger
  `wishenka.wishlists`.
- `wishenka/wishlists/schemas.py` — `WishItemRecipientViewDTO`,
  `WishItemGifterViewDTO`, `PromiseActionDTO`.
- `wishenka/wishlists/policy.py` — `WishlistAccessPolicy.is_recipient`.
  The recipient follows the wish.

### Logs

- `wishenka/web/app.py` — `ShareTokenAccessFilter` on `uvicorn.access`,
  and `RequestLoggingMiddleware` on logger `wishenka.web`. Both rewrite
  `/share/{token}` and `/api/public/wishlists/{token}` before the
  record is emitted.
- `wishenka/logging.py` — `JsonFormatter` and `configure_logging`.
- `wishenka/web/routes/reservations.py` — client promise-route logs.
- `wishenka/web/routes/sharing.py` — logger `wishenka.web.sharing`,
  event `wishlist_shared_view` (wishlist id, not the token).
- `wishenka/web/routes/wishlists.py` — event `public_wishlist_viewed`
  carries the wishlist id.
- `wishenka/wishlists/service.py` — reservation audit and surprise
  warnings.
- `wishenka/wishlists/store.py` — wish-transaction commit and rollback
  logs. Logger `wishenka.wishlists.store`.

### Share page

- `wishenka/web/routes/sharing.py` — `view_public_share`
  (`GET /share/{public_token}`) and `get_item_card_partial`
  (`GET /wishlists/{wishlist_id}/items/{item_id}/card`).
- `wishenka/web/templates/share_wishlist.html`.
- `wishenka/web/templates/partials/item_card.html` — giver facts render
  when `item.is_recipient` is false. The remainder line uses
  `item.available_quantity`. The booking form requires `can_promise`,
  which requires `viewer_identified`.
- `wishenka/web/routes/reservations_ui.py` — cabinet
  `GET /web/reservations`.
- `wishenka/web/routes/items_ui.py` — item management UI. Guests do not
  receive quick-add or edit controls.

### Existing tests

The test modules cited by the rows below. Research in
`ai-tasks/WISHENKA-37/20-architecture.md` lists each function.
`GET /healthz` still does not close A3. The share visit does. Row R5
is `tests/test_booking_ceiling_r5.py`.

### Notifications

No module under `wishenka/` sends a message to the recipient. S6 is
closed because the recipient walk produces no recipient-facing
notification. This checklist does not add a sender.

### Shipped behavior this matrix points at

- WISHENKA-18 — promise actions and recipient silence on those actions
  and on wish reads. `wishenka/web/routes/reservations.py`.
- WISHENKA-19 — wish-card giver controls. `sharing.py` and
  `partials/item_card.html`.
- WISHENKA-20 — "My reservations" cabinet.
  `wishenka/web/routes/reservations_ui.py`.
- WISHENKA-57 — shared quantity outcome when more than one copy accepts
  bookings. `wishenka/wishlists/store.py` (`execute_wish`).
- WISHENKA-38 — one recipient walk closes S5, S6, and S8. A share
  visit closes A3. Both checks are in
  `tests/test_surprise_role_context.py`.
- WISHENKA-39 — race and load ceiling (R5). The six checks are in
  `tests/test_booking_ceiling_r5.py`.

The free remainder indexed here is the one already computed in
`project_wish_item`: requested quantity, minus received units, minus
units on `ACTIVE` and `PURCHASED` promises, floored at zero for the
view. Writes keep that ceiling inside the wish-scoped transaction from
WISHENKA-57.

The author's archive warning may say that a booking exists before an
archive. That prompt is an author prompt in
`wishenka/web/routes/items_ui.py` and
`wishenka/web/templates/partials/item_archive_modal.html`. It is not a
recipient exit. This matrix leaves that exception where it is.

A recipient who has no Telegram user, and what happens to promises when
a profile is deleted, stay open product questions.

## Where the gaps live

A row whose gap is none is covered by the tests named on that row. An
open row names the sibling that owns the suite.

WISHENKA-38 closed S5, S6, S8, and A3. The checks are in
`tests/test_surprise_role_context.py`.

- S5, S6, and S8.
  `test_recipient_walk_hides_booking_in_response_log_and_notice`
  is one owner read of a booked wish. It judges the answer, the log
  of that request, and the absence of a recipient-facing notice.
- A3.
  `test_share_link_visit_creates_no_account` opens the share link
  with no session. The visit creates no account.

WISHENKA-39 closed R5 with `tests/test_booking_ceiling_r5.py`.

- R5. One unit each and the whole remainder, on one store and on one
  process per gifter. Repeated contention and the load profile keep
  the same ceiling.
  `test_one_copy_one_unit_each`,
  `test_many_copies_one_unit_each`,
  `test_one_copy_whole_remainder`,
  `test_many_copies_whole_remainder`,
  `test_repeated_contention_many_copies`, and
  `test_load_profile_one_copy_and_many_copies`.
  R1–R4 stay on the tests already named on those rows.

## Family 1. Surprise at every exit

A response the recipient of a wish can receive omits the gifter, the
reservation, the booked quantity, and the free remainder. It also omits
whether the gift has been bought. A log written while serving that
recipient does not name a gifter. A notification addressed to that
recipient does not reveal a booking or a purchase.

On a personal list the owner is the recipient of every wish, including
a wish that has only a display name. On a collaborative list the
recipient is the person that wish is for. The same person can be a
gifter of one wish and the recipient of another.

### S1. Recipient wish read

The body of the wish list and of one wish, when the caller is the
recipient, includes the requested quantity and the received quantity.
It omits the gifter, the reservation, the booked quantity, and the
free remainder.

Modules:

- `wishenka/web/routes/items.py` — `list_items`, `get_item`.
- `wishenka/wishlists/service.py` — `project_wish_item` returns
  `WishItemRecipientViewDTO` when the caller is the recipient.
- `wishenka/wishlists/schemas.py` — `WishItemRecipientViewDTO`.
- `wishenka/wishlists/policy.py` — `WishlistAccessPolicy.is_recipient`.

Covered by:

- `tests/test_wish_items_crud_api.py`
  `test_get_items_and_single_item_surprise_invariant`
- `tests/test_wish_items_crud_api.py`
  `test_get_items_collaborative_addressing_surprise_invariant`
- `tests/test_reservation_actions_api.py`
  `test_recipient_create_and_wish_reads_stay_silent`
- `tests/test_reservations_surprise_invariant.py`
  `test_recipient_view_has_no_reservation_attributes`
- `tests/test_wishlist_roles_lifecycle.py`
  `test_zero_leak_projection_omits_reservation_data`

Gap for this exit alone: none. The combined walk is S8.

### S2. Recipient promise refusal

A recipient who tries to promise their own wish receives the same
refusal when the wish is free and when it is already promised. A
recipient who tries to change, cancel, or mark a promise receives the
same answer as a missing promise. The answer omits the gifter, the
booked quantity, and the free remainder.

Modules:

- `wishenka/web/routes/reservations.py` — create and the mutation
  routes under the reservations prefix.
- `wishenka/wishlists/service.py` — self-reservation refusal.
- `wishenka/web/routes/sharing.py` — `get_item_card_partial` drops a
  giver notice when the item is a recipient view.

Covered by:

- `tests/test_reservation_actions_api.py`
  `test_recipient_cancel_does_not_reveal_the_promise`
- `tests/test_reservation_actions_api.py`
  `test_recipient_create_and_wish_reads_stay_silent`
- `tests/test_reservation_actions_api.py`
  `test_recipient_create_refusal_hides_whether_a_promise_exists`
- `tests/test_reservation_actions_api.py`
  `test_recipient_mutation_refusal_matches_a_missing_promise`
- `tests/test_wish_card_giver_controls.py`
  `test_personal_owner_mutations_are_not_found`
- `tests/test_wish_card_giver_controls.py`
  `test_personal_owner_display_name_cannot_promise`
- `tests/test_reservations_surprise_invariant.py`
  `test_recipient_cannot_book_own_gift_raises_self_reservation_error`
- `tests/test_reservations_surprise_invariant.py`
  `test_coauthor_cannot_book_item_where_they_are_explicit_recipient`

Gap for this exit alone: none.

### S3. Recipient share page and wish card

The page opened by the share link, and the wish card on it, omit the
gifter's name, a booking sentence, and the free remainder when the
viewer is the recipient.

Modules:

- `wishenka/web/routes/sharing.py` — `view_public_share`,
  `get_item_card_partial`.
- `wishenka/web/templates/share_wishlist.html`.
- `wishenka/web/templates/partials/item_card.html` — the giver block is
  skipped when `item.is_recipient` is true.
- `wishenka/web/routes/items_ui.py` — reorder and archive responses
  use the same recipient projection.

Covered by:

- `tests/test_wishlists_htmx_sharing.py`
  `test_public_share_view_owner_surprise_invariant`
- `tests/test_wish_card_giver_controls.py`
  `test_personal_owner_display_name_hides_giver_facts`
- `tests/test_wish_card_giver_controls.py`
  `test_recipient_notice_refresh_has_no_booking_sentence`
- `tests/test_wish_card_giver_controls.py`
  `test_collaborative_list_decides_recipient_per_wish`
- `tests/test_wish_items_list_reorder_ui.py`
  `test_rbac_and_surprise_invariant_on_reorder_and_archive`

Gap for this exit alone: none.

### S4. Another gifter, and the cabinet

A gifter sees the free remainder and only their own promise. A refusal
does not name the person who holds the other units. The cabinet and a
successful refresh list only the caller's promises.

Modules:

- `wishenka/wishlists/schemas.py` — `WishItemGifterViewDTO` exposes
  `available_quantity` and `my_*` promise fields.
- `wishenka/web/templates/partials/item_card.html` — shortage and
  refusal notices, own-promise line.
- `wishenka/web/routes/reservations_ui.py` — cabinet list and card.
- `wishenka/wishlists/store.py` — the losing cross-process attempt,
  covered by the multiprocess test below.

Covered by:

- `tests/test_wish_card_giver_controls.py`
  `test_own_line_and_availability_show_together`
  (the gifter summary shows the free remainder and that caller's
  promise)
- `tests/test_wish_card_giver_controls.py`
  `test_gifter_refusal_notice_names_no_holder`
- `tests/test_wish_card_giver_controls.py`
  `test_shortage_leaves_the_last_promise`
- `tests/test_reservations_cabinet_ui.py`
  `test_groups_only_the_callers_promises`
- `tests/test_reservations_cabinet_ui.py`
  `test_success_refresh_hides_the_other_gifter`
- `tests/test_reservations_cabinet_ui.py`
  `test_personal_owner_and_collaborative_recipient`
- `tests/test_shared_inventory_multiprocess.py`
  `test_last_free_units_one_success_across_processes`
  (the losing attempt names no other gifter)

Gap for this exit alone: none. Load around the same ceiling is family 2.

### S5. Logs

A log written while the recipient views the wish does not name a
gifter. A log of a promise action on the client route does not name a
gifter. A refused recipient create is the same log when the wish has a
promise and when it does not. A refused recipient change carries the
path identifier and does not name a gifter.

Modules:

- `wishenka/web/routes/reservations.py` — logger
  `wishenka.web.reservations`.
- `wishenka/wishlists/service.py` — logger `wishenka.wishlists`.
- `wishenka/wishlists/store.py` — wish-transaction logs omit the row
  and the gifter.
- `wishenka/web/routes/items.py` — logger `wishenka.web.items`.
- `wishenka/web/routes/items_ui.py` — item UI privacy logs.

Covered by:

- `tests/test_reservation_observability.py`
  `test_zero_surprise_leaks_in_recipient_audit_trails`
- `tests/test_reservation_actions_api.py`
  `test_completed_promise_log_omits_the_gifter`
- `tests/test_reservation_actions_api.py`
  `test_recipient_create_refusal_hides_whether_a_promise_exists`
- `tests/test_reservation_actions_api.py`
  `test_recipient_mutation_refusal_matches_a_missing_promise`
- `tests/test_reservation_actions_api.py`
  `test_busy_promise_logs_warning_without_gifter`
- `tests/test_shared_inventory_multiprocess.py`
  `test_wish_transaction_logs_commit_without_row_or_gifter`
- `tests/test_shared_inventory_multiprocess.py`
  `test_wish_transaction_logs_domain_rollback_without_gifter`
- `tests/test_wish_items_tma_ui.py`
  `test_tma_ui_observability_privacy_invariants`
- `tests/test_surprise_role_context.py`
  `test_recipient_walk_hides_booking_in_response_log_and_notice`
  (the answer and the log of that same request)

That walk is one owner read. The body and every response header omit
the gifter, the reservation, the booked quantity, the free remainder,
and whether the gift has been bought. Requested quantity and received
quantity may remain. The log of that request does not name the gifter.
The separate checks listed above stay in place. The same test closes
S6 and S8.

Gap: none.

Operator records of a gifter's own booking may still identify that
gifter to operators. That stream is already checked by
`tests/test_reservation_observability.py`
`test_item_reserved_observability_event` and the sibling booking events
in the same module, and by `tests/test_wishlist_roles_lifecycle.py`
`test_reservation_audit_logging`, which asserts `gifter_id` is present.
Those records are an operator stream of the gifter's own action. They
are a recipient exit only if a recipient path emits them. This matrix
leaves that operator stream on the stories that shipped it.

These neighboring checks do not assert this row.
`tests/test_wishlist_roles_lifecycle.py`
`test_warning_logging_on_access_denial_and_surprise_invariant` asserts
warning event names only. `tests/test_wish_items_crud_api.py`
`test_item_observability_privacy_invariants_no_tokens_or_auth_data`
asserts capability tokens and the session secret stay out of item CRUD
logs. `tests/test_shared_inventory_multiprocess.py`
`test_wish_transaction_logs_storage_rollback_without_row_dump` asserts
the storage-failure log omits the row dump and the tokens. None of them
assert that a recipient log omits a gifter.

### S6. Notifications to the recipient

A message the service sends the recipient about a wish, a receipt, an
archive, or a reminder omits the gifter, the reservation, the booked
quantity, and the free remainder. The product sends no message to the
recipient. The proof is that the recipient walk produces no
recipient-facing notification and no queue row for the recipient.

Modules: `wishenka/notices/` (queue store, worker, sender) and
`wishenka/wishlists/service.py` (`_draft_receipt_notices`). The sender exists since
WISHENKA-23, but only as a giver notice. The owner, who is the recipient, never gets a row.

Covered by:

- `tests/test_surprise_role_context.py`
  `test_recipient_walk_hides_booking_in_response_log_and_notice`
- `tests/test_surprise_receipt_walk.py`
  `test_recipient_walk_creates_no_notice_for_owner` and
  `test_second_walk_receipt_and_gifted_read_hide_the_booking`

During the first walk, captured records do not name a notification, an
outbox enqueue, or a push (event name and message). The tables now exist, so the
former absence check was replaced by two assertions: `notice_rows` returns no
row of `notification_outbox` (and none for the owner), and `receipt_columns`
shows `wl_receipts` has no column outside the fixed five (no giver).
`test_recipient_walk_creates_no_notice_for_owner` repeats the empty-queue and
column check after a receipt, a promise and a purchase. The second walk records
a receipt on a promised wish and reads `GET .../gifted`: neither response nor
captured log carries a gifter, a booking or a booked quantity. The checks do not
look for notice copy. Notice-path log rules are in
[gift-receipt.md](gift-receipt.md).

Gap: the Telegram bot is mocked in every test, so the real sender is not
exercised (WISHENKA-156).

### S7. Public list answer for an unidentified visitor

The public list answer omits the free remainder. It also omits the
gifter, the reservation, and the booked quantity when the visitor is
not identified, including when a stale session is sent. That omission
is accepted product behavior.

An unidentified opener of the share page sees the free remainder and
does not see a booking control (A2). A recipient exit omits the gifter,
the reservation, the booked quantity, and the free remainder.

Modules:

- `wishenka/web/routes/wishlists.py` — `public_wishlist` calls
  `projection(wl, None, True)`. The public item dict has `quantity` and
  `received_quantity`. It has no `available_quantity`.

Covered by:

- `tests/test_wishlist_api.py`
  `test_anonymous_public_view_hides_existing_reservation`
- `tests/test_wishlist_api.py`
  `test_public_api_shows_persisted_wish_without_reservation_details`
- `tests/test_wishlist_management_ui.py`
  `test_anonymous_public_display_ignores_stale_session_and_hides_reservation`
  (calls `GET /api/public/wishlists/{token}` with a stale session
  cookie; the exit is this API, not the share page)

Gap for this exit alone: none. The share page showing the free remainder
to an unidentified opener is accepted product behavior (A2).

### S8. One walk across exits

For one booked wish, one recipient request meets the response rule, the
log rule, and the absence of a recipient-facing notification together.

Modules: `get_item` in `wishenka/web/routes/items.py`, the request log
from `RequestLoggingMiddleware` in `wishenka/web/app.py`, and
`project_wish_item` in `wishenka/wishlists/service.py`. No notification
module is on this walk.

Covered by:

- `tests/test_surprise_role_context.py`
  `test_recipient_walk_hides_booking_in_response_log_and_notice`

The caller is the owner of a personal list and therefore the recipient,
including a wish that has only a display name. The same test closes S5
and S6.

Gap: none.

## Family 2. Concurrent booking and the free-remainder ceiling

The ceiling is already in force. This family points at it. WISHENKA-57
shipped it together with the reservation limit in the product spec.

The free remainder is the requested quantity, minus units already
received, minus units occupied by intended and purchased promises.
After a successful new promise or a successful increase, that remainder
is zero or positive. A promise that would make it negative is refused
and leaves the last complete balance unchanged. A purchased promise
still occupies its units. A cancel or a decrease releases those units
once. Recording receipt does not close the promise. Two attempts to
take the same last units end with exactly one success for those units.
The attempt that loses is told the free remainder and is not told who
won.

One running copy still has `ItemConcurrencyCoordinator` in
`wishenka/wishlists/concurrency.py`. Another process cannot see that
lock. Several copies share `WishlistStore.execute_wish` in
`wishenka/wishlists/store.py`.

### R1. One copy, last units

Two bookings of the same free units inside one running copy leave a
remainder that is zero or positive. Only one of them takes those units.
An increase past the remainder is refused.

Modules:

- `wishenka/wishlists/concurrency.py` — `ItemConcurrencyCoordinator`.
- `wishenka/wishlists/store.py` — single-store allocation.
- `wishenka/web/routes/reservations.py` — shortage answer names the
  free remainder.

Covered by:

- `tests/test_reservations_surprise_invariant.py`
  `test_concurrent_race_condition_prevented_by_coordinator`
- `tests/test_reservations_surprise_invariant.py`
  `test_update_reservation_quantity_rejects_insufficient_balance`
- `tests/test_reservation_actions_api.py`
  `test_shortage_names_the_free_remainder`

`tests/test_wishlists_sqlite_repo.py`
`test_atomic_reservation_allocation_and_rollback` asserts a failed
allocation rolls back and leaves `available_quantity` at 2 with no
reservation row. It does not assert two bookings of the same units, so
it is not coverage for this row.

Gap for these examples: none.

### R2. Several copies

The shared quantity outcome from WISHENKA-57: one success for the last
units, a refused increase that keeps the earlier promise, a release
that returns units once, a lower requested quantity that sees the other
booking, receipt that is not capped by occupied units, unrelated wishes
that both succeed, and a busy wish that leaves the last complete
balance.

Module: `wishenka/wishlists/store.py` — `execute_wish`.

Covered by `tests/test_shared_inventory_multiprocess.py`:

- `test_last_free_units_one_success_across_processes`
- `test_increase_refused_leaves_earlier_promise`
- `test_cancel_releases_units_once`
- `test_smaller_quantity_releases_units_once`
- `test_lower_requested_quantity_sees_other_process_booking`
- `test_receipt_is_not_capped_by_occupied_units`
- `test_different_wishes_both_succeed`
- `test_one_store_keeps_self_booking_and_archive_rules`
  (one store: a refused second booking leaves a zero remainder and
  names no gifter; self-booking and an archived wish stay refused)
- `test_locked_wish_raises_inventory_busy_and_leaves_balance`

Gap for these examples: none.

### R3. Purchased units stay occupied

A purchase keeps the units out of the free remainder. A cancel returns
them. The wish card still shows the remainder after a shortage and does
not present the refused attempt as a saved booking.

Modules:

- `wishenka/wishlists/service.py` — purchase keeps the occupying
  status; cancel releases the units.
- `wishenka/web/templates/partials/item_card.html` — shortage copy and
  the booking form.

Covered by:

- `tests/test_reservations_surprise_invariant.py`
  `test_purchased_reservation_retains_inventory_lock`
- `tests/test_reservations_surprise_invariant.py`
  `test_cancel_reservation_restocks_available_quantity`
- `tests/test_wish_card_giver_controls.py`
  `test_shortage_leaves_the_last_promise`
- `tests/test_wish_card_giver_controls.py`
  `test_busy_inventory_does_not_look_like_a_booking`

Gap for these examples: none.

### R4. What the loser is told

The visible remainder is the free remainder after the successful
attempt. It is zero or positive. The sentence does not name the holder.

Modules:

- `wishenka/web/routes/reservations.py` — shortage body.
- `wishenka/web/templates/partials/item_card.html` — shortage and
  refusal sentences.
- `wishenka/wishlists/store.py` — losing cross-process attempt.

Covered by:

- `tests/test_reservation_actions_api.py`
  `test_shortage_names_the_free_remainder`
- `tests/test_wish_card_giver_controls.py`
  `test_shortage_leaves_the_last_promise`
- `tests/test_wish_card_giver_controls.py`
  `test_gifter_refusal_notice_names_no_holder`
- `tests/test_shared_inventory_multiprocess.py`
  `test_last_free_units_one_success_across_processes`

Gap for these examples: none.

### R5. Race and load beyond R1–R4

Repeated contention, many gifters, and a load profile that keeps the
same ceiling. Five gifters book through `WishlistStore.execute_wish`.
The units they book equal the free units. A refusal is
`InsufficientQuantityError` and adds no row. `InventoryBusyError`
fails the check.

Modules: the same write path as R2 (`WishlistStore.execute_wish` in
`wishenka/wishlists/store.py`).

Covered by `tests/test_booking_ceiling_r5.py`:

- `test_one_copy_one_unit_each`
- `test_many_copies_one_unit_each`
- `test_one_copy_whole_remainder`
- `test_many_copies_whole_remainder`
- `test_repeated_contention_many_copies`
- `test_load_profile_one_copy_and_many_copies`

One-unit checks ask for one of two free units. Whole-remainder checks
ask for all three free units. One-copy checks share one store.
Many-copies checks use one process per gifter. Repeated contention
runs three one-unit starts and three whole-remainder starts.
The load profile runs two rounds of both shapes on one store and two
rounds on many copies. R1–R4 stay on the tests already named on those
rows.

Gap: none.

## Family 3. Anonymous giver access by share link

A person who has the share link can open the list in the Mini App
without a separate registration or onboarding. Viewing does not grant
editing. Promising still identifies a Telegram user, as WISHENKA-18
already requires: an unnamed visitor does not store a promise. The link
is the way in. It is not a second account form.

The invite secret stays off the public page. After the owner replaces
the share link, the old link stops opening the list.

### A1. Open by link with no session

The share page shows the list title and the wishes. It omits quick-add
and edit controls. It omits the reservations cabinet. The invite secret
is absent.

Modules:

- `wishenka/web/routes/sharing.py` — `view_public_share`.
- `wishenka/web/templates/share_wishlist.html`.
- `wishenka/web/routes/items_ui.py` — guest and anonymous callers do
  not receive item-edit UI.
- `wishenka/web/routes/reservations_ui.py` — anonymous cabinet refusal.
- `wishenka/wishlists/service.py` — `get_wishlist_by_public_token`.
  The invite token is a different capability from `public_token`.

Covered by:

- `tests/test_wishlists_htmx_sharing.py`
  `test_public_share_view_guest_sees_reservations_and_items`
  (titles, and the invite secret is absent)
- `tests/test_wish_items_tma_ui.py`
  `test_guest_and_anonymous_access_denied_to_item_ui`
- `tests/test_reservations_cabinet_ui.py`
  `test_anonymous_gets_neither`
- `tests/test_wishlist_roles_lifecycle.py`
  `test_public_token_provides_read_and_gifter_access_without_exposing_invite`
- `tests/test_wishlist_api.py`
  `test_sharing_is_private_revocable_and_persists_after_restart`
  (a stranger cannot open the private list; the public link can)

Gap for these assertions: none.

### A2. Remainder on the share page, no booking control

Accepted product behavior. An unidentified opener of the share page
sees the free remainder and does not see a booking control. The public
list answer omits the free remainder (S7). A recipient exit omits the
gifter, the reservation, the booked quantity, and the free remainder.

Modules:

- `wishenka/web/routes/sharing.py` — `view_public_share` sets
  `viewer_identified` from the optional session.
- `wishenka/web/templates/partials/item_card.html` — prints
  `available_quantity` for a non-recipient item. The booking form is
  rendered when `can_promise` is true. `can_promise` is
  `viewer_identified` and an active list.
- `wishenka/wishlists/service.py` — an unidentified caller is not the
  recipient, so `project_wish_item` returns
  `WishItemGifterViewDTO`, which carries `available_quantity`.

Covered by:

- `tests/test_wish_card_giver_controls.py`
  `test_anonymous_share_shows_availability_without_a_book_control`

That test is the proof of the remainder and the missing booking
control. `tests/test_wishlists_htmx_sharing.py`
`test_public_share_view_guest_sees_reservations_and_items` asserts
titles and that the invite secret is absent. It stays on A1 for those
assertions.

Gap: none.

### A3. No unnamed promise

A promise attempt without a session is rejected and stores nothing.
Opening the list by the share link, with the visitor unidentified,
creates no account.

Modules:

- `wishenka/web/routes/reservations.py` — create and mutation routes
  depend on `get_current_user`.
- `wishenka/users/store.py` and `wishenka/web/routes/auth.py` — a user
  row is written on Telegram authentication, not on a public read.
- `wishenka/web/routes/sharing.py` — `view_public_share`
  (`GET /share/{public_token}`) does not insert a user.

Covered by:

- `tests/test_reservation_actions_api.py`
  `test_unauthenticated_create_is_rejected`
- `tests/test_reservation_actions_api.py`
  `test_unauthenticated_mutation_is_rejected`
- `tests/test_surprise_role_context.py`
  `test_share_link_visit_creates_no_account`
  (unidentified `GET /share/{public_token}`; the `users` count is
  unchanged; the log has no `user_created` event)

Gap: none. `tests/test_auth_user_store.py`
`test_guest_request_does_not_create_user` hits `GET /healthz`, so that
request does not close this row. The promise refusals above do not
close the visit. The share-visit test does. That response shows the
free remainder (`Доступно:`) and does not show `Забронировать`. Row A2
stays on
`tests/test_wish_card_giver_controls.py`
`test_anonymous_share_shows_availability_without_a_book_control`.

### A4. Two public exits for one link

The difference is accepted product behavior. An unidentified opener of
the share page sees the free remainder and does not see a booking
control (A2). The public list answer omits the free remainder (S7). A
recipient exit omits the gifter, the reservation, the booked quantity,
and the free remainder. Each exit has its own test.

Modules:

- Share page: `wishenka/web/routes/sharing.py` and
  `partials/item_card.html` (A2).
- Public list answer: `wishenka/web/routes/wishlists.py`
  `projection(..., public=True)` (S7).

Covered by:

- `tests/test_wish_card_giver_controls.py`
  `test_anonymous_share_shows_availability_without_a_book_control`
  (share page shows the free remainder and no booking control)
- `tests/test_wishlist_api.py`
  `test_anonymous_public_view_hides_existing_reservation`
- `tests/test_wishlist_api.py`
  `test_public_api_shows_persisted_wish_without_reservation_details`
- `tests/test_wishlist_management_ui.py`
  `test_anonymous_public_display_ignores_stale_session_and_hides_reservation`
  (public list answer omits the free remainder, including with a stale
  session)
- `tests/test_wish_card_giver_controls.py`
  `test_personal_owner_display_name_hides_giver_facts`
  (recipient card omits the free remainder and booking sentences)
- `tests/test_wishlists_htmx_sharing.py`
  `test_public_share_view_owner_surprise_invariant`
  (recipient share page omits the gifter's name and a booking sentence)

Gap: none. The rule is decided.

### A5. Recipient using the same link

When the identified opener is the recipient, family 1 applies on that
page.

Module: `wishenka/web/routes/sharing.py` — `view_public_share`.

Covered by S3 (`test_public_share_view_owner_surprise_invariant` in
`tests/test_wishlists_htmx_sharing.py`).

Gap: none beyond S3.

### A6. Replaced or unknown link

After the owner replaces the share link, the old link does not open the
list and the new link does.

Modules:

- `wishenka/wishlists/service.py` — `regenerate_public_token`.
- `wishenka/web/routes/wishlists.py` — share reset route
  `POST /api/wishlists/{wishlist_id}/share/reset`.
- `wishenka/web/routes/sharing.py` — unknown token is a 404.

Covered by:

- `tests/test_wishlist_api.py`
  `test_sharing_is_private_revocable_and_persists_after_restart`
- `tests/test_wishlist_roles_lifecycle.py`
  `test_token_regeneration_invalidates_old_tokens`

Gap: none.

### A7. The link stays out of access logs

A log of a public open does not print the share token.

Modules:

- `wishenka/web/app.py` — `ShareTokenAccessFilter`,
  `RequestLoggingMiddleware`.
- `wishenka/web/routes/sharing.py` — shared-view log fields are
  wishlist id and role flags.
- `wishenka/web/routes/wishlists.py` — public-view log fields are
  wishlist id.

Covered by:

- `tests/test_wishlist_api.py`
  `test_server_access_log_filter_redacts_public_token`
- `tests/test_wishlist_api.py`
  `test_management_authorization_lifecycle_and_log_redaction`
- `tests/test_wishlists_htmx_observability.py`
  `test_share_token_access_filter_redaction`

Gap: none.
