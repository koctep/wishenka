# WISHENKA-140: Remove Remaining Inline JavaScript and Inline Event Handlers for Strict CSP

## Goals

Enable a strict Content Security Policy (CSP) without `'unsafe-inline'` for scripts across all web pages and interactive fragments by eliminating all remaining inline scripts and inline event-handler attributes, without changing any user-facing behavior.

- **Security readiness**: Removing inline executable code and inline event attributes removes the last blocker to enforcing a strict script CSP.
- **Behavioral parity**: All existing interactive flows (CSRF protection, idempotent reservation actions, reservation cabinet and wish card updates, modal dismissal, quantity stepping, and quick-add preview dismissal) must continue to work identically for end users.
- **Regression protection**: Automated verification must ensure that neither full pages nor dynamically loaded modal/preview fragments reintroduce inline scripts or inline event-handler attributes.

## User Stories

1. **As a Security / Platform Owner**, I want all web pages and dynamically rendered HTML fragments to contain zero inline scripts and zero inline event-handler attributes, so that a strict CSP disallowing `'unsafe-inline'` scripts can be enforced in a follow-up step without breaking application functionality.
2. **As a Wishlist Giver / Viewer**, I want reservation actions (reserving, releasing, updating quantities, and viewing updated card or cabinet states), error notices, and CSRF/idempotency protections to work seamlessly without inline scripts.
3. **As a Wishlist Owner**, I want to open and close the item edit and archive modals, step item quantities up and down within allowed bounds, and dismiss the quick-add preview card just as before, without inline event handlers.
4. **As a QA / Maintainer**, I want automated tests to verify the absence of inline scripts and inline event handlers across both full pages and modal/preview fragments, and to validate the extracted client-side behavior against the served static assets rather than inline page scripts.

## Definition of Done

1. **Zero inline scripts**: Rendered HTML pages and fragments contain no inline executable script blocks (external script references only).
2. **Zero inline event handlers**: Rendered HTML pages and fragments (including item edit modal, item archive modal, and quick-add preview fragment) contain no inline event-handler attributes (`on*`).
3. **Preserved CSRF and reservation behavior**:
   - Identified viewers automatically have CSRF protection prepared and attached to mutating requests.
   - Reservation actions include idempotency protection, handle busy/conflict/authorization/CSRF-rejection responses, and refresh either the reservations cabinet or the wish card while preserving the card's expanded/collapsed state.
4. **Preserved modal and preview interactions**:
   - Closing or cancelling the item edit modal clears the modal container.
   - Closing or cancelling the item archive modal clears the modal container.
   - Incrementing and decrementing quantity in the item edit modal respects the configured minimum quantity (including locked/reserved quantity constraints) and maximum bound (`1000`).
   - Dismissing the quick-add preview card clears the preview area.
5. **Updated automated test coverage**:
   - Tests checking for the absence of inline handlers cover modal and preview fragments in addition to full pages.
   - Existing tests that previously inspected inline page scripts are updated to verify the served static script(s) instead, and the full test suite passes.

## Task Description

### Problem

Following WISHENKA-108, one inline script block remained in the base page layout (handling CSRF token preparation, reservation request headers and idempotency keys, reservation cabinet refreshes, and wish card swaps) along with six inline click-handler attributes across three modal/preview fragments:
- Item edit modal: close button, cancel button, quantity decrement button, quantity increment button.
- Item archive modal: cancel button.
- Quick-add preview card: dismiss button.

While these remain in the HTML, a strict CSP without `'unsafe-inline'` for scripts cannot be enabled without breaking core user flows.

### Programming Language

- **Python / JavaScript** (server-side templates/tests in Python, client-side behavior in JavaScript).

### Functional Requirements

1. **Client-side application behavior (formerly in base layout inline script)**:
   - Prepare and attach CSRF tokens to mutating requests for identified viewers, including retrying/queuing reservation actions when token preparation is in flight and clearing cached tokens on invalid-CSRF responses.
   - Generate and reuse idempotency keys for reservation requests until a definitive non-transient response is received.
   - Refresh the reservations cabinet or the individual wish card after reservation requests, showing appropriate busy or refusal/shortage notices and preserving the card's expanded state across card replacement.
2. **Modal and preview interactions (formerly inline event handlers)**:
   - Dismissing the item edit modal (via close or cancel control) clears the modal container.
   - Dismissing the item archive modal (via cancel control) clears the modal container.
   - Decrementing or incrementing the quantity input in the item edit modal adjusts the numeric value by 1 within the item's minimum allowed quantity and maximum allowed quantity (`1000`), defaulting safely if the input is empty or non-numeric.
   - Dismissing the quick-add preview card clears the quick-add preview target.

### Non-Functional Requirements

- **Security**: No inline executable scripts or inline `on*` event attributes in any rendered HTML page or partial fragment.
- **Compatibility**: Must work both on initial page load and on dynamically inserted fragments (modals and previews loaded asynchronously).
- **Reliability**: No regressions in existing user flows or automated test contracts.

### Constraints and Out of Scope

- **Out of scope**: Adding or modifying the `Content-Security-Policy` HTTP response header itself is explicitly a separate follow-up step and must not be implemented in this task.
- **Out of scope**: Static asset caching policy (`Cache-Control` / cache-busting) is tracked separately (WISHENKA-139).
- **Out of scope**: Reorder URL parameterization (WISHENKA-141), touch drag-and-drop (WISHENKA-109), and Playwright/CDP browser test suite expansion (WISHENKA-110).

### Edge Cases

- Clicking quantity step buttons when the quantity field is empty or contains non-numeric text must fall back safely without producing `NaN`.
- Quantity decrement must not go below the item's minimum allowed quantity (e.g., when reservations lock a minimum quantity); quantity increment must not exceed `1000`.
- Modal and preview controls are injected dynamically after initial page load, so event handling must work for dynamically added elements as well as elements present on initial load.
- If a reservation request fails due to an expired/invalid CSRF token or transient busy state, the user must still see the appropriate error/busy message and the UI must remain recoverable.

## Q&A

- **Q**: Should this task enable the strict `Content-Security-Policy` header?
  **A**: No. Per the Jira task description, enabling the CSP header is a separate step; this task removes the remaining inline JS and inline `onclick` handlers so strict CSP becomes possible.
