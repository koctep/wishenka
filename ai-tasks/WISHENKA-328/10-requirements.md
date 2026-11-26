# WISHENKA-328: Reads leave the save lock; two bot saves share the busy outcome

## Goals

Several people can use the bot and the Mini App at the same time, and one
save can briefly hold an exclusive lock on the shared database. A save is
supposed to take that lock. A lookup that only reads is supposed to leave
it free so a concurrent save can proceed.

Two lookups still take that lock. Opening the private birthday reminder
list only reads reminders, and it takes the same exclusive lock a save
takes. After a person saves their language, the product looks up the
active private chat so it can refresh the bot menu. That lookup only
reads, and it takes the same exclusive lock a save takes. While either
lookup holds the lock, another person's save waits or fails.

Two saves in the private bot still report a generic database failure when
the lock outlasts the brief wait the product already uses. Other person
saves already report a temporary-unavailable outcome and keep nothing from
the failed attempt. Turning one's own reservation confirmations on or off
can surface the generic failure. Recording the private chat where the bot
can reach the person can surface the generic failure. The person cannot
tell a brief clash from a broken save.

This task is a technical-debt follow-up from WISHENKA-121. It is not a new
screen, a new permission, or a new waiting policy.

Implementation language: Python.

## User Stories

- As a person opening my private birthday reminders, I see my list. That
  opening is a read. It leaves the exclusive lock to saves. Today that
  opening takes the same exclusive lock a save takes.
- As a person who saved my language, the product looks up my active private
  chat so it can refresh the bot menu. That lookup is a read. It leaves the
  exclusive lock to saves. Today that lookup takes the same exclusive lock
  a save takes. If I have no active private chat, my language stays saved
  and the menu refresh is skipped, as it is today.
- As a person turning my own reservation confirmations on or off, my choice
  is kept when the save completes. If the database stays locked after the
  brief wait the product already uses, I get the same temporary-unavailable
  outcome other person saves already use, and my previous choice stays.
  Today that save can surface a generic database failure.
- As a person opening the private bot, the product records the private chat
  where it can reach me. If that save completes, the chat is recorded. If
  the database stays locked after the same brief wait, that save reports
  the same temporary-unavailable outcome, and the chat record stays as it
  was. Today that save can surface a generic database failure.
- As a person whose language, birthdate, or sign-in save already reports
  temporary unavailability, that outcome stays as it is.
- As a person using a Mini App wishlist screen, my shared wishlist request
  keeps the exclusive lock and the temporary-unavailable outcome it already
  has, for a read and for a change.
- As a person whose gift should stay a surprise, the temporary-unavailable
  outcome does not name another person or reveal gift details.

## Definition of Done

- Opening the private birthday reminder list is a read. It does not take
  the exclusive lock a save takes. The list shows the same reminders it
  shows when no save is in progress. Adding, editing, and deleting a
  reminder stay saves.
- After a language save, the lookup of the active private chat is a read.
  It does not take the exclusive lock a save takes. The language save
  itself stays a save and already reports temporary unavailability when
  the lock outlasts the brief wait. A missing chat still skips the menu
  refresh and leaves the language saved.
- Turning reservation confirmations on or off still waits the brief
  interval a person save already waits. If the lock clears, the choice is
  kept once. If the lock remains, the save reports the temporary-unavailable
  outcome the person store already uses, and the previous choice stays.
  A generic database failure is the wrong result for that lock.
- Recording the private chat on bot open still waits that same brief
  interval. If the lock clears, the chat is recorded once. If the lock
  remains, that save reports the same temporary-unavailable outcome, and
  the chat record stays as it was. A person record already saved in the
  earlier step of opening the bot stays saved. This task does not join
  those two steps into one save.
- A database problem that is not this lock stays the ordinary failure the
  product already uses for that path.
- These reads and saves do not add a second wait or a second attempt. The
  brief wait a save already uses stays as it is.
- The temporary-unavailable outcome is the one person saves already use.
  This task does not invent a new status, a new sentence, or a new screen.
  It does not include database text, another person's identity, or gift
  details the product already hides.

## Task Description

WISHENKA-121 made person saves take the exclusive lock up front and, when
that lock outlasts the brief wait, report a temporary-unavailable outcome
with nothing kept from the attempt. Lookups that only read were meant to
leave that lock to saves. Two reads still take it, and two bot saves still
report a generic database failure.

The birthday list is the private list of reminders the person keeps for
themselves. Opening it reads those reminders and changes nothing. Today
that read takes the exclusive lock a save takes, so a concurrent save of a
wish, a reservation, or a person can wait behind a list that only needed
to read.

