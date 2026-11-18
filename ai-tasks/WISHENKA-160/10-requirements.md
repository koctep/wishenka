# WISHENKA-160: Older Modals (Edit, Archive) Error Visibility and Modal Presentation

## Goals

Ensure that wishlist owners and editors using the Mini App's item edit/create and archive modals:
1. Always see clear, actionable error feedback when an action fails (conflicts, busy state, validation or state errors) instead of silent failures.
2. Can view and interact with the edit and archive modals comfortably on mobile and desktop screens, with proper modal overlay presentation and unobstructed action buttons.

## Task Description

### Problem
During testing of the gift-receipt flow, a pre-existing defect was identified in the older Mini App modals (wish item edit/create modal and wish item archive confirmation modal):
- **Invisible error responses**: When submitting the edit form or archive confirmation results in a client or server error (such as reducing quantity below the already reserved/received amount, concurrent modification / busy wish, archived wishlist, or invalid input), the error response is not displayed to the user. The modal remains frozen or shows no feedback, making it appear as if the button did nothing.
- **Unstyled modals and obscured controls**: The edit and archive modals render as plain unstyled blocks in the normal page flow rather than modal overlays/sheets. On mobile viewports, the archive confirmation button (and bottom modal controls) are overlapped by the fixed bottom quick-add bar, preventing or hindering interaction.
- **Inconsistent inline archive action**: Triggering archive from inside the edit modal lacks a proper update target, which can corrupt the button content when an out-of-band response is returned.

### Implementation Language
- **Python** (with the existing Mini App web templates, styles, and client-side scripts).

### Scope & Constraints
- Applies to the item edit/create modal, the item archive confirmation modal, and the inline archive button inside the edit modal.
- Must preserve existing surprise secrecy invariants (never exposing booking/gifter details to the wishlist owner) and XSS protections.
- Must work cleanly on mobile viewports (including safe-area spacing and layering above the fixed quick-add bar) as well as desktop.
- Existing stale-reorder error handling is already in place and must remain intact.

### Non-Goals
- **Global error toast system**: A general-purpose toast notification mechanism for arbitrary network/server failures across the entire Mini App is out of scope (tracked separately in WISHENKA-90).
- **Receipt dialog accessibility & UX enhancements**: Focus trapping, screen-reader modal attributes, and quantity selector scaling for the receipt modal are out of scope (tracked in WISHENKA-161).
- **CSS token refactoring & shared web-layer helpers**: Consolidating CSS design tokens or refactoring shared Python/JS constants is out of scope (tracked in WISHENKA-163 and WISHENKA-165).
- **Test-infrastructure overhaul / real-htmx vendoring**: Replacing the test stub with vendored htmx is out of scope (tracked in WISHENKA-145 and WISHENKA-162).
- **Domain business-rule changes**: No changes to reservation, reduction-lock, archiving, or receipt business rules.

## User Stories

1. **Error visibility on item edit**:
   As a **Wishlist Owner / Editor**, when I edit a wish item and the save fails (for example, I try to set the quantity below the already reserved/received count, the wish is temporarily busy, or the wishlist is archived), I want to see a clear error message inside the modal (or a clear notice if the modal can no longer remain open) so that I understand why the change was not saved and what to do next.

2. **Error visibility on item archive**:
   As a **Wishlist Owner / Editor**, when I confirm archiving a wish item and the action fails (for example, the wishlist is archived, the item is no longer available, or it was already fully received), I want to see clear feedback and have the UI reflect the current state so that I am not left guessing whether the item was archived.

3. **Safe inline archive from the edit modal**:
   As a **Wishlist Owner / Editor**, when I click the archive button inside the item edit modal and confirm it, I want the action to update the list and close the modal (or show an error/notice if it fails) without breaking or replacing the button itself.

4. **Usable modal presentation on mobile and desktop**:
   As a **Wishlist Owner / Editor** on a mobile phone, when I open the item edit modal or the item archive modal, I want it to appear as a clearly separated modal overlay/sheet above the page content and above the fixed quick-add bar, with all buttons (including Save, Cancel, and Confirm Archive) unobstructed and easy to tap.

## Definition of Done

1. **Edit modal error feedback**:
   - Submitting invalid or conflicting edits (e.g., quantity below reserved/received count) displays the server-provided error message inside the edit modal while preserving the user's entered form values.
   - Submitting when the wish is temporarily busy displays the busy error message inside the edit modal.
   - Submitting when the wishlist is archived or the resource is unavailable surfaces clear error feedback to the user rather than failing silently.
2. **Archive modal & inline archive feedback**:
   - Confirming archive when an error occurs (e.g., archived wishlist, missing resource, or nothing remaining to archive) displays clear user-facing feedback and leaves the UI in a consistent state.
   - Triggering archive from the button inside the edit modal cleanly updates the page/modal state on both success and failure without replacing the button label with unexpected markup.
3. **Modal visual presentation & layering**:
   - Both the edit modal and the archive modal render as proper modal overlays/sheets (with backdrop dimming, sheet container styling, scrolling for tall content, and safe-area bottom padding).
   - Both modals layer above the fixed quick-add bar so that no modal button (including the archive confirmation button) is covered or blocked by the quick-add bar.
   - Interactive controls inside both modals meet usable touch-target sizing on mobile.
4. **Automated verification**:
   - Automated tests verify that error responses for the edit and archive modals are rendered visibly to the user and that modal layering/visibility prevents the quick-add bar from obscuring modal actions.
   - All existing tests continue to pass without regressions.

## Q&A

- **Q**: Should this task implement a global toast banner for all failed requests across the app?
  **A**: No. Global toast notifications for generic network/server errors are tracked separately in WISHENKA-90. This task focuses specifically on making error responses and modal UI work properly for the older edit and archive modals.
- **Q**: Does this task change any backend validation or reservation rules?
  **A**: No. Backend rules (such as reduction lock, busy lock, and archive guards) remain unchanged; the focus is on surfacing their responses and styling the modals properly.
