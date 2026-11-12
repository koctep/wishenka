# WISHENKA-19: Giver Booking Controls on the Wish Card

## Goals

Friends coordinate gifts so the same units are not bought twice, and the
person the gift is for still meets it as a surprise. On a personal list that
person is the owner of every wish. A gifter who is not the recipient must be
able to promise units from the wish card, choose how many when more than one
unit is free, see what remains, and change, cancel, or mark their own promise
as bought. The own line stays «Забронировано вами (N)» for the combined
occupying quantity. The word «Куплено» is added only when the latest
occupying promise is bought and it is the only occupying promise.

The quantity outcome is already in force (WISHENKA-57). The promise actions
are already available to a client (WISHENKA-18). This task does not replace
either one. It puts those actions on the wish card the gifter is already
looking at. The aggregated "My reservations" cabinet, and its home counter,
belong to WISHENKA-20.

## User Stories

Roles follow the product: owner, co-author, gifter, and recipient. On a
personal list the owner is the recipient of every wish and must not see
availability or giver controls on those wishes. On a collaborative list,
whether someone is the recipient is decided per wish. A display name alone
does not make someone the recipient.

- As a gifter who opened a friend's list, I want a booking action on the
  compact card and on the expanded card, so that I can promise units without
  leaving the list and without an extra confirmation.
- As a gifter, I want to choose how many units to promise when more than one
  unit is free, and I want that choice to stop at the free remainder, so that
  I cannot take units another friend can still buy.
- As a gifter, I want every non-recipient card to show «Доступно: X из Y»
  while units are free, and «Забронировано» when none are free, so that I can
  coordinate without learning who holds the rest.
- As a gifter who already promised this wish, I want the own line to be
  «Забронировано вами (N)», with N my combined occupying quantity, on the
  compact card and on the expanded card. I want to change the latest promise,
  cancel it, or mark it «Куплено» there, so that I manage the promise where I
  made it. The word «Куплено» is added only when the latest occupying promise
  is bought and it is the only occupying promise. When I hold more than one
  occupying promise and the latest is bought, the combined quantity is not
  labeled as bought.
- As a gifter who marked the latest promise bought by mistake, I want
  «Вернуть в бронь» to clear that mark without freeing the units, so that the
  promise stays mine. «Вернуть в бронь» acts on the latest promise. An earlier
  intended promise stays intended.
- As another gifter, I want the card to hide who holds the remaining units
  and whether those units were marked bought, so that the surprise is not
  passed along.
- As the owner of a personal list, I want no availability line and no giver
  controls on any wish of that list, so that I do not see booking facts on my
  own gifts. A display name on a wish does not offer me those controls.
- As the recipient of a wish, I want the card to show no booking action, no
  remainder, no «Забронировано», no own-booking controls, and no purchase
  mark, so that I cannot infer the surprise from the list.
- As a co-author of a collaborative list, I want giver controls on a wish
  meant for someone else, and none of those facts on a wish meant for me.
  Whether I am the recipient is decided per wish. A display name alone does
  not make me the recipient.

## Definition of Done

The task is done when all of the following hold.

1. An identified gifter who is not the recipient of an active wish can promise
   a positive whole number of units from that wish's card, while the list is
   not archived or deleted, the free remainder is at least 1, and the caller
   holds no occupying promise on that wish. An occupying promise is intended
   or purchased. A cancelled promise does not occupy units and does not block
   a new one. The promise is immediate. There is no extra confirmation. The
   list author does not have to approve it. No separate profile form is
   required. On a personal list the owner is the recipient of every wish and
   is not offered this action or the availability line. A display name on a
   wish does not change that and does not offer the owner giver controls on
   their own gifts.
2. That booking action is available while the card is collapsed and while it
   is expanded. Using it does not leave the list and does not toggle the card
   open or closed. Expanding the card does not change the meaning of the
   status and does not require a second, conflicting set of controls when the
   summary and the details are on screen together.
3. When more than one unit may be taken, the gifter chooses a whole number on
   that same card. A new promise starts at 1. The choice cannot exceed the
   free remainder and cannot be 0. When only one unit may be taken, the
   action promises that unit and does not ask for a count. Leaving the choice
   at 1 promises one unit.
