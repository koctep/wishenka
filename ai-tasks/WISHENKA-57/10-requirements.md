# WISHENKA-57: Shared Coordination of Gift Promises

## Goals

Gifters divide a wish so that friends do not buy the same units twice. Intended
and purchased promises occupy their units. A new or larger promise cannot take
more than the free remainder. Recording receipt does not close that promise.
After a successful receipt, occupied units plus received units may exceed the
requested quantity.

That outcome is reliable while one running copy of the service handles the wish.
When several copies accept bookings together, each copy can agree to the last free
units before the others learn about that agreement. Friends then prepare duplicate
gifts, and the list no longer matches what was actually promised.

This task makes that quantity outcome hold for one shared inventory served by
several copies at once. The recipient still learns nothing about who is booking or
buying.

## User Stories

Roles follow the product: owner, co-author, gifter, and recipient.

- As a gifter, I want my booking of the last free units to be the only successful
  one when someone else books those same units at the same time through another
  copy of the service, so that we do not both buy them.
- As a gifter, I want an increase of my existing promise to be refused when another
  copy has already taken the remaining units, so that my earlier promise stays as
  it was and the wish is not overbooked.
- As a gifter, I want units I release by cancelling or reducing my promise to
  become available once, so that another gifter can take them and a second copy
  cannot treat the same units as free again.
- As an owner, I want lowering the requested quantity to stay consistent with
  promises already made and units already received, even when a gifter is booking
  that wish through another copy at the same time, so that a refused change keeps
  the previous quantity.
- As a recipient, I want simultaneous bookings of my wish to stay hidden, so that
  a race between gifters does not reveal the surprise.
- As an operator of the service, I want several copies to serve one wishlist
  inventory without duplicate gift promises.

## Definition of Done

The task is done when all of the following hold.

1. Two or more copies share one inventory. Simultaneous attempts to promise the
   last free units of one wish end with exactly one success for those units. After
   every attempt has finished, the free remainder for further promises is zero or
   positive. A promise that would make that remainder negative is refused and
   leaves the last complete balance unchanged.
2. Raising an existing promise while another copy books the same wish uses the
   free remainder. The increase is refused when it would make that remainder
   negative. A refused increase leaves the earlier promise unchanged. After a
   successful increase, the free remainder is zero or positive.
3. A release (cancel, or a smaller quantity) racing with a new or larger promise
   on another copy keeps the released units available once. Those units are not
   dropped, and they are not consumed by two promises.
4. Lowering the requested quantity on one copy while another copy books the same
   wish is refused when the new quantity would be below occupied units plus
   received units. A refused change keeps the previous quantity.
5. Recording receipt on one copy while another copy changes promises on the same
   wish follows the receipt outcome. Receipt adds units to the wish received
   quantity, counted once. It does not close, cancel, or complete a promise. A
   receipt is refused when it would make received quantity larger than the
   requested quantity. Remaining unfulfilled quantity is the requested quantity
   minus units already received. A refused receipt leaves the last complete
   balance unchanged. Receipt is not limited by subtracting occupied promises.
   After a successful receipt, occupied units plus received units may exceed the
   requested quantity.
6. An attempt that stops before it finishes leaves the last complete balance. It
   does not add a partial promise and does not leave a partial receipt.
7. During and after these races, a recipient view contains no booking, gifter,
   purchase status, or free-remainder information. A gifter who loses a race is
   not told who won.
8. Promises for different wishes can succeed at the same time. A busy wish does
   not block an unrelated wish.
9. The same quantity outcome still holds when only one copy handles the race.
   Existing booking rules stay in force: a person cannot book a wish meant for
   themselves; intended and purchased promises occupy their units; a cancelled
   promise does not; a cancel frees units; recording receipt does not close,
   cancel, or complete a promise; an archived wish keeps existing promises and
   refuses new ones.
10. The implementation language is Python 3.12+.

## Task Description

### Problem

The service coordinates gift promises so friends do not buy the same units. That
coordination currently chooses the winner inside a single running copy. A second
copy can read the same free remainder and accept a second promise. The result is
overbooking: more units are promised than the owner requested, or two gifters each
believe they hold the last unit.

The ticket names candidate coordination mechanisms. Those mechanisms are ways to
build the guarantee. The business need is one shared outcome for every copy that
can change the same wish.

### Programming language

Python 3.12+, the language of the wishlist service.

### Functional requirements

1. Every copy that accepts changes to wishes uses the same inventory. A promise
   recorded by one copy counts in the occupied quantity of every other copy before
   that other copy records a conflicting promise.
