# Service Notifications, Occasion Reminders, and Private Birthday Tracking

> **Status: IMPLEMENTED by [WISHENKA-29](https://pypost.atlassian.net/browse/WISHENKA-29), building
> on the gift receipt notice foundation from [WISHENKA-23](gift-receipt.md#notice-path).**

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
| `NoticeStore` / `ClaimedNotice` | `wishenka/notices/store.py` | Fenced claiming, pre-send eligibility refresh, settlement, and retention purge for `notification_outbox` |
| `claim_reminder` / `refresh_reminder` / `settle_reminder` | `wishenka/notices/reminders.py` | Fenced claiming, live authorization/preference refresh, localized rendering, and settlement for `reminder_outbox` |
| `ReminderScheduler` / `utc_event_date` | `wishenka/notices/scheduler.py` | Bounded, cursor-driven UTC scanner for dated wishlists and private birthday entries |
| `reserve_permit` / `block_until` | `wishenka/notices/rate.py` | Cross-process SQLite rate limiter and `RetryAfter` throttle state in `notice_rate_slots` |
| `NoticeWorker` | `wishenka/notices/worker.py` | Lifespan background loop driving the hourly scheduler, draining both queues, and emitting windowed summaries |
| `NoticeSender` / `classify_error` | `wishenka/notices/sender.py` | Aiogram-backed Telegram sender mapping outcomes to `DELIVERED`, `REJECTED`, `RETRYABLE`, or `AMBIGUOUS` |
| `create_birthday_router` | `wishenka/bot/birthdays.py` | Private-chat `/birthdays` and `/cancel` commands, inline callbacks, and durable `birthday_input` state |
| `create_router` | `wishenka/bot/entry.py` | Private `/start` destination registration, `/reservation_confirmations on\|off`, and menu entry |
| Operator CLI | `wishenka/notices/operator.py` | Content-free inspection (`counts`, `list`) and manual resolution (`retry`, `fail`) of `uncertain` rows |

### Database Schema and Migrations

Two Alembic revisions extend the wishlist database schema (see [`doc/dev/migrations.md`](migrations.md)):

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

### Surprise Protection and Live Eligibility Rules

1. **Candidate selection at mutation time (`WishlistService` and `EventProducer`):**
   - Shared wishlist events (`_record_shared_event`) snapshot candidate recipients in the domain
     transaction: the wishlist owner, current members (`wl_members`), and holders of `ACTIVE` or
     `PURCHASED` reservations on the affected wish (or on any wish in the list for
     `list_archived`). The acting user (`actor_id`) is always excluded.
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
     `gift_received` notice or a `reservation_confirmation` for that wish, even if they also hold a
     collaborator or giver role.
   - On a collaborative wishlist (`is_collaborative = 1`), the list owner can act as a giver for a
     wish assigned to another recipient (`recipient_user_id != owner_id`).
   - Independently safe wishlist changes (`item_created`, `item_updated`, `item_archived`,
     `item_restored`, `list_updated`, `list_archived`, `list_restored`, `membership_changed`) and
     neutral occasion reminders remain eligible for the recipient when they have access, because
     neither their trigger nor their text depends on reservation or receipt state.
3. **Notification categories and preference precedence:**
   - Every notice checks `wl_list_notification_settings(user_id, wishlist_id, event_type)` first
     (when `list_id` is present), falling back to `user_notification_settings(user_id, event_type)`,
     and then to the category default:

     | Category (`event_type`) | Covers `kind` / queue | Default when unset |
     | ----------------------- | --------------------- | ------------------ |
     | `gift_received` | `notification_outbox` (`gift_received`) | Enabled (`1`) |
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
     - For `gift_received`, the list must not be `deleted`, the wish must not be archived
       (`is_archived = 0`), the user must not be the wish recipient, the `gift_received` setting
       must be enabled, and the user must still hold a reservation on the wish.
     - For `reservation_confirmation`, the list must be `active`, the user must still hold a
       reservation on the item, must not be the recipient, and `reservation_changes` must be
       explicitly `1`.
     - For shared wishlist changes, the list must be `active` or `archived`, the item (if set) must
       exist, and the user must currently be the owner, a member, or hold an active/purchased
       reservation on the item (or on any item in the list for `list_archived`).
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
  - Deleting an entry sets `deleted = 1, revision = revision + 1` and removes any pending
    `birthday_input` for that entry.
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

- **`SAFE_SHARED_EVENTS`**: `"item_created"`, `"item_updated"`, `"item_archived"`,
  `"item_restored"`, `"list_updated"`, `"list_archived"`, `"list_restored"`,
  `"membership_changed"`, `"reservation_confirmation"`. Passing any other `kind` raises
  `ValueError("Unsupported shared notification event")`.

### Running the Reminder Scheduler (`wishenka.notices.scheduler`)

```python
from wishenka.notices.scheduler import ReminderScheduler, utc_event_date

event_day = utc_event_date("2026-12-25T00:00:00Z")
scheduler = ReminderScheduler(wishlist_store, settings)
more_pages = await scheduler.run_once(now=int(time.time()))
```

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
```

Programmatic functions in `wishenka.notices.operator`:

- `await counts(store) -> dict[str, dict[str, int]]`: returns `{"receipt": {<status>: <count>},
  "reminder": {<status>: <count>}}`.
- `await list_uncertain(store, queue, limit=100) -> list[dict[str, int]]`: returns
  `[{"id": <int>, "attempts": <int>}, ...]` for `queue in ("receipt", "reminder")` and
  `1 <= limit <= 100`.
- `await resolve(store, queue, ident, action, now) -> bool`: transitions row `ident` from
  `uncertain` to `pending` (`action="retry"`, clearing `ambiguous=0` on `receipt`) or `failed`
  (`action="fail"`). Returns `True` if a row was updated, `False` if not found or not `uncertain`.

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
| `receipt_notice_retention_days` | `WISHENKA_RECEIPT_NOTICE_RETENTION_DAYS` | `30` | `>= 1`; retention period before `purge_finished` deletes terminal receipt rows |
| `notice_global_per_second` | `WISHENKA_NOTICE_GLOBAL_PER_SECOND` | `20` | `1..30`; global send limit per second across all worker processes |
| `notice_chat_interval_seconds` | `WISHENKA_NOTICE_CHAT_INTERVAL_SECONDS` | `1` | `>= 1`; minimum interval in seconds between sends to the same `chat_id` |
| `notice_reminder_lead_days` | `WISHENKA_NOTICE_REMINDER_LEAD_DAYS` | `(7,)` | Non-empty tuple of positive integers (`> 0`); lead days in UTC before an occasion |

## Observability

Structured log events use `extra={"event": ...}` and never include user IDs, chat IDs, birthday
labels or dates, wish/list titles, capability links, bot tokens, or raw exception messages:

| Event | Level | Logger | Fields |
| ----- | ----- | ------ | ------ |
| `receipt_notice_window_summary` | INFO | `wishenka.wishlists.notices` | `window_seconds`, `sent`, `retried`, `failed_terminal`, `uncertain` |
| `service_delivery_window_summary` | INFO | `wishenka.wishlists.notices` | `window_seconds`, `sent`, `retried`, `failed_terminal`, `uncertain`, `skipped` |
| `receipt_notice_worker_error` | ERROR | `wishenka.wishlists.notices` | `error_class` (logged once per consecutive worker failure streak) |
| `reminder_scheduler_error` | ERROR | `wishenka.wishlists.notices` | `error_class` (logged once per consecutive scheduler failure streak; does not block queue delivery) |
| `reminder_scan_completed` | DEBUG | `wishenka.notices.scheduler` | `lists_scanned`, `birthdays_scanned`, `intents_created` (emitted only on non-empty scans) |
| `receipt_notice_uncertain` | DEBUG | `wishenka.wishlists.notices` | `outbox_id`, `attempt`, `error_class` (when a receipt send is ambiguous or lease expires) |

See [`ai-tasks/WISHENKA-29/50-observability.md`](../../ai-tasks/WISHENKA-29/50-observability.md)
for the complete observability specification.

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

Run the focused notification, reminder, upgrade, operator, and observability test suites with:

```bash
make test PYTEST_JOBS=0 PYTEST_ARGS='tests/test_notice_delivery_repro.py tests/test_notice_wishlist_events.py tests/test_notice_upgrade.py tests/test_notice_operator.py tests/test_reminder_scan_paging.py tests/test_service_notice_observability.py tests/test_receipt_notices.py tests/test_receipt_observability.py'
```

## Known Limitations and Follow-up Tasks

- **[WISHENKA-181](https://pypost.atlassian.net/browse/WISHENKA-181):** Physical retention and
  purge policy for soft-deleted `birthday_entries`, terminal `reminder_outbox` rows, inactive
  `bot_destinations`, and `notice_receipt_keys`.
- **[WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35):** Account deletion and
  personal-data erasure must include `bot_destinations`, `birthday_entries`, `birthday_input`,
  `reminder_outbox`, `notice_receipt_keys`, and chat-scoped `notice_rate_slots`.
- **[WISHENKA-180](https://pypost.atlassian.net/browse/WISHENKA-180):** Replace `NoticeWorker` access
  to the private `NoticeStore._store` attribute with a public store transaction interface.
- **[WISHENKA-156](https://pypost.atlassian.net/browse/WISHENKA-156):** Opt-in live Telegram smoke
  test and multiprocess worker race coverage for the expanded service queue and shared rate limits.
- **[WISHENKA-34](https://pypost.atlassian.net/browse/WISHENKA-34):** Mini App UI screen for
  managing global and per-list notification settings.
