# WISHENKA-305: One log line per viewing-history event

## Goals

People who read viewing-history logs need one record per action. Today, recording a view
can write the view-recorded event twice, and listing history can write the view-listed
event twice. Counts of those events then look larger than the number of actions. A
refusal to record history because the wishlist was deleted can also be told with the
favorites denial name, which makes a history refusal look like a favorites refusal.

This is follow-up debt from WISHENKA-292 (item 3). The business outcome is trustworthy
log lines: each of those actions writes its event once, and a history refusal for a
deleted wishlist is not labeled as a favorites denial. Access rules, history order, and
what the person sees stay as they are.

Implementation language: Python.

## User Stories

- As someone reading viewing-history logs, I want one view-recorded event when a view is
  recorded, so a count of that event matches the number of recordings.
- As someone reading viewing-history logs, I want one view-listed event when history is
  listed, so a count of that event matches the number of listings.
- As someone reading viewing-history logs, I want a refusal to record history for a
  deleted wishlist to use the history denial event, or to omit a misnamed favorites
  event, so that refusal is not counted as a favorites denial.
- As someone who already checks the service-level denial for recording a view of a
  deleted wishlist, I want that denial to remain, so those existing checks still see it.

## Definition of Done

The task is done when all of the following hold:

1. Recording a view writes the view-recorded event once, not twice.
2. Listing history writes the view-listed event once, not twice.
3. When history is refused because the wishlist was deleted, the history path does not
   emit the favorites denial event. It uses the history denial event, or no misnamed
   favorites event.
4. The favorites denial that already happens when recording a view of a deleted wishlist
   stays. That one is the service-level denial, and existing checks count it. It is not
   removed.
5. Access rules, history order, and what the person sees do not change. Only the log
   lines change.
6. The facts those events already carry stay the same. A view-listed event still reports
   how many entries were listed. These lines still omit wishlist titles and secrets.
7. Clearing history, and favorites actions that are not this deleted-wishlist view
   denial, keep the log lines they already have.

## Task Description

Viewing history records that a person opened a wishlist, and later lists those recent
views. Each of those actions is meant to leave one log event: view-recorded when a view
is stored, view-listed when the history is read back.

The same event is written more than once for one action. A later count of view-recorded
or view-listed events then overstates how many recordings or listings happened. Clearing
history was already reduced to one event and is not part of this change.

When a view cannot be recorded because the wishlist was deleted, the history refusal
must not be reported as a favorites denial. The history path uses the history denial
event, or it writes no event under the favorites denial name. The service-level
favorites denial that already happens for that deleted-wishlist view, and that existing
checks count, stays. Removing the extra success lines must not drop that denial.

The person still receives the same refusal, still sees the same history, and still sees
it in the same order. Who may record or list history does not change.

### Business entities

- **Viewer:** the person whose view is recorded or whose history is listed.
- **Wishlist:** the list being viewed. A deleted wishlist cannot be recorded into
  history.
- **View-recorded event:** the log line that a view was stored. One recording produces
  one such line.
- **View-listed event:** the log line that history was listed, including how many
  entries were returned. One listing produces one such line.
- **History denial event:** the log line that history was refused because the wishlist
  was deleted.
- **Favorites denial event:** the log line that names a favorites refusal. The history
  path does not use this name for a deleted-wishlist history refusal. The service-level
  denial already counted when a view of a deleted wishlist is recorded remains.

### Functional requirements

1. Write the view-recorded event once per recorded view.
2. Write the view-listed event once per history listing.
3. On a history refusal for a deleted wishlist, do not emit the favorites denial event
   from the history path. Use the history denial event, or emit no misnamed favorites
   event.
4. Keep the service-level favorites denial that already happens when recording a view of
   a deleted wishlist. Existing checks count that denial. Do not remove it.
5. Leave access rules, history order, visible history, and the refusal the person
   receives unchanged.

### Non-functional requirements

- A count of view-recorded events equals the number of successful recordings. A count of
  view-listed events equals the number of listings.
- Log lines for these events stay free of wishlist titles and secrets.
- No new viewer action and no new screen.

### Constraints and assumptions

- This task changes log lines only.
- The service-level denial for a deleted-wishlist view is the one existing checks
  already count. It is distinct from a second, misnamed favorites event on the history
  path.
- Out of scope: who may view or list history, history order, what each entry shows,
  clearing history, and favorites behavior other than preserving that counted denial.

## Q&A

**Why change the logs if the person already sees the right history?**
The screen can be right while the log count is wrong. Two identical events for one
recording or one listing make later counts look like twice the activity. A history
refusal named as a favorites denial is counted as the wrong kind of refusal.

**Why keep a denial when the goal is fewer log lines?**
The extra lines are the repeated view-recorded and view-listed events, and a favorites
name on the history path. The service-level denial for recording a view of a deleted
wishlist is already the denial existing checks count. Removing it would drop a record
those checks require.

**Does the person see anything different?**
No. Access rules, history order, the refusal for a deleted wishlist, and the history
itself stay as they are. Only the log lines change.

**Are there open questions?**
No. One view-recorded event per recording, one view-listed event per listing, no
favorites denial name on the history refusal, and the counted service-level denial
stays.
