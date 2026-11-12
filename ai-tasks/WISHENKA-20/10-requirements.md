# WISHENKA-20: My Reservations Cabinet

## Goals

A gifter promises gifts on many lists. The home screen is where they return,
and today it does not tell them how many gifts they still hold or gather
those promises in one place. They need one card that shows the size of that
commitment, and one screen that lists only their own open promises, grouped
by wishlist, so they can get back to editing a promise or marking it bought.

The promise actions already exist (WISHENKA-18). The quantity rules already
exist (WISHENKA-57). The wish card already lets a gifter book, change,
cancel, and mark a promise bought (WISHENKA-19). This task is the caller's
own cabinet: the home counter and the grouped list, with a way to reach
edit and purchase. It is the place a gifter looks across lists. It is the
caller's record of their own promises.

The cabinet keeps the surprise. It shows only the caller's own promises. It
must not reveal who else promised a wish. A recipient must not learn
bookings of gifts meant for them from this screen. On a personal list the
owner is the recipient of every wish, so bookings of those wishes stay off
that owner's cabinet. An anonymous viewer has no cabinet.

## Active count

The home badge uses one rule, and every mention of the badge, the counter,
or the active count in this document means this rule.

The active count is the number of distinct wishes on which the caller holds
at least one occupying promise. An occupying promise is a promise that is
still intended or already marked purchased. Intended and purchased both
count. A cancelled promise does not count. Units do not count. Two or more
occupying promises on the same wish count as one wish.

A purchased promise stays in the count because it still holds the gift and
the gifter still has to keep, correct, or drop it. Marking a promise bought
does not end the booking. Recording receipt does not end it either. A wish
counts while any of the caller's promises on it remain intended or
purchased, including when the wish or its list is archived.

The cabinet lists each occupying promise. The badge counts wishes. When the
caller holds two occupying promises on one wish, the cabinet shows two
promises and the active count grows by one.

## User Stories

Roles follow the product: owner, co-author, gifter, and recipient. On a
personal list the owner is the recipient of every wish. On a collaborative
list, whether someone is the recipient is decided per wish. A display name
alone does not make someone the recipient.

- As a gifter, I want a home card «Мои бронирования» with the active count,
  so that I can see how many gifts I still hold before I open a list.
- As a gifter, I want that card to open a list of my own intended and
  purchased promises, grouped by wishlist, so that I can review every open
  promise without walking each list.
- As a gifter, I want the wishlist group header to show the wishlist title
  and, when the list has them, the event title and the event date, so that
  I can tell which list and which occasion I promised for.
- As a gifter, I want each promise to show the wish, my quantity on that
  promise, and whether it is still intended or already «Куплено», so that I
  know what I still have to buy.
- As a gifter, while giver controls are still on the wish card, I want a
  cabinet row to offer only «К желанию», so that the row opens that card.
  WISHENKA-19 edits the latest promise only. An earlier promise is listed,
  and it is not edited from the cabinet while the card still has giver
  controls. «Изменить», «Отменить бронь», «Куплено», and «Вернуть в
  бронь» appear in the cabinet only after those card controls are gone.
- As a gifter whose wish card no longer has giver controls, and whose list
  is still active, I want the cabinet to let me change, cancel, mark
  purchased, and «Вернуть в бронь» on that promise, so that an archived
  wish does not strand my booking.
- As a gifter, I want an archived or deleted list to refuse change, cancel,
  the purchase mark, and «Вернуть в бронь». I want the promise on an
  archived list to stay visible with «Вишлист в архиве», so that I still
  see it and the product does not pretend the list is open. Deleting a
  list cancels occupying promises, so they leave the cabinet and drop out
  of the active count.
- As another gifter, I want this screen to hide who else promised the same
  wish, so that the surprise is not passed along.
- As the owner of a personal list, I want bookings of my own wishes to stay
  off this screen, so that I do not learn who is preparing my gifts. I am
  the recipient of every wish on that list.
