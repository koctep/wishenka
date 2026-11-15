# Gift Receipt and the «Подаренные» Section

> **Status: BACKEND IMPLEMENTED by WISHENKA-23; frontend (receipt screen, «Подаренные» section,
> cabinet UI) is WISHENKA-24 — not implemented.**

The backend is the receipt command, the gifted read, the derived views, the receipt history, the
giver notice path (outbox, worker, sender) and the migrations. No template or script calls the
two new routes yet. The cabinet marker (`wish_received`) is computed but no template renders it.

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
  giver, booked quantity or purchase fact. The one known exception is the existing
  quantity-reduction lock in the edit form (WISHENKA-154), unchanged.

### Not implemented

- Receipt screen, «Подаренные» section, cabinet marker UI, wish-card changes: WISHENKA-24.
- Notification settings screen (only tables and lookup exist): WISHENKA-34.
- Metrics exporter: WISHENKA-84 (the metrics are derived from logs and SQL, see Logging).
- Undo or correction of a receipt: WISHENKA-153. The act is final.
- Product decisions (assumptions A to D, public «already gifted» label, history after list
  deletion, co-author who is the recipient, edit-form quantity lock): WISHENKA-154.
- Follow-up debt (all Low): WISHENKA-155 (one digit-free `quantity_invalid` message), 156 (opt-in
  real-Telegram smoke test, two-process worker race test), 157 (log-contract and test hardening),
  158 (split receipt code out of `service.py`, unify the two flush call sites in `store.py`), 159
  (fail-closed `wl is not None` guards).

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
- **Exceptions** (`wishlists/exceptions.py`): `WishRefusalError` base with a stable `reason`;
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

Two Alembic revisions, see [migrations.md](migrations.md). The chain is now
`add_item_order_index` -> `add_gift_receipts` -> `add_notice_outbox` (head).

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
- `head_revision(database_url=<in-memory default>)` in `wishlists/migrations.py` returns the
  single head id of the script directory without opening a database; the concurrency test uses
  it instead of a hard-coded name.

## API / Usage

