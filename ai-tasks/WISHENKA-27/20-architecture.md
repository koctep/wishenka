# WISHENKA-27: Bot entry and shared wishlist navigation

## Research

- `wishenka/main.py` starts FastAPI only; aiogram is currently used for sending receipt notices,
  not for receiving bot updates. A bot update receiver and its lifecycle are new work.
- `wishenka/web/static/miniapp.js` already produces `p_<public-token>` and `i_<invite-token>`
  Mini App links and reads a start parameter. Its current `publicView` calls the anonymous public
  projection and displays titles only: it does not provide reservation controls and cannot safely
  stand in for an identified recipient's view. The existing `/share/{public_token}` route uses
  the current viewer and the wishlist service's role-aware projection. Public capability rotation
  revokes the old link; public tokens have no separate time expiry. Invitation tokens and their
  explicit acceptance flow are distinct and must remain unchanged.
- Telegram supports inline `web_app` buttons in private bot chats and direct Mini App `startapp`
  links; `start_param` can reach the Mini App. Telegram requires user action to open an inline
  Mini App: `/start` cannot silently open it. See
  [Telegram Mini Apps](https://core.telegram.org/bots/webapps) and
  [Bot API](https://core.telegram.org/bots/api#inlinekeyboardbutton).
- User language is recorded in the user store, but a bot entrant may not have a stored profile.
  Use an existing explicit preference if present, else Telegram language code, else English;
  do not introduce a preference editor or overwrite preference on entry.

## Implementation Plan

1. Add a separately runnable aiogram 3 polling entry point with injected configuration and
   service dependencies. Keep FastAPI startup independent; run exactly one receiver per token,
   and close bot sessions and stores on shutdown. Provide a documented development command.
2. Implement private-chat `/start` and help callbacks, localizable menu text and validated
   configuration for HTTPS Mini App launch URLs. No list is created by rendering the menu.
3. Support ordinary entry, `p_<token>` bot start entry, and the existing `startapp` links. A
   valid-format target offers an explicit Open wishlist button; Mini App performs authoritative
   lookup and role-aware rendering. Invalid syntax receives generic recovery and the menu.
4. Add Mini App entry dispatch for creation, collection and public share. Authentication uses
   verified Telegram init data before role-sensitive data is rendered or reservations are made.
   Guest viewing remains available where already permitted; distinguish it from a verified viewer
   and never reuse a guest projection as the authenticated recipient's final view.
5. Test end-to-end with fake Telegram transport, local app and seeded temporary SQLite data,
   including role overlap and invalid or revoked links; no live bot or external network is needed.

### Failing repro for Step 3

Before production changes, add timeout-bounded tests under `tests/test_bot_entry_repro.py` and,
where browser execution is needed, the existing local Mini App test harness. Feed a fake private
`/start` update into the router and assert the four localized actions and distinct targets; assert
that malformed start parameters yield a generic recovery with menu and no writes. Seed a shared
wishlist, enter with `p_<token>`, bootstrap an identified recipient through verified test init data,
then assert the requested list opens with no reservation identity or status and that a giver can
reserve through the established role-aware flow. Assert rotated/deleted/unknown tokens yield the
same recovery. Tests should initially fail on missing bot entry or dispatch, not network errors;
review the red failure before implementing, then iterate until green. Test the existing `i_` flow
as a regression and ensure ordinary starts and rendering never create a list.

## Architecture

```text
Telegram private chat -- /start, help --> aiogram receiver/router
                                                |
                           localized text + buttons (HTTPS URLs)
                                                v
                        Mini App entry dispatcher + Telegram auth
                           |                |                 |
                      home/create     public capability    invitation
                           |                |                 |
                        web API      role-aware share     existing flow
                                            |
                                    wishlist service/store
```

### Components and dependencies

- **Bot receiver:** owns polling lifecycle, validates configuration, registers router and receives
  updates. It is separate from the web server so scaling web workers cannot create competing
  consumers. Deployment starts exactly one polling instance; no webhook is introduced here.
- **Entry router:** accepts only private `/start` messages and help callbacks, selects localized
  copy and constructs a fixed inline keyboard. Normal, malformed and syntactically valid `p_`
  payloads are distinct inputs. Unknown payload types are generic errors; they are never treated
  as paths, URLs, SQL, user identities or collaborator grants. Help uses safe static content.
- **Launch URL builder:** constructs URLs from trusted configured HTTPS origin and fixed routes,
  encoding a validated bounded URL-safe token as data. Create and collection are fixed entry
  intents, not user-supplied redirects. No external origin or arbitrary path can be selected by a
  payload. Preserve the existing direct-link `p_` and `i_` contract.
- **Mini App dispatcher:** normal entry and My wishlists reach the existing collection; create
  entry exposes an explicit create action rather than performing a write on navigation. Shared
  entry rechecks the token on every access and renders the established role-aware view for the
  authenticated viewer. Revocation, deletion or inaccessibility at any point shows the same
  localized recovery, with a path to normal menu. The share handoff must work both from `/start`
  and existing direct `startapp` links. Preserve the collaborator invitation acceptance path.
- **Auth and domain:** signed Telegram init data establishes identity through existing auth APIs;
  the wishlist service and its policy remain the sole authority for visibility, reservation
  and surprise protection. A public share capability grants only existing share access, not edit or
  membership rights. Never trust `initDataUnsafe` as authentication or reveal token or list details
  in failure messages, previews, logs, analytics or exception text.

### Interfaces and flow

- `handle_start(message, command, dependencies)` reads optional command arguments, returns a
  Telegram message and inline keyboard; it does not mutate wishlists or persist drafts. A help
  callback answers the callback and returns explanatory text. User-facing strings are RU/EN with
  fallback; all four actions remain accessible on error.
- The launch builder receives one of `home`, `create`, `collection` or `public(token)` and returns
  a WebApp button URL based on trusted settings. A target token is never interpolated into HTML
  or error copy. Telegram `/start p_<token>` is bounded to Telegram's 64-character start limit;
  the existing generated public token fits. Direct `startapp` keeps the existing format.
- The Mini App entry receives the fixed intent or share token, validates shape, authenticates
  when Telegram init data is present, then calls existing web/domain interfaces. Resolve a share
  capability at the point of use, including after launch, not just at bot entry; apply the same
  generic unavailable response for malformed, revoked, deleted, missing or inaccessible targets.
  Preserve no-onboarding public viewing, with authentication before identified actions and before
  rendering any role-sensitive data. Errors must not claim success.
- Creation is a separate explicit user action; no view, retry or repeated `/start` mutates lists.
  Transport errors and invalid configuration fail visibly without echoing secrets.

### Patterns and tradeoffs

Dependency injection permits fake Telegram transport and isolated stores in tests. A dedicated
polling process separates update ownership from web workers. A fixed intent allowlist and existing
capability policy avoid an open redirect and privilege escalation. The shared token retains existing
rotation semantics and has no invented expiry; deleted or revoked tokens naturally fail lookup.

## Q&A

- **Can the bot automatically open the Mini App?** No. It presents an explicit button; tapping it
  takes the user to the requested destination without a separate registration or onboarding.
- **Does opening a link create a collaborator?** No. Only the separate existing invitation flow can
  grant membership after explicit acceptance.
- **Why not use the existing public Mini App projection unchanged?** It is anonymous and omits
  reservation controls; it cannot establish recipient identity or satisfy the required giver flow.
- **What if access changes after the button is sent?** The Mini App and every protected operation
  re-evaluate the capability and authorization; a stale button cannot retain revoked rights.
