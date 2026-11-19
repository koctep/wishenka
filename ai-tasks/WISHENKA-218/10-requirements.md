# WISHENKA-218: Remove Occupied-Units Floor Leak in Wish Quantity Editing (FR-5 / Q12)

Implementation language: `Python`

## Goals

A core product invariant of the Telegram Wishlist Service (`specs/00-high.md`, Invariant 1) is preserving the surprise for the gift recipient: authors and recipients must never learn whether a wish has been booked, how many units are booked, or who booked them.

Currently, wish editing enforces a quantity-reduction floor based on units occupied by giver promises. When an author attempts to reduce a wish's requested quantity below the number of occupied units (or views the edit form's minimum allowed quantity), the system reveals that givers have booked units and how many units are occupied—breaking the surprise invariant.

The product decision settled in `WISHENKA-154` (`FR-5` / Q12, documented in `in-docs/spec.md` section 5.5) removes this last surprise exception in the edit flow. Implementing this task delivers:

- **Uncompromised surprise protection:** Authors and recipients can edit wish quantities without any UI hint, minimum-value constraint, or validation error ever revealing giver booking activity.
- **Consistent over-booked lifecycle:** Reducing requested quantity below `received + occupied` transitions the wish cleanly into the existing over-booked state (`in-docs/spec.md` section 7.3), letting givers resolve conflicts autonomously without cancelling promises behind their backs.
- **Spec-to-code alignment:** Brings the running application into compliance with the target rules already documented in `in-docs/spec.md` section 5.5.

## Task Description

### Problem

When editing a wish's requested quantity, the current behavior prevents reducing the quantity below the sum of received units and occupied promise units (or exposes occupied promise counts as a floor). This leaks booking information to the wish author/recipient.

### Scope

#### In Scope

- Removing any edit-form display, minimum-value restriction, or validation floor based on units occupied by giver promises.
- Allowing an author to reduce a wish's requested quantity down to `max(1, received_quantity)`, and rejecting reductions below `received_quantity` (or below `1`).
- Transitioning the wish into the standard over-booked state when `received_quantity + occupied_quantity > new_requested_quantity`, without automatically cancelling or altering existing open promises.
- Notifying givers who hold open promises (intended or purchased) on that wish when a quantity reduction causes `received_quantity + occupied_quantity > new_requested_quantity`, so they can adjust or cancel their promises.
- Ensuring all edit responses, validation messages, and form controls leak zero booking information to authors or recipients.

#### Out of Scope

- Implementing the «Завершено» («Completed») state for purchased promises on fully received wishes (`FR-6` / Shortcut E, tracked separately in `WISHENKA-219`).
- Changing the existing wishlist-level archival warning setting (`in-docs/spec.md` section 5.5).
- Changing gift receipt recording, undo, or correction flows (`WISHENKA-153`).
- Changing giver booking, purchase, or cancellation mechanics outside of the over-booked state rules already defined in `in-docs/spec.md` section 7.3.

### Constraints

- **Programming language:** `Python`.
- **Surprise & Privacy invariants (`specs/00-high.md`):** No screen, form field, validation error, or feedback shown to an author or recipient may disclose the existence of promises, occupied unit counts, or giver identities.
- **Promise autonomy (`in-docs/spec.md` section 7.3):** Reducing requested quantity must never automatically cancel, reduce, or close any giver's promise.

## Main Business Entities and Roles

### Entities (Business Perspective)

- **Wishlist:** A personal or collaborative collection of wishes.
- **Wish:** An item in a wishlist with a `requested_quantity` (integer >= 1), `received_quantity` (integer >= 0, recorded by authors), and `occupied_quantity` (sum of units held by open giver promises).
- **Promise (Reservation):** A giver's open commitment (in `intended` or `purchased` state) for a positive number of units of a wish.
- **Over-booked State:** A valid state of a wish where `received_quantity + occupied_quantity > requested_quantity`. While in this state, new promises and upward quantity edits on promises are blocked, whereas givers may still reduce, cancel, or mark purchased their existing promises.
- **Giver Notification:** A personal message sent to a giver holding an open promise when the wish becomes over-booked due to a requested-quantity reduction.

### Roles

- **Author:** Owner, administrator, or member (co-author) of a wishlist with rights to edit wishes on that list.
- **Recipient:** The intended recipient of the wish (may also be the author or a co-author).
- **Gifter:** A user who holds an open promise on the wish or views the shared wishlist to book gifts.

## User Stories