- As the recipient of a wish on a collaborative list, I want this screen to
  omit other people's promises on that wish. Promises I made on wishes meant
  for someone else still appear.
- As an anonymous viewer, I want no home card and no cabinet, so that a
  shared link does not present someone else's commitments or an empty
  personal counter.

## Definition of Done

The task is done when all of the following hold.

1. An identified user sees the home card «Мои бронирования». Its badge is
   the active count.
2. An identified user whose active count is 0 sees badge 0. Opening the
   card shows «Нет бронирований» and no wishlist group.
3. A viewer who is not identified has no home card and no cabinet. A shared
   list does not grow this card.
4. The cabinet lists only the caller's occupying promises, grouped by
   wishlist. The group header shows the wishlist title. When the list has
   an event title or an event date, the header shows each one it has. Each
   wishlist that contains at least one such promise appears once. Groups
   follow alphabetical order of the wishlist title. Promises inside a group
   follow the order in which the caller made them, earliest first. A
   cancelled promise is absent. A wishlist with no occupying promise from
   the caller is absent.
5. Each promise is its own row. The row shows the wish title, that promise's
   quantity, «Забронировано» or «Куплено», and who the wish is for. It shows
   «Желание в архиве» when the wish is archived, and «Вишлист в архиве» when
   the list is archived. The row does not name another gifter and does not
   show another gifter's quantity or purchase mark.
6. A wish the caller receives does not appear because someone else promised
   it. On a personal list the owner is the recipient of every wish,
   including a wish that has only a display name, so bookings of that list
   stay off the owner's cabinet. On a collaborative list, silence applies to
   wishes meant for the caller. A display name alone does not make the
   caller the recipient, and it does not hide a promise the caller actually
   made.
7. The badge follows the active count when the caller holds more than one
   occupying promise on the same wish: the cabinet shows each promise, and
   the wish contributes one to the badge.
8. When the wish is still presented with giver controls, the cabinet row
   offers only «К желанию». That opens the wish card, and WISHENKA-19
   edits the latest promise only. An earlier promise is listed, and it is
   not edited from the cabinet while the card still has giver controls.
   «Изменить», «Отменить бронь», «Куплено», and «Вернуть в бронь» appear
   in the cabinet only after those card controls are gone. This task does
   not add a second set of giver controls to the wish card.
9. When the wish is no longer presented with giver controls, and the list is
   still active, the cabinet offers «Изменить», «Отменить бронь»,
   «Куплено», and «Вернуть в бронь» for that promise. Whether a quantity is
   accepted stays the rule already in force (WISHENKA-57).
10. On an archived or deleted list, the cabinet refuses change, cancel, the
    purchase mark, and «Вернуть в бронь». While a list is archived, the
    caller's occupying promise stays in the cabinet with «Вишлист в
    архиве». Deleting a list still cancels occupying promises, so they
    leave the cabinet and drop out of the active count.
11. The strings this task introduces are the Russian copy named in the
    functional requirements. The implementation language is Python 3.12+.

## Task Description

### Problem

Gifters can already promise a gift, change it, cancel it, and mark it
bought, and the wish card already carries those actions. Nothing on the
home screen tells them how many gifts they still hold, and nothing gathers
those promises across wishlists. Without that cabinet, a friend who booked
gifts on several lists has to open each list and scan each card.

The product already asks for this screen. The Mini App has a section «Мои
бронирования», opened from a home card, with a counter of active bookings.
Inside, bookings are grouped by wishlist. The counter counts distinct
reserved wishes, regardless of how many units a wish asks for. This task
fills that gap. The active count above is the rule for that counter.

