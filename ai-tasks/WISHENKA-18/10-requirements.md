# WISHENKA-18: Gifter Promise Actions and Recipient Silence

## Goals

Friends coordinate gifts so the same units are not bought twice, and the
recipient still meets the gift as a surprise. A gifter who opened a list must
be able to promise units, change that promise, drop it, or mark it bought.
The person the wish is for must not learn any of that from the answers the
service gives them.

The quantity outcome for one shared inventory is already in force
(WISHENKA-57). This task does not replace it. It makes the promise actions
available to the client, and it keeps booking facts out of every answer shown
to the recipient of that wish.

Booking screens belong to WISHENKA-19 and WISHENKA-20. This task is the
behavior those screens will call.

## User Stories

Roles follow the product: owner, co-author, gifter, and recipient. Recipient
is decided per wish, not as a single role on the whole list.

- As a gifter who opened a friend's list, I want to promise some or all of the
  free units of a wish, so that another friend does not buy the same units.
- As a gifter, I want to raise or lower the size of my own intended or
  purchased promise, so that a change of plans frees units or takes units that
  are still free. A cancelled promise is not given a new size.
- As a gifter, I want to cancel my own promise, so that those units are free
  for someone else.
- As a gifter, I want to mark my own promise as bought, and to return it to
  intended if that mark was a mistake, so that I can track the purchase
  without giving the units back to the pool.
- As a recipient of a wish, I want every answer about that wish to omit
  bookings, gifters, purchase marks, and the free remainder, so that I cannot
  infer the surprise by asking the service directly.
- As a co-author, I want to promise a wish meant for someone else, and to see
  no booking facts on a wish meant for me.
- As another gifter, I want to see how many units are still free, and only my
  own promise, so that I can coordinate without learning who holds the rest.
  When I hold more than one promise on a wish, I see my combined quantity and
  the latest promise.

## Definition of Done

The task is done when all of the following hold.

1. An identified gifter can promise a positive whole number of units of an
   active wish that is not meant for them, while the list is not archived or
   deleted. The promise is immediate. The list author does not have to approve
   it. No separate profile form is required.
2. Subject to the archive and delete behavior in item 10, that gifter can
   raise or lower their own intended or purchased promise. A quantity change
   applies only to an intended or purchased promise. A cancelled promise
   cannot be given a new size and cannot occupy units again. A raise that
   would make the free remainder negative is refused, and the earlier promise
   stays. A lower promise frees the released units once. Lowering a purchased
   promise frees the released units and does not clear the purchase mark. A
   non-positive size is refused.
3. Subject to the archive and delete behavior in item 10, that gifter can
   cancel their own intended or purchased promise. The cancelled promise no
   longer occupies units. Cancelling an already cancelled promise is refused
   and changes nothing. Cancel after archive stays allowed when the list
   itself is still active.
4. Subject to the archive and delete behavior in item 10, that gifter can
   mark their own intended promise as purchased, and can return their own
   purchased promise to intended. Neither change frees units. A purchase mark
   on a promise that is not intended is refused. An undo on a promise that is
   not purchased is refused.
5. Only the gifter who holds the promise may change it, cancel it, mark it
   purchased, or undo that mark. Another person who tries is refused. The
   refusal does not name the holder.
6. A person who is the recipient of that wish cannot promise it. The refusal
   does not reveal whether anyone else has promised it, who they are, how many
   units are occupied, or whether a promise was marked purchased.
7. The same person, reading that wish or receiving the answer of a refused
   booking action, is not shown booking presence, booked quantity, free
   remainder, a fully-booked mark, their own booking, another person's
   identity, or a purchase mark on a promise. The wish's requested quantity
   and the received quantity the list author recorded stay visible. Those are
   the author's own figures, not a gifter's purchase mark.
8. A gifter who is not the recipient of the wish sees the free remainder and
   their own promise facts. They do not see another gifter's identity. When
   they hold one promise, they see its quantity and whether it is intended or
   purchased. When a gifter holds more than one promise on a wish, the wish
   view shows the caller's combined quantity and the latest promise (status
   of that latest promise). This task does not merge those promises into one.
   The success answer of a promise action refers to the promise that action
   just changed, not the combined view. A shortage refusal states the shortage
   and the free remainder and does not name who holds the rest.
9. On a collaborative list, silence applies only to wishes meant for the
   caller. The same person sees gifter facts on a wish meant for someone else.
