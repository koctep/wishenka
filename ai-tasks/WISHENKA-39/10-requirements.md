# WISHENKA-39: Load and concurrent booking checks

## Goals

Gifters book the same wish at the same moment. The product already
limits that booking: the units they occupy cannot pass the free
remainder, and the last free units go to the bookings that fit.

Those rules are already shown for a short race. What this task still
has to prove is the same ceiling when many gifters compete together,
when that competition is repeated, and when a stretch of competing
bookings keeps going. The owner and the gifters need evidence that a
crowd books exactly the quantity that was available: the same unit is
not promised twice, and units that gifters are asking for are not
dropped.

This task adds that automated proof. The deliverable is checks of the
ceiling the product already has.

## User Stories

Roles follow the product: owner, gifter, and recipient. On a personal
list the owner is the recipient of every wish.

- As a gifter, I want many of us trying to book the last free units at
  the same moment to succeed for exactly those units, so that two of us
  do not buy the same unit and a free unit is not lost.
- As a gifter, I want the same result each time we compete for a known
  free remainder, so that an earlier crowd does not leave a second
  booking or a missing unit.
- As an owner, I want a stretch of friends booking a wish to keep the
  booked quantity within what was available, so the list still matches
  what can be given.
- As an operator of the service, I want an automated proof of that
  ceiling under repeated contention, many gifters, and a load of
  bookings, so a two-person example is not the only evidence.

## Definition of Done

The task is done when all of the following hold.

1. Automated checks close row R5 of `doc/dev/verification-matrix.md`:
   repeated contention, many gifters, and a load profile that keeps
   the same ceiling.
2. Many gifters, one unit each. More than two gifters try at the same
   moment to book one wish. Each asks for one unit. There are more
   gifters than free units, and at least one unit is free. The number
   of units booked in that contention equals the number that were free.
   Each booked unit has one gifter. Every other gifter is refused. A
   refusal leaves the last complete balance unchanged.
3. Whole remainder. More than two gifters each try, at the same moment,
   to book the entire free remainder of one wish. Exactly one succeeds.
   The booked quantity equals the available quantity. Every other
   gifter is refused. A refusal leaves the last complete balance
   unchanged.
4. Repeated contention. The competitions in items 2 and 3 run again,
   each time from a known free remainder. For each repetition, the
   booked quantity equals the available quantity for that repetition.
   Units already booked on that wish are not booked again.
5. Load profile. A bounded series of those competitions, with many
   gifters, keeps the ceiling for the whole series. The ceiling is
   judged per wish. After every finished attempt, the free remainder
   is zero or positive. Booked quantity does not exceed the quantity
   that was available. Each repetition that matches item 2 or item 3
   still books exactly the available quantity for that repetition.
6. The checks use the shared inventory friends already share. They hold
   when one running copy accepts the bookings and when more than one
   running copy accepts them together.
7. Rows R1, R2, R3, and R4 stay on the checks already named for those
   rows.
8. Rows S5, S6, S8, and A3 stay closed by WISHENKA-38.
9. The checks are Python 3.12+. Each check finishes within a bound
   chosen for that check. An unbounded wait is not proof.
10. Product behavior stays as it is. The task adds no locking design
    and no isolation design.

## Task Description

### Problem

The reservation limit says the total booked by gifters cannot exceed
the quantity the owner requested (high-level spec, section 6). Gifters
see a current free remainder so they do not buy the same units twice.

That ceiling is already in force. The free remainder is the requested
quantity, minus units already received, minus units occupied by
intended and purchased promises. After a successful new promise, that
remainder is zero or positive. A promise that would make it negative
is refused and leaves the last complete balance unchanged. A purchased
promise still occupies its units. A cancel or a decrease releases
those units once.

WISHENKA-57 made that outcome hold for one shared inventory, including
when several running copies accept bookings. The verification matrix
records the short examples on rows R1–R4. Row R5 is still open.

The ticket is written as automated concurrency tests: N gifters book
the last available units at the same time, and overbooking is
impossible. The business reason is the reservation limit under a
crowd. Booked quantity for that contention equals the quantity that
was available. Friends can trust the last units.

### Programming language

Python 3.12+, the language of the wishlist service. The deliverable is
automated checks in that language.

### What this task delivers

Automated checks that close matrix row R5. They prove the current
ceiling under repeated contention, many gifters, and a bounded load of
those contentions. They leave product behavior unchanged.

### Out of scope

- Further locking and isolation. WISHENKA-57 already keeps one shared
  inventory balance. WISHENKA-49 owns further locking and isolation.
  This story is the race and load checks.
- A second proof of rows R1, R2, R3, and R4. That includes the
  two-party race, a refused increase, a release that returns units
  once, a lower requested quantity, receipt, a purchased promise that
  stays occupied, and the sentence a losing gifter is shown.
- Surprise and share-link checks. WISHENKA-38 closed S5, S6, S8, and
  A3. The other surprise and share-link rows the matrix already marks
  covered stay on those checks.
- A notification sender, payments, crowdfunding, and secret gifts
  outside the list.
- A capacity plan. The load profile keeps the ceiling under contention.
  It sets no response-time target and no throughput target.
- Partial fills. A request that no longer fits is refused in full, as
  the product already does.
- Idempotent replay of one gifter repeating the same tap.

### Functional requirements

#### Ceiling the checks prove

Available quantity for a contention is the free remainder when the
attempts start. Booked quantity for that contention is the sum of units
newly occupied by promises that succeed in it.

The free remainder is the requested quantity, minus units already
received, minus units occupied by intended and purchased promises. It
is zero or positive. A new promise that would make it negative is
refused and leaves the last complete balance unchanged.

#### Many gifters, one unit each

