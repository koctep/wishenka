# WISHENKA-23: Backend of Gift Receipt and Archive of Gifted Wishes

Programming language for implementation: **Python 3.12+** (see
`00-roadmap.md`).

Source of truth for behavior: the specification written by the Done story
WISHENKA-22. This file does not copy it. It selects the backend subset that
WISHENKA-23 must deliver and gives each item a stable ID that maps back to
the WISHENKA-22 requirement.

- `ai-tasks/WISHENKA-22/10-requirements.md`: FR-1 to FR-6, 19 corner cases
  (`CC-n` below), Q&A, assumptions A to D.
- `ai-tasks/WISHENKA-22/20-architecture.md`: split of work, plan for
  WISHENKA-23, architecture assumptions AR-1 to AR-5.
- `ai-tasks/WISHENKA-22/50-observability.md` and `60-tech-debt.md`: logging
  rules and the follow-ups owned by this story (`TD-n.m` below, Group 1).
- `in-docs/spec.md` sections 7.2 and 7.3, `doc/dev/gift-receipt.md`.

If this file and a WISHENKA-22 document disagree, WISHENKA-22 wins and this
file is corrected.

## Goals

Why the story exists. An owner receives gifts in real life, and today the
product cannot record it. The system has a counter of received units but no
way to set it through the product, no dated history, no «Подаренные», and no
notice to givers. As a result:

- the owner's active list shows wishes that already arrived;
- givers may buy a gift that is no longer needed;
- a received gift cannot be told apart from a wish the owner deleted.

This story builds the backend that makes the owner's act work end to end:
rules, storage, archive separation, and the notice to givers. The surprise
principle stays intact: receipt never shows the owner or the recipient who
promised, how many, or whether it was bought.

WISHENKA-24 builds the screens on top of this backend. This story delivers
no screens.

## Scope

### In scope

- Recording full or partial receipt of a wish by an author, with all its
  guards (R-1).
- A dated history of receipt acts that carries no giver, and the migration of
  data that exists before the story (R-2).
- The effect of receipt on open promises and on free quantity (R-3).
- The split of «Подаренные», the active list and the archive over one wish,
  including archive and restore of a partly received wish and legacy
  archived rows (R-4).
- Recipient-safe read data for the active list, «Подаренные», the archive and
  the giver views (R-5).
- The notice path to givers, in the minimum form fixed by the architecture:
  one event type (gift received), on by default, storage and lookup of both
  settings levels (user and list), the notice recorded together with the
  receipt, and its delivery after the receipt is final (R-6).
- Web access for the receipt and the read data, for authors only (R-7).
- Surprise and privacy rules for every artifact above (R-8).

### Out of scope

| Topic | Owner |
| ----- | ----- |
| Notification settings screen and any route that writes settings | WISHENKA-34 |
| Metrics exporter (Prometheus, OpenTelemetry); metrics are derived from logs only | WISHENKA-84 |
| Undo or correction of a receipt; the act is final | WISHENKA-153 |
| Product decisions on open points (assumptions A to D, public «already gifted» label, history of deleted lists, co-author who is the recipient, the edit-form lock) | WISHENKA-154 |
| Receipt screen, «Подаренные» section, cabinet marker, wish card changes, readable refusal screens, JS and templates | WISHENKA-24 |
| Shared purchase, money, thanking givers, secret gifts outside the list | excluded by the product |
| More notification event types (booking events and others) and any second, parallel notification mechanism | existing notification stories (see Constraints) |

The settings storage written by this story is filled only by tests and by
the later settings story. No user can change a setting through the product
before WISHENKA-34.

## Main Business Entities

Defined in WISHENKA-22. Used here without change: wish, received quantity,
remaining quantity, promise (open when intended or purchased), occupied
quantity, receipt record (wish, quantity, date, no giver), gifted wish,
archived wish, author (owner, or co-author with the right to edit wishes).

Added by this story, in business terms:

- **Gift notice**: one message to one giver about one receipt act.
- **Notice setting**: whether a user wants gift notices, at user level and,
  overriding it, per list.

## User Stories

