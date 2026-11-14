# WISHENKA-22: Gift Receipt Specification (Partial and Full Receipt, Booking Sync)

Programming language for implementation: Markdown for this specification
story (documentation only). Python 3.12+ for WISHENKA-23 and WISHENKA-24.

## Goals

An owner receives gifts in real life. Today the product has no finished
story for that moment. The product concept promises a life cycle of
active, booked, purchased, received, archived. It promises that the owner
can close a wish fully or by part of its quantity, that givers hear about
it, and that received gifts live apart from wishes the owner deleted. The
detail is still open. `in-docs/spec.md` leaves the exact reconciliation of
received and booked quantity «to implementation», and lists it as an open
question.

This is a specification story. It fixes the scenarios and corner cases in
business terms, so that WISHENKA-23 (backend rules and archive) and
WISHENKA-24 (receipt screen and «Подаренные» section) build the same
behavior without guessing. It does not design data, interfaces, or screens.

The business value:

- The owner keeps an honest list. What arrived leaves the active wishes,
  and what is still wanted stays.
- Givers do not buy a gift that is no longer needed. They learn that a gift
  arrived and decide for themselves about their own promise.
- The owner keeps a warm history of received gifts, and it is not mixed up
  with wishes the owner simply deleted.
- The surprise survives. Receipt never shows the owner who promised, how
  many, or whether it was bought.

Already built, and not changed here: promise create, change, and cancel
(WISHENKA-18, WISHENKA-57), giver controls on the wish card
(WISHENKA-19), and the giver cabinet «Мои бронирования» (WISHENKA-20).

Already built, and changed here for wishes with received units: the safe
archive. Today the safe archive flags the whole wish as archived and
keeps its promises, and restoring returns the whole wish to the active
list. For a wish with received units this story changes that: archive and
restore act on the unreceived part only (FR-3.8, FR-5.2, corner cases 10
and 11). For a wish with no received units the safe archive stays as it
is. The giver cabinet and the wish card for givers also change for fully
received wishes (FR-3.6).

## Scope

In scope: the business rules and scenarios for

- recording full or partial receipt of a wish;
- the effect of receipt on promises that are open at that moment;
- the notice to givers that a gift arrived;
- the separation of «Подаренные» from the archive of deleted wishes.

Out of scope:

- Any schema, interface, screen layout, or notification text wording
  beyond what is stated below. Architecture is Step 2, and the build is
  WISHENKA-23 and WISHENKA-24.
- Undoing or correcting a receipt (see Q&A, Q9).
- Money, shared purchase, and thanking givers. The product excludes them.
- Changes to the lifecycle of the list itself (archive and delete of a
  whole list).

## Main Business Entities

- **Wish**: an item on a list, with a requested quantity. A wish with no
  stated quantity means one unit.
- **Received quantity**: the number of units of a wish the owner has marked
  as received so far. It only grows, and it never exceeds the requested
  quantity.
- **Remaining quantity**: requested quantity minus received quantity. It is
  what the owner still wants.
- **Promise**: a giver's booking of some units of a wish. It is open while
  it is intended or purchased, and closed when cancelled. A promise is not
  tied to a particular received unit.
- **Occupied quantity**: the sum of units in open promises on the wish.
- **Receipt record**: one act of the owner saying «I received N units of
  this wish». A wish can have several, over time. A record carries the
  wish, the quantity, and the date. It does not carry any giver.
- **Gifted wish** (shown in «Подаренные»): a wish with received quantity
  above zero. It is shown with the received quantity and when it was
  received.
- **Archived wish**: a wish the owner deleted. It is shown in the archive.

Roles follow the product: owner, co-author, gifter, recipient. «Author»
below means the owner and, on a collaborative list, a co-author with the
right to edit wishes.

## User Stories

- As an owner, I want to mark that I received a gift, choosing how many
  units arrived, so that my list shows what I still want.
- As an owner of a wish for five units who got two, I want the other three
  to stay on my active list, so that people can keep giving the rest.
- As an owner, I want a fully received wish to leave my active list and
  appear in «Подаренные», so that my list is not cluttered with things I
  already have.
- As an owner, I want «Подаренные» to be separate from my archive of
  deleted wishes, so that a gift I got is never mistaken for a wish I
  dropped, and a deleted wish is never mistaken for a gift.
- As a gifter holding an open promise on a wish, I want to be told when
  the owner received some of it, so that I do not buy something that is no
  longer needed.
