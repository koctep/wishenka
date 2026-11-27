# Telegram bot entry and Mini App navigation

## Overview

The bot handles private `/start` and `/help` messages, presents a Russian or English menu, and opens
the Mini App or a public wishlist. [Bot journeys and notifications](../../in-docs/bot-scenarios.md)
contains the functional specification. Private text and forwarded messages can create wishes
through a reviewable draft. Support and feedback requests (`/support`, `support:open`) are
documented in [Telegram bot support and feedback channel](bot-support.md). Private birthday
tracking (`/birthdays`), opt-in reservation confirmations (`/reservation_confirmations on|off`),
shared wishlist notifications, and occasion reminders are described in
[Service notifications and reminders](notifications.md). The receipt notice worker is also
described in [Gift receipt](gift-receipt.md).

## Architecture and navigation

`wishenka.bot.__main__` starts a separate aiogram polling process and provides the configured
Mini App URL, `UserStore`, `WishlistStore`, `ItemPreviewService`, and `WISHENKA_SUPPORT_*` settings
to `wishenka.bot.entry.create_router`. The router handles private
chats only. It uses a stored language when available, otherwise the Telegram language code;
`en*` language codes select English and all others select Russian. Both `/help` and the
`How it works` (`entry:help`) callback respond in the selected language, explain
`/reservation_confirmations on|off` and `/support`, and present the main navigation keyboard. When `user_store` is configured, verified private-chat interactions (`chat.id == from_user.id`)
across `wishenka/bot/entry.py`, `wishenka/bot/support.py`, `wishenka/bot/birthdays.py`, and
`wishenka/bot/capture.py` resolve the user through the shared
`wishenka.bot.principal.ensure_private_bot_user(dependencies, user, chat_id, ...)` helper: it
reads the existing `users` row first (preserving stored `language_code` without unnecessary writes),
upserts via `upsert_from_bot` under `_private_bot_user` log suppression if absent, and activates
their private destination in `bot_destinations` through `UserStore.write` with operation
`record_private_chat`. `write` forwards to `_immediate` once. A leftover lock is WARNING
`user_store_busy` and `UserStoreBusyError`. There is no second retry. Verified `/start` and `/help` commands also clear
any active support session (`clear_support_session`).

