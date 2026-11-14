# WISHENKA-109: Touch-friendly reordering of wishes for Telegram mobile

## Goals

A wishlist owner who uses the product on a phone (the Telegram Mini App on iOS or Android) must
be able to change the order of wishes by dragging a card with a finger, in the same way a
desktop owner does with a mouse.

Business value:

- **Parity across devices**: the product specification states that the order of cards can be
  changed manually (`in-docs/spec.md`, section 5.4). Assumption: the typical user opens the
  product inside Telegram on a phone (not measured; no usage data is available). Today dragging
  works only with a mouse. On a phone the owner can only press
  the up/down buttons, one step at a time.
- **Less effort for long lists**: moving a wish across many positions by single-step buttons
  takes many taps; a finger drag does it in one gesture.
- **No loss of existing ways to reorder**: mouse drag and the up/down buttons stay available.

Source of the task: technical debt recorded in `ai-tasks/WISHENKA-15/60-tech-debt.md`
("HTML5 drag-and-drop only", Jira: WISHENKA-109, type Debt, priority Low, 3 SP).

## User Stories

- As a wishlist owner on a phone in Telegram, I want to drag a wish card to a new position with
  my finger and have the new order saved, so that I can arrange my list without many button
  taps.
- As a wishlist owner on a phone, I want a short tap on a card to still expand or collapse it,
  so that a drag feature does not make reading wish details harder.
- As a wishlist owner on a phone, I want to scroll a long list by swiping as usual, so that
  reordering never blocks normal navigation.
- As a wishlist owner on a desktop, I want mouse drag-and-drop and the up/down buttons to keep
  working exactly as today.
- As an owner who cannot or does not want to drag (assistive technology, keyboard, motor
  limitations), I want the up/down buttons to remain, so that I can always reorder.
- As a visitor of a shared wishlist, I must not be able to change the order of someone else's
  wishes.

## Definition of Done

Acceptance criteria (business behaviour; each is verifiable, by automated checks where feasible
without a browser, otherwise by a documented manual check on a touch device or touch emulation):

1. **Touch reorder works**: on a touch device, the owner can start a reorder from a collapsed
   wish card, without expanding it first, move it over another card, release, and see the new
   order immediately. The way to start is visible or discoverable on the collapsed card: a
   visible dedicated drag area on the collapsed card, or a deliberate gesture on the card such
   as a long press (the mechanism is left to the architecture step). A drag area that is
   visible only after the card is expanded does not satisfy this criterion. The new order is saved for the correct wishlist and the list is
   refreshed from the server result, the same as after a mouse drop. Reorder from an expanded
   card behaves the same way (criterion 15).
2. **Drop position matches the finger**: releasing in the upper half of a target card places the
   dragged card before it; releasing in the lower half places it after it, as with the mouse.
   Releasing on the card itself or outside the list changes nothing and sends nothing.
3. **Visual feedback**: while a card is being dragged by touch, the owner can see which card is
   being moved and where it will land (the same kind of feedback the mouse drag gives, or
   better). The feedback disappears when the gesture ends or is cancelled.
4. **Tap is not a drag**: a short tap on a card summary (outside any dedicated drag area)
   expands or collapses it, exactly as today. A tap never starts a reorder, and finishing a drag never also toggles the card.
   Taps on buttons, links, and form fields inside a card keep their own actions (including the
   up/down, edit, archive, and reservation controls) and never start a drag.
5. **Scrolling is preserved**: a normal vertical swipe over the list, including over collapsed
   cards, scrolls the page and does not reorder anything, unless it starts on the dedicated
   drag area or follows the deliberate start gesture (if the design uses one). Where a long list does not fit the screen, the owner can still reach
   all positions during a drag (for example the page follows the finger near the screen edge) or
   can fall back to the buttons.
6. **Cancelled gestures are safe**: if the touch is interrupted (the system takes over the
   gesture, the app is backgrounded, a second finger touches the screen, the page is
   re-rendered), nothing is saved and the list shows the order stored on the server.
7. **Existing ways keep working**: mouse drag-and-drop on desktop behaves as before
   (WISHENKA-108 acceptance criteria 2-4 still hold); the up/down buttons behave as before,
   including disabled state on the first and last card and the re-rendered list.
8. **Same server contract and validation**: touch reorder saves through the same existing
   reorder action as the mouse drag and carries the full list of active wish ids. The server
   rules do not change: the submitted order must be an exact permutation of the active wishes,
   otherwise it is rejected with the existing error, and the owner sees the order stored on the
   server after reload. Only users allowed to edit the wishlist can reorder; the existing
   permission checks and events are unchanged.
