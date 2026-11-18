# WISHENKA-153: Undo and Correction of Gift Receipt

Programming language for implementation: **Python 3.12+** (FastAPI backend and Jinja2/HTMX web
routes), **JavaScript** (classic script), **CSS**. Recorded in `00-roadmap.md`.

## Goals

When gift receipt was specified and built (WISHENKA-22, WISHENKA-23, WISHENKA-24), every receipt
act was made final and irreversible (WISHENKA-22 Q9, assumption C). In real usage an author can
mistakenly tap the wrong quantity (for example, marking 3 units received instead of 1) or record
receipt on the wrong wish. Today there is no way to undo or fix that mistake: the wish may
disappear from the active list prematurely, givers may stop booking it, and «Подаренные» shows an
inaccurate history.

This task resolves the open product decisions from WISHENKA-22 Q9 / tech-debt item N1 and
delivers the ability to undo or correct a receipt act in both the backend business rules and the
«Подаренные» screen.

The business value:

- **Error recovery without data loss:** Authors can cancel a mistaken receipt record or fix its
  quantity without deleting the wish or losing the original receipt date.
- **Honest active list:** Undoing or reducing a receipt returns the unreceived units to the active
  list (unless the unreceived part was archived), so givers can book what the owner still wants.
- **Fair giver coordination:** Givers with open promises are informed when a receipt is undone or
  corrected downward, and any over-booked state («перебронь») is automatically relieved if the
  total of received and occupied units drops back within the requested quantity.
- **Surprise preserved:** Undoing or correcting a receipt never reveals to authors or recipients
  whether any promises exist, how many units are booked, or whether any giver was notified.

## Scope

### In scope

- Product decisions on:
  - what operations are available on a receipt record (cancel/undo and quantity correction);
  - how dated receipt records behave on undo and correction;
  - how already-sent notifications and new notifications to givers behave;
  - how the over-booked state («перебронь») and open promises behave;
  - how wish visibility across the active list, «Подаренные», and the archive behaves.
- Backend business rules for cancelling a receipt record and correcting a receipt record's
  quantity, including authorization, concurrency, state transitions, and giver notifications.
- Mini App UI on the «Подаренные» screen allowing authors to cancel or correct a receipt record,
  with clear confirmation and privacy-safe feedback.

### Out of scope

- Recalling, deleting, or editing Telegram bot messages that were already sent to givers.
- Automatically reopening promises that a giver already cancelled after an earlier receipt
  notice.
- Editing general wish fields (title, description, link, price, requested quantity) from the
  «Подаренные» screen.
- Changing the rules for who may record receipt (co-author/recipient rule, WISHENKA-154) or
  notification settings screens (WISHENKA-34).
- New metrics exporters (WISHENKA-84).

## Main Business Entities

- **Wish**: an item on a list with a requested quantity (default 1 when unstated).
- **Receipt record**: a dated record of a single receipt act («N units received on date D»). A
  wish can have multiple receipt records over time.
- **Received quantity**: the sum of quantities across all active (non-cancelled) receipt records
  of a wish.
- **Remaining quantity**: `requested quantity - received quantity`.
- **Promise**: a giver's open booking (intended or purchased) of some units of a wish. Promises
  remain independent of receipt records.
- **Occupied quantity**: the sum of units in open promises on the wish.
- **Free quantity**: `max(0, requested quantity - received quantity - occupied quantity)`.
- **Over-booked state («перебронь»)**: the state where `received quantity + occupied quantity >
  requested quantity` (`free quantity = 0`).

Roles: **Author** (list owner, admin, or co-author/member with edit rights), **Gifter**,
**Recipient**, **Anonymous viewer**.

## User Stories

- As an author who accidentally marked a wish as received (or entered too high a quantity), I want
  to cancel that receipt record or reduce its quantity from «Подаренные», so that the wish returns
  to my active list with the right remaining quantity and my gifted history stays accurate.
- As an author who entered too low a quantity on an existing receipt record, I want to correct
  that record's quantity upward (within the remaining quantity) while keeping its original date, so
  that the dated history reflects when the gift actually arrived.