The Create wishlist, My wishlists and Open Mini App buttons use `WebAppInfo` URLs with the
`startapp` values `create`, `collection` and `home`. The menu also includes `How it works`
(`entry:help`), `Contact support` (`support:open`; see
[Telegram bot support and feedback channel](bot-support.md)), and `Birthdays` (`birthday:open`)
callback buttons (see
[Service notifications and reminders](notifications.md#private-birthdays-tracking-flow)). Mini App
startup authenticates the user and
opens the home view for these intents; `create` focuses its first button and does not create a
wishlist. A valid `/start p_<token>` adds an Open wishlist button whose URL carries that payload.
Malformed bot payloads receive a generic unavailable message and the normal menu.

`wishenka/web/static/miniapp.js` accepts `p_<token>` public links and `i_<token>` collaborator
invitations. The latter opens a preview and requires explicit confirmation to join. A public
link resolves via `GET /api/public/wishlists/{token}/view`: an authenticated user receives a
role-specific projection, while an anonymous visitor receives recipient-safe item data. An
eligible authenticated giver can reserve through
`POST /api/public/wishlists/{token}/items/{item_id}/reservations`; the service resolves the
capability and creates the reservation in the same storage operation. Missing, invalid or revoked
public links produce a generic Mini App recovery view. Authentication and CSRF requirements are
explained in [Authentication](auth.md).

The older HTML `/share/{token}` route is separate from this Mini App view. Its anonymous
projection can expose availability; [WISHENKA-63](https://pypost.atlassian.net/browse/WISHENKA-63)
tracks that pre-existing privacy issue. Do not treat the Mini App projection as a fix for the
legacy route.

## Capturing a wish in chat

`wishenka.bot.capture.create_capture_router` handles non-command text in private chats, including
forwarded text. `wishenka.bot.entry.create_router` mounts `create_support_router`,
`create_birthday_router`, and `create_capture_router` in that priority order when the wishlist
store is available: while a support session is active in `support_input`, the support router
consumes private messages first without creating wish drafts (see
[Telegram bot support and feedback channel](bot-support.md)); otherwise, while a birthday label or
date input session is active in `birthday_input`, the birthday router consumes the text message
before wish capture. The
polling process supplies both dependencies. When capture starts in a verified private chat,
`ensure_private_bot_user` resolves or creates the user and marks their `bot_destinations` entry
active.

The classifier extracts a URL and residual title. Supported links are sent to the existing preview
service; partial or failed extraction leaves a manual draft and identifies missing fields. Other
schemes are kept in the draft for correction without a preview request. At save, `link` and
`image_url` must be absolute HTTP(S) URLs. The user can edit or clear optional fields, inspect full
values across bounded Telegram messages, choose an eligible wishlist, and explicitly save or cancel.
With one eligible list it is selected automatically; several lists use paginated inline buttons.
The offer loads those lists with `list_accessible_wishlist_ids`, then
`get_wishlist_headers_by_ids` and this person's membership
(`list_user_memberships_by_wishlist_ids`). It does not read `wl_items` or
`wl_reservations`. A successful header load adds no new log. Saving the chosen
list stays on the existing wish write. When no list is available the menu
offers Mini App navigation. Access is rechecked on save.

The migrations `add_bot_drafts`, `add_bot_capture_order`, and `add_bot_capture_order_retention`
create durable SQLite state. An active draft and message-order watermark (`bot_capture_order`) are
stored atomically before network preview; `updated_at` (UNIX epoch seconds) is initialized on
insert/backfill and refreshed on every draft edit, preview enrichment, save, or cancel. The owner
and chat bind each callback; an expiry and revision reject stale actions. A newer message replaces
the active draft, and a delayed preview cannot overwrite a newer message or edit. Preview
enrichment increments the revision so previously displayed save buttons cannot submit unseen
values. Redelivery can show the persisted manual draft after an interruption. The save transaction
combines the domain write and receipt, allowing a repeated callback to return the previous result
without creating another wish.

Active drafts expire after 24 hours, pending birthday inputs after one hour, active support
sessions after `WISHENKA_SUPPORT_SESSION_TTL_SECONDS` (one hour by default), and save receipts
after seven days. The bot starts a cleanup loop immediately, then hourly; it removes up to 100
expired rows per pass across `bot_drafts`, `birthday_input`, `support_input`, `support_tickets`
(retaining ticket rate-limit metadata for 30 days), and stale `bot_capture_order` watermarks
(`updated_at IS NULL OR updated_at <= now - order_retention_days * 86400`, defaulting to
`Settings.bot_capture_order_retention_days = 30`, minimum `2`) that have no active, unexpired
`bot_drafts` row (`state = 'active' AND expires > now`). Cleanup retries a failure in one minute.
[WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35) covers account deletion. Include
the bot draft tables, support tables (`support_input`, `support_tickets`), and the
notification/birthday tables (see
[Service notifications and reminders](notifications.md)) when implementing that deletion. The
atomic capture mutation (`wishenka/bot/capture.py`) saves a wish with
`RepoWishlistOps.add_wish_item` inside `WishlistStore.run_repository`. The draft
SQL (`bot_drafts` and `bot_capture_order`) shares that immediate transaction.
`run_repository` commits and flushes commit logs on the repository it built.
The save does not apply a second snapshot add.

## Running and configuration

Start the web server using the repository workflow, and run one bot receiver alongside it:

```bash
python -m wishenka.bot
```

Run exactly one polling receiver per bot token. Settings are loaded from `WISHENKA_` environment
variables or `.env`:

- `WISHENKA_BOT_TOKEN`: real Telegram bot token; the default is a nonfunctional placeholder.
- `WISHENKA_MINI_APP_URL`: HTTPS Mini App URL without credentials or a fragment. The router
  replaces any existing `startapp` query parameter. The empty default fails router validation.
- `WISHENKA_DATABASE_URL`: shared database URL for users, wishlists, drafts and receipts.
- `WISHENKA_LOG_LEVEL` and `WISHENKA_LOG_JSON`: log level and structured JSON output.
- `WISHENKA_TELEGRAM_BOT_USERNAME` and `WISHENKA_TELEGRAM_APP_SHORT_NAME`: configure Mini App
  share-link generation; see [Authentication](auth.md) for session and origin configuration.
- `WISHENKA_SUPPORT_CHAT_ID`, `WISHENKA_SUPPORT_ADMIN_IDS`, `WISHENKA_SUPPORT_SESSION_TTL_SECONDS`,
  `WISHENKA_SUPPORT_MAX_MESSAGE_LENGTH`, `WISHENKA_SUPPORT_RATE_LIMIT_WINDOW_SECONDS`, and
  `WISHENKA_SUPPORT_RATE_LIMIT_MAX_TICKETS`: configure the support and feedback channel; see
  [Telegram bot support and feedback channel](bot-support.md#configuration).
- `WISHENKA_BOT_CAPTURE_ORDER_RETENTION_DAYS`: retention window in days (`Settings.bot_capture_order_retention_days`,
  default `30`, minimum `2`) before stale `bot_capture_order` watermarks are removed by
  `cleanup_drafts`.

Configure Telegram and the application's public HTTPS endpoint consistently. The bot process
closes its Telegram session and database engine when polling stops. It is independent of the
receipt notice worker and does not enable that worker's settings.

## Logging and verification

The entry router emits `bot_start_handled` with a bounded outcome (`menu`, `public_link`, or
`invalid_link`) and `bot_start_failed` for errors. Public view events are
`public_entry_viewed` and `public_entry_unavailable`. These events exclude payloads, link tokens,
user identifiers and exception text. The bot error handler consumes exceptions to prevent aiogram
from logging their contents. Capture emits `bot_capture_preview`, `bot_capture_draft_ready`,
`bot_capture_save`, `bot_capture_action_error`, `bot_draft_cleanup_completed` (`INFO` when
`total_removed > 0`, `DEBUG` when `0`; includes `total_removed`, `bot_drafts_removed`,
`birthday_input_removed`, `support_input_removed`, `support_tickets_removed`,
`bot_capture_order_removed`, `order_retention_days`, and `duration_ms`), and
`bot_draft_cleanup_failed` (includes `order_retention_days`). Support emits
`bot_support_prompted`, `bot_support_cancelled`, `bot_support_rejected`, `bot_support_submitted`,
and `bot_support_unavailable` on `wishenka.bot.support` (see
[Telegram bot support and feedback channel](bot-support.md#observability)). These events omit
message contents, URLs, identifiers, and exception text. A context-local filter suppresses
specified dependency loggers during sensitive work; it does not automatically cover future
loggers. Cleanup failures retry after one minute. Uvicorn's access filter masks capability paths and
removes query strings; external proxies and their access logs must be configured separately.

Run the focused tests with:

```bash
make test PYTEST_JOBS=0 PYTEST_ARGS='tests/test_bot_principal.py tests/test_bot_start_repro.py tests/test_bot_entry_repro.py'
make test PYTEST_JOBS=0 PYTEST_ARGS='tests/test_bot_capture_repro.py tests/test_bot_capture_atomic_store_repro.py tests/test_bot_capture_order_retention_repro.py tests/test_bot_capture_order_retention.py'
make test PYTEST_JOBS=0 PYTEST_ARGS='tests/test_bot_support_repro.py tests/test_bot_support.py tests/test_wishenka_182_repro.py'
make test-serial PYTEST_ARGS='tests/test_bot_menu_miniapp_e2e_browser.py'
```

They exercise a fake Telegram transport and Mini App browser behavior. In particular,
`tests/test_bot_menu_miniapp_e2e_browser.py` dispatches `/start` through
`wishenka.bot.entry.create_router`, opens the generated `startapp` targets (`create`,
`collection`, `home`) in headless Chromium via `tests/browser_cdp.py` for both `en` and `ru`,
verifies localized rendering, button focus on `create`, zero implicit wishlist creation, and safe
recovery for invalid `startapp` values without leaking existing wishlist data. Observability tests
also check dispatcher error handling and actual Uvicorn access output. The full quality gate is
`make check PYTEST_JOBS=4`.

## Troubleshooting

- If the bot does not respond, check the token, network connectivity, private-chat context and
  that only one polling receiver is active. Inspect `bot_start_failed` without logging payloads.
- If startup rejects the Mini App URL, set an HTTPS URL without user credentials or a fragment.
  Check that the configured address points to the deployed Mini App.
- If a link is unavailable, check whether it was revoked or the list was deleted; the user-facing
  response intentionally does not distinguish these cases. Do not paste capability links into logs.
- If sign-in or reservation fails, check Telegram session, origin and CSRF configuration in
  [Authentication](auth.md). Anonymous viewers do not get reservation controls.
- If capture cannot save, verify that the selected list remains accessible, required fields are
  valid, and links use HTTP(S). Expired or replaced drafts require a new message.
- If `bot_draft_cleanup_failed` occurs, check database availability and storage capacity. The loop
  retries automatically; avoid including draft content or links in diagnostic logs. If
  `bot_capture_order` rows accumulate or are pruned unexpectedly, verify
  `WISHENKA_BOT_CAPTURE_ORDER_RETENTION_DAYS` (`>= 2`) and inspect `bot_draft_cleanup_completed`
  (`bot_capture_order_removed`, `order_retention_days`).
- For support and feedback channel issues (`bot_support_unavailable` or session expiry), see
  [Telegram bot support and feedback channel troubleshooting](bot-support.md#troubleshooting).
- For receipt notice delivery failures, see
  [Gift receipt troubleshooting](gift-receipt.md#troubleshooting).