4. A non-recipient sees «Доступно: X из Y» when the free remainder is at
   least 1, and «Забронировано» when the free remainder is 0. X is the free
   remainder and is never negative. Y is the wish's requested quantity. This
   line stays visible when the caller also holds a promise. It does not name
   another gifter and does not say that a promise was marked bought.
5. A gifter who holds an occupying promise sees the own line
   «Забронировано вами (N)» on that card, together with the availability line
   above. N is always the combined occupying quantity. They can cancel the
   latest promise and mark it «Куплено» while the card is collapsed and while
   it is expanded. They can change that promise when another legal size
   exists.
   The card does not offer a second new promise while an occupying promise
   remains. Cancel and the purchase mark are immediate and have no extra
   confirmation. The word «Куплено» on the own line follows item 7.
6. A quantity change applies to the latest promise only. The control shows
   that promise's current size, not a rewritten combined total. The gifter
   may set it to any positive whole number up to that size plus the free
   remainder. A lower size frees the released units. Lowering a purchased
   promise does not clear the purchase mark. Setting the size to 0 is not
   offered; cancel is how the promise is dropped. Applying the same size
   leaves the promise unchanged.
7. Marking the latest promise «Куплено» does not free units. The own line is
   always «Забронировано вами (N)», with N the combined occupying quantity.
   The word «Куплено» is added only when the latest occupying promise is
   bought and it is the only occupying promise. When the caller holds more
   than one occupying promise and the latest is bought, the combined quantity
   is not labeled as bought. Other gifters still see only the availability
   line. The holder can clear a mistaken «Куплено» mark. Clearing it returns
   that promise to an intended booking and does not free units. The control
   that clears the mark is labeled «Вернуть в бронь» and is shown only when
   the latest promise is bought. «Вернуть в бронь» still acts on the latest
   promise. An earlier intended promise stays intended. The «Куплено» action
   is shown only when the latest promise is intended.
8. When the caller holds more than one occupying promise, the own line is
   still «Забронировано вами (N)» with N the combined occupying quantity.
   That line does not add «Куплено», including when the latest occupying
   promise is bought and an earlier promise is also bought. «Вернуть в бронь»
   still acts on the latest promise. An earlier intended promise stays
   intended. Change, cancel, «Куплено», and «Вернуть в бронь» act on the
   latest promise. This task does not merge promises and does not list every
   promise on the card.
9. The recipient of the wish sees none of the availability line, the booking
   action, the quantity selector, the caller's own quantity, «Куплено»,
   «Вернуть в бронь», change, or cancel. On a personal list the owner is the
   recipient of every wish and must not see availability or giver controls on
   those wishes. On a collaborative list, whether someone is the recipient is
   decided per wish, and this silence applies only to wishes meant for the
   caller. The same person sees giver controls on a wish meant for someone
   else. A display name alone does not make someone the recipient, and does
   not offer the owner of a personal list giver controls on their own gifts.
10. A refusal leaves the last promise and the last balance. The gifter is told
    the attempt did not take the units. A shortage shows the current free
    remainder and does not name who holds the rest. A busy wish can be
    retried and consumes nothing. The recipient is not offered the actions
    and learns nothing that confirms a promise.
11. After a successful action the same card shows the new availability and
    the caller's own promise. The gifter stays on the list. One successful
    booking creates one promise; the booking action is then replaced by the
    own-promise controls. After a cancel that leaves the caller with no
    occupying promise, «Забронировать» returns when the free remainder is at
    least 1. That action creates a new promise. It does not resize the
    cancelled one.
12. Fully booked wishes stay in the list. Editor controls already on the card
    stay. This story does not change archive, delete, or receipt. The
    implementation language is Python 3.12+.

## Task Description

### Problem

Gifters can already promise, resize, cancel, mark bought, and undo that mark,
and a wish read already hides those facts from the recipient. The wish card
in the Mini App does not let the gifter do any of that. Without the controls
on the card, a friend looking at the list cannot claim a gift or correct
their own claim, which is the coordination the product exists to provide.

