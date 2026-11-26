# WISHENKA-323: One wishlist rule set for Mini App screens

## Goals

People manage wishlists in the Telegram Mini App: lists, wishes, membership,
archive, delete, restore, favorites, viewing history, invite join, sharing,
reservations, and gift receipts. Those actions follow product rules for who
may act, who is told about a shared change, how a public or invite link stays
unique, and what a viewer is allowed to see.

After the web data-access work (WISHENKA-80), the same wishlist action rules
are kept in two copies. Mini App screens can still prefer the second copy
instead of the product people already use. A later change can land in only
one copy. A check that follows the second copy then proves a different
product from the one people use. If a screen prefers that second copy, a
person can follow it too.

This task makes every duplicated wishlist action rule one set, and makes
every Mini App screen follow the product people already use. What a person
can do, what they are refused, what they see, and which share notices go out
stay the outcomes of that product. Reservation and receipt outcomes stay,
and a repeated reservation or receipt does not apply twice. Those outcomes
do not gain a second copy of the rules. The work is maintenance of one
product, not a new feature. Priority is medium. It is not a blocker for
other work.

Implementation language: Python.

## User Stories

- As an owner, administrator, giver, or recipient, I get the same permission,
  the same refusal, and the same surprise protection on every Mini App
  screen, so a second copy of the rules cannot change what I am allowed to
  do.
- As a person who shares a list or joins by invite, I still get a unique
  public link and a unique invite link, and a clash is handled the same way
  it is handled in the product people already use.
- As a member of a shared list, I still receive the same notices about list
  and wish changes, and a recipient is still left out of anything that would
  spoil a gift.
- As a viewer of a wishlist, I still see the same actions and the same hidden
  gift details I see in the product people already use.
- As an owner or member, creating and updating lists and wishes, membership,
  archive, delete, restore, favorites, viewing history, and joining by
  invite follow one set of rules on every Mini App screen. Screens do not
  prefer a second copy of those rules.
- As someone who keeps the product rules, I change any of those wishlist
  action rules in one place, so the Mini App cannot drift from a second copy.
- As someone who checks these flows, I still see the same person-facing
  outcomes. The checks prove those outcomes on the path a real Mini App
  request already uses, and they do not keep a second product path.
- As a giver or owner, a repeated reservation or a repeated receipt does not
  apply twice, and those outcomes do not gain a second copy of the rules.

## Definition of Done

The task is done when all of the following hold:

1. Every duplicated wishlist action rule is one set. That covers lists,
   wishes, membership, archive, delete, restore, favorites, viewing history,
   and invite join, including who may act, who is told, how a colliding link
   is handled, and what a viewer is shown. A Mini App screen does not apply a
   second copy of those rules.
2. Who is told about a shared change, and who is excluded so a gift stays a
   surprise, is decided by that same set. One action does not notify a
   different set of people because a second copy ran.
3. A new public link and a new invite link stay unique. When a new link
   clashes with one already in use, the attempt is repeated and then refused
   the same way it already is for a person using the Mini App. There is not
   a second clash policy.
4. What a viewer is shown for a wishlist — which actions are offered and
   which gift details stay hidden — comes from that same set and matches
   what the product people already use shows.
5. Every Mini App screen follows the product people already use and does not
   prefer a second copy of the wishlist rules. That includes lists, wishes,
   membership, archive, delete, restore, favorites, viewing history, invite
   join, sharing, gift receipts, and reservations.
6. Checks of these flows still prove the same person-facing outcomes. They
   do so on the path a real Mini App request already uses. They do not keep
   a second product path.
7. Reservations and gift receipts stay the outcomes the product already
   produces. A repeated reservation or a repeated receipt does not apply
   twice. Access refusals and surprise isolation stay as they are. Those
   outcomes do not gain a second copy of the rules.
8. History still lists the same entries in the same order. This task does
   not make that listing cheaper. A briefly busy save is not given a new
   retry rule here. Extra checks whose only point is link-clash retries or
   busy-save contention stay on their own follow-ups.

## Task Description

WISHENKA-80 left the same wishlist action rules in two copies so existing
checks would keep running. The copies cover lists, wishes, membership,
archive, delete, restore, favorites, viewing history, and invite join: who
may act, who hears about a shared change, how a colliding public or invite
link is handled, and what a viewer is shown. Each affected screen can still
prefer the second copy instead of the product people already use.

The parent record is WISHENKA-80 technical-debt item 1, filed as this Debt
issue (medium, label tech-debt, 8 story points). The business reason is a
single product. People must not get a different list, wish, membership,
archive, delete, restore, favorite, history, invite, permission, notice,
link, or view because a second copy handled the action. Maintainers must
not edit the same rule twice. Checks must prove the product people actually
use.

Where the two copies disagree on a rule that both the Mini App and bot
capture apply, the person-facing outcome a person already gets in the Mini
App stands. Bot capture follows that same outcome for that shared rule. It
does not keep a different result for the same rule. Outcomes that only bot
capture or another non-screen flow decides, and that the Mini App does not
also decide, stay as those flows already produce them. This task does not
redesign those flows beyond the shared rules. This task does not invent new
permissions, new notices, or new screens.

Reservation and receipt outcomes stay as the product already produces them.
A repeated reservation or a repeated receipt does not apply twice. This task
does not drop those outcomes and does not give them a second competing rule
set. It stops screens from preferring the second copy of the wishlist action
rules, and it stops those duplicated rules from living twice.

### Business entities

- **Owner:** creates the wishlist and holds full control of it.
- **Administrator:** a member allowed to manage the list and its wishes.
- **Giver:** a person who opens a shared list, reserves a wish, and can mark
  a purchase.
