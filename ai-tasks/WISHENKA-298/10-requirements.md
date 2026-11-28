# WISHENKA-298: Keep the anonymous share on the giver contract

## Goals

Friends coordinate gifts so the same units are not bought twice, and the
person the gift is for still meets it as a surprise. A public share is how
someone who is not signed in opens a list. That visitor needs the free
remainder, and must not be treated as the recipient.

On base commit `762922f` two standing checks failed. The anonymous share hid
the remainder, and a guest visit was recorded as if that guest were the
recipient. [WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235)
already settled the product: an anonymous share shows availability, and a
missing caller is not the recipient. Both checks pass on the current tree.

This debt keeps that giver and anonymous contract. The two checks stay
green. Restoring the old silent recipient card would hide the remainder
again and would call a guest the recipient. That outcome is rejected.

Implementation language: Python.

## User Stories

Roles follow the product: owner, co-author, giver, and recipient. An
anonymous visitor opened the public share and is not signed in. On a
personal list the owner is the recipient of every wish.

- As an anonymous visitor of a public share, I want the wish card to show
  that units are still free, so that I can see whether the gift is still
  available without learning who holds the rest.
- As an anonymous visitor, I do not want a book control, and I do not want
  a visit to create an account, so that I can read the list without
  promising units or becoming a user.
- As the owner of a personal list, I want a visit I make myself recorded as
  the recipient, so that my surprise protection still applies to me.
- As an identified giver who is not the owner, I want my visit recorded as
  not the recipient, so that I keep the giver view of that personal list.
- As someone who holds the secret link, I want a visit record that does not
  repeat that link, so that the record cannot be reused to open the list.

## Definition of Done

The task is done when the current giver and anonymous contract still holds
and both standing checks pass. No new product behavior is required. The
checks already passed together in 0.92s on this tree.

1. An unidentified visitor opens the Russian public share of a personal
   list that asks for 2 units, with none taken. The page shows the
   availability line («Доступно:») and does not offer «Забронировать». The
   visit adds no account.
2. The same unidentified visit is recorded as not the recipient. The list
   is recorded as a personal list, not a group list. The secret link does
   not appear in that record.
3. When the owner of that personal list opens the same share, the visit is
   recorded as the recipient, and still as a personal list, without the
   secret link in the record.
4. When another signed-in person who is not the owner opens the same share,
   the visit is recorded as not the recipient, and still as a personal
   list, without the secret link in the record.
5. These two checks stay green:
   `test_share_link_visit_creates_no_account` and
   `test_wishlist_shared_view_observability`.
6. The WISHENKA-235 contract is unchanged. An anonymous visitor is not
   folded back into the recipient's silent card.

## Task Description

### Problem

The product already states two facts that must hold together on a public
share.

- A non-recipient sees the free remainder, for example «Доступно: 3 из 5»,
  or «Забронировано» when nothing is free. Other people do not learn who
  holds the rest. An anonymous visitor is that kind of reader.
- An unidentified visitor may read that line and may not book. Opening the
  link creates no account and no promise. The book control stays hidden
  until the visitor is identified.

On base `762922f` the anonymous share showed quantity only and omitted
«Доступно:». The guest visit was recorded with the recipient flag set. That
pair treated a missing caller as the recipient and hid the remainder.

WISHENKA-235 restored the availability line for the anonymous visitor and
stopped treating a missing caller as the recipient. The two checks that
caught the old pair now pass. This task locks that result. It does not
reopen the question of whether the checks or the product were wrong.

### Functional requirements

1. An anonymous visitor of a personal list's public share sees the shared
   availability line and does not see a book control. For a wish that asks
   for 2 units with nothing taken, the Russian page includes «Доступно:»
   and does not include «Забронировать».
2. That visit creates no account and no promise.
3. A visit record for a personal list says whether the visitor is the
   recipient. An unidentified visitor is not the recipient. The owner is
   the recipient. Another signed-in person who is not the owner is not the
   recipient. The record also says the list is not a group list.
4. The visit record does not repeat the secret link.
5. The recipient's own card stays silent about availability and booking.
   On a personal list the owner is that recipient. This task does not take
   that silence away from the owner.

### Non-functional requirements

1. The Russian labels already used for availability and for the book
   control stay the labels. This task does not add copy.
2. Reading the public share does not create an account, a promise, or a
   profile form.
3. The secret link stays out of the visit record for the guest, the owner,
   and the other signed-in giver.

### Constraints and assumptions

- The accepted contract is the one WISHENKA-235 put in place. This task
  does not revert it. Hiding the remainder from an anonymous visitor, or
  recording a missing caller as the recipient, fails the task.
- The two named checks are the proof. They already pass. Changing them so
  they again expect a silent recipient card would fail the task.
- Recording receipt stays with the list's authors. A giver and an anonymous
  visitor do not mark receipt. This task does not add a receipt action on
  the shared page.
- These debts stay out of scope: WISHENKA-356 (a separate anonymous public
  view check), WISHENKA-357 (app startup from one import path), and
  WISHENKA-311 (browser checks that fail only under parallel load).
- The gifted section, received counts, and public "already given" marks
  stay hidden from anonymous visitors and from givers, as the product
  already requires.

### Main entities

- **Public share.** The list opened by its secret link. An anonymous
  visitor has no identity on that visit.
- **Wish.** A gift request. A non-recipient may see the free remainder. A
  recipient may not see that line.
- **Availability line.** The shared remainder line, «Доступно:» while units
  are free. It does not name a holder.
- **Book control.** The action «Забронировать», offered only to an
  identified giver who is not the recipient, when units are free and that
  giver holds no promise.
- **Recipient.** The person the gift is for. On a personal list, the owner
  of every wish. A missing caller is not the recipient.
- **Visit record.** The note that someone opened the share: which list,
  whether the visitor is the recipient, and whether the list is a group
  list. It does not carry the secret link.

## Q&A

- **Why did the ticket ask whether the checks were stale or the product
  had regressed?** On `762922f` the anonymous share hid «Доступно:» and the
  guest visit was recorded as the recipient. WISHENKA-235 answered that
  question. An anonymous visitor is not the recipient. They see
  availability so they can coordinate, and they do not see a book control
  because they cannot promise units anonymously. Both checks now pass.
  This task keeps that answer.
- **Does "stay green" mean rewrite the checks?** No. The checks already
  describe the contract: no new account, the remainder is visible, booking
  is absent, a guest is not the recipient, the owner of a personal list is
  the recipient, and the secret link is absent from the visit record.
- **Does instant access include booking or an account?** No. Opening the
  public link needs no extra profile and creates no account. Booking still
  requires a Telegram identity.
- **Are the other open debts part of this task?** No. WISHENKA-356,
  WISHENKA-357, and WISHENKA-311 stay where they are. Receipt on the shared
  page stays out of this task as well.