Both routes are in `wishenka/web/routes/receipts.py` (router prefix `/api/wishlists/{wishlist_id}`,
tag `receipts`, mounted in `create_app`). Authentication is `get_current_user`: session cookie or
bearer token, 401 without one. A cookie session needs the CSRF token like other mutations
(`BrowserSecurityMiddleware`, header `X-CSRF-Token` from `GET /api/auth/csrf`).

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
  | `InventoryBusyError` | 503 | `busy` | the promise-route sentence, nothing changed, retry |

  A wish id that exists in another list is `not_found`. The route constant of the
  `quantity_invalid` message differs from the `QuantityInvalidError` default ("Quantity must be
  a positive whole number"); WISHENKA-155 unifies them. Clients should map by `reason`.

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
- `ReceiptEntryDTO`: `received_at`, `quantity`, `is_approximate` (false). Entries are oldest
  first. No reservation, giver or promise field exists on either DTO.

### Other read data changed by this story

- **`WishItemRecipientViewDTO`** gains `remaining_quantity`; **`WishItemGifterViewDTO`** gains
  `remaining_quantity` and `is_fully_received` (default false); **`MyReservationItemDTO`** gains
  `is_fully_received` (default false, set from the wish by `get_user_reservations`). The first two
  fill the new fields from the quantities in a `mode="before"` validator when they are absent, so
  older constructors keep working.
- **Cabinet row** (`CabinetRow` in `web/routes/reservations_ui.py`): new `wish_received` (the wish
  is fully received) and `offer_actions = (wish archived or wish received) and list not archived`.
  The four promise actions are therefore offered for a received wish on an active list. No
  template renders `wish_received` yet (WISHENKA-24). Hiding the giver controls on the wish card
  of a fully received wish is a WISHENKA-24 task as well.
- **Public and wishlist projection** (`projection` in `web/routes/wishlists.py`): each item now
  has `remaining_quantity` and `is_active`, and a wish that is not `is_active` (archived or fully
  received) is omitted for anonymous, public-link and non-member viewers. Members still get all
  wishes. This is a visible behaviour change of the projection: before, archived wishes were
  listed for non-members.
- **Archive and restore** (`items.py` `execute`, `items_ui.py`): `NothingRemainingError` is a 409
  with the fixed message "Nothing remains to receive" on the archive and restore routes for a
  fully received wish.

## Notice path

Delivery of the giver notice is a transactional outbox plus an in-process async worker.

### Outbox table `notification_outbox`

Created by `add_notice_outbox`. Columns: `id`, `event_type` (`gift_received`), `receipt_id` (FK
to `wl_receipts`, cascade), `wishlist_id` (FK, cascade), `wish_item_id` (FK, cascade),
`giver_user_id`, `status`, `skip_reason`, `attempts` (default 0), `ambiguous` (0 or 1),
`next_attempt_at` (integer epoch seconds), `claimed_at` (integer epoch seconds, set only while
`sending`), `last_error_class`, `created_at`, `updated_at` (ISO text). Unique key
`(event_type, receipt_id, giver_user_id)`, index `idx_notice_outbox_due (status,
next_attempt_at)`. There is no payload, text or quantity column: the text is rendered at send
time from the current titles.

| `status` | Meaning |
| -------- | ------- |
| `pending` | waiting for `next_attempt_at` |
| `sending` | claimed by a worker; `claimed_at` is the claim token |
| `sent` | delivered (terminal) |
| `failed` | gave up (terminal), `last_error_class` holds the class name |
| `skipped` | terminal; `skip_reason` is `setting_list`, `setting_user` or `target_gone` |

`ambiguous = 1` marks a send whose outcome is unknown (a timeout, a 5xx, a network or unexpected
error, or a dead claim). It is never cleared.

### Producer (inside the receipt transaction)

`WishlistService._draft_receipt_notices`: one notice per distinct giver with an `ACTIVE` or
`PURCHASED` reservation on the wish, in first-reservation order, excluding anyone who is the
recipient of that wish (`is_recipient_id`). It is one notice per giver per act, not per promise.
The giver has no more than one row per receipt (the unique key). Because a receipt id is new in
its own transaction, a key hit does not happen in practice. The rows are inserted by
`_flush_receipt_effects` with `next_attempt_at = now`.

The settings gate is evaluated by the producer, never by the worker
(`WishlistService._notice_gate`), in this order: the list-level row
(`wl_list_notification_settings`: `user_id`, `wishlist_id`, `event_type`, `enabled`), else the
user-level row (`user_notification_settings`: `user_id`, `event_type`, `enabled`), else default
on. A disabled giver gets a `skipped` row (kept for audit)
with `skip_reason` `setting_list` or `setting_user`. No production code writes the settings tables
yet (WISHENKA-34); tests do.

### Worker claim protocol

`NoticeStore.claim_next(now)` (every method is one `BEGIN IMMEDIATE` transaction through
`WishlistStore.transaction`) looks at up to 50 due rows ordered by `next_attempt_at, id`: `pending`
rows whose `next_attempt_at <= now`, and `sending` rows whose `claimed_at <= now - lease`. For each
row in order:

1. If the list is deleted or missing, or the wish is missing: the row becomes `skipped` with
   `target_gone` and the loop continues.
2. If the row is a stale `sending` row (the claim is older than the lease): it is settled first
   and never sent in the same call. It is marked `ambiguous = 1`, `last_error_class =
   StaleClaim`, and becomes `failed` when it was already ambiguous or has reached the maximum
   attempts, otherwise `pending` with the backoff. The loop continues.
3. Otherwise a `pending` row is claimed: `status = sending`, `claimed_at = now`, `attempts + 1`.

The settle writes (`complete`, `fail`, `reschedule`) are one guarded `UPDATE ... WHERE id = ?
AND status = 'sending' AND claimed_at = <token>`. If the claim was lost the write changes
nothing and the DEBUG event `receipt_notice_late_write_ignored` is logged.

`NoticeWorker.run_once` drains all due rows, reading the clock afresh for every claim and settle.
The send is wrapped in `asyncio.wait_for(..., request_timeout + 5)`. The outcome mapping
(`sender.classify_error`, ordered, subclasses first):

| Outcome | Errors | Effect |
| ------- | ------ | ------ |
| `DELIVERED` | no error | `sent` |
| `REJECTED` | forbidden, bad request, not found, entity too large, migrate to chat | `failed` at once, never retried |
| `RETRYABLE` | retry after (honoured: delay is the larger of the backoff and `retry_after`), unauthorized | `pending` with backoff |
| `AMBIGUOUS` | everything else: 5xx, network, timeout, unexpected | first time `pending` with `ambiguous = 1`, second time `failed` |

An attempt number at the maximum also ends in `failed`. Backoff after the n-th failed attempt is
`min(base * 2**(n - 1), max)` seconds (defaults: 30, 60, 120, 240 after attempts 1 to 4; the fifth
failure is terminal). The text is plain (no parse mode): "Желание «<wish>» из списка «<list>»
отмечено как полученное." plus a fixed line inviting the giver to review the promise, with each
title cut at 100 characters. No quantity, no other giver, no hint of excess.

### Delivery guarantee

Delivery is at-least-once. A duplicate is possible when a process dies or is cancelled after
Telegram accepted the message and before the row is marked `sent`: the row stays `sending`, is
reclaimed after the lease as `ambiguous`, and is resent once. The `ambiguous` flag bounds this to
one possible duplicate notice per giver per act; a second unconfirmed outcome ends in `failed`.
A failed or lost delivery never fails or rolls back the receipt. Several acts give several notices.

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

`NoticeStore.purge_finished(threshold)` deletes `sent`, `skipped` and `failed` rows with
`updated_at <= threshold`. It runs at the end of each cleanup cycle (`run_cleanup_cycle`,
`_purge_notices`) with `threshold = now - receipt_notice_retention_days`. A failure is a WARNING
`receipt_notice_purge_failed` and never fails the cycle; INFO `receipt_notice_rows_purged` (`rows`)
is logged only when rows were deleted. It runs only while `background_cleanup_enabled` is true.

## Configuration

All settings are `wishenka.config.Settings` fields; environment names are the field name in upper
case with the prefix `WISHENKA_`. Out-of-range values fail at startup.

| Field | Default | Validation | Meaning |
| ----- | ------- | ---------- | ------- |
| `receipt_notice_worker_enabled` | `True` | bool | Start the notice worker (still needs a usable token) |
| `receipt_notice_poll_interval_seconds` | `5.0` | `> 0`; must not exceed the window | Worker poll interval |
| `receipt_notice_max_attempts` | `5` | `1 <= n <= 20` | Maximum attempts per row |
| `receipt_notice_backoff_base_seconds` | `30` | `>= 1` | First retry delay |
| `receipt_notice_backoff_max_seconds` | `1800` | `>=` the backoff base | Retry delay cap |
| `receipt_notice_request_timeout_seconds` | `30.0` | `> 0` | Telegram HTTP timeout; the worker waits this plus 5 s |
| `receipt_notice_claim_lease_seconds` | `300` | `>=` request timeout + 30 | Age after which a `sending` row counts as dead |
| `receipt_notice_summary_window_seconds` | `300` | `>= 60` | Fixed wall-clock window of the INFO summary |
| `receipt_notice_retention_days` | `30` | `>= 1` | Age after which finished rows are purged |

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
| `receipt_recorded_http` | INFO | `wishenka.web.receipts` | `item_id` |
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
| `receipt_notice_window_summary` | INFO | `wishenka.wishlists.notices` | `window_seconds`, `sent`, `retried`, `failed_terminal` |
| `receipt_notice_rows_purged` | INFO | `wishenka.wishlists.cleanup` | `rows` |
| `receipt_notice_purge_failed` | WARNING | `wishenka.wishlists.cleanup` | `error_class` |
| `receipt_notice_created` | DEBUG | `wishenka.wishlists.notices` | `outbox_id` |
| `receipt_notice_skipped` | DEBUG | `wishenka.wishlists.notices` | `outbox_id`, `gate` (`list` or `user`) |
| `receipt_notice_sent` | DEBUG | `wishenka.wishlists.notices` | `outbox_id`, `attempt` |
| `receipt_notice_send_failed`, `receipt_notice_retry_scheduled`, `receipt_notice_failed_terminal` | DEBUG | `wishenka.wishlists.notices` | `outbox_id`, `attempt`, `error_class` |
| `receipt_notice_late_write_ignored` | DEBUG | `wishenka.wishlists.notices` | `outbox_id` |
| `receipt_notice_batch_processed` | DEBUG | `wishenka.wishlists.notices` | `rows` |

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
- `ambiguous` gauge: `SELECT count(*) FROM notification_outbox WHERE ambiguous = 1`. The flag is
  never cleared, so a row that was ambiguous and later `sent` still counts. Read it as "rows in the
  retention window with a possible duplicate or loss"; add `AND status IN ('sent', 'failed')` for
  possible duplicates and `AND status = 'failed'` for unconfirmed deliveries.
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
- **Rows stuck in `sending`.** A worker died or was cancelled mid-send. They are reclaimed after
  `receipt_notice_claim_lease_seconds` (default 300) by the next `claim_next` of any worker: marked
  `ambiguous` with `last_error_class = StaleClaim`, then `pending` (resent once) or `failed`.
  Nothing to do unless no worker runs at all.
- **Queue read by status.** `SELECT status, count(*) FROM notification_outbox GROUP BY status;`
  and for details `SELECT id, status, attempts, ambiguous, next_attempt_at, last_error_class
  FROM notification_outbox WHERE status IN ('pending', 'sending', 'failed') ORDER BY id`.
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
- **Not built yet** (see Overview): undo (WISHENKA-153), settings screen (WISHENKA-34), metrics
  exporter (WISHENKA-84), the UI (WISHENKA-24), product decisions (WISHENKA-154).

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
