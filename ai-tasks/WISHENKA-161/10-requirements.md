# WISHENKA-161: Gift Receipt Dialog Accessibility, Focus Management, and Mobile Behavior

## Goals

Ensure that wishlist authors (owners, administrators, and members) using the Mini App's gift-receipt dialog can complete gift receipt actions smoothly, predictably, and accessibly across keyboard, screen-reader, and mobile touch interfaces:

1. **Predictable focus continuity**: Keyboard and screen-reader users never lose their place in the wishlist after confirming or encountering an error in the gift-receipt flow.
2. **True modal isolation**: While the receipt dialog is open, navigation and assistive technologies remain safely confined to the dialog rather than wandering into obscured background content.
3. **Uninterrupted list context**: Expanding the «Подаренные» section is respected across subsequent gift-receipt updates.
4. **Scalable quantity selection**: Recording a gift receipt remains effortless both for single/small-quantity wishes and for wishes with large quantities (hundreds of units).
5. **Verified mobile usability**: Touch targets, safe-area spacing, and visual layering above the fixed quick-add bar are verified by automated browser checks.

## Task Description

### Problem

During WISHENKA-24 (gift-receipt UI), several accessibility and mobile UX limitations were accepted as follow-up debt (tracked as T-2 in `ai-tasks/WISHENKA-24/60-tech-debt.md`):

1. **Lost focus after successful receipt**: Closing the dialog via Cancel or Escape returns focus to the originating wish card, but after a successful receipt the dialog closes and the wish card is updated or removed, leaving keyboard and screen-reader users with focus dropped onto the page body. Focus behavior after an in-dialog refusal is also unspecified/untested.
2. **Missing modal focus containment and screen-reader isolation**: When the receipt dialog is open, Tab navigation can leave the dialog and reach controls on the underlying page, the background page is not isolated from assistive technologies, and the dialog lacks modal accessibility semantics.
3. **«Подаренные» section collapses on update**: When an author expands the «Подаренные» section and then records a receipt, the section resets to its collapsed state instead of staying open.
4. **Unbounded quantity choice list**: The quantity selector enumerates every integer from 1 to the remaining quantity. For a wish with a large quantity (e.g., 500 units), this produces an unwieldy list of hundreds of options.
5. **Missing browser test coverage**: Automated browser tests do not yet cover focus return after a successful receipt, focus behavior on refusal, keyboard focus containment, 44 px minimum touch targets, or visual layering above the fixed quick-add bar on mobile viewports.

### Implementation Language

- **Python** (web application and automated browser/route tests) and **JavaScript** (Mini App client-side behavior), alongside the existing web templates and styles.

### Main Domain Entities

- **Wishlist Author**: Wishlist owner, administrator, or member permitted to record gift receipts.
- **Wish**: An item in the active wishlist with a remaining unreceived quantity (1 or more).
- **Gift-Receipt Dialog**: The modal confirmation screen where an author chooses how many units were received and confirms the final receipt action.
- **«Подаренные» Section**: The collapsible history section on the wishlist page listing received gifts separately from archived wishes.
- **Quick-Add Bar**: The fixed bottom bar on the wishlist page for adding new wishes.

### Scope & Functional Requirements

1. **Focus Management**:
   - **Dismissal**: Cancelling or dismissing the receipt dialog continues to return focus to the control on the wish card that opened it.
   - **Partial receipt**: After a successful partial receipt (the wish remains in the active list with reduced remaining quantity), focus moves to the updated wish card (or its receipt trigger) so the user remains at the same item.
   - **Full receipt**: After a successful full receipt (the wish leaves the active list), focus moves to a meaningful, predictable location in the list area (such as the list status notice, the next remaining wish, or the active list / «Подаренные» region) rather than dropping to the page root.
   - **Refusal inside dialog**: When a receipt attempt is refused and the dialog displays a refusal message, focus remains inside the dialog (directed to the feedback message or primary dialog control) so keyboard and screen-reader users immediately perceive the refusal.

2. **Modal Accessibility & Focus Containment**:
   - While the receipt dialog is open, keyboard Tab / Shift+Tab navigation is trapped within the dialog's visible interactive controls and wraps around without escaping to the background page.
   - While the receipt dialog is open, background page content is isolated from keyboard focus and assistive technologies.
   - The receipt dialog exposes proper modal dialog semantics and an accessible title to screen readers.

3. **«Подаренные» Section State Preservation**:
   - If the author has expanded the «Подаренные» section before recording a gift receipt, the section remains expanded after the receipt update completes.
   - If the section was collapsed, it remains collapsed after the receipt update.

4. **Scalable Quantity Selection**:
   - For wishes with small remaining quantities (up to a reasonable threshold), the author can pick a quantity from a compact list of choices.
   - For wishes with large remaining quantities (above the threshold), the dialog provides a scalable numeric entry / stepper experience rather than enumerating hundreds of options, while still enforcing valid whole-number bounds from 1 to the remaining quantity.
   - The confirmation summary reflecting the selected quantity and remaining count updates accurately for both selection modes, and submitting an out-of-range or invalid quantity is prevented or handled cleanly.

