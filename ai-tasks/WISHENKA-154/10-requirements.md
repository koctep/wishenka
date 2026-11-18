# WISHENKA-154: Product Decisions on Open Privacy and Gift Receipt Visibility Questions

Implementation language: `Markdown (documentation-only; no code changes)`.

## Goals

When gift receipt was specified in `WISHENKA-22`, several product-level questions and working assumptions (assumptions A–D, shortcut E, and open questions Q6, Q8, Q11, Q12) were recorded as unconfirmed so that specification and follow-up work could proceed without blocking. Meanwhile, `WISHENKA-153` already resolved assumption C / Q9 by introducing receipt cancellation and quantity correction.

Leaving the remaining six product points unresolved creates ambiguity across specifications, future UI/backend stories, and existing surprise-invariant exceptions:

- Implementers and reviewers lack a single, authoritative decision record confirming whether receipt and booking remain independent (A), who may record receipt and see «Подаренные» (B, D), and how a purchased promise ends after full receipt (E).
- `in-docs/spec.md` section 16 still lists co-author/recipient rights (Q11) as an open question, and sections 5.5, 6.3, 7.2, and 7.3 do not explicitly reflect the settled answers on public «already gifted» labels (Q6), deleted-list history (Q8), edit-form quantity lock tightening (Q12), and completing a purchased promise (E).
- The existing edit-form quantity-reduction lock (Q12) remains an unaddressed exception to the product's core surprise principle (`specs/00-high.md`, invariant 1).

The business value of this task:

- **Single source of product truth:** Fix clear, unambiguous product decisions for all six open items (i–vi) in one place and reflect them in `in-docs/spec.md`.
- **Uncompromised surprise principle:** Eliminate ambiguity around co-author/recipient permissions and establish the target product rule to remove the edit-form quantity lock leak.
- **Consistent giver lifecycle:** Resolve the contradiction in `in-docs/spec.md` section 7.3 where givers are told they «самостоятельно завершают или отменяют свои брони» while no completion state existed for purchased promises.
- **Zero wasted engineering effort:** Keep this task strictly documentation-only (requirements and specification updates), separating product decisions from code changes so future implementation stories build against settled rules.

## Scope

### In scope

- Recording autonomous, unambiguous product decisions for all six items from `WISHENKA-22/60-tech-debt.md` (item N3 and shortcut E):
  - **(i)** Confirmation / update of assumptions A–D from `WISHENKA-22` (noting that assumption C / Q9 was already superseded by `WISHENKA-153`).
  - **(ii)** Whether givers may see a public «уже подарено» («already gifted») marker or the «Подаренные» history (Q6).
  - **(iii)** Whether «Подаренные» history is preserved after a wishlist is deleted (Q8).
  - **(iv)** Rights and surprise boundaries for a co-author who is simultaneously the recipient of a wish — closing section 16 of `in-docs/spec.md` (Q11).
  - **(v)** Product decision to tighten the existing edit-form quantity-reduction lock that reveals occupied units to authors/recipients (Q12).
  - **(vi)** Product decision on a «завершено» («completed») state for a purchased promise after full receipt (shortcut E / FR-3.6).
- Updating `in-docs/spec.md` (relevant sections including 3, 4.4, 5.5, 6.3, 7.2, 7.3, 11.2, and 16) to reflect these settled product decisions.

### Out of scope

- Any production code, test code, database schema, API, or UI/template changes.
- Implementing the edit-form quantity-lock tightening (decision (v)) or the «completed» promise state (decision (vi)) in code — those belong to follow-up implementation tasks.
- Reopening `WISHENKA-153` (undo/correction of gift receipt, which already closed Q9 / assumption C).
- Notification settings screens (`WISHENKA-34`) or metrics exporters (`WISHENKA-84`).

## Main Business Entities and Roles

- **Wishlist:** A personal or collaborative collection of wishes. Can be active, archived, or deleted.
- **Wish:** An item on a wishlist with a requested quantity (default 1 when unstated), a received quantity, and an unreceived remaining quantity.
- **Promise (Reservation):** A giver's commitment for a number of units of a wish. A promise is open while intended or purchased, and closed when cancelled or completed.
- **Receipt record:** A dated record that the author received N units of a wish. Independent of giver promises and free of giver identity.
- **«Подаренные» (Gifted history):** The read-only view (with undo/correction controls per `WISHENKA-153` on active lists) of wishes with received quantity above zero.