- As an author, I record how many units of a wish arrived, so that my list
  shows only what I still want (R-1, R-4).
- As an author of a wish for five units who got two, I want three to stay
  active, so that givers can keep giving (R-1, R-4).
- As an author, I want my received wishes kept apart from deleted ones, so
  that a gift is never mistaken for a wish I dropped (R-4, R-5).
- As a giver with an open promise, I want a notice that the owner received
  the wish, so that I do not buy something no longer needed (R-6).
- As a giver, I want the product not to cancel or change my promise behind my
  back (R-3).
- As a giver, I want to switch this notice off generally or for one list (R-6;
  the screen is WISHENKA-34).
- As a recipient, I want receipt and its refusals to reveal nothing about
  promises, givers or purchases (R-8).

## Functional Requirements

Each ID shows the WISHENKA-22 items it implements in brackets.

### R-1. Recording receipt [FR-1, FR-2.1 to FR-2.3, FR-2.5]

- R-1.1. Only an author of the list may record receipt. A gifter or an
  anonymous caller is refused. (FR-1.1)
- R-1.2. Receipt is accepted only for an active wish on an active list. A
  wish in the archive, a wish on an archived or deleted list, and a wish with
  nothing remaining are refused, each with its own business reason. (FR-1.2,
  CC-9)
- R-1.3. The quantity of one act is at least one and at most the remaining
  quantity. Zero, negative and above-remaining values are refused. (FR-1.3,
  CC-6, CC-7)
- R-1.4. Receipt works for a wish nobody promised. A wish with no stated
  quantity counts as one unit. (FR-1.4, CC-16)
- R-1.5. The act is instant: no confirmation by givers, no giver named by the
  owner. (FR-1.5)
- R-1.6. Several acts add up. After a partial act the wish stays active with
  the reduced remaining quantity. After the act that reaches the requested
  quantity the wish is fully received and leaves the active list. A partial
  act on a wish nobody promised changes no promise and creates no notice.
  (FR-2.1 to FR-2.3, CC-1, CC-19)
- R-1.7. Two authors acting at the same time, and an act racing a promise on
  the same wish, never push received above requested and never lose an open
  promise. The loser gets a readable refusal. (FR-2.5, CC-8)
- R-1.8. A failed act changes nothing: no counter, no record, no notice.

### R-2. Receipt history and existing data [FR-5.4, FR-5.7, CC-19, AR-3]

- R-2.1. Each act is kept as its own dated record with the wish and the
  quantity. A record never carries a giver and is never tied to a promise.
  The total of the records equals the received quantity of the wish.
- R-2.2. A wish that already has received units but no record before this
  story gets one record with an approximate date (AR-3). The approximation is
  stated in the migration notes and is never shown as an exact date. (TD-1.3)
- R-2.3. Receipt history of a list goes with the list when it is purged. The
  behavior between soft deletion and purge, and what «Подаренные» shows for a
  soft-deleted list, is decided at Step 2 and must match FR-5.7. (FR-5.7,
  TD-1.15)
- R-2.4. Receipt history of an archived list stays readable. (FR-5.7)

### R-3. Effect on promises and free quantity [FR-2.4, FR-2.6, FR-3.1 to FR-3.5, FR-3.7]

- R-3.1. Receipt never closes, changes, cancels or marks purchased any
  promise. Only its giver does. Intended and purchased promises are treated
  alike. (FR-3.1, FR-3.5)
- R-3.2. Received plus occupied above requested is a legal state (the
  over-booked state). Open promises stay in the cabinet and in the active
  count until the giver acts. (FR-3.2, FR-3.3, CC-2, CC-3)
- R-3.3. In that state, and for a fully received wish, no new promise is
  accepted and no giver may raise a promise. A giver may lower, cancel, mark
  purchased, or undo purchase. A cancelled promise stays cancelled. (FR-3.4,
  FR-3.6, CC-13)
- R-3.4. Free quantity is requested minus received minus occupied, never below
  zero. It is what any giver may still book. (FR-2.4, FR-3.7)