- As a gifter, I want to decide myself what to do with my promise after
  receipt, so that the product does not cancel or change it behind my back.
- As a gifter, I want my cabinet to keep showing my promise until I act, so
  that I do not lose track of what I promised.
- As another gifter, I want the remaining free quantity to reflect what the
  owner already received, so that I do not book a gift that has arrived.
- As a recipient, I want receipt to reveal nothing about promises, givers,
  or purchases, so that the surprise stays intact.

## Functional Requirements

### FR-1. Who may record receipt, and when

- FR-1.1. Only an author of the list may record receipt. A gifter or an
  anonymous viewer may not.
- FR-1.2. Receipt may be recorded only for a wish that is active, on a list
  that is active. A wish in the archive, a wish on an archived or deleted
  list, and a wish with no remaining quantity are all refused with a clear
  business reason.
- FR-1.3. The owner chooses the quantity received in this act. It is at
  least one and at most the remaining quantity.
- FR-1.4. Receipt does not need a giver to exist. An owner may record a
  gift that nobody promised, for example one that came from someone outside
  the product.
- FR-1.5. The act is instant, with no confirmation by givers. The owner
  never says who gave the gift.

### FR-2. Partial and full receipt

- FR-2.1. Each act adds to the received quantity. Several acts over time
  are normal: two units now, one next week.
- FR-2.2. After a partial act the wish stays active with the reduced
  remaining quantity. It is shown on the active list with what is still
  wanted, and its received part appears in «Подаренные».
- FR-2.3. After the act that brings received quantity up to the requested
  quantity, the wish is fully received. It leaves the active list and is
  shown only in «Подаренные».
- FR-2.4. A fully received wish takes no new promises. A partly received
  wish takes new promises only up to the free quantity: requested, minus
  received, minus occupied, never below zero.
- FR-2.5. Two authors recording receipt at the same time must not push the
  received quantity past the requested quantity. The later act is
  refused with a reason the author can read, and is never silently accepted
  beyond the limit.
- FR-2.6. The owner may reduce the requested quantity of a wish, but never
  below received plus occupied. This already holds, and receipt must keep
  it true. The refusal of a reduction is a known exception to the surprise
  rules (FR-6.1 and the surprise bullet of the non-functional
  requirements): the existing edit form already shows a locked quantity
  (received plus units occupied by promises), so it tells the owner that
  some units are occupied (see Q12).

### FR-3. Effect on open promises

- FR-3.1. Receipt never closes, cancels, changes, or marks purchased any
  promise by itself. Only the promise's giver does that, with the controls
  they already have.
- FR-3.2. A giver's open promise stays open and stays in the giver's
  cabinet and in the active count until the giver acts. This is true when
  the wish is partly received, when it is fully received, and when it
  later leaves the active list.
- FR-3.3. Receipt may leave the sum of received and occupied units above
  the requested quantity. This state is allowed. The product does not
  choose whose promise to drop. It says only that the total cannot be
  honoured, and it leaves the choice to the givers.
- FR-3.4. While in that state, no new promise is possible on the wish, and
  no giver may raise an existing promise. A giver may still lower, cancel,
  or mark purchased their promise. A cancelled promise cannot be reopened.
  To give again, the giver creates a new promise under FR-2.4, and only
  when the free quantity covers it.
- FR-3.5. A purchased promise is treated like an intended one for receipt.
  Receipt does not end it. The giver who bought may keep it for reference or
  cancel it, and the product does not judge.
- FR-3.6. On a fully received wish, an open promise remains visible to its
  giver in the cabinet with a clear marker that the gift was received. The
  giver may cancel it, lower it, or, for an intended promise, mark it
  purchased, as FR-3.4 allows. The giver may not change it upward or book
  more. This changes today's behavior: now the cabinet offers promise
  actions only for an archived wish on an active list, and the wish card
  shows giver controls only for active wishes. After this story, a giver
  of a fully received wish gets the cabinet actions and the marker, and
  the wish card shows no giver controls for it. A purchased promise kept
  after full receipt has no «completed» state. The giver can only cancel
  it, lower it, or undo the purchase, and the marker stays until the giver
  cancels. The exact wording and layout are for WISHENKA-24.
- FR-3.7. Cancelling or lowering a promise frees units for new promises
  only as far as the free quantity of FR-2.4 becomes above zero. In the
  over-booked state, the first cancellations only reduce the excess and free
  nothing.