9. **Accessibility fallback**: the up/down buttons stay visible and operable by keyboard and by
   assistive technology, keep their accessible names, and the touch feature does not remove
   keyboard operation of the card toggle (Enter or Space). Reordering never depends on a
   gesture alone.
10. **Visitors cannot reorder**: on the public share page and for any viewer without edit rights
    the cards offer no touch reorder, no drag handle, and no reorder request is possible from
    the page. Card expand/collapse and reservation controls work as before.
11. **Repeated use after list refresh**: after any action that re-renders the list (reorder by
    touch, mouse, or buttons, add, edit, archive, restore), touch reordering works again
    without reloading the page, and does not fire twice for one gesture.
12. **Works in the Telegram Mini App**: acceptance criteria 1-6 hold inside the Telegram mobile
    WebView and in Telegram Web. Swiping must not close or minimise the Mini App window in the
    middle of a reorder gesture, or the remaining limit is documented as a platform limit
    (criterion 14).
13. **No regression**: the full existing automated test suite passes. No change to wish-order
    rules, permissions, reservations, or visual design beyond the drag feedback and any drag
    area.
14. **Documentation matches reality**: developer documentation that today states touch
    reordering relies on the move buttons is updated to describe the new touch behaviour and
    its limits, including any platform limit from criterion 12.
15. **Reorder while expanded**: an owner can also reorder a card that is currently expanded,
    with the same start mechanism and the same outcome as for a collapsed card (recommended;
    the trade-off is that an expanded card is tall and harder to carry across a long list, so
    the architecture step may choose to collapse the dragged card for the duration of the
    gesture, provided the owner's expanded state is not lost without notice). Reorder is never
    required to work only while expanded.

## Task Description

### Problem

Reordering by dragging is implemented with the browser's native drag-and-drop for mouse. Most
touch browsers, including the Telegram mobile WebView, do not fire those events, so a phone
owner cannot drag at all. The up/down buttons are the only way, and they sit inside the
expanded card details, so each step costs: expand the card, tap the arrow, find the card again
after the list re-renders.

A small drag-handle element already exists in the expanded card details, but it has no
behaviour of its own; the whole card is the mouse drag source.

### Why (business reason)

The product is a Telegram Mini App; the primary device is a phone. A feature that the
specification describes as "order can be changed manually" should be usable on the primary
device, not only on desktop. The gap was recorded as low-priority debt in WISHENKA-15 because
the button fallback made the feature technically reachable.

### Current behaviour (for reference, not a design)

- Owner view cards are draggable with a mouse; drop saves the full order to the existing
  reorder action and replaces the list with the server response.
- Up/down buttons are in the expanded card details, are disabled on the first/last card, and
  save a one-step swap through a separate existing action.
- Tapping a card summary expands or collapses it; buttons, links, and form fields inside do
  not toggle it.
- The share page shows cards without drag capability and without reorder controls.

### In scope

- Touch (finger) reordering of wish cards on the owner wishlist page, saving through the
  existing reorder action, with the same validation and permissions.
- Visual feedback during the touch drag.
- Disambiguation of tap, scroll, and drag on cards.
- Keeping mouse drag-and-drop, up/down buttons, and card toggle working.
- Updating existing tests and developer documentation affected by the change; adding automated
  checks feasible without a browser, plus a documented manual touch check.

### Out of scope

- Browser-level (Playwright/CDP) end-to-end tests of toggling and dragging, including touch
  emulation: WISHENKA-110.
- Removing the hardcoded reorder address from the script and declaring it in the page:
  WISHENKA-141.
- Moving the remaining inline script and inline handlers out of the shared layout and modal
  partials: WISHENKA-140.
- Any change to the server reorder action, wish-order rules, permissions, reservations, or
  archived-items handling.
- Drag between lists, drag of archived items, multi-select drag, undo of a reorder.
- Keyboard-driven drag (the up/down buttons remain the keyboard path).
- Making the product's content-security policy stricter.

## Constraints and Assumptions

- Implementation language: Python (page templates and backend; primary) with JavaScript for
  the client script. No server-side change is expected to be necessary.
- Choice of mechanism (pointer-based custom code versus a third-party library) is deferred to
  the architecture step. The following project rules bound that choice:
  - The Mini App shell (`GET /`) is served with a strict content-security policy:
    `default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' https:; frame-ancestors https://web.telegram.org`
    (header set in `wishenka/web/routes/miniapp.py`). It is set only on the shell `GET /`;
    `security.py` sets no content-security policy, and `/web/*` pages send none. Only own
    scripts and the Telegram SDK origin are allowed to run on the shell.
  - The wishlist pages (`/web/...`), where reordering happens, currently send no
    content-security policy of their own, and already load the Telegram SDK and htmx 1.9.12
    (with the json-enc extension) from third-party hosts (`telegram.org`, `unpkg.com`) without
    integrity hashes. Adding another third-party CDN dependency would extend that existing,
    already-recorded debt ("Unpinned CDN scripts", WISHENKA-15) and conflicts with the goal of
    allowing a stricter policy later (WISHENKA-108). No document explicitly forbids or permits
    new CDN dependencies; this is an open question for the architecture step (see Q&A).
  - Page behaviour is delivered from the product's own static resources (`/static/wishlist.js`,
    classic deferred script, no inline copy; WISHENKA-108). Inline script must not be
    reintroduced for this feature.
  - Existing automated checks of the script are limited to what is feasible without a browser;
    there is no JavaScript test runner in the repository.
