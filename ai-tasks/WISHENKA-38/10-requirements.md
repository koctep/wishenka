# WISHENKA-38: End-to-end surprise and role-context tests

## Goals

The recipient of a wish must stay surprised, and a share link must not
become a second way to create an account.

A recipient response, in its body and its headers, omits the gifter,
the reservation, the booked quantity, the free remainder, and whether
the gift has been bought. The response may still include the requested
quantity and the received quantity. One walk judges the response and
the log of that same request so the log cannot hide the gifter. The
log of that request does not name the gifter. Nothing the service sends
the recipient may reveal a booking.

Separate checks already cover many exits one at a time. What is still
open is one walk that judges the recipient response and the log of that
same request together, proof that no recipient-facing notification is
produced, and proof that opening the list by the share link creates no
account.

This task adds those automated checks. The deliverable is tests of
behavior the product already has.

## User Stories

Roles follow the product: owner, recipient, gifter, and an unidentified
opener of a share link. On a personal list the owner is the recipient
of every wish, including a wish that has only a display name.

- As a recipient who owns a personal list, I want one walk of a booked
  wish to judge my response and the log of that same request together,
  so the log cannot hide the gifter. The response omits the gifter, the
  reservation, the booked quantity, the free remainder, and whether the
  gift has been bought. That omission covers the body and the headers.
  The response may still include the requested quantity and the
  received quantity. The log of that request does not name the gifter.
- As that recipient, I want proof that the service produces no message
  to me about the wish, so a booking cannot reach me through a notice.
- As an unidentified opener of a share link, I want the visit to create
  no account, so reading the list is not registration. An unidentified
  opener sees the free remainder and no booking control. This opener is
  outside the recipient rule. Row A2 stays on its existing check.
- As an operator, I want the audit of a gifter's own booking to be
  allowed to name that gifter. A recipient-facing log must not.

## Definition of Done

The task is done when all of the following hold.

1. Automated tests close these open rows of
   `doc/dev/verification-matrix.md`: S5, S6, S8, and A3.
2. S5. One scenario asserts the recipient response and the log of that
   same request together. The response omits the gifter, the
   reservation, the booked quantity, the free remainder, and whether
   the gift has been bought. That omission covers the body and the
   headers. The response may still include the requested quantity and
   the received quantity. The log of that request does not name the
   gifter.
3. S6. That recipient activity produces no recipient-facing
   notification. The product has no notification sender. The check
   proves none is produced. A sender, a push channel, and notification
   copy stay out of this task.
4. S8. One walk of one booked wish on a personal list asserts the
   recipient response, the log of that recipient request, and the
   absence of a recipient-facing notification together. The caller is
   the owner, and that owner is the recipient of the wish.
5. A3. Opening the list by the share link, with the visitor
   unidentified, creates no account. The health check is a different
   request and does not close this row.
6. The suite judges an unidentified share-page opener by the accepted
   share-page rule: they see the free remainder and no booking control.
   That opener is outside the recipient rule. Matrix row A2 stays on
   its existing check.
7. The operator audit of a gifter's own booking may contain the gifter
   identity. The suite leaves that stream allowed. A recipient-facing
   log of the recipient request must not name the gifter.
8. Race and load tests stay on WISHENKA-39 (matrix row R5).
9. The tests are Python 3.12+. Each check finishes within a bound
   chosen for that check.
10. Product behavior stays as it is. Per-exit checks the matrix already
    marks covered stay in place.

One walk may close S5, S6, and S8 when it asserts all three for the
same recipient request. A3 is a separate visit.

## Task Description

### Problem

The surprise rule and the split between recipient and gifter are
product invariants (high-level spec, section 6; functional spec,
booking visibility and notifications). The verification matrix records
which exit already has a check.

Four gaps remain open and belong to this story:

- S5. Answer checks and log checks are separate. No one scenario
  asserts the recipient response and the log of that same request
  together.
- S6. No part of the product sends a message to the recipient, and no
  test shows that a recipient-facing notification is absent.
- S8. No single walk covers the recipient response, the notification
  outcome, and the log of that recipient request for one booked wish.
- A3. No test opens the share link and checks that the visit created
  no account.

### Programming language

Python 3.12+, the language of the wishlist service. The deliverable is
automated tests in that language.

### What this task delivers

Automated end-to-end checks that close matrix rows S5, S6, S8, and A3.
The checks prove the current surprise rule and the current share-link
visit. They leave the product behavior unchanged.

### Out of scope

- A notification sender, a push channel, reminder copy, and notification
  settings. The functional spec describes notices the product may send
  later. Until a sender exists, the proof for S6 is that no
  recipient-facing notification is produced.
- Race and load tests. WISHENKA-39 owns matrix row R5.
- A second proof of rows the matrix already marks covered: S1, S2, S3,
  S4, S7, A1, A2, A4, A5, A6, A7, R1, R2, R3, and R4.
- The author's archive warning. That prompt may say a booking exists.
  It is an author prompt, and it is outside the recipient exits in this
  walk.
- A new account created by the share-link visit, and a booking stored
  for an unidentified visitor. A promise with no session is already
  refused. This task adds the missing visit check (A3) only.

