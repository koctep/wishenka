# WISHENKA-338: Opening one wishlist leaves the save lock free

## Goals

Several people can use the Mini App at the same time. A save of a wishlist
takes an exclusive lock so two saves do not overlap. A lookup that only
reads one wishlist is supposed to leave that lock free, so a save can
proceed while someone is only looking.

Opening one wishlist still takes that lock. The same lock is taken when a
person opens that wishlist's detail, its members, one wish, the list of
wishes, the gifted wishes, or the yes-or-no favorite mark shown with that
wishlist. None of these openings change the wishlist. While one of them
holds the lock, another person's save waits.

The older note also described these openings as rewriting the wishlist on
every look. That rewrite is not what these openings do now. They still
reserve the lock a save takes. The lock is not already free.

This task is a technical-debt follow-up from WISHENKA-213. It is not a new
screen, a new permission, or a new waiting policy.

Implementation language: Python.

## User Stories

- As a person opening one wishlist, I see that wishlist. The opening is a
  read. It leaves the exclusive lock to saves. Today that opening takes
  the same exclusive lock a save takes. A missing wishlist stays missing.
  A deleted wishlist stays deleted.
- As a person opening the detail of one wishlist, I see the same wishes,
  in the same order, with the same surprise rules. A recipient still sees
  no promise and no giver. A giver still sees the available quantity. The
  opening is a read and leaves the exclusive lock to saves. Today it takes
  that lock.
- As an owner, co-author, or member opening the members of one wishlist, I
  see the same members. A person who is not allowed to see members is still
  refused. The opening is a read and leaves the exclusive lock to saves.
  Today it takes that lock.
- As a person opening one wish on a wishlist, I see that wish as the
  product already shows it to me. A missing wish stays missing. The opening
  is a read and leaves the exclusive lock to saves. Today it takes that
  lock.
- As a person opening the wishes of one wishlist, I see the same wishes in
  the same order. Archived wishes stay visible only to a member, and only
  when the opening already includes them. The opening is a read and leaves
  the exclusive lock to saves. Today it takes that lock.
- As an author opening the gifted wishes of one wishlist, I see the same
  received wishes and the same receipts. A person who is not an author is
  still refused. The opening is a read and leaves the exclusive lock to
  saves. Today it takes that lock.
- As a signed-in person asking whether one wishlist is a favorite, I get
  the same yes or no. A person who is not signed in is not a favorite.
  That question is a read and leaves the exclusive lock to saves, including
  when the mark is shown together with that one wishlist. Today the mark
  is asked inside the same exclusive lock as opening the wishlist.
- As a person marking or unmarking a favorite, my choice stays a save and
  still takes the exclusive lock.
- As a person saving a wishlist, a member, a wish, an archive, a restore,
  or an ownership transfer, my save still takes the exclusive lock. This
  task does not turn those saves into reads.
- As a person whose gift should stay a surprise, these openings reveal
  nothing the product already hides.

## Definition of Done

- Opening one wishlist is a read. It does not take the exclusive lock a
  save takes. The person sees the same wishlist, or the same missing or
  deleted result, as when no save is in progress.
- Opening the detail, the members, one wish, the wish list, and the gifted
  wishes of that wishlist are reads. None of them takes the exclusive lock
  a save takes. Each shows the same content and the same refusal it shows
  today: members stay limited to people who may see them, gifted wishes
  stay limited to authors, and surprise rules stay as they are.
- The yes-or-no favorite mark for one wishlist is a read. It does not take
  the exclusive lock, including when it is shown with that wishlist. The
  answer stays the same. Marking and unmarking a favorite stay saves.
- These openings change nothing. They do not add a favorite, a view, a
  member, a wish, or a receipt.
- A save of a wishlist still takes the exclusive lock. Settings, ownership,
  members, wishes, archive, restore, and delete stay saves.
- A request that still uses the shared wishlist repository and still takes
  the exclusive lock keeps the temporary-unavailable outcome it already
  has when the lock outlasts the brief wait. This task does not change
  that outcome, that wait, or that sentence.
- These openings do not add a new failure outcome, a new sentence, or a
  new screen.

## Task Description

WISHENKA-213 made a single-wishlist save load that one wishlist instead of
every wishlist. The follow-up for lookups was left open. The seven lookups
are opening one wishlist, opening its detail, opening its members, opening
one wish, opening its wishes, opening its gifted wishes, and asking whether
that one wishlist is a favorite.