The ticket also asks for a quick way to edit and to purchase. Those
outcomes already live on the wish card. While that card still has giver
controls, the cabinet offers only «К желанию». That opens the card, and
WISHENKA-19 edits the latest promise only. An earlier promise is listed
and is not edited from the cabinet while the controls remain. This task
picks up change, cancel, the purchase mark, and «Вернуть в бронь» only
when that card no longer offers the actions and the list is still active.
An archived or deleted list refuses all four. It does not build a new
inventory, and it does not replace the card.

### Programming language

Python 3.12+. The cabinet is a Mini App screen of this service.

### Already in the product

These behaviors exist and this task does not redefine them.

- A promise is intended, purchased, or cancelled. Intended and purchased
  promises occupy their units. A cancelled promise does not. Marking a
  promise purchased, or returning it to intended, does not free units.
  Recording receipt adds received units and does not close the promise.
  Those rules are WISHENKA-57.
- An identified gifter can create a promise, change its quantity, cancel
  it, mark it purchased, and undo that mark. A recipient cannot create one.
  On a personal list the owner is the recipient of every wish. On a
  collaborative list, whether someone is the recipient is decided per wish.
  A display name alone does not make someone the recipient. Those actions
  and that silence are WISHENKA-18.
- The wish card already shows giver controls to a non-recipient: book,
  change, cancel, «Куплено», and «Вернуть в бронь». The archive title row
  has no giver controls. Those controls are WISHENKA-19. This task does not
  add controls to the card and does not change the card's own line.
- On an archived or deleted list, a new promise and every change to an
  existing one are refused. On an archived wish whose list is still active,
  a new promise is refused, and change, cancel, purchase, and undo of an
  existing promise still succeed. Deleting a list cancels occupying
  promises. This task does not change that.
- The home screen already lists the caller's own wishlists, collaborative
  lists, and favorites, and it links to viewing history. This task adds the
  reservations card to that home. It does not rebuild those sections.
- The caller's open promises are already kept as that caller's intended and
  purchased promises. This task presents them. It does not invent a second
  record of who promised a gift.

### Still required

- The home card «Мои бронирования» with the active count.
- The cabinet screen: the caller's occupying promises, grouped by wishlist,
  in the Russian copy below.
- While giver controls are still on the wish card, a cabinet row offers
  only «К желанию». That opens the card, and WISHENKA-19 edits the latest
  promise only. An earlier promise is listed and is not edited from the
  cabinet while those controls remain. After the controls are gone, the
  cabinet offers change, cancel, mark purchased, and «Вернуть в бронь» on
  that promise when the list is still active, and refuses all four when
  the list is archived or deleted.
- Surprise silence: only the caller's promises, and no bookings of gifts
  meant for the caller. Anonymous viewers have no cabinet.

### Functional requirements

1. The home card title is «Мои бронирования». It sits on the home screen of
   an identified user, with the wishlist sections. Choosing it opens the
   cabinet. The cabinet title is the same phrase. The badge on the card is
   the active count, including when that count is 0.
2. The empty cabinet says «Нет бронирований». It shows no wishlist group and
   no promise row.
3. A viewer who is not identified does not see the card, the badge, or the
   cabinet. Opening a list by a shared link does not reveal this screen.
4. The cabinet includes a promise only when the caller holds it and it is
   intended or purchased. Promises held by anyone else are absent, including
   promises on a wish the caller receives. On a personal list the owner is
   the recipient of every wish, so that list contributes no booking to the
   owner's cabinet. A display name alone does not hide a promise the caller
   made, and it does not turn the caller into the recipient.
5. Promises are grouped by wishlist. The group header shows the wishlist
   title. When the list has an event title or an event date, the header
   shows each one it has. One wishlist produces one group. Groups follow
   alphabetical order of the wishlist title. The group contains each of the
   caller's occupying promises on that list, including two promises on the
   same wish, earliest promise first. The row quantity is that promise's
   quantity. The cabinet does not replace the row with the combined total
   the wish card uses. The cabinet does not offer a control to reorder
   groups or rows.