- R-3.5. Reducing the requested quantity is still refused below received plus
  occupied. This keeps working after receipt. The known disclosure of the
  existing edit form stays as it is and is not changed here. (FR-2.6, CC-12)

### R-4. Gifted, active and archived wishes [FR-3.8, FR-5.1 to FR-5.3, FR-5.7, AR-1, AR-5]

- R-4.1. A wish with received units is shown in «Подаренные» (received part),
  whatever its archive state. A wish with remaining quantity and not archived
  is shown on the active list. An archived wish with remaining quantity is
  shown in the archive with its unreceived part. A fully received wish is
  never in the archive. (FR-5.2, FR-5.3, AR-1)
- R-4.2. Archiving a partly received wish moves only its unreceived part to
  the archive. The received part stays in «Подаренные». Open promises are
  kept. (FR-3.8, CC-10)
- R-4.3. Restoring returns only the remaining quantity to the active list.
  The received part stays where it was. (FR-3.8, CC-11)
- R-4.4. Archiving a fully received wish is refused, and so is restoring a
  wish with nothing remaining, each with a business reason. (FR-3.8)
- R-4.5. Legacy rows that are archived and fully received are brought to the
  derived state: shown only in «Подаренные», never in the archive. Partly
  received archived rows stay archived. The change of stored rows is
  accepted as irreversible and its count is reported. (AR-5, TD-1.3)
- R-4.6. «Active» (not archived and with remaining quantity) means the same
  everywhere in the product: the active list, reordering, counts and every
  other place that depends on it never disagree about which wishes are
  active. (AR-1, TD-1.14)

### R-5. Recipient-safe read data [FR-2.2, FR-3.6, FR-5.4 to FR-5.6, FR-6.3]

- R-5.1. Active list data shows the remaining quantity of each wish.
- R-5.2. «Подаренные» data, for authors only, lists each gifted wish with its
  description, link, price, recipient, received quantity, and its receipt
  dates and quantities. It holds no giver and no promise information, and
  gifters and anonymous callers are refused. It offers nothing to edit, move,
  promise or archive. (FR-5.4 to FR-5.6)
- R-5.3. Archive data shows the unreceived quantity of each archived wish.
- R-5.4. Giver views and the cabinet row tell whether the wish is fully
  received, derived only from received and requested quantity, so they reveal
  nothing about other promises. A giver whose promise is open (intended or
  purchased) on a wish that was then fully received keeps seeing that promise,
  marked as received, until the giver cancels it; the promise itself stays open
  and the wish is out of the active list. (FR-3.6, CC-4)
- R-5.5. A recipient viewing the list before or after receipt sees no booking
  data and no booking marker. (FR-6.3, CC-17)

### R-6. Gift notice to givers [FR-4, AR-4, FR-6.4]

- R-6.1. After each successful act, every giver with an open promise on the
  wish gets one notice, even if holding several promises. Several acts give
  several notices. (FR-4.1, FR-4.5, FR-4.8, CC-5, CC-14)
- R-6.2. Nobody else gets one: not a giver with a cancelled promise, not a
  non-holder, not the person for whom the wish is meant. An owner who holds a
  promise on another wish is a giver there. When nobody promised, no notice is
  created. (FR-4.4, FR-1.4, CC-18)
- R-6.3. The notice says only that the owner marked this wish as received,
  names the wish and the list, and invites the giver to review the promise.
  It gives no quantities, no other giver, no total, no hint that the promise
  is excess, no hint of others' purchases. (FR-4.2, FR-4.3, FR-6.4)
- R-6.4. The notice is controlled by the setting at list level, else at user
  level, else on. List level wins in both directions. The setting that applies
  at the moment of the act decides, and a giver who switched the notice off is
  not messaged. The decision stays auditable. (FR-4.6, AR-4)
- R-6.5. The notice is recorded atomically with the receipt: either both
  exist or neither, so no accepted receipt loses its notice, even if the
  system stops right after the act. Delivery happens only after the receipt is
  final. A failed delivery (blocked bot, network, limits) never changes,
  fails or delays the receipt. A failed delivery is retried at most a stated
  maximum number of times (the number is fixed at Step 2 and documented), then
  the notice ends in a final failed state that stays visible for diagnosis.
  (FR-4.7, CC-15)
