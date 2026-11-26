# WISHENKA-326: A shared wishlist request ends a brief lock as unavailable

## Goals

Several people can use the Mini App at the same time, and one change can
briefly hold the wishlist database. A wishlist save that goes through the
store and a request that uses the shared wishlist repository already wait
the same brief interval for that lock. The wait is already shared.

If the lock is still held when that wait ends, the store save is
temporarily unavailable and nothing from the attempt is kept. The shared
request is an ordinary storage failure. The person cannot tell a brief
clash from a broken request, and a screen that already answers a busy
store save as temporarily unavailable does not receive that outcome. This
is true for a read and for a change.

This task changes only the outcome after that wait. The shared request
becomes temporarily unavailable the same way the store save already does.
A database problem that is not that lock stays an ordinary storage
failure. This task does not add a new wait.

The work is a technical-debt follow-up from WISHENKA-80. It is not a new
screen, a new permission, or a new waiting policy.

Implementation language: Python.

## User Stories

- As a person whose request uses the shared wishlist repository, when the
  database is briefly locked, my request already waits the same brief
  interval a wishlist save through the store already waits. This task does
  not add a new wait. This applies when I am reading and when I am changing
  the wishlist.
- As a person whose request still cannot take the lock after that shared
  wait, I see the same temporary-unavailable outcome a store wishlist save
  already shows. Nothing from my attempt is kept. Today the shared request
  is an ordinary storage failure and the store save is already temporarily
  unavailable.
- As a person whose change succeeds after that wait, my change is kept
  once, the same as a change that never met the lock.
- As a person whose read succeeds after that wait, I see the wishlist data
  the product would have shown if the lock had not been there.
- As a person whose request fails for a database reason other than that
  lock, I still get the ordinary storage failure the product already uses.
- As a person whose gift should stay a surprise, the
  temporary-unavailable outcome does not name another person or reveal gift
  details.

## Definition of Done

- A request that uses the shared wishlist repository, whether it reads or
  changes wishlist data, already waits the same brief interval a wishlist
  save through the store already waits when a transient write lock is held.
  The wait is already shared. This task does not add a second waiting
  policy, a new wait, or a new number of attempts.
- After that wait, if the lock remains, the shared request is temporarily
  unavailable the same way the store save already is. Nothing from the
  attempt is kept. Today that request is an ordinary storage failure.
- If the lock clears during that wait, the request completes. A change is
  kept once. A read shows the wishlist data the product would have shown
  if the lock had not been there.
- A database failure that is not that lock stays an ordinary storage
  failure. Permission refusals, missing wishlists, and other product
  refusals stay as they are.
- Store wishlist saves that already wait and already show the
  temporary-unavailable outcome keep that behavior. This task does not
  change them.
- The temporary-unavailable outcome does not include database text, another
  person's identity, or gift details that the product already hides.

## Task Description

WISHENKA-80 left Mini App requests on a shared wishlist repository so a
screen can read or change one wishlist without loading every wishlist.
That request and a wishlist save through the store share one database.
Both already wait the same brief interval when a write lock is held. If
the lock remains after that wait, the store save is temporarily
unavailable and keeps nothing from the attempt. The shared request is an
ordinary storage failure.

The business reason is one outcome for one clash. After the wait both
paths already take, a person whose shared-repository request still cannot
take the lock should see that the attempt was temporarily unavailable and
changed nothing, the same way a store wishlist save already does. An
ordinary storage failure is the wrong result for that lock. The missing
behavior is that outcome, not a new wait.

The gap is every such request, a read and a change alike. The wait is
already shared. This task changes only the outcome after the wait. It does
not add a new wait or a series of new attempts. Link-clash retries stay as
they are.

A lock that outlasts the wait is shown as that same temporary-unavailable
outcome, so screens that already answer a busy store save keep answering
it. This task does not invent a new status, a new sentence, or a new
screen. Product refusals that are not a database lock stay on their current
responses. Other database failures stay ordinary storage failures.

### Business entities

- **Person:** an owner, member, giver, or recipient using the Mini App.
- **Shared wishlist request:** one request that reads or changes wishlist
  data through the shared wishlist repository. It already waits the same
  brief interval a store wishlist save waits. A read is not a wishlist
  save. A store wishlist save is the existing path that already shows the
  temporary-unavailable outcome when the lock remains.
- **Transient write lock:** another change still holding the database. Both
  paths already wait the same brief interval for it. It can clear during
  that wait, or it can outlast that wait.
- **Temporary-unavailable outcome:** the result a store wishlist save
  already shows when the lock outlasts the shared wait. The attempt changed
  nothing. Screens that already handle it answer it as temporarily
  unavailable. A shared wishlist request does not show this today; after
  the same wait it is an ordinary storage failure.
- **Ordinary storage failure:** the result for a database problem that is
  not this lock. A shared wishlist request also shows this today when the
  lock outlasts the shared wait. This task leaves other database failures
  on this result.

### Boundaries

In scope: the outcome after the shared wait, for every request that uses
the shared wishlist repository, when the lock outlasts that wait. That
includes reads and changes. The shared request becomes temporarily
unavailable the same way the store save already does. The wait itself is
already shared and stays as it is. Every other failure stays as it is.

Out of scope:

- The wait both paths already share. This task does not add or change it.
- Store wishlist saves that already wait and already show the
  temporary-unavailable outcome. Their behavior stays unchanged.
- A new waiting time, a new attempt count, or a new person-facing message.
- Link-clash retries when a new public or invite link is already taken.
  That remains its own follow-up.
- WISHENKA-324: the receipts screen's extra repository fallback stays.
- WISHENKA-328: user-profile reads and how they take a database lock.
- WISHENKA-342: user-profile reads and their busy failure.
- WISHENKA-335: where database upgrades are started from.

## Q&A

**Why is this more than an internal error rename?** A shared wishlist
request and a store wishlist save already wait the same brief interval
when the database write lock is held. After that wait, the store save is
temporarily unavailable and the shared request is an ordinary storage
failure. The person cannot tell a brief clash from a broken request. The
request may be a read or a change. This task changes only that outcome.

**What does "retry" mean here?** Both paths already wait the same brief
interval for the lock. If the lock clears, the request continues. If it
does not, the store save is temporarily unavailable and the shared request
is an ordinary storage failure. This task changes only that second outcome
so the shared request is temporarily unavailable the same way. It does not
add a wait or extra attempts. Link-clash retries stay as they are.

**Which response does the person get?** The temporary-unavailable outcome
the product already shows for a store wishlist save when the lock outlasts
the shared wait. This task does not define a new one. Other database
failures stay ordinary storage failures.

**Are there open questions?** No. The source note is WISHENKA-80
(`ai-tasks/WISHENKA-80/60-tech-debt.md`, shared-repository lock handling).
