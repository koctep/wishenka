# WISHENKA-37: Technical Debt Analysis

## Shortcuts Taken

The deliverable is the checklist in `doc/dev/verification-matrix.md`.
It records coverage and gaps. This task adds no product code, no route,
and no test. The service does not read the matrix.

WISHENKA-38 owns the end-to-end surprise checks. WISHENKA-39 owns race
and load. That split is the accepted scope of this checklist.

## Code Quality Issues

No Python file changed, so the service has no rename, split, or leftover
from this task.

The matrix already says which named tests do not assert a row. Those
notes match the tests:

- S5 leaves
  `test_warning_logging_on_access_denial_and_surprise_invariant`,
  `test_item_observability_privacy_invariants_no_tokens_or_auth_data`,
  and `test_wish_transaction_logs_storage_rollback_without_row_dump`
  off the covered list. The first asserts warning event names. The
  second asserts capability tokens and the session secret stay out of
  item CRUD logs. The third asserts the storage-failure log omits the
  row dump and the tokens.
- R1 leaves `test_atomic_reservation_allocation_and_rollback` off the
  covered list. That test rolls one failed allocation back to
  `available_quantity` 2 and no reservation row.

The remaining covered-by names assert the row they are attached to.
That includes the S4 remainder line
(`test_own_line_and_availability_show_together`), the A2 share page
(`test_anonymous_share_shows_availability_without_a_book_control`),
the A3 note that `test_guest_request_does_not_create_user` calls
`GET /healthz`, and the S7 note that
`test_anonymous_public_display_ignores_stale_session_and_hides_reservation`
calls `GET /api/public/wishlists/{token}`. No false citation turned up.
`doc/dev/verification-matrix.md` stays as it is.

## Missing Tests

This task added no test. A missing pytest timeout is out of scope for
that reason.

The checks that are still open are already on the matrix and already
owned:

- WISHENKA-38: the S5 combined recipient answer and log, S6, S8, and
  the A3 share-link visit that creates no account.
- WISHENKA-39: R5, race and load.

Those gaps stay on those two stories.

## Performance Concerns

This task adds no request path and no load profile. R5 remains the
load gap owned by WISHENKA-39. There is no new performance follow-up.

## Follow-up Tasks

There is no new follow-up. The only open work is already owned by
WISHENKA-38 and WISHENKA-39.

- WISHENKA-38 owns the end-to-end surprise checks: the S5 combined
  answer-and-log walk, S6 notifications, S8, and the A3 share-link
  visit that creates no account.
- WISHENKA-39 owns R5, the race and load suite.

Those keys are existing stories. This file leaves them there.
