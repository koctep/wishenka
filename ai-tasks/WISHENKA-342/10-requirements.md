# WISHENKA-342: A person lookup refuses changes and reports a busy database

## Goals

Several people can use the bot and the Mini App at the same time. A save
takes an exclusive lock so two saves do not overlap. Looking up a person
only reads. That lookup already leaves the exclusive lock to saves.

Two gaps remain, and they sit on that same person lookup.

The lookup does not refuse a change at the moment it is attempted. It
undoes work when the lookup ends. A wishlist read already refuses a change
immediately, then hands its connection back ready for a later save. If that
hand-back fails, the wishlist read discards the connection so a later save
is still able to write. A person lookup has neither the refusal nor the
hand-back. A change attempted inside the lookup can reach the stored
person until the lookup ends, and a failed hand-back is not a concern only
because the refusal is missing.

When the database stays busy through the brief wait the product already
uses, a person save reports a temporary-unavailable outcome and keeps
nothing from the attempt. The same clash during a person lookup surfaces
as an ordinary database failure. The person, and any caller of the lookup,
cannot tell a brief clash from a broken lookup.

This task is a technical-debt follow-up from WISHENKA-254 (TD-1), left
open by WISHENKA-328. It is not a new screen, a new permission, or a new
waiting policy.

Implementation language: Python.

## User Stories

- As a person looked up by my Telegram identity, I am found or I stay
  absent, as I am today. The lookup changes nothing. A change attempted
  during the lookup is refused at once. After the lookup, a later save can
  still write. If the lookup cannot hand its connection back ready to
  write, that connection is discarded. A failure the lookup already has
  stays the failure the caller sees.
- As a person looked up by the product's own person id, I get the same
  guarantee: the same person or the same absence, a refused change, a
  connection that is ready to write afterwards or discarded, and the
  original lookup failure kept when one already exists.
- As a person whose lookup hits a busy database, the lookup reports the
  temporary-unavailable outcome person saves already use. The lookup
  changed nothing. Today that clash is an ordinary database failure.
- As a person whose lookup hits a database problem that is not this busy
  clash, I still get the ordinary failure that lookup already produces.
  The lookup does not adopt the wrapped failure a person save uses for
  that kind of problem.
- As a person saving my language, birthdate, sign-in, or any other person
  change, my save stays a save. Its exclusive lock and its
  temporary-unavailable outcome stay as they are.
- As a person opening my birthday reminders, or having my private chat
  looked up after a language save, those reads stay as WISHENKA-328 left
  them. They already leave the exclusive lock free. This task does not add
  a write refusal or a busy outcome to them.
- As a person opening a wishlist, that read stays as WISHENKA-338 left it.
  Its write refusal, its busy outcome, and its discarded connection stay
  on the wishlist read.

## Definition of Done

- Looking up a person by Telegram identity is a read. It still leaves the
  exclusive lock to saves. A change attempted during the lookup is refused
  at once. The person sees the same record, or the same absence, as when
  no save is in progress. A successful lookup adds no new message.
- Looking up a person by the product's own person id follows the same
  rule: same record or same absence, change refused, exclusive lock left
  to saves, no new message on success.
- After either lookup, the connection is ready for a later save to write.
  If restoring that readiness fails, the connection is discarded and is
  not reused. When the lookup already failed, that failure remains the one
  reported. Discarding the connection does not replace it.
- A busy database on either lookup reports the temporary-unavailable
  outcome person saves already use. The attempt changed nothing. The brief
  wait the product already uses stays the only wait. This task adds no
  second wait and no second attempt.
- A database problem that is not this busy clash stays the ordinary
  failure the person lookup already produces. It is not rewritten into the
  failure a person save uses for other storage problems.
- Person saves, including language, birthdate, sign-in, and preparing the
  store, stay as they are. Their exclusive lock and their
  temporary-unavailable outcome stay as they are.
- The birthday-reminder opening and the private-chat lookup after a
  language save stay as WISHENKA-328 left them.
- A wishlist read stays as WISHENKA-338 left it.
- This task adds no new person-facing sentence, status, or screen. The
  temporary-unavailable outcome is the one person saves already show.

## Task Description

WISHENKA-254 made a wishlist read refuse a change at once, hand the
connection back ready to write, discard it when that hand-back fails, and
report a busy database as temporarily unavailable. The same note left the
person lookup behind. WISHENKA-328 then made two other reads leave the
exclusive lock free, and it named this person lookup as the follow-up
that still lacks the stricter read guard and the busy outcome.

