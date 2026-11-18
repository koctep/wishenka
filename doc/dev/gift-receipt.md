# Gift Receipt and the «Подаренные» Section

> **Status: BACKEND IMPLEMENTED by WISHENKA-23; Mini App UI IMPLEMENTED by WISHENKA-24 (see
> [Mini App UI](#mini-app-ui-wishenka-24)); Undo & Correction IMPLEMENTED by WISHENKA-153;
> Dialog Accessibility & Mobile UX IMPLEMENTED by WISHENKA-161.**

The backend is the receipt command, the gifted read, the derived views, the receipt history, the
giver notice path (outbox, worker, sender) and the migrations. The Mini App page layer
(WISHENKA-24) calls the domain service directly through its own HTML routes and does not call the
two JSON routes. It adds the receipt dialog, the owner card, the «Подаренные» section and the
cabinet marker, and changes no domain rule, storage, migration or JSON interface.

Sources of truth, in order: `in-docs/spec.md` (sections 7.2, 7.3), `ai-tasks/WISHENKA-22/`
(specification), `ai-tasks/WISHENKA-23/20-architecture.md` (design, governs where it differs from
the WISHENKA-22 draft) and `50-observability.md`. Where this file and the code differ, the code
wins.

## Overview

An author records that a gift arrived in real life. The product keeps **receipt** (the author's
statement about the real world) and **promise** (a giver's statement about intent) as independent
facts. It never reconciles them on the giver's behalf, because it cannot know which giver's gift
came.

### Rules as implemented

- **Who and when.** A member of the list records receipt: the owner, an admin or a member
  (`ctx.is_member` in `WishlistService.record_item_fulfillment`). A giver who is not a member and
  an anonymous caller cannot. The wish must be active on an active list. The quantity is from 1 to
  the remaining quantity. No giver is named and none is needed: an unpromised gift can be
  recorded.
- **Partial receipt.** Each act adds to `received_quantity`. The wish stays active with the
  reduced remaining quantity, and its received part is in the gifted read.
- **Full receipt.** The act that brings received up to requested makes the wish fully received
  (`WishItem.is_fully_received`). It leaves the active list and is returned only by the gifted
  read. No new promise can be made on it (the free quantity is zero).
- **Free quantity.** `max(0, requested - received - occupied)`. Unchanged.
- **Receipt never touches promises.** It does not cancel, change or mark purchased any
  reservation. A purchased promise is treated like an intended one for notices.
- **Over-booked state.** After receipt `received + occupied` may exceed `requested`. This is
  legal and nothing in the code resolves it.
- **Archive split.** `archive_wish_item` sets `is_archived` only. A wish with received units that
  is archived is a member of the archive (`is_in_archive`) while it still has remaining quantity,
  and its received part stays in the gifted read. `restore_wish_item` brings the wish back at the
  tail of the active order. A fully received wish is refused by both with `NothingRemainingError`
  (HTTP 409).
- **Gifted read is not the archive.** It lists wishes with `received_quantity > 0`, for members
  only, with receipt entries and no promise or giver field.
- **Surprise.** Receipt results, refusals, the gifted read and the notice carry no promise,
  giver, booked quantity or purchase fact. The one known exception in current code is the legacy
  quantity-reduction lock in the edit form; `WISHENKA-154` settled the target rule (`FR-5` / Q12)
  to remove it, and implementation is planned in `WISHENKA-218`.

### Settled product decisions (WISHENKA-154)

All six open product questions from `WISHENKA-22` (assumptions A–D, Q6, Q8, Q11, Q12, and
shortcut E) are settled in `in-docs/spec.md` (`WISHENKA-154`):

- **Assumptions A–D (`FR-1`):**
  - **A (confirmed):** Receipt and promise remain independent facts; recording receipt never
    closes, cancels, or modifies any promise, and `received + occupied > requested` (over-booked)
    is valid.
  - **B (confirmed):** Any list author (owner, admin, or member/co-author) may record receipt
    (and undo/correct per `WISHENKA-153`), including when the author is also the wish's recipient.
  - **C (superseded):** Receipt is no longer final; `WISHENKA-153` introduced cancellation and
    quantity correction of receipt records on active lists.
  - **D (confirmed):** «Подаренные» is strictly author-only and never visible to gifters or
    anonymous viewers.
- **No public «уже подарено» label (`FR-2` / Q6):** Gifters and anonymous viewers never see
  «Подаренные», receipt dates, received quantities, or a public «уже подарено» badge. Partially
  received active wishes show only the available remainder (or «Забронировано» when zero). Fully
  received wishes leave the active list; gifters with open promises see the received marker
  exclusively in «Мои бронирования» and personal receipt notices.
- **Gifted history on list deletion vs archive (`FR-3` / Q8):** Deleting a wishlist permanently
  removes its «Подаренные» history together with the wishlist and its wishes (no standalone
  long-term gifted history is retained). Archiving a wishlist preserves «Подаренные» in read-only
  mode.
- **Co-author who is also the recipient (`FR-4` / Q11):** On a collaborative wishlist, an admin or
  member who is the recipient of a wish retains full author rights on that wish (edit,
  archive/restore, record/undo/correct receipt) under strict surprise protection (no booking,
  giver, or purchase data shown) and cannot act as a gifter on that wish (no self-booking). On
  other wishes in the same list where someone else is the recipient, they act as a normal gifter.
- **Planned / target spec rules (not yet implemented in code):**
  - **`FR-5` (Q12, planned in `WISHENKA-218`):** Tighten the edit-form quantity-reduction lock so
    authors can reduce requested quantity down to `max(1, received_quantity)` without seeing or
    being blocked by occupied promise units; if `received + occupied > new_requested`, the wish
    enters the standard over-booked state and open-promise givers are notified.
  - **`FR-6` (Shortcut E, planned in `WISHENKA-219`):** Add an explicit «Завершено»
    («Завершить» / «Подарок вручён») completion action for **purchased** promises on fully
    received wishes, moving the promise to a closed state (freeing occupied units, excluding it
    from active «Мои бронирования» counters, and stopping further receipt/undo notices). Intended
    (unpurchased) promises cannot be completed directly.

### Not implemented

- Notification settings screen (only tables and lookup exist): WISHENKA-34.
- Metrics exporter: WISHENKA-84 (the metrics are derived from logs and SQL, see Logging).
- Planned target rules from `WISHENKA-154`: edit-form quantity-reduction lock tightening (`FR-5` /
  Q12) in `WISHENKA-218`, and «Завершено» state for purchased promises (`FR-6` / Shortcut E) in
  `WISHENKA-219`.
- Follow-up debt of the UI story: see [Follow-up tickets](#follow-up-tickets-of-the-ui).
- Follow-up debt of the backend (all Low): WISHENKA-155 (one digit-free `quantity_invalid`
  message), 156 (opt-in real-Telegram smoke test, two-process worker race test), 157 (log-contract
  and test hardening), 158 (split receipt code out of `service.py`, unify the two flush call sites
  in `store.py`), 159 (fail-closed `wl is not None` guards).

## Architecture

- **Wish row.** `quantity` and `received_quantity` stay on `wl_items`. No new column, no second
  row per wish. Remaining is derived.
- **Receipt history, `wl_receipts`.** One append-only row per act. Columns: `id`,
  `wish_item_id` (FK to `wl_items`, `ON DELETE CASCADE`), `quantity` (`>= 1`), `received_at`
  (text, ISO), `is_approximate` (0 or 1). No giver column and no link to reservations, by design.
  Index `idx_wl_receipts_item (wish_item_id, received_at, id)`. The counter and the record are
  written in the same transaction. Dataclass: `ReceiptRecord` in `wishlists/models.py`
  (`WishItem.receipts`, empty by default).
- **Derived views, one predicate set** (`WishItem` properties in `wishlists/models.py`):

  | Property | Rule |
  | -------- | ---- |
  | `remaining_quantity` | `max(0, quantity - received_quantity)` |
  | `is_fully_received` | `received_quantity >= quantity` |
  | `is_gifted` | `received_quantity > 0` |
  | `is_active` | not `is_archived` and not `is_fully_received` |
  | `is_in_archive` | `is_archived` and not `is_fully_received` |

  `is_active` is the single predicate behind the active list and reorder (`get_wishlist_view`,
  `reorder_wish_items`), the restore tail order and the public projection. `list_wish_items`
  uses `is_active`, or with `include_archived` every wish that is not fully received. The
  gifted read uses `is_gifted` and never joins reservations.
- **`record_item_fulfillment(item_id, actor, received_quantity, *, wishlist_id=None)`.** Guards
  in a fixed order, membership first, so a non-member learns nothing about the list or wish
  state: unknown wish or wrong `wishlist_id` -> `ItemNotFoundError`; not a member ->
  `PermissionDeniedError`; list deleted -> `WishlistDeletedError`; list archived ->
  `WishlistArchivedError`; wish archived -> `WishArchivedError`; quantity below one ->
  `QuantityInvalidError`; fully received -> `NothingRemainingError`; quantity above remaining ->
  `QuantityAboveRemainingError`. On success it adds to the counter, appends a `ReceiptRecord`
  and drafts the notices. The store persists all effects in the same transaction
  (`WishlistStore._flush_receipt_effects`, called from `_persist_wish` and `_write`).
- **`cancel_item_receipt(item_id, receipt_id, actor, *, wishlist_id=None)`** and
  **`correct_item_receipt(item_id, receipt_id, actor, new_quantity, *, wishlist_id=None)`**
  (WISHENKA-153): undo or adjust an existing `wl_receipts` row. Guards run in fixed order:
  unknown wish or wrong `wishlist_id` -> `ItemNotFoundError`; not a member ->
  `PermissionDeniedError`; list deleted -> `WishlistDeletedError`; list archived ->
  `WishlistArchivedError`; (`correct_item_receipt` only) `new_quantity < 1` ->
  `QuantityInvalidError`; acquire per-item lock; missing `receipt_id` on that wish ->
  `ReceiptNotFoundError` (`reason = "receipt_not_found"`, HTTP 404); (`correct_item_receipt` only)
  `new_quantity > receipt.quantity + item.remaining_quantity` -> `QuantityAboveRemainingError`.
  Note that `item.is_archived` does **not** block cancelling or correcting a receipt: an archived
  remainder wish stays `is_archived = True` with its updated `remaining_quantity`.
  `correct_item_receipt` preserves `received_at` and `is_approximate`, and treats
  `new_quantity == receipt.quantity` as a no-op (no `updated_at` change, no notices).
  `WishlistStore._flush_receipt_effects` flushes `_updated_receipts` (`UPDATE wl_receipts SET
  quantity = ...`) and `_deleted_receipt_ids` (`DELETE FROM wl_receipts`) in the same
  `BEGIN IMMEDIATE` transaction, and records `SharedEvent` (`receipt_reverted` on cancel or
  downward correction; `receipt_increased` on upward correction) into `reminder_outbox` for
  distinct open-promise givers (`ACTIVE`/`PURCHASED`, excluding `is_recipient_id`). Using
  `reminder_outbox` avoids `notification_outbox.receipt_id ON DELETE CASCADE` on cancel and
  `notice_receipt_keys` deduplication on upward correction.
- **Exceptions** (`wishlists/exceptions.py`): `WishRefusalError` base with a stable `reason`;
  `ReceiptNotFoundError` (`reason = "receipt_not_found"`);
  `QuantityInvalidError` and `QuantityAboveRemainingError` also derive from `ValueError`;
  `NothingRemainingError` and `QuantityAboveRemainingError` carry `remaining_quantity`.
- **Policy** (`wishlists/policy.py`): `is_recipient_id(user_id, item)` (and `is_recipient`
  delegating to it), `can_view_gifted(ctx, wishlist)` (member of a non-deleted list).
- **Concurrency.** The receipt runs through `WishlistStore.execute_wish(...,
  operation_name="record_item_fulfillment")`: one `BEGIN IMMEDIATE` wish-scoped transaction with
  `busy_timeout` 5000 ms, no new lock. Inside it: load the wish, promises and notice settings,
  check the guards and the cap, add the counter, insert the receipt, insert the outbox rows,
  commit. A refusal or any error rolls everything back. A receipt racing a promise or another
  receipt serialises. A lost race surfaces as `quantity_above_remaining` or `nothing_remaining`
  with the then-current remaining quantity. A busy lock is `InventoryBusyError`, answered 503.
- **Notice path.** `wishenka/notices/` (`models.py`, `store.py`, `sender.py`, `worker.py`) plus
  the lifespan wiring in `web/app.py`. See the section below.

### Legacy data and the migrations

Built by `add_gift_receipts` and `add_notice_outbox` and extended by `add_birthday_reminders` and
`add_notice_uncertain`, see [migrations.md](migrations.md). The chain is now
`add_item_order_index` -> `add_gift_receipts` -> `add_notice_outbox` -> `add_bot_drafts` ->
`add_bot_capture_order` -> `add_birthday_reminders` -> `add_notice_uncertain` ->
`add_support_channel` -> `add_idempotency_records` (head).

- **`add_gift_receipts`.** Creates `wl_receipts` and its index. Back-fills one record per wish
  that has `received_quantity > 0` and no record yet: quantity = `received_quantity`,
  `received_at` = the wish's `updated_at`, `is_approximate = 1`. The date is an approximation of
  the last update, never the real moment, and the gifted read exposes it as
  `ReceiptEntryDTO.is_approximate`. Then it normalises legacy rows with `is_archived = 1`,
  `received_quantity > 0` and `received_quantity >= quantity`: the flag is set to 0, so a fully
  received wish is only gifted, never archived. A partly received archived row stays archived.
  The statements are repeatable after a partial failure (`IF NOT EXISTS`, back-fill guarded by
  `NOT EXISTS`). The row counts are logged as INFO `legacy_receipts_backfilled` and
  `legacy_archived_rows_normalised` (field `rows`) on `wishenka.wishlists.migrations`.
- **Irreversible.** `downgrade()` raises `NotImplementedError`: it could not tell which archived
  rows were normalised, and dropping the table would lose the history. Restore from a backup.
- **`add_notice_outbox`.** Creates `notification_outbox`, `user_notification_settings` and
  `wl_list_notification_settings` (see below). Its downgrade drops the three tables.
- **`add_notice_uncertain`.** Rebuilds `notification_outbox` with `status = 'uncertain'`,
  `claim_token`, `requires_membership`, and `CHECK(ambiguous=0 OR status NOT IN ('pending','sending'))`,
  and creates `notice_receipt_keys` (see [notifications.md](notifications.md)).
- `head_revision(database_url=<in-memory default>)` in `wishlists/migrations.py` returns the
  single head id of the script directory without opening a database; the concurrency test uses
  it instead of a hard-coded name.

## API / Usage

Both routes are in `wishenka/web/routes/receipts.py` (router prefix `/api/wishlists/{wishlist_id}`,
tag `receipts`, mounted in `create_app`). Authentication is `get_current_user`: session cookie or
bearer token, 401 without one. A cookie session needs the CSRF token like other mutations
(`BrowserSecurityMiddleware`, header `X-CSRF-Token` from `GET /api/auth/csrf`).
Both `POST /api/wishlists/{wishlist_id}/items/{item_id}/receipts` and the HTMX UI route
`POST /web/wishlists/{wishlist_id}/items/{item_id}/receipt` accept an optional `Idempotency-Key`
header (see [idempotency.md](idempotency.md)).

### `POST /api/wishlists/{wishlist_id}/items/{item_id}/receipts`

Records one receipt act.

- **Body** (`ReceiptRequestDTO`, `extra="forbid"`): `{"quantity": <int>}`. An unknown field
  (for example `giver`) or a value pydantic cannot read as an integer (for example `"abc"`) is
  422. The lax mode coerces `"3"` and `3.0` to 3. A quantity below 1 passes the DTO and is
  400 `quantity_invalid`, not 422. There is no giver or confirmation field.
- **Success**: HTTP 201, `ReceiptResultDTO`:
  - `item`: the recipient-safe view (`WishItemRecipientViewDTO`: wish fields, `quantity`,
    `received_quantity`, `remaining_quantity`, `is_archived`, `is_recipient=true`; no booking
    field exists on it);
  - `received_now`: the quantity of this act;
  - `received_quantity`, `remaining_quantity`, `is_fully_received`: the counters after the act.
- **Refusals**: `detail` is `{"reason": <code>, "message": <fixed text>}`. Only the two
  remaining-quantity reasons add `"remaining_quantity": <int>`. The messages hold no number
  except the minimum 1 of `quantity_invalid` and never state or imply booked units. The table is
  `_REFUSALS` in `receipts.py` (matched in that order):

  | Domain error | HTTP | `reason` | Message |
  | ------------ | :--: | -------- | ------- |
  | `QuantityInvalidError` | 400 | `quantity_invalid` | Quantity must be a whole number of at least 1 |
  | `QuantityAboveRemainingError` | 409 | `quantity_above_remaining` | Quantity is above the remaining quantity |
  | `WishArchivedError` | 409 | `wish_archived` | The wish is archived |
  | `WishlistArchivedError` | 409 | `wishlist_not_active` | The wishlist is not active |
  | `WishlistDeletedError` | 404 | `wishlist_not_active` | The wishlist is not active |
  | `NothingRemainingError` | 409 | `nothing_remaining` | Nothing remains to receive |
  | `PermissionDeniedError` | 403 | `forbidden` | Forbidden |
  | `ItemNotFoundError`, `WishlistNotFoundError` | 404 | `not_found` | Resource not found |
  | `ReceiptNotFoundError` | 404 | `receipt_not_found` | Resource not found |
  | `InventoryBusyError` | 503 | `busy` | the promise-route sentence, nothing changed, retry |

  A wish id that exists in another list is `not_found`. The route constant of the
  `quantity_invalid` message differs from the `QuantityInvalidError` default ("Quantity must be
  a positive whole number"); WISHENKA-155 unifies them. Clients should map by `reason`.

### `DELETE /api/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}` (WISHENKA-153)

Cancels (undoes) a single receipt act, removes the `wl_receipts` row, decrements
`received_quantity`, and queues `receipt_reverted` in `reminder_outbox` for open-promise givers.
Accepts `Idempotency-Key` (see [idempotency.md](idempotency.md)).

- **Success**: HTTP 200, `ReceiptResultDTO` with `received_now=0` and updated counters.
- **Refusals**: same `_REFUSALS` table as `POST`, including 404 `receipt_not_found` when
  `receipt_id` is absent on the wish.

### `PATCH /api/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}` (WISHENKA-153)

Corrects the quantity of an existing receipt act while preserving `received_at` and
`is_approximate`. Accepts `Idempotency-Key`.

- **Body** (`ReceiptRequestDTO`, `extra="forbid"`): `{"quantity": <int>}`.
- **Success**: HTTP 200, `ReceiptResultDTO` with `received_now=payload.quantity` and updated
  counters. Same-quantity correction is a no-op (no `updated_at` change, no notices).
- **Refusals**: same `_REFUSALS` table (`quantity_invalid`, `quantity_above_remaining` with
  `max_allowed = old_quantity + remaining_quantity`, `receipt_not_found`, `wishlist_not_active`,
  `forbidden`, `not_found`, `busy`).

### `GET /api/wishlists/{wishlist_id}/gifted`

Returns `list[GiftedItemDTO]` for members of a non-deleted list (full snapshot read through
`store.execute`, same refusal table: 403 `forbidden` for a non-member, 404 `not_found` for an
unknown list, 404 `wishlist_not_active` for a deleted one). The read stays available when the
list is archived. Order: newest receipt first (a wish without records falls back to its
`updated_at`), then `id`.

- `GiftedItemDTO`: `id`, `title`, `description`, `link`, `image_url`, `price`, `currency`
  (default `RUB`), `store_name`, `store_icon_url`, `recipient_user_id`, `recipient_name`,
  `quantity` (1), `received_quantity` (0), `remaining_quantity` (0), `is_archived`, and
  `receipts`.
- `ReceiptEntryDTO`: `id` (default 0), `received_at`, `quantity`, `is_approximate` (false). Entries are oldest
  first. No reservation, giver or promise field exists on either DTO.

### Other read data changed by this story

- **`WishItemRecipientViewDTO`** gains `remaining_quantity`; **`WishItemGifterViewDTO`** gains
  `remaining_quantity` and `is_fully_received` (default false); **`MyReservationItemDTO`** gains
  `is_fully_received` (default false, set from the wish by `get_user_reservations`). The first two
  fill the new fields from the quantities in a `mode="before"` validator when they are absent, so
  older constructors keep working.
- **Cabinet row** (`CabinetRow` in `web/routes/reservations_ui.py`): new `wish_received` (the wish
  is fully received) and `offer_actions = (wish archived or wish received) and list not archived`.
  The four promise actions are therefore offered for a received wish on an active list.
  `reservations_list.html` renders `wish_received` as the marker «Желание получено владельцем»
  (WISHENKA-24, see the UI section). The wish card of a fully received wish shows no giver
  controls (`item_card.html`, `can_promise` requires `not item.is_fully_received`).
- **Public and wishlist projection** (`projection` in `web/routes/wishlists.py`): each item now
  has `remaining_quantity` and `is_active`, and a wish that is not `is_active` (archived or fully
  received) is omitted for anonymous, public-link and non-member viewers. Members still get all
  wishes. This is a visible behaviour change of the projection: before, archived wishes were
  listed for non-members.
- **Archive and restore** (`items.py` `execute`, `items_ui.py`): `NothingRemainingError` is a 409
  with the fixed message "Nothing remains to receive" on the archive and restore routes for a
  fully received wish. The Mini App HTML routes (`items_ui.py`) no longer answer with that JSON
  detail: they answer 409 with out-of-band fragments only (see the UI section).

## Notice path

Delivery of the giver notice is a transactional outbox plus an in-process async worker. Extended in
[WISHENKA-29](notifications.md) and [WISHENKA-60](notifications.md) with live eligibility
rechecks, verified bot destinations, shared rate limiting, `claim_token` fencing, `uncertain`
quarantine for ambiguous sends, and partial-receipt durability across wish archival.

### Outbox table `notification_outbox`

Created by `add_notice_outbox` and updated by `add_notice_uncertain`. Columns: `id`, `event_type`
(`gift_received`), `receipt_id` (FK
to `wl_receipts`, cascade), `wishlist_id` (FK, cascade), `wish_item_id` (FK, cascade),
`giver_user_id`, `status`, `skip_reason`, `attempts` (default 0), `ambiguous` (0 or 1),
`next_attempt_at` (integer epoch seconds), `claimed_at` (integer epoch seconds, set only while
`sending`), `last_error_class`, `created_at`, `updated_at` (ISO text), `claim_token` (random token
fencing `sending` rows), and `requires_membership` (0 or 1). Unique key
`(event_type, receipt_id, giver_user_id)`, also mirrored in `notice_receipt_keys` so purging
terminal rows does not allow duplicate receipt notices, index `idx_notice_outbox_due (status,
next_attempt_at)`. There is no payload, text or quantity column: the text is rendered at send
time from the current titles.

| `status` | Meaning |
| -------- | ------- |
| `pending` | waiting for `next_attempt_at` |
| `sending` | claimed by a worker; fenced by `claim_token` |
| `sent` | delivered (terminal) |
| `failed` | gave up (terminal), `last_error_class` holds the class name |
| `skipped` | terminal; `skip_reason` is `setting_list`, `setting_user` or `target_gone` |
| `uncertain` | quarantined ambiguous send or expired lease; requires operator resolution via `wishenka.notices.operator` |

`ambiguous = 1` marks a send whose outcome is unknown (a timeout, a 5xx, a network or unexpected
error, or a dead claim) and places the row in `status = 'uncertain'` (`CHECK(ambiguous=0 OR status
NOT IN ('pending','sending'))`).

### Producer (inside the receipt transaction)

`WishlistService._draft_receipt_notices`: one notice per distinct giver with an `ACTIVE` or
`PURCHASED` reservation on the wish, in first-reservation order, excluding anyone who is the
recipient of that wish (`is_recipient_id`). It is one notice per giver per act, not per promise.
The giver has no more than one row per receipt (`notice_receipt_keys` and the unique key). The rows
are inserted by `_flush_receipt_effects` with `next_attempt_at = now` and `requires_membership = 1`
when the giver is currently a wishlist member.

The settings gate is evaluated by the producer (`WishlistService._notice_gate`) and rechecked live
by the worker (`NoticeStore._eligible`), in this order: the list-level row
(`wl_list_notification_settings`: `user_id`, `wishlist_id`, `event_type`, `enabled`), else the
user-level row (`user_notification_settings`: `user_id`, `event_type`, `enabled`), else default
on. A disabled giver gets a `skipped` row (kept for audit)
with `skip_reason` `setting_list` or `setting_user`. No production code writes the `gift_received`
settings rows yet (WISHENKA-34); tests do.

### Worker claim protocol

`NoticeStore.claim_next(now)` (every method is one `BEGIN IMMEDIATE` transaction through
`WishlistStore.transaction`) looks at up to 50 due rows ordered by `next_attempt_at, id`: `pending`
rows whose `next_attempt_at <= now`, and `sending` rows whose `claimed_at <= now - lease`. For each
row in order:

1. If the row is a stale `sending` row (the claim is older than the lease): it is settled first
   and never sent in the same call. It is marked `status = 'uncertain'`, `ambiguous = 1`,
   `last_error_class = StaleClaim`, `claimed_at = NULL`, `claim_token = NULL`, and the loop
   continues.
2. If the list is deleted or missing, the wish is missing, or `NoticeStore._eligible` fails
   (`received_quantity <= 0`, giver became recipient, setting disabled, membership required and
   revoked, reservation removed, or no active `bot_destinations` entry): the row becomes `skipped`
   with `target_gone` (logging DEBUG `receipt_notice_skipped_ineligible`) and the loop continues.
   Because `_eligible` checks `i.received_quantity > 0` rather than `i.is_archived = 0`, pending
   `gift_received` notices for a partial receipt remain eligible and are still delivered if the
   author archives the remaining unreceived units of the wish before the worker runs.
3. If `reserve_permit` (global and per-chat rate limit in `notice_rate_slots`) denies a slot now:
   `next_attempt_at` is pushed to `now + 1` and the loop continues.
4. Otherwise a `pending` row is claimed: `status = sending`, `claimed_at = now`,
   `claim_token = secrets.token_urlsafe(18)`, `attempts + 1`.

Immediately before network send, `NoticeWorker.run_once` calls `NoticeStore.refresh_claim(claim)`
to re-verify `claim_token`, live eligibility, language, and current titles; if eligibility changed,
`skip_claim` marks the row `skipped`. The settle writes (`complete`, `uncertain`, `fail`,
`reschedule`, `skip_claim`) are one guarded `UPDATE ... WHERE id = :id AND status = 'sending' AND
claim_token = :token`. If the claim was lost the write changes nothing and the DEBUG event
`receipt_notice_late_write_ignored` is logged.

`NoticeWorker.run_once` drains all due receipt and service/reminder rows, reading the clock afresh
for every claim and settle. The send is wrapped in `asyncio.wait_for(..., request_timeout + 5)`.
The outcome mapping (`sender.classify_error`, ordered, subclasses first):

| Outcome | Errors | Effect |
| ------- | ------ | ------ |
| `DELIVERED` | no error | `sent` |
| `REJECTED` | forbidden, bad request, not found, entity too large, migrate to chat | `failed` at once (never retried; forbidden/not found also sets `bot_destinations.active = 0`) |
| `RETRYABLE` | retry after (honoured: delay is the larger of the backoff and `retry_after`, and `block_until` throttles all workers), unauthorized | `pending` with backoff |
| `AMBIGUOUS` | everything else: 5xx, network, timeout, unexpected | `uncertain` with `ambiguous = 1` (never automatically retried) |

An attempt number at the maximum also ends in `failed`. Backoff after the n-th failed attempt is
`min(base * 2**(n - 1), max)` seconds (defaults: 30, 60, 120, 240 after attempts 1 to 4, capped at
3600 s; the fifth failure is terminal). The text is plain (no parse mode), rendered in English for
`en*` language codes and Russian otherwise, with each title cut at 100 characters. No quantity, no
other giver, no hint of excess.

### Delivery guarantee

External delivery cannot be promised as exactly-once because Telegram may accept a request before
the HTTP response is lost. When a send times out, fails ambiguously, or a worker dies while a row
is `sending`, the row transitions to `status = 'uncertain'` and is held for explicit operator
resolution (`python -m wishenka.notices.operator`) rather than being automatically resent or
reported as delivered. See [Service notifications and reminders](notifications.md) for operator
commands. A failed or uncertain delivery never fails or rolls back the receipt.

### Worker and lifespan

`web/app.py` `_start_notice_worker` runs in the lifespan of every web process (no leader
election; the claim lease and guarded writes make parallel workers safe) after the cleanup worker.
The task is `app.state.notice_task`, the sender `app.state.notice_sender`, the queue store
`app.state.notice_store`. `create_app(settings, notice_sender=None)` accepts a fake sender for
tests.

- The worker is **not started** when `receipt_notice_worker_enabled` is false, or when there is no
  usable bot token: `build_sender` returns `None` for an empty token, the placeholder
  `dummy_bot_token` or a token that fails aiogram's `validate_token`. INFO
  `receipt_notice_worker_disabled` with `reason` `disabled_by_setting` or `no_bot_token` is logged.
  A no-op sender is deliberately not used, it would mark rows `sent`. **Deployment requirement:**
  without a real bot token receipts still work and rows are enqueued (`pending`), but no notice is
  ever sent, and the rows wait until a process with a token starts.
- On shutdown `_stop_notice_worker` cancels the task (a send in flight stays `sending` and is
  handled by the lease rule), closes the sender (`sender.close()`) and logs INFO
  `receipt_notice_worker_stopped`. The cleanup worker is stopped first and a failure there does
  not skip the notice stop.
- `NoticeWorker.run` polls every `receipt_notice_poll_interval_seconds`. A failing tick logs one
  ERROR `receipt_notice_worker_error` per failure streak and backs off (poll interval doubled per
  failure, capped at 60 s).

### Retention

`NoticeStore.purge_finished(threshold)` deletes terminal (`sent`, `skipped`, and `failed`) rows in
a single transaction from both `notification_outbox` (`updated_at <= threshold`) and
`reminder_outbox` (`next_attempt_at <= threshold_epoch`), while preserving `notice_receipt_keys`
and all `pending`, `sending`, and `uncertain` rows. It runs at the end of each cleanup cycle
(`run_cleanup_cycle`, `_purge_notices`) with `threshold = now - receipt_notice_retention_days`.
When rows are deleted, `NoticeStore.purge_finished` logs INFO `notice_outbox_purged`
(`receipt_purged`, `reminder_purged`, `total_purged`) on `wishenka.wishlists.notices` and cleanup
logs INFO `receipt_notice_rows_purged` (`rows`). A failure is a WARNING `receipt_notice_purge_failed`
and never fails the cycle. It runs only while `background_cleanup_enabled` is true. See
[WISHENKA-183](https://pypost.atlassian.net/browse/WISHENKA-183) for planned batched deletion.

## Mini App UI (WISHENKA-24)

The page layer on top of the contract above. Sources: `ai-tasks/WISHENKA-24/10-requirements.md`
(U-1 to U-21, N-1 to N-8), `20-architecture.md`, `50-observability.md`, `60-tech-debt.md`. Where
this section and the code differ, the code wins.

### Components

| File | Role |
| ---- | ---- |
| `wishenka/web/routes/receipts_ui.py` | Router `/web/wishlists/{wishlist_id}` (tag `receipts-ui`): receipt creation (`get_receipt_dialog`, `record_receipt_ui`) and per-act edit/cancel (`get_receipt_edit_dialog`, `correct_receipt_ui`, `get_receipt_cancel_dialog`, `cancel_receipt_ui`). Included in `create_app` after `items_ui_router`. |
| `wishenka/web/gifted_view.py` | `RECEIPT_REFUSAL_HEADER` (`X-Receipt-Refusal`), `NOTHING_REMAINING_TEXT`, the escaping helper `oob_text`, the view models `GiftedAct` (carries `receipt_id`), `GiftedRow`, `utc_day`, `build_gifted_rows`, and `read_gifted_rows` (fail-soft). |
| `wishenka/web/templates/partials/item_receipt_modal.html` | Receipt creation dialog, context `wishlist_id`, `item_id`, `item_title`, `remaining`, `selected`, `feedback`, `blocked`, `oob`. |
| `wishenka/web/templates/partials/receipt_edit_modal.html`, `receipt_cancel_modal.html` | Per-act correction and cancellation confirmation modals (WISHENKA-153). |
| `wishenka/web/templates/partials/gifted_items_section.html` | The «Подаренные» section, context `gifted_rows`, `wishlist_id`, `can_edit_wishlist`, `oob`. |
| `wishenka/web/static/receipt.js` | Dialog behaviour (classic script in an IIFE, `defer`, after `wishlist.js`). |
| `wishenka/web/static/wishlist.js` | Two additions: the `swapWishCard` wrapper and the `htmx:responseError` listener for a stale reorder. |
| `partials/item_card.html`, `archived_items_section.html`, `item_archive_modal.html`, `reservations_list.html`, `wishlist_detail.html`, `base.html`, `static/miniapp.css` | Owner card, archive texts, cabinet marker, page wiring, script tag, styles. |
| `items_ui.py`, `sharing.py` | `is_member` card flag, `_nothing_remaining_response`, `REORDER_REFUSAL_HEADER`, `has_received`. |

### Routes

Both routes need a session (`get_current_user`, 401 without one). The POST is a cookie-session
mutation, so it needs the CSRF token; the inline script of `base.html` adds `X-CSRF-Token` to
every non-GET htmx request in `htmx:configRequest` once the token is fetched.

- **`GET /web/wishlists/{wishlist_id}/items/{item_id}/receipt`** opens the dialog. It is
  advisory: it reads the wish (`get_wishlist_by_id`) and applies the service guards in order
  (unknown wish, not a member, list not active, wish archived, nothing remaining) without
  writing. A member of an active list with remaining units gets 200 and the form (INFO
  `ui_receipt_form_opened`). Any guard that fails gets the same dialog in the blocked state
  (sentence and a close button, no form, no title for a non-member), the status of the JSON
  route and the header `X-Receipt-Refusal`. `nothing_remaining` also carries the list and
  «Подаренные» fragments as out-of-band elements (the stale card leaves the list). A non-member
  of a deleted list gets `wishlist_not_active` (404) instead of `forbidden`, because
  `get_wishlist_by_id` raises before membership can be checked.
- **`POST /web/wishlists/{wishlist_id}/items/{item_id}/receipt`** (form field `quantity`) calls
  `WishlistService.record_item_fulfillment(item_id, user, quantity, wishlist_id=...)` and then
  reads the committed state in the same `_execute`. Text that is not a whole number is passed
  as 0, so the service refuses it as `quantity_invalid` after its membership and state guards
  (`_quantity_of`). Success is 201 with out-of-band fragments only:
  1. `#item-modal-container` emptied (the dialog closes);
  2. `#list-notice`: «Отмечено получено: N шт. («title»)» (the text is escaped);
  3. a partial receipt: the card of the wish with `hx-swap-oob="true"` (first and last flags
     from the list); a full receipt: the whole `#items-list` (`innerHTML:#items-list`) because
     the wish left the list and the flags and the empty text come along;
  4. the «Подаренные» section (`outerHTML`).
- **`GET /web/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}/edit`** and
  **`GET /web/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}/cancel`**
  (WISHENKA-153): open the correction modal (`partials/receipt_edit_modal.html`) or cancellation
  confirmation modal (`partials/receipt_cancel_modal.html`) for a specific `receipt_id` (INFO
  `ui_receipt_entry_form_opened`). Refusals return the blocked modal with `X-Receipt-Refusal`.
- **`POST /web/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}/edit`** (form field
  `quantity`) and **`POST /web/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}/cancel`**
  (WISHENKA-153): call `correct_item_receipt` or `cancel_item_receipt`, accept `Idempotency-Key`,
  and on 200 return OOB fragments emptying `#item-modal-container` and updating `#list-notice`,
  `#items-list`, `#gifted-items-section`, and `#archived-items-section`. `receipt.js` submits
  both forms via `submitReceipt` (with or without a `quantity` input).

### Dialog flow

1. The card button `.btn-receipt-item` («Получено») does `hx-get` on the GET route into
   `#item-modal-container` (`innerHTML`). It is inside `.item-actions`, so only under
   `can_edit_wishlist` (member of an active list), and only while `item.remaining_quantity > 0`.
2. The dialog is `#item-receipt-modal` (`role="dialog"`, `aria-modal="true"`,
   `aria-labelledby="receipt-title"` across `item_receipt_modal.html`, `receipt_edit_modal.html`,
   and `receipt_cancel_modal.html`). Quantity selection in `item_receipt_modal.html` is
   thresholded by `RECEIPT_SELECT_MAX = 20` (`select_max` in `receipts_ui.py`):
   - `remaining == 1`: hidden field (`value="1"`), no choice;
   - `1 < remaining <= 20`: labelled `<select id="receipt-quantity" name="quantity"
     data-receipt-quantity data-remaining="...">`;
   - `remaining > 20`: `.quantity-control` with `-`/`+` `.btn-step` buttons
     (`data-receipt-step="-1"` / `"1"`) and `<input id="receipt-quantity" type="number"
     name="quantity" data-receipt-quantity data-remaining="..." min="1" max="..." step="1"
     inputmode="numeric" required>`.
   Both interactive modes render a live summary (`[data-receipt-summary]`, `aria-live="polite"`)
   and state that the act cannot be undone. `#receipt-feedback` has `role="alert"` and
   `tabindex="-1"`.
3. **Modal isolation, focus trap, and lifecycle (`receipt.js`, WISHENKA-161)**:
   - On `htmx:afterSwap` into `#item-modal-container`, `setBackgroundInert(true)` walks from
     `#item-modal-container` up to `document.body` and sets `inert` and `aria-hidden="true"` on
     non-ancestor element siblings (skipping `<script>`, `<style>`, `<template>`), keeping the
     modal itself interactive. Focus moves to `#receipt-feedback` if non-empty (blocked/refusal),
     otherwise to the first interactive control.
   - `Tab` / `Shift+Tab` inside `#item-receipt-modal` is trapped by `getFocusable(modal)` across
     visible, enabled descendants.
   - `closeDialog()` (Cancel, Escape, or backdrop click) clears `#item-modal-container`, calls
     `setBackgroundInert(false)` (restoring only elements marked by `receipt.js`), and restores
     focus (`restoreFocusToPage`) to `#${openerCardId} .item-card-summary`, else `openerElement`,
     else `#list-notice` (`tabindex="-1"`).
   - `receipt.js` updates `[data-receipt-summary]` on `change`, `input`, and `[data-receipt-step]`
     clicks (clamping to `[1, remaining]`).
4. On `submit` of `form[data-receipt-form]`, if `field` is an `<input type="number">` and
   `!field.checkValidity()`, `receipt.js` calls `field.reportValidity()` and aborts submission.
   Otherwise it prevents the browser submit, captures whether
   `#gifted-items-section details.gifted-items-details` is currently `open` (`giftedWasOpen`,
   captured in `submitReceipt` and restored in `finishAttempt`), and calls
   `htmx.ajax('POST', action, {target: '#receipt-feedback', swap: 'none', values: {quantity}})`
   once (`submitReceipt`; this is the only `htmx.ajax` call of the script). The result arrives
   through out-of-band elements only. While the request is open the form has `data-pending`
   and `aria-busy`, the confirm button is disabled and a second submit does nothing. The
   feedback is emptied at the start of every attempt.
5. When the `htmx.ajax` Promise settles, `finishAttempt(form, giftedWasOpen)`:
   - restores `details.gifted-items-details.open = true` if `giftedWasOpen` was true;
   - if `#item-receipt-modal` is still in `document` (refusal, including
     `quantity_above_remaining` OOB replacement, or network failure): keeps background `inert`,
     clears busy state if `form` is connected, shows «Не удалось сохранить отметку. Повторите
     попытку.» if feedback is empty, and focuses `#receipt-feedback` (or primary control);
   - if `#item-receipt-modal` left `document` (receipt succeeded): removes background `inert`,
     focuses `#${openerCardId} .item-card-summary` (partial receipt) or `#list-notice`
     (`tabindex="-1"`, full receipt), and clears `openerCardId`.

### Refusals and the marker header

Every refusal of the receipt routes carries `X-Receipt-Refusal: <reason>`. The statuses come from
the JSON route table, read-only, from `receipts._REFUSALS` (`_classify`). The sentences are
`_SENTENCES` in `receipts_ui.py`. The closed set of the header:

| `reason` | Status | Sentence |
| -------- | :----: | -------- |
| `quantity_invalid` | 400 | Укажите целое число не меньше 1. |
| `quantity_above_remaining` | 409 | Нельзя отметить больше, чем осталось. Осталось: {n}. |
| `nothing_remaining` | 409 | Это желание уже полностью получено. |
| `wish_archived` | 409 | Желание в архиве. Восстановите его, чтобы отметить получение. |
| `wishlist_not_active` | 409 or 404 | Вишлист не активен, отметить получение нельзя. |
| `forbidden` | 403 | У вас нет права отмечать получение в этом вишлисте. |
| `not_found` | 404 | Желание не найдено. Обновите страницу. |
| `receipt_not_found` | 404 | Эта запись о получении уже удалена. Обновите страницу. (`web.receipt.error.receipt_not_found`) |
| `busy` | 503 | Не удалось сохранить отметку сейчас. Повторите попытку. |

- `busy` is the UI mapping of `InventoryBusyError`. It is not in `_REFUSALS`; the constant is
  `BUSY` in `receipts_ui.py`. The sentence is neutral and names no booking. The dialog stays
  open and keeps the chosen quantity.
- The remaining quantity in `quantity_above_remaining` is the one of the exception. After this
  refusal the response also carries the refreshed card and the dialog (`oob`, `outerHTML`) with
  the sentence, so the author sees the current remaining quantity. `nothing_remaining` carries
  the list, «Подаренные» and the blocked dialog. This effect read is best effort: if it raises
  a domain error, the status and the sentence of the refusal are unchanged and only the
  sentence is shown (`_effect_fragments` returns `None`).
- The set exists in three places that must agree: `receipts._REFUSALS` (plus `busy`),
  `_SENTENCES` and `REFUSAL_REASONS` in `receipt.js`. `test_ui_reason_table_matches_json_route`
  and `test_closed_reason_set_mirrors_the_refusal_table` guard it.
- A refusal body is out-of-band only: the sentence is
  `<div id="receipt-feedback" hx-swap-oob="innerHTML">`. No top-level element lands in the
  `swap: 'none'` target.

#### Why `htmx:beforeSwap` is overridden

htmx 1.9.12 does not swap 4xx and 5xx responses: it fires `htmx:responseError` and drops the
body, so the sentence and the out-of-band fragments of a refusal would never reach the page.
`receipt.js` listens to `htmx:beforeSwap` on `document`. When the event has an `xhr` with
`getResponseHeader` and the value of `X-Receipt-Refusal` is in `REFUSAL_REASONS`, it sets
`detail.shouldSwap = true` and `detail.isError = false`. The key is only that header and only a
value of the closed set, so every other error (network failure, an unmarked 500, a stale reorder
400, any older modal) keeps the default htmx behaviour. Do not widen the condition to a status
range. Real htmx still writes `console.error` for the unswapped 4xx of other requests; that is
expected.

### Stale states

- **Stale card.** A giver-side refresh of a wish card goes through `window.swapWishCard`,
  defined by the inline script of `base.html`. `wishlist.js` wraps it (only if it is a
  function): when the answer is not an `.item-card` with the id of the card being replaced (for
  example an error body for a wish that was fully received meanwhile), the card is replaced by
  `p.item-card-unavailable` (`role="status"`) with the text «Желание больше недоступно.
  Обновите страницу.». The raw answer is never shown.
- **Stale reorder.** The reorder route answers 400 `Invalid item order` (JSON body unchanged)
  and now adds the header `X-Reorder-Refusal: stale_order` (`REORDER_REFUSAL_HEADER` in
  `items_ui.py`). It is a separate namespace from `X-Receipt-Refusal`: the two never meet.
  The listener of `wishlist.js` on `htmx:responseError` checks that header, writes «Список
  изменился. Обновляем.» into `#list-notice` (when it exists) and reloads the page after
  `STALE_RELOAD_DELAY_MS` = 800 ms. An error without the header does nothing (tested).
- **Stale archive and restore.** For a fully received wish `archive_item_ui` and
  `restore_item_ui` answer 409 with `X-Receipt-Refusal: nothing_remaining` through
  `_nothing_remaining_response`. The body is out-of-band only (every top-level element has
  `hx-swap-oob`): `#item-modal-container` emptied, `#list-notice` with
  «Это желание уже полностью получено.», and, when the one extra read succeeds, the list, the
  archive section and «Подаренные». Nothing lands in the card or list target, so the htmx
  default target never receives text. A failed read degrades to the dialog close and the
  notice.

### Owner card, archive and cabinet

- **Flag `is_member`.** The card partial gets `is_member` from `ctx.is_member` (page, card
  route in `sharing.py`) and `_editor_card_flags()` (UI routes). Only a member sees receipt
  figures; a giver, an anonymous visitor and a share-page viewer keep `×M`.
- **Card.** For a member and `received_quantity > 0` the badge is `badge-received`
  «Осталось N из M» and the details have three spans: «Запрошено», «Получено», «Осталось».
  Otherwise the old `×M` badge and «Количество: M». The giver block is guarded by
  `can_promise`, which needs `not item.is_fully_received`, so a stale giver card has no
  promise controls.
- **Archive.** An archived wish with received units is listed with «Осталось N»
  (`.archived-item-remaining`). The archive dialog adds the note «Архивируется только
  неполученная часть: полученные штуки останутся в разделе «Подаренные».» when
  `has_received` (set in `archive_confirm_ui` from `item.received_quantity > 0`).
- **Cabinet.** `reservations_list.html` renders `p.reservation-wish-received` «Желание получено
  владельцем» when `row.wish_received`, and omits the link «К желанию» for such a row. The
  promise status text is not changed (a purchased promise stays «куплено»); a partly received
  wish has no marker and keeps the link. The four promise actions stay governed by
  `offer_actions`.

### Section «Подаренные»

- **Visibility.** `view_wishlist_detail` computes `can_view_gifted` with
  `WishlistAccessPolicy.can_view_gifted(ctx, wishlist)` (a member of a non-deleted list) and
  reads the rows only then. The section is not rendered for a giver, an anonymous or share-page
  viewer, or a non-member, and it is shown on an archived list. It sits after `#items-list`,
  before the archive section, and is separate from the archive.
- **Content.** `<section id="gifted-items-section">`; with rows a `<details>` «Подаренные (N)»
  with one `li.gifted-item#gifted-item-{id}` per wish: title, price (`"<price> <currency>"`,
  `RUB` by default), «Для: <recipient>» when set, «Получено: K из M», and the acts, oldest
  first as in `ReceiptEntryDTO`, each `dd.mm.yyyy — N шт.` (`utc_day`, UTC calendar day). An
  approximate date (`is_approximate`, back-filled data) is shown as `≈ date (дата примерная)`.
  Wish order is the service order (newest receipt first). With no rows the element is empty
  (it stays as the target of out-of-band updates); when the read failed (`gifted_rows is
  none`) it shows «Не удалось загрузить «Подаренные». Обновите страницу.».
- **No data beyond the read, active-list controls.** `GiftedRow` has no promise, giver or
  booking field because `GiftedItemDTO` has none. When `can_edit_wishlist` is true (active list
  and member), each act with `act.receipt_id > 0` renders edit and cancel buttons targeting the
  `/receipts/{receipt_id}/edit` and `/receipts/{receipt_id}/cancel` modals; on archived lists
  «Подаренные» is read-only.
- **Freshness.** Every receipt response carries the section as an out-of-band element, built by
  `read_gifted_rows` (a domain error gives `None`, never a failed response).

### Invariants for developers

- **Surprise secrecy.** The dialog, the card badge, the gifted section, the notice, every
  fragment and every log record omit giver, promise, booked quantity and purchase facts. Do not
  add a field of `WishItemGifterViewDTO` or a reservation to these templates. Tests:
  `test_get_modal_has_no_booking_data`, `test_owner_card_has_no_booking_data`,
  `test_section_has_no_controls_or_booking_data`, `test_full_ui_flow_log_contract`.
- **XSS.** All titles and sentences go through Jinja autoescape or `oob_text`
  (`Markup.format`, which escapes arguments). The notice text with the title is built as a plain
  string and passed to `oob_text` as an argument, so it is escaped too. `receipt.js`
  writes only `textContent` and never server markup.
- **CSP readiness.** This task adds no inline handler and no inline script. The only script tag
  is `<script src="/static/receipt.js" defer>` after `wishlist.js`. The inline script of
  `base.html` is unchanged; a test pins its SHA-256, so an intended edit (WISHENKA-140) needs a
  conscious hash update in `test_inline_script_is_unchanged_and_free_of_receipt_code`. The
  pre-existing `onclick` of the archive modal is left under WISHENKA-140.
- **Dependency on private names.** `receipts_ui.py` imports `receipts._REFUSALS`
  (`wishenka/web/routes/receipts.py`) and the private helpers `_editor_card_flags`, `_execute`,
  `_items_list_html` from `items_ui.py`. WISHENKA-158 (receipt code split) must keep
  `receipts._REFUSALS` importable; the rename to a public accessor is in WISHENKA-163.
- **One record per outcome.** See the log events below.

### Accepted limits

- **S-3 & S-4 (resolved by WISHENKA-161).** Focus return after partial/full receipt and refusal,
  `aria-modal="true"`, `inert`/`aria-hidden` background isolation, `Tab`/`Shift+Tab` focus trap,
  `details.gifted-items-details` open-state preservation, and the `RECEIPT_SELECT_MAX = 20`
  stepper (`> 20`) are implemented and covered in `tests/test_receipt_accessibility_browser.py`.
- The new Russian texts were written by the implementer only and are not reviewed by the
  product owner; «шт.» does not decline.
- Older modals (edit, archive) still show no 4xx or 5xx answers and have no CSS of their own;
  this story fixed only its own paths (marked receipt refusals, stale reorder, stale archive and
  restore). See WISHENKA-160.

### Log events of the UI

Logger `wishenka.web.receipts_ui`, every record has `extra={"event": ...}`, fixed messages, ids
`wishlist_id`, `item_id`, `actor_id` only (no `operation`, `user_id`, `quantity`, title, giver).
`remaining_quantity` only for `quantity_above_remaining` and `nothing_remaining`.

| Event | Level | Written by | Extra keys besides ids |
| ----- | ----- | ---------- | ---------------------- |
| `ui_receipt_form_opened` | INFO | GET, dialog opened | none |
| `ui_receipt_entry_form_opened` | INFO | GET, edit/cancel dialog opened | `receipt_id` |
| `ui_receipt_form_refused` | WARNING | GET, any refusal incl. `busy` | `reason`, `http_status`, `remaining_quantity`? |
| `ui_receipt_entry_form_refused` | WARNING | GET, edit/cancel dialog refusal incl. `busy` | `reason`, `http_status`, `remaining_quantity`? |
| `receipt_recorded_http` | INFO | POST, after commit and state read | none |
| `receipt_corrected_http` | INFO | POST `/edit`, after commit and state read | `receipt_id` |
| `receipt_cancelled_http` | INFO | POST `/cancel`, after commit and state read | `receipt_id` |
| `receipt_refused` | WARNING | POST, refusal | `reason`, `http_status`, `remaining_quantity`? |
| `receipt_inventory_busy` | WARNING | POST, `InventoryBusyError` | none |

The stale archive and restore write no UI record (the service already writes
`wish_archive_refused`); the stale reorder writes only the existing `ui_items_reorder_rejected`.
`receipt_recorded_http`, `receipt_refused` and `receipt_inventory_busy` have the same names on
`wishenka.web.receipts` (JSON route): tell the channel by logger name, and filter by logger in
any metric. Details, audit and the metrics derivable from these events:
`ai-tasks/WISHENKA-24/50-observability.md`. No client-side logging exists in `receipt.js` or the
new `wishlist.js` code.

### Browser tests and the htmx stub

`tests/test_receipt_modal_browser.py` (module mark `timeout(45)` and `browser`) has nine
browser tests: dialog summary and dismissal, partial and full receipt on the page, no second
request on a second tap, refusal then generic failure, busy keeps the dialog and the quantity,
the guarded closed `beforeSwap` override, a stale giver card, a stale reorder, and an unmarked
error that shows no notice and does not reload. The helpers are `record_receipt`,
`archive_item_rest`, `open_receipt_dialog`, `posts_to`, `scroll_to` in
`tests/browser_helpers.py`. See [testing.md](testing.md).

The tests run the own stub `tests/browser_assets/htmx_stub.js`, not real htmx, and the stub does
not process `hx-*` attributes, so the tests start flows with `htmx.ajax`. The stub was extended
by this story: `htmx:beforeSwap` carries `detail.xhr` (`status`, `responseText`,
`getResponseHeader`), `shouldSwap` and `isError`; an unswapped error dispatches
`htmx:responseError`; `swap: 'none'`; out-of-band swaps. Known divergences from real htmx
1.9.12:

- The in-flight gate of the double-tap test holds `window.fetch`, but real htmx sends XHR, so
  the gate would not hold a request under the real library.
- `assert_clean_console` in the receipt browser tests would fail under real htmx, which logs
  `console.error` for every unswapped 4xx.
- The stub swaps nothing for status 400 and above, so its header text that the additions are
  "all additive" is not strictly true.
- The connection `hx-get` on the card button, the `htmx-request` classes and the CSRF header
  are not exercised; they were verified once by hand against real htmx in a scratch copy.

Covered by WISHENKA-145 (real-htmx smoke test) and WISHENKA-162 (stub and assertions).

### Follow-up tickets of the UI

| Ticket | Subject |
| ------ | ------- |
| WISHENKA-160 | Bug (High): older modals show no 4xx/5xx answers and have no CSS (edit 409 and 503, archive 409, reorder 400); link to WISHENKA-90 |
| WISHENKA-161 | Implemented: receipt dialog accessibility (`aria-modal`, `inert`, Tab trap, focus return), `gifted-items-details` open state, `RECEIPT_SELECT_MAX = 20` stepper, 44 px mobile touch targets |
| WISHENKA-162 | Stub docstring, XHR gate, console assertions (with WISHENKA-145) |
| WISHENKA-163 | Web-layer structure: shared OOB helpers, private imports, page-state dataclass, constants module, notice text in the sentence table |
| WISHENKA-164 | Wording review of the new Russian texts, quantity forms |
| WISHENKA-165 | Implemented: CSS tokens, `STALE_RELOAD_DELAY_MS`, one default currency |

Existing tickets that cover related work: WISHENKA-145 (real htmx smoke test, stub fidelity),
157 (log-contract hardening, shared event names), 158 (receipt code split; keep
`receipts._REFUSALS` importable), 140 (inline script and `onclick`, SHA-256 pin), 118 (snapshot
and writer cost: the page now reads the list three times), 33 (RU/EN rendering), 90 (global
htmx error hooks).

## Configuration

All settings are `wishenka.config.Settings` fields; environment names are the field name in upper
case with the prefix `WISHENKA_`. Out-of-range values fail at startup.

| Field | Default | Validation | Meaning |
| ----- | ------- | ---------- | ------- |
| `receipt_notice_worker_enabled` | `True` | bool | Start the notice worker (still needs a usable token) |
| `receipt_notice_poll_interval_seconds` | `5.0` | `> 0`; must not exceed the window | Worker poll interval |
| `receipt_notice_max_attempts` | `5` | `1 <= n <= 20` | Maximum attempts per row |
| `receipt_notice_backoff_base_seconds` | `30` | `>= 1` | First retry delay |
| `receipt_notice_backoff_max_seconds` | `3600` | `>=` the backoff base | Retry delay cap |
| `receipt_notice_request_timeout_seconds` | `30.0` | `> 0` | Telegram HTTP timeout; the worker waits this plus 5 s |
| `receipt_notice_claim_lease_seconds` | `300` | `>=` request timeout + 30 | Age after which a `sending` row counts as dead |
| `receipt_notice_summary_window_seconds` | `300` | `>= 60` | Fixed wall-clock window of the INFO summary |
| `receipt_notice_retention_days` | `30` | `>= 1` | Age after which finished rows are purged |
| `notice_global_per_second` | `20` | `1 <= n <= 30` | Global send limit per second across workers |
| `notice_chat_interval_seconds` | `1` | `>= 1` | Per-chat minimum send interval in seconds |
| `notice_reminder_lead_days` | `(7,)` | positive ints | Occasion reminder lead days in UTC |

The cross-field rules live in `Settings._check_receipt_notice_limits` (backoff max, lease,
poll vs window). Module constants that are not settings: `CLAIM_BATCH_LIMIT = 50`,
`TITLE_LIMIT = 100`, `MAX_ERROR_BACKOFF_SECONDS = 60.0`, the backoff factor 2.

Other settings used: `bot_token` (`WISHENKA_BOT_TOKEN`, default `dummy_bot_token`, meaning "not
configured"), `log_level` (`WISHENKA_LOG_LEVEL`, default `INFO`), `background_cleanup_enabled`.
The notice event is on by default for every user; settings rows are written by tests only until
a settings screen exists (WISHENKA-34).

## Logging

Every record sets `extra={"event": ...}`. The notice path correlates by `outbox_id` only.

| Event | Level | Logger | Keys |
| ----- | ----- | ------ | ---- |
| `item_fulfilled` | INFO | `wishenka.wishlists` | `wishlist_id`, `item_id`, `user_id`, `actor_id`, `quantity`, `received_quantity`, `total_quantity`, `fully_received` |
| `receipt_cancelled` | INFO | `wishenka.wishlists` | `wishlist_id`, `item_id`, `receipt_id`, `user_id`, `actor_id`, `received_quantity`, `total_quantity` |
| `receipt_corrected` | INFO | `wishenka.wishlists` | `wishlist_id`, `item_id`, `receipt_id`, `user_id`, `actor_id`, `old_quantity`, `new_quantity`, `received_quantity`, `total_quantity` |
| `receipt_recorded_http` | INFO | `wishenka.web.receipts` | `item_id` |
| `receipt_cancelled_http`, `receipt_corrected_http` | INFO | `wishenka.web.receipts` | `item_id`, `receipt_id` |
| `receipt_refused` | WARNING | `wishenka.web.receipts` | `operation`, `wishlist_id`, `item_id`, `actor_id`, `reason`, `http_status`, `remaining_quantity` (the two remaining-quantity reasons only) |
| `fulfillment_quantity_exceeded` | WARNING | `wishenka.wishlists` | `item_id`, `wishlist_id`, `user_id`, `received_quantity`, `remaining_unfulfilled` |
| `access_denied` (`action=record_item_fulfillment`) | WARNING | `wishenka.wishlists` | `actor_id`, `user_id`, `wishlist_id`, `item_id`, `action` |
| `receipt_inventory_busy` | WARNING | `wishenka.web.receipts` | `operation`, `wishlist_id`, `item_id`, `actor_id` |
| `wish_archived_partial`, `wish_restored_partial` | INFO | `wishenka.wishlists` | `wishlist_id`, `item_id`, `actor_id`, `received_quantity`, `total_quantity` (silent when nothing was received) |
| `wish_archive_refused` | WARNING | `wishenka.wishlists` | `wishlist_id`, `item_id`, `actor_id`, `reason=nothing_remaining` |
| `legacy_receipts_backfilled`, `legacy_archived_rows_normalised` | INFO | `wishenka.wishlists.migrations` | `rows` |
| `receipt_notice_worker_started`, `receipt_notice_worker_stopped` | INFO | `wishenka.wishlists.notices` | none |
| `receipt_notice_worker_disabled` | INFO | `wishenka.wishlists.notices` | `reason` |
| `receipt_notice_worker_error` | ERROR | `wishenka.wishlists.notices` | `error_class` |
| `receipt_notice_window_summary` | INFO | `wishenka.wishlists.notices` | `window_seconds`, `sent`, `retried`, `failed_terminal`, `uncertain` |
| `service_delivery_window_summary` | INFO | `wishenka.wishlists.notices` | `window_seconds`, `sent`, `retried`, `failed_terminal`, `uncertain`, `skipped` |
| `receipt_notice_rows_purged` | INFO | `wishenka.wishlists.cleanup` | `rows` |
| `receipt_notice_purge_failed` | WARNING | `wishenka.wishlists.cleanup` | `error_class` |
| `receipt_notice_created` | DEBUG | `wishenka.wishlists.notices` | `outbox_id` |
| `receipt_notice_skipped` | DEBUG | `wishenka.wishlists.notices` | `outbox_id`, `gate` (`list` or `user`) |
| `receipt_notice_sent` | DEBUG | `wishenka.wishlists.notices` | `outbox_id`, `attempt` |
| `receipt_notice_send_failed`, `receipt_notice_retry_scheduled`, `receipt_notice_failed_terminal`, `receipt_notice_uncertain` | DEBUG | `wishenka.wishlists.notices` | `outbox_id`, `attempt`, `error_class` |
| `receipt_notice_late_write_ignored` | DEBUG | `wishenka.wishlists.notices` | `outbox_id` |
| `receipt_notice_batch_processed` | DEBUG | `wishenka.wishlists.notices` | `rows` |
| `ui_receipt_form_opened`, `ui_receipt_entry_form_opened`, `ui_receipt_form_refused`, `ui_receipt_entry_form_refused`, `receipt_recorded_http`, `receipt_corrected_http`, `receipt_cancelled_http`, `receipt_refused`, `receipt_inventory_busy` | INFO or WARNING | `wishenka.web.receipts_ui` | ids only, see [Log events of the UI](#log-events-of-the-ui) |

Rules:

- **Notice events carry `outbox_id` only.** No `receipt_id`, `item_id`, `wishlist_id`,
  `event_type` or giver id, so no log line joins an outbox row to a receipt, a wish or a list.
  The join exists only in the database. Producer DEBUG events are written after the commit.
- **At INFO or above** the worker writes only the aggregate `receipt_notice_window_summary`, once
  per closed fixed wall-clock window and only when the window processed rows (counted only when
  the guarded write changed a row), plus start, stop, disabled, purge and the error record. An idle
  worker, an empty window and a stop write no summary (the stop does write
  `receipt_notice_worker_stopped`, without counts; unfinished window counters are dropped).
- **Never logged**: giver identity (user id, Telegram id, username, name, chat id); anything about
  reservations (ids, status, occupied or free quantity, number of promises); the number of notices
  or givers per receipt; notice text, titles, free-text exception messages, Telegram error bodies;
  the bot token and cookies. In `receipt_refused` the field `remaining_quantity` is logged only
  for `quantity_above_remaining` and `nothing_remaining`. The service event
  `fulfillment_quantity_exceeded` logs the same number as `remaining_unfulfilled`, and no other
  event logs a remaining quantity. Failures log `error_class` (the class name) only. Event names
  and fixed messages of the notice path contain none of `notification`, `outbox`, `push`.
- **Operator-only logs requirement.** Debug logs and the window summary must stay in
  operator-only logs and never reach an owner or any user. On an otherwise idle system a summary
  with non-zero counts appears after a window that contained a receipt with an open promise, and
  `WISHENKA_LOG_LEVEL=DEBUG` (a normal setting) re-exposes presence: `receipt_notice_created`
  appears right after `item_fulfilled`. Do not forward these logs to a user-visible channel.
- `item_fulfilled` is logged inside the unit of work, before the commit. A failed commit can leave
  the record of an act that was rolled back (the store then logs `wishlist_inventory_rolled_back`).
- An enqueue failure has no event of its own: the receipt rolls back like any storage failure,
  which avoids a presence signal.

### Metrics

No exporter exists (WISHENKA-84). Candidates are derived from INFO-and-above events and SQL. No
metric uses a DEBUG event, and labels never use a user, wishlist, item or giver.

- Accepted receipts: `item_fulfilled` (`fully_received` gives the full flag); refused:
  `receipt_refused.reason`; cross-check `SELECT count(*) FROM wl_receipts`.
- Queue by status: `SELECT status, count(*) FROM notification_outbox GROUP BY status`.
  Depth is the `pending` count (add `sending` for "not finished"); oldest pending age is
  `now - min(created_at)` over `pending` rows; terminal failures are the `failed` count.
- Sent, retried, failed-terminal totals: the `receipt_notice_window_summary` counts, delayed by up
  to one window.
- `ambiguous` / `uncertain` gauge: `SELECT count(*) FROM notification_outbox WHERE ambiguous = 1`.
  Unconfirmed sends and expired `sending` leases transition to `status = 'uncertain'` with
  `ambiguous = 1` (`CHECK(ambiguous=0 OR status NOT IN ('pending','sending'))`). Explicit operator
  resolution via `operator.resolve(..., action="retry")` resets `ambiguous = 0` when re-queuing a
  row as `pending`, whereas `action="fail"` moves the row to `status = 'failed'` with
  `ambiguous = 1`. Query `WHERE status = 'uncertain'` for quarantined unconfirmed deliveries
  awaiting operator action and `WHERE ambiguous = 1 AND status = 'failed'` for unconfirmed
  deliveries resolved as failed.
- Delay proxy: `updated_at - created_at` of `sent` rows (no `sent_at` column, second resolution).
- Not derivable: totals of send failures by class (`last_error_class` describes the current state
  of a row and is cleared by a later success); a duplicates counter (dropped by design).

## Troubleshooting

- **No notice arrives and rows stay `pending`.** Check the startup log for INFO
  `receipt_notice_worker_disabled`: `reason=no_bot_token` means `WISHENKA_BOT_TOKEN` is empty,
  `dummy_bot_token` or malformed; `disabled_by_setting` means
  `WISHENKA_RECEIPT_NOTICE_WORKER_ENABLED=false`. Set a real token and restart. Rows are kept and
  are sent after a worker starts.
- **A giver got no notice though the promise was open.** Look at the row:
  `SELECT status, skip_reason, attempts, ambiguous, last_error_class FROM notification_outbox
  WHERE giver_user_id = ?`. `skipped` with `setting_list` or `setting_user` is a settings row
  that switched the event off; `skipped` with `target_gone` means the list was deleted or the wish
  gone at claim time; `failed` with a Telegram error class (for example a forbidden bot) is a
  rejected send that is never retried. A giver who is the recipient of the wish gets no row.
- **Rows stuck in `sending`.** A worker died or was cancelled mid-send. They are settled after
  `receipt_notice_claim_lease_seconds` (default 300) by the next `claim_next` of any worker: marked
  `status = 'uncertain'` (`ambiguous = 1`, `last_error_class = 'StaleClaim'`) and quarantined
  without automatic resend until resolved via `python -m wishenka.notices.operator` (see
  [notifications.md](notifications.md)).
- **Queue read by status.** `SELECT status, count(*) FROM notification_outbox GROUP BY status;`
  and for details `SELECT id, status, attempts, ambiguous, next_attempt_at, last_error_class
  FROM notification_outbox WHERE status IN ('pending', 'sending', 'uncertain', 'failed') ORDER BY id`.
  `next_attempt_at` is epoch seconds.
- **ERROR `receipt_notice_worker_error`.** The queue could not be read or settled in a tick (the
  field is the exception class). The worker backs off to 60 s and logs again only after a
  successful tick. Check the database and the writer lock.
- **DEBUG `receipt_notice_late_write_ignored`.** A settle arrived after its claim was lost
  (a send slower than the lease, or the row was reclaimed). The late result is dropped by the
  guard. If it recurs, check that the lease is well above the request timeout (the validator
  requires lease >= timeout + 30).
- **Receipt refused.** Read `detail.reason`: `quantity_above_remaining` and `nothing_remaining`
  include the current `remaining_quantity` (a lost race between two authors looks like this);
  `wish_archived` means restore the wish first. `wishlist_not_active` with 409 is an archived
  list: restore it. With 404 it is a deleted list, which this route cannot restore;
  `forbidden` is a non-member; `busy` is a retryable 503 with nothing changed.
- **A downgrade is needed.** `alembic downgrade` stops at `add_gift_receipts`, which raises
  `NotImplementedError`. Restore the database from a backup taken before the release.
- **Receipt dates look the same for old wishes.** Back-filled records use the wish's last update
  and have `is_approximate = true`.
- **Wishes missing in the public view.** Archived and fully received wishes are hidden from
  public-link and non-member viewers by design (`projection`).
- **Receipt dialog shows nothing after a refusal.** The answer must carry `X-Receipt-Refusal`
  with a value of the closed set, otherwise `receipt.js` leaves htmx at its default (4xx and 5xx
  are not swapped) and the dialog shows the generic sentence. Check the response header of the
  `/web/.../receipt` request and that `REFUSAL_REASONS` in `receipt.js` still equals the
  `receipts._REFUSALS` reasons plus `busy`.
- **Reorder error shows nothing, or the page reloads by itself.** The reload is the stale-order
  handler (`X-Reorder-Refusal: stale_order`, 800 ms). Any other 400 on a page action is not
  shown; that is WISHENKA-160.
- **«Подаренные» is missing.** It is rendered only for a member of a non-deleted list, and the
  element is empty when nothing was received. «Не удалось загрузить «Подаренные»» means
  `read_gifted_rows` got a domain error; reload the page.
- **Not built yet** (see Overview): settings screen (WISHENKA-34), metrics
  exporter (WISHENKA-84), target rules `FR-5` (`WISHENKA-218`) and `FR-6` (`WISHENKA-219`) from
  `WISHENKA-154`, and the UI follow-ups WISHENKA-160 to 164.

## Tests

New modules, each with a module-level `pytest.mark.timeout`: `tests/test_gift_receipt_service.py`,
`test_gift_receipt_api.py`, `test_gift_receipt_migration.py`, `test_receipt_notices.py`,
`test_receipt_notices_extra.py`, `test_receipt_concurrency.py`, `test_receipt_observability.py`,
`test_surprise_receipt_walk.py`; helpers `tests/receipt_support.py` and `tests/notice_support.py`
(`FakeNoticeSender`). Three existing modules were edited: `test_wishlist_migrations_concurrency.py`
(`_HEAD = head_revision()`), `test_surprise_role_context.py` (the absence assertion replaced by
`notice_rows` and `receipt_columns` checks, see [verification-matrix.md](verification-matrix.md))
and `test_shared_inventory_multiprocess.py` (a receipt on a fully received wish now raises
`NothingRemainingError`, not a plain `ValueError`). The Telegram `Bot` is mocked everywhere; a live
smoke test is WISHENKA-156.

UI modules (WISHENKA-24), each with a module-level `pytest.mark.timeout`:
`tests/test_receipt_ui_routes.py` (GET and POST routes, refusals by reason, busy, 401 and CSRF,
reason table, logging), `test_receipt_card_ui.py` (owner card, button, archive texts, stale
archive and restore, giver guard, stale reorder header), `test_gifted_section_ui.py`,
`test_cabinet_received_marker.py`, `test_receipt_static_script.py` (script served and ordered,
inline script hash, closed reason set, no inline handlers), `test_receipt_ui_observability.py`
(full-flow log scan), `test_receipt_undo_correction_repro.py` (WISHENKA-153: service, notices,
JSON `DELETE`/`PATCH`, and UI edit/cancel modals), and the browser modules
`test_receipt_modal_browser.py` and `test_receipt_accessibility_browser.py` (WISHENKA-161:
`aria-modal`/background `inert`/Tab trap, focus return on partial/full/refusal,
`gifted-items-details` open state, `remaining=500` stepper, 44 px mobile touch targets & quick-add
overlay at `390x844`); helper `tests/receipt_ui_support.py`. See [testing.md](testing.md).