- FR-3.8. Archiving a partly received wish moves only its unreceived part
  to the archive. Its received part stays in «Подаренные» and is not
  affected. Restoring it brings back its remaining quantity as an active
  wish, and the received part stays where it was. Open promises on that
  wish are kept, as today, and are not closed by archiving. Givers see
  them in the cabinet with «Желание в архиве» and the same four actions as
  for any archived wish. Such a promise still counts in the occupied
  quantity. A fully received wish has no unreceived part, so there is
  nothing left to archive: archiving is not offered for it, and the wish
  stays in «Подаренные».

### FR-4. Notifying givers

- FR-4.1. After each successful receipt act, every giver who holds an open
  promise (intended or purchased) on that wish gets one notice, in the
  Telegram bot, through the user's notification settings.
- FR-4.2. The notice says that the owner marked this wish as received
  (fully or in part). It names the wish and the list. It does not state
  how many units were received or requested. It invites the giver to
  review their promise.
- FR-4.3. The notice must not name other givers, must not give the total
  booked, must not give received or requested quantity (a giver could
  derive from them how much others booked), and must not say whether the
  giver's own promise is now excess. It must not hint at purchases made by
  others. The giver already sees their own promise and the free quantity
  of the wish, and decides from that.
- FR-4.4. A giver whose promise is closed (cancelled) gets nothing. A
  person who holds no promise gets nothing. The owner and the recipient
  get no booking notice as a recipient. An owner who holds a promise of
  their own on another wish gets notices as any giver (corner case 18).
- FR-4.5. A giver holding several open promises on the same wish gets one
  notice for that act, and not one per promise.
- FR-4.6. A giver who has switched off this kind of notice is not messaged.
  A list-level setting overrides the general one, as for other notices.
- FR-4.7. Failing to deliver a notice, for example because the giver blocked
  the bot, never fails or delays the receipt. The receipt stands.
- FR-4.8. Several acts in a row give several notices, one per act. The
  product does not merge them.

### FR-5. «Подаренные» and the archive are separate

- FR-5.1. «Подаренные» holds wishes with received quantity above zero. It
  records what the owner received. It is not a trash can and it is not the
  archive.
- FR-5.2. The archive holds wishes the owner deleted. A wish with received
  quantity above zero is never put into the archive as a whole. Its
  received part is always in «Подаренные» (see FR-3.8).
- FR-5.3. The two sections are shown apart, and a wish never shows in
  both as the same unit. A partly received wish may appear in three places:
  the active list (the remaining part), «Подаренные» (the received part),
  and, after deletion, the archive (the unreceived part).
- FR-5.4. Moving a wish into «Подаренные» keeps its description, link,
  price, and recipient. It adds the received quantity and the dates of the
  receipt acts. It never adds giver names or promise information.
- FR-5.5. «Подаренные» is shown to authors of the list. It is not open to
  gifters, and it is never a way to learn about promises. Whether a gifter
  may see the gifted history of a list is left open (Q6).
- FR-5.6. «Подаренные» is read-only. A received wish cannot be edited,
  moved, or promised from there. A reopen action is out of scope (Q9).
- FR-5.7. «Подаренные» stays visible and readable when the list is
  archived. Deleting a list removes its gifted history together with the
  list.

### FR-6. Surprise and privacy

- FR-6.1. Recording receipt shows the owner and any recipient only what
  they gave: the wish and the quantity received. It never shows whether the
  wish was booked, by how many, or whether any promise was bought.
- FR-6.2. A refused receipt (for example, quantity above the remaining)
  never states, or implies, how many units are booked.
- FR-6.3. The receipt screen and «Подаренные» are the owner's view and use
  recipient-safe data only. The recipient of a wish learns nothing of its
  bookings from either one.
- FR-6.4. Notices to givers follow FR-4.3 and show nothing about the owner
  beyond the fact of receipt.

## Corner Cases