6. An intended row says «Забронировано». A purchased row says «Куплено».
   An archived wish adds «Желание в архиве». An archived list adds
   «Вишлист в архиве». The row names who the wish is for. On a personal
   list that person is the list owner. On a collaborative list it is the
   person designated on the wish, or the display name when no person is
   designated. The row does not name another gifter.
7. When the wish is still presented with giver controls, the row offers
   only «К желанию». That opens the wish card. WISHENKA-19 edits the
   latest promise only. «Изменить», «Отменить бронь», «Куплено», and
   «Вернуть в бронь» stay on that card for the latest promise. An earlier
   promise is listed, and it is not edited from the cabinet while the card
   still has giver controls. Those four labels appear on a cabinet row only
   after the card controls are gone. This task leaves the giver controls on
   the card and does not add a second set.
8. When the wish is no longer presented with giver controls and the list is
   still active, the cabinet offers those same four labels for that
   promise. «Изменить» changes that promise's quantity. «Отменить бронь»
   drops that promise. «Куплено» marks that promise purchased. «Вернуть в
   бронь» returns that purchased promise to intended. The quantity rules
   already in force decide whether «Изменить» is accepted. A refusal leaves
   the promise as it was. The cabinet does not name another gifter in a
   refusal.
9. On an archived or deleted list, the cabinet refuses change, cancel, the
   purchase mark, and «Вернуть в бронь». While the list is archived, the
   promise stays visible with «Вишлист в архиве». After a list is deleted,
   its occupying promises are cancelled and leave the cabinet. The active
   count follows.
10. After the caller changes a promise, the cabinet and the next home visit
    show the resulting promises and the active count. Cancelling the last
    occupying promise on a wish removes that wish from the count. Cancelling
    the last occupying promise on a wishlist removes that group.
11. This task does not add search, tags, or a sort control inside the
    cabinet. It does not add a receipt screen, a notification, or a payment.
    It does not translate the rest of the home screen.

### Non-functional requirements

1. Opening the home card and the cabinet stays as responsive as opening the
   home screen today. This task adds no new latency target.
2. The badge and the cabinet use the same occupying promises. The badge
   reports the active count. The cabinet reports each promise.
3. The screen available to the caller contains only that caller's promises.
   Hiding another gifter's name in the label, while leaving that person's
   booking in the content, does not meet this requirement. A recipient who
   opens the cabinet learns nothing about bookings of gifts meant for them.
4. An unidentified viewer receives no cabinet and no zero badge that would
   look like a personal total.
5. The quantity outcome and the surprise rule stay in force as further
   copies of the service are added. The cabinet does not invent a second
   balance.

### Constraints and assumptions

- The caller is the Telegram user who opened the Mini App. "No registration"
  means no extra profile form. It does not give an anonymous viewer a
  cabinet.
- Piece counts are positive whole numbers. The active count ignores units.
- A gifter may hold more than one occupying promise on one wish. The
  cabinet lists each of them. The active count includes that wish once.
- On a personal list the owner is the recipient of every wish. On a
  collaborative list, whether someone is the recipient is decided per wish.
  A display name alone does not make someone the recipient.
- Labels this task introduces stay the Russian copy named above. Russian
  and English are both product languages. This task does not add a
  translation catalog for the rest of the home.
- Sibling work stays on its own tickets:
  - WISHENKA-57 owns the shared quantity outcome. This task uses it.
  - WISHENKA-18 owns the promise actions and recipient silence on those
    actions. This task uses them and does not add another action.
  - WISHENKA-19 owns giver controls on the wish card and edits the latest
    promise only. While those controls are present, this task opens that
    card from «К желанию» and does not edit an earlier promise from the
    cabinet. It offers the same outcomes from the cabinet only when the
    card no longer has them.
- Also out of scope: notification text, payments, crowdfunding, secret
  gifts added by a gifter, a new promise store, receipt, and a history of
  cancelled promises. Identifying a recipient who has no Telegram user stays
  an open product question.