- As an author viewing an archived list, I expect «Подаренные» to remain read-only so I do not
  accidentally modify historical records of an archived list.
- As a gifter holding an open promise on a wish whose receipt was cancelled or reduced, I want to
  be notified that the receipt mark was cancelled or corrected, so I know the gift may still be
  needed and can keep or adjust my promise.
- As a gifter on a wish that was in an over-booked state («перебронь»), I want the wish to become
  bookable again automatically if undoing or reducing a receipt brings `received + occupied` back
  below the requested quantity.
- As a recipient, I want cancelling or correcting a receipt to reveal nothing about promises,
  givers, or notifications, so the surprise stays intact.

## Functional Requirements

### FR-1. Who may undo or correct a receipt, and when

- FR-1.1. Only an **author** of the list (owner, admin, or member with edit rights) may cancel or
  correct a receipt record. A gifter or anonymous viewer may not.
- FR-1.2. Cancellation or correction is allowed only when the **list is active** (not archived and
  not deleted). On an archived or deleted list, the operation is refused with a clear business
  reason.
- FR-1.3. Cancellation or correction is allowed on a wish whose unreceived part is archived (a
  partly received wish where the author archived the remainder), as long as the list itself is
  active.
- FR-1.4. Legacy receipt records (created by back-fill during earlier migration, with approximate
  dates) can be cancelled or corrected in the same way as regular receipt records.

### FR-2. Cancelling (undoing) a receipt record

- FR-2.1. An author may cancel any single receipt record of a wish from «Подаренные».
- FR-2.2. Cancelling a receipt record removes that record from the wish's receipt history and
  decreases the wish's received quantity by that record's quantity.
- FR-2.3. If the wish's total received quantity becomes zero, the wish leaves «Подаренные». If
  other receipt records remain (`received quantity > 0`), the wish stays in «Подаренные» with
  the updated total and remaining records.
- FR-2.4. If the wish's unreceived part is **not archived**, decreasing the received quantity
  makes `remaining quantity > 0`:
  - If the wish was previously fully received (and therefore absent from the active list), it
    **returns to the active list** with the updated remaining quantity.
  - If the wish was already on the active list (partly received), its remaining quantity increases
    accordingly.
- FR-2.5. If the wish's unreceived part **is archived**, the wish stays in the archive with its
  increased remaining quantity and does **not** automatically move back to the active list.

### FR-3. Correcting the quantity of a receipt record

- FR-3.1. An author may edit the quantity of an existing receipt record from «Подаренные».
- FR-3.2. The new quantity must be a positive integer (`>= 1`) and must not cause the wish's total
  received quantity to exceed its requested quantity (i.e., `new_record_quantity <=
  current_record_quantity + remaining_quantity`).
  - Zero or negative quantities are refused (to remove a record completely, the author uses the
    cancel/undo action; if the UI allows entering 0 or confirms cancellation, the business rule
    treats it as FR-2 cancellation only if explicitly confirmed as cancellation, never silently).
  - Exceeding the requested quantity is refused with a clear business reason naming only the
    allowed maximum (never revealing booked quantities).
- FR-3.3. Correcting a receipt record's quantity **preserves the original date** of that receipt
  record.
- FR-3.4. If the corrected quantity equals the current quantity (a no-op), no state changes and no
  notifications are sent.
- FR-3.5. Downward correction (`new_quantity < old_quantity`) applies the same visibility and
  archive rules as FR-2.4 and FR-2.5 (returning a previously fully received non-archived wish to
  the active list).
- FR-3.6. Upward correction (`new_quantity > old_quantity`) applies the same visibility rules as
  recording an additional receipt: if total received quantity reaches `requested quantity`, the
  wish leaves the active list and becomes fully received.

### FR-4. Effect on promises and the over-booked state («перебронь»)

- FR-4.1. Cancelling or correcting a receipt record **never** creates, modifies, cancels, or
  reopens any giver promise. Promises remain independent of receipt records.