Roles:

- **Owner:** Creator of the wishlist with full management rights over settings, members, and wishes.
- **Administrator:** Co-manager of a collaborative wishlist with rights to manage settings, members, and wishes.
- **Member (Co-author):** Participant of a collaborative wishlist with rights to add, edit, archive, and record receipt for wishes.
- **Author:** Collective term for Owner, Administrator, and Member on a list.
- **Gifter:** A user viewing a shared wishlist who books or purchases wishes.
- **Recipient:** The person for whom a wish is intended (may be the list owner, a collaborative list member, another Telegram user, or a named person without Telegram).

## User Stories

- As a product team, we want all six open receipt-privacy and visibility questions resolved and written into `in-docs/spec.md`, so that implementation teams never have to guess product intent.
- As a gifter viewing a partially received wish, I want to see only the available remainder without seeing how many units were already received, so that I cannot deduce how many units other gifters have booked.
- As a wishlist owner who deletes a list (or my account), I want the gifted history of that list to be deleted together with the list, while archived lists keep their gifted history readable.
- As a co-author on a collaborative wishlist who is also the recipient of a wish, I want to manage my wishes and mark them received normally while still having the surprise protected from me.
- As a recipient editing my own wish's requested quantity, I want the system never to reveal how many units gifters have booked, even when I reduce the quantity.
- As a gifter who purchased a gift that the owner has now marked fully received, I want to explicitly mark my purchased promise as completed («Подарок вручён» / «Завершено») instead of having to cancel it or leave it open indefinitely in my cabinet.

## Functional Requirements

### FR-1. Confirmation of Assumptions A–D (Item i)

- **FR-1.1 (Assumption A confirmed):** Promise and receipt remain independent facts. Recording receipt never automatically closes, cancels, or modifies any giver's promise. The over-booked state (`received + occupied > requested`) remains valid and is resolved by givers adjusting their own promises (or by the owner increasing requested quantity or undoing/reducing receipt per `WISHENKA-153`).
- **FR-1.2 (Assumption B confirmed):** Any author of the list (owner, administrator, or member/co-author on a collaborative list) may record receipt (and undo/correct receipt per `WISHENKA-153`), including when the author is also the recipient of that wish (see FR-4).
- **FR-1.3 (Assumption C superseded):** Assumption C («receipt is final») from `WISHENKA-22` is formally retired and replaced by the settled behavior of `WISHENKA-153`: authors may cancel or correct receipt records on active lists in «Подаренные».
- **FR-1.4 (Assumption D confirmed):** «Подаренные» is visible only to authors of the list (owner, administrators, and members) and is never visible to gifters or anonymous viewers.

### FR-2. No Public «Already Gifted» Label for Gifters (Item ii / Q6)

- **FR-2.1:** Gifters and anonymous viewers must **not** see «Подаренные», receipt dates, received quantities, or a public «уже подарено» («already gifted») badge on wish cards or lists.
- **FR-2.2:** For a partially received active wish, gifters continue to see only the available remainder (or «Забронировано» when the available remainder is zero).
- **FR-2.3:** For a fully received wish, the wish leaves the active list for everyone; gifters who already hold an open promise on that wish see the «received» indicator exclusively inside their personal «Мои бронирования» cabinet and receive the personal receipt notice.

### FR-3. Gifted History on List Deletion (Item iii / Q8)

- **FR-3.1:** Deleting a wishlist permanently removes its «Подаренные» gifted history together with the wishlist and its wishes. No standalone long-term gifted history is retained after list deletion.
- **FR-3.2:** Archiving a wishlist preserves its «Подаренные» history in read-only mode so authors can keep a record of received gifts without keeping the list active.

### FR-4. Co-Author Who Is Also the Recipient (Item iv / Q11, Spec Section 16)