- R-6.6. Delivery is at least once: a notice is never silently lost, and in
  rare failure cases a giver may get a duplicate. The duplicate is bounded:
  at most one extra notice per giver per act. (FR-4.7)
- R-6.7. This story ships the storage and lookup of settings only. It adds no
  way for a user to change a setting. (see Out of scope)

### R-7. Web access [FR-1, FR-5, FR-6.2]

- R-7.1. The receipt and the read data of R-5 are reachable through the web
  interface of the product with the same authentication and protection against
  forged requests as other changes, so that WISHENKA-24 can build on them.
  Exact paths and data shapes are fixed at Step 2.
- R-7.2. Refusals use a closed set of business reasons with fixed wording.
  The wording never states or implies how many units are booked. The refusal
  for an above-remaining quantity may name only the remaining quantity. A busy
  lock gives the same retryable answer as the promise actions. (FR-6.2)

### R-8. Surprise and privacy [FR-6, invariants 1 and 4 of `specs/00-high.md`]

- R-8.1. The receipt answer, every refusal, the «Подаренные» data and the
  notice show no giver, no booked quantity, and no purchase. (FR-6.1 to
  FR-6.4)
- R-8.2. Logs of the receipt and of the notice path name no giver on any
  stream the owner or a recipient can reach. Rules for log content are in
  `ai-tasks/WISHENKA-22/50-observability.md` and are applied at Step 6.
- R-8.3. The check that today guards the surprise
  (`tests/test_surprise_role_context.py`, which asserts that notification
  tables and log words do not exist) is **replaced by a stronger check**, not
  weakened or deleted: notification storage may exist, but the walk of a
  recipient creates no notice for the owner and shows no promise. (TD-1.4)

## Non-functional Requirements and Constraints

- Language: Python 3.12+. Follow `lsr-python`.
- Existing test suite stays green, except the change of R-8.3, which is
  intended. No other existing test is weakened.
- Surprise secrecy invariants of the product hold for every new artifact
  (R-8).
- Consistency: concurrent acts keep received at most requested (R-1.7).
- Delivery: a notice never blocks, changes or fails the receipt (R-6.5).
- Data safety: migration of existing rows is repeatable on a copy, and its
  irreversibility is documented (R-2.2, R-4.5).
- Tests follow the repository rules (`do-testing`: pytest, timeouts, bounded
  waits). Notice tests never contact the live messenger.
- The story keeps one notification mechanism for the product. It must agree
  with the existing story WISHENKA-60 and not build a parallel one (TD-2.1,
  to settle at Step 2).
- The story stays one Jira ticket for now; the basis is in Q3. Size is
  controlled by the minimum above: one event type, no settings screen.
- Operations: the metrics named in WISHENKA-22 are derived from logs. No
  exporter (WISHENKA-84).

## Definition of Done

Every R-ID is verifiable through at least one item below.

1. An author can record partial and full receipt through the web interface;
   a partial act on a wish nobody promised changes no promise and creates no
   notice; refusals follow R-1 and R-7 (R-1.1 to R-1.8; corner cases 1, 6, 7,
   8, 9, 16, 19).
2. Receipt never changes a promise; the over-booked state is legal and
   blocks only new and raised promises; a promise open on a fully received
   wish stays open, visible to its giver with the «received» marker until the
   giver cancels it, while the wish leaves the active list and the giver is
   notified (R-3.1 to R-3.5, R-5.4; corner cases 2, 3, 4, 12, 13).
3. «Подаренные», the active list and the archive are three views over one
   wish, with partial archive and restore working, «active» meaning the same
   in every place, and legacy archived rows handled (R-4.1 to R-4.6; corner
   cases 10, 11).
4. The read data is recipient-safe: the active list shows the remaining
   quantity of each wish; «Подаренные» data, for authors only, lists each
   gifted wish with its receipt dates and quantities and no giver or promise
   information, offers nothing to edit, move, promise or archive, and refuses
   gifters and anonymous callers; the archive shows the unreceived quantity of
   each archived wish (R-5.1 to R-5.3).
