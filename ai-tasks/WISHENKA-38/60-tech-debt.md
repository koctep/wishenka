# WISHENKA-38: Technical Debt Analysis

## Shortcuts Taken

No shortcut was taken. The deliverable is the two checks in
`tests/test_surprise_role_context.py`. Product behavior stays as it
is. No notification sender, push channel, or notice copy was added.

The module follows `ai-tasks/WISHENKA-38/20-architecture.md`. One
owner `GET /api/wishlists/{wishlist_id}/items/{item_id}` judges the
recipient body, the headers, the log of that request, and the absence
of a recipient-facing notice. A separate unidentified
`GET /share/{public_token}` judges that the visit creates no account.
The gifter booking audit stays outside the recipient log window.

`doc/dev/architecture.md` still names `user_notification_settings` and
`notification_outbox`. No module creates those tables. This task
proves a notice is not produced. It does not add the tables or a
worker. That sketch is existing documentation, not a crutch added
here.

## Code Quality Issues

No code-quality debt. Product modules were not changed. The new test
module has no unused imports, no commented-out code, and no debug
prints. Its longest line is 100 characters, the project limit. Step 5
recorded a clean `make analyze` run.

The leak scan and the notice scan are the checks the architecture
names: gifter identity, booking facts, and the words that would mark
a notification, an outbox enqueue, or a push. They are the proof this
task delivers, not a leftover to rewrite.

Test constants (`quantity` 8, received 1, booked 3, remainder 4, and
the test session secret) live only in that module. No product value
was hardcoded.

## Missing Tests

No missing test for this task. Both checks are present:

- `test_recipient_walk_hides_booking_in_response_log_and_notice`
  closes S5, S6, and S8 for one booked wish.
- `test_share_link_visit_creates_no_account` closes A3 and judges the
  unidentified opener by the accepted share-page rule.

The module timeout is present. Line 28 sets
`pytestmark = pytest.mark.timeout(30)`, so both tests carry an
explicit 30-second bound. There is no sleep and no poll. A missing
timeout is not debt here.

The log window is INFO and above, as the architecture specifies.
DEBUG lines on that read do not name the gifter. The suite does not
add a second proof of rows the matrix already marks covered.

`doc/dev/verification-matrix.md` still describes S5, S6, S8, and A3
as open. Pointing those rows at the new tests is Step 8 of this task.
It is not a missing test and not a follow-up.

Race and load coverage (matrix row R5) stays on WISHENKA-39. This
task does not add it.

Step 5 ran this module only. Both tests passed. No pre-existing
failure was observed, so there is no `NON-BLOCKER — pre-existing`
entry.

## Performance Concerns

No performance concern. Each check is one in-process call with a
30-second bound. This task adds no load profile and no latency
target. R5 remains the load gap, and WISHENKA-39 already owns it.
There is no new performance follow-up.

## Follow-up Tasks

There is no new follow-up.

The checks this task delivers are not follow-ups. Updating
`doc/dev/verification-matrix.md` so S5, S6, S8, and A3 name the new
tests is Step 8 of WISHENKA-38, not a later ticket. R5 stays on the
existing story WISHENKA-39.
