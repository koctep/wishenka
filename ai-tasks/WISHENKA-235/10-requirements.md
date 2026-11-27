# WISHENKA-235: Anonymous public share shows availability without a book control

## Goals

Friends coordinate gifts so the same units are not bought twice, and the
person the gift is for still meets it as a surprise. A public share is how
someone who is not signed in opens a list. That visitor needs the same
shared availability line other non-recipients see, so they can tell whether
units are still free. They are not the recipient, and they are not yet a
giver who may take units.

Booking still requires a Telegram identity. Opening the public link needs
no extra profile form. It does not create an anonymous promise. The book
control stays hidden until the visitor is identified.

Today the public share shows that visitor the recipient's silent card. The
free remainder is missing. Hiding the book control is right. Hiding
availability is not. This task restores the availability line on the public
share and keeps the book control absent. It was found while WISHENKA-140
was in progress. The standing check has failed since base commit `b338710`.

Implementation language: Python.

## User Stories

Roles follow the product: owner, co-author, giver, and recipient. An
anonymous visitor is a person who opened the public share and is not signed
in. On a personal list the owner is the recipient of every wish.

- As an anonymous visitor of a public share, I want the wish-card summary
  to show how many units are still free, so that I can see whether the gift
  is still available without learning who holds the rest.
- As an anonymous visitor, I do not want a book control, so that I cannot
  take units before I am identified in Telegram.
- As the recipient of a wish, including the owner of a personal list, I
  still want no availability line and no book control, so that the surprise
  stays intact.
- As an identified giver who is not the recipient, I still want the
  availability line and, when units are free and I hold no promise, the
  book control, so that I can promise units from the card.

## Definition of Done

The task is done when all of the following hold.

1. An anonymous visitor opens the public share of a personal list, in
   Russian, for a wish that asks for 2 units, with none taken and none
   received. The wish-card summary shows «Доступно: 2 из 2». The same
   summary does not show «Забронировать».
2. That visitor is not the recipient. A card that stays silent the way the
   recipient's card stays silent does not meet this task, because the
   availability line is missing.
3. The availability line is the shared one already used for other
   non-recipients. While units are free it is «Доступно: X из Y», where X
   is the free remainder and Y is the requested quantity. When nothing is
   free it is «Забронировано». In both cases the anonymous summary has no
   book control.
4. The anonymous summary does not name a holder, does not show
   «Забронировано вами», and does not show a purchase mark. The visitor
   still does not see the gifted section, how many units were already
   received, or a public "already given" mark.
5. The recipient of the wish, including the owner of that personal list,
   still sees neither the availability line nor a book control.
6. An identified giver who is not the recipient still sees the availability
   line. When units are free and that giver holds no promise, the book
   control is still offered.
7. The standing check
   `test_anonymous_share_shows_availability_without_a_book_control` passes.
   Its failure today is that the summary is missing «Доступно: 2 из 2».

## Task Description

### Problem

The product already states two facts that must hold together on a public
share.

- A non-recipient sees the free remainder, for example «Доступно: 3 из 5»,
  or «Забронировано» when nothing is free. Other people do not learn who
  holds the rest.
- An unidentified visitor may read that line and may not book. A promise
  requires a Telegram identity. No separate profile form is required once
  the person is identified.

The public share currently presents the unidentified visitor as if they
were the recipient. The recipient's card correctly omits availability and
the book control. Applied to an anonymous visitor, that silence removes
«Доступно: 2 из 2» from a wish that still has both units free. The book
control is also absent, which matches the rule, but only because the whole
availability block is gone.

The standing check opens that public share with no session, reads the
wish-card summary, and requires «Доступно: 2 из 2» and the absence of
«Забронировать». It fails on the missing availability line.

### Functional requirements

1. On a public share, an anonymous visitor sees the shared availability
   line on each wish they are not the recipient of. For a wish asking for
   2 units with nothing taken and nothing received, the Russian summary
   reads «Доступно: 2 из 2».
2. That same summary does not offer a book control. The Russian label of
   that control is «Забронировать». The visitor is not offered a quantity
   choice, a change, a cancel, or a purchase mark.
3. When the free remainder is zero, the anonymous summary reads
   «Забронировано» and still has no book control.
4. The line states the remainder against the requested quantity. It does
   not name holders and does not reveal purchase status.
5. The recipient's card is unchanged: no availability line and no book
   control. On a personal list the owner is that recipient for every wish.
6. An identified non-recipient keeps the availability line and the book
   control under the rules already in force for givers.

### Non-functional requirements

1. The Russian and English labels already used for availability and for the
   book control stay the labels. This task does not add copy. The standing
   check reads the Russian public share.
2. The recipient still cannot infer a promise, a holder, or a purchase from
   the public share.
3. Reading the public share does not create a promise and does not require
   a profile form.

### Constraints and assumptions

- "Open by link without registration" means no extra profile form. It does
  not mean an anonymous promise. The book control appears only after the
  visitor is identified.
- This task restores the anonymous public-share summary. It does not change
  who may record receipt, who may edit the list, or how an identified giver
  books, changes, cancels, or marks a promise bought.
- The gifted section, received counts, and public "already given" marks
  stay hidden from anonymous visitors and from givers, as the product
  already requires.
- The suspected cause, that a missing viewer is folded into the recipient's
  view and the free remainder is omitted, is a lead for later design. The
  acceptance criterion is the visitor outcome above, not that lead by
  itself. Restoring the remainder by also showing «Забронировать» to an
  anonymous visitor would fail the criterion.

### Main entities

- **Public share.** The list opened by its public link. An anonymous
  visitor has no Telegram identity on that visit.
- **Wish.** A gift request. A non-recipient may see the free remainder
  against the requested quantity, or that nothing is free. A recipient may
  not see that line.
- **Availability line.** «Доступно: X из Y» while units are free, and
  «Забронировано» when none are free. It does not name a holder.
- **Book control.** The action «Забронировать», offered only to an
  identified giver who is not the recipient, when units are free and that
  giver holds no promise.
- **Recipient.** The person the gift is for. On a personal list, the owner
  of every wish. Their card stays silent about availability and booking.

## Q&A

- **Why does the ticket mention a projection that treats a missing viewer
  as the recipient?** That is a suspected cause, found with the failing
  check during WISHENKA-140. The business rule does not depend on it. An
  anonymous visitor of a public share is not the recipient. They see
  availability so they can coordinate, and they do not see a book control
  because they cannot promise units anonymously. Showing the recipient's
  silent card hides availability. Showing a book control would let an
  unidentified visitor take units.
- **Does instant access without registration include booking?** No. Opening
  the public link needs no extra profile. Booking still requires a Telegram
  identity. The card shows the remainder either way and offers
  «Забронировать» only after identification.
- **Which check records the criterion?** The existing check
  `test_anonymous_share_shows_availability_without_a_book_control` in
  `tests/test_wish_card_giver_controls.py`. It already fails because the
  summary is missing «Доступно: 2 из 2». The same summary must not contain
  «Забронировать».