- **FR-4.1:** On a collaborative wishlist, an author (administrator or member) who is also designated as the recipient of a wish retains full author rights on that wish: editing, archiving/restoring, recording receipt, and viewing/managing «Подаренные» (including undo/correction per `WISHENKA-153`).
- **FR-4.2:** The surprise principle applies without exception to co-author recipients: no screen, action, refusal, or notification shown to them for a wish where they are the recipient may reveal booking existence, booked quantities, giver identities, or purchase status.
- **FR-4.3:** Role separation on the same wish: a co-author who is the recipient of a wish cannot act as a gifter on that wish (cannot book their own wish). On other wishes in the same collaborative list where someone else is the recipient, they act as a normal gifter and receive gifter notices.
- **FR-4.4:** Open question 2 in `in-docs/spec.md` section 16 («Как разграничивать права совместного редактора, который одновременно является получателем подарка») is closed and moved to agreed requirements.

### FR-5. Tightening the Edit-Form Quantity-Reduction Lock (Item v / Q12)

- **FR-5.1:** The target product rule removes the surprise exception in the wish edit form: editing a wish's requested quantity must **never** display or enforce a floor based on units occupied by giver promises.
- **FR-5.2:** An author may reduce a wish's requested quantity down to `max(1, received_quantity)`. Reduction below `received_quantity` remains refused because the author already recorded those receipts (no booking leak).
- **FR-5.3:** If reducing the requested quantity causes `received_quantity + occupied_quantity > new_requested_quantity`, the wish enters the standard over-booked state: existing promises are not cancelled automatically, new promises and upward edits are blocked, and givers with open promises are notified so they can adjust or cancel their promises.
- **FR-5.4:** Because `WISHENKA-154` is documentation-only, the code and UI implementation of FR-5.1–FR-5.3 is deferred to a dedicated follow-up implementation task, while `in-docs/spec.md` documents the target rule and notes the transition.

### FR-6. «Completed» State for a Purchased Promise After Full Receipt (Item vi / Shortcut E)

- **FR-6.1:** Receiving a gift (even fully) still never closes a promise automatically (FR-1.1).
- **FR-6.2:** When a wish is fully received, a gifter holding a **purchased** promise on that wish is given an explicit action to **complete** («Завершить» / «Подарок вручён») that promise, in addition to the existing option to cancel it.
- **FR-6.3:** Completing a purchased promise moves it to a closed «Завершено» state: it no longer occupies units on the wish, no longer counts toward active promises in «Мои бронирования», and no longer receives future receipt/undo notices.
- **FR-6.4:** An intended (not yet purchased) promise on a fully received wish cannot be marked completed directly — the gifter may only cancel it, reduce it, or mark it purchased first.
- **FR-6.5:** Because `WISHENKA-154` is documentation-only, the code and UI implementation of FR-6.2–FR-6.4 is deferred to a dedicated follow-up implementation task, while `in-docs/spec.md` documents the target rule.

## Non-functional Requirements and Constraints

- **Implementation language:** `Markdown (documentation-only; no code changes)`.
- **Surprise invariant:** All decisions uphold `specs/00-high.md` invariant 1 (surprise) and invariant 4 (privacy). Decision (v) eliminates the last known exception in the edit form.
- **No code or schema design:** This task updates requirements and `in-docs/spec.md` only; no Python, HTML, JS, CSS, or SQLite changes are permitted.
- **Traceability:** Each decision in `in-docs/spec.md` must remain clear, concise, and free of internal task keys or implementation details.

## Definition of Done

1. All six open product decision items (i–vi) are clearly documented with unambiguous business decisions and rationale in `10-requirements.md`.
2. `in-docs/spec.md` is updated to reflect all six decisions across the relevant sections (roles/collaborative work, wish editing, booking visibility, purchase/receipt/promise lifecycle, data deletion, and section 16 closed questions).
3. `in-docs/spec.md` section 16 no longer lists the co-author/recipient question as open.
4. No production code, tests, or `doc/dev/` files are modified (unless Step 8 of this task records planned/spec alignment in `doc/dev/` if applicable).
5. Follow-up implementation work for decisions (v) and (vi) is clearly identified for Step 7 tech-debt / Jira follow-ups.

## Task Description

