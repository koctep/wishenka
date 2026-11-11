# WISHENKA-51: Developer Documentation Updates

## Overview

This document summarizes the developer documentation updates made for Jira task WISHENKA-51:
"[Техдолг] Эндпоинты FastAPI и HTMX-представления для вишлистов и шеринга".

Primary documentation file updated:
- [`doc/dev/wishlists.md`](file:///home/src/doc/dev/wishlists.md)

## Summary of Documentation Updates

### 1. HTMX Web Endpoints (`wishenka.web.routes.sharing`)

Documented all server-rendered endpoints and HTMX partial routes in `doc/dev/wishlists.md`:

- `GET /share/{public_token}`:
  Public wishlist page rendering `share_wishlist.html`. Enforces the Surprise Invariant:
  for unauthenticated guests or non-recipient collaborators, displays availability and
  reservation status; for the recipient or personal owner, strictly hides all reservation
  details. Emits `wishlist_shared_view` with `wishlist_id`, `is_recipient`, and `is_collab`.
- `GET /wishlists/{wishlist_id}/items/{item_id}/card`:
  HTMX partial returning `partials/item_card.html` for atomic item card updates and
  out-of-band DOM swaps without full-page reloads.
- `GET /invite/{invite_token}`:
  Collaborator invitation preview rendering `invite_preview.html`. If the token is valid
  and active, renders wishlist details and a join button. If the token is invalid, expired,
  or from a deleted wishlist, returns a friendly error card with HTTP 200 rather than
  raw JSON errors. Emits `invite_preview_accessed`.
- `POST /invite/{invite_token}/join`:
  Accepts invitation for authenticated users, joins the user as `MEMBER`, and returns
  `HX-Redirect: /share/{public_token}` for seamless client-side navigation. Emits
  `invite_joined` or `invite_join_failed`.
- `GET /wishlists/{wishlist_id}/members/partial`:
  Renders `#member-list` partial (`partials/member_list.html`) listing owner and collaborators
  with role badges (`Администратор`, `Участник`). Accessible by list members.
- `DELETE /wishlists/{wishlist_id}/members/{user_id}/partial`:
  Owner-only endpoint to remove a collaborator and return the updated `#member-list`
  HTML partial. Emits `member_removed`.
- `GET /wishlists/{wishlist_id}/share-modal`:
  Owner-only drawer partial (`partials/share_modal.html`) displaying readonly public and
  invite link inputs with contextual guidance for gifters vs co-authors.
- `POST /wishlists/{wishlist_id}/invite/regenerate`:
  Owner-only endpoint to revoke the current invite token, generate a fresh token, and
  return the updated `#share-modal` partial via HTMX swap. Emits `invite_regenerated`.

### 2. Jinja2 Template Layout (`wishenka/web/templates/`)

Documented the server-side template structure and Jinja2 environment configuration:

- `wishenka/web/templates.py`:
  Centralized template engine configuration initializing `fastapi.templating.Jinja2Templates`
  pointing to `wishenka/web/templates/`.
- `wishenka/web/templates/base.html`:
  Master layout containing responsive meta viewport, Telegram WebApp SDK script
  (`telegram-web-app.js`), HTMX 1.9.12 runtime, and extensible Jinja2 blocks
  (`{% block title %}`, `{% block content %}`).
- `wishenka/web/templates/share_wishlist.html`:
  Full public wishlist page layout with header metadata and an items grid iterating
  over `wishlist.items` via `partials/item_card.html`.
- `wishenka/web/templates/invite_preview.html`:
  Dual-state invitation page displaying either an invitation acceptance card with an
  HTMX join form or a user-friendly error card with navigation back to `/`.
- `wishenka/web/templates/partials/item_card.html`:
  Modular gift item card (`id="item-card-{{ item.id }}"`) displaying title, price,
  quantity, link, and reservation indicators guarded by `item.is_recipient`.
- `wishenka/web/templates/partials/member_list.html`:
  Reactive collaborator list (`id="member-list"`) with role badges and owner `hx-delete`
  removal triggers.
- `wishenka/web/templates/partials/share_modal.html`:
  Modal dialog partial (`id="share-modal"`) displaying shareable links and `hx-post`
  regeneration trigger.

### 3. Surprise Invariant Guarantees in Server-Rendered Templates

Documented the multi-tier enforcement of the Surprise Invariant in web templates:

- Domain projection separation: `WishlistService.get_wishlist_by_public_token` and
  `get_wishlist_view` project recipient items to `WishItemRecipientViewDTO` which completely
  omits reservation counts, statuses, and gifter details.
- Template-level conditional guards: in `partials/item_card.html`, reservation badges
  (`badge-reserved`, `badge-my-reserved`, `badge-available`) are strictly wrapped in
  `{% if not item.is_recipient %}`.
- Zero-leak DOM guarantee: for recipients and list owners, no reservation-related elements,
  classes, or data attributes are rendered into the HTML document.
- Token isolation: `invite_token` is isolated exclusively to the owner share modal and is
  never exposed in public share views or item partials.
- Log sanitization: `ShareTokenAccessFilter` and `RequestLoggingMiddleware` sanitize
  `/share/{token}` and `/invite/{token}` in access and application logs.

### 4. Structured Observability and Audit Logging

Added reference entries for new sharing events in `doc/dev/wishlists.md`:
- `wishlist_shared_view` (`INFO`): Public share view rendered (`wishlist_id`, `is_recipient`).
- `wishlist_shared_view_failed` (`WARNING`): Lookup failed on public token.
- `invite_preview_accessed` (`INFO`): Invite preview accessed (`wishlist_id`, `status`).
- `invite_joined` (`INFO`): Collaborator joined via invite (`wishlist_id`, `user_id`, `role`).
- `invite_join_failed` (`WARNING`): Collaborator onboarding failed.
- `invite_regenerated` (`INFO`): Invite token regenerated (`wishlist_id`, `user_id`).

## Verification Checklist

- [x] HTMX web endpoints documented (`/share/{token}`, `/invite/{token}`, partials).
- [x] Jinja2 template architecture and layout documented (`wishenka/web/templates/`).
- [x] Surprise Invariant server-rendered template guarantees documented.
- [x] Audit logging events and access log redaction documented.
- [x] All lines in `doc/dev/wishlists.md` and `70-dev-docs.md` strictly <= 100 characters.