The ticket names buttons, a quantity selector, and the labels «Доступно: X из
Y» and «Забронировано». Those are the giver's job on the card. The promise
actions and the quantity rules are already delivered. This task does not add
a new way to store a promise and does not build the cabinet of all of a
gifter's promises.

### Programming language

Python 3.12+. The wish card is the server-rendered Mini App screen already in
this service. This story stays on that card.

### Already in the product

These behaviors exist and this task does not redefine them.

- A promise can be created, resized, cancelled, marked purchased, and
  returned from purchased to intended. Intended and purchased promises occupy
  their units. A cancelled promise does not. Marking purchased, or returning
  it to intended, does not free units. A quantity change applies only to an
  intended or purchased promise. A cancelled promise cannot be given a new
  size. Lowering a purchased promise frees the released units and does not
  clear the purchase mark.
- The free remainder is requested quantity minus received units minus
  occupied units, and it is never negative. A new or larger promise that
  would make it negative is refused and leaves the last complete balance.
  Recording receipt adds received units and does not close the promise.
  Those rules are WISHENKA-57.
- The client can already create a promise, change its quantity, cancel it,
  mark it purchased, and undo that mark. A recipient cannot create one.
  On a personal list the owner is the recipient of every wish. On a
  collaborative list, whether someone is the recipient is decided per wish.
  A display name alone does not make someone the recipient. Those rules and
  the actions are WISHENKA-18. This task uses them and does not redefine
  them.
- The wish card is the same card on the wishlist screen and on the list
  opened by a shared link. It has a compact summary and an expanded detail.
  The compact summary shows the photo or placeholder, title, price, and the
  existing badges. It shows no availability and no booking action.
- The expanded card, for a person who is not the recipient, shows exactly one
  status and hides the others. Nothing free shows «Забронировано», including
  when the caller holds the units. The caller holding units while some remain
  free shows «Забронировано вами (N)» and hides the availability line.
  Otherwise it shows «Доступно: X из Y», with X the free remainder and Y the
  requested quantity. The recipient's card shows none of these lines.
- Neither state offers a booking action, a quantity choice, change, cancel,
  or «Куплено».
- People who may edit the list still see edit, reorder, and archive on the
  expanded card. The archive section lists archived wishes as titles with
  restore for an editor. It is not this wish card.
- When a gifter holds more than one promise, the wish view already shows the
  combined quantity and the latest promise's status. An action result is the
  promise just changed. This task does not merge those promises, and it does
  not treat that latest status as a «Куплено» label on the combined quantity.
- On an archived or deleted list, a new promise and every change to an
  existing one are refused. On an archived wish whose list is still active, a
  new promise is refused, and change, cancel, purchase, and undo of an
  existing promise still succeed. Deleting a list cancels occupying promises.
  This task does not change that.

### Still required

- The giver can book, choose a legal count, and read the availability line
  from the compact card and from the expanded card.
- The giver who holds a promise can change the latest promise, cancel it,
  mark it «Куплено», and clear that mark, from both states of the same card.
- Availability and the caller's own promise are shown together. The current
  expanded card shows only one of them.
- The own line is always «Забронировано вами (N)», with N the combined
  occupying quantity. The word «Куплено» is added only when the latest
  occupying promise is bought and it is the only occupying promise. When the
  caller holds more than one occupying promise and the latest is bought, the
  combined quantity is not labeled as bought. «Вернуть в бронь» still acts
  on the latest promise. An earlier intended promise stays intended.
- The recipient of that wish still sees a card with no booking facts. On a
  personal list the owner is the recipient of every wish and sees no
  availability and no giver controls. On a collaborative list, whether
  someone is the recipient is decided per wish. A display name alone does
  not make someone the recipient, and does not offer the owner of a personal
  list giver controls on their own gifts.
- The card updates in place after each action. The list is not replaced by
  the "My reservations" cabinet.

### Functional requirements

