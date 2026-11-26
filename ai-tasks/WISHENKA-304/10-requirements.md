# WISHENKA-304: Deterministic order when viewing times match

## Goals

A viewer should be able to trust the order of their viewing history. The history is already
shown most recent view first. That order is fixed only by the view time. When two entries
share that time, which one appears first can change from one reading to the next. The list
then feels unreliable, and a check of that order can pass or fail by chance.

A repeated view of the same wishlist keeps the same history entry and moves it to the latest
place in the history. The entry's lasting identity therefore does not say which view is
newer. Equal view times must follow the sequence in which views were recorded.

This is follow-up debt from WISHENKA-292 (item 2). While that task was being checked, one
run in about thirteen showed a history order that did not match the expected sequence. Two
hundred eighty later rounds did not reproduce it, so no separate defect was proven. Equal
view times remain a real way for the order to change. This task makes that case
deterministic and covers it with a regression that freezes the view time.

Implementation language: Python.

## User Stories

- As a viewer, I want the wishlist I recorded later to appear before one I recorded earlier
  when both have the same view time, so the top of my history is the view I made last.
- As a viewer, I want a repeated view of a wishlist to count as my newest view of that list,
  including when the new view time is the same as other entries, so opening it again brings
  it forward.
- As a viewer, I want the same order when my history is read back from the stored history as
  when it is still only the current session's list.

## Definition of Done

The task is done when all of the following hold:

1. When view times differ, the history stays most recent view first. A later view time always
   ranks ahead of an earlier one.
2. When two or more entries of the same viewer share a view time, their relative order is the
   same on every read. The view recorded later in that viewer's recording sequence appears
   before the view recorded earlier.
3. The recording sequence is the entry's position in that viewer's history list after the view
   is recorded, or a counter that increases by one on every recorded view. A repeated view
   moves the existing entry to the newest place in that sequence. The entry's lasting identity
   is not a freshness order and is not the tie-break.
4. A repeated view still updates the one existing entry for that viewer and wishlist. It does
   not add a second entry. If the repeated view's time equals other entries, that wishlist
   appears ahead of entries recorded earlier in the sequence.
5. The same tie-break applies to the history the viewer is shown from the current session and
   to the history read back from the stored history.
6. When more entries share a view time than the history can show, which of those entries are
   shown follows the same tie-break: entries recorded later in the sequence are kept ahead of
   entries recorded earlier. The existing limit on how many entries are shown does not change.
7. A regression freezes the view time so at least two entries share it. It checks a pair of
   distinct wishlists recorded in a known order, and a repeated view that does not move the
   clock. It checks both the session history and the stored history. The asserted order is the
   recording sequence, newest recording first, and does not change between runs.
8. One viewer's sequence does not change another viewer's history.
9. What is recorded, who may see an entry, clearing the history, and what each entry shows
   stay as they are today. Only the order among equal view times, and the choice of which
   equal-time entries remain inside the existing limit, change.

## Task Description

Viewing history lists wishlists a viewer recently opened, most recent view first. Ordering
uses only the view time. Entries that share a view time have no agreed order.

In the session list, a repeated view keeps the old entry and moves it to the end of the
history. That end means "recorded later." The entry's lasting identity stays the one it had
when it was first created. Treating that identity as freshness would rank a repeated view as
older than a first view that happened to receive a later identity, even when the times match
and the repeat is the newest recording.

The stored history has the same gap. It orders by view time alone, so equal times are not a
stable order after the history is saved and read back.

The business outcome is one agreed order for that case, on both paths, proven while the view
time is held still.

### Business entities

- **Viewer:** the person whose viewing history is listed.
- **History entry:** one viewer's record of one wishlist. It has a view time and a lasting
  identity. A repeated view keeps that identity, refreshes the view time, and counts as a
  new, later recording.
- **Viewing history:** that viewer's ordered entries, most recent view first, bounded by the
  existing limit. The same order rules apply to the session history and to the stored
  history.
- **Recording sequence:** the order in which views were recorded for one viewer. Each new
  view, including a repeat, takes the newest place. That place is the entry's position in
  the history list after the view is recorded, or a counter that only increases. It is not
  the entry's lasting identity.

### Functional requirements

1. Keep most-recent-first order by view time whenever the times differ.
2. Break equal view times by recording sequence, newest recording first. Use list position
   or a counter that increases on every recorded view, including a repeat. Do not use the
   entry's lasting identity.
3. Apply that order when listing the session history and when listing the stored history.
4. Apply that order when choosing which equal-time entries stay inside the existing limit.
5. Treat a repeated view as one entry moved to the newest place in the sequence.
6. Prove the equal-time cases with a regression that freezes the view time, on the session
   history and on the stored history, including a repeated view.

### Non-functional requirements

- The order for a given set of views is repeatable. Two reads with the same view times and
  the same recording sequence return the same order.
- The rule is limited to ordering and to which equal-time entries fit in the existing limit.
  It does not add a new screen or a new viewer action.

### Constraints and assumptions

- The history remains personal to one viewer.
- Equal view times means the recorded times compare as the same instant. This task does not
  redefine how close two different times must be to count as equal.
- The existing limit, access rules, clear action, and entry contents stay in force.
- The lasting identity of an entry may stay stable across a repeated view. Callers that
  already rely on that identity still can. They must not read freshness from it.
- The rare order mismatch from WISHENKA-292 is covered by the frozen-time regression.
  Reproducing that exact one-in-thirteen run is not required.
- Out of scope: access rules for history, duplicate event records, visual design of the
  history screen, and any change to order when view times differ.

## Q&A

**Why is a tie-break needed if different view times already sort correctly?**
Two views can be stored with the same time. Without a second rule, the list can change
between reads, and a check of that list can pass or fail by chance. WISHENKA-292 saw one
such mismatch in about thirteen runs; two hundred eighty later rounds did not show it
again. The product still needs one agreed order for that case.

**Why is the entry's lasting identity the wrong tie-break?**
A repeated view keeps that identity and moves the entry to the end of the session history.
The identity remembers the first recording, not the latest one. A wishlist opened again
would stay behind a wishlist first opened later, even when the repeat is the newest view
and the times match.

**Why must the stored history follow the same rule?**
The viewer can be shown history that was saved and read back, not only the list still held
for the current session. A stable session order with an unstable stored order would still
show a different list after the history is stored.

**Are there open questions?**
No. The business outcome is a single, repeatable order. The tie-break is the recording
sequence: list position, or a counter that increases on each recorded view, including a
repeat. The entry's lasting identity is not that sequence.