Each lookup only reads. A missing wishlist, a deleted wishlist, a missing
wish, a refused member list, and a refused gifted list stay refusals. The
detail and the wish list keep the surprise rules and the archived-wish
rule. The favorite answer is yes, no, or no for a person who is not signed
in.

Today each of these lookups takes the exclusive lock a save takes. Opening
one wishlist and asking its favorite mark share that lock. A concurrent
save waits behind a lookup that changes nothing. The older note said these
lookups also rewrite the wishlist. That rewrite is not part of these
lookups now. The remaining problem is the lock.

Saves stay saves. Updating settings and transferring ownership sit beside
the favorite question in the old grouping, and both change the wishlist.
They keep the exclusive lock. Marking a favorite, removing a favorite, and
any other change keep the lock.

### Business entities

- **Person:** an owner, a co-author, a member, a giver, a recipient, or a
  visitor who can open a wishlist.
- **Wishlist:** one list. Opening it, or its detail, is a read.
- **Members:** the people on that one list. Opening them is a read.
- **Wish:** one item on that list, or the list of items. Opening them is a
  read.
- **Gifted wishes:** the received wishes and their receipts. Opening them
  is a read for an author.
- **Favorite mark:** whether one wishlist is a favorite for one person.
  Asking is a read. Changing the mark is a save.
- **Exclusive lock:** the lock a save takes so two saves do not overlap. A
  read in this task leaves it free.
- **Temporary-unavailable outcome:** the result a shared wishlist request
  already shows when the lock outlasts the brief wait. This task leaves
  that result on requests that still take the lock.

### Boundaries

In scope:

- Opening one wishlist.
- Opening the detail of that wishlist.
- Opening its members.
- Opening one wish on it.
- Opening its wishes, with the archived-wish rule unchanged.
- Opening its gifted wishes.
- The yes-or-no favorite mark for that one wishlist, including when the
  mark is shown with the wishlist.

Out of scope:

- Person reads and person saves. Birthday reminders, language, the private
  chat, and other person data stay as they are.
- The temporary-unavailable outcome of the shared wishlist repository.
  A request that still takes the exclusive lock keeps that outcome, the
  brief wait, and the sentence it already uses. This task does not add a
  wait or a new way to report a remaining lock.
- Saves, including settings, ownership transfer, members, wishes, archive,
  restore, delete, and marking or unmarking a favorite.
- Opening a wishlist by its public link or its invite. Those openings still
  take the exclusive lock.
- The favorites list, view history, recording a view, and the list of
  deleted wishlists. Those still load more than one wishlist's worth of
  work and stay on their own follow-up.
- Saves that rewrite unchanged rows. That stays on its own follow-up.
- Extra checks that single-wishlist saves load only one wishlist. That
  stays on its own follow-up.
- A new person-facing sentence, status, or screen.
- Gift quantity, reservation, and surprise rules.

## Q&A

**Why is this a product problem?** Opening one wishlist, its members, its
wishes, its gifted wishes, or its favorite mark changes nothing. Each
opening still takes the exclusive lock a save takes, so a concurrent save
waits behind a lookup. The business goal is that these openings leave that
lock to saves.

**Is the lock already free?** No. These openings still take it. The older
note also said they rewrite the wishlist on every look. That rewrite is
not what these openings do now. The lock remains.

**Why does the favorite mark belong here?** The mark shown with one
wishlist is a yes-or-no read. Today it is asked inside the same exclusive
lock as opening that wishlist. Marking or unmarking a favorite is a save
and stays a save. The favorites list, which covers many wishlists, stays
out of this task.

**Why do settings and ownership stay saves?** They change the wishlist.
They were grouped with the favorite question only because they also target
one wishlist. This task does not turn a change into a read.

**Why is the shared repository outcome unchanged?** Requests that still
take the exclusive lock already report a remaining lock as temporarily
unavailable, after the brief wait they already use. This task moves the
listed openings off that lock. It does not change the outcome, the wait,
or the sentence for a request that still takes the lock.

**Why are person reads out of scope?** Person data, including birthday
reminders and the private chat, is a different lock problem and already
has its own follow-up. This task is only the one-wishlist openings listed
above.
