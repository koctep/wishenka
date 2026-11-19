# WISHENKA-217: Edge-Case Verification for Gift Receipt Cancellation and Correction

Programming language for implementation: **Python 3.12+** (recorded in `00-roadmap.md`).

## Goals

WISHENKA-153 introduced the ability for wishlist authors to cancel a mistaken gift receipt record or correct its received quantity. While the primary happy paths and core service rules are covered, several critical edge cases across the programmatic and interactive user flows lack dedicated automated verification (`ai-tasks/WISHENKA-153/60-tech-debt.md`, Missing Tests items 2–5).

From a business and user-reliability perspective, verifying these edge cases guarantees:

- **Safe retries without duplicate side effects:** When a mobile client or web view retries a receipt cancellation or quantity correction due to a flaky network or double-tap, the system replays the original outcome without mutating the wish a second time or sending duplicate notifications to givers. Conversely, reusing the same retry token for a different operation or different parameters is rejected to prevent silent data corruption.
- **Strict wish and list isolation:** A receipt record belongs strictly to a single wish on a single wishlist. Attempting to cancel or correct a receipt using another wish's or another wishlist's context must be refused without altering the target receipt.
- **Safe no-op corrections:** Confirming a quantity correction with the same quantity the receipt already has must succeed cleanly without altering receipt history, changing received totals, or notifying givers unnecessarily.
- **Clear refusal when opening stale or read-only prompts:** When an author opens a cancel or edit confirmation prompt for a receipt that was concurrently removed, or on an archived wishlist, the system must refuse the action with a clear business reason rather than displaying a broken or misleading form.

## Scope

### In scope

Automated verification (across both programmatic client operations and interactive UI flows) of the following edge-case business guarantees for gift receipt cancellation and quantity correction:

1. **Idempotent replay and conflict protection:**
   - Replaying a receipt cancellation or quantity correction with the same retry/idempotency key and identical request parameters returns the original result without performing a second state mutation or generating duplicate giver notifications.
   - Reusing an existing retry/idempotency key with different parameters (such as a different quantity or a different operation/target) is refused as a conflict.
2. **Cross-wish and cross-wishlist receipt isolation:**
   - Attempting to cancel or correct a valid receipt record while specifying a different wish or a different wishlist is refused as not found, and the receipt belonging to the other wish remains untouched.
3. **No-op quantity correction:**
   - Submitting a quantity correction where the new quantity equals the receipt's current quantity succeeds cleanly without changing the wish's received quantity, altering the receipt record, or emitting giver change notifications.
4. **Refusal responses when opening edit or cancel prompts:**
   - Requesting the edit or cancel confirmation prompt for a receipt that does not exist (e.g., concurrently cancelled) is refused as not found.
   - Requesting the edit or cancel confirmation prompt on an archived wishlist is refused as blocked/read-only.

### Out of scope

- Client-side JavaScript DOM unit testing (`receipt.js` DOM/event handling is tracked separately and outside this Python test-coverage task).
- Changing existing production business rules or adding new user-facing features (unless an uncovered defect is discovered during verification).
- Performance or load testing of full-wishlist UI re-rendering.

## Main Business Entities

- **Wishlist**: A collection of wishes with a lifecycle state (active or archived).
- **Wish**: An item on a wishlist with a requested quantity and a derived received quantity.
- **Receipt record**: A dated record of a single receipt act belonging to exactly one wish.
- **Author**: A user authorized to manage a wishlist (owner, admin, or member with edit rights).
- **Giver**: A user who may hold an open promise on a wish and receive notifications when receipt state changes.
- **Idempotency key**: A client-supplied operation token used to safely deduplicate retried cancellation or correction requests.

## User Stories

