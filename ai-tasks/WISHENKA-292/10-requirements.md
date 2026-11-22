# WISHENKA-292: Convenient wishlist viewing history

## Goals

A user should quickly return to wishlists they recently viewed and stay in control of the saved
history. Each entry should be easy to recognize, the time of the last view should be clear, and
clearing the history should look like a deliberate action that does not compete with the content.
This is part of the epic WISHENKA-287 (a single light and recognizable Wishenka design) and
continues the shared visual identity established by WISHENKA-288, 289 and 290.

Implementation language: Python, JavaScript, HTML and CSS.

## Task Description

The viewing history is a personal section of the Mini App, reachable from the home screen, that
lists wishlists the authenticated user recently opened, most recent first, and lets the user clear
it (product specification `in-docs/spec.md` section 8.2 and `specs/00-high.md`). This task
improves how the section looks and reads. It preserves the existing behavior: which wishlists are
recorded, ordering, the existing limit on the number of entries, navigation back, and the
result of clearing. It does not introduce new data about entries, search, filtering, removal of a
single entry, a new retention rule, or a new way to authenticate. A reference mockup is attached
to the Jira ticket; where it differs from these requirements, the requirements and the existing
product rules decide.

### Business entities

- **History entry:** a previously opened wishlist as remembered for one viewer, with the
  wishlist title (or a neutral untitled label), the time of the viewer's most recent view and,
  where it applies, the viewer's relation to the list (for example owner, participant or saved
  favorite).
- **Viewing history:** the viewer's private, ordered collection of entries, most recent view
  first, with a bounded number of entries.
- **Clearing the history:** a viewer-initiated action that removes every entry of that viewer
  and affects nothing else (the wishlists themselves, favorites and other users' histories remain).

### Functional requirements

1. Present each entry as a distinct, visually separated item so that neighboring entries are
   easy to scan and tell apart. An entry shows the wishlist title as its primary element and the
   last-viewed time as secondary, supporting information, including the viewer's relation to the
   list when it is already shown today. The existing information is not removed.
2. Show the wishlist title prominently and let long or multi-word titles remain readable,
   without breaking the layout. An untitled wishlist still shows a meaningful label.
3. Show the last-viewed time in a clear, localized and human-readable form, visibly tied to its
   entry and visually quieter than the title. Entries stay in most-recent-first order.
4. Make opening a list from history easy: the whole entry or an obvious, clearly labeled action
   opens that wishlist in one step, with an accessible name that includes the wishlist title.
   Opening a list continues to record the view as before.
5. Keep a way to return to the home screen from the history screen, consistent with the
   other screens that follow the shared visual identity.
6. Show the clear-history action only when there is something to clear. It must be noticeable
   and recognizable as a destructive-style action, yet visually secondary to the list of entries
   and positioned so that it is not triggered by accident while scanning or opening entries.
   Clearing must feel deliberate: the user is made aware that all history is removed (for example
   through an explicit confirmation or comparable safeguard), and can back out without any change.
7. After clearing, clearly show the outcome: the history becomes empty and a confirmation
   message is perceivable. If clearing fails, explain it and leave the displayed history
   consistent with what is actually stored, so the user can retry; an unsuccessful action is never
   presented as success.
8. When the history is empty, explain it with a clear, friendly message that says that the
   section fills as the user opens wishlists, and give an obvious way onward (for example back to
   home or to the user's lists). The empty state looks intentional and is not an empty screen.
   While loading and after a load failure, provide understandable feedback and a way to retry or
   leave.
9. Provide equivalent meaning and complete labels, messages, confirmations and errors in Russian
   and English, following the viewer's selected language; date and time formatting follows that
   language.
10. Keep the section visually coherent with the shared Wishenka identity (colors, typography,
    spacing, cards and buttons) used on the home screen, wishlist detail and settings, so that
    familiar functionality remains familiar.

### Non-functional requirements and constraints

- The screen must remain usable on a narrow phone viewport, in the Telegram Mini App and a
  normal mobile browser, with long Russian and English titles and labels, without horizontal
  scrolling or overlapped controls. Touch targets must be comfortable for a finger.
- Interactive elements must be distinguishable beyond color, operable by keyboard and assistive
  technology, show a visible focus, and have understandable names. Outcomes of actions (loading,
  cleared, failure) must be perceivable without relying only on a visual change. Text contrast
  must remain readable.
- Privacy: history is private to its viewer. A person sees and clears only their own history.
  A deleted wishlist is not offered as an entry. Entries show only the wishlist title, the
  last-viewed time and the viewer's relation to the list, and contain no reservation or purchase
  information. The surprise invariant is preserved. Access checks are unchanged by this task.
- Existing rules remain unchanged: which views are recorded, the ordering, the bound on
  the number of entries, what clearing deletes, authorization and the deleted wishlist behavior.
  No new performance target is imposed; ordinary interaction gives timely visible feedback.

## User Stories

- As a user, I can scan my viewing history and tell entries apart at a glance, so I recognize
  the list I am looking for.
- As a user, I can read each list's title and when I last viewed it without effort, so I can
  judge how recent it is.
- As a user, I can open the list I need from the history in one step, so I return to it quickly.
- As a user, I can clear my history through a noticeable but unobtrusive and deliberate action,
  so that I control the saved data without clearing it by accident.
- As a user opening the section for the first time, I see a clear explanation of the empty
  history, so I understand that nothing is wrong.
- As a Russian or English speaking user on a phone, I see the same complete experience in my
  language, so I can use it comfortably.

## Definition of Done

1. Entries are visibly separated and easy to scan; neighboring entries are easy to tell apart,
   including with long titles and on a narrow phone viewport in both languages.
2. The title is the primary element and the last-viewed time is a legible secondary element
   in the user's language; order remains most recent first.
3. Any entry can be opened in one step by a clearly labeled control or area, which keeps
   recording the view, and the viewer can go back to home.
4. The clear-history action appears only for a non-empty history, is noticeable and distinctly
   marked, does not dominate the list, is made deliberate, and can be cancelled without change.
5. Successful clearing leaves an explained empty history with a perceivable confirmation; failed
   clearing is explained, retryable and leaves a consistent display.
6. An empty history shows a clear explanatory message and a way onward in both languages;
   loading and failure states are understandable.
7. All texts exist in Russian and English with the same meaning; the screen is keyboard and
   assistive-technology operable with visible focus, with no horizontal overflow on phone width.
8. Appearance is consistent with the shared Wishenka identity; existing history behavior
   (recording, order, limit, clearing scope, access rules) and other journeys still work.
9. No history content discloses protected reservation or purchase information, and deleted
   wishlists are not listed.

## Q&A

- **Why this change?** The Jira business goal: the user quickly returns to previously viewed
  wishlists and controls the saved history. The user value is recognizing a list, understanding
  when it was viewed, and seeing clearing as a deliberate action.
- **What is the source of truth for inherited behavior?** `specs/00-high.md` (personal sections,
  privacy priority), `in-docs/spec.md` sections 8.2 and the Mini App navigation description, and
  `doc/dev/wishlists.md` for the existing history limits. This task does not replace those rules.
- **Is a new capability requested, such as removing a single entry, search or retention
  settings?** No. The scope is clarity, scanning and safe use of the existing history and its
  single clear action.
- **Is a confirmation required before clearing?** The ticket asks that clearing looks like a
  deliberate action; the exact safeguard (confirmation step or equivalent) is left to the next
  steps, provided it is explicit, cancellable and accessible.
- **What if the mockup `WISHENKA-292_History.png` differs?** The mockup could not be reviewed in
  this step. It is a visual guide, to be checked against these requirements in later steps.