10. This story does not change the current archive and delete behavior, and it
    does not freeze promises that already exist. On an archived or deleted
    list, a new promise, a quantity change, a cancel, a purchase mark, and an
    undo are refused. On an archived wish whose list is still active, a new
    promise is refused, but a quantity change, a cancel, a purchase mark, and
    an undo of an existing promise still succeed. Cancel after archive stays
    allowed. Deleting a list cancels occupying promises as part of that
    deletion. "Promises that already exist stay" must not be read as undoing
    that cancellation. The quantity outcome already delivered by WISHENKA-57
    still holds for these actions, including when several copies share one
    inventory.
11. Existing wish reads keep the same silence for the recipient and the same
    gifter facts for everyone else. Wishlist collection answers stay free of
    booking facts for every caller.
12. The implementation language is Python 3.12+.

## Task Description

### Problem

Gifters can already promise, resize, cancel, and mark a gift inside the
wishlist service, and a wish read already hides those facts from the recipient
of that wish. A client of the service still cannot perform the promise
actions. Without that surface, the Mini App cannot book a gift, and a
recipient who reaches a future booking answer could learn the surprise.

The ticket names client endpoints and a row lock. Those are ways to build the
behavior. The need is the four promise actions, the existing undo of a
purchase mark, and silence toward the recipient of the wish. The lock and the
quantity formula are already delivered.

### Programming language

Python 3.12+, the language of the wishlist service.

### Already in the product

These behaviors exist and this task does not redefine them.

- A promise can be created, cancelled, marked purchased, and returned from
  purchased to intended. Intended and purchased promises occupy their units. A
  cancelled promise does not. Marking purchased, or returning it to intended,
  does not free units. A quantity change applies only to an intended or
  purchased promise. A cancelled promise cannot be given a new size and cannot
  occupy units again. Lowering a purchased promise frees the released units
  and does not clear the purchase mark.
- Archive and delete already work as follows, and this task does not change
  them or freeze promises that already exist. On an archived or deleted list,
  a new promise, a quantity change, a cancel, a purchase mark, and an undo are
  refused. On an archived wish whose list is still active, a new promise is
  refused, but a quantity change, a cancel, a purchase mark, and an undo of an
  existing promise still succeed. Cancel after archive stays allowed. Deleting
  a list cancels occupying promises as part of that deletion. "Promises that
  already exist stay" must not be read as undoing that cancellation.
- A new or larger promise uses the free remainder: requested quantity minus
  received units minus occupied units. A promise that would make that
  remainder negative is refused and leaves the last complete balance. The
  free remainder shown is never negative.
- Recording receipt adds received units and does not close the promise.
  Receipt is capped by the requested quantity. After a successful receipt,
  occupied units plus received units may exceed the requested quantity.
  Lowering the requested quantity is refused when it would fall below occupied
  units plus received units.
- Those outcomes hold for one shared inventory served by several copies.
  A busy wish refuses the attempt without consuming units. A different wish
  is not blocked. This task does not specify how copies exclude each other.
- The recipient of a wish cannot promise that wish. On a personal list the
  owner is the recipient. On a collaborative list the recipient is the person
  named on that wish. A co-author can promise a wish meant for someone else.
- A wish read already follows that split. The recipient shape has no booking
  facts. The gifter shape has the free remainder and only the caller's own
  promise. When that caller holds more than one promise on the wish, the wish
  view shows the caller's combined quantity and the latest promise (status of
  that latest promise). Wishlist collection answers omit booking facts for
  every caller.
- One gifter may already hold more than one promise on the same wish. When a
  gifter holds more than one promise on a wish, the wish view shows the
  caller's combined quantity and the latest promise (status of that latest
  promise). This task does not merge those promises into one. The success
  answer of a promise action refers to the promise that action just changed,
  not the combined view.

### Still required

- The service accepts, from an identified gifter, the actions in the
  definition of done, including the refusals that definition states: create,
  change quantity, cancel, mark purchased, and return a purchased promise to
  intended. A quantity change applies only to an intended or purchased
  promise.
- Every answer of those actions, and any wish included with them, uses the
  recipient shape when the caller is the recipient of that wish, and the
  gifter shape otherwise. The caller cannot ask for the other shape.
- A recipient's refusal does not confirm that a promise exists.
- A new promise uses a positive whole number of units. The create path must
  refuse a non-positive size. Today only a quantity change enforces that
  floor.
