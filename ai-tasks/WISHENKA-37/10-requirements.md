# WISHENKA-37: Verification matrix for product invariants

## Goals

Friends must not buy the same gift twice, and the recipient must still be
surprised. Those rules are already product invariants. Checks for them are
scattered across many test modules. A change can keep one exit quiet and
leak the surprise through another, or keep the free-remainder ceiling in one
example and miss a race.

This task gives a developer one checklist that answers which invariant is
checked where, and which check is still missing.

The deliverable is a document only. The matrix records coverage and gaps.
It does not implement the automated suites. WISHENKA-38 owns the end-to-end
surprise-invariant tests. WISHENKA-39 owns the race and load tests.

## User Stories

Roles follow the product: owner, co-author, gifter, and recipient. Recipient
is decided per wish.

- As a developer changing a wish, a promise, a share link, or a message, I
  want one checklist of the surprise rule, the free-remainder ceiling, and
  anonymous link access, so that I can see which exit already has a check.
- As a reviewer, I want each invariant tied to the exit that can break it
  (an answer, a notification, or a log), so that a pass on one exit is a
  pass on that exit alone.
- As a recipient, I want every exit I can receive to stay a surprise. A
  recipient exit omits the gifter, the reservation, the booked quantity,
  and the free remainder.
- As an unidentified opener of the share page, I want the free remainder
  without a booking control. An unidentified opener of the share page sees
  the free remainder and does not see a booking control.
- As a reader of the public list answer, I want that answer to omit the
  free remainder. The public list answer omits the free remainder.
- As a gifter with a share link, I want to open the list without a separate
  registration, and I want a race for the last units to leave a free
  remainder that is zero or positive.

## Definition of Done

The task is done when all of the following hold.

1. This file is the verification matrix. A developer can read a row and see
   the rule, the exit or scenario, the existing test, or the fact that no
   test exists, and the sibling story that owns a missing suite. Every gap
   names that owner. The gap that no test opens the share link and checks
   that the visit created no account names WISHENKA-38 (role-context
   end-to-end).
2. The matrix covers the three families in the story: surprise at every
   exit (answers, notifications, and logs), concurrent booking and the
   free-remainder ceiling, and anonymous giver access by share link.
3. The document states that the matrix records coverage and gaps and does
   not implement the WISHENKA-38 or WISHENKA-39 suites.
4. Promise actions, the wish card, the reservations cabinet, and the shared
   quantity outcome stay on WISHENKA-18, WISHENKA-19, WISHENKA-20, and
   WISHENKA-57. The matrix points at them.
5. The service language is Python 3.12+. This task adds no product code and
   no new tests.
6. Accepted product behavior: an unidentified opener of the share page sees
   the free remainder and does not see a booking control. The public list
   answer omits the free remainder. A recipient exit omits the gifter, the
   reservation, the booked quantity, and the free remainder.

## Task Description

### Problem

The high-level spec (section 6) and the functional spec (booking visibility,
notifications, and publication by link) already require three outcomes:

1. The recipient never learns about a booking or a purchase.
2. Opening a list by link does not require a separate registration.
3. Booked units stay within the quantity the owner requested. The ceiling
   in force is the free remainder from WISHENKA-57.

What this story adds is the map of those outcomes onto exits and scenarios,
including the exits that have no check yet.

### Programming language

Python 3.12+, the language of the wishlist service. The deliverable of this
task is a document. Later tests, if a sibling story adds them, use the same
language.

### What this task delivers

A verification matrix. It records coverage and gaps. It does not implement
those suites.

Sibling split:

- This task is the checklist: which invariant is checked where.
- WISHENKA-38 owns the end-to-end surprise-invariant tests.
- WISHENKA-39 owns the race and load tests.
- WISHENKA-18 already shipped the promise actions and recipient silence on
  those actions and on wish reads.
- WISHENKA-19 already shipped the wish-card giver controls.
- WISHENKA-20 already shipped the "My reservations" cabinet.
- WISHENKA-57 already shipped the shared quantity outcome, including when
  more than one copy of the service accepts bookings.

The matrix points at that shipped behavior. It does not describe those
features again as new work.

### How to read a row

Each row has an identifier, the rule for that exit or scenario, the tests
that already check it, and the gap. A gap names the sibling that owns the
suite. The gap that no test opens the share link and checks that the visit
created no account names WISHENKA-38 (role-context end-to-end). "Covered"
means the named test already asserts that row. It does not mean a later
end-to-end walk is unnecessary when the row says the walk is still open.

### Functional requirements: the matrix

#### Family 1. Surprise at every exit

Rule. A response the recipient of a wish can receive omits the gifter, the
reservation, the booked quantity, and the free remainder. It also omits
whether the gift has been bought. A log written while serving that
recipient does not name a gifter. A notification addressed to that
recipient does not reveal a booking or a purchase.