- The reorder action accepts only the full permutation of active wishes; the feature must send
  the complete current order on every drop.
- Existing styling already marks the drag handle as a touch area that does not scroll the page
  (`touch-action: none` on `.item-drag-handle`); the card summary and the card body have no such
  rule, so by default a swipe on them scrolls the page. How to keep scrolling while allowing
  drag is a design decision for the architecture step.
- The drag handle currently lives inside the collapsed-by-default card details, so it is visible
  only after a card is expanded. A handle-only design that keeps it there would preserve the
  pain named in the Problem section (expand the card, act, find the card again), so criterion 1
  requires that reorder can start from a collapsed card. Whether this is a visible dedicated
  area on the compact row (the handle moves or is duplicated there) or a deliberate gesture such
  as a long press on the card is left to the architecture step, subject to criteria 4, 5 and 15.
- Telegram Mini App clients can interpret a downward swipe as a gesture to close or minimise the
  window. The product does not configure this behaviour today: the Mini App shell
  (`miniapp.js`) only calls the SDK's `expand()`; it does not disable vertical swipes and does
  not enable a closing confirmation. The SDK is also loaded on wishlist pages. Whether the
  platform lets the product prevent the swipe-to-close in the client versions in use is not
  verified (see criterion 12).
- The wishlist list container already declares its wishlist (WISHENKA-108) on the owner and
  share pages; the feature may rely on that declaration.
- Real-device testing in Telegram is manual; automated checks are limited to server-rendered
  markup and static-script content until WISHENKA-110 lands.

## Business Entities and Interactions

- **Wishlist**: owned collection of wishes; the list that receives the new order.
- **Wish card**: compact summary plus expandable details; reacts to tap (expand/collapse),
  finger drag (reorder), mouse drag (reorder), and up/down buttons (one-step move).
- **Wish order**: owner-defined sequence of active wishes, saved as a whole; archived wishes
  are not part of it.
- **Owner / editor**: the only role that can reorder, by any method.
- **Visitor** (public share view): can expand cards and use reservation controls; cannot
  reorder.

## Q&A

- **Q: Why is a technical change needed from a business point of view?**
  A: The primary device is a phone in Telegram, where mouse drag does not work. Reordering
  needs one-step buttons and several taps per move. Touch drag removes that friction without
  removing the existing ways.
- **Q: Must mouse drag and buttons keep working?**
  A: Yes. Both stay; touch drag is an addition (criterion 7, 9).
- **Q: Should the new feature change the server request or validation?**
  A: No. It reuses the existing reorder action with the same permutation check (criterion 8).
- **Q: Are third-party scripts acceptable?**
  A: Open. The project already loads htmx and the Telegram SDK from third-party hosts without
  integrity hashes and has no written rule against more; the Mini App shell CSP allows only own
  scripts and `telegram.org`. The architecture step must decide and record the choice,
  weighing the preference for own static resources and a future stricter policy.
- **Q: Does the drag start from the whole card or a handle?**
  A: The mechanism is not decided here. Requirements fix the outcome: reorder must be startable
  from a collapsed card (criterion 1), also works while expanded (criterion 15), tap toggles,
  swipe scrolls (criteria 4, 5).
- **Q: Who tests on a real device?**
  A: A manual check in Telegram mobile is recorded at the development step; automated
  browser tests belong to WISHENKA-110.
- **Q: What about WISHENKA-141 and WISHENKA-140?**
  A: Out of scope. They remove the hardcoded reorder address and the remaining inline script
  respectively; this task must not depend on them and must not make them harder.
- **References**: `in-docs/spec.md` sections 5.4, UC-03; `ai-tasks/WISHENKA-15/60-tech-debt.md`;
  `ai-tasks/WISHENKA-108/10-requirements.md`, `20-architecture.md`, `60-tech-debt.md`;
  `doc/dev/miniapp.md` sections 9.8, 9.8.1.
