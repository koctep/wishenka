# Service Notifications, Occasion Reminders, and Private Birthday Tracking

> **Status: IMPLEMENTED by [WISHENKA-29](https://pypost.atlassian.net/browse/WISHENKA-29) and
> extended by [WISHENKA-60](https://pypost.atlassian.net/browse/WISHENKA-60), building on the gift
> receipt notice foundation from [WISHENKA-23](gift-receipt.md#notice-path).**

## Overview

The notification and reminder subsystem delivers Telegram bot messages for shared wishlist activity,
gift receipts, approaching dated wishlist events, and owner-scoped private birthday reminders. It
enforces the Surprise Invariant across overlapping roles, verifies live recipient eligibility and
notification preferences immediately before network send, coordinates global and per-chat rate
limits across worker processes, and quarantines ambiguous send outcomes (`uncertain`) instead of
automatically resending or treating them as confirmed deliveries.

Key capabilities:

- **Transactional event production:** Domain mutations (`item_created`, `item_updated`,
  `item_archived`, `item_restored`, `list_updated`, `list_archived`, `list_restored`,
  `membership_changed`, and opt-in `reservation_confirmation`) enqueue content-free intents in
  `reminder_outbox` inside the same SQLite `BEGIN IMMEDIATE` transaction as the domain write. Gift
  receipts continue to use `notification_outbox` with persistent deduplication keys in
  `notice_receipt_keys`.
- **Surprise protection and live eligibility:** Both queues re-evaluate live wishlist/item state,
  roles, recipient exclusions, notification settings (`wl_list_notification_settings` overriding
  `user_notification_settings`), and verified bot destinations (`bot_destinations`) at claim time
  and again immediately before network delivery.
- **Private birthday tracking (`/birthdays`):** Users privately add, list, edit, and delete up to
  20 labeled `MM-DD` entries in a private bot chat without supplying a birth year or linking to
  another user's account.
- **UTC occasion scheduler:** `ReminderScheduler` scans active dated wishlists and private birthday
  entries in bounded pages (`PAGE_SIZE = 1000`) with persistent cursors, scheduling reminders in
  UTC for configured lead days (default `(7,)`) and mapping February 29 to February 28 in non-leap
  years.
- **Shared persistent rate limiter:** `notice_rate_slots` enforces global (`20/s` default),
  per-chat (`1s` default), and provider `RetryAfter` (`blocked`) limits across processes without
  holding database locks during network I/O.
- **Uncertain-delivery quarantine and operator CLI:** Timeouts, network errors, 5xx responses, and
  expired `sending` leases transition rows to `status = 'uncertain'` and never automatically
  resend. Operators inspect aggregate counts and explicitly retry or fail uncertain rows via
  `python -m wishenka.notices.operator`.

## Architecture

```text
Wishlist / Bot Mutations -- BEGIN IMMEDIATE --> EventProducer.record() ----> reminder_outbox
Gift Receipt -------------- BEGIN IMMEDIATE --> _flush_receipt_effects() --> notification_outbox
                                                                             + notice_receipt_keys
Dated Wishlists ----------- UTC paged scan -\
                                             +--> ReminderScheduler -------> reminder_outbox
Private /birthdays -------- birthday_entries /
                                                                                   |
               wl_list_notification_settings / user_notification_settings          |
               + live role & recipient check + active bot_destinations             |
                                       |                                           v
                              claim + refresh <------------------------- NoticeWorker (fenced)
                                       |
                        notice_rate_slots (BEGIN IMMEDIATE)
                                       |
                                       v
                            NoticeSender (Telegram Bot API)
```

### Key Components

| Component | Module | Responsibility |
| --------- | ------ | -------------- |
| `EventProducer` / `SharedEvent` | `wishenka/notices/events.py` | Enqueues content-free shared wishlist and opt-in reservation confirmation intents inside the domain transaction |
| `NotificationPreferencesStore` | `wishenka/notices/preferences.py` | Manages global (`user_notification_settings`) and per-wishlist (`wl_list_notification_settings`) notification preferences, access checks, and effective preference resolution |
| `TransactionalStore` | `wishenka/notices/models.py` | `Protocol` defining an atomic `BEGIN IMMEDIATE` `transaction(work)` boundary satisfied by `WishlistStore` and `NoticeStore` |
| `NoticeStore` / `ClaimedNotice` | `wishenka/notices/store.py` | Public `transaction(work)` boundary, fenced claiming, pre-send eligibility refresh, reminder lifecycle (`claim_reminder`, `refresh_reminder`, `settle_reminder`), settlement, and unified retention purge for `notification_outbox` and `reminder_outbox` |
| `upsert_bot_destination` / `deactivate_bot_destination` | `wishenka/notices/destinations.py` | Shared `bot_destinations` lifecycle helpers that maintain `active` and `updated_at` across bot and notice call sites |
| `claim_reminder` / `refresh_reminder` / `settle_reminder` | `wishenka/notices/reminders.py` | `TransactionalStore`-backed fenced claiming, live authorization/preference refresh, localized rendering, and settlement for `reminder_outbox` |
| `ReminderScheduler` / `utc_event_date` | `wishenka/notices/scheduler.py` | Bounded, cursor-driven UTC scanner for dated wishlists and private birthday entries using `TransactionalStore` |
| `reserve_permit` / `block_until` | `wishenka/notices/rate.py` | Cross-process SQLite rate limiter and `RetryAfter` throttle state in `notice_rate_slots` |
| `NoticeWorker` | `wishenka/notices/worker.py` | Lifespan background loop driving the hourly scheduler, draining both queues, and emitting windowed summaries |
| `NoticeSender` / `classify_error` | `wishenka/notices/sender.py` | Aiogram-backed Telegram sender mapping outcomes to `DELIVERED`, `REJECTED`, `RETRYABLE`, or `AMBIGUOUS` |
| `create_birthday_router` | `wishenka/bot/birthdays.py` | Private-chat `/birthdays` and `/cancel` commands, inline callbacks, and durable `birthday_input` state |
| `create_router` | `wishenka/bot/entry.py` | Private `/start` destination registration, `/reservation_confirmations on\|off`, and menu entry |
| Operator CLI | `wishenka/notices/operator.py` | Content-free inspection (`counts`, `list`) and manual resolution (`retry`, `fail`) of `uncertain` rows |

### Database Schema and Migrations

Five Alembic revisions extend the wishlist database schema for notifications, reminders, and retention (see [`doc/dev/migrations.md`](migrations.md)):

1. **`add_birthday_reminders`** (down revision `add_bot_capture_order`):
   - `bot_destinations(user_id PRIMARY KEY, chat_id, active DEFAULT 1)`: records verified private
     Telegram chats where the user has directly interacted with the bot.
   - `birthday_entries(id PRIMARY KEY AUTOINCREMENT, owner_id, label, month, day, revision DEFAULT 1, deleted DEFAULT 0)`:
     owner-scoped private birthday entries.
   - `birthday_input(owner_id, chat_id, entry_id, revision, stage, label, expires_at, PRIMARY KEY (owner_id, chat_id))`:
     durable multi-step bot input state with a 1-hour TTL.
   - `reminder_outbox(id PRIMARY KEY AUTOINCREMENT, occurrence_key UNIQUE, kind, user_id, list_id, item_id, birthday_id, revision, event_date, status DEFAULT 'pending', claimed_at, claim_token, attempts DEFAULT 0, next_attempt_at)`
     with index `idx_reminders_due(status, next_attempt_at)`.
   - `notice_rate_slots(bucket PRIMARY KEY, second, count)` with index `idx_notice_rate_second(second)`.
   - `notice_scheduler_cursors(source PRIMARY KEY, last_id)`.
2. **`add_notice_uncertain`** (down revision `add_birthday_reminders`):
   - Adds `requires_membership INTEGER NOT NULL DEFAULT 0` to `reminder_outbox`.
   - Rebuilds `notification_outbox` to allow `status = 'uncertain'`, adds `claim_token TEXT` and
     `requires_membership INTEGER NOT NULL DEFAULT 0`, enforces
     `CHECK(ambiguous=0 OR status NOT IN ('pending','sending'))`, converts any legacy
     `pending`/`sending` rows with `ambiguous = 1` to `uncertain`, and sets
     `requires_membership = 1` on migrated legacy rows so former membership is rechecked at send.
   - Creates `notice_receipt_keys(event_type, receipt_id, giver_user_id, PRIMARY KEY(event_type, receipt_id, giver_user_id))`
     and populates it from existing `notification_outbox` rows so terminal-row purging in
     `notification_outbox` never allows a duplicate receipt notice for the same `(event_type,
     receipt_id, giver_user_id)`.
3. **`add_notice_retention_columns`** (down revision `add_deleted_session_revocations`):
   - Adds `deleted_at INTEGER` and index `idx_birthday_entries_deleted_at(deleted, deleted_at)` to
     `birthday_entries`; anonymizes legacy `deleted = 1` rows (`label = ''`, `month = 0`,
     `day = 0`, `deleted_at = COALESCE(deleted_at, now)`).
   - Adds `updated_at INTEGER` and index `idx_bot_destinations_active_updated(active, updated_at)` to
     `bot_destinations`; backfills `updated_at = now` where `NULL`.
   - Adds `created_at INTEGER NOT NULL DEFAULT 0` and index
     `idx_notice_receipt_keys_created(created_at)` to `notice_receipt_keys`; backfills `created_at`
     from matching `notification_outbox.created_at` rows (or `now` if the outbox row was already
     purged).
4. **`add_reminder_outbox_updated_at`** (down revision `add_bot_capture_order_retention`):
   - Adds `updated_at INTEGER` and index
     `idx_reminder_outbox_status_updated(status, updated_at)` to `reminder_outbox`, and backfills
     existing rows with `COALESCE(claimed_at, next_attempt_at)` where `updated_at IS NULL`.
   - All `reminder_outbox` writers (`wishenka/notices/scheduler.py`, `wishenka/notices/events.py`,
     `wishenka/notices/reminders.py`, `wishenka/notices/store.py`, `wishenka/notices/worker.py`,
     and `wishenka/notices/operator.py`) stamp `updated_at` on inserts and state transitions so
     retention age is measured from the last update/settlement timestamp.
5. **`add_receipt_delivery_fence`** (down revision `add_reminder_outbox_updated_at`):
   - Creates `receipt_delivery_fence(wish_item_id, user_id, attempt_id, queue, row_id, state CHECK(state IN ('in_flight','uncertain')), PRIMARY KEY(wish_item_id, user_id))`
     to coordinate external receipt delivery attempts across processes and block concurrent promise completion.
   - Creates `receipt_delivery_fence_audit(id PRIMARY KEY, wish_item_id, user_id, attempt_id, operator, evidence, resolved_at DEFAULT CURRENT_TIMESTAMP)`
     to record audited manual resolutions of unresolved fences.
6. **`unify_user_keys_and_cascades`** (down revision `add_receipt_delivery_fence`, `WISHENKA-188`):
   - Migrates `bot_destinations.user_id`, `birthday_entries.owner_id`, and `birthday_input.owner_id` from `users.id` to `users(telegram_id)` with `ON DELETE CASCADE`.
   - Rebuilds `reminder_outbox` with `ON DELETE CASCADE` foreign keys on `user_id` (`users(telegram_id)`), `list_id` (`wl_lists(id)`), `item_id` (`wl_items(id)`), and `birthday_id` (`birthday_entries(id)`), cleaning any orphaned rows during rebuild.

### Surprise Protection and Live Eligibility Rules

1. **Candidate selection at mutation time (`WishlistService` and `EventProducer`):**
   - Shared wishlist events (`_record_shared_event`) snapshot candidate recipients in the domain
     transaction: the wishlist owner, current members (`wl_members`), and holders of `ACTIVE` or
     `PURCHASED` reservations on the affected wish (or on any wish in the list for `list_archived`,
     `list_restored`, and `list_updated`), excluding any user who is the recipient of that wish
     (`WishlistAccessPolicy.is_recipient_id`). The acting user (`actor_id`) is always excluded.
   - `PATCH /api/wishlists/{wishlist_id}` (`update_wishlist`),
     `PATCH /api/wishlists/{wishlist_id}/members/{user_id}/role` (`set_role`), and
     `WishlistService.transfer_ownership` emit `list_updated` and `membership_changed` events when
     their respective state changes.
   - `member_recipients` records which candidates were members at event time; `EventProducer.record`
     stores `requires_membership = 1` for those rows so a member who is removed before delivery
     does not receive details of a private list change.
   - Only users with an active verified row in `bot_destinations` (`active = 1`) are queued by
     `EventProducer.record`.
   - **Own-reservation confirmations (`reservation_confirmation`):** Reservation changes affect
     only the actor's own reservation. Notifying other givers when a reservation changes would leak
     another giver's activity via message timing, so legacy `reservation_changed` rows are hard-blocked
     in `_event_authorized`. Instead, `_record_reservation_confirmation` queues an intent solely
     for `actor_id` when creating a reservation, marking it `PURCHASED`, reverting it to `ACTIVE`,
     cancelling it, or changing its quantity — provided `actor_id` is not the wish recipient
     (`WishlistAccessPolicy.is_recipient_id`) and has explicitly opted in (`reservation_changes = 1`).
2. **Recipient exclusion under overlapping roles:**
   - A user who is the recipient of a wish (`item.recipient_user_id == user_id`, or
     `wishlist.owner_id == user_id` on a non-collaborative list) is **never** sent a
     `gift_received` notice, a `reservation_confirmation`, or any shared event whose eligibility
     derives solely from holding a reservation on that wish, even if they also hold a collaborator
     or giver role.
   - Reservation-derived eligibility enforces strict recipient exclusion (`recipient_user_id <> user`
     and non-collaborative `owner_id <> user`) both when enqueueing in
     `WishlistService._record_shared_event` and during live pre-send verification in
     `claim_reminder` and `refresh_reminder`.
   - On a collaborative wishlist (`is_collaborative = 1`), the list owner can act as a giver for a
     wish assigned to another recipient (`recipient_user_id != owner_id`).
   - Independently safe wishlist changes (`item_created`, `item_updated`, `item_archived`,
     `item_restored`, `list_updated`, `list_archived`, `list_restored`, `membership_changed`) and
     neutral occasion reminders remain eligible for the recipient when they have access as owner or
     member, because neither their trigger nor their text depends on reservation or receipt state.
3. **Notification categories and preference precedence:**
   - Every notice checks `wl_list_notification_settings(user_id, wishlist_id, event_type)` first
     (when `list_id` is present), falling back to `user_notification_settings(user_id, event_type)`,
     and then to the category default:

     | Category (`event_type`) | Covers `kind` / queue | Default when unset |
     | ----------------------- | --------------------- | ------------------ |
     | `gift_received` | `notification_outbox` (`gift_received`), `reminder_outbox` (`receipt_reverted`, `receipt_increased`) | Enabled (`1`) |
     | `wishlist_changes` | `item_*`, `list_*`, `membership_changed` | Enabled (`1`) |
     | `reminders` | `list`, `birthday` | Enabled (`1`) |
     | `reservation_changes` | `reservation_confirmation` (`reservation_changed` always suppressed) | Disabled (`0`) |

   - Users toggle their global `reservation_changes` setting in a private bot chat with
     `/reservation_confirmations on` and `/reservation_confirmations off`.
4. **Two-phase live verification (`claim` + `refresh` before send):**
   - Both `NoticeStore.claim_next` / `NoticeStore.refresh_claim` and
     `claim_reminder` / `refresh_reminder` verify live database state inside `BEGIN IMMEDIATE`
     transactions before claiming and again immediately before calling `NoticeSender.send`:
     - The user must have an active `bot_destinations` row (`active = 1`).
     - If `requires_membership = 1`, the user must still be in `wl_members` for `list_id`.
     - For `gift_received`, `receipt_reverted`, and `receipt_increased`, the list must not be
       `deleted`, the wish must have `received_quantity > 0` (for `gift_received` and
       `receipt_increased`, so pending notices for a partial receipt survive subsequent archival of
       the remaining unreceived units; `receipt_reverted` stays eligible even when
       `received_quantity` drops to `0`), the user must not be the wish recipient, the
       `gift_received` setting must be enabled, and the user must still hold an `ACTIVE` or
       `PURCHASED` reservation on the wish.
     - For `item_quantity_overbooked`, the list must be active or archived, the giver must still
       hold an active or purchased promise, must not be the recipient, and received plus occupied
       units must still exceed requested quantity. The notice uses `wishlist_changes` preferences.
     - For `reservation_confirmation`, the list must be `active`, the user must still hold a
       reservation on the item, must not be the recipient, and `reservation_changes` must be
       explicitly `1`.
     - For shared wishlist changes, the list must be `active` or `archived`, the item (if set) must
       exist, and the user must currently be the owner, a member, or hold an active/purchased
       reservation on the item (or on any item in the list for `list_archived`, `list_restored`, and
       `list_updated`) where the user is not the wish recipient (`recipient_user_id <> user` and
       non-collaborative `owner_id <> user`).
     - For `list` occasion reminders, the list must be `active`, the user must be the owner, a
       member, or have favorited the list (`wl_favorites`), `utc_event_date(wl.event_date)` must
       still match the queued `event_date`, and `event_date` must not be in the past (`event_date >=
       today_utc`).
     - For `birthday` reminders, the `birthday_entries` row must match `birthday_id`, `revision`,
       `owner_id`, and `deleted = 0`, and `event_date` must not be in the past.
   - Any row failing eligibility at claim or refresh is transitioned to `status = 'skipped'`.
   - When Telegram rejects a send with `TelegramForbiddenError` or `TelegramNotFound`, settlement
     marks the row `failed` and sets `bot_destinations.active = 0` for that `chat_id` so subsequent
     events are skipped until the user interacts with the bot again.
5. **Localization and safe plain-text rendering:**
   - Language is resolved at send time from `users.language_code`: codes starting with `en`
     (case-insensitive) render English; all other values render Russian.
   - Titles and labels are truncated to `100` characters (`TITLE_LIMIT = 100`). Messages are plain
     text and never include capability tokens, URLs, reservation quantities, or other givers'
     identities.

### Notification Preferences & `birthday_reminders` Priority (`WISHENKA-34`)

`NotificationPreferencesStore` (`wishenka/notices/preferences.py`) exposes global and per-wishlist notification controls backed directly by `user_notification_settings` and `wl_list_notification_settings` (keyed by `users.telegram_id`, with no intermediate cache):

- **Global categories** (`GLOBAL_NOTIFICATION_DEFAULTS`): `wishlist_changes` (`True`), `reservation_changes` (`False`, explicit opt-in), `gift_received` (`True`), `reminders` (`True`), `birthday_reminders` (`True`).
- **Per-wishlist categories** (`WISHLIST_NOTIFICATION_CATEGORIES`): `wishlist_changes`, `reservation_changes`, `gift_received`, `reminders`. A list-level row may be `True`, `False`, or deleted (`None` in the API) to inherit the global setting.
- **Effective resolution order**: `override` (`wl_list_notification_settings`) -> `global` (`user_notification_settings`) -> `default` (`GLOBAL_NOTIFICATION_DEFAULTS`).
- **Access check**: Only non-deleted wishlists (`status IN ('active', 'archived')`) where the user is `owner_id`, a member in `wl_members`, or has the list in `wl_favorites` are exposed or configurable.
- **`birthday_reminders` precedence in `wishenka/notices/reminders.py`**: When `claim_reminder` or `refresh_reminder` evaluates a `kind == "birthday"` row, `_read_user_setting` resolves `COALESCE(birthday_reminders, reminders)` (falling back to `1` if neither row exists). Disabling `birthday_reminders` suppresses already-queued `reminder_outbox` birthday rows (`status = 'skipped'`) without deleting `birthday_entries`.
- **Mini App endpoints (`wishenka/web/routes/profile.py`)**: `GET /api/profile/preferences`, `PUT /api/profile/notifications/global`, `GET /api/profile/notifications/wishlists/{wishlist_id}`, and `PUT /api/profile/notifications/wishlists/{wishlist_id}` (plus `GET /settings` UI).
- **Settings UI (`WISHENKA-291`)**: the screen shows inherited vs override badges derived from
  this resolution order and reconciles ambiguous failures by re-reading the preferences; no
  backend rule changed. See
  [miniapp.md](miniapp.md#personal-settings-screen-wishenka-291).

### Private `/birthdays` Tracking Flow

Implemented in `wishenka/bot/birthdays.py` (`create_birthday_router`), mounted by
`wishenka.bot.entry.create_router` when `wishlist_store` is provided:

- **Entry points:** `/birthdays` command in a private chat (`chat.type == "private"` and
  `chat.id == from_user.id`) or the `Birthdays` / `Дни рождения` inline button (`birthday:open`) on
  the `/start` menu.
- **Destination registration and log privacy:** Every verified private interaction upserts the user
  in `UserStore` under `_PrivateUserLogFilter` (which suppresses `wishenka.users` log records during
  the upsert so profile fields are not logged) and sets `bot_destinations.active = 1`.
- **Listing and limits:** Lists up to 20 active (`deleted = 0`) entries owned by the authenticated
  internal `user.id`, formatted as `<label>: MM-DD`, with per-entry `Edit` (`birthday:e:<id>:<rev>`)
  and `Delete` (`birthday:d:<id>:<rev>`) buttons and an `Add` (`birthday:add`) button.
- **Two-stage durable input (`birthday_input`):**
  - Clicking `Add` or `Edit` writes a row in `birthday_input` (`stage = 'label'`,
    `expires_at = now + 3600`) scoped to `(owner_id, chat_id)`.
  - Stage 1 (`label`): accepts non-command text of 1 to 80 characters after stripping whitespace and
    advances to `stage = 'date'`.
  - Stage 2 (`date`): validates `MM-DD` using `calendar.monthrange(2000, month)` so February 29
    (`02-29`) is accepted without requiring a birth year. Invalid dates return an error prompt while
    keeping the pending label intact so the user can retry.
  - Creating a new entry enforces a cap of 20 active entries per owner. Editing checks `(id,
    owner_id, revision, deleted = 0)` and increments `revision` when `label`, `month`, or `day`
    changed, then deletes the `birthday_input` row.
  - Deleting an entry immediately anonymizes PII in `birthday_entries` by setting
    `deleted = 1, revision = revision + 1, label = '', month = 0, day = 0, deleted_at = :now`,
    and removes any pending `birthday_input` for that entry.
  - `/cancel` deletes the caller's `birthday_input` row without modifying committed
    `birthday_entries`. Expired `birthday_input` rows (up to 100 per pass) are also purged by
    `cleanup_drafts` in `wishenka/bot/capture.py`.

### UTC Occasion Scheduling

`ReminderScheduler` (`wishenka/notices/scheduler.py`) is invoked by `NoticeWorker.run`:

- **UTC date interpretation (`utc_event_date`):** Parses ISO date/datetime strings; naive values are
  assumed UTC and timezone-aware values are converted to UTC before taking `.date()`.
- **Bounded paged scans:** Each `run_once(now)` call scans up to `PAGE_SIZE = 1000` active dated
  wishlists and up to `1000` active birthday entries in a single transaction, recording the last
  seen ID in `notice_scheduler_cursors` (`source = 'lists'` and `source = 'birthdays'`) and
  wrapping around to `0` when a page has fewer than `1000` rows. When a full page is read,
  `run_once` returns `True` and `NoticeWorker` schedules the next page immediately; otherwise the
  scheduler waits `3600` seconds (1 hour).
- **Lead window and deduplication:**
  - Configured lead days (`Settings.notice_reminder_lead_days`, default `(7,)`) are sorted and
    deduplicated. An occasion on UTC date `event` with `remaining = (event - today).days` matches
    every configured `lead` where `0 <= remaining <= lead`. This catches up missed windows after a
    service restart up to the event date itself, while never scheduling overdue occasions
    (`remaining < 0`).
  - **Wishlist reminders:** Candidate recipients are the union of `owner_id`, `wl_members`, and
    `wl_favorites` for the active list. Inserted into `reminder_outbox` with `INSERT OR IGNORE` and
    unique `occurrence_key = "list:{wishlist_id}:{event_iso}:{lead}:{user_id}"`.
  - **Birthday reminders:** Evaluates `today.year` and `today.year + 1`. If `month == 2` and
    `day == 29` in a non-leap year (`not calendar.isleap(year)`), the occurrence date is mapped to
    February 28 (`YYYY-02-28`). Inserted into `reminder_outbox` for the entry's owner with
    `occurrence_key = "birthday:{birthday_id}:{revision}:{year}:{lead}:{owner_id}"`. Editing or
    deleting a birthday increments `revision`, invalidating any unsent reminder from the previous
    revision at claim/refresh time and allowing a new occurrence key for the updated date.

### Shared Rate Limiter

`wishenka/notices/rate.py` coordinates send permits across all worker processes via
`notice_rate_slots`:

- `reserve_permit(conn, chat, now, global_limit, chat_interval)` runs inside the claim
  `BEGIN IMMEDIATE` transaction:
  - Purges stale per-chat rows older than `now - max(chat_interval, 3600)`.
  - Checks the `blocked` bucket: if `second > now`, a provider-wide `RetryAfter` cooldown is active
    and no row is claimed.
  - Checks the `global` bucket: rejects if `second == now` and `count >= global_limit` (default 20
    sends/second) or if `second > now`.
  - Checks `chat:{chat_id}`: rejects if `second + chat_interval > now` (default 1 second between
    messages to the same chat).
  - When permitted, increments `global` and updates `chat:{chat_id}`. When rejected, the caller
    pushes the row's `next_attempt_at` to `now + 1` without incrementing `attempts` and commits
    immediately — never sleeping inside a database transaction.
- `block_until(conn, deadline)` is called during settlement whenever Telegram returns
  `retry_after`, setting `blocked.second = MAX(second, deadline)` so all workers pause claiming
  until the cooldown expires.

### Fenced Claims, Retries, and Uncertain-Delivery Quarantine

- **Claim tokens:** Claiming a row in either `notification_outbox` or `reminder_outbox` sets
  `status = 'sending'`, `claimed_at = now`, `attempts = attempts + 1`, and generates a fresh
  `claim_token = secrets.token_urlsafe(18)`. Every refresh and settlement query requires
  `WHERE id = :id AND status = 'sending' AND claim_token = :token`.
- **Outcomes:**
  - `DELIVERED`: settled as `status = 'sent'`.
  - `REJECTED` (`TelegramForbiddenError`, `TelegramBadRequest`, `TelegramNotFound`,
    `TelegramEntityTooLarge`, `TelegramMigrateToChat`) or `attempt >= receipt_notice_max_attempts`:
    settled as `status = 'failed'`.
  - `RETRYABLE` (`TelegramRetryAfter`, `TelegramUnauthorizedError`) below max attempts: returned to
    `status = 'pending'` with `next_attempt_at = now + max(backoff_seconds(attempt), ceil(retry_after))`,
    where `backoff_seconds(n) = min(base * 2**(n - 1), max)`.
  - `AMBIGUOUS` (HTTP/network timeout, connection drop, 5xx, or unexpected exception) or a stale
    `sending` row whose `claimed_at <= now - receipt_notice_claim_lease_seconds`: settled as
    `status = 'uncertain'` (with `ambiguous = 1` and `last_error_class = 'StaleClaim'` for expired
    receipt claims). **Uncertain rows are quarantined and never automatically retried**, preventing
    blind duplicate sends when Telegram may have accepted the message before the connection failed.
- **Per-giver receipt delivery lock & durable fence (`wishenka.notices.fence`, `WISHENKA-219`):**
  Both `notification_outbox` (`gift_received`) and `reminder_outbox` (`receipt_increased`,
  `receipt_reverted`) share the coordination key `(wish_item_id, user_id)`:
  1. `delivery_lock(database_url, item_id, user_id)` acquires a nonblocking per-key `asyncio.Lock`
     within the process and a nonblocking exclusive `fcntl.flock` on
     `<db>.receipt-locks/<sha256(item_id:user_id)>` across processes on the same host (mode `0700`
     directory, `0600` lock files, never unlinked while running).
  2. Before sending a claimed receipt notice, `NoticeWorker.run_once` enters `delivery_lock`, calls
     `begin_attempt(store, key, queue, row_id, token)` (which re-verifies the `sending` claim token,
     checks for an `active`/`purchased` promise in `wl_reservations`, and inserts an `in_flight`
     row into `receipt_delivery_fence`), holds the lock across network I/O, and calls
     `finish_attempt(store, key, token, definitive=...)` to delete the fence on definitive outcomes
     or mark it `uncertain` on ambiguous outcomes.
  3. If the lock is busy or `begin_attempt` fails because a fence is already active, `defer_claim`
     returns the unsent row to `pending` (`attempts = MAX(0, attempts - 1)`) without consuming a
     retry attempt.
  4. `complete_reservation` acquires the same `delivery_lock` and checks `has_fence` before its wish
     transaction; if busy or fenced, it fails closed with HTTP 503. When completion commits in
     `WishlistStore._persist_wish` and no other `active` or `purchased` promise exists for
     `(wish_item_id, user_id)`, pending/sending `notification_outbox` rows (`skip_reason = 'target_gone'`)
     and `reminder_outbox` rows (`kind IN ('receipt_increased', 'receipt_reverted')`) are atomically
     marked `skipped` in the same transaction.

### Retention Cleanup

`run_cleanup_cycle` (`wishenka/wishlists/cleanup.py`) invokes two `NoticeStore` cleanup methods:

1. **`NoticeStore.purge_finished(threshold, *, now=None, reminder_threshold=None, batch_size=DEFAULT_PURGE_BATCH_SIZE)`**
   purges terminal (`sent`, `skipped`, `failed`) rows from both outbox queues in bounded
   per-transaction batches (`DEFAULT_PURGE_BATCH_SIZE = 500`, `batch_size >= 1`, raising
   `ValueError` otherwise). Each `_purge_batch` call runs inside a single `BEGIN IMMEDIATE`
   transaction deleting at most `batch_size` rows per queue (`ORDER BY id LIMIT :batch_size`) and
   loops until both queues return fewer than `batch_size` rows:
   - **`notification_outbox`:** deletes terminal rows with `updated_at <= threshold`
     (`now - receipt_notice_retention_days * 86400`), while preserving `notice_receipt_keys` so
     purged receipts cannot be re-enqueued as duplicates.
   - **`reminder_outbox`:** deletes terminal rows with
     `COALESCE(updated_at, next_attempt_at) <= reminder_cutoff`
     (`now - reminder_retention_days * 86400`) that satisfy the **active-cycle guard**:
     `kind NOT IN ('list', 'birthday') OR event_date < today_utc`. Keeping terminal `list` and
     `birthday` reminders until `event_date < today_utc` preserves `occurrence_key` deduplication
     (`INSERT OR IGNORE`) for the current/upcoming occasion cycle. All `reminder_outbox` writers
     (`scheduler.py`, `events.py`, `reminders.py`, `store.py`, `worker.py`, `operator.py`) stamp
     `updated_at` on inserts and state transitions (`COALESCE` preserves compatibility with legacy
     rows where `updated_at` is `NULL`).
   - **Preserved rows:** `pending`, `sending`, and `uncertain` rows in both tables are never purged.

2. **`NoticeStore.purge_retention_records(*, birthday_threshold, destination_threshold, receipt_key_threshold)`**
   physically deletes expired retention records inside a single `BEGIN IMMEDIATE` transaction:
   - **`birthday_entries`:** deletes `deleted = 1` rows with
     `deleted_at IS NULL OR deleted_at <= birthday_cutoff` (`now - birthday_retention_days * 86400`)
     subject to the **`uncertain` / active reminder guard**: rows referenced by a `reminder_outbox`
     row in `status IN ('pending', 'sending', 'uncertain')` are preserved until those reminders
     settle or are resolved by an operator.
   - **`bot_destinations`:** deletes `active = 0` rows with
     `updated_at IS NULL OR updated_at <= destination_cutoff`
     (`now - bot_destination_retention_days * 86400`). Call sites maintain `updated_at` via
     `upsert_bot_destination` and `deactivate_bot_destination` (`wishenka/notices/destinations.py`).
   - **`notice_receipt_keys`:** deletes rows with `created_at <= receipt_key_cutoff`
     (`now - receipt_dedup_retention_days * 86400`) that have no matching row in
     `notification_outbox` (preserving dedup protection while any outbox row still exists).

## API / Usage

### Recording Shared Domain Events (`wishenka.notices.events`)

Domain mutations in `WishlistService` append `SharedEvent` instances to
`self._new_shared_item_events`, which `WishlistStore._flush_receipt_effects` persists in the same
database transaction via `EventProducer.record`:

```python
from wishenka.notices.events import EventProducer, SharedEvent

producer = EventProducer()
event = SharedEvent(
    kind="item_created",
    wishlist_id=wishlist.id,
    item_id=item.id,
    event_id=secrets.token_hex(16),
    recipients=(collaborator_telegram_id,),
    member_recipients=frozenset({collaborator_telegram_id}),
)
await producer.record(conn, event, now=int(time.time()))
```

- A quantity reduction that leaves the wish over-booked queues `item_quantity_overbooked` for
  distinct eligible open-promise givers, including the editor when eligible. Those givers do not
  also receive the generic `item_updated` notice for that edit. The item change and outbox rows
  commit together; later delivery failures do not roll back the edit. The localized notice omits
  other givers and booking quantities. No new configuration is required; existing
  `wishlist_changes` preferences apply.

- **`SAFE_SHARED_EVENTS`**: `"item_created"`, `"item_updated"`, `"item_quantity_overbooked"`,
  `"item_archived"`,
  `"item_restored"`, `"list_updated"`, `"list_archived"`, `"list_restored"`,
  `"membership_changed"`, `"reservation_confirmation"`, `"receipt_reverted"`,
  `"receipt_increased"`. Passing any other `kind` raises
  `ValueError("Unsupported shared notification event")`.

### Notice Store Transaction Boundary and Reminder Operations (`wishenka.notices.models`, `wishenka.notices.store`)

`TransactionalStore` (`wishenka/notices/models.py`) defines the shared `BEGIN IMMEDIATE`
transaction protocol (`async def transaction(self, work: Callable[[AsyncConnection], Awaitable[T]]) -> T`)
implemented by both `WishlistStore` and `NoticeStore`.

`NoticeStore` (`wishenka/notices/store.py`) exposes public transaction and reminder methods so
`NoticeWorker` and `wishenka/notices/` modules never reach into `NoticeStore._store`:

- **`NoticeStore.transaction(work)`**: Runs `work(conn)` inside a single `BEGIN IMMEDIATE`
  transaction via the underlying `WishlistStore`.
- **`NoticeStore.claim_reminder(now)`**: Claims a due `reminder_outbox` row using the store's
  configured lease, `global_limit`, and `chat_interval` settings.
- **`NoticeStore.refresh_reminder(claim, now)`**: Rechecks live consent and eligibility and
  refreshes authorized reminder text before delivery.
- **`NoticeStore.settle_reminder(claim, status, next_attempt, error_class=None, throttle_until=None)`**:
  Settles a fenced reminder claim inside one `BEGIN IMMEDIATE` transaction.

### Running the Reminder Scheduler (`wishenka.notices.scheduler`)

```python
from wishenka.notices.scheduler import ReminderScheduler, utc_event_date

event_day = utc_event_date("2026-12-25T00:00:00Z")
scheduler = ReminderScheduler(store, settings)  # store: TransactionalStore (NoticeStore or WishlistStore)
more_pages = await scheduler.run_once(now=int(time.time()))
```

- **`ReminderScheduler(store, settings)`**: Accepts any `TransactionalStore` (e.g., `NoticeStore`
  when instantiated by `NoticeWorker`, or `WishlistStore` directly).
- **`run_once(now)`**: Scans up to 1000 active dated wishlists and 1000 active birthday entries in
  UTC. Returns `True` if either scan hit `PAGE_SIZE` (indicating more pages remain), or `False`
  when the full cycle completed and cursors reset to `0`.

### Operator CLI and Functions (`wishenka.notices.operator`)

Use the operator module to inspect queue health and manually resolve quarantined `uncertain` rows
without exposing user IDs, chat IDs, or message contents:

```bash
# 1. Inspect aggregate row counts by status for both 'receipt' and 'reminder' queues
python -m wishenka.notices.operator counts

# 2. List up to 100 uncertain row IDs and attempt counts in a specific queue
python -m wishenka.notices.operator list --queue receipt
python -m wishenka.notices.operator list --queue reminder

# 3. Explicitly mark an uncertain row as terminal failed (no resend)
python -m wishenka.notices.operator fail --queue reminder --id 42

# 4. Explicitly re-queue an uncertain row as pending (WARNING: may send a duplicate)
python -m wishenka.notices.operator retry --queue receipt --id 17

# 5. Resolve a row that has an active receipt_delivery_fence (operator and evidence required)
python -m wishenka.notices.operator fail --queue receipt --id 17 \
  --operator oncall-name --evidence "Confirmed process exited and Telegram delivered message"
```

Programmatic functions in `wishenka.notices.operator`:

- `await counts(store) -> dict[str, dict[str, int]]`: returns `{"receipt": {<status>: <count>},
  "reminder": {<status>: <count>}}`.
- `await list_uncertain(store, queue, limit=100) -> list[dict[str, int]]`: returns
  `[{"id": <int>, "attempts": <int>}, ...]` for `queue in ("receipt", "reminder")` and
  `1 <= limit <= 100`.
- `await resolve(store, queue, ident, action, now, *, operator="", evidence="") -> bool`:
  transitions row `ident` from `uncertain` to `pending` (`action="retry"`, clearing `ambiguous=0`
  on `receipt`) or `failed` (`action="fail"`). When a `receipt_delivery_fence` row exists for
  `(queue, ident)`, non-empty `operator` and `evidence` are required (`ValueError` otherwise);
  `resolve` acquires `delivery_lock`, records the resolution in `receipt_delivery_fence_audit`, and
  deletes the fence in the same transaction. Returns `True` if a row was updated, `False` if not
  found or not `uncertain`.
- `await resolve_attempt(store, item_id, user_id, *, operator, evidence) -> bool`
  (`wishenka.notices.fence`): directly resolves a reconciled `receipt_delivery_fence` entry under
  `delivery_lock`, writing `receipt_delivery_fence_audit` and removing the fence.

## Configuration

All settings are defined on `wishenka.config.Settings` (`WISHENKA_` environment prefix):

| Setting | Environment Variable | Default | Validation / Meaning |
| ------- | -------------------- | ------- | -------------------- |
| `bot_token` | `WISHENKA_BOT_TOKEN` | `"dummy_bot_token"` | Must be a valid Telegram token; placeholder disables the notice worker |
| `receipt_notice_worker_enabled` | `WISHENKA_RECEIPT_NOTICE_WORKER_ENABLED` | `True` | Enables the background worker (drains both `notification_outbox` and `reminder_outbox` and runs `ReminderScheduler`) |
| `receipt_notice_poll_interval_seconds` | `WISHENKA_RECEIPT_NOTICE_POLL_INTERVAL_SECONDS` | `5.0` | `> 0` and `<= summary_window_seconds`; worker poll interval |
| `receipt_notice_max_attempts` | `WISHENKA_RECEIPT_NOTICE_MAX_ATTEMPTS` | `5` | `1..20`; max delivery attempts per row before terminal `failed` |
| `receipt_notice_backoff_base_seconds` | `WISHENKA_RECEIPT_NOTICE_BACKOFF_BASE_SECONDS` | `30` | `>= 1`; initial exponential retry delay in seconds |
| `receipt_notice_backoff_max_seconds` | `WISHENKA_RECEIPT_NOTICE_BACKOFF_MAX_SECONDS` | `3600` | `>= backoff_base_seconds`; maximum retry backoff delay (1 hour) |
| `receipt_notice_request_timeout_seconds` | `WISHENKA_RECEIPT_NOTICE_REQUEST_TIMEOUT_SECONDS` | `30.0` | `> 0`; HTTP request timeout (worker awaits `timeout + 5` seconds) |
| `receipt_notice_claim_lease_seconds` | `WISHENKA_RECEIPT_NOTICE_CLAIM_LEASE_SECONDS` | `300` | `>= request_timeout_seconds + 30`; age after which a `sending` row becomes `uncertain` |
| `receipt_notice_summary_window_seconds` | `WISHENKA_RECEIPT_NOTICE_SUMMARY_WINDOW_SECONDS` | `300` | `>= 60`; fixed wall-clock aggregation window for INFO summary logs |
| `receipt_notice_retention_days` | `WISHENKA_RECEIPT_NOTICE_RETENTION_DAYS` | `30` | `>= 1`; retention period before `purge_finished` deletes terminal rows in `notification_outbox` |
| `birthday_retention_days` | `WISHENKA_BIRTHDAY_RETENTION_DAYS` | `30` | `>= 1`; retention period before `purge_retention_records` deletes anonymized `deleted = 1` rows in `birthday_entries` |
| `bot_destination_retention_days` | `WISHENKA_BOT_DESTINATION_RETENTION_DAYS` | `30` | `>= 1`; retention period before `purge_retention_records` deletes inactive (`active = 0`) rows in `bot_destinations` |
| `reminder_retention_days` | `WISHENKA_REMINDER_RETENTION_DAYS` | `30` | `>= 1`; retention period before `purge_finished` deletes terminal rows in `reminder_outbox` (subject to active-cycle guard) |
| `receipt_dedup_retention_days` | `WISHENKA_RECEIPT_DEDUP_RETENTION_DAYS` | `30` | `>= 1`; retention period before `purge_retention_records` deletes `notice_receipt_keys` rows without an active outbox row |
| `notice_global_per_second` | `WISHENKA_NOTICE_GLOBAL_PER_SECOND` | `20` | `1..30`; global send limit per second across all worker processes |
| `notice_chat_interval_seconds` | `WISHENKA_NOTICE_CHAT_INTERVAL_SECONDS` | `1` | `>= 1`; minimum interval in seconds between sends to the same `chat_id` |
| `notice_reminder_lead_days` | `WISHENKA_NOTICE_REMINDER_LEAD_DAYS` | `(7,)` | Non-empty tuple of positive integers (`> 0`); lead days in UTC before an occasion |

## Observability

Structured log events use `extra={"event": ...}` and never include user IDs, chat IDs, birthday
labels or dates, wish/list titles, capability links, bot tokens, or raw exception messages:

| Event | Level | Logger | Fields |
| ----- | ----- | ------ | ------ |
| `receipt_notice_worker_started`, `receipt_notice_worker_stopped` | INFO | `wishenka.wishlists.notices` | none (`receipt_notice_worker_stopped` is emitted on shutdown without summary counts; unfinished window counters are dropped) |
| `receipt_notice_worker_disabled` | INFO | `wishenka.wishlists.notices` | `reason` |
| `receipt_notice_window_summary` | INFO | `wishenka.wishlists.notices` | `window_seconds`, `sent`, `retried`, `failed_terminal`, `uncertain` |
| `service_delivery_window_summary` | INFO | `wishenka.wishlists.notices` | `window_seconds`, `sent`, `retried`, `failed_terminal`, `uncertain`, `skipped` |
| `notice_outbox_purged` | INFO | `wishenka.wishlists.notices` | `receipt_purged`, `reminder_purged`, `total_purged`, `batches`, `batch_size` (emitted only when rows are deleted) |
| `notice_retention_records_purged` | INFO | `wishenka.wishlists.notices` | `birthdays_purged`, `destinations_purged`, `receipt_keys_purged` (emitted only when rows are deleted) |
| `receipt_notice_enqueue_failed` | ERROR | `wishenka.wishlists.notices` | `error_class` (operator-only; emitted when `notification_outbox` / `notice_receipt_keys` enqueueing fails before rollback; no IDs) |
| `receipt_notice_worker_error` | ERROR | `wishenka.wishlists.notices` | `error_class` (logged once per consecutive worker failure streak) |
| `reminder_scheduler_error` | ERROR | `wishenka.wishlists.notices` | `error_class` (logged once per consecutive scheduler failure streak; does not block queue delivery) |
| `reminder_scan_completed` | DEBUG | `wishenka.notices.scheduler` | `lists_scanned`, `birthdays_scanned`, `intents_created` (emitted only on non-empty scans) |
| `shared_notice_events_queued` | DEBUG | `wishenka.wishlists.notices` | `kind`, `queued_count` (emitted after commit when `reminder_outbox` rows are inserted) |
| `service_notice_skipped` | DEBUG | `wishenka.wishlists.notices` | `outbox_id`, `reason` (`unauthorized`, `ineligible`, `refresh_ineligible`), `kind` (when claimed) |
| `notification_global_updated` | INFO | `wishenka.notices.preferences` | `updated_count`, `categories` |
| `notification_wishlist_updated` | INFO | `wishenka.notices.preferences` | `wishlist_id`, `role`, `updated_count`, `cleared_count` |
| `notification_global_invalid_request` | WARNING | `wishenka.web.profile` | `user_id`, `status_code` (`422`) |
| `notification_wishlist_not_found` | WARNING | `wishenka.web.profile` | `user_id`, `wishlist_id`, `status_code` (`404`) |
| `notification_wishlist_invalid_request` | WARNING | `wishenka.web.profile` | `user_id`, `wishlist_id`, `status_code` (`422`) |
| `receipt_notice_retry_scheduled` | DEBUG | `wishenka.wishlists.notices` | `outbox_id`, `attempt`, `max_attempts`, `error_class` (when present) |
| `receipt_notice_skipped_ineligible` | DEBUG | `wishenka.wishlists.notices` | `outbox_id`, `attempt` |
| `receipt_notice_uncertain` | DEBUG | `wishenka.wishlists.notices` | `outbox_id`, `attempt`, `error_class` (when a receipt send is ambiguous or lease expires) |
| `receipt_notices_suppressed` | INFO | `wishenka.wishlists.notices` | `item_id`, `user_id`, `gift_skipped`, `reminder_skipped` (when `complete_reservation` suppresses pending/sending receipt notices) |
| `receipt_notice_deferred` / `service_notice_deferred` | DEBUG | `wishenka.wishlists.notices` | `outbox_id`, `reason` (`fence_active` or `lock_busy`), plus `attempt` or `kind` |
| `receipt_claim_deferred` | INFO | `wishenka.notices.fence` | `queue`, `row_id` (when an unsent claim is returned to `pending` without consuming an attempt) |
| `receipt_fence_resolved` | INFO | `wishenka.notices.fence` | `item_id`, `user_id`, `operator`, `resolved_rows` (omits full `evidence` text) |
| `receipt_fence_busy` / `receipt_fence_uncertain` | WARNING | `wishenka.notices.fence` | `item_id`, `user_id` (plus `queue`, `row_id` on `receipt_fence_busy`) |
| `receipt_fence_stale_claim`, `receipt_fence_no_open_promise`, `receipt_fence_recorded`, `receipt_fence_cleared`, `receipt_fence_resolve_noop` | DEBUG | `wishenka.notices.fence` | `item_id`, `user_id` (plus `queue`/`row_id` or `operator` where applicable) |
| `operator_notice_resolved` | INFO | `wishenka.notices.operator` | `queue`, `row_id`, `action`, `has_fence`, `operator` |
| `operator_notice_resolve_noop` | WARNING | `wishenka.notices.operator` | `queue`, `row_id`, `action` |

### SQL Gauge Semantics (`notification_outbox`) and Domain Log Contracts

- **`last_error_class` current-state gauge:** `NoticeStore.complete` clears `last_error_class = NULL` when a row transitions to `status = 'sent'`. Consequently, `SELECT last_error_class, count(*) FROM notification_outbox WHERE status IN ('pending', 'uncertain', 'failed') GROUP BY last_error_class` is a **current-state gauge** of unresolved/failed rows, not a historical failure counter.
- **`ambiguous` gauge:** `ambiguous = 1` marks rows with an unconfirmed send outcome (`CHECK(ambiguous=0 OR status NOT IN ('pending','sending'))`). `operator.resolve(..., action="retry")` clears `ambiguous = 0` when re-queuing an `uncertain` row to `pending`, whereas `action="fail"` leaves `ambiguous = 1` on `failed`. Query `WHERE status = 'uncertain'` for active unresolved ambiguity awaiting operator action, and `WHERE ambiguous = 1 AND status IN ('sent', 'failed')` for historical ambiguity within the 30-day retention window.
- **Post-commit `item_fulfilled`:** `WishlistStore` sets `_defer_commit_logs = True` on hydrated `WishlistService` instances and flushes `_pending_commit_logs` only after the SQLite transaction commits, so rolled-back receipts (including `receipt_notice_enqueue_failed`) never emit `item_fulfilled`.
- **Owner-stream privacy on `item_archived`:** `item_archived` (`INFO`, `wishenka.wishlists`) emits `{"event": "item_archived", "item_id", "wishlist_id", "actor_id"}` without `active_reservations_count` so owner-stream logs never expose reservation presence.

See [`ai-tasks/WISHENKA-29/50-observability.md`](../../ai-tasks/WISHENKA-29/50-observability.md),
[`ai-tasks/WISHENKA-60/50-observability.md`](../../ai-tasks/WISHENKA-60/50-observability.md),
[`ai-tasks/WISHENKA-181/50-observability.md`](../../ai-tasks/WISHENKA-181/50-observability.md),
[`ai-tasks/WISHENKA-157/50-observability.md`](../../ai-tasks/WISHENKA-157/50-observability.md), and
[`ai-tasks/WISHENKA-219/50-observability.md`](../../ai-tasks/WISHENKA-219/50-observability.md) for
the complete observability specifications.

## Troubleshooting

- **User does not receive any notifications or reminders:**
  1. Verify that the user has interacted with the bot in a private chat (`/start`, `/birthdays`, or
     wish capture) so a row exists in `bot_destinations` with `active = 1`. Merely logging into the
     Mini App does not prove the bot can message the user.
  2. If the user previously blocked the bot, a `TelegramForbiddenError` or `TelegramNotFound`
     response sets `bot_destinations.active = 0`. Have the user send `/start` in private chat to
     reactivate their destination.
  3. Check `wl_list_notification_settings` and `user_notification_settings` for the relevant
     category (`wishlist_changes`, `gift_received`, `reminders`, or `reservation_changes`).
- **Over-booking notice is missing:** Check the `wishlist_changes` preferences and active bot
  destination. The worker rechecks that the giver's promise is open, the giver is not the
  recipient, and the wish is still over-booked; a stale or unauthorized notice is skipped.
- **Actor does not receive reservation confirmations:**
  - `reservation_changes` defaults to disabled (`0`). The user must send
    `/reservation_confirmations on` in a private chat with the bot (and must not be the recipient
    of the wish) before performing the reservation action.
- **Rows accumulate in `status = 'uncertain'`:**
  - Indicates timeouts, network drops, 5xx errors, or workers killed while a send was in flight
    (`last_error_class = 'StaleClaim'` on `notification_outbox`).
  - Run `python -m wishenka.notices.operator counts` and
    `python -m wishenka.notices.operator list --queue <receipt|reminder>` to inspect.
  - Decide whether to drop the uncertain rows (`fail --queue <q> --id <id>`) or resend them
    (`retry --queue <q> --id <id>`), noting that `retry` may deliver a duplicate message if Telegram
    accepted the earlier attempt before the connection dropped.
- **Birthday or wishlist reminder was skipped:**
  - Editing or deleting a birthday increments `birthday_entries.revision` (and sets `deleted = 1`
    on delete); changing a wishlist's `event_date` or archiving/deleting the list invalidates
    previously queued `reminder_outbox` rows, which transition to `skipped` at claim/refresh time.
  - Reminders are evaluated in UTC (`utc_event_date`); if `event_date` is already before the current
    UTC date when claimed, the row is skipped.
- **High retry rate or delayed sends during bursts:**
  - Check `notice_rate_slots` (`SELECT * FROM notice_rate_slots`). A `blocked` row with
    `second > now` means Telegram returned `429 Too Many Requests` (`TelegramRetryAfter`) and all
    workers are respecting the provider cooldown.
- **`reminder_scheduler_error` or `receipt_notice_worker_error` in logs:**
  - Both loops back off exponentially up to 60 seconds (`MAX_ERROR_BACKOFF_SECONDS`) and recover
    automatically on the next successful tick. Scheduler errors do not pause delivery of already
    queued notices. Check SQLite availability and disk space.

## Testing

Run the focused notification, reminder, upgrade, operator, concurrency, and observability test suites with:

```bash
make test PYTEST_JOBS=0 PYTEST_ARGS='tests/test_notice_delivery_repro.py tests/test_notice_wishlist_events.py tests/test_notice_upgrade.py tests/test_notice_operator.py tests/test_notice_worker_concurrency.py tests/test_telegram_notice_smoke.py tests/test_reminder_scan_paging.py tests/test_service_notice_observability.py tests/test_receipt_notices.py tests/test_receipt_observability.py tests/test_wishenka_60_repro.py tests/test_wishenka_60_observability.py tests/test_wishenka_34_repro.py tests/test_wishenka_34_preferences.py tests/test_wishenka_181_repro.py tests/test_wishenka_183_repro.py tests/test_wishenka_183_updated_at.py tests/test_notice_retention.py'
```

### Live Telegram Smoke Test & Manual Verification Checklist

Use this checklist before releases or after changes to `wishenka/notices/sender.py` or `notice_text`
to verify real Telegram Bot API delivery without affecting offline CI.

#### Prerequisites

- A dedicated test Telegram bot token (`WISHENKA_TELEGRAM_SMOKE_TOKEN`).
- An explicit test Telegram chat ID (`WISHENKA_TELEGRAM_SMOKE_CHAT_ID`) that has already started a
  private conversation (`/start`) with that test bot.
- Optionally, an invalid/unreachable chat ID (`WISHENKA_TELEGRAM_SMOKE_INVALID_CHAT_ID`, defaults to
  `0`) for the negative rejection check.
- Local test environment installed (`.venv/bin/pytest`).

#### Safety Rules

- **Explicit test chat only:** Never supply a production bot token or a real user's chat ID.
- **No secrets in Git:** Never commit `WISHENKA_TELEGRAM_SMOKE_TOKEN` or
  `WISHENKA_TELEGRAM_SMOKE_CHAT_ID` to `.env`, fixtures, or documentation.
- **Default offline runs:** When the smoke environment variables are unset, `pytest` automatically
  skips the live `@pytest.mark.telegram_smoke` tests while still running the offline guard checks in
  `tests/test_telegram_notice_smoke.py`.

#### Automated Smoke Command

```bash
WISHENKA_TELEGRAM_SMOKE_TOKEN="<test-bot-token>" \
WISHENKA_TELEGRAM_SMOKE_CHAT_ID="<test-chat-id>" \
.venv/bin/pytest -m telegram_smoke
```

To override the default negative target (`0`):

```bash
WISHENKA_TELEGRAM_SMOKE_TOKEN="<test-bot-token>" \
WISHENKA_TELEGRAM_SMOKE_CHAT_ID="<test-chat-id>" \
WISHENKA_TELEGRAM_SMOKE_INVALID_CHAT_ID="-1" \
.venv/bin/pytest -m telegram_smoke
```

#### Manual Verification Checks

- [ ] **Positive delivery:** `test_telegram_smoke_delivers_plain_text_with_special_chars_and_truncation`
      passes (`SendOutcome.DELIVERED`) and a single notification message appears in the test chat.
- [ ] **Plain-text & special-character rendering:** Inspect the received message in Telegram and
      confirm `<script>`, `&`, `"`, `'`, and `>` appear literally as plain text (no HTML tag
      stripping, no entity escaping, no parse errors).
- [ ] **Title truncation & message size:** Confirm both the wish title and list title are capped at
      `TITLE_LIMIT` (`100` characters) and the full message renders cleanly well below Telegram's
      4096-character limit.
- [ ] **Error-handling / negative check:** `test_telegram_smoke_rejects_invalid_chat` passes,
      confirming Telegram rejects the invalid target and `AiogramNoticeSender.send` classifies the
      error as `SendOutcome.REJECTED` with a non-empty `error_class` without messaging any real user.

#### Cleanup

- [ ] Unset `WISHENKA_TELEGRAM_SMOKE_TOKEN`, `WISHENKA_TELEGRAM_SMOKE_CHAT_ID`, and
      `WISHENKA_TELEGRAM_SMOKE_INVALID_CHAT_ID` from your shell session (`unset WISHENKA_TELEGRAM_SMOKE_TOKEN WISHENKA_TELEGRAM_SMOKE_CHAT_ID WISHENKA_TELEGRAM_SMOKE_INVALID_CHAT_ID`).
- [ ] Optionally delete the test message(s) from the test Telegram chat.

## Known Limitations and Follow-up Tasks

- **[WISHENKA-184](https://pypost.atlassian.net/browse/WISHENKA-184):** Extract the duplicated
  live-eligibility SQL in `claim_reminder` and `refresh_reminder` into a shared helper, and move
  `update_wishlist` / `set_role` domain mutations from `wishenka/web/routes/wishlists.py` into
  public `WishlistService` methods.
- **[WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35):** Account deletion and
  personal-data erasure must include `bot_destinations`, `birthday_entries`, `birthday_input`,
  `reminder_outbox`, `notice_receipt_keys`, and chat-scoped `notice_rate_slots`.
- **[WISHENKA-156](https://pypost.atlassian.net/browse/WISHENKA-156):** Opt-in live Telegram smoke
  test and multiprocess worker race coverage for the expanded service queue and shared rate limits.
- **[WISHENKA-194](https://pypost.atlassian.net/browse/WISHENKA-194) / [WISHENKA-195](https://pypost.atlassian.net/browse/WISHENKA-195) / [WISHENKA-196](https://pypost.atlassian.net/browse/WISHENKA-196):**
  Follow-ups from `WISHENKA-34` (implemented): batch per-wishlist override queries and deduplicate
  the accessible-wishlist helper in `NotificationPreferencesStore`, wire
  `NotificationPreferencesStore` via `app.state` / FastAPI dependency in `profile.py`, and
  refresh inherited effective badges dynamically in `settings.html` with DOM/E2E test coverage.