The recipient follows the wish. On a personal list the owner is the
recipient of every wish, including a wish that has only a display name. On
a collaborative list the recipient is the person that wish is for. The
same person can be a gifter of one wish and the recipient of another.

**S1. Recipient wish read.** The body of the wish list and of one wish,
when the caller is the recipient, includes the requested quantity and the
received quantity. It omits the gifter, the reservation, the booked
quantity, and the free remainder.

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

**S2. Recipient promise refusal.** A recipient who tries to promise their
own wish receives the same refusal when the wish is free and when it is
already promised. A recipient who tries to change, cancel, or mark a
promise receives the same answer as a missing promise. The answer omits
the gifter, the booked quantity, and the free remainder.

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

**S3. Recipient share page and wish card.** The page opened by the share
link, and the wish card on it, omit the gifter's name, a booking sentence,
and the free remainder when the viewer is the recipient.

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

**S4. Another gifter, and the cabinet.** A gifter sees the free remainder
and only their own promise. A refusal does not name the person who holds
the other units. The cabinet and a successful refresh list only the
caller's promises.

Covered by:

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

**S5. Logs.** A log written while the recipient views the wish does not
name a gifter. A log of a promise action on the client route does not
name a gifter. A refused recipient create is the same log when the wish
has a promise and when it does not. A refused recipient change carries
the path identifier and does not name a gifter.

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
- `tests/test_shared_inventory_multiprocess.py`
  `test_wish_transaction_logs_storage_rollback_without_row_dump`
- `tests/test_wishlist_roles_lifecycle.py`
  `test_reservation_audit_logging`
- `tests/test_wishlist_roles_lifecycle.py`
  `test_warning_logging_on_access_denial_and_surprise_invariant`
- `tests/test_wish_items_tma_ui.py`
  `test_tma_ui_observability_privacy_invariants`
- `tests/test_wish_items_crud_api.py`
  `test_item_observability_privacy_invariants_no_tokens_or_auth_data`

Gap: these checks are separate modules. No one scenario asserts the
recipient answer and the log of that same request together. That combined
check belongs to the WISHENKA-38 suite.

Operator records of a gifter's own booking may still identify that gifter
to operators. That stream is already checked by
`tests/test_reservation_observability.py`
`test_item_reserved_observability_event` and the sibling booking events in
the same module. Those records are an operator stream of the gifter's own
action. They are a recipient exit only if a recipient path emits them.
This matrix leaves that operator stream on the stories that shipped it.

**S6. Notifications to the recipient.** A message the service sends the
recipient about a wish, a receipt, an archive, or a reminder omits the
gifter, the reservation, the booked quantity, and the free remainder.

Covered by: none. There is no notification sender in the product code and
no test that inspects notification text.

Gap: WISHENKA-38 owns the end-to-end surprise checks, including this exit.
This task does not add a sender and does not write that suite. Any future
message to the recipient stays on this row.

**S7. Public list answer for an unidentified visitor.** The public list
answer omits the free remainder. It also omits the gifter, the reservation,
and the booked quantity when the visitor is not identified, including when
a stale session is sent. That omission is accepted product behavior. An
unidentified opener of the share page sees the free remainder and does not
see a booking control (A2). A recipient exit omits the gifter, the
reservation, the booked quantity, and the free remainder.

Covered by:

- `tests/test_wishlist_api.py`
  `test_anonymous_public_view_hides_existing_reservation`
- `tests/test_wishlist_api.py`
  `test_public_api_shows_persisted_wish_without_reservation_details`
- `tests/test_wishlist_management_ui.py`
  `test_anonymous_public_display_ignores_stale_session_and_hides_reservation`

Gap for this exit alone: none. The share page showing the free remainder
to an unidentified opener is accepted product behavior (A2).

**S8. One walk across exits.** For one booked wish, the recipient answer,
the recipient notification when a sender exists, and the log of that
recipient request satisfy S1, S5, and S6 together.

Covered by: no single test.

Gap: WISHENKA-38.

#### Family 2. Concurrent booking and the free-remainder ceiling

Rule, already in force. Pointed at here, shipped by WISHENKA-57 together
with the reservation limit in the product spec.

The free remainder is the requested quantity, minus units already received,
minus units occupied by intended and purchased promises. After a successful
new promise or a successful increase, that remainder is zero or positive.
A promise that would make it negative is refused and leaves the last
complete balance unchanged. A purchased promise still occupies its units.
A cancel or a decrease releases those units once. Recording receipt does
not close the promise. Two attempts to take the same last units end with
exactly one success for those units. The attempt that loses is told the
free remainder and is not told who won.

**R1. One copy, last units.** Two bookings of the same free units inside
one running copy leave a remainder that is zero or positive. Only one of
them takes those units. An increase past the remainder is refused.

