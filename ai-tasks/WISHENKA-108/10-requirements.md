# WISHENKA-108: Wishlist page behaviour independent of inline script and page address

## Goals

The wishlist page behaviours that owners and visitors rely on (expanding a wish card and, for
owners, reordering wishes by dragging) must keep working exactly as today, but must stop
depending on two fragile conditions:

- the behaviour code being embedded in the markup of every page of the product;
- the wishlist identity being guessed from the browser address.

Business value:

- **Reliability for owners**: a future change to page addresses must not silently break
  reordering. Today a broken guess results in a drag that appears to work on screen but is never
  saved.
- **Safer and lighter pages**: behaviour code is delivered as a separate, cacheable resource
  instead of being repeated in every page. This also allows the product to adopt a stricter
  browser content-security policy for these behaviours in the future.
- **Maintainability for the team**: page behaviour can be reviewed, changed, and verified apart
  from page markup.

Source of the task: technical debt recorded in `ai-tasks/WISHENKA-15/60-tech-debt.md`
(Jira: WISHENKA-108, type Debt, priority Low, 2 SP).

## User Stories

- As a wishlist owner, I want to drag wishes into a new order and have that order saved for the
  correct wishlist, so that the order I see is the order visitors see.
- As a wishlist owner or a visitor, I want to expand and collapse a wish card by click or by
  keyboard (Enter or Space) without triggering actions of the controls inside the card, so that I
  can read wish details comfortably.
- As a product developer, I want the behaviour of the wishlist page to be independent of the
  page address layout, so that renaming or restructuring routes does not break reordering.
- As a product operator, I want the page behaviour delivered as a standalone resource, so that
  it is cacheable and does not inflate every page.

## Definition of Done

Acceptance criteria (business behaviour, each verifiable by automated tests):

1. **Card expand/collapse is unchanged**: clicking or pressing Enter or Space on a card summary
   toggles its details and its expanded/collapsed accessibility state; clicks on links, buttons,
   form fields, and areas marked as not toggling do not toggle the card. This holds on the owner
   page and on the public share page.
2. **Drag-and-drop reorder is unchanged**: an owner dragging a card before or after another card
   sees the new order immediately, the new order is saved, and the list is refreshed from the
   server result. Dropping a card onto itself or outside the list changes nothing.
3. **The wishlist is identified explicitly**: the wishlist that receives the new order is the one
   the page itself declares as its own, not a value derived from the browser address. Reorder
   still saves to the correct wishlist when the page address does not follow the usual wishlist
   path pattern.
4. **The declaration survives list refreshes**: after any action that re-renders the wish list
   (reorder, move up/down, add, edit, archive, restore), a subsequent drag-and-drop still saves
   to the correct wishlist.
5. **The page works without the inline script**: the owner and share pages contain no inline
   copy of the card-toggle and reorder behaviour; that behaviour is delivered by a separate
   resource served by the product, available on every page where it is used, and loaded by the
   shared page layout.
6. **Existing behaviours stay intact**: all other behaviour currently provided by the shared
   page layout (viewer identification and request protection, reservation controls, giver
   controls) is not altered by this task.
7. **No regression in existing automated checks**: the full existing test suite passes. Tests
   that today locate the toggle behaviour in the page markup are updated only to locate it in
   its new delivery location, with unchanged assertions about behaviour.
8. **Documentation matches reality**: developer documentation that currently states the
   behaviour lives inline in the shared layout is updated to describe its new location and the
   explicit wishlist declaration.

## Task Description

### Problem

The card-toggle and drag-and-drop reorder behaviours are embedded in the shared page layout and
therefore repeated in every page, including pages that never use them. The reorder behaviour
additionally works out which wishlist to save to by pattern-matching the browser address. If
the address layout changes, or the page is shown under another address, the lookup fails and the
reorder is not saved, with no message to the owner.

### Why (business reason)

The inline form blocks future tightening of browser security rules, cannot be cached
separately, and ties a user-visible feature to an unrelated implementation detail (the route
layout). Removing both couplings reduces the risk of silent data-saving failures and the cost
of future UI changes. It is recorded as low-priority debt, so no change in user-visible
behaviour is expected or wanted.

### In scope

- Card expand/collapse behaviour on the owner wishlist page and on the public share page.
- Drag-and-drop reorder behaviour on the owner wishlist page.
- The way the page tells that behaviour which wishlist it belongs to.
- Delivery of that behaviour as a standalone resource.
- Updating existing tests and developer documentation affected by the move.

### Out of scope

- Touch-friendly (mobile/Telegram) drag reordering: WISHENKA-109.
- Browser-level (Playwright) end-to-end tests of toggling and drag-and-drop: WISHENKA-110.
- Moving other behaviour out of the shared layout (viewer identification and request
  protection, reservation and giver controls). It is acknowledged that this behaviour is also
  inline today; it may be handled by separate tasks.
- Any change to wish-order rules, permissions, reservation rules, or the visual design.
- Making the content-security policy stricter; this task only removes one obstacle to it.

## Constraints and Assumptions

- Implementation language: Python (backend and page templates) with JavaScript for the extracted
  standalone script. Primary language is Python.
- User-visible behaviour, accessibility attributes, and keyboard support must not change.
- The product already serves static resources from a dedicated location; no new kind of
  delivery is assumed to be needed.
- Wish cards currently attach the toggle through attributes on the card markup itself. If the
  goal of independence from inline script is to be met for cards, that attachment is also
  considered part of this task's scope; the architecture step decides how.
- The wishlist list container is produced by two pages (owner page and share page); only the
  owner page uses reorder. The declared wishlist identity must be correct wherever the
  container appears.
- Automated checks for the JavaScript behaviour are limited to what is feasible without a
  browser (WISHENKA-110 covers browser-level tests).

## Business Entities and Interactions

- **Wishlist**: owned collection of wishes; has a unique identity that the page must declare
  explicitly.
- **Wish card**: compact summary plus expandable details; interacts with the visitor by click and
  keyboard.
- **Wish order**: owner-defined sequence of cards; changed by drag-and-drop and saved for a
  specific wishlist.
- **Owner**: reorders wishes. **Visitor** (public share view): can expand cards but cannot
  reorder.

## Q&A

- **Q: Why is a technical change needed from a business point of view?**
  A: To prevent silent loss of the owner's reordering if page addresses change, to keep pages
  lighter, and to unblock stricter browser security policy. User-visible behaviour does not
  change.
- **Q: Is the user-visible behaviour expected to change?**
  A: No. Any visible difference is a defect.
- **Q: Does this include touch support for dragging?**
  A: No, see WISHENKA-109.
- **Q: Does this include browser end-to-end tests?**
  A: No, see WISHENKA-110.
- **Q: Which source describes the debt?**
  A: `ai-tasks/WISHENKA-15/60-tech-debt.md`, Shortcuts Taken and Follow-up Tasks sections.