2. The quantity outcome is the same on every copy:
   - Intended and purchased promises occupy their units. Cancelled promises do
     not. Recording receipt does not close, cancel, or complete a promise.
   - Receipt adds units to the wish received quantity, counted once. A receipt is
     refused when it would make received quantity larger than the requested
     quantity. Remaining unfulfilled quantity is the requested quantity minus
     units already received. A refused receipt leaves the last complete balance
     unchanged. Receipt is not limited by subtracting occupied promises. After a
     successful receipt, occupied units plus received units may exceed the
     requested quantity.
   - The ceiling for a new promise or a larger promise is the free remainder:
     requested quantity minus received units minus occupied units. That remainder
     is zero or positive after the promise change. A promise that would make the
     free remainder negative is refused and leaves the last complete balance
     unchanged.
   - Lowering the requested quantity is refused when the new quantity would be
     below occupied units plus received units. A refused change keeps the previous
     quantity.
   - The free remainder shown for further promises is the greater of zero and
     (requested quantity minus received units minus occupied units). It is never
     negative.
3. Every inventory change uses that same quantity outcome, including when the
   actions arrive through different copies:
   - Creating a promise, or increasing a promise, uses the free remainder. The
     change is refused when it would make that remainder negative, and the refusal
     leaves the last complete balance unchanged.
   - Decreasing a promise, or cancelling a promise, releases those units once.
     Cancelled promises do not occupy units.
   - Lowering the requested quantity is refused when the new quantity would be
     below occupied units plus received units. A refused change keeps the previous
     quantity.
   - Recording receipt adds units to the wish received quantity, counted once. It
     does not close, cancel, or complete a promise. A receipt is refused when it
     would make received quantity larger than the requested quantity. Remaining
     unfulfilled quantity is the requested quantity minus units already received.
     A refused receipt leaves the last complete balance unchanged. Receipt is not
     limited by subtracting occupied promises. After a successful receipt,
     occupied units plus received units may exceed the requested quantity.
4. Marking a promise purchased, or returning it from purchased to intended, does
   not free units. When that status change overlaps a quantity change on the same
   wish, both actions finish as whole outcomes: a release or a new promise is
   applied once.
5. When two actions conflict, one definite winner is kept in full. The loser is
   refused and shown the free remainder that remains. A success does not later
   disappear.
6. A gifter's refusal states the shortage and the free remainder. It does not name
   another gifter. The recipient is not told about the race and has no view that
   reveals it.
7. Actions on different wishes proceed independently.
8. If a copy stops during an inventory change, other copies observe the last
   complete balance for that wish.

### Non-functional requirements

1. An uncontended booking stays as responsive as a booking on the service today.
   This task adds no new latency target.
2. A gifter waiting on one wish receives a definite success or refusal. The wait
   ends. A refusal caused by a busy wish can be retried, and that attempt does
   not consume units.
3. The quantity outcome stays in force as further copies are added. It does not
   depend on sending every booking through one chosen copy.
4. Surprise and role permissions stay as already specified. Intended and purchased
   promises occupy their units. Cancelled promises do not. Recording receipt does
   not close, cancel, or complete a promise. Receipt adds units to the wish
   received quantity, counted once, and is refused when it would make received
   quantity larger than the requested quantity. Remaining unfulfilled quantity is
   the requested quantity minus units already received. A refused receipt leaves
   the last complete balance unchanged. Receipt is not limited by subtracting
   occupied promises. After a successful receipt, occupied units plus received
   units may exceed the requested quantity. A new or larger promise is limited by
   the free remainder. That remainder is zero or positive after the promise
   change. A promise that would make the free remainder negative is refused and
   leaves the last complete balance unchanged. The free remainder shown for
   further promises is the greater of zero and (requested quantity minus received
   units minus occupied units). It is never negative. Lowering the requested
   quantity is refused when the new quantity would be below occupied units plus
   received units. A refused change keeps the previous quantity.

### Constraints and assumptions

- Roles, piece-count booking, the surprise rule, and the reservation limit are
  already specified. This task keeps those rules.
- Every copy shares one logical inventory. A copy does not keep a private booking
  total.
- Architecture decides how copies reach one shared outcome. This document requires
  the outcome only. It does not name a storage mode, a lock algorithm, or an extra
  infrastructure product, and it does not require two mechanisms together.
- Sibling work stays on its own tickets:
  - WISHENKA-18 owns the reservation API: create, quantity change, cancel,
    purchased, limit check, and recipient-field censorship.
  - Booking screens belong to WISHENKA-19 and WISHENKA-20.
  - This task owns the shared quantity outcome: no overbooking when several
    copies share one inventory. That outcome is definition of done items 1-9.
  - WISHENKA-49 owns reservation locking and race stress tests. The shared
    quantity outcome for copies of one inventory stays on this task.
  - WISHENKA-39 owns race-condition coverage beyond the acceptance examples in
    the definition of done.
- Also out of scope: idempotent replay of a repeated tap, gifter notifications,
  cabinet query speed, retention of old coordination state, payments,
  crowdfunding, and secret gifts added by a gifter.