The person lookup is the read of one person by Telegram identity and the
read of one person by the product's own id. Both already leave the
exclusive lock to saves. Both return the person or an absence. Neither
creates a person. Settings, language resolution, and the private bot use
the Telegram-identity lookup. The id lookup is the same read for a known
person id.

Today a change attempted inside that lookup is undone when the lookup
ends. It is not refused when it is attempted. After the lookup there is
nothing to hand back, because the refusal was never turned on. A later
save can write only because the lookup never took write protection.

A busy database on that lookup is an ordinary database failure. Person
saves already turn that same clash into a temporary-unavailable outcome
after the brief wait the product already uses. The lookup must use that
outcome. Any other storage problem on the lookup keeps the ordinary
failure it has today. Person saves wrap that other kind of problem. The
lookup must keep its own failure.

A successful lookup stays quiet. Person saves may record that a change
was kept. This task adds no success message on the lookup.

### Business entities

- **Person:** anyone the product stores and can look up, by Telegram
  identity or by the product's own person id.
- **Person lookup:** a read of that one person. It returns the person or
  an absence. It changes nothing.
- **Exclusive lock:** the lock a person save takes so two saves do not
  overlap. This lookup already leaves it free.
- **Write refusal:** the lookup rejects a change at the moment it is
  attempted, then hands the connection back ready for a later save, or
  discards the connection when that hand-back fails.
- **Temporary-unavailable outcome:** the result a person save already
  shows when the database stays busy through the brief wait. The attempt
  changed nothing.
- **Ordinary failure:** the result a person lookup already shows for a
  database problem that is not this busy clash.

### Boundaries

In scope:

- The person lookup by Telegram identity.
- The person lookup by the product's own person id.
- A write refusal on those lookups, including handing the connection back
  ready to write, or discarding it when the hand-back fails, without
  hiding a failure the lookup already has.
- The existing temporary-unavailable outcome when those lookups find the
  database busy.
- A quiet success. The lookup adds no new success message.

Out of scope:

- Person saves and preparing the store. They keep the exclusive lock and
  the temporary-unavailable outcome they already have. Other storage
  problems on a save stay wrapped as they are today.
- The birthday-reminder opening and the private-chat lookup after a
  language save. WISHENKA-328 already leaves the exclusive lock free on
  those reads. They stay without this write refusal and without this busy
  outcome.
- Wishlist reads. WISHENKA-338 and WISHENKA-254 already refuse a change,
  discard a connection that cannot be handed back, and report a busy
  wishlist read as temporarily unavailable. This task does not change
  that read.
- A second wait, a second attempt, a new sentence, a new status, or a new
  screen.
- Gift quantity, reservation, and surprise rules.

## Q&A

**Why is this a product problem?** A person lookup changes nothing and
already leaves the exclusive lock to saves. It still allows a change until
the lookup ends, and a busy database looks like a broken lookup. Wishlist
reads already refuse the change and report the clash as temporarily
unavailable. The business goal is the same guarantee on the person lookup.

**Which lookups are in scope?** The read of one person by Telegram
identity and the read of one person by the product's own id. Both go
through the same person-lookup path. A missing person stays missing.

**Why must the connection be ready to write afterwards?** The refusal
exists only for the lookup. A later save on a reused connection must still
be able to write. If the lookup cannot restore that readiness, the
connection is discarded. If the lookup already failed, that failure stays
the one reported.

**Why does a busy lookup use the save's outcome?** Person saves already
report a busy database as temporarily unavailable, after the brief wait
the product already uses. The lookup must use that outcome so a brief
clash is distinct from a broken lookup. This task adds no wait and no
retry of its own.

**Why do other storage errors stay ordinary?** A person save wraps a
storage problem that is not a busy database. The person lookup does not.
This task changes only the busy clash. Every other storage problem on the
lookup stays the failure the lookup already produces.

**Why are the birthday list and the private-chat lookup unchanged?**
WISHENKA-328 already made those reads leave the exclusive lock free, and
it left the stricter guard and the busy outcome to this task's person
lookup. Those two reads are separate paths. They stay as that task left
them.

**Why is the wishlist read unchanged?** It already has the write refusal,
the discarded connection, and the busy outcome. This task copies that
guarantee onto the person lookup. It does not reopen the wishlist read.

**Are there open questions?** No. The source note is WISHENKA-254
(`ai-tasks/WISHENKA-254/60-tech-debt.md`, TD-1). WISHENKA-328 records the
same follow-up and leaves those other reads alone.