5. **Mobile Usability & Layering**:
   - All interactive controls inside the receipt dialog meet a minimum 44 px touch-target size on mobile viewports.
   - On mobile viewports, the open receipt dialog overlays the page above the fixed quick-add bar so no dialog control is covered or blocked, and bottom safe-area spacing is preserved.

6. **Automated Browser Verification**:
   - Automated browser tests verify:
     - Focus movement into the dialog, Tab containment within the dialog, and background isolation while open.
     - Focus return after Cancel/Escape, after partial receipt, after full receipt, and focus retention on refusal.
     - «Подаренные» remaining expanded after a receipt when previously opened.
     - Scalable quantity selection behavior for large-quantity wishes.
     - Minimum 44 px touch-target sizing on dialog controls and visual overlay above the fixed quick-add bar at mobile viewport width.

### Non-Functional Requirements & Constraints

- **Surprise secrecy**: No booking, reservation, or giver details may be exposed in any dialog state, focus target, notice, or accessible label.
- **No domain rule changes**: Backend receipt validation, refusal reasons, and reservation rules remain unchanged.
- **Bounded automated tests**: All browser and Python tests must use bounded waits and explicit test timeouts per project testing standards.

### Non-Goals

- **Older edit/archive modals**: Error visibility and modal styling for the edit and archive modals are out of scope (handled in WISHENKA-160).
- **Real-htmx test vendoring / stub overhaul**: Replacing the test stub with real htmx is out of scope (tracked in WISHENKA-145 and WISHENKA-162).
- **Web-layer structural refactoring**: Consolidating shared constants, OOB helpers, or sentence tables is out of scope (tracked in WISHENKA-163).
- **Wording / i18n review & CSS token refactoring**: Russian/English copy updates and CSS theme token refactoring are out of scope (tracked in WISHENKA-164, WISHENKA-33, and WISHENKA-165).

## User Stories

1. **Focus continuity after recording a receipt**:
   As a **Wishlist Author** using a keyboard or screen reader, when I confirm a partial or full gift receipt, I want focus to land on the updated wish card or a predictable place in my wishlist so that I do not lose my position on the page.

2. **Confined modal navigation**:
   As a **Wishlist Author** using a keyboard or screen reader, while the gift-receipt dialog is open, I want keyboard navigation to stay inside the dialog and the background page to be hidden from my screen reader so that I do not accidentally interact with controls behind the dialog.

3. **Preserved «Подаренные» view**:
   As a **Wishlist Author**, when I open the «Подаренные» section to review received gifts and then mark another wish as received, I want «Подаренные» to stay open so that I can immediately see the newly added entry without expanding the section again.

4. **Comfortable quantity entry for large wishes**:
   As a **Wishlist Author** with a wish that has a large quantity (e.g., 500 units), when I open the gift-receipt dialog, I want a clean numeric/stepper control instead of a 500-item dropdown so that I can quickly enter how many units I received on mobile.

5. **Unobstructed mobile controls**:
   As a **Wishlist Author** on a mobile phone, I want all buttons and inputs in the gift-receipt dialog to be comfortably tappable (at least 44 px) and positioned above the fixed quick-add bar so nothing blocks my confirmation.

## Definition of Done

1. **Focus continuity**:
   - Partial receipt returns focus to the updated wish card (or its receipt trigger).
   - Full receipt moves focus to a predictable, meaningful element in the list area rather than the document body.
   - In-dialog refusal keeps focus inside the dialog on the feedback or primary control.
   - Cancel / Escape continues to return focus to the trigger that opened the dialog.
2. **Modal accessibility**:
   - Keyboard Tab / Shift+Tab cycles strictly within the open receipt dialog.
   - Background page content is inert / inaccessible to keyboard and assistive technologies while the dialog is open.
   - The dialog exposes modal semantics and an accessible title.
3. **«Подаренные» state preservation**:
   - An expanded «Подаренные» section stays expanded after a receipt update; a collapsed section stays collapsed.
4. **Scalable quantity selection**:
   - Wishes with large remaining quantities do not render hundreds of individual options and allow entering/stepping any valid integer from 1 to the remaining quantity, with accurate confirmation summary updates.
5. **Mobile targets and layering**:
   - Interactive controls in the receipt dialog meet at least 44 px touch-target dimensions, and the dialog layers cleanly above the fixed quick-add bar on mobile viewports.
6. **Automated verification**:
   - Automated browser tests cover focus lifecycle (open, trap, partial/full receipt, refusal), «Подаренные» state preservation, large-quantity selection, 44 px touch targets, and overlay above the quick-add bar.
   - All existing and new tests pass without regressions.

## Q&A

- **Q**: Does this task change any backend gift-receipt rules or surprise-secrecy behavior?
  **A**: No. All backend receipt validation, refusal reasons, and surprise-secrecy guarantees remain unchanged.
- **Q**: Are the older item edit and archive modals included in this task?
  **A**: No. Those were addressed separately in WISHENKA-160; this task focuses exclusively on the gift-receipt dialog and «Подаренные» section behavior from WISHENKA-24 T-2.