### Functional requirements

#### S5. Recipient response and its log

For one recipient request about a booked wish, one scenario asserts
both of the following.

The response, in its body and its headers, omits:

- the gifter
- the reservation
- the booked quantity
- the free remainder
- whether the gift has been bought

The response may include the requested quantity and the received
quantity.

The log written while serving that request does not name the gifter.

The caller is the owner of a personal list. On a personal list that
owner is the recipient of every wish, including a wish that has only a
display name.

#### S6. No recipient-facing notification

The product sends no message to the recipient. There is no push and no
other recipient notice for a wish, a receipt, an archive, or a
reminder.

The check proves that the recipient activity in the walk produces no
recipient-facing notification. The check passes on that absence.
Notification copy stays out of this task. A recipient-facing
notification produced during the walk fails the check.

A future sender, if a later story adds one, stays on matrix row S6.
This task leaves that sender unbuilt.

#### S8. One walk across exits

One walk uses one booked wish on a personal list. The caller is the
owner, and that owner is the recipient.

The walk asserts, for that one request:

- the recipient response meets the S5 response rule
- the log of that same request meets the S5 log rule
- no recipient-facing notification is produced (S6)

#### A3. Share-link visit creates no account

An unidentified person opens the list by the share link. The visit
creates no account.

The health check does not open the share link, so it leaves this row
open. The already-covered refusal of a promise with no session also
leaves this row open. The row closes when the share-link visit itself
creates no account.

During that visit the opener sees the free remainder and sees no
booking control. That display is accepted product behavior (matrix row
A2). The opener is outside the recipient rule. This task leaves A2 on
its existing check.

#### Operator audit

The audit of a gifter's own booking may name that gifter. That stream
stays allowed. A recipient-facing log of the recipient request must
not name the gifter.

### Non-functional requirements

1. Each check finishes within a bound chosen for that check. An
   unbounded wait is not a valid check.
2. The checks join the service's existing automated test run. This task
   adds no load profile and no latency target.
3. These requirements and the tests are in English.

### Constraints and assumptions

- Parent epic: WISHENKA-36. WISHENKA-37 published the verification
  matrix. WISHENKA-39 owns row R5.
- Operator audit of a gifter's own booking may contain the gifter
  identity. Those records become a recipient exit only when a recipient
  path emits them. This suite allows them on the gifter's own action.
- An unidentified opener of the share page sees the free remainder and
  no booking control. The public list answer omits the free remainder.
  Both facts stay as they are.
- A recipient who has no Telegram user, and what happens to promises
  when a profile is deleted, stay open product questions. This task
  leaves them open.
- Payments, crowdfunding, and secret gifts outside the list stay
  outside the product.

### Main entities

- **Wish.** A gift request on a list. On a personal list the owner is
  the recipient of every wish.
- **Reservation.** A gifter's booking of one or more units, including a
  purchased booking. Hidden from the recipient.
- **Free remainder.** Units still open for a gifter to book. A
  recipient response omits it. An unidentified share-page opener sees
  it.
- **Recipient response.** Body and headers of the recipient's request.
  It omits the gifter, the reservation, the booked quantity, the free
  remainder, and whether the gift has been bought. It may still include
  the requested quantity and the received quantity.
- **Recipient-facing log.** A log written while serving that recipient.
  It must not name the gifter.
- **Operator audit.** A record of a gifter's own booking. It may name
  that gifter.
- **Recipient-facing notification.** A message to the recipient about a
  wish, a receipt, an archive, or a reminder. None is produced.
- **Share link.** Opens one list. The visit creates no account.
- **Account.** A person identified through Telegram. Opening the share
  link does not create one.

### Boundaries

In scope: automated checks that close S5, S6, S8, and A3.

Out of scope: product features, a notification system, race and load
tests, and a second proof of rows the matrix already marks covered.

## Q&A

- **Why tests instead of a new feature?** The surprise rule and the
  role split already exist. The business need is proof that a recipient
  response, in its body and its headers, omits the gifter, the
  reservation, the booked quantity, the free remainder, and whether the
  gift has been bought. The requested quantity and the received
  quantity may remain. One walk judges the response and the log of that
  same request so the log cannot hide the gifter. The log of that
  request does not name the gifter. The gifter, the booking, and the
  booked quantity stay out of any notice, and a share-link visit creates
  no account.
- **Why prove that no notice is produced?** The product has no
  recipient notification sender. Requiring notice text would invent a
  channel the product does not have. S6 passes when the walk produces
  no recipient-facing notification.
- **Why may an operator record name the gifter?** That stream records
  the gifter's own booking for operators. A recipient-facing log must
  not name the gifter. The suite keeps the two streams apart.
- **Why is the free remainder on the share page allowed?** An
  unidentified opener is outside the recipient rule. They see the free
  remainder and no booking control. A recipient response still omits
  the free remainder.
- **Why does the health check leave A3 open?** A3 is the visit that
  opens the list by the share link and creates no account. The health
  check is a different request.
- **Why does R5 stay out of this story?** Repeated contention and load
  belong to WISHENKA-39. This story is the surprise walk and the
  share-link visit.
