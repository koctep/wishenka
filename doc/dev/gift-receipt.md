# Gift Receipt and the «Подаренные» Section

> **Status: PLANNED — specified by WISHENKA-22, not implemented until
> WISHENKA-23 (backend) and WISHENKA-24 (frontend). Everything below
> describes target behaviour, route paths and DTO names are indicative.**

Read this document as a specification handed to the developers of
WISHENKA-23 and WISHENKA-24. Current behaviour is described in
[items.md](items.md), [reservations.md](reservations.md) and
[architecture.md](architecture.md). When the code lands, the Step 8 of each
follow-up story turns the relevant parts of this file into current
documentation and removes the "planned" markers.

Sources of truth, in order: `in-docs/spec.md` (sections 7.2, 7.3), then
`ai-tasks/WISHENKA-22/10-requirements.md` (rules FR-1 to FR-6, corner
cases), `20-architecture.md` (design, contract) and `50-observability.md`
(logging).

## Overview

An author records that a gift arrived in real life. The product keeps
**receipt** (the owner's statement about the real world) and **promise** (a
giver's statement about intent) as independent facts. It never reconciles
them on the giver's behalf, because it cannot know which giver's gift came.

### Scenarios and rules

- **Who and when.** Only an author of the list (owner, or a participant with
  the right to edit wishes) records receipt. The wish must be active on an
  active list, with remaining quantity above zero. The author chooses a
  quantity from 1 to the remaining quantity. No giver is named and none is
  needed: an unpromised gift can be recorded (FR-1).
- **Partial receipt.** Each act adds to the received quantity. The wish
  stays on the active list with the reduced remaining quantity, and its
  received part appears in «Подаренные» (FR-2.1, FR-2.2).
- **Full receipt.** The act that brings received up to requested makes the
  wish fully received. It leaves the active list and is shown only in
  «Подаренные». It takes no new promises (FR-2.3, FR-2.4).
- **Free quantity.** `max(0, requested - received - occupied)`. This formula
  is unchanged.
- **Receipt never touches promises.** It does not close, cancel, change or
  mark purchased any promise. Only the giver does that (FR-3.1, FR-3.2).
  A purchased promise is treated like an intended one (FR-3.5).
- **Over-booked state.** After receipt, `received + occupied` may exceed
  `requested`. This is legal. While it lasts, no new promise and no increase
  of an existing one is possible. A giver may still lower, cancel or mark
  purchased. The first cancellations only shrink the excess and free nothing
  (FR-3.3, FR-3.4, FR-3.7). The product does not choose whose promise to drop.
- **Fully received wish and its givers.** An open promise stays in the
  giver's cabinet with a «received» marker and the cabinet actions. The wish
  card shows no giver controls. A purchased promise has no "completed" state
  and stays until the giver cancels (FR-3.6).
- **Giver notice.** After each successful act, every giver with an open
  promise gets one notice per act (not per promise) in the Telegram bot,
  subject to notification settings. It names the wish and the list and
  invites the giver to review the promise. It carries no quantities, no other
  giver and no hint of excess. A failed delivery never fails the receipt
  (FR-4).
- **Archive split.** A wish with received units is never archived as a
  whole. Archive moves only the unreceived part to the archive, the received
  part stays in «Подаренные». Restore brings back the remaining quantity.
  Archive is not offered for a fully received wish. Open promises survive
  both (FR-3.8, FR-5.2).
- **«Подаренные» is not the archive.** It holds wishes with received quantity
  above zero, is read-only, shows the dates of the receipt acts and never
  shows givers or promises. It is for authors and not for gifters. It stays
  readable when the list is archived and goes with the list when the list is
  deleted (FR-5).
- **Surprise.** Receipt, its refusals, «Подаренные» and the notice reveal
  nothing about promises, givers, booked quantity or purchases (FR-6). The one
  known exception is the existing quantity-reduction lock in the edit form
  (requirements Q12), which is unchanged.

Not covered: undo or correction of a receipt (tracked in WISHENKA-153), and
money, shared purchase, thanking givers.

## Architecture

Planned design, see `20-architecture.md` sections 1 to 7 for the diagram.

- **Wish row (single source of truth).** `quantity` and `received_quantity`
  stay on `wl_items`. There is no new column and no split of the wish into
  two rows. Remaining is derived.
- **Receipt records (`wl_receipts`, new).** One append-only row per act:
  wish, quantity, date. No giver column, and no link to reservations, by
  design. The counter equals the sum of the records, and both are written in
  the same transaction. Deleting a list cascades to the records.
- **Derived views over one row.** One shared predicate set, not per-template
  logic:

  | View | Rule |
  | ---- | ---- |
  | Active list (and reorder) | `is_archived = 0` and `received_quantity < quantity` |
  | «Подаренные» | `received_quantity > 0`, regardless of `is_archived` |
  | Archive | `is_archived = 1` and `received_quantity < quantity`, shown with the unreceived quantity |

  No «Подаренные» query may join `wl_reservations`.
- **`WishlistService.record_item_fulfillment`.** Exists today with the
  author check, the quantity floor and cap, and the counter write. It gains
  the guards of FR-1.2, the receipt record write and the notice set. It runs
  through `WishlistStore.execute_wish` (`BEGIN IMMEDIATE`) and adds no new
  lock.
- **`archive_wish_item`, `restore_wish_item`.** Act on the unreceived part.
  Archive of a fully received wish is refused.
- **Legacy rows.** Rows with `is_archived = 1` and `received_quantity > 0`
  may exist today. A fully received one is shown only in «Подаренные» and the
  WISHENKA-23 migration clears its flag. A partly received one stays archived.
  Restore of a fully received legacy row is refused with `nothing_remaining`.
- **Notification path.** A transactional outbox plus an async worker, as
  already decided in [architecture.md](architecture.md) (see below).
- **Read models.** Active list item plus `remaining_quantity`. «Подаренные»
  entries with receipt dates and quantities. Archive with unreceived
  quantity. Giver card and cabinet row gain a boolean `is_fully_received`,
  derived only from the two counters.

### Concurrency

The receipt is one more writer in the wish-scoped transaction. Inside it the
order is: load wish and open promises, check guards, check the cap, add the
counter, insert the receipt record, build the notice set, insert outbox rows,
commit. A refusal rolls everything back. A receipt racing a promise on one
wish serialises: either order keeps the invariants. `InventoryBusyError`
becomes the same retryable 503 as on promise routes.

### Notification path

1. **Producer** (in the receipt transaction): one outbox row per distinct
   giver with an `ACTIVE` or `PURCHASED` promise on the wish, excluding anyone
   who is the recipient of that wish. The payload holds giver id, wish id,
   list id, event type and receipt record id. It holds no quantity.
2. **Settings gate, evaluated by the producer** in the same transaction, once
   per giver. The worker never reads settings. The row is created `pending`
   or `skipped` (terminal, kept for audit). Lookup order: list-level row, else
   user-level row, else default on. Two levels are stored:
   `user_notification_settings` `(user_id, event_type)` and a new list-level
   table, indicatively `wishlist_notification_settings`
   `(user_id, wishlist_id, event_type)`. No screen writes them in this story
   (see Troubleshooting).
3. **Worker** (async, started from the app lifespan): takes `pending` rows,
   renders a fixed template, sends through the bot, marks `sent`. A send error
   schedules a retry with a bounded attempt count, then a terminal `failed`
   state. It runs after commit and never delays or fails the receipt.
4. **Delivery is at-least-once.** A duplicate is possible if the worker
   crashes between send and mark-sent. The de-dup key `(receipt record,
   giver)` only bounds duplicates to one row per giver per act. Several acts
   give several notices.

## API / Usage

All names and paths are indicative. WISHENKA-23 fixes the final ones in its
own Step 2 and Step 8. The shape and rules below are the contract between the
two stories.

### Receipt command

Author only, cookie or bearer, CSRF as for other mutations.

- **Input**: the wish and an integer `quantity`. Nothing else. No giver field
  exists.
- **Success**: the wish in its recipient-safe projection, plus
  `received_quantity`, `remaining_quantity` and a fully-received flag. Never a
  booking field.
- **Refusals**: a closed set of business reasons with fixed wording that never
  states or implies booked units:

  | Reason | Meaning | HTTP |
  | ------ | ------- | :--: |
  | `quantity_invalid` | below one | 400 |
  | `quantity_above_remaining` | above remaining; message may name only the remaining quantity | 409 |
  | `wish_archived` | wish is in the archive | 409 |
  | `wishlist_not_active` | list archived (409) or deleted (404) | 409 / 404 |
  | `nothing_remaining` | wish already fully received | 409 |
  | `forbidden` | not an author | 403 |
  | `busy` | wish lock busy, nothing changed, retry | 503 |

  A lost race between two authors surfaces as `quantity_above_remaining` or
  `nothing_remaining` with the then-current remaining quantity.

### Read models for WISHENKA-24

- **Active list item**: as today plus `remaining_quantity`. A fully received
  wish is not in it.
- **«Подаренные»**: for authors only (gifters and anonymous callers are
  refused). Per wish: recipient-safe fields, `received_quantity`, and receipt
  entries (date, quantity). Read-only: no edit, move, promise or archive link.
- **Archive**: archived, not fully received wishes, with `remaining_quantity`
  as the unreceived quantity.
- **Gifter card and cabinet row**: add `is_fully_received`. The cabinet shows
  the four promise actions for a wish that is archived on an active list, or
  fully received on an active list. The wish card shows no giver controls for
  a fully received wish.
- **Archive and restore** keep their routes. Archive of a fully received wish
  and restore of a wish with nothing remaining are refused with
  `nothing_remaining`.

### Contracts between WISHENKA-23 and WISHENKA-24

- WISHENKA-23 owns the rules FR-1 to FR-3, the notice path (FR-4), the
  shared active predicate, the archive split, the read models and the routes.
  It fixes the final route paths, DTO names and refusal wording.
- WISHENKA-24 owns the receipt screen (quantity 1 to remaining, explicit
  confirmation because the act is final), the active list and card changes,
  the «Подаренные» section separate from the archive, the cabinet marker for a
  received wish, readable refusals mapped from the closed reasons, and the
  reorder UI.
- WISHENKA-24 starts after the contract above is fixed in WISHENKA-23 Step 4,
  or against a stub that returns the contract shape.
- The frontend has no notice API. Only the bot sends notices. WISHENKA-24 does
  not own the notice text.
- Open for WISHENKA-24: the cabinet link target for a fully received wish
  (recommended: omit the link and keep the actions).

### Logging rules (from `50-observability.md`)

WISHENKA-23 owns all domain logging. WISHENKA-24 adds only route-level records
for the receipt route and no client-side logging of wish or booking data.

- Logger `wishenka.wishlists` for domain events, a `wishenka.web.*` logger for
  the route, one dedicated logger for the worker. Every record sets
  `extra={"event": "<snake_case>"}` with a fixed message and no interpolated
  ids. Business-level fields only.
- INFO: `receipt_recorded`, `wish_archived_partial`, `wish_restored_partial`,
  migration counts, worker started or stopped, and the window summary.
  WARNING: `receipt_refused` (closed `reason` only), `wish_archive_refused`.
  ERROR: `receipt_notice_worker_error`, `receipt_notice_enqueue_failed`
  (`error_class` only).
- **Notice path correlates by `outbox_id` only.** Every `receipt_notice_*`
  event carries no `receipt_id`, `item_id`, `wishlist_id`, `event_type` or
  giver id, and no log field may join an `outbox_id` to a receipt, a wish or a
  list. The join exists only in the database.
- **Per-row producer and worker events are DEBUG only**, and producer events
  are written after the commit. At INFO or above the worker writes only the
  aggregate `receipt_notice_window_summary` (`window_seconds`, `sent`,
  `retried`, `failed_terminal`), once per fixed wall-clock window, only when
  the window processed rows. Window setting: minimum 60 s, default 300 s,
  poll interval not above the window. An idle worker writes nothing, no
  heartbeat.
- **DEBUG logs are operator-only** and must never be exposed to owners or any
  user. `LOG_LEVEL=DEBUG` is a normal setting and re-exposes presence.
- **Never log**: giver identity (user id, Telegram id, username, name, chat
  id); anything about reservations (ids, status, occupied or free quantity,
  number of promises); the number of notices or givers on a receipt record;
  notice text, titles, outbox payload, free-text exception messages, Telegram
  error bodies; tokens and cookies. `remaining_quantity` may be logged only
  for `quantity_above_remaining` and `nothing_remaining`.
- Event names and fixed messages of the notice path must not contain
  `notification`, `outbox` or `push` (the recipient-walk test checks them).
- `item_fulfilled` may be kept or renamed to `receipt_recorded` by
  WISHENKA-23, never both for one act.

## Configuration

Planned, to be fixed by WISHENKA-23:

- A summary window setting (indicatively
  `receipt_notice_summary_window_seconds`): minimum 60, default 300.
- A worker poll interval not above the window and a bounded retry count.
  These must be settings, not literals.
- The notice event is on by default for every user (AR-4). Settings rows are
  written only by tests until a settings screen exists.
- `Settings.log_level` already exists (`wishenka/config.py`, default `INFO`).
- Schema changes go through an Alembic revision, see
  [migrations.md](migrations.md): `wl_receipts` with back-fill (dates of
  records created for existing received wishes are approximate), normalisation
  of legacy archived rows (not reversible by a downgrade), the outbox and both
  settings tables.

## Troubleshooting

Nothing is built yet, so there are no runtime symptoms to describe. What can
be stated now are the open points and where each decision is tracked:

- **Undo or correct a receipt**: not in this version, the act is final.
  Tracked in WISHENKA-153.
- **Product-owner decisions** on assumptions A to D, a public «already gifted»
  label for gifters, history after list deletion, a co-author who is also the
  recipient, and the existing edit-form quantity lock that reveals occupied
  units: tracked in WISHENKA-154.
- **Notification settings screen**: out of scope for 23 and 24, so a giver
  cannot switch the notice off yet. Belongs to WISHENKA-34.
- **Metrics exporter**: the project has none, candidate metrics are derived
  from logs. The exporter question belongs to WISHENKA-84.
- **Open for WISHENKA-23 Step 2**: the split of WISHENKA-23 into notification
  infrastructure and domain rules (decision before its Step 1); one shared
  outbox with WISHENKA-60; outbox retention; behaviour of a soft-deleted list
  versus «Подаренные» (cascade fires only on purge); whether
  `receipt_notice_enqueue_failed` reveals presence.
- **Known test change**: `tests/test_surprise_role_context.py` asserts that the
  two notification tables do not exist and checks log text for
  `notification`, `outbox` and `push`. WISHENKA-23 must replace it with a
  stronger recipient-walk check, not weaken or delete it. See the note in
  [verification-matrix.md](verification-matrix.md).