- **Recipient:** the person a gift is for. They do not see reservation or
  giver details.
- **Wishlist:** a personal or shared collection of wishes, with public and
  invite links, members, favorites, and viewing history.
- **Wish:** one wanted item, including quantity and gifted state.
- **Reservation:** a giver's claim on some quantity of a wish.
- **Gift receipt:** the owner's record that a wish was received, in full or
  in part.
- **Share notice:** the message that a shared list changed, sent only to
  people who are allowed to hear it.
- **Viewer presentation:** the actions and gift details a given person is
  allowed to see for one wishlist.

### Functional requirements

1. **One wishlist action rule set.** Lists, wishes, membership, archive,
   delete, restore, favorites, viewing history, and invite join are decided
   once and apply on every Mini App screen. Screens do not prefer a second
   copy. Who may act, who is told, how a colliding link is handled, and what
   a viewer is shown are parts of that same set, not a narrower set.
2. **One share-notice rule set.** The people told about a shared change, and
   the people left out to protect a surprise, are chosen once per action, as
   part of that set.
3. **One link rule.** Public links and invite links stay unique. A clash uses
   the retry-then-refuse outcome the product people already use, as part of
   that set. Invite join uses that same set.
4. **One viewer presentation.** The actions offered and the gift details
   hidden for a viewer match the product people already use, as part of that
   set.
5. **Screens follow the product people already use.** List, wish, membership,
   archive, delete, restore, favorites, viewing history, invite join,
   receipt, sharing, and reservation screens do not prefer a second copy of
   the rules.
6. **Checks prove the real request.** Existing checks keep the same
   person-facing results on the path a real Mini App request already uses.
   They do not keep a second product path.
7. **Reservation and receipt outcomes stay.** A repeated reservation or a
   repeated receipt does not apply twice. Those outcomes do not gain a
   second copy of the rules. Permissions, refusals, and surprise isolation
   match the product people already use. Russian and English behavior is
   unchanged.

### Non-functional requirements

- **Consistency:** two copies of the same wishlist action rule cannot
  disagree after this task, because those rules are maintained once.
- **Privacy:** the surprise principle in `specs/00-high.md` stays in force.
  Recipients still do not learn who reserved or bought a gift.
- **Compatibility:** Mini App inputs, outcomes, and error meanings stay as
  they are in the product people already use.
- **Operability:** log events people already rely on for these actions keep
  their current meaning. This task does not add a new user-visible signal.

## Constraints and assumptions

- The implementation language is Python, matching the existing service.
- `specs/00-high.md` and `in-docs/` remain the product authority. This task
  does not change those rules. It stops them from being applied twice.
- The behavior to preserve for Mini App screens is the product people
  already use. The second copy is not another source of truth.
- Where a shared wishlist rule disagrees between the two copies, the
  person-facing outcome a person already gets in the Mini App stands. Bot
  capture and other non-screen flows follow that outcome for that shared
  rule. They do not keep a different result for the same rule. Outcomes that
  only those flows decide, and that the Mini App does not also decide, stay
  as those flows already produce them. This task does not redesign those
  flows beyond the shared rules.
- Out of scope, already filed separately:
  - Cheaper history listing (WISHENKA-325).
  - How the receipt screen reaches the wishlist data it already shows
    (WISHENKA-324). That reach is separate from this task. This task owns
    receipt screens no longer preferring a second copy of the wishlist
    rules. WISHENKA-324 does not own that preference.
  - A new retry when a save is briefly busy (WISHENKA-326).
  - Extra checks aimed only at link-clash retries or busy-save contention
    (WISHENKA-327).
- Splitting large wishlist modules, and new product features, are out of
  scope.
- Reservation screens can prefer the second copy as well. They are in scope
  here, because every Mini App screen with that preference must stop using
  it. Reservation and receipt outcomes still must not gain a second copy of
  the rules.

## Q&A

- **Q: Why do this if people already use one product in the Mini App?**
  **A:** The wishlist action rules are still kept in two copies. A future
  edit, a check, or a screen that prefers the second copy can produce a
  different permission, notice, link, view, or other wishlist action result.
  One rule set removes that split. Screens follow the product people already
  use. A repeated reservation or receipt still does not apply twice.
- **Q: Does this change what owners, givers, or recipients can do?**
  **A:** No. The outcomes a person already gets in the Mini App stay,
  including surprise isolation. A repeated reservation or a repeated receipt
  does not apply twice.
- **Q: What if the two copies already disagree?**
  **A:** On a rule both the Mini App and bot capture apply, the
  person-facing outcome a person already gets in the Mini App stands. Bot
  capture follows that outcome for that rule and does not keep a different
  result. Outcomes that only bot capture or another non-screen flow decides
  stay as that flow already produces them. The second copy is not kept as an
  alternate product.
- **Q: Are the cheaper history listing, the receipt screen's reach to
  wishlist data, a retry when a save is briefly busy, and extra clash checks
  part of this task?**
  **A:** No. Those are WISHENKA-325, WISHENKA-324, WISHENKA-326, and
  WISHENKA-327. WISHENKA-324 is how the receipt screen reaches the wishlist
  data it already shows. It is not stopping screens from preferring a second
  copy of the rules. This task owns that preference, including on receipt
  screens, and does not own the receipt screen's reach.
- **Q: Do reservation and receipt outcomes go away, or gain a second set of
  rules?**
  **A:** No. Those outcomes stay, including that a repeat does not apply
  twice. They are not given a second competing rule set. Screens stop
  preferring a second copy of the duplicated wishlist action rules.