- FR-4.2. When received quantity decreases, `free quantity = max(0, requested - received -
  occupied)` is recalculated:
  - If `received + occupied` drops below `requested`, the over-booked state **ends automatically**:
    `free quantity > 0`, and givers can create new promises or raise existing ones up to `free
    quantity`.
  - If `received + occupied` remains `>= requested`, `free quantity` stays `0`, and new promises
    or raising existing promises remain blocked.
- FR-4.3. If a wish transitions from fully received back to partly received (or unreceived), the
  «gift received» marker on open promises in the giver cabinet («Мои бронирования») is removed,
  and giver controls on the active wish card become available again (provided the wish is not
  archived).
- FR-4.4. When received quantity decreases, the locked minimum for editing the wish's requested
  quantity (`received + occupied`, WISHENKA-22 FR-2.6) decreases accordingly.

### FR-5. Notifying givers

- FR-5.1. Already-sent Telegram notifications for the original receipt act are **not** recalled or
  deleted.
- FR-5.2. When a receipt record is **cancelled** or **corrected downward** (`new_quantity <
  old_quantity`), every giver who currently holds an **open promise** (intended or purchased) on
  that wish receives one notification through the Telegram bot, subject to their notification
  settings (user-level and list-level override).
- FR-5.3. The downward-correction / cancellation notice states that the author cancelled or
  corrected a receipt mark for the named wish in the named list and invites the giver to review
  their promise.
- FR-5.4. When a receipt record is **corrected upward** (`new_quantity > old_quantity`), givers
  with open promises receive the standard receipt notification (WISHENKA-22 FR-4).
- FR-5.5. **Privacy in notices:** Cancellation/correction notices must follow WISHENKA-22 FR-4.3:
  they must **not** include any quantities (old, new, received, requested, or occupied), must
  **not** name other givers, and must **not** reveal whether the wish is over-booked or whether
  the giver's promise is excess.
- FR-5.6. Givers whose promises are already closed (cancelled), users without an open promise, and
  the wish's recipient (unless they are an author/giver on another wish per WISHENKA-22 CC-18) do
  not receive a notice. A giver with multiple open promises on the same wish receives at most one
  notice per undo/correction act.
- FR-5.7. Failure to deliver a notification never fails, delays, or rolls back the undo or
  correction.

### FR-6. «Подаренные» screen and UX

- FR-6.1. In «Подаренные», each receipt record of a wish displays its date (or approximate-date
  indicator for legacy back-filled records) and quantity, and—when the list is active and the
  viewer is an author—provides controls to **correct the quantity** and **cancel (undo)** the
  receipt record.
- FR-6.2. «Подаренные» remains free of any other editing actions (wishes cannot be edited,
  reordered, or booked from «Подаренные»).
- FR-6.3. Cancelling a receipt record requires explicit confirmation from the author before
  applying the change.
- FR-6.4. After a successful undo or correction:
  - «Подаренные» updates to reflect the removed or updated record (and removes the wish from
    «Подаренные» if its received quantity becomes zero).
  - If the wish is on the active list (or returned to the active list), the active list reflects
    the updated remaining quantity (or restored wish).
- FR-6.5. **Concurrency and stale state:** If two authors act on the same receipt record
  concurrently, or if the record was already cancelled, or if the list was archived/deleted, the
  later action is refused with a clear, privacy-safe message in Russian.
- FR-6.6. **Surprise and privacy:** No control, confirmation prompt, success message, or refusal
  message on «Подаренные» may reveal whether any promises exist, how many units are booked, or
  whether any givers were notified.

## Corner Cases

