# WISHENKA-294: Comfortable and reliable experience on all key screens

## Goals

A user should be able to use the redesigned Wishenka comfortably and with confidence in familiar
conditions: on a phone, in the Telegram Mini App and in a normal mobile browser, in Russian or
English, with short and long texts. The user always understands whether an action is in progress,
done or failed; text, actions and hints are easy to perceive. This is the closing quality story
of the epic WISHENKA-287 (a single light and recognizable Wishenka design) and of the sprint goal
(key scenarios are visually coherent, light and convenient, familiar functionality and
multilingual clarity are preserved). It builds on the shared visual identity (WISHENKA-288), the
home overview (289), the wishlist detail workspace (290), personal settings (291) and the
viewing history (292).

Implementation language: Python, JavaScript, HTML and CSS.

## Task Description

This is a cross-cutting quality story, not a new screen. The earlier stories each verified their
own screen. This task checks the key scenarios as one product, finds where phone layout, long
text, feedback or readability is missing or unproven, and closes those gaps. It introduces no new
features, no new data and no new rules; familiar behavior, privacy and the surprise invariant
(`specs/`, `in-docs/spec.md`) stay unchanged, and Russian and English stay equivalent.

### Key screens and scenarios in scope

Screens of the Mini App (also opened in a normal mobile browser) and of the web pages that share
its identity:

1. **Home overview:** sections of the user's lists, favorites, create-wishlist action, entry to
   history and settings, empty sections, deleted/restore state.
2. **Create and edit wishlist:** the create action, wishlist settings (title, description and
   related fields) with save, cancel and failure.
3. **Wishlist detail with items:** title and description, item cards (expanded and collapsed),
   members and sharing controls, quick add, reorder, archived and gifted sections.
4. **Item dialogs:** add, edit, archive, reserve or release, and gift receipt dialogs (mark,
   correct, cancel) with quantity controls and their refusal/failure messages.
5. **Personal settings:** language, birth date and reminders, notifications (global and per
   wishlist), account deletion with its preview and confirmation.
6. **Viewing history:** list of entries, open, clear with confirmation, empty, loading, failure.
7. **Sharing and public view:** share dialog (copy link, roles), public wishlist view, invitation
   preview, unavailable-link page.
8. **Reservations cabinet:** the user's own reservations and received gifts view.
9. **Unavailable states:** deleted or inaccessible wishlist, expired or invalid link, failed
   start (invalid start parameter).

### Business entities

- **Screen state:** one of loading, empty, content, success, failure, or in-progress for a user
  action, as the user perceives it.
- **User action:** a familiar operation (open, create, edit, reorder, reserve, mark received,
  change a setting, clear history, share) with an outcome the user must be able to recognize.
- **Viewing context:** the combination of device width (narrow phone through desktop), host
  (Telegram Mini App or browser), language (Russian or English) and text length.

### Functional requirements

Each acceptance criterion of the ticket is restated as observable behavior on the screens above.

1. **Phone layout without horizontal scrolling (criterion 1).** On a narrow phone width (from
   320 px up) every key screen fits the width: the page does not scroll sideways, no content is
   cut off or hidden behind another element, and no control is pushed outside the visible area.
   Primary actions of a screen (create, add item, save, confirm, cancel, share, open, clear,
   back) stay visible and reachable without hunting; they are not covered by fixed bars,
   keyboards' neighbors or overlapping panels. Dialogs fit the screen and remain usable when
   content is taller than the screen.
2. **Long titles and texts (criterion 2).** Long wishlist titles, item names, descriptions,
   notes, member names and links, and the longer of the Russian and English labels, wrap or are
   shown in full without overlapping neighboring controls, without breaking the card or dialog
   and without hiding the action next to them. A single very long word or a link does not widen
   the page. Text that is shortened for space must still be reachable in full elsewhere on the
   screen. Pluralized and dated texts read correctly in both languages.