Covered by:

- `tests/test_reservations_surprise_invariant.py`
  `test_concurrent_race_condition_prevented_by_coordinator`
- `tests/test_wishlists_sqlite_repo.py`
  `test_atomic_reservation_allocation_and_rollback`
- `tests/test_reservations_surprise_invariant.py`
  `test_update_reservation_quantity_rejects_insufficient_balance`
- `tests/test_reservation_actions_api.py`
  `test_shortage_names_the_free_remainder`

**R2. Several copies.** The shared quantity outcome from WISHENKA-57:
one success for the last units, a refused increase that keeps the earlier
promise, a release that returns units once, a lower requested quantity
that sees the other booking, receipt that is not capped by occupied
units, unrelated wishes that both succeed, and a busy wish that leaves
the last complete balance.

Covered by `tests/test_shared_inventory_multiprocess.py`:

- `test_last_free_units_one_success_across_processes`
- `test_increase_refused_leaves_earlier_promise`
- `test_cancel_releases_units_once`
- `test_smaller_quantity_releases_units_once`
- `test_lower_requested_quantity_sees_other_process_booking`
- `test_receipt_is_not_capped_by_occupied_units`
- `test_different_wishes_both_succeed`
- `test_one_store_keeps_self_booking_and_archive_rules`
- `test_locked_wish_raises_inventory_busy_and_leaves_balance`

**R3. Purchased units stay occupied.** A purchase keeps the units out of
the free remainder. A cancel returns them. The wish card still shows the
remainder after a shortage and does not present the refused attempt as a
saved booking.

Covered by:

- `tests/test_reservations_surprise_invariant.py`
  `test_purchased_reservation_retains_inventory_lock`
- `tests/test_reservations_surprise_invariant.py`
  `test_cancel_reservation_restocks_available_quantity`
- `tests/test_wish_card_giver_controls.py`
  `test_shortage_leaves_the_last_promise`
- `tests/test_wish_card_giver_controls.py`
  `test_busy_inventory_does_not_look_like_a_booking`

**R4. What the loser is told.** The visible remainder is the free
remainder after the successful attempt. It is zero or positive. The
sentence does not name the holder.

Covered by:

- `tests/test_reservation_actions_api.py`
  `test_shortage_names_the_free_remainder`
- `tests/test_wish_card_giver_controls.py`
  `test_shortage_leaves_the_last_promise`
- `tests/test_wish_card_giver_controls.py`
  `test_gifter_refusal_notice_names_no_holder`
- `tests/test_shared_inventory_multiprocess.py`
  `test_last_free_units_one_success_across_processes`

**R5. Race and load beyond R1–R4.** Repeated contention, many gifters, and
a load profile that keeps the same ceiling.

Covered by: none. No load suite is present. R1–R4 are the acceptance
examples already shipped with the features and with WISHENKA-57.

Gap: WISHENKA-39 owns the race and load tests. This matrix records the
gap and does not implement the suite.

#### Family 3. Anonymous giver access by share link

Rule. A person who has the share link can open the list in the Mini App
without a separate registration or onboarding. Viewing does not grant
editing. Promising still identifies a Telegram user, as WISHENKA-18
already requires: an unnamed visitor does not store a promise. The link
is the way in. It is not a second account form.

The invite secret stays off the public page. After the owner replaces the
share link, the old link stops opening the list.

**A1. Open by link with no session.** The share page shows the list title
and the wishes. It omits quick-add and edit controls. It omits the
reservations cabinet. The invite secret is absent.

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

**A2. Remainder on the share page, no booking control.** Accepted product
behavior. An unidentified opener of the share page sees the free remainder
and does not see a booking control. The public list answer omits the free
remainder (S7). A recipient exit omits the gifter, the reservation, the
booked quantity, and the free remainder.

Covered by:

- `tests/test_wish_card_giver_controls.py`
  `test_anonymous_share_shows_availability_without_a_book_control`

That test is the proof of the remainder and the missing booking control.
`tests/test_wishlists_htmx_sharing.py`
`test_public_share_view_guest_sees_reservations_and_items` asserts titles
and that the invite secret is absent. It stays on A1 for those assertions.

**A3. No unnamed promise.** A promise attempt without a session is
rejected and stores nothing.

Covered by:

- `tests/test_reservation_actions_api.py`
  `test_unauthenticated_create_is_rejected`
- `tests/test_reservation_actions_api.py`
  `test_unauthenticated_mutation_is_rejected`

Gap: no test opens the share link and checks that the visit created no
account. `tests/test_auth_user_store.py`
`test_guest_request_does_not_create_user` hits a health check, so it is
not this scenario. WISHENKA-38 owns this missing check (role-context
end-to-end). This task does not write that suite.