- Replacing general wishlist storage is out of scope. An earlier debt note bundled
  private in-memory lists into this follow-up. Durable wishlist storage is a
  separate track and is not repeated here.

### Main entities

- **Wish.** A gift request. Attributes: requested quantity, received quantity,
  free remainder, and whether new promises are still allowed. The free remainder
  shown for further promises is the greater of zero and (requested quantity
  minus received units minus occupied units). It is never negative. An archived
  wish refuses new promises and keeps promises that already exist.
- **Promise (reservation).** A gifter's claim on a positive number of units of one
  wish. Attributes: gifter, quantity, and status (intended, purchased, or
  cancelled). Intended and purchased promises occupy their units. Cancelled
  promises do not. Recording receipt does not close, cancel, or complete a
  promise. The promise keeps its status and continues to occupy its units.
  Receipt adds units to the wish received quantity, counted once. A receipt is
  refused when it would make received quantity larger than the requested
  quantity. Remaining unfulfilled quantity is the requested quantity minus units
  already received. A refused receipt leaves the last complete balance unchanged.
  Receipt is not limited by subtracting occupied promises. After a successful
  receipt, occupied units plus received units may exceed the requested quantity.
- **Inventory change.** One create, increase, decrease, cancel, requested-quantity
  decrease, or receipt. It either completes in full or leaves the last complete
  balance unchanged. Recording receipt does not close, cancel, or complete a
  promise. A new promise or a larger promise completes only when the free
  remainder stays zero or positive. A promise that would make that remainder
  negative is refused. A receipt completes when received quantity stays at most
  the requested quantity. Receipt is not limited by subtracting occupied
  promises. After a successful receipt, occupied units plus received units may
  exceed the requested quantity. A refused receipt leaves the last complete
  balance unchanged. Lowering the requested quantity completes only when the new
  quantity is at least occupied units plus received units. A refused change keeps
  the previous quantity.
- **Service copy.** A running instance that can accept inventory changes. Several
  copies may run together and agree on one balance per wish.

### Boundaries

In scope: the shared quantity outcome for inventory changes, including changes
that arrive through different copies, and the same outcome when only one copy is
running.

Out of scope: new user-facing flows, a new reservation API, notification text, and
coordination work that does not change the quantity outcome.

## Q&A

- **Why does the ticket mention a database write lock and a distributed lock?**
  Both are candidate ways to stop two copies from accepting the same units. The
  reason for the work is that a new or larger promise on any copy is limited by
  the same free remainder. Architecture chooses the mechanism. This document does
  not require a particular database statement, a particular lock algorithm, or
  both mechanisms together.
- **Why is one running copy not enough?** The product is expected to serve
  bookings from more than one running copy. A decision that exists only inside one
  copy cannot stop another copy from promising the same units.
- **What does the losing gifter see?** That the requested units are no longer
  free, together with the current free remainder. The free remainder shown is the
  greater of zero and (requested quantity minus received units minus occupied
  units). It is never negative. The other gifter's name stays hidden. The
  recipient sees nothing that would reveal a booking or a purchase.
- **What if the owner lowers the requested quantity during a booking?** Lowering
  the requested quantity is refused when the new quantity would be below occupied
  units plus received units. A refused change keeps the previous quantity. This
  floor is separate from receipt. After a successful receipt, occupied units plus
  received units may exceed the requested quantity.
- **Does marking a promise purchased free the units?** No. Intended and purchased
  promises occupy their units. Cancelled promises do not. Only a cancel or a
  decrease releases units. Recording receipt does not close, cancel, or complete
  a promise. Receipt adds units to the wish received quantity, counted once. A
  receipt is refused when it would make received quantity larger than the
  requested quantity. Remaining unfulfilled quantity is the requested quantity
  minus units already received. A refused receipt leaves the last complete
  balance unchanged. Receipt is not limited by subtracting occupied promises.
  After a successful receipt, occupied units plus received units may exceed the
  requested quantity.
- **What limits a new or larger promise?** The free remainder: requested quantity
  minus received units minus occupied units. That remainder is zero or positive
  after the promise change. A promise that would make the free remainder negative
  is refused and leaves the last complete balance unchanged. The free remainder
  shown for further promises is the greater of zero and (requested quantity
  minus received units minus occupied units). It is never negative.
- **What remains for the sibling tickets?** WISHENKA-18 owns the reservation
  API: create, quantity change, cancel, purchased, limit check, and
  recipient-field censorship. Booking screens belong to WISHENKA-19 and
  WISHENKA-20. This task owns the shared quantity outcome: no overbooking when
  several copies share one inventory (definition of done items 1-9).
  WISHENKA-49 owns reservation locking and race stress tests. The shared
  quantity outcome for copies of one inventory stays on this task. WISHENKA-39
  owns race-condition coverage beyond the examples required above.