1. The booking action label is «Забронировать». It is offered only to an
   identified gifter who is not the recipient, holds no occupying promise on
   that wish, and faces a free remainder of at least 1 on an active wish in
   an active list. An unidentified viewer sees the availability line the card
   already shows to a non-recipient and is not given a promise. On a personal
   list the owner is the recipient of every wish and is not offered this
   action or the availability line. A display name on a wish does not change
   that and does not offer the owner giver controls on their own gifts.
2. The quantity selector is on the card, next to the action that uses it. For
   a new promise it offers the whole numbers from 1 through the free
   remainder, and only when that remainder is greater than 1. For a change it
   offers the whole numbers from 1 through the latest promise's size plus the
   free remainder. «Изменить» is offered only when that upper bound is greater
   than 1, so a different legal size exists. A latest promise of 1 with
   nothing free has no «Изменить»; cancel and the purchase controls remain.
   The gifter applies a change with «Изменить».
3. The shared status uses the Russian copy already on the card and named in
   the product spec: «Доступно: X из Y» or «Забронировано». The caller's own
   line is always «Забронировано вами (N)», where N is the combined quantity
   of occupying promises. The word «Куплено» is added only when the latest
   occupying promise is bought and it is the only occupying promise. When the
   caller holds more than one occupying promise and the latest is bought, the
   combined quantity is not labeled as bought. «Вернуть в бронь» still acts
   on the latest promise. An earlier intended promise stays intended.
4. Giver controls do not depend on permission to edit the list. A guest who
   opened the shared link, and who is an identified non-recipient, gets them.
   A recipient who may edit the list keeps the editor controls and does not
   get giver controls. On a personal list the owner is the recipient of every
   wish and does not get giver controls or the availability line. On a
   collaborative list, whether someone is the recipient is decided per wish.
   A display name alone does not make someone the recipient.
5. Using a giver control keeps the gifter on the list and does not expand or
   collapse the card. After success, that card shows the new free remainder
   and the caller's own promise. Fully booked wishes remain in the list.
6. The cancel control is labeled «Отменить бронь». It frees that promise's
   units at once. Other gifters then see the larger remainder, or «Доступно»
   instead of «Забронировано» when the wish was fully taken. The cancelled
   promise is not given a new size from this card. If the caller holds no
   occupying promise afterward and the free remainder is at least 1,
   «Забронировать» is offered again and creates a new promise.
7. «Куплено» and «Вернуть в бронь» follow requirement 7 in the definition of
   done. The own line is always «Забронировано вами (N)», with N the combined
   occupying quantity. The word «Куплено» is added only when the latest
   occupying promise is bought and it is the only occupying promise. When the
   caller holds more than one occupying promise and the latest is bought, the
   combined quantity is not labeled as bought. «Вернуть в бронь» still acts
   on the latest promise. An earlier intended promise stays intended. Other
   gifters do not see either label. A purchased promise still reduces the
   free remainder.
8. On a personal list the owner is the recipient of every wish and must not
   see availability or giver controls on those wishes. On a collaborative
   list, whether someone is the recipient is decided per wish. Silence on a
   collaborative list applies only to wishes meant for the caller. The same
   person sees giver controls on a wish meant for someone else. A display
   name alone does not make someone the recipient, and does not offer the
   owner of a personal list giver controls on their own gifts. The recipient
   card omits booking facts in the content of the card, not by a switch the
   recipient can turn back on. This task does not identify a person named
   only by a display name.
9. This story does not change archive, delete, or receipt. Receipt does not
   remove the holder's controls and does not close the promise. The free
   remainder shrinks when units are received. This story does not add a
   receipt screen and does not add a separate label for "all received". The
   spec's word when nothing is free remains «Забронировано».
10. Promises whose wish card has left the active list are not managed here.
    The archive title row does not gain giver controls. Cancel after archive,
    when the card is gone, stays with the cabinet in WISHENKA-20. If an
    archived wish is still shown as this same card while the list is active,
    a new promise is not offered, and change, cancel, «Куплено», and
    «Вернуть в бронь» remain available.

### Non-functional requirements

1. Booking from the card stays as responsive as reading the list today. This
   task adds no new latency target.