3. **Visual feedback (criterion 3).** For every key action the user can tell the state:
   - *Waiting:* while data loads or an action is processed, a visible and announced waiting
     indication is shown, and the triggering control cannot be used twice by accident.
   - *Empty:* an empty section or list explains why it is empty and, where it fits, offers the
     way onward; it never looks like a broken screen.
   - *Error:* a failed load or action is explained in the user's language, is not shown as
     success, leaves the screen consistent with what is actually saved, keeps the user's input
     where this is already the case, and offers a retry or a way out.
   - *Success:* a completed action shows a visible and announced confirmation or an
     unambiguous change of the screen.
   Feedback is perceivable without relying on color alone and is available to assistive
   technology. Feedback of one action does not stay on screen as stale or contradictory text
   after the situation has changed.
4. **Readable text and distinguishable controls (criterion 4).** Body, secondary and hint text
   have sufficient contrast and size on the light canvas and in the dark theme where the
   product supports it. Controls are large enough for a finger (at least 44 by 44 px, the
   convention already used in the product), are spaced so neighboring controls are not hit by
   accident, and are visibly different from plain text and from each other (primary versus
   secondary versus destructive). Interactive elements have a visible keyboard focus and an
   understandable name. Text does not become unreadable when the user enlarges the browser text
   size.
5. **Familiar actions keep working (criterion 5).** After the quality fixes, familiar actions
   still behave as before: creating, opening, editing, archiving and restoring lists; adding,
   editing, reordering, reserving and receipt marking of items; changing settings and
   notification preferences; viewing and clearing history; sharing and opening shared links; and
   navigation between home, a list, settings and history with a way back from each.
6. **Consistency across screens.** The same state (loading, empty, error, success) looks and
   reads alike on different screens, using the shared Wishenka identity. A user who learned how
   feedback looks on one screen recognizes it on another.
7. **Language parity.** Every message added or changed by this task exists in Russian and
   English with the same meaning and follows the viewer's selected language, including
   messages for waiting, empty, error and success states.

### Non-functional requirements and constraints

- No new features, data, entities, access rules, retention rules or authentication methods; this
  task changes how existing behavior looks, reads and reports its state.
- Privacy and the surprise invariant are unchanged: no new text, error, empty state, hint or
  announcement may reveal reservation or purchase information to the list owner, and no
  message may expose the content of private or deleted lists to an unauthorized viewer.
- Must work in the Telegram Mini App and in a normal mobile browser, and keep working for the
  server-rendered pages (wishlist detail, share, settings, cabinet, invitation) as for the
  script-rendered Mini App screens.
- Existing observable hooks that browser tests rely on are not removed without replacement; the
  existing test suite stays green apart from known pre-existing failures.
- No new performance target; ordinary interaction gives timely visible feedback.

## User Stories

- As a phone user, I can complete every key scenario without scrolling sideways or losing an
  important button, so I use Wishenka comfortably one-handed.
- As a Russian or English speaking user, I can read long titles and descriptions without them
  breaking the screen, so my own words never make the app hard to use.
- As a user, I always see whether my action is in progress, done or failed, so I know whether to
  wait, continue or try again.
- As a user opening an empty section, I understand that it is empty and what to do next.
- As a user with imperfect eyesight or a bright screen, I can read text and tell buttons apart
  without effort.
- As a returning user, I find my lists, settings and history working as before after the
  redesign, so I do not have to relearn them.
- As a Telegram Mini App user, I get the same comfort as in a mobile browser.

## Definition of Done

1. On every screen of the list above no horizontal scrolling appears at 320 px, 360 px and
   375 px, and at least one wider phone width, in both languages; important actions stay
   visible and unobstructed.
2. Long Russian and English titles, descriptions, names and links do not overlap controls or
   widen the page on any listed screen, including dialogs and cards.
3. Each listed screen and action shows clear feedback for waiting, empty, error and success as
   defined in requirement 3; no failure is presented as success; duplicate submission is
   prevented while an action is pending.