| # | Situation | Required behavior |
| - | --------- | ----------------- |
| 1 | Wish for 5 units, 1 receipt of 5 (fully received). Author cancels that receipt. | Receipt record removed, `received = 0`, wish leaves «Подаренные» and returns to active list with remaining 5. Open-promise givers notified; cabinet "received" marker removed. |
| 2 | Wish for 5, 2 receipts: 2 on Nov 10, 3 on Nov 12. Author cancels the Nov 12 receipt. | Nov 12 record removed, Nov 10 record stays (`received = 2`). Wish returns to active list with remaining 3 and stays in «Подаренные» with 2. |
| 3 | Wish for 5, 3 promised by A, 2 by B. Author mistakenly received 2 (over-booked: 2 + 5 = 7 > 5). Author cancels the receipt of 2. | `received = 0`, `occupied = 5`, over-booked state ends (`free = 0` because 5 are booked, no excess). A and B are notified; if A later cancels 1, `free` becomes 1. |
| 4 | Wish for 5, 3 promised by A. Author mistakenly received 4 (over-booked: 4 + 3 = 7 > 5). Author corrects receipt from 4 down to 1. | `received = 1`, `occupied = 3`, `free = 1`. Over-booked state ends automatically; 1 unit is now free for new bookings. Original receipt date is preserved. A is notified. |
| 5 | Wish for 5, 4 promised by A. Author mistakenly received 4 (over-booked: 4 + 4 = 8 > 5). Author corrects receipt from 4 down to 3. | `received = 3`, `occupied = 4`, sum is 7 > 5. Still over-booked (`free = 0`), new bookings still blocked, excess reduced from 3 to 2. A is notified. |
| 6 | Wish for 5, 2 received, remaining 3 archived by owner (FR-3.8). Author cancels the receipt of 2. | Receipt removed, wish leaves «Подаренные». Wish remains in the archive with remaining 5 (does not jump back to active list). |
| 7 | List is archived. Author opens «Подаренные» and tries to cancel or correct a receipt. | Undo/correct controls are not offered (or refused with a business reason if invoked). «Подаренные» is read-only on an archived list. |
| 8 | Author corrects a receipt from 1 up to 3 on a wish for 5. | Allowed (3 <= 5). Original date preserved. Wish stays active with remaining 2. Standard receipt notice sent to open-promise givers. |
| 9 | Author tries to correct a receipt to 0, negative, or above `requested_quantity`. | Refused with a clear business reason (never revealing booked quantities). |
| 10 | Giver B cancelled their promise after the mistaken receipt notice; Giver A kept theirs. Author cancels the receipt. | Only A receives the cancellation notice. B's cancelled promise stays closed and B receives nothing. |
| 11 | Two authors cancel the same receipt record at the same time. | First succeeds; second is refused with a clear message that the receipt record is no longer present. |
| 12 | Author corrects a receipt to the exact same quantity. | No-op: no history change, no notifications sent. |
| 13 | Wish has a legacy back-filled receipt record (approximate date). Author corrects its quantity. | Allowed; approximate-date flag/meaning is preserved, quantity is updated. |

## Definition of Done

1. All product decisions from WISHENKA-22 Q9 / tech-debt N1 (operations, dated records,
   notifications, over-booked state, archive interaction) are documented in Q&A with no open
   ambiguities.
2. Backend supports cancelling a receipt record and correcting a receipt record's quantity with
   all rules FR-1 to FR-5 and corner cases 1–13 enforced.
3. Undo and downward correction end the over-booked state automatically when `received + occupied
   <= requested`, and remove the "received" marker in the giver cabinet when a wish is no longer
   fully received.
4. Givers with open promises are notified on undo/downward correction (without quantities or
   other-giver leaks) and on upward correction; failed delivery never blocks the operation.
5. The «Подаренные» screen provides undo (with confirmation) and quantity correction for authors
   on active lists, updates both «Подаренные» and the active list consistently, and keeps
   archived lists read-only.
6. Surprise and privacy invariants hold across all new backend responses, UI fragments,
   confirmations, and notifications (no promise, giver, or booking-count leakage).
7. Automated tests cover all functional requirements, corner cases, concurrency, and surprise/privacy
   invariants.
8. `in-docs/spec.md` (sections 7.2 and 7.3) and `doc/dev/` documentation are updated to reflect
   that receipts can be undone or corrected.

## Non-functional Requirements and Constraints

- **Implementation language:** Python 3.12+ (FastAPI, Jinja2, HTMX), JavaScript, CSS.
- **Surprise & privacy:** Zero leakage of promise existence, giver identity, booked quantities, or
  purchase status to authors or recipients in any response, UI element, confirmation, or refusal
  (the existing edit-form quantity lock from WISHENKA-22 Q12 remains the only known exception).
