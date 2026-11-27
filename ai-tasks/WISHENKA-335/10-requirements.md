# WISHENKA-335: One shared way to bring a database current

## Goals

The product brings stored data up to the latest agreed changes before
people use it. That procedure lives with wishlists. Person storage uses
the same procedure by asking the wishlist area. There is one history of
changes and one procedure. The procedure is not a shared capability that
any database can use while keeping its own history.

A later database would have to carry its own copy of the same steps:
wait while another start is already applying changes, apply that
database's own ordered changes, leave an already-current database
alone, adopt a recognized older shape without rewriting its rows, refuse
an unknown older shape, refuse an unsupported database address, and
choose the durable journal for a file database. Person storage is
already tied to the wishlist area for a procedure that is not a wishlist
rule.

This task makes that procedure one shared way. Each database keeps its
own history. The wishlist history stays the wishlist history. People and
wishlists still share the history they already share. Nothing a person
sees changes. The person-key change and the check that rolls it backward
stay as they are.

This task comes from the technical-debt note on WISHENKA-188. It is not
a new screen, a new history of changes, or a new rule for who a person is.

Implementation language: Python.

## User Stories

- As a person opening the product, my wishlists and my profile are
  already at the latest agreed shape. I see the same lists, wishes,
  members, and profile as before. This task does not move, drop, or
  rewrite those records.
- As the product starting wishlist storage, startup still brings that
  database to the latest change in the wishlist history. A recognized
  older wishlist is still adopted at the matching point without
  rewriting its rows. An unknown older wishlist is still refused. An
  already-current database is left as it is.
- As the product starting person storage, startup still brings the same
  database current. It uses the shared way. It does not keep a private
  copy of that way, and it does not ask the wishlist area to apply the
  changes.
- As the product starting the site, the bot, or the notice tools,
  startup still brings the database current before that surface is used.
  The site still starts both wishlist storage and person storage. The
  bot and the notice tools still start wishlist storage.
- As a maintainer of a later database, that database can use the same
  shared way and keep a history of its own. This task does not add that
  database and does not add that history.
- As a maintainer of the person-key change, the existing forward check
  and the backward check from WISHENKA-334 still describe the same
  restoration. This task does not change what that change moves or what
  the rollback gives back.

## Definition of Done

- There is one shared way to bring a database to the latest change in
  that database's own history.
- Wishlist storage and person storage both use that shared way on
  startup. Person storage does not ask the wishlist area to apply the
  changes, and it does not keep a second copy of the procedure.
- The wishlist history is unchanged: the same ordered changes, the same
  adoption of a recognized older wishlist, and the same refusal of an
  unknown older wishlist. Rows of a recognized older wishlist are not
  rewritten in order to adopt it.
- Applying the changes still waits, for a bounded time, when another
  start is already applying them to the same file, and still fails when
  that wait runs out. An in-memory database does not take that file wait.
- An unsupported database address is still refused. A file database
  still ends on the durable journal. A second application to an
  already-current database still changes nothing and does not adopt the
  older shape again.
- The same outcomes are still recorded: the application started, it
  finished and how long it took, it failed, and a recognized older
  wishlist was adopted at which point in the history.
- The existing checks of those outcomes still pass, including the
  person-key rollback check from WISHENKA-334. That check still restores
  the earlier identity and the earlier shape of invite tokens and
  support tickets. The person-key change itself is not redesigned.
- No new screen, no new sentence for a person, and no second history of
  changes.

## Task Description

WISHENKA-188 left person storage asking the wishlist area to bring the
database current. The debt is that the procedure for applying a
database's own history lives inside wishlists. The product has one such
procedure and one history. Wishlist startup, person startup on the site,
and the wishlist startup used by the bot and the notice tools all end
in that same procedure.

The shared way is only where that procedure lives and who may use it.
It is not a new rule for what the wishlist history does. Recognizing an
older wishlist, refusing an unknown one, waiting on a file, choosing the
durable journal, and recording start, finish, failure, and adoption stay
the same outcomes.

Each database keeps its own history. Today people and wishlists share
one history because they share one database. This task does not split
that history and does not invent a second one. A later database may use
the shared way with a history of its own. That later database is not
part of this task.

The person-key change stays the change WISHENKA-188 shipped. The
backward check from WISHENKA-334 stays that check. This task does not
rewrite either of them to fit the shared way.

### Business entities

- **Database:** the stored record the product opens on startup. People
  and wishlists share one database today. Each database has its own
  history of agreed changes.
- **Change history:** the ordered changes for one database. The wishlist
  history stays that history. This task does not add, remove, or reorder
  a change.
- **Shared application:** the one way a database is brought to the
  latest change in its own history. Wishlist startup and person startup
  both use it. It is not owned by wishlists, and it is not copied once
  per database.
- **Recognized older wishlist:** a wishlist database from before the
  history was recorded, whose shape matches a known point. It is adopted
  at that point without rewriting rows. An unknown older shape is
  refused.
- **Person:** someone the product already knows. This task does not
  change which identity the product remembers, and it does not change
  the rollback of the person-key change.
- **Maintainer:** the person who relies on the existing checks that the
  database comes current, and on the person-key rollback check.

### Boundaries

In scope:

- One shared way to apply a database's own history.
- Wishlist startup and person startup both use that way.
- Person startup no longer depends on the wishlist area to apply
  changes.
- The current outcomes of applying changes stay: bounded wait, refusal
  of an unsupported address, adoption of a recognized older wishlist,
  refusal of an unknown older wishlist, no second adoption, durable
  journal on a file database, and the same recorded outcomes.
- A later database can use the same way without copying it. This task
  does not add that database.

Out of scope:

- A new history, a split of the shared people-and-wishlists history, or
  a new change in that history.
- The person-key change and the check that rolls it backward
  (WISHENKA-334). What they restore stays as it is.
- Person storage's own preparation of a file database before the shared
  application runs. That preparation stays.
- How long the wait is, the sentences a person already sees when startup
  fails, and the refusal when the wait runs out.
- A new screen, a new person-facing sentence, or a rewrite of existing
  rows for its own sake.

## Q&A

**Why is this a product problem?** Startup must bring stored data
current before a person uses it. That procedure is trapped in the
wishlist area, so person storage has to ask wishlists, and any later
database would copy the same steps. The business goal is one shared way,
with each database keeping its own history.

**Is there already a second copy?** No. Inspection of the startup paths
shows one procedure, owned by wishlists. Person startup on the site
calls it. The bot and the notice tools start wishlist storage, which
calls it. The debt is the ownership, not a second procedure to delete.

**Does this split people from wishlists?** No. They still share the one
database and the one history they already share. The shared way applies
that history. It does not create a separate history for people.

**What stays wishlist-specific?** Which older wishlist shapes count as
recognized, and the ordered wishlist changes themselves. Those stay with
the wishlist history. The shared way does not absorb them into a rule
for every database.

**Why is the person-key work untouched?** WISHENKA-334 already checks
that rolling the person-key change backward restores the earlier
identity and the earlier shape of invite tokens and support tickets.
This task does not redesign that change or that check.

**Why is a later database mentioned but not built?** The shared way
exists so a later database does not need a private copy. This task does
not add that database or a history for it.
