# Telegram bot entry and Mini App navigation

## Overview

The bot handles private `/start` messages, presents a Russian or English menu, and opens the
Mini App or a public wishlist. [Bot journeys and notifications](../../in-docs/bot-scenarios.md)
contains the functional specification. Forwarded wish creation and the additional notification
scenarios remain planned. The existing receipt notice worker is described in
[Gift receipt](gift-receipt.md).

## Architecture and navigation

`wishenka.bot.__main__` starts a separate aiogram polling process and provides the configured
Mini App URL and `UserStore` to `wishenka.bot.entry.create_router`. The router handles private
chats only. It uses a stored language when available, otherwise the Telegram language code;
Russian language codes select Russian and all others select English. A help callback responds in
the selected language. The router does not create a user or wishlist during entry.

The Create wishlist, My wishlists and Open Mini App buttons use `WebAppInfo` URLs with the
`startapp` values `create`, `collection` and `home`. Mini App startup authenticates the user and
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
- `WISHENKA_DATABASE_URL`: shared database URL, used to look up the user's language preference.
- `WISHENKA_LOG_LEVEL` and `WISHENKA_LOG_JSON`: log level and structured JSON output.
- `WISHENKA_TELEGRAM_BOT_USERNAME` and `WISHENKA_TELEGRAM_APP_SHORT_NAME`: configure Mini App
  share-link generation; see [Authentication](auth.md) for session and origin configuration.

Configure Telegram and the application's public HTTPS endpoint consistently. The bot process
closes its Telegram session and database engine when polling stops. It is independent of the
receipt notice worker and does not enable that worker's settings.

## Logging and verification

The entry router emits `bot_start_handled` with a bounded outcome (`menu`, `public_link`, or
`invalid_link`) and `bot_start_failed` for errors. Public view events are
`public_entry_viewed` and `public_entry_unavailable`. These events exclude payloads, link tokens,
user identifiers and exception text. The bot error handler consumes exceptions to prevent aiogram
from logging their contents. Uvicorn's application access filter masks capability paths and
removes query strings; external proxies and their access logs must be configured separately.

Run the focused tests with:

```bash
make test PYTEST_JOBS=0 PYTEST_ARGS='tests/test_bot_start_repro.py tests/test_bot_entry_repro.py'
```

They exercise a fake Telegram transport and Mini App browser behavior. Observability tests also
check dispatcher error handling and actual Uvicorn access output. The full quality gate is
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
- For receipt notice delivery failures, see
  [Gift receipt troubleshooting](gift-receipt.md#troubleshooting).
