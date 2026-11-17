# Telegram Bot Support and Feedback Channel

> **Status: IMPLEMENTED by [WISHENKA-30](https://pypost.atlassian.net/browse/WISHENKA-30).**

## Overview

The Telegram bot support and feedback channel (`wishenka/bot/support.py`) provides a localized
(Russian and English) entry point in private bot chats so users can ask questions, report broken
product links or bugs, and send feedback without accidentally creating wishlists or wish drafts.

Key capabilities:

- **Discoverable help and support entry points:** Private `/start` menus include a localized
  `Contact support` / `Написать в поддержку` (`support:open`) button; `/help` and the
  `How it works` / `Как это работает` (`entry:help`) callback explain core bot flows and direct
  users to `support:open` or `/support`.
- **Interactive and inline support submission:** Users can open a durable support session via
  `support:open` or `/support` and send their message in the next turn, or submit directly in one
  command via `/support <text>`.
- **Strict session isolation and router precedence:** While a support session is active in
  `support_input`, plain-text messages and URLs are consumed by `create_support_router` before
  reaching `create_birthday_router` or `create_capture_router`, preventing `ItemPreviewService`
  calls and wish draft creation.
- **Metadata-only diagnostic context and capability redaction:** Forwarded tickets include safe
  account and bot metadata (`DiagnosticContext`) while stripping secret capability tokens (`p_*`,
  `i_*`, `/share/*`, `/invite/*`, `/api/public/wishlists/*`, and stored token values) and never
  querying wish item titles, reservations, or gift receipts.
- **Per-user sliding-window rate limiting and truthful delivery:** Submissions are rate-limited via
  content-free metadata rows in `support_tickets`. Tickets are confirmed with a `SUP-...` reference
  only after at least one configured Telegram destination (`support_chat_id` or
  `support_admin_ids`) accepts the message.

## Architecture

```text
Private Telegram Update
  |
  v
wishenka.bot.entry.create_router (/start, /help, entry:help, /reservation_confirmations)
  |
  +--> 1. create_support_router  (wishenka/bot/support.py)
  |       - /support, /support <text>, support:open, support:cancel, /cancel
  |       - intercepts private messages when support_input is active (expires_at > now)
  |       - raises SkipHandler when no support_input session is active
  |
  +--> 2. create_birthday_router (wishenka/bot/birthdays.py)
  |       - /birthdays, birthday:*, /cancel
  |       - intercepts private text when birthday_input is active; otherwise SkipHandler
  |
  +--> 3. create_capture_router  (wishenka/bot/capture.py)
          - captures wishes and URLs into bot_drafts when no input session is active
```

### Key Components

| Component | Path | Responsibility |
| --------- | ---- | -------------- |
| Support Router & Service | `wishenka/bot/support.py` | Manages `support_input` sessions, `/support` and `/cancel` commands, `support:open` and `support:cancel` callbacks, validation, rate limiting, capability redaction, diagnostic context collection, and ticket forwarding |
| Bot Entry Router | `wishenka/bot/entry.py` | Handles `/start`, `/help`, `entry:help`, and `/reservation_confirmations`; exposes the `support:open` button; clears active `support_input` sessions when superseded; mounts sub-routers in priority order |
| Birthday Router | `wishenka/bot/birthdays.py` | Clears any active `support_input` session when `/birthdays` or `birthday:*` callbacks run; handles `/cancel` for `birthday_input` when support does not consume it |
| Wish Capture & Cleanup | `wishenka/bot/capture.py` | Captures wishes when neither `support_input` nor `birthday_input` is active; `cleanup_drafts` purges expired `support_input` and aged `support_tickets` rows |
| Bot Runner | `wishenka/bot/__main__.py` | Wires `Settings` support parameters into `Dependencies` and runs the hourly `cleanup_loop` |
| Configuration | `wishenka/config.py` | Defines and validates `WISHENKA_SUPPORT_*` settings on `Settings` |
| Schema Migration | `wishenka/wishlists/alembic/versions/add_support_channel.py` | Alembic revision (`add_support_channel`, down revision `add_notice_uncertain`) creating `support_input` and `support_tickets` |

### Router Precedence and Session Isolation

`wishenka.bot.entry.create_router` mounts sub-routers in deterministic order when `wishlist_store`
is present:

1. `create_support_router(dependencies)`
2. `create_birthday_router(dependencies)`
3. `create_capture_router(dependencies)`

Session mutual exclusion and superseding rules:

- **Opening a support session (`_open_support_session`):** Runs a `BEGIN IMMEDIATE` transaction
  that inserts or replaces the `(owner_id, chat_id)` row in `support_input` (`expires_at = now +
  support_session_ttl_seconds`), deletes any pending `(owner_id, chat_id)` row from
  `birthday_input`, and clears `edit_field = NULL` on any active `bot_drafts` row for that user and
  chat. Existing wishlists, items, birthday entries, and unedited draft state remain untouched.
- **Active session interception:** While `support_input.expires_at > now`, non-command text
  messages are handled by `text_message` (submitting the ticket) and non-text messages (photos,
  stickers, voice notes, documents) are handled by `non_text_message` (returning a localized
  text-only prompt while keeping the session open). When no session exists or `expires_at <= now`
  (in which case the expired row is lazily deleted), the handlers raise `SkipHandler` so birthday
  input or wish capture proceeds normally.
- **Cancelling (`support:cancel` or `/cancel`):** `support:cancel` deletes `support_input` and
  confirms cancellation. `/cancel` in `create_support_router` deletes `support_input` and answers if
  a row existed; if no `support_input` row existed, it raises `SkipHandler` so
  `create_birthday_router` can handle `/cancel` for `birthday_input`.
- **Superseding by other commands:** Sending `/start`, `/help`, `entry:help`,
  `/reservation_confirmations`, `/birthdays`, or pressing any `birthday:*` callback calls
  `clear_support_session(store, owner_id, chat_id)` so a forgotten support prompt never captures a
  later message after the user switches flows.

### Database Schema and Migration (`add_support_channel`)

Created by Alembic revision `add_support_channel` (`down_revision = "add_notice_uncertain"`, see
[migrations.md](migrations.md)):

- **`support_input(owner_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, expires_at INTEGER NOT NULL, PRIMARY KEY (owner_id, chat_id))`**:
  Durable active support session state per internal user ID and private chat ID.
- **`support_tickets(id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_ref TEXT NOT NULL UNIQUE, owner_id INTEGER NOT NULL, telegram_id INTEGER NOT NULL, created_at INTEGER NOT NULL)`**
  with index **`idx_support_tickets_owner_time ON support_tickets(owner_id, created_at)`**:
  Content-free log of delivered support tickets used for unique ticket references and cross-restart
  sliding-window rate limiting. Message bodies are never stored in SQLite.
- **Periodic cleanup (`cleanup_drafts` in `wishenka/bot/capture.py`):** Deletes up to 100 expired
  `support_input` rows (`expires_at <= now`) and up to 100 `support_tickets` rows older than 30 days
  (`created_at <= now - 30 * 86400`) per hourly pass.

### Capability Redaction, Privacy, and Surprise Protection

- **Capability token redaction (`redact_capabilities`):** Before formatting a ticket, the user's
  message is scrubbed using regex patterns (`_STARTAPP_TOKEN_RE`, `_CAPABILITY_PATH_RE`,
  `_CAPABILITY_TOKEN_RE`) and exact replacement against all non-empty tokens (`len >= 4`) loaded
  from `wl_lists(public_token, invite_token)`, `wl_tokens(token)`, and `wl_invite_tokens(token)`.
  Any `p_<token>`, `i_<token>`, `/share/<token>`, `/invite/<token>`, or
  `/api/public/wishlists/<token>` secret is replaced with `[REDACTED]`.
- **Metadata-only diagnostic context (`collect_diagnostic_context`):** Queries only `bot_destinations`
  (`active` boolean), `wl_lists` (counts of `active` and `archived` lists owned by
  `telegram_user_id`), `wl_members` (count of non-deleted collaborative memberships), and
  `bot_drafts` (boolean presence of an active draft). It never queries `wl_items` titles or links,
  `wl_reservations`, or `wl_receipts`, preserving the Surprise Invariant.
- **Link preview suppression:** Outbound `send_message` calls to support destinations pass
  `link_preview_options=LinkPreviewOptions(is_disabled=True)` so Telegram does not generate webpage
  previews for user-supplied links.
- **Private user log suppression:** User upserts in `principal()`, `/start`, and `/help` set the
  `_private_bot_user` `ContextVar` filter on `wishenka.users`, preventing `user_created` and
  `user_updated` logs from writing Telegram IDs or profile names during private bot interactions.
  Moreover, `support.py` preserves an existing `users.language_code` when upserting so stored
  language preferences are respected.

## API / Usage

### `create_support_router(dependencies)`

Builds the private-chat `aiogram.Router` for `/support`, `support:open`, `support:cancel`,
`/cancel`, and active-session message interception. Mounted automatically by
`wishenka.bot.entry.create_router(dependencies)` when `dependencies.wishlist_store` is not `None`.

### `clear_support_session(store, owner_id, chat_id)`

Deletes any active `support_input` row for `(owner_id, chat_id)` inside a `WishlistStore.transaction`
when another bot command or callback supersedes the support session.

- **`store`**: `WishlistStore` instance.
- **`owner_id`**: Internal user ID (`users.id`).
- **`chat_id`**: Private Telegram chat ID.

### `DiagnosticContext` and `collect_diagnostic_context(...)`

`DiagnosticContext` is a frozen dataclass holding metadata-only diagnostic fields:
`ticket_ref`, `submitted_at_iso` (`%d.%m.%y %H:%M:%S UTC`), `internal_user_id`,
`telegram_user_id`, `username`, `display_name`, `effective_language`, `telegram_language_code`,
`bot_destination_active`, `active_wishlist_count`, `archived_wishlist_count`,
`collaborative_membership_count`, and `active_draft_present`.

`await collect_diagnostic_context(conn, ...)` executes inside an active `AsyncConnection` and
returns `(DiagnosticContext, known_tokens)`.

### `redact_capabilities(text_value, known_tokens=())`

Replaces capability tokens and share/invite link secrets in `text_value` with `"[REDACTED]"` and
returns the sanitized string.

### `generate_ticket_ref(now)` and `format_support_ticket(context, sanitized_message)`

- **`generate_ticket_ref(now)`**: Generates a reference matching `SUP-\d{8}-[A-Z0-9]{8}` from UTC
  `now` (`%m%d%H%M` with `"202"` mapped to `"303"` to avoid short numeric fixture collisions, plus
  8 random characters from `_TICKET_ALPHABET`).
- **`format_support_ticket(context, sanitized_message)`**: Renders the plain-text support ticket
  header and truncates `sanitized_message` so the combined payload never exceeds Telegram's
  4096-character limit.

## Configuration

All settings are defined on `wishenka.config.Settings` (`WISHENKA_` environment prefix) and passed
into `wishenka.bot.__main__.Dependencies`:

| Setting | Environment Variable | Default | Validation / Meaning |
| ------- | -------------------- | ------- | -------------------- |
| `support_chat_id` | `WISHENKA_SUPPORT_CHAT_ID` | `None` | Optional integer chat ID of the primary Telegram support group/channel/chat |
| `support_admin_ids` | `WISHENKA_SUPPORT_ADMIN_IDS` | `()` | Optional tuple of integer administrator chat IDs (deduplicated with `support_chat_id`) |
| `support_session_ttl_seconds` | `WISHENKA_SUPPORT_SESSION_TTL_SECONDS` | `3600` | `60..86400`; lifetime in seconds of an interactive `support_input` session |
| `support_max_message_length` | `WISHENKA_SUPPORT_MAX_MESSAGE_LENGTH` | `2000` | `100..3500`; maximum allowed character length of a stripped support message |
| `support_rate_limit_window_seconds` | `WISHENKA_SUPPORT_RATE_LIMIT_WINDOW_SECONDS` | `3600` | `>= 60`; sliding window in seconds for per-user ticket rate limiting |
| `support_rate_limit_max_tickets` | `WISHENKA_SUPPORT_RATE_LIMIT_MAX_TICKETS` | `3` | `1..50`; maximum delivered tickets per user within `support_rate_limit_window_seconds` |

At least one destination (`WISHENKA_SUPPORT_CHAT_ID` or a non-empty `WISHENKA_SUPPORT_ADMIN_IDS`)
must be configured in production for support tickets to be delivered.

## Observability

Structured events are emitted on logger `wishenka.bot.support` with `extra={"event": ...}` and
never include user IDs, chat IDs, usernames, ticket references, message text, URLs, capability
tokens, or exception strings:

| Event | Level | Extra Fields | Meaning |
| ----- | ----- | ------------ | ------- |
| `bot_support_prompted` | INFO | `event` | Interactive support session opened via `/support` or `support:open` |
| `bot_support_cancelled` | INFO | `event` | Support session cancelled by the user via `support:cancel` or `/cancel` |
| `bot_support_rejected` | INFO | `event`, `reason` | Submission rejected (`reason`: `empty`, `too_long`, `non_text`, or `rate_limited`) |
| `bot_support_submitted` | INFO | `event`, `outcome` | Ticket delivered to at least one destination (`outcome`: `delivered` or `partial`) |
| `bot_support_unavailable` | WARNING | `event`, `reason` | No destination configured (`reason`: `unconfigured`) or a subset of configured destinations failed (`reason`: `partial_send_failed`) |
| `bot_support_unavailable` | ERROR | `event`, `reason` | Delivery to all configured destinations failed (`reason`: `send_failed`) |

Additional error boundaries:

- Unhandled exceptions in any bot router are caught by `wishenka.bot.entry:entry_error` on logger
  `wishenka.bot.entry`, which logs `bot_start_failed` with only the exception class name.
- Hourly cleanup errors are caught by `wishenka.bot.__main__:cleanup_loop` on logger
  `wishenka.bot.cleanup`, emitting `bot_draft_cleanup_failed`.
- Enable `WISHENKA_LOG_JSON=true` so `JsonFormatter` serializes the `extra` fields (`event`,
  `reason`, `outcome`).

## Troubleshooting

- **User receives "Support is temporarily unavailable" / "Канал поддержки временно недоступен":**
  1. Check `wishenka.bot.support` logs for `bot_support_unavailable`.
  2. If `reason="unconfigured"`, neither `WISHENKA_SUPPORT_CHAT_ID` nor
     `WISHENKA_SUPPORT_ADMIN_IDS` is set on the bot process. Configure at least one valid chat ID.
  3. If `reason="send_failed"`, the bot could not send to any configured support chat. Verify that
     the bot is a member of `WISHENKA_SUPPORT_CHAT_ID` with permission to post messages and that
     every admin in `WISHENKA_SUPPORT_ADMIN_IDS` has started a private chat with the bot.
- **Logs show `bot_support_unavailable` with `reason="partial_send_failed"` alongside `bot_support_submitted` (`outcome="partial"`):**
  - At least one destination succeeded (so the user truthfully received their `SUP-...` ticket
    reference), but one or more configured destination chat IDs rejected the send. Audit all chat
    IDs in `WISHENKA_SUPPORT_CHAT_ID` and `WISHENKA_SUPPORT_ADMIN_IDS`.
- **User's message created a wish draft instead of a support ticket:**
  - The user either did not open a support session first (`support:open` or `/support`), their
    session expired after `WISHENKA_SUPPORT_SESSION_TTL_SECONDS` (default 1 hour), or they ran
    another command (`/start`, `/help`, `/birthdays`, `/reservation_confirmations`) that superseded
    the support session before sending the text.
- **User is rate-limited immediately:**
  - Check `SELECT COUNT(*), MIN(created_at) FROM support_tickets WHERE owner_id = :id` against
    `WISHENKA_SUPPORT_RATE_LIMIT_WINDOW_SECONDS` and `WISHENKA_SUPPORT_RATE_LIMIT_MAX_TICKETS`.
    Rejected or failed deliveries never write to `support_tickets`.

## Testing

Run the support channel reproduction, unit, migration, and observability tests with:

```bash
make test PYTEST_JOBS=0 PYTEST_ARGS='tests/test_bot_support_repro.py tests/test_bot_support.py'
```

## Known Limitations and Follow-up Tasks

- **[WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35):** Account deletion and personal
  data cleanup must include `support_input` and `support_tickets`.
- **[WISHENKA-182](https://pypost.atlassian.net/browse/WISHENKA-182):** Replace full-table token
  scans in `collect_diagnostic_context` with scoped lookups or regex-only redaction outside the
  write transaction, and unify the private-bot user upsert + `bot_destinations` helper across
  `entry.py`, `support.py`, `birthdays.py`, and `capture.py`.
- **[WISHENKA-156](https://pypost.atlassian.net/browse/WISHENKA-156):** Extend opt-in real Telegram
  Bot API smoke tests to cover support ticket delivery and `LinkPreviewOptions(is_disabled=True)`.