- The acting gifter is the Telegram user who opened the list. An unidentified
  caller does not receive an ownerless promise. Opening the list still does
  not require a separate profile or onboarding.
- The success answer of a promise action refers to the promise that action
  just changed, not the combined view. When a gifter holds more than one
  promise on a wish, the wish view shows the caller's combined quantity and
  the latest promise (status of that latest promise). This task does not
  merge those promises into one.

### Functional requirements

1. Create, quantity change, cancel, mark-purchased, and undo are available to
   the gifter who holds, or is making, the promise, except where archive or
   delete already refuses them (requirement 8). Returning a purchased promise
   to intended stays available to that same gifter on those same terms. It is
   an existing product action, not a new status.
2. Each action finishes as one outcome. A refusal leaves the last complete
   promise and the last complete balance.
3. Quantity checks are the checks already delivered by WISHENKA-57. This task
   applies them to the client-facing actions. It does not replace them with a
   rule that ignores received units, and it does not treat a purchased
   promise as free. A quantity change applies only to an intended or
   purchased promise. A cancelled promise cannot be given a new size and
   cannot occupy units again. Lowering a purchased promise frees the released
   units and does not clear the purchase mark.
4. Silence is per wish. A collaborative-list member who is the recipient of
   one wish and a gifter of another receives the matching shape on each wish.
5. A wish addressed only by a display name, with no known person, does not
   make a Telegram user the recipient. This task does not identify that
   person. Surprise silence applies when the caller is the known recipient:
   the designated person, or the owner of a personal list.
6. The gifter's success answer shows the free remainder and does not name
   another gifter. The success answer of a promise action refers to the
   promise that action just changed, not the combined view. When a gifter
   holds more than one promise on a wish, the wish view shows the caller's
   combined quantity and the latest promise (status of that latest promise).
   This task does not merge those promises into one.
7. Wish reads that already hide booking facts from the recipient keep doing
   so. When a gifter holds more than one promise on a wish, the wish view
   shows the caller's combined quantity and the latest promise (status of
   that latest promise). This task does not merge those promises into one.
   Collection answers that omit booking facts for every caller stay that way.
   This task does not add booking facts to those collection answers.
8. This story does not change the current archive and delete behavior, and it
   does not freeze promises that already exist. On an archived or deleted
   list, a new promise, a quantity change, a cancel, a purchase mark, and an
   undo are refused. On an archived wish whose list is still active, a new
   promise is refused, but a quantity change, a cancel, a purchase mark, and
   an undo of an existing promise still succeed. Cancel after archive stays
   allowed. Deleting a list cancels occupying promises as part of that
   deletion. "Promises that already exist stay" must not be read as undoing
   that cancellation.

### Non-functional requirements

1. An uncontended promise stays as responsive as a promise on the service
   today. This task adds no new latency target.
2. A gifter receives a definite success or refusal. A refusal caused by a busy
   wish can be retried and does not consume units. It does not name another
   gifter.
3. Silence does not depend on the client hiding fields. The service omits
   them for the recipient of that wish.
4. The quantity outcome and the surprise rule stay in force as further copies
   are added.

### Constraints and assumptions

- The booker is the Telegram user. "No registration" means no extra profile
  form. It does not mean an anonymous promise with no owner.
- A gifter may hold more than one promise on one wish. Change, cancel, and
  purchase act on one promise that gifter owns. When a gifter holds more than
  one promise on a wish, the wish view shows the caller's combined quantity
  and the latest promise (status of that latest promise). This task does not
  merge those promises into one. The success answer of a promise action refers
  to the promise that action just changed, not the combined view.
- Piece counts are positive whole numbers.
- Sibling work stays on its own tickets:
  - WISHENKA-57 owns the shared quantity outcome and the exclusion that makes
    it hold across copies. This task uses that outcome.
  - WISHENKA-19 and WISHENKA-20 own booking screens, including the aggregated
    "My promises" section and its home counter.
  - WISHENKA-49 owns further reservation locking and race stress tests.
  - WISHENKA-39 owns race-condition coverage beyond the quantity outcome.
- Also out of scope: notification text, payments, crowdfunding, secret gifts
  added by a gifter, idempotent replay of a repeated tap, recording receipt,
  and lowering the requested quantity. Those last two stay on the rules
  WISHENKA-57 already delivered.
- Identifying a recipient who has no Telegram user, and what happens to
  promises when a profile is deleted, stay open product questions. This task
  does not close them.

### Main entities