2. A gifter receives a definite success or refusal on the card. A refusal
   caused by a busy wish can be retried and does not consume units.
3. The recipient's card contains no booking action, remainder, holder, or
   purchase mark. On a personal list that recipient is the owner, for every
   wish. Hiding those facts only from view, while leaving them in the card
   content, does not meet this requirement.
4. The quantity outcome and the surprise rule stay in force as further copies
   of the service are added. The card does not invent a second balance.

### Constraints and assumptions

- The booker is the Telegram user who opened the Mini App. "No registration"
  means no extra profile form. It does not mean an anonymous promise.
- Piece counts are positive whole numbers. The selector's ceiling is the
  free remainder for a new promise, and the latest promise's size plus the
  free remainder for a change.
- A gifter may already hold more than one promise. The own line is always
  «Забронировано вами (N)», with N the combined occupying quantity. The word
  «Куплено» is added only when the latest occupying promise is bought and it
  is the only occupying promise. The card acts on the latest promise.
  «Вернуть в бронь» still acts on the latest promise. An earlier intended
  promise stays intended. The card does not create another promise from
  «Забронировать» while any of the caller's promises still occupy units.
- On a personal list the owner is the recipient of every wish and must not
  see availability or giver controls on those wishes. On a collaborative
  list, whether someone is the recipient is decided per wish. A display name
  alone does not make someone the recipient.
- Labels on this card stay the Russian copy named above. Russian and English
  are both product languages, and the wish card is Russian today. This task
  does not add a translation catalog.
- The availability line uses the requested quantity as Y even when some units
  were already received. X already subtracts received units and occupied
  units.
- Sibling work stays on its own tickets:
  - WISHENKA-57 owns the shared quantity outcome. This task uses it.
  - WISHENKA-18 owns the client promise actions and recipient silence on
    those actions. This task uses them and does not add another action.
  - WISHENKA-20 owns the "My reservations" cabinet, the home counter, and
    management of promises that are no longer on an active wish card.
  - WISHENKA-15 owns the compact and expanded card, manual order, and
    archive. This task adds giver controls and does not replace that card.
- Also out of scope: notification text, payments, crowdfunding, secret gifts
  added by a gifter, a new promise store, and idempotent replay beyond the
  card rule that one successful booking shows own-promise controls instead of
  a second «Забронировать». Identifying a recipient who has no Telegram user
  stays an open product question.

### Main entities

- **Wish.** A gift request on a list. Attributes a recipient may see: title
  and the other wish details, requested quantity, and received quantity
  recorded by the list author. Attributes a non-recipient may see: the free
  remainder against the requested quantity, or the fact that nothing is free.
- **Promise.** A gifter's claim on a positive number of units of one wish.
  On the card the holder sees «Забронировано вами (N)», with N the combined
  occupying quantity. The word «Куплено» is added only when the latest
  occupying promise is bought and it is the only occupying promise. Only that
  holder sees change, cancel, «Куплено», and «Вернуть в бронь». «Вернуть в
  бронь» acts on the latest promise. An earlier intended promise stays
  intended.
- **Wish card.** The compact and expanded presentation of one wish on the
  list, including the list opened by a shared link. Giver controls live on
  this card. The recipient's card is the same presentation without those
  facts.
- **Caller and wish.** On a personal list the owner is the recipient of every
  wish and is not offered availability or giver controls. On a collaborative
  list the same person can be a recipient of one wish and a gifter of
  another. Silence and giver controls follow that wish. A display name alone
  does not make someone the recipient.

### Boundaries

In scope: giver controls and availability on the existing wish card, for an
identified non-recipient, including the shared-link list; in-place update of
that card; surprise silence on the recipient's card, including every wish
for the owner of a personal list.

Out of scope: a new promise action, a change to the quantity rules, the "My
reservations" cabinet and its home counter, notification text, receipt, and
editor archive or reorder behavior.

## Q&A

- **Why is this a screen if the actions already exist?** Friends coordinate
  on the list they opened. WISHENKA-18 made the actions available to a
  client. WISHENKA-57 already stops two gifters from taking the same units.
  Neither one puts a control on the wish card. That card is this task.