5. Receipt history is dated, has no giver, and existing received wishes have
   an approximate record, with the approximation stated in the migration
   notes (R-2.1, R-2.2).
6. The history of a list is removed together with the list on purge, and the
   history of an archived list stays readable (R-2.3, R-2.4).
7. A giver with an open promise gets one notice per act, by the rules of
   R-6, with settings at both levels and default on; the notice recorded
   with the receipt is never lost; failed delivery leaves the receipt intact;
   the maximum number of delivery attempts exists, is a stated number and is
   documented; a duplicate notice, if provoked, is at most one extra per
   giver per act (R-6.1 to R-6.6; corner cases 5, 14, 15, 18).
8. The product offers no way to change a notice setting; only storage and
   lookup exist (R-6.7).
9. Refusals use a closed set of business reasons with fixed wording that
   never states or implies booked quantity; a busy lock gives a retryable
   answer, the same as the promise actions (R-7.2). Receipt and read data
   are reachable through the web interface with the same protection as other
   changes (R-7.1).
10. No artifact reveals a giver or booked quantity to the owner or a
    recipient, logs included; the old surprise test is replaced by the
    stronger check (R-5.5, R-8.1 to R-8.3; corner case 17).
11. All 19 corner cases of WISHENKA-22 are covered across items 1 to 10 by
    automated tests; the existing suite is green.
12. Out-of-scope items are untouched and recorded as owned by their tickets.

## Task Description

The product stored «received» as a number but gave no way to record it,
and none of the consequences. This story adds the owner's act and its
consequences on the backend: history, archive separation, free-quantity
rules, and the notice to givers.

Carried follow-ups (Group 1 of WISHENKA-22 `60-tech-debt.md`), to be settled
in the named step:

- TD-1.1, TD-1.3, TD-1.14: this file (R-6, R-2, R-4).
- TD-1.2: the split decision is recorded here as no split, minimum scope,
  pending confirmation by the product owner (see Q3). Action: a comment on
  WISHENKA-23, to be made by the orchestrator at close.
- TD-1.17: sequencing and contract with WISHENKA-24 (co-owned). The contract
  is fixed at Step 2 and Step 4; a comment on both tickets is a Step 2 and
  close-out item.
- TD-1.4: R-8.3. TD-1.10: tests at Step 3.
- TD-1.5, TD-1.6, TD-1.7, TD-1.8, TD-1.13, TD-1.15: Steps 2 and 6 (event
  name, presence in logs, notice retention and counters, summary window,
  metrics from logs, soft delete).
- TD-1.12: Step 8, planned notes in `doc/dev` become current.

## Q&A

- Q1. Why does the story exist, since the counter already exists?
  A. The owner cannot yet use it: there is no safe way to record receipt, no
  history, no separation from deleted wishes, and no notice. The business aim
  is an honest list and givers who do not buy what already arrived.
- Q2. Is the settings screen part of the minimum?
  A. No. Only storage and lookup of both levels with default on. The screen
  is WISHENKA-34 (WISHENKA-22 architecture Q2).
- Q3. May a story this large stay one ticket?
  A. For now, yes. The WISHENKA-22 architecture left the split to the product
  owner. The orchestrator run is not authorised to split a Jira ticket, so the
  story keeps its scope, cut to the minimum notification infrastructure: one
  event type, no screen, no exporter, no undo. This decision should be
  confirmed by the product owner (TD-1.2).
- Q4. Are open points from WISHENKA-22 closed here?
  A. No. Assumptions A to D and Q6, Q8, Q11, Q12 stay open and are owned by
  WISHENKA-154. The story builds on the stated assumptions.
- Q5. Does the story change today's behavior for the archive?
  A. Yes, for wishes with received units only: archive and restore act on the
  unreceived part (R-4). A wish with no received units behaves as today.
- Q6. What replaces the old surprise test?
  A. A walk that allows notification storage to exist and checks that no
  notice and no promise data reach the owner or a recipient (R-8.3).