4. Text and secondary hints are readable, controls are at least 44 by 44 px and distinguishable,
   keyboard focus is visible, and feedback is available to assistive technology.
5. Familiar actions with lists, items, settings, history, sharing and reservations work as
   before; navigation back is available from every screen.
6. All texts added or changed exist in Russian and English with the same meaning.
7. Privacy and the surprise invariant are verified unchanged: no new text discloses protected
   reservation or purchase data.
8. A cross-screen verification exists that covers the phone-fit, long-text, feedback and
   touch-target requirements for all listed screens, and the existing tests still pass.

## Q&A

- **Why this change?** Jira business goal: the user comfortably and confidently uses the
  redesigned Wishenka on a phone and in the Telegram Mini App. User value: the interface stays
  understandable with different text lengths and screen sizes, the user always knows the state
  of an action, and text and controls are easy to perceive.
- **Is a new screen or capability requested?** No. It is a quality pass over the screens
  redesigned in 288 to 292 and the other key screens. Findings that need new functionality are
  out of scope and become separate follow-ups.
- **Which screens are the key ones?** Those listed in "Key screens and scenarios in scope",
  taken from the templates `wishenka/web/templates` (base, wishlist detail, settings, share,
  invitation preview, reservations cabinet, item partials) and the script-rendered screens in
  `wishenka/web/static/miniapp.js` (home, history, wishlist detail, public view, invitation).
- **What already exists as verification (from the current tests)?**
  - Phone width, overflow and touch targets: history (`tests/test_history_screen_browser.py`,
    320 and 375 px), settings (`tests/test_personal_settings_browser.py`, 320 and 375 px), home
    (`tests/test_home_overview_browser.py`, 412 and 360 px), wishlist detail
    (`tests/test_wishlist_detail_browser.py`, 360 and 412 px), receipt and edit dialogs
    (`tests/test_receipt_accessibility_browser.py`, 390 px), invitation link button
    (`tests/test_visual_identity_browser.py`). Criterion 1 is therefore covered per screen, but
    not at one common width set and not for create/edit wishlist dialogs, share dialog,
    public view, cabinet, unavailable states and item add/archive dialogs.
  - Long text: long Russian title in settings (`test_personal_settings_browser.py`), title
    clipping on home (`test_home_overview_browser.py`), long titles in history (history test).
    Not verified: long item names, descriptions and notes in item cards and dialogs, long
    member names, long links in the share dialog and public view, and long English text.
  - Feedback: history (loading, empty, error with retry, cleared; history test), settings
    (failed update, ambiguous state, pending deletion; settings test), home (empty states,
    deleted/restore), detail (refresh failure, retry), receipt dialogs (refusal, busy, second
    tap; `test_receipt_modal_browser.py`). Not verified uniformly: create-wishlist failure
    and waiting on home, item add/edit/archive failure and waiting, share/copy confirmation,
    public view and cabinet loading/empty/error states.
  - Readability and controls: contrast and focus (`tests/test_visual_identity_browser.py`,
    `tests/test_receipt_theme_browser.py`), touch targets on the screens above. Not verified:
    text contrast of hints and secondary text on all screens, and behavior with enlarged text.
  - Familiar actions (criterion 5): covered by the existing functional and browser tests of
    lists, items, reorder, receipts, settings and history; a full run after the changes is the
    check.
  Step 2 should design a focused audit of the uncovered items and fixes where the audit finds
  a defect, plus one cross-screen test that checks phone fit, long text and touch targets over
  all listed screens.
- **Is a particular device or minimum width fixed?** The tests already use 320 px as the
  narrowest width; this task keeps 320 px as the minimum.
- **Does "readable text" require a particular contrast value?** Sufficient contrast is
  required; the exact threshold is left to Step 2, provided it is not weaker than the contrast
  checks that the product already applies.
- **Are screenshots or mockups attached?** No attachments on the ticket; existing identity from
  WISHENKA-288 is the visual reference.