Saving a language already uses the person save and already reports
temporary unavailability when the lock remains. After that save, the
product looks up the active private chat in order to refresh the bot menu.
That lookup reads one chat and changes nothing. Today it takes the
exclusive lock a save takes, including when the lookup falls back to the
person data because the wishlist data is unavailable. The language is
already stored before this lookup runs. This task changes the lookup only.

The shared wishlist request used by Mini App screens reads and changes
wishlist data in one request. It already takes the exclusive lock for both,
and WISHENKA-326 already made a remaining lock temporarily unavailable.
The source note grouped that request with the reads above. Treating it as
a read that leaves the lock free would stop wishlist changes on that
request. This task leaves that request unchanged.

Turning reservation confirmations on or off is a save of that person's own
preference. The person must already exist. The save already waits the
brief interval. When the lock remains, the failure is a generic database
failure. It must be the temporary-unavailable outcome, and the previous
preference must stay.

Opening the private bot may create or refresh the person first. That step
already uses a person save and already reports temporary unavailability.
The next step records the private chat as the place the bot can deliver
messages. That step is its own save. When its lock remains, the failure is
a generic database failure. It must be the temporary-unavailable outcome,
and the chat record must stay as it was. The person record from the earlier
step stays saved.

### Business entities

- **Person:** anyone using the private bot or the Mini App profile.
- **Birthday reminder list:** the person's private reminders. Opening the
  list is a read. Changing a reminder is a save and stays a save.
- **Active private chat:** the chat where the bot can reach the person.
  Looking it up after a language save is a read. Recording it when the
  private bot opens is a save.
- **Reservation confirmation preference:** the person's choice to receive
  or skip confirmations of their own reservation actions. Changing it is a
  save.
- **Exclusive lock:** the lock a save takes so two saves do not overlap. A
  read in this task leaves it free.
- **Temporary-unavailable outcome:** the result a person save already shows
  when the lock outlasts the brief wait. The attempt changed nothing.
- **Ordinary failure:** the result for a database problem that is not this
  lock. This task leaves that result as it is.
- **Shared wishlist request:** one Mini App request that reads or changes
  wishlist data. It already takes the exclusive lock and already shows the
  temporary-unavailable outcome. This task leaves it unchanged.

### Boundaries

In scope:

- The birthday reminder list opens as a read and leaves the exclusive lock
  to saves.
- The lookup of the active private chat after a language save is a read and
  leaves the exclusive lock to saves, including the fallback to person data
  when wishlist data is unavailable.
- The reservation-confirmation save and the private-chat save report the
  existing temporary-unavailable outcome when the lock outlasts the brief
  wait, and they keep nothing from the failed attempt.

Out of scope:

- The shared wishlist request. It keeps its exclusive lock and the
  temporary-unavailable outcome from WISHENKA-326. This task does not turn
  its reads into reads that leave the lock free.
- WISHENKA-342. Person lookups that already leave the exclusive lock to
  saves stay as they are. This task does not add a stricter read guard or
  a busy outcome on those lookups.
- A second wait or a second attempt. The brief wait a save already uses
  stays as it is.
- Person saves that already report temporary unavailability, including
  language, birthdate, sign-in, and the create-or-refresh step when the
  private bot opens.
- How a read reports its own failure. This task stops the two reads from
  taking the exclusive lock. It does not add a new failure outcome for
  them.
- A new person-facing sentence, status, or screen.
- Gift quantity, reservation, and surprise rules.

## Q&A

**Why are these reads a product problem?** Opening the birthday list and
looking up the private chat change nothing. They still take the exclusive
lock a save takes, so a concurrent save waits behind a lookup. The business
goal is that a read leaves that lock to saves.

**Why is the shared wishlist request unchanged?** That request both reads
and changes wishlist data, and it already takes the exclusive lock for
both. WISHENKA-326 already reports a remaining lock as temporarily
unavailable. Leaving the lock free on that request would stop its changes.
The source note named it beside the reads; the current behavior is a
read-and-change, so it stays out of this task.

**What does the bot save change?** Turning confirmations on or off, and
recording the private chat, already wait the brief interval. When the lock
remains, they surface a generic database failure. They must report the
temporary-unavailable outcome person saves already use, with nothing kept
from that attempt. Creating or refreshing the person on bot open already
has that outcome and stays as it is.

**What does "retry" mean here?** A save already waits one brief interval
for the lock. If the lock clears, the save completes once. If it does not,
the outcome is temporary unavailability. This task does not add a wait or
an extra attempt.

**Which response does the person get?** The temporary-unavailable outcome
person saves already show. This task does not define a new one. Other
database failures stay ordinary failures.

**Are there open questions?** No. The source note is WISHENKA-121
(`ai-tasks/WISHENKA-121/60-tech-debt.md`, direct reads that take a save
lock, and two bot saves that skip the temporary-unavailable outcome).