| # | Situation | Required behavior |
| - | --------- | ----------------- |
| 1 | Wish for 5 units, 2 received, 3 left, no promises | Wish stays active with 3 remaining, 2 in «Подаренные» |
| 2 | Wish for 5, 3 promised by A and 2 by B, owner receives 2 | A and B both get a notice, both promises stay open. Received plus occupied is 7, above 5, so the over-booked state of FR-3.3 applies and no one can book or raise |
| 3 | Wish for 5, 5 promised by A, owner receives 3 | Received plus occupied is 8, above 5. A gets a notice and keeps the promise, no one can book, A decides |
| 4 | Wish for 1, promised by A and purchased, owner receives it | A gets a notice, wish is fully received and leaves the active list, A's promise stays visible to A with the «received» marker, until A cancels |
| 5 | Owner receives a unit nobody promised, while a giver holds a promise on other units | The giver gets a notice, because they hold an open promise on that wish |
| 6 | Owner tries to record more than remaining | Refused, with a message that names only the remaining quantity |
| 7 | Owner tries to record zero or a negative number | Refused |
| 8 | Two authors record receipt at once | Together they must not pass the requested quantity, the later act is refused with a readable reason |
| 9 | Wish is archived, or its list is archived or deleted | Receipt refused with a business reason |
| 10 | Wish with received units is archived | Received part stays in «Подаренные», the rest goes to the archive |
| 11 | Archived wish with received units is restored | Remaining quantity returns to the active list, received part stays in «Подаренные» |
| 12 | Owner lowers requested quantity of a partly received wish | Allowed only down to received plus occupied. The refusal may show that units are locked, as the existing edit form does today (Q12) |
| 13 | Giver cancels the promise after the notice | Promise closes, giver leaves the notice recipients for later acts, free quantity follows FR-2.4 |
| 14 | Giver holds two open promises on the received wish | One notice for the act, both promises stay |
| 15 | Giver has switched off the notice, or blocked the bot | No notice, or a failed notice, and the receipt still stands |
| 16 | Wish has no quantity stated | Treated as one unit, so a receipt of one fully receives it |
| 17 | Recipient of a wish views the list after receipt | Sees only the received quantity, nothing about promises |
| 18 | The owner is also a giver of another wish on a collaborative list | The owner's own promises behave as any giver's, and the owner gets notices as a giver for wishes where the owner is not the recipient |
| 19 | Same wish received in several acts | Each act is a separate record with its own date, and the totals add up |

## Definition of Done

This is a specification story, so done means the behavior is written down
clearly enough that the next two stories can proceed without product
questions.

1. The scenarios for full and partial receipt are described, including
   several acts on one wish and a wish with several givers.
2. The effect of receipt on open promises is fixed: receipt never closes a
   promise, the giver decides, the over-booked state is allowed and
   explained, and what each side sees in that state is stated.
3. The giver notice is specified: who gets it, when, what it says, what it
   must not say, and what happens when it cannot be delivered.
4. The separation of «Подаренные» and the archive is specified, including
   a partly received wish that is later archived and restored.
5. The surprise rules for the owner, the recipient, and the givers are
   stated for each artifact (the receipt act, «Подаренные», the notice).
6. Corner cases are listed with the expected behavior.
7. The open points that the story could not close are listed in Q&A with
   the assumption taken for now.
8. The split of work between WISHENKA-23 and WISHENKA-24 is stated.
9. No schema, interface, or screen design is present.

## Non-functional Requirements and Constraints

- Language: Markdown for this story. Python 3.12+ for WISHENKA-23 and
  WISHENKA-24.
- Surprise and privacy: receipt, «Подаренные», notices, and refusals never
  reveal promises, givers, quantities booked, or purchases (FR-6, FR-4.3).
  The one known exception is the existing edit form (Q12).
- Consistency: concurrent receipt acts never push the received quantity past
  the requested quantity (FR-2.5).
- Delivery: a failed notice never fails or delays the receipt (FR-4.7).
- Scope limits: no shared purchase, no money, no secret gift outside the
  list, and no undo of a receipt in this story.

## Task Description

Today the product already counts received units as part of the quantity
of a wish and already limits what can be booked after receipt. It does not
say what should happen to the promises of givers, who is told, what the
owner sees afterwards, or how gifted wishes differ from deleted ones.

The central decision is that receipt and promise are separate facts.
Receipt is the owner's statement about the real world. A promise is the
giver's statement about what the giver intends. The product does not
reconcile them on the giver's behalf, because it cannot know whether a
given gift came from that giver. It makes the owner's act cheap, tells the
givers, and leaves each giver's promise to the giver. This matches the
product statement that givers are told and «самостоятельно завершают или
отменяют свои брони».

Constraints:

- The surprise principle and the privacy rules of the product stay in
  force (`specs/00-high.md`, invariants 1 and 4).
- The limit on booked units stays: booked units never exceed what the owner
  asked for (invariant 3). Receipt is the one case where occupied plus
  received can pass the requested quantity, and only because the product
  does not cancel promises for the giver.