- As an author on an unstable mobile connection, if my receipt cancellation or quantity correction request is retried with the same operation key, I want the system to return the same confirmation without corrupting the wish's received count or notifying givers twice.
- As an author (or client integration), if an operation key is accidentally reused for a different quantity or different receipt action, I want the system to reject the conflicting request so no unintended change occurs.
- As a wishlist author, I want receipt records to be strictly scoped to their own wish and wishlist, so a malformed or stale request targeting another wish can never modify my receipt.
- As an author who opens the edit quantity form and submits the existing quantity unchanged, I want the operation to succeed cleanly without triggering unnecessary notifications to givers.
- As an author opening an edit or cancel prompt for a receipt that was already removed (or on an archived wishlist), I want a clear refusal explaining why the action cannot proceed.

## Functional Requirements

### FR-1. Idempotent Replay and Conflict Detection

- **FR-1.1 (Replay):** Repeating a receipt cancellation or a receipt quantity correction with the same idempotency key and identical request payload (in both programmatic and UI flows) must return the original success response without re-executing the mutation, altering the wish's received quantity again, or creating duplicate giver notifications.
- **FR-1.2 (Conflict):** Reusing a previously committed idempotency key with a different payload (e.g., a different quantity on correction, or a mismatched operation) must be rejected with a conflict error, leaving the receipt and wish state unchanged.

### FR-2. Cross-Item and Cross-Wishlist Receipt Isolation

- **FR-2.1:** Attempting to cancel or correct a valid receipt record under a different wish than the one it belongs to must be refused as "receipt not found".
- **FR-2.2:** Attempting to cancel or correct a valid receipt record under a different wishlist than the one its wish belongs to must be refused as "receipt not found".
- **FR-2.3:** In all cross-item or cross-wishlist refusal cases, the target receipt record and its owning wish must remain completely unmodified.

### FR-3. No-Op Quantity Correction

- **FR-3.1:** Submitting a receipt quantity correction with the same quantity as the receipt's current quantity (via both programmatic and UI flows) must succeed and leave the receipt record, the wish's received quantity, and active/gifted visibility unchanged.
- **FR-3.2:** A no-op quantity correction must not generate giver change notifications.

### FR-4. Refusal Responses on Opening Edit and Cancel Prompts

- **FR-4.1 (Missing or concurrently deleted receipt):** Requesting the edit prompt or cancel confirmation prompt for a receipt that does not exist (or belongs to another wish) must return a "not found" refusal with the appropriate refusal reason.
- **FR-4.2 (Archived wishlist):** Requesting the edit prompt or cancel confirmation prompt for a receipt on an archived wishlist must return a conflict/blocked refusal indicating the operation is not permitted on an archived list.

## Non-Functional Requirements

- **NFR-1:** All new automated tests must be deterministic, isolated, and include explicit bounded execution timeouts consistent with repository testing standards.
- **NFR-2:** Verification must run cleanly against the repository's standard test suite without modifying unrelated tests or production behavior.

## Definition of Done

- Automated tests cover idempotency replay and conflict for both cancellation and quantity correction across programmatic and UI flows.
- Automated tests cover cross-item and cross-wishlist `receipt_id` isolation for both cancellation and quantity correction.
- Automated tests cover no-op quantity correction across both programmatic and UI flows.
- Automated tests cover refusal responses (`receipt_not_found` and archived-list refusal) when opening edit and cancel prompts.
- All new and existing relevant tests pass within the repository quality gate.

## Task Description

This task addresses item #3 of the follow-up tasks in `ai-tasks/WISHENKA-153/60-tech-debt.md` (Missing Tests items 2–5). It closes the automated test coverage gaps for edge cases of gift receipt cancellation and quantity correction introduced in WISHENKA-153.

## Q&A

- **Why are these tests needed from a business perspective?**
  Without automated verification of retries, cross-wish isolation, no-op edits, and stale/archived prompt refusals, regressions in these edge cases could cause silent double-cancellations, duplicate giver notifications, cross-wish data corruption, or broken UI error handling.
- **Are production code changes expected?**
  No feature changes are requested; this is a test-coverage task. Production code should only be touched if automated verification uncovers a genuine bug violating the stated requirements.