- **As a wish author/recipient**, I want to reduce the requested quantity of my wish down to `max(1, received_quantity)` without seeing or being blocked by how many units gifters have booked, so that my surprise is never spoiled.
- **As a wish author/recipient**, if I try to reduce the requested quantity below the number of units I have already marked as received, I want a clear validation error referencing only the received quantity, so that I understand why the edit was rejected without any booking data being exposed.
- **As a gifter with an open promise**, when the author reduces a wish's requested quantity such that `received_quantity + occupied_quantity > new_requested_quantity`, I want my promise to remain intact and to receive a notification about the over-booked situation, so that I can decide whether to adjust or cancel my promise.
- **As a gifter viewing an over-booked wish**, I want new bookings and increases to existing bookings to be blocked while still being able to reduce, cancel, or mark my existing promise as purchased, so that no additional over-booking occurs while existing commitments are resolved.

## Functional Requirements

- **FR-1 (No occupied-units floor in wish editing):**
  - Editing a wish's requested quantity must never display, enforce, or hint at a lower bound derived from units occupied by giver promises.
  - Edit form controls (such as minimum allowed values) and server-side validation must depend solely on `1` and `received_quantity`.
- **FR-2 (Minimum allowed requested quantity):**
  - An author may reduce `requested_quantity` down to `max(1, received_quantity)`.
  - Any attempt to set `requested_quantity` below `max(1, received_quantity)` must be rejected with a clear message that references only `received_quantity` (or the minimum of 1), never mentioning promises or occupied units.
- **FR-3 (Transition to over-booked state):**
  - When a valid reduction sets `new_requested_quantity` such that `received_quantity + occupied_quantity > new_requested_quantity`, the wish enters the over-booked state (`in-docs/spec.md` section 7.3).
  - Existing open promises are preserved untouched (not automatically cancelled, reduced, or closed).
  - While the wish remains over-booked, new promises and upward quantity edits on existing promises are disallowed; givers may still reduce, cancel, or mark their existing promises as purchased.
- **FR-4 (Over-booked notifications to open-promise givers):**
  - When a requested-quantity reduction causes `received_quantity + occupied_quantity > new_requested_quantity`, each giver holding an open promise (intended or purchased) on that wish is sent a notification informing them that the wish's requested quantity was reduced and they may need to adjust or cancel their promise.
  - Notifications must not expose other givers' identities or booking details.
  - A notification delivery failure must not prevent or roll back the wish quantity update.
  - If the reduction does not cause `received_quantity + occupied_quantity > new_requested_quantity`, no over-booking notification is sent.
- **FR-5 (Zero booking leakage to authors/recipients):**
  - After saving a reduced quantity (whether or not it caused an over-booked state), the author/recipient response must be identical in structure and content regardless of whether any promises exist on the wish.

## Non-functional Requirements and Constraints

- **Implementation language:** `Python`.
- **Consistency:** Concurrent wish edits and giver bookings must not allow `requested_quantity` to end up below `received_quantity` or allow new bookings when `received_quantity + occupied_quantity >= requested_quantity`.
- **Privacy & Surprise:** Strictly compliant with `specs/00-high.md` Invariant 1 (surprise) and Invariant 4 (privacy).
- **No regressions:** Existing wish editing fields (title, description, link, price, etc.), receipt recording, and over-booked state handling from `WISHENKA-22` / `WISHENKA-153` must continue to work as specified.

## Definition of Done

1. An author can reduce a wish's requested quantity down to `max(1, received_quantity)` even when giver promises occupy more units than `new_requested_quantity`.
2. Attempting to reduce requested quantity below `max(1, received_quantity)` is rejected without revealing any booking information.
3. No UI element, validation message, or response shown to an author or recipient reveals whether units are booked or how many units are booked.
4. Reducing requested quantity such that `received_quantity + occupied_quantity > new_requested_quantity` preserves all existing open promises, blocks new promises and upward edits while over-booked, and notifies givers with open promises.
5. Automated tests cover all scenarios above (normal reduction with promises, rejection below `received_quantity`, over-booked transition, giver notifications, and zero booking leakage to authors/recipients).

## Q&A

- **Q1 (from `WISHENKA-154` / Q12): What happens if `new_requested_quantity` equals `received_quantity` while open promises exist?**
  - **A:** `new_requested_quantity == received_quantity` (when `received_quantity >= 1`) is allowed. Since `occupied_quantity > 0`, `received_quantity + occupied_quantity > new_requested_quantity` holds, so the wish enters the over-booked state and open-promise givers are notified.
- **Q2: Are givers notified if the author reduces `requested_quantity` but `received_quantity + occupied_quantity <= new_requested_quantity`?**
  - **A:** No. There is no conflict with existing promises, so no over-booking notification is needed.
- **Q3: Are closed (cancelled) promises notified?**
  - **A:** No. Only givers with **open** promises (intended or purchased) are notified.