- There is no shared purchase, no money, and no secret gift outside the
  list.
- A failed delivery of a notice never fails or delays the receipt.

### Split of work

The split below is derived from the titles of the Jira stories WISHENKA-23
and WISHENKA-24 and is to be confirmed with the product owner.

- **WISHENKA-23, backend business logic and archive.** Rules FR-1 to FR-3,
  FR-4 (who is notified and when, delivery failure handling), the
  separation of the gifted and archived sets from FR-5, FR-6, and the
  corner cases.
- **WISHENKA-24, frontend screen and «Подаренные» section.** The owner
  screen to choose the received quantity (FR-1.3), the view of the active
  list and of the received part, the «Подаренные» section (FR-5), the
  giver cabinet marker for a received wish (FR-3.6), and the readable
  refusals.

### Assumptions

- A. The product keeps promise and receipt as independent facts, and no
  promise is ever closed by receipt.
- B. Authors with the right to edit wishes may record receipt, as the
  existing owner rules do. On a personal list that is the owner.
- C. The receipt act is final within this story.
- D. «Подаренные» is for authors, and not for gifters.

## Q&A

- Q1. Should receipt cancel promises automatically, at least when the wish is
  fully received?
  A. No. The product cannot tell which giver's gift arrived. The giver is
  notified and decides, as the concept in `in-docs/spec.md` section 7.3
  says. Clearing promises on the giver's behalf could also hide a purchase
  the giver already made.
- Q2. What if received plus promised units exceed the request?
  A. This is allowed (FR-3.3). No new promise is possible, no one may raise
  a promise, and the givers decide. The state ends when givers cancel or
  lower promises, or the owner raises the requested quantity.
- Q3. Does the owner see who gave the gift?
  A. No. A receipt record carries no giver, and the owner's view is
  recipient-safe.
- Q4. Who is notified, and about what?
  A. Each giver with an open promise on that wish, once per act, with the
  wish and the list, and the fact of receipt (FR-4). No quantities are
  given. Nothing is said about others' promises.
- Q5. Why not tell each giver whether their promise is now excess?
  A. It would reveal how much others booked. For the same reason the notice
  carries no received or requested quantity: with the free quantity and the
  giver's own promise, a giver could derive the total booked by others.
  Every giver can see the free quantity of the wish and their own promise,
  and decides from that.
- Q6. May gifters see «Подаренные» of a list they view?
  A. Not in this story (assumption D). The product statement speaks of the
  owner's history. If product later wants a public «already gifted» label,
  it needs its own decision and surprise review. Open for the product
  owner.
- Q7. Is a wish both in «Подаренные» and the archive?
  A. Not as the same unit. A wish with received units is never archived as
  a whole (FR-5.2). Its unreceived part can be archived, and its received
  part stays in «Подаренные».
- Q8. What happens to the gifted history when a list is deleted?
  A. It goes with the list (FR-5.7). Open for the product owner if long-term
  history of deleted lists is wanted.
- Q9. Can the owner undo or correct a receipt by mistake?
  A. Out of scope here, because `in-docs/spec.md` does not describe it. It is
  an obvious follow-up. Until then the act is final (assumption C), and the
  receipt screen should make the quantity choice explicit. Open for the
  product owner.
- Q10. Should the notice go to a giver who already purchased?
  A. Yes. That giver most needs to know before the gift is wrapped for an
  owner who already has it (FR-3.5).
- Q11. May a co-author record receipt on a collaborative list when they are
  the recipient of that wish?
  A. Assumption B says authors may. The open question about co-authors who
  are also recipients remains in `in-docs/spec.md` section 16 and is not
  closed here. Receipt shows recipient-safe data only, so it does not
  open a leak.
- Q12. Does refusing a quantity reduction reveal how many units are
  occupied by promises?
  A. Yes, today. The existing edit form (`doc/dev/items.md`, section 10)
  shows a locked quantity equal to reserved plus received units and a
  warning, so the owner can learn that something is booked. This is
  a known exception to the surprise rules, not created by this story. Its
  tightening is open for the product owner. This story only requires that
  the receipt act itself and its refusals reveal nothing (FR-6.2).

Sources used: `specs/00-high.md` (sections 4.2, 4.4, 6), `in-docs/spec.md`
(sections 5.5, 6, 7.2, 7.3, 9, 16), `doc/dev/items.md` and
`doc/dev/reservations.md` for the current quantity rules, and
`ai-tasks/WISHENKA-20/10-requirements.md` for style.
