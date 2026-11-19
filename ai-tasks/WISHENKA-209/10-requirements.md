# WISHENKA-209: Preserve form state on Create Item modal validation errors

## Goals

Ensure that when a user creates a wish item through the detailed Create Item modal and a validation error occurs, the modal stays open, displays a clear inline error message, and preserves all entered form values so the user can fix the mistake without retyping the entire item.

### Business Value

- Prevents accidental data loss when users fill out multiple optional fields (link, price, currency, quantity, recipient, description, image URL, priority, category) in the Create Item modal and hit a validation error.
- Aligns the error-handling experience of the Create Item modal with the Edit Item modal, providing consistent, predictable feedback inside the modal dialog.
- Preserves existing inline Quick Add bar behavior so fast single-line item entry continues to report errors in the list notice area without opening a modal.

## Programming Language

- **Primary implementation language**: Python (with existing HTML/Jinja2 web templates).

## User Stories

- **As a wishlist owner or collaborative editor**, when I open the Create Item modal, fill in item details, and submit invalid data (for example, an empty title, non-numeric price, invalid URL/quantity/priority, or domain validation failure), I want the Create Item modal to remain open with an inline error banner and all my entered field values preserved, so that I can correct the invalid field and resubmit without losing my work.
- **As a wishlist owner or collaborative editor**, when I use the inline Quick Add bar on the wishlist page and submit invalid input, I want the existing list-level error notice behavior to remain unchanged, so that quick-add errors do not unexpectedly open a modal.
- **As a collaborative wishlist member**, when a validation error occurs while creating an item in a collaborative wishlist, I want the collaborative recipient options and my selected/entered recipient values to remain available in the re-rendered Create Item modal.

## Functional Requirements

1. **Modal Error Re-rendering on Create Validation Failure**:
   - When a submission originating from the Create Item modal fails input or domain validation (HTTP `400`), the system must keep the Create Item modal open and display the localized validation error message inside the modal's error banner.
   - The modal must remain in "create" mode (not switch to "edit" mode).
2. **Form State Preservation**:
   - On validation failure from the Create Item modal, all user-submitted fields must be preserved in the re-rendered form: title, link, price, currency, quantity, recipient selection, manual recipient name, description, image URL, priority, and category.
   - For collaborative wishlists, the recipient selection list must remain populated and reflect the user's previously chosen recipient (if any).
3. **Quick Add Bar Isolation**:
   - Submissions originating from the inline Quick Add bar must retain their current validation error behavior (displaying the error in the page/list notice area without opening the Create Item modal).
4. **Successful Creation Unchanged**:
   - When a Create Item modal submission succeeds, the new item card is added to the wishlist, the modal closes, and the Quick Add bar state is reset as before.
5. **Regression Coverage**:
   - Automated tests must verify that invalid submissions from the Create Item modal return the error inside the modal with preserved form inputs, and that invalid submissions from the Quick Add bar still surface errors in the list notice area.

## Non-Functional Requirements

- **Usability & Consistency**: Error presentation and form preservation in the Create Item modal must match the UX of the Edit Item modal.
- **Localization**: Validation error messages and modal labels must continue to respect the user's active locale.
- **Security & Access Control**: Wishlist membership, active-wishlist checks, and permission rules must continue to be enforced identically on every submission.

## Constraints and Assumptions

- The distinction between Create Item modal submissions and inline Quick Add bar submissions must be unambiguous so each flow receives the appropriate error-handling UX.
- Domain-level permission or wishlist-state errors (e.g., wishlist not found, deleted, archived, or permission denied) continue to follow existing modal/notice error handling.
- No new database schema changes or external service dependencies are required.

## Main Business Entities

- **Wishlist**: Container of wish items; may be personal or collaborative (having multiple members who can be targeted as recipients).
- **Wish Item (Draft / Form Input)**: The set of attributes a user enters when creating a wish (title, link, price, currency, quantity, priority, category, description, image URL, and optional recipient targeting).
- **Wishlist Editor (Actor)**: An authenticated user who owns or is an active member of the wishlist.

## Definition of Done

- Submitting invalid data from the Create Item modal keeps the modal open in create mode, displays the validation error message inside the modal, and preserves all entered field values (including collaborative recipient fields when applicable).
- Submitting invalid data from the inline Quick Add bar continues to display the error in the list notice area without opening the modal.
- Successful item creation from both the Create Item modal and the Quick Add bar continues to work without regressions.
- Automated regression tests cover Create Item modal validation error preservation and Quick Add bar error isolation, and all relevant checks pass.

## Task Description

During WISHENKA-160, it was identified that the Create Item modal submits to the same flow as the inline Quick Add bar. When a `400` validation error occurs, the response closes the modal container and displays a list-level notice instead of re-rendering the Create Item modal with the error message and the user's submitted form values. This task separates or distinguishes the Create Item modal error path so users do not lose their entered form state on validation errors.

## Q&A

- **Q**: Why is this needed from a business perspective?
  - **A**: Users filling out the detailed Create Item modal enter up to a dozen fields. Losing all entered data and closing the modal on a simple validation mistake (e.g., invalid price or URL) causes frustration and rework. Preserving form state inside the modal matches the Edit Item modal UX and prevents data loss (see [ai-tasks/WISHENKA-160/60-tech-debt.md](file:///home/src/ai-tasks/WISHENKA-160/60-tech-debt.md)).