- **Wish.** A gift request. Attributes the recipient may see: title and the
  other wish details, requested quantity, and received quantity recorded by
  the list author. Attributes only a non-recipient may see: free remainder,
  whether nothing is free, and that caller's own promise.
- **Promise.** A gifter's claim on a positive number of units of one wish.
  Attributes: gifter, quantity, and status (intended, purchased, or
  cancelled). Only the holding gifter may change it. The recipient is not
  shown the promise.
- **Caller and wish.** The same person can be a recipient of one wish and a
  gifter of another. Silence follows the wish, not a list-wide badge.

### Boundaries

In scope: client-facing create, quantity change, cancel, mark purchased, and
undo of that mark; refusals that do not reveal another gifter; per-wish
silence on the answers of those actions and on wish reads.

Out of scope: screens, the shared quantity mechanism, receipt, a new cabinet
of all of a gifter's promises, and notification text.

## Q&A

- **Why does the ticket list endpoints and a row lock?** The endpoints are
  the client-facing actions above. The row lock is one way to stop two copies
  from promising the same units. WISHENKA-57 already requires that shared
  outcome. This document does not name a storage statement or a lock
  algorithm, and it does not require a second mechanism.
- **Why is the check not "sum of promises at most the requested quantity"?**
  That wording ignores units already received, and it would free units when a
  promise is marked purchased. The rule in force is the free remainder from
  WISHENKA-57. A purchased promise still occupies its units. After receipt,
  occupied units plus received units may exceed the requested quantity. A new
  or larger promise is still limited by the free remainder.
- **Why include undoing a purchase mark?** The ticket names the change to
  "bought". The product already lets the gifter undo a mistaken mark, and the
  service already does that without freeing units. The client surface must
  keep that action. It is not a new status and it does not close the promise.
- **What does the recipient learn from a refused booking?** Nothing that
  confirms a promise, a holder, a quantity, or a purchase mark. A different
  refusal for "not yours" versus "no such promise" would reveal that a
  promise exists. The recipient's answer must not make that distinction.
- **What does another gifter learn?** The free remainder, and their own
  promise facts if they have a promise. When a gifter holds more than one
  promise on a wish, the wish view shows the caller's combined quantity and
  the latest promise (status of that latest promise). This task does not
  merge those promises into one. The success answer of a promise action refers
  to the promise that action just changed, not the combined view. A shortage
  refusal repeats the free remainder. It does not name the person who holds
  the rest.
- **Does a co-author who is also a recipient see a blank list?** No. Silence
  is per wish. Wishes meant for other people still show the free remainder
  and that co-author's own promises.
- **Where are the screens and the "My promises" section?** WISHENKA-19 and
  WISHENKA-20. This task does not draw them and does not add a new cabinet
  query. When a gifter holds more than one promise on a wish, the wish view
  shows the caller's combined quantity and the latest promise (status of that
  latest promise). This task does not merge those promises into one. The
  success answer of a promise action refers to the promise that action just
  changed, not the combined view.
- **What remains for the sibling tickets?** WISHENKA-57 owns the shared
  quantity outcome. This task owns the client-facing promise actions and
  recipient silence. Screens belong to WISHENKA-19 and WISHENKA-20. The
  quantity rules already delivered by WISHENKA-57 stay in force. This task
  does not replace them.
- **What do archive and delete do to promises?** This story does not change
  the current behavior and does not freeze promises that already exist. On an
  archived or deleted list, a new promise, a quantity change, a cancel, a
  purchase mark, and an undo are refused. On an archived wish whose list is
  still active, a new promise is refused, but a quantity change, a cancel, a
  purchase mark, and an undo of an existing promise still succeed. Cancel
  after archive stays allowed. Deleting a list cancels occupying promises as
  part of that deletion. "Promises that already exist stay" must not be read
  as undoing that cancellation.
- **Can a cancelled promise be given a new size?** No. A quantity change
  applies only to an intended or purchased promise. A cancelled promise cannot
  be given a new size and cannot occupy units again. Lowering a purchased
  promise frees the released units and does not clear the purchase mark. The
  free-remainder checks stay the ones WISHENKA-57 already delivered.
- **What is shown when one gifter holds several promises on a wish?** When a
  gifter holds more than one promise on a wish, the wish view shows the
  caller's combined quantity and the latest promise (status of that latest
  promise). This task does not merge those promises into one. The success
  answer of a promise action refers to the promise that action just changed,
  not the combined view.