More than two gifters attempt this together. Each asks for one unit of
the same wish. More gifters attempt than there are free units, and at
least one unit is free.

The booked quantity equals the available quantity. Each successful unit
belongs to one gifter. Every gifter who does not receive a unit is
refused. The refusal adds no promise and leaves the last complete
balance unchanged.

#### Whole remainder

More than two gifters attempt this together. Each asks for the entire
free remainder of the same wish. The remainder is at least one unit.

Exactly one gifter succeeds. The booked quantity equals the available
quantity. Every other gifter is refused. The refusal adds no promise
and leaves the last complete balance unchanged.

#### Repeated contention

Items "Many gifters, one unit each" and "Whole remainder" each run
more than once. Every repetition starts from a known free remainder.

For each repetition, the booked quantity equals the available quantity
of that repetition. Units already occupied on that wish stay occupied
once. A later repetition does not grant them again.

#### Load profile

A bounded series runs many of those repetitions with many gifters. The
series may include more than one wish. Each wish is judged on its own
remainder.

After every finished attempt in the series:

- the free remainder of that wish is zero or positive
- the booked quantity from that attempt does not exceed the quantity
  that was available
- a repetition shaped as "Many gifters, one unit each" or "Whole
  remainder" books exactly the available quantity for that repetition

The series ends in that same state.

#### Shared inventory

The checks run against the inventory the product already shares. The
same results hold when one running copy accepts the attempts and when
more than one running copy accepts them together. A copy does not keep
a private booking total.

### Non-functional requirements

1. Each check finishes within a bound chosen for that check. An
   unbounded wait is not proof.
2. The checks join the service's existing automated test run. The load
   profile is that bounded series. It is not a capacity target.
3. These requirements and the checks are in English.

### Constraints and assumptions

- Parent epic: WISHENKA-36. WISHENKA-37 published the verification
  matrix. This task owns row R5.
- "Many gifters" means more than two acting at the same moment. The
  two-party examples stay on rows R1 and R2. This document does not
  fix a larger crowd size. The later steps choose a bounded crowd and
  a bounded number of repetitions.
- "Exactly" applies to the two request shapes in the functional
  requirements: each gifter asks for one unit, or each asks for the
  whole remainder. A request larger than what remains is refused in
  full. The leftover stays available. That refusal is the existing
  rule. It does not fail the exact result for the shapes above.
- How a repetition is given its starting remainder is a setup for the
  check. It does not add a new release rule or a new receipt rule.
- A person still cannot book a wish meant for themselves. An archived
  wish still keeps existing promises and refuses new ones. Those rules
  stay in force. This task does not re-prove them.
- The losing gifter is still told the free remainder and is still not
  told who won. That sentence stays on row R4.
- The recipient still learns nothing about who is booking or buying.
  This task does not re-check the surprise walk.
- Payments, crowdfunding, and secret gifts outside the list stay
  outside the product.

### Main entities

- **Wish.** A gift request. Attributes used here: requested quantity,
  received quantity, and the free remainder. The free remainder is zero
  or positive.
- **Promise.** A gifter's claim on a positive number of units of one
  wish. Intended and purchased promises occupy their units. A refused
  attempt does not add a promise.
- **Available quantity.** The free remainder at the start of one
  contention.
- **Booked quantity.** Units newly occupied by promises that succeed in
  that contention. For the request shapes in this task, it equals the
  available quantity.
- **Gifter.** A person who books units of a wish. Many gifters compete
  in one contention.
- **Contention.** One moment when more than two gifters try to book the
  same wish. It ends when every attempt has succeeded in full or been
  refused in full.
- **Load profile.** A bounded series of contentions. It keeps the same
  ceiling on every wish it touches.
- **Running copy.** One running instance that accepts bookings. Several
  copies share one inventory.

### Boundaries

In scope: automated proof that repeated contention, many gifters, and a
bounded load profile keep the booking ceiling, including the exact
result for the last available units.

Out of scope: a locking or isolation design, a second proof of rows the
matrix already marks covered, and the surprise checks closed by
WISHENKA-38.

## Q&A

- **Why is the ticket a set of tests?** The business need is trust in
  the reservation limit when a crowd books the last units. The short
  races already exist. This task proves the same ceiling for many
  gifters, for repeated races, and for a bounded load of those races.
- **Why does an earlier WISHENKA-57 note mention race stress tests on
  WISHENKA-49?** That note is older than the verification matrix.
  `doc/dev/verification-matrix.md` assigns row R5 to WISHENKA-39.
  WISHENKA-49 keeps further locking and isolation. This story follows
  the matrix: the proof is here, and a new coordination design is not.
- **Why must booked quantity equal the available quantity, when the
  spec says booked units cannot exceed the request?** The high-level
  limit forbids overbooking. The race in this ticket is stricter for
  the last available units. While gifters are asking for those units in
  the two shapes above, the successful bookings equal the quantity that
  was free. A unit is not given to two gifters, and it is not dropped.
  A request that cannot fit is still refused in full.
- **How large is N, and how long is the load profile?** N is more than
  two gifters at once. The profile is a bounded series of those
  contentions, long enough that the ceiling is judged across
  repetitions. Crowd size, repetition count, and the time bound are
  chosen in later steps. They are not a capacity plan.
- **What does the load profile measure?** That the ceiling still holds
  across the series, per wish. It sets no response-time target and no
  throughput target.
- **Does a refusal of a request that no longer fits fail the exact
  result?** It does not, for the two shapes this task requires. Each
  of those requests fits in the starting remainder on its own. After
  the winners take that remainder, further requests are refused in
  full and the booked quantity equals the available quantity.
- **Does this repeat WISHENKA-38?** Those rows stay closed there. This
  task does not walk the recipient response, the recipient log, the
  absence of a recipient notice, or the share-link visit.