`WISHENKA-22` established the gift receipt specification under four unconfirmed assumptions (A–D) and left several product questions (Q6, Q8, Q9, Q11, Q12, and shortcut E on purchased promise completion) open for a product-owner decision. `WISHENKA-153` subsequently resolved Q9 (replacing assumption C with undo and quantity correction).

This task (`WISHENKA-154`) serves as the single, code-free decision record for the remaining six items (i–vi), aligning `in-docs/spec.md` so that both the current product behavior and the target rules for follow-up implementation tasks are unambiguous.

## Q&A

- **Q1 (Item i). Are assumptions A–D from `WISHENKA-22` confirmed?**
  A. **A, B, and D are confirmed; C is superseded by `WISHENKA-153`.**
  - **A (confirmed):** Receipt and promise are independent; receipt never closes or modifies a promise, and the over-booked state is valid.
  - **B (confirmed):** Any list author (owner, administrator, or member/co-author) may record receipt, including a co-author who is the recipient (see Q4).
  - **C (superseded):** Receipt is no longer final; `WISHENKA-153` introduced cancellation and quantity correction of receipt records on active lists.
  - **D (confirmed):** «Подаренные» is strictly for list authors, never for gifters.

- **Q2 (Item ii / Q6). Should gifters see a public «уже подарено» («already gifted») label or «Подаренные» history?**
  A. **No.** «Подаренные» remains author-only, and active wish cards do not show a public «already gifted» badge or received count to gifters. On a partially received wish, showing the received count alongside the available remainder would let a gifter calculate how many units other gifters booked (violating the booking-privacy rule of `WISHENKA-22` FR-4.3 / Q5). Fully received wishes leave the active list automatically, while gifters with open promises on them see the received marker in «Мои бронирования».

- **Q3 (Item iii / Q8). Should gifted history be preserved after a wishlist is deleted?**
  A. **No.** Deleting a wishlist permanently deletes its «Подаренные» history along with the list. Authors who want to keep a read-only record of received gifts without keeping the list active should archive the wishlist instead (archived lists keep «Подаренные» readable). This also matches the personal-data deletion rules in `in-docs/spec.md` section 11.2.

- **Q4 (Item iv / Q11). How are rights and surprise handled for a co-author who is also the recipient (spec section 16)?**
  A. **Full author rights with strict surprise protection and no self-booking.** A co-author (administrator or member) who is the recipient of a wish may edit, archive/restore, record receipt, and undo/correct receipt for that wish. All screens, refusals, and notices for that wish remain strictly recipient-safe (no booking or giver data shown). They cannot book a wish where they are the recipient, but may act as a normal gifter on other wishes in the same collaborative list where someone else is the recipient. Section 16 of `in-docs/spec.md` is updated to move this question to closed requirements.

- **Q5 (Item v / Q12). Should the existing edit-form quantity-reduction lock (which reveals occupied units) be tightened?**
  A. **Yes.** Authors should be able to reduce a wish's requested quantity down to `max(1, received_quantity)` without seeing or being blocked by units occupied by giver promises. If the reduction causes `received + occupied > requested`, the wish enters the standard over-booked state and open-promise givers are notified to adjust or cancel their promises. Because `WISHENKA-154` has no code changes, the implementation is tracked as a follow-up task.

- **Q6 (Item vi / Shortcut E). Should a purchased promise have a «завершено» («completed») state after full receipt?**
  A. **Yes.** While receipt never closes a promise automatically (assumption A), a gifter holding a **purchased** promise on a fully received wish should be able to explicitly mark it **completed** («Завершено» / «Подарок вручён») rather than being forced to «cancel» a gift they actually gave or leave it open in their cabinet forever. Completing a promise closes it (freeing occupied units and removing it from active cabinet counts). Implementation is tracked as a follow-up task.

Sources: `specs/00-high.md`, `in-docs/spec.md` (sections 3, 4.4, 5.5, 6.3, 7.2, 7.3, 11.2, 16), `ai-tasks/WISHENKA-22/10-requirements.md`, `ai-tasks/WISHENKA-22/60-tech-debt.md`, and `ai-tasks/WISHENKA-153/10-requirements.md`.