### Main entities

- **Wish.** A gift request on a list. In this cabinet the caller sees the
  title, who the wish is for, and whether the wish is archived. The caller
  does not see another person's promise on it.
- **Promise.** The caller's claim on a positive number of units of one
  wish. In this cabinet an occupying promise is intended or purchased. The
  caller sees that promise's quantity and status. Only the caller who holds
  it sees it here.
- **Wishlist group.** The wishes' list, used as the cabinet section. The
  caller sees its title, its event title and date when it has them, and
  whether the list is archived.
- **Home card.** The entry «Мои бронирования» on the home screen. Its badge
  is the active count.
- **Caller and wish.** On a personal list the owner is the recipient of
  every wish. On a collaborative list the same person can be a recipient of
  one wish and a gifter of another. This screen shows promises the caller
  made. It does not show bookings of wishes meant for the caller.

### Boundaries

In scope: the home card and its badge, the cabinet of the caller's own
occupying promises grouped by wishlist, surprise silence on that screen,
and a way back to a promise. While giver controls are on the wish card,
that way is «К желанию», which opens the card; WISHENKA-19 edits the
latest promise only, and an earlier promise is not edited from the
cabinet. When those controls are gone and the list is still active, the
cabinet offers change, cancel, mark purchased, and «Вернуть в бронь».
An archived or deleted list refuses all four.

Out of scope: a new quantity engine, a new promise action, giver controls
on the wish card, notification text, receipt, and translating the rest of
the home.

## Q&A

- **Why does the home need a counter if the wish card already shows a
  promise?** The card answers "what about this gift?" while the gifter is
  on that list. The home answers "how many gifts do I still hold?" before
  any list is opened. The spec places that counter on the home card «Мои
  бронирования».
- **What does the active count include?** The Active count section is the
  only definition. A purchased promise stays in it because a purchase mark
  does not end the booking. A badge that omitted those wishes would hide
  commitments the cabinet still lists.
- **Why not count units or promise rows?** The spec says the counter counts
  different reserved wishes, regardless of how many units were reserved.
  Two promises on one wish are still one gift on the badge. The cabinet
  lists both promises so the gifter can see each one. The badge stays the
  active count.
- **Why is a cancelled promise absent?** A cancelled promise no longer
  holds units and is no longer an open commitment. The cabinet is the list
  of promises the caller still holds.
- **Who is missing from the cabinet?** Everyone except the caller. Another
  gifter's promise is never a row. A recipient does not learn bookings of
  gifts meant for them by opening this screen. On a personal list the owner
  is the recipient of every wish, so those bookings are not in the owner's
  cabinet. A display name alone does not change that.
- **Why do anonymous viewers have no cabinet?** The cabinet is a personal
  record. A shared link can be opened without identifying the viewer.
  Showing a card there would either leak a personal total or present an
  empty counter that looks like an account. Unidentified viewers have
  neither the card nor the screen.
- **Where are edit and purchase?** On the wish card, which WISHENKA-19
  already owns. While giver controls are still on the card, a cabinet row
  offers only «К желанию». That opens the card, and WISHENKA-19 edits the
  latest promise only. An earlier promise is listed, and it is not edited
  from the cabinet while the card still has giver controls. «Изменить»,
  «Отменить бронь», «Куплено», and «Вернуть в бронь» appear in the cabinet
  only after those card controls are gone, and only while the list is still
  active. On an archived or deleted list those four outcomes stay refused.
  The quantity outcome stays WISHENKA-57. The action itself stays
  WISHENKA-18.
- **What remains for the sibling tickets?** WISHENKA-57 owns quantity.
  WISHENKA-18 owns promise actions and silence on their answers.
  WISHENKA-19 owns giver controls on the wish card. WISHENKA-20 owns the
  home counter and the caller's cabinet.