**A4. Two public exits for one link.** The difference is accepted product
behavior. An unidentified opener of the share page sees the free remainder
and does not see a booking control (A2). The public list answer omits the
free remainder (S7). A recipient exit omits the gifter, the reservation,
the booked quantity, and the free remainder. Each exit has its own test.

Gap: none. The rule is decided.

**A5. Recipient using the same link.** When the identified opener is the
recipient, family 1 applies on that page. Covered by S3
(`test_public_share_view_owner_surprise_invariant`).

**A6. Replaced or unknown link.** After the owner replaces the share
link, the old link does not open the list and the new link does.

Covered by:

- `tests/test_wishlist_api.py`
  `test_sharing_is_private_revocable_and_persists_after_restart`
- `tests/test_wishlist_roles_lifecycle.py`
  `test_token_regeneration_invalidates_old_tokens`

**A7. The link stays out of access logs.** A log of a public open does
not print the share token.

Covered by:

- `tests/test_wishlist_api.py`
  `test_server_access_log_filter_redacts_public_token`
- `tests/test_wishlist_api.py`
  `test_management_authorization_lifecycle_and_log_redaction`
- `tests/test_wishlists_htmx_observability.py`
  `test_share_token_access_filter_redaction`

### Non-functional requirements

1. A row is usable when it names the test, or states that no test exists.
   A bare "covered" without a name does not count.
2. This task adds no latency target and no load profile. Load belongs to
   WISHENKA-39 (R5).
3. The checklist is English and lives with the task artifacts so a later
   step can publish it without inventing new rules.

### Constraints and assumptions

- The deliverable is a document. Product code and new tests are out of
  this task.
- WISHENKA-38 and WISHENKA-39 implement the suites named in the gaps.
  This matrix is the list those suites can be checked against.
- The author's archive warning may acknowledge that a booking exists
  before an archive. The functional spec calls that a conscious exception
  for the author. It is an author prompt, not a recipient exit. This
  matrix does not extend that exception and does not remove it.
- A recipient who has no Telegram user, and what happens to promises when
  a profile is deleted, stay open product questions. This task does not
  close them.
- Payments, crowdfunding, and secret gifts outside the list stay outside
  the product.

### Main entities

- **Wish.** A gift request. A recipient exit may show the title, the
  requested quantity, and the received quantity. A recipient exit omits
  the gifter, the reservation, the booked quantity, and the free
  remainder. An unidentified opener of the share page sees the free
  remainder and does not see a booking control. The public list answer
  omits the free remainder.
- **Promise.** A gifter's claim on a positive number of units. Status is
  intended, purchased, or cancelled. The recipient is not shown the
  promise.
- **Share link.** The capability that opens one list without a separate
  registration. Replacing it retires the previous link. It is distinct
  from the invite used to join a collaborative list.
- **Exit.** An answer body, a notification, or a log that a person or an
  operator can receive. The surprise rule is per exit.
- **Free remainder.** Requested quantity minus received units minus units
  occupied by intended and purchased promises. Zero or positive after a
  successful promise change.

### Boundaries

In scope: the three-family checklist, the names of tests that already
cover a row, and the gaps owned by WISHENKA-38 and WISHENKA-39.

Out of scope: new product behavior, new tests, a notification sender, and
a second description of the promise API, the wish card, the cabinet, or
the shared quantity outcome.

## Q&A

- **Why a matrix rather than more tests in this story?** The business
  need is one place that shows which invariant is checked where. The
  end-to-end surprise suite is WISHENKA-38. The race and load suite is
  WISHENKA-39. This document records coverage and gaps and does not
  implement those suites.
- **Why list answers, notifications, and logs?** Those are the exits
  through which a recipient can learn the surprise. The functional spec
  already forbids booking facts in recipient notifications. The matrix
  checks that each exit has a named test or an explicit gap.
- **Why do some operator logs still identify the acting gifter?** A
  record of that gifter's own booking is an operator stream shipped with
  reservation observability. S5 checks recipient-path logs and client
  promise-route logs, which omit the gifter. The matrix does not reopen
  the operator stream.
- **Why do the share page and the public list answer differ on the free
  remainder?** The difference is accepted product behavior. An
  unidentified opener of the share page sees the free remainder and does
  not see a booking control. The public list answer omits the free
  remainder. A recipient exit omits the gifter, the reservation, the
  booked quantity, and the free remainder. A2, S7, and A4 record that
  decision.
- **What does "anonymous" mean?** A person who opens the share link
  without a session. They can read the list. Storing a promise still
  requires a Telegram user (WISHENKA-18). The link does not add a
  registration form.
- **Does this story re-specify booking, the card, the cabinet, or the
  shared quantity outcome?** It points at WISHENKA-18, WISHENKA-19,
  WISHENKA-20, and WISHENKA-57. Those stories already shipped that
  behavior.