- **Concurrency & consistency:** Concurrent undo/correction/receipt/promise actions must never
  leave `received_quantity < 0` or `received_quantity > requested_quantity`, or apply a stale
  update to a deleted/already-cancelled receipt record.
- **Delivery resilience:** Notification delivery failures never fail or delay undo/correction.
- **Backward compatibility:** Existing receipt creation, archive split/restore, and promise
  lifecycle rules from WISHENKA-22/23/24 remain intact.

## Task Description

WISHENKA-22 intentionally deferred undoing or correcting a gift receipt (Q9, assumption C) to a
follow-up. WISHENKA-23 and WISHENKA-24 implemented dated receipt records, «Подаренные», and giver
notifications under the assumption that receipts are final.

This story closes that gap by allowing authors to undo or correct mistaken receipt records from
«Подаренные», updating wish availability and the over-booked state cleanly, and notifying
open-promise givers without breaking the surprise principle.

### Assumptions

- **A1.** Cancelling or correcting a receipt is an author-only action on an active list (same
  author roles as recording receipt).
- **A2.** Already-sent Telegram messages cannot be recalled; instead, open-promise givers receive
  a follow-up notice when a receipt is cancelled or corrected downward.
- **A3.** A wish whose unreceived part was archived stays archived when a receipt is undone or
  reduced (the owner must explicitly restore it if they want it back on the active list).

## Q&A

- **Q1. Should the product support both cancelling (undoing) a receipt record and correcting its
  quantity, or only full cancellation?**
  A. Both. Each receipt act is a dated record in «Подаренные». Supporting both **cancel** (remove
  that record) and **correct quantity** (adjust its quantity while keeping its date) lets an author
  fix a typo (e.g., 3 → 2) without losing the original receipt date or having to delete and
  re-create the record.

- **Q2. What happens to the dated receipt record on undo vs. correction?**
  A. On **undo (cancel)**, the receipt record is removed from the wish's history; if no records
  remain (`received = 0`), the wish leaves «Подаренные». On **correction**, the existing record's
  quantity is updated in place and its **original date is preserved** (because the gift arrived on
  that date; only the recorded count was wrong).

- **Q3. What happens to Telegram notifications already sent to givers?**
  A. Already-sent messages are **not** recalled or edited (Telegram delivery is fire-and-forget and
  givers may have already read them). Instead, when a receipt is **cancelled** or **corrected
  downward**, givers who currently hold an **open promise** on that wish receive a new notice
  informing them that the author cancelled or corrected the receipt mark and inviting them to
  review their promise. When a receipt is **corrected upward**, open-promise givers receive the
  standard receipt notice.

- **Q4. What about givers who already cancelled their promise after the mistaken receipt?**
  A. Their promises stay closed (cancelled) and are never reopened automatically. Because they no
  longer hold an open promise, they do not receive the cancellation/correction notice. They may
  create a new promise if free quantity is available.

- **Q5. What happens to the over-booked state («перебронь»)?**
  A. Undoing or reducing a receipt decreases `received_quantity`. If `received_quantity +
  occupied_quantity` drops to or below `requested_quantity`, the over-booked state **ends
  automatically** and `free_quantity > 0` becomes available for new or raised promises. If
  `received + occupied` is still above `requested`, the over-booked state continues with the
  reduced excess. If a fully received wish becomes partly received or unreceived, the «gift
  received» marker disappears from open promises in the giver cabinet.

- **Q6. What if the unreceived part of a partly received wish was archived before the author
  undoes or reduces the receipt?**
  A. The wish remains in the archive with its increased remaining quantity; it does **not**
  automatically return to the active list, because the author explicitly archived the unreceived
  part. If all receipts are cancelled (`received = 0`), the wish leaves «Подаренные» and exists
  only in the archive.

- **Q7. Can an author undo or correct a receipt on an archived list?**
  A. No. Consistent with WISHENKA-22 FR-5.7, «Подаренные» on an archived list is read-only. To
  undo or correct a receipt, the author must first restore the list.