- **Why both the compact card and the expanded card?** The product spec
  places the booking action on both. The compact card is what a gifter scans.
  A booking action there without the availability line would be a blind
  claim, so the status is on both states too. Own-promise controls are on
  both for the same reason: the gifter manages the promise where they made
  it. One visible set is enough when the summary and the details are on
  screen together.
- **Why is the current badge not enough?** The expanded card shows
  «Забронировано», «Забронировано вами (N)», or «Доступно: X из Y», and only
  one of them. A holder who took the last units loses the own-booking line.
  A holder who left units free loses the availability line. The spec wants
  other gifters to see the remainder, and the holder to see their own
  promise as well. This task shows both.
- **What do X and Y mean after a partial receipt?** Y stays the requested
  quantity, as in the spec example «Доступно: 3 из 5» and on the card today.
  X is the free remainder: requested, minus received, minus occupied, and
  never below 0. Receipt is not relabeled. When nothing is free, the line is
  «Забронировано», including when received units are part of why nothing is
  free.
- **Why is there no second «Забронировать» after the first promise?** The
  spec treats the gifter's claim as one booking managed by «Изменить» and
  «Отменить бронь». A second create from the card would look like a duplicate
  claim. If the service already holds more than one promise for this gifter,
  the own line is «Забронировано вами (N)», with N the combined occupying
  quantity, and the card acts on the latest promise. The word «Куплено» is
  not added in that case. The card does not merge the promises and does not
  list them. The cabinet is WISHENKA-20.
- **Why does the change control show the latest size, not the combined
  size?** The number the gifter edits is the size that promise will have
  after «Изменить». When they hold one promise, that size and the combined
  quantity are the same number. When they hold more than one, the own line
  stays «Забронировано вами (N)» with N the combined quantity and does not
  add «Куплено». The control shows the latest promise so a change does not
  pretend to resize every promise.
- **Who is the recipient on a personal list?** The owner, for every wish.
  They see no availability line and no giver controls. On a collaborative
  list, whether someone is the recipient is decided per wish. A display name
  alone does not make someone the recipient, and it does not offer the owner
  of a personal list giver controls on their own gifts.
- **When does the own line include «Куплено»?** The own line is always
  «Забронировано вами (N)», with N the combined occupying quantity. The word
  «Куплено» is added only when the latest occupying promise is bought and it
  is the only occupying promise. When the caller holds more than one
  occupying promise and the latest is bought, the combined quantity is not
  labeled as bought. «Вернуть в бронь» still acts on the latest promise. An
  earlier intended promise stays intended.
- **Why include «Вернуть в бронь»?** The ticket names «Куплено». The product
  already lets the gifter undo a mistaken mark without freeing units, and
  WISHENKA-18 kept that action for the client. This card is where the gifter
  manages the promise. Without the undo control, a mistaken «Куплено» cannot
  be corrected on the list. The spec names «Изменить», «Отменить бронь», and
  «Куплено». It does not name the undo label. «Вернуть в бронь» is the label
  for that existing action.
- **Why is cancel immediate?** The spec says booking and cancel happen at
  once, without an extra confirmation. «Куплено» and «Вернуть в бронь» follow
  that same immediate pattern. «Изменить» applies the number the gifter
  chose. It is not a dialog that asks whether to proceed, and it does not
  fire on every step of the selector.
- **What does another gifter learn from «Куплено»?** Nothing. Purchased units
  stay occupied, so the availability line shrinks or becomes
  «Забронировано». The words «Куплено» and «Вернуть в бронь» are only on the
  holder's card.
- **Where is "My reservations"?** WISHENKA-20. This task does not add the
  home counter, the grouped cabinet, or giver controls on the archive title
  row. A promise whose card has left the active list is managed there.
- **What remains for the sibling tickets?** WISHENKA-57 owns the free
  remainder. WISHENKA-18 owns the promise actions and silence on their
  answers. WISHENKA-19 owns the giver controls on the wish card. WISHENKA-20
  owns the cabinet. WISHENKA-15 owns the card's compact and expanded states,
  order, and archive. This task does not replace those results.
