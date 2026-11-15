# WISHENKA-24: Receipt Screen and «Подаренные» Section in the Mini App (Architecture)

Implementation language (from `00-roadmap.md`): Python 3.12+ (FastAPI page routes, Jinja2),
JavaScript (classic static scripts, no inline JS), CSS. Python rules: `lsr-python`; JavaScript
rules: `lsr-javascript` (JSDoc, `const`/`let`, `===`, no inline code); Markdown: `lsr-markdown`.

This document designs only the page layer of the Mini App. It changes no domain rule, storage,
migration, notice path or JSON route of WISHENKA-23 (N-6, DoD 15). Inputs: `10-requirements.md`
(U-1 to U-21, N-1 to N-8, DoD 1 to 16, C-1 to C-13, UA-1 to UA-6), `doc/dev/gift-receipt.md`,
`ai-tasks/WISHENKA-23/20-architecture.md` section 6, `ai-tasks/WISHENKA-22/` (plan for 24,
`50-observability.md`, `60-tech-debt.md`).

## Research

All facts below were verified in the code at HEAD `7fb5503`.

### Real UI code

- **Routes.** `wishenka/web/routes/items_ui.py` (router prefix `/web/wishlists/{wishlist_id}`,
  logger `wishenka.web.items_ui`) holds the wish page `GET ""` (`view_wishlist_detail`), the edit,
  archive-confirm, archive, restore, move and reorder routes. Every domain call goes through
  `_execute(request, action)`: it runs `action(svc)` on `app.state.wishlist_service` when injected
  (tests) or `app.state.wishlist_store.execute(action)` (one `BEGIN IMMEDIATE` full-snapshot
  transaction). `store.execute` maps a lock timeout to `InventoryBusyError` as well
  (`_raise_for_storage_error`, called from `execute` with no wish scope), so busy is observable on
  the snapshot path. Items are projected per viewer by `project_wish_item(item, user)`
  (recipient view for the owner of a personal list and for `recipient_user_id`, otherwise the
  gifter view, which also has `remaining_quantity` and `is_fully_received`).
- **Card route.** `sharing.py::get_item_card_partial` (`GET /wishlists/{id}/items/{item}/card`)
  renders `partials/item_card.html` from `get_wishlist_view`, so a wish that is not `is_active`
  gives a plain FastAPI 404 with the JSON body `{"detail": "Item not found"}`.
- **Page template.** `wishlist_detail.html`: header, `#items-list` (`data-wishlist-id`),
  `archived_items_section.html` guarded by `can_edit_wishlist`, `#item-modal-container`, quick
  add. `can_edit_wishlist = WishlistAccessPolicy.can_add_or_edit_item(ctx, wl)` = member AND list
  ACTIVE, so it is false for members of an archived list. The «Подаренные» section therefore needs
  its own flag (U-12): `WishlistAccessPolicy.can_view_gifted(ctx, wl)` (member of a non-deleted
  list).
- **Card template.** `partials/item_card.html`: summary badges (`×M` when `quantity > 1`), a giver
  block for `not item.is_recipient`, details panel with `Количество: M`, author actions
  (`btn-edit-item`, `btn-move-up/down`, `btn-archive-confirm`) only under `can_edit_wishlist`. It
  is rendered by the page, `sharing.py` (card route), the share page and four `items_ui` handlers
  (`_editor_card_flags()` supplies `viewer_identified`, `wishlist_active`).
- **Modals.** The author opens a modal with a `<button hx-get=".../edit" hx-target=
  "#item-modal-container" hx-swap="innerHTML">`; the modal root is a `div.modal-backdrop` carrying
  Tailwind-style classes (no Tailwind is loaded: `miniapp.css` has no `.modal-backdrop` rule, so
  existing modals are unstyled blocks at the end of the page). Closing is an inline
  `onclick="document.getElementById('item-modal-container').innerHTML = ''"` (six inline handlers
  in three partials, WISHENKA-140). Forms use `hx-post` with `hx-swap="none"` plus
  `hx-swap-oob` fragments (archive, quick add): `<div id="item-modal-container"
  hx-swap-oob="innerHTML"></div>` closes the modal.
- **CSRF.** The inline script of `base.html` fetches `/api/auth/csrf` once and adds
  `X-CSRF-Token` in a document-level `htmx:configRequest` listener for every non-GET htmx request
  (also `htmx.ajax`, which dispatches the same event). `BrowserSecurityMiddleware` enforces it for
  cookie sessions. Bearer sessions need no token.
- **Errors in forms.** There is no `htmx.config` override and no `htmx:beforeSwap` error handling
  (only `wishlist.js` cancels a touch drag on `beforeSwap`). htmx 1.9 does not swap 4xx/5xx
  responses by default (documented: v1.htmx.org/docs, `htmx:beforeSwap` with
  `detail.shouldSwap` and `detail.isError`). Consequence: the 409/503 modal re-render of
  `submit_edit_item` (documented in `miniapp.md` 9.6) is never shown by a real htmx 1.9.12, and
  `archive`/`restore` 409 (`NothingRemainingError`) and reorder 400 are silent today (issue 1
  below).
- **Card refresh defect (U-19).** The inline script of `base.html` handles `htmx:afterRequest` for
  giver actions: after a reservation action it `fetch`es the card route and calls the global
  `swapWishCard(card, markup)` with `response.text()` whatever the status, so a 404 body
  `{"detail":"Item not found"}` ends up in the card. `swapWishCard` is a global function
  declaration, so a script that runs later (`defer`) can wrap `window.swapWishCard`.
- **Static scripts.** `wishlist.js` (IIFE, delegated listeners, JSDoc). A test pins exactly one
  non-comment `htmx.ajax(` in it (`tests/test_wishlist_touch_reorder.py`, "Guard (green by
  design)"), so a second `htmx.ajax` call cannot go into that file (design decision 5).
- **Cabinet.** `reservations_ui.CabinetRow` already has `wish_received` and
  `offer_actions`; `partials/reservations_list.html` renders neither a marker nor a link rule
  (`<a href=wish_href>К желанию</a>` is unconditional).
- **Test infrastructure.** Browser tests run real Chromium over CDP (`tests/browser_cdp.py`,
  `browser_helpers.py`, `conftest.py` fixtures `seed_wishlist`, `wishlist_page`, `share_page`,
  Bearer auth, external scripts replaced by `tests/browser_assets/htmx_stub.js`). The stub
  implements only `htmx.ajax(verb, url, {target, swap, values})` with an unconditional
  `innerHTML` swap; it ignores `hx-*` attributes, `swap: 'none'`, OOB fragments, response status
  and `hx-swap-oob`. Tests start htmx flows by calling `htmx.ajax` themselves.
- **Observability.** `items_ui` UI events are `ui_*` on `wishenka.web.items_ui` with
  `wishlist_id`, `item_id`, `actor_id`, `user_id`. The JSON receipt route logs on
  `wishenka.web.receipts`: `receipt_recorded_http` (`item_id`), `receipt_refused`
  (`operation`, `wishlist_id`, `item_id`, `actor_id`, `reason`, `http_status`,
  `remaining_quantity` for two reasons), `receipt_inventory_busy`.

### External facts checked (htmx 1.9 documentation)

- 4xx and 5xx responses are not swapped; `htmx:beforeSwap` may set `detail.shouldSwap = true` and
  `detail.isError = false`.
- `hx-swap="none"`: out-of-band swaps are still processed.
- `hx-swap-oob="<swap>:<selector>"` swaps into the matching target (`true`/`outerHTML` replaces
  the element inline).
- `htmx.ajax(verb, path, {source, event, handler, target, swap, values, headers, select})` returns
  a Promise that resolves after `htmx:afterOnLoad`.

Verified in the htmx 1.9.12 source (CDN script, no copy in the repo; checked by the reviewer):
4xx and 5xx are not swapped by default; `detail.shouldSwap` and `detail.isError` of
`htmx:beforeSwap` are writable and `isError` is read back after the event; `htmx:responseError`
fires only if `isError` is still true; OOB is handled in `selectAndSwap` before the swap and
`swap: 'none'` still processes OOB; `htmx.ajax` returns a Promise. Residual: the real htmx cannot
run in the offline test suite (the stub emulates the documented contract), so the real-htmx
behaviour is covered by markup assertions and the stub only.

## Design Decisions

1. **New page-route module `wishenka/web/routes/receipts_ui.py`** (router prefix
   `/web/wishlists/{wishlist_id}`, logger `wishenka.web.receipts_ui`), mounted in `create_app`
   right after `items_ui_router`. `items_ui.py` already has 1104 lines and WISHENKA-158 wants
   receipt code out of big modules. It imports `_execute`, `_editor_card_flags`,
   `_items_list_html`, `_archived_section_html` from `items_ui` (same package, shared helpers; no
   rename, so existing tests that import `items_ui` names stay valid). `items_ui` must not import
   `receipts_ui` (no cycle); the shared view-model code lives in a third module
   `wishenka/web/gifted_view.py`, which also exports the two constants both modules need
   (`RECEIPT_REFUSAL_HEADER = "X-Receipt-Refusal"` and `NOTHING_REMAINING_TEXT`), so there is no
   duplicated literal and no cycle.
2. **Full-snapshot path, one transaction per request** (`_execute`, as 23 section 6 says). It is
   required, not a style choice: the success response needs the new card or list, and the gifted
   section, from the same committed state; `execute_wish` loads one wish only. Busy still arrives
   as `InventoryBusyError`. Ownership of rules stays in `record_item_fulfillment`; the route only
   maps its closed refusals.
3. **One refusal table, no copy.** `receipts_ui` reads `_REFUSALS` (exception class, HTTP status,
   reason, English message) from `wishenka/web/routes/receipts.py` and uses only the first three
   columns, so «same refusal class gives the same closed reason» holds by construction. The
   English message is never rendered. A test fails if a class in the table has no Russian
   sentence (and so if WISHENKA-158 changes the table).
4. **Refusals are real HTTP statuses with a receipt-specific marker header.** Responses use the
   statuses of the JSON contract (400, 403, 404, 409, 503) and the header
   `X-Receipt-Refusal: <closed reason>`. The header is emitted only by three producers whose body
   is a server HTML fragment built for out-of-band application: the receipt GET and POST routes
   (`receipts_ui.py`) and the stale archive and restore responses (`items_ui`, P15). `receipt.js`
   handles `htmx:beforeSwap` and overrides (`shouldSwap = true`, `isError = false`, both writable
   in htmx 1.9.12 and read back after the event) only when the header value is in the closed set
   of receipt reasons (the `_REFUSALS` reasons plus `busy`); any other value, and any response
   without the header, is left to htmx. Why this is safe: the reorder 400 has a JSON body and must
   never be swapped into `#items-list`, so it carries a different header in a different namespace,
   `X-Reorder-Refusal: stale_order` (decision 11), which no override reads; the override cannot
   fire for it by construction, and a red test pins that (T-3 header test, B-6). Simplest robust
   option chosen over (a) an explicit `stale_order` exclusion (fragile: every new marker needs an
   exclusion) and (b) an HTML OOB body for stale reorder (changes a pinned JSON body and widens the
   story). Alternative rejected: return 200 for refusals; it hides outcomes from access logs and
   from the `http_status` log field.
5. **New static script `wishenka/web/static/receipt.js`**, loaded by `base.html` with
   `<script src="/static/receipt.js" defer></script>` after `wishlist.js`. Reasons: the
   existing guard allows one `htmx.ajax(` call in `wishlist.js`; `wishlist.js` has 538 lines; the
   receipt behaviour is a separate concern. `receipt.js` contains exactly one `htmx.ajax(` call.
   The inline script of `base.html` is not edited (N-2). No test pins its length today; T-6 adds a
   snapshot check: the SHA-256 of the inline script text equals a constant recorded in Step 3 from
   HEAD `7fb5503` (changes only with WISHENKA-140).
6. **Script-driven submit, not `hx-post` on the form.** The in-flight guard (U-4, DoD 4) is a MUST
   and must be proven in the real browser, while the offline stub implements only `htmx.ajax`.
   `receipt.js` handles `submit` on `form[data-receipt-form]`, calls
   `htmx.ajax('POST', form.action-path, {target: '#receipt-feedback', swap: 'none', values:
   {quantity}})`. The same real-htmx path adds the CSRF header (the `htmx:configRequest` listener
   sees the event), so no second CSRF path exists (TD-2.5, N-3). The form carries no `hx-*`
   attribute (htmx would submit it a second time).
7. **Server-rendered fragments for every outcome**, all out of band (`hx-swap="none"` style):
   modal close, card or list, «Подаренные», notice. The success response is `201`.
8. **Card refresh fix (U-19) in `wishlist.js` by wrapping `window.swapWishCard`**: the wrapper
   accepts the markup only when its root element is `.item-card` with the same `id` as the card
   (content check, independent of the status); otherwise it replaces the card by a neutral
   element created with `textContent`. This also covers the SHOULD part (any failed refresh).
   The inline script does not grow. When WISHENKA-140 moves the inline code, the wrapper folds
   into it.
9. **No JSON route and no new gifted HTML route.** The section is rendered on page load and
   refreshed by the receipt response (out of band). A separate `GET .../gifted` HTML route would
   be dead code. The U-15 failure text is shown when the read inside the same action raises a
   domain error (fail-soft), see section «Templates» (`gifted_items_section.html`).
10. **View models in Python, copy in templates.** Dates are formatted in
    `gifted_view.py` (UTC calendar day `dd.mm.yyyy`), texts live in templates, refusal sentences
    in one dict in `receipts_ui.py`.
11. **Stale reorder keeps its error semantics.** The reorder 400 stays an HTTP error with the JSON
    body `{"detail": "Invalid item order"}` and gets the header `X-Reorder-Refusal: stale_order`.
    htmx 1.9.12 does not swap it (default), fires `htmx:responseError` (`isError` stays true), and
    `wishlist.js` handles that event with a listener registered on `document` (U-11): notice in `#list-notice`, reload. Nothing in
    `receipt.js` touches it. Move up/down (`hx-target="#items-list"`) and drag
    (`htmx.ajax(... target '#items-list' ...)`, `wishlist.js:112`) share this behaviour, so
    `#items-list` is never replaced by the error text.

## Architecture

### Component diagram

```mermaid
flowchart LR
    subgraph Browser
        Page["wishlist_detail.html (members)"]
        Wl["wishlist.js (wrap swapWishCard, stale reorder)"]
        Rc["receipt.js (modal, submit guard, beforeSwap marker)"]
        Inline["base.html inline script (unchanged)"]
    end
    subgraph Routes["wishenka/web/routes"]
        RU["receipts_ui.py: GET/POST .../items/{id}/receipt"]
        IU["items_ui.py: page, archive, restore, reorder"]
        SH["sharing.py: card route"]
        RES["reservations_ui.py: cabinet"]
        REC["receipts.py: JSON route (unchanged, _REFUSALS read-only)"]
    end
    GV["web/gifted_view.py: GiftedRow, build_gifted_rows"]
    Svc["WishlistService via WishlistStore.execute (full snapshot)"]
    Page -->|hx-get receipt| RU
    Rc -->|htmx.ajax POST (CSRF via inline listener)| RU
    RU --> Svc
    IU --> Svc
    IU --> GV
    RU --> GV
    RU -.reads table.-> REC
    Inline -->|fetch card| SH
    Wl -.wraps.-> Inline
    RES --> Svc
```

### Modules and responsibilities

| Module | Responsibility | New or changed |
| ------ | -------------- | -------------- |
| `wishenka/web/routes/receipts_ui.py` | GET receipt modal, POST receipt, reason to Russian sentence mapping, logging of each outcome, OOB fragment assembly | new |
| `wishenka/web/gifted_view.py` | `GiftedAct`, `GiftedRow`, `build_gifted_rows(dtos)`, `utc_day(value)`, `read_gifted_rows(svc, wishlist_id, user)` (fail-soft read), `RECEIPT_REFUSAL_HEADER`, `NOTHING_REMAINING_TEXT` | new |
| `wishenka/web/routes/items_ui.py` | page route adds `is_member`, gifted rows (fail-soft); `_editor_card_flags` adds `is_member`; archive-confirm context; `nothing_remaining` HTML response on archive and restore; header `X-Reorder-Refusal` on stale reorder | changed |
| `wishenka/web/routes/sharing.py` | card route passes `is_member` | changed (1 line) |
| `wishenka/web/routes/reservations_ui.py` | no change (`wish_received`, `offer_actions` exist) | unchanged |
| `wishenka/web/app.py` | `include_router(receipts_ui_router)` | changed (2 lines) |
| `templates/partials/item_receipt_modal.html` | receipt dialog | new |
| `templates/partials/gifted_items_section.html` | «Подаренные» section (also OOB) | new |
| `templates/partials/item_card.html` | badges, details, «Получено» button, giver guard, `card_oob` root attribute | changed |
| `templates/partials/archived_items_section.html`, `item_archive_modal.html` | «Осталось N», archive text for a received part | changed |
| `templates/partials/reservations_list.html` | marker, link omission | changed |
| `templates/wishlist_detail.html` | `#list-notice`, gifted section | changed |
| `templates/base.html` | one `<script src defer>` tag | changed (1 line, no inline code) |
| `static/receipt.js` | modal behaviour, submit guard, feedback reset, refusal marker override (guarded) | new |
| `static/wishlist.js` | `swapWishCard` wrapper, stale reorder notice | changed |
| `static/miniapp.css` | receipt dialog, gifted section, notice styles | changed |

### Routes

Both routes use `get_current_user` (401 JSON without credentials), live under the existing CSRF
middleware, and are page routes of the Mini App (HTML in, HTML out).

| Method and path | Auth | CSRF | Request | Response |
| --------------- | ---- | ---- | ------- | -------- |
| `GET /web/wishlists/{wishlist_id}/items/{item_id}/receipt` | session or Bearer, member | none (GET) | none | 200 `partials/item_receipt_modal.html` (form) or, for a member with a stale card, the same dialog in blocked state (see below) |
| `POST /web/wishlists/{wishlist_id}/items/{item_id}/receipt` | session or Bearer | `X-CSRF-Token` for cookie sessions | form field `quantity` (string), nothing else is read | 201 OOB fragments, or a refusal (below) |

`quantity` is declared `Annotated[str, Form()] = ""` and parsed in the route
(`int(value.strip())`); a non-integer raises `QuantityInvalidError()` inside the same mapping, so
`"abc"`, `""` and `"3.0"` give the closed reason `quantity_invalid` (U-8 first row) instead of a
FastAPI 422. An unknown extra field is ignored (the route reads only `quantity`); the JSON route
stays the strict one.

#### POST: calling the service (one transaction)

```python
async def action(svc: WishlistService) -> ReceiptOutcome:
    item = await svc.record_item_fulfillment(item_id, user, quantity, wishlist_id=wishlist_id)
    shown = project_wish_item(item, user)            # recipient or gifter view of the viewer
    ordered = await svc.list_wish_items(wishlist_id=wishlist_id, actor=user)
    gifted = await read_gifted_rows(svc, wishlist_id, user)    # fail-soft, rows or None
    return ReceiptOutcome(item=shown, ordered_ids=[i.id for i in ordered], ..., gifted=gifted)
```

`record_item_fulfillment` keeps all guards (membership first, then list, wish, quantity,
remaining). The route adds none. `read_gifted_rows` (in `gifted_view.py`) catches `WishlistError` only, returns `None`,
and the template shows the U-15 failure text.

#### POST success (201)

Body: no main content, only out-of-band fragments (the form posts with `swap: 'none'`):

| Fragment | Markup | When |
| -------- | ------ | ---- |
| close dialog | `<div id="item-modal-container" hx-swap-oob="innerHTML"></div>` | always |
| notice | `<div id="list-notice" hx-swap-oob="innerHTML">…</div>` with «Отмечено получено: K шт. («Title»)» (K from the act, title autoescaped) | always |
| card | `item_card.html` rendered with `card_oob=True` (root gets `hx-swap-oob="true"`), `is_first`/`is_last` from the new order, `can_edit_wishlist=True`, `is_member=True`, `_editor_card_flags()` | partial receipt (remaining > 0) |
| list | `<div hx-swap-oob="innerHTML:#items-list">` + `items_list.html` (so first/last flags and the empty-list text are right; the container itself is not re-emitted) | full receipt |
| gifted | `gifted_items_section.html` with `oob=True` | always |

The recipient of the wish gets the recipient view (`project_wish_item`), so no booking marker is
rendered (U-7, U-20).

#### POST and GET refusals

Mapping (reason from `_REFUSALS`, sentence from `receipts_ui._SENTENCES`; the statuses are those
of the JSON route):

| Reason | Status | Sentence (U-8) | Extra fragments |
| ------ | :----: | -------------- | --------------- |
| `quantity_invalid` | 400 | «Укажите целое число не меньше 1.» | none |
| `quantity_above_remaining` | 409 | «Нельзя отметить больше, чем осталось. Осталось: N.» (N from the exception) | card OOB with current data, and the dialog re-rendered OOB (`outerHTML` of `#item-receipt-modal`) with options up to the current remaining and the sentence in `#receipt-feedback` |
| `nothing_remaining` | 409 | «Это желание уже полностью получено.» | list OOB (card leaves), gifted OOB, and the dialog re-rendered OOB in blocked state (no form, «Закрыть»), so a POST `nothing_remaining` does not leave a dead form open |
| `wish_archived` | 409 | «Желание в архиве. Восстановите его, чтобы отметить получение.» | none |
| `wishlist_not_active` | 409 or 404 | «Вишлист не активен, отметить получение нельзя.» | none |
| `forbidden` | 403 | «У вас нет права отмечать получение в этом вишлисте.» | none |
| `not_found` | 404 | «Желание не найдено. Обновите страницу.» | none |
| `busy` (`InventoryBusyError`) | 503 | «Не удалось сохранить отметку сейчас. Повторите попытку.» | none |

Common body for the "none" rows: `<div id="receipt-feedback" hx-swap-oob="innerHTML">sentence
</div>` (the persistent `role="alert"` region, so the text is announced). Header on every refusal:
`X-Receipt-Refusal: <reason or busy>`. The extra fragments of the first two effect rows need
current data; the transaction of a refused act is rolled back, so the route does one more
read-only `_execute` (card or list, and gifted rows) through the helper `_effect_fragments`. That
read is best effort: it catches `WishlistError` and `InventoryBusyError` (a lock contention is
likely exactly when a refusal happens) and on failure the response degrades to the plain sentence
fragment of the "none" rows, without card, list, gifted or dialog fragments. The status, the
header and the sentence of the real refusal are never replaced by a 500 or a generic text. For
`quantity_above_remaining` the degraded dialog keeps its options (the sentence already names N);
for `nothing_remaining` the degraded dialog stays open with its form and the sentence (a retry
gives the same refusal; accepted).

Not-signed-in (401 JSON), CSRF failure (403 JSON from the middleware), 422, 500 and a network
error carry no marker and are not swapped; `receipt.js` shows the generic sentence «Не удалось
сохранить отметку. Повторите попытку.» by a post-condition check (the dialog is still open and
`#receipt-feedback` is empty; `receipt.js` empties the region when each attempt starts, so a
sentence from an earlier refusal or busy attempt cannot mask it), see the JavaScript section. No English text from any backend
response is ever placed in the page.

`GET` guards use the same exceptions in the service order (item not found, not a member, list
deleted or archived, wish archived, fully received) through `_check_receipt_open(wl, item, user)`
and the same table. They are advisory; the POST is the authority. Success: dialog with the wish
title and `remaining_quantity`. Refusal (a member with a stale card): 200-class statuses are not
used; the response has the contract status, the marker header and the dialog in blocked state
(feedback sentence, no form, button «Закрыть»). For `nothing_remaining` the GET adds the list and
gifted OOB fragments through the same `_effect_fragments` helper (U-8: the card leaves the list);
that extension is built in P13, so at P9 the blocked dialog for `nothing_remaining` is the plain
blocked dialog without OOB. GET busy (`InventoryBusyError` from the snapshot read) is 503 with
header `X-Receipt-Refusal: busy`, the neutral busy sentence in the blocked dialog, no fragments. A
non-member gets the `forbidden` or `not_found` dialog like on the JSON route (the inherited
contract distinguishes them). For every blocked dialog shown to a non-member (`forbidden`,
`not_found`) the route passes `item_title=""` and the template renders no title element, so
nothing about the wish content leaks; the title is passed only when the viewer is a member of the
list and the wish was found (blocked states `wish_archived`, `nothing_remaining`,
`wishlist_not_active` for members).

#### Logging of the UI path (N-7, DoD 16)

Logger `wishenka.web.receipts_ui`. Event names for the three attempt outcomes are the JSON
route's names, so metrics derived by event name (22 `wishlist_receipts_total`) cover both
channels; the channel is told apart by the logger name only. No `operation` field is written:
22's `50-observability.md` allows `wishlist_id`, `item_id`, `actor_id`, `reason`, `http_status`,
`remaining_quantity` (the last only for two reasons) and lists no `operation` for
`receipt_refused`, and N-7 says "fields allowed by 22". (The JSON route of 23 writes `operation`
and its `receipt_recorded_http` / `receipt_inventory_busy` are not in 22's table at all; they are
23's additions and are not changed. The UI records mirror their meaning and use only fields that
22 allows on `receipt_refused`.)

| Outcome | Level | Event | Fields (a subset of 22's `receipt_refused` list) |
| ------- | ----- | ----- | ------------------------------------------------ |
| accepted | INFO | `receipt_recorded_http` | `wishlist_id`, `item_id`, `actor_id` |
| refused | WARNING | `receipt_refused` | `wishlist_id`, `item_id`, `actor_id`, `reason`, `http_status`, `remaining_quantity` only for `quantity_above_remaining` and `nothing_remaining` |
| busy | WARNING | `receipt_inventory_busy` | `wishlist_id`, `item_id`, `actor_id` |
| dialog opened | INFO | `ui_receipt_form_opened` | `wishlist_id`, `item_id`, `actor_id` |
| dialog refused | WARNING | `ui_receipt_form_refused` | `wishlist_id`, `item_id`, `actor_id`, `reason`, `http_status`, `remaining_quantity` as for `receipt_refused` (own event name so the refusal-rate metric counts real attempts only) |

One record per outcome, written by the route after the action (the success record after the
commit). The service already writes `item_fulfilled` for an accepted act (unchanged). Never
logged: requested or received quantity, titles, the Russian or English text, the header, any
giver or reservation data, `user_id` (the notice-path join key; 23 uses `actor_id` only), the
`operation` key. Event names and fixed messages contain none of `notification`, `outbox`, `push`
(`_NOTICE_MARKS` of `tests/test_surprise_role_context.py`). The browser adds no logging of wish
or booking data; `receipt.js` writes nothing to the console.

Test interplay: `tests/test_receipt_observability.py` filters records by logger-name equality
with `wishenka.web.receipts`; the new logger `wishenka.web.receipts_ui` is deliberately not swept
into it (it is not a prefix match and stays so; that file is not edited). The UI events need
their own never-logged scan: `test_ui_logging_once_per_outcome` (T-2) is that scan (allowed field
set, no quantity, title, giver names, booking numbers, `user_id`, `operation`, notice words).
Step 6 verifies and documents this (plan pointer at the end).

### Templates

#### `partials/item_receipt_modal.html` (U-1 to U-4, N-4)

Context: `wishlist_id`, `item_id`, `item_title` (empty string for a non-member), `remaining`
(int), `feedback` (text or empty), `blocked` (bool), `selected` (int, default 1), `oob` (bool,
default false: the refusal responses re-render the dialog out of band).

```html
<div class="modal-backdrop receipt-backdrop" id="item-receipt-modal" data-receipt-modal
     {% if oob %}hx-swap-oob="outerHTML" {% endif %}role="dialog" aria-labelledby="receipt-title">
  <div class="modal-sheet receipt-sheet">
    <h2 id="receipt-title">Отметить получение</h2>
    {% if item_title %}<p class="receipt-wish">{{ item_title }}</p>{% endif %}
    {% if not blocked %}<p class="receipt-remaining">Осталось: {{ remaining }}</p>{% endif %}
    <div id="receipt-feedback" class="receipt-feedback" role="alert">{{ feedback }}</div>
    {% if blocked %}
      <button type="button" class="btn-modal-close" data-modal-close>Закрыть</button>
    {% else %}
    <form data-receipt-form method="post"
          action="/web/wishlists/{{ wishlist_id }}/items/{{ item_id }}/receipt">
      {% if remaining > 1 %}
      <label for="receipt-quantity">Сколько штук получено</label>
      <select id="receipt-quantity" name="quantity" data-receipt-quantity
              data-remaining="{{ remaining }}">
        {% for n in range(1, remaining + 1) %}
        <option value="{{ n }}"{% if n == selected %} selected{% endif %}>{{ n }}</option>
        {% endfor %}
      </select>
      <p class="receipt-summary" data-receipt-summary aria-live="polite">
        Будет отмечено получено: {{ selected }} шт. из {{ remaining }} оставшихся</p>
      {% else %}
      <input type="hidden" name="quantity" value="1">
      <p class="receipt-summary" data-receipt-summary>Будет отмечено получено: 1 шт.</p>
      {% endif %}
      <p class="receipt-final">Это действие нельзя отменить.</p>
      <button type="submit" class="btn-receipt-confirm">Отметить полученным</button>
      <button type="button" class="btn-modal-close" data-modal-close>Отмена</button>
    </form>
    {% endif %}
  </div>
</div>
```

- No inline handler, no inline script, no inline style. The dialog holds only the wish title, the
  remaining quantity and the chosen quantity: no giver, promise, booking or free-quantity field
  (the route passes nothing else to the template, so none can render).
- Real `<select>`, `<label for>`, `<button>`: keyboard operable and labelled (N-4). The hidden
  input for remaining 1 shows no choice (U-3). `role="alert"` on the persistent region announces
  refusals. `aria-modal` is deliberately not set (no focus trap is built; SHOULD part).
- `selected` is clamped to `[1, remaining]` by the route. With `oob` true the root carries
  `hx-swap-oob="outerHTML"` and replaces `#item-receipt-modal` in place; the GET and the plain
  states render it without the attribute.

#### `partials/gifted_items_section.html` (U-12 to U-16)

Context: `gifted_rows` (list of `GiftedRow` or `None`), `oob`. It always renders the container
`<section id="gifted-items-section"[ hx-swap-oob="outerHTML"]>` (as the archive section does) and
inside it:

- `gifted_rows is none`: `<p class="gifted-error" role="status">Не удалось загрузить «Подаренные».
  Обновите страницу.</p>` (U-15 failure; active list untouched).
- `gifted_rows` empty: nothing (hidden when empty, UA-2).
- otherwise `<details class="gifted-items-details"><summary>Подаренные ({{ rows|length }})
  </summary><ul id="gifted-items-list">` with, per row, `li.gifted-item#gifted-item-{id}`: title,
  price with currency when set, `Для: name` when set, `Получено: K из M`, and
  `ul.gifted-receipts` with one `li` per act: `{day} — {quantity} шт.`; for an approximate act
  `≈ {day} (дата примерная) — {quantity} шт.`.
- No `button`, `form`, `a` or `hx-*` attribute inside the section (U-14); no reservation or
  giver data (the rows are built from `GiftedItemDTO`, which has none). Description and store
  link are not shown. The section is collapsed by default like the archive section; a swap after
  a receipt re-collapses it (accepted, see Issues).

Order of entries and acts is the order of `list_gifted_items` (newest receipt first; acts oldest
first); the view model does not re-sort.

`gifted_view.py`:

```python
@dataclass(frozen=True)
class GiftedAct:
    day: str            # dd.mm.yyyy, UTC calendar day
    quantity: int
    approximate: bool

@dataclass(frozen=True)
class GiftedRow:
    item_id: int
    title: str
    price: str | None   # "1500 RUB"
    recipient_name: str | None
    received: int
    requested: int
    acts: tuple[GiftedAct, ...]

def utc_day(value: datetime) -> str: ...        # naive means UTC, as reservations_ui._event_day
def build_gifted_rows(items: list[GiftedItemDTO]) -> list[GiftedRow]: ...
async def read_gifted_rows(svc, wishlist_id: int, user) -> list[GiftedRow] | None:
    """list_gifted_items + build_gifted_rows; WishlistError -> None (fail-soft, U-15)."""
```

#### Page: `wishlist_detail.html` and `view_wishlist_detail`

- The action additionally returns `is_member = ctx.is_member` and, when
  `WishlistAccessPolicy.can_view_gifted(ctx, wl)`, `gifted_rows` (fail-soft as above), else
  `gifted_rows` is absent and the section is not included. Context adds `is_member`,
  `can_view_gifted`, `gifted_rows`.
- Template: inside `{% if is_member %}` an empty `<div id="list-notice" role="status"
  aria-live="polite"></div>` above `#items-list` (target of confirmation and refusal notices).
  Below `#items-list`: `{% if can_view_gifted %}{% include gifted section %}{% endif %}`, then the
  existing archive section (still `can_edit_wishlist`; the archive must not become visible on an
  archived list, that is existing behaviour). `can_edit_wishlist` is not used for «Подаренные», so
  members of an archived list see it (U-12, DoD 5). Non-members, givers, anonymous and share-page
  viewers get neither the section nor any count (`share_wishlist.html` is not touched).

#### Owner card: `partials/item_card.html` (U-1, U-7, U-19)

New context variable `is_member` (True from `_editor_card_flags()`, `ctx.is_member` on the page
and on the card route, absent on the share page, so public views are unchanged, U-21).

- Badge: `{% if is_member and item.received_quantity > 0 %}<span class="badge badge-quantity
  badge-received">Осталось {{ item.remaining_quantity }} из {{ item.quantity }}</span>{% elif
  item.quantity > 1 %}` existing `×M` `{% endif %}`.
- Details: when `is_member and item.received_quantity > 0` three spans
  `.item-quantity-requested` «Запрошено: M», `.item-quantity-received` «Получено: K»,
  `.item-quantity-remaining` «Осталось: N»; otherwise the existing `span.item-quantity`.
- Button in the existing `.item-actions` block (so only under `can_edit_wishlist`: member on an
  active list; never for givers, anonymous, archived lists): `<button type="button"
  class="btn-receipt-item" data-no-toggle hx-get="{{ item_web }}/receipt" hx-target=
  "#item-modal-container" hx-swap="innerHTML">Получено</button>`, rendered when
  `item.remaining_quantity > 0`. Cards in the list are active by construction; archived wishes
  are not cards. It is a native `<button>` (keyboard operable; text label). `.item-actions` sits in the collapsed
  details area of the card, so the owner expands the card first (as for edit, move and archive);
  accepted, not changed.
- Giver guard: `can_promise` also requires `not item.is_fully_received` (the attribute exists on
  the gifter view only; undefined is falsy on the recipient view). A fully received wish never
  reaches a giver card today (projection omits it), so this is defence in depth; the observable
  defect is the raw error body (decision 8).
- Root `div.item-card`: `{% if card_oob %} hx-swap-oob="true"{% endif %}`.
- Cards with nothing received render exactly as today.

#### Archive section and modal (U-10)

- `archived_items_section.html`: per row `{% if item.received_quantity > 0 %}<span
  class="archived-item-remaining">Осталось {{ item.remaining_quantity }}</span>{% endif %}`
  after the title. The section is still fed by `archived_items` (`is_in_archive` wishes only), so
  a received wish never appears whole (U-16). Its gating by `can_edit_wishlist` is unchanged.
- `item_archive_modal.html`: a second paragraph when the context flag `has_received` is true
  (set in `archive_confirm_ui` from `item.received_quantity > 0`): «Архивируется только
  неполученная часть: полученные штуки останутся в разделе «Подаренные».» (new wording, meaning
  fixed by U-10).
- Restore: `restore_item_ui` already renders the card; with the card changes it shows the
  remaining quantity. «Подаренные» is not part of its response (unchanged, DoD 8).
- Stale archive or restore of a fully received wish (`NothingRemainingError`): `items_ui`
  replaces `_raise_nothing_remaining` in the two handlers by `_nothing_remaining_response(...)`:
  status 409, header `X-Receipt-Refusal: nothing_remaining`, body OOB fragments: close dialog,
  `#list-notice` with «Это желание уже полностью получено.», `innerHTML:#items-list` with the
  refreshed list, the archive section and the gifted section (one extra read-only `_execute`).
  Every top-level element of the body carries `hx-swap-oob` (restore targets `#items-list` with
  `beforeend`, the edit-modal archive targets the card with `outerHTML`, so non-OOB content would
  be swapped into the list or card); all fragments are Jinja-rendered (autoescape).
  The JSON route and the status are unchanged; the old 409 body of the HTML routes was only the
  fixed English sentence and no test asserts it (`test_archive_restore_routes_nothing_remaining`
  checks the status only).

#### Cabinet: `partials/reservations_list.html` (U-17, U-18)

- After `.reservation-status`: `{% if row.wish_received %}<p class="reservation-wish-received">
  Желание получено владельцем</p>{% endif %}` (shown on active and archived lists; no quantity,
  no wording about excess or other givers; a purchased promise keeps «Куплено»).
- `<a href="{{ row.wish_href }}">К желанию</a>` only `{% if not row.wish_received %}`.
- Actions block unchanged (`offer_actions` already covers a received wish on an active list and
  hides actions on an archived list). The inline cabinet refresh in `base.html` is unchanged.

### JavaScript (static scripts only)

#### `receipt.js` (new, IIFE, JSDoc, delegated listeners on `document`)

| Behaviour | Mechanism |
| --------- | --------- |
| Chosen quantity line (U-3) | `change` on `[data-receipt-quantity]` rewrites `[data-receipt-summary]` with `textContent`: «Будет отмечено получено: K шт. из N оставшихся» (N from `data-remaining`) |
| Submit and in-flight guard (U-4, DoD 4) | `submit` on `form[data-receipt-form]`: `preventDefault`; if `form.dataset.pending === 'true'` return; set it, disable the submit button, `aria-busy`; **empty `#receipt-feedback` (`textContent = ''`) as the first act of the attempt**; call `window.htmx.ajax('POST', path, {target: '#receipt-feedback', swap: 'none', values: {quantity}})`; `Promise.resolve(result).then(done, done)`; `done` re-enables the button when the form is still in the document (the `<select>` value is never touched, so the chosen quantity survives), and runs the post-condition check below. Only `quantity` is sent |
| Generic failure (U-8 last row) | in `done`: if the form is still in the document and `#receipt-feedback` is empty (it was emptied at the start of this attempt, so only a response of this attempt can have filled it), set its `textContent` to the fixed sentence «Не удалось сохранить отметку. Повторите попытку.» (covers 401, 403 CSRF, 422, 500, network error, any unmarked response, also directly after a refusal or busy sentence of an earlier attempt) |
| Refusal marker (decision 4) | `htmx:beforeSwap`: guard first, `if (!detail || !detail.xhr || typeof detail.xhr.getResponseHeader !== 'function') return;` (the existing offline stub dispatches `htmx:beforeSwap` with `detail = {target}` and no `xhr`, and `receipt.js` loads on every page, including the existing 53 browser tests); then read `X-Receipt-Refusal`; only when the value is in the closed set of receipt reasons (`_REFUSALS` reasons plus `busy`) set `detail.shouldSwap = true; detail.isError = false`. A response without the header, with another value, or the reorder response (`X-Reorder-Refusal`) is untouched. Also makes the stale archive and restore responses visible |
| Dismissal (N-4) | click on `[data-modal-close]` and `Escape` (when `#item-receipt-modal` exists) empty `#item-modal-container` (`replaceChildren()`), no request; focus returns to the opener card summary when it still exists |
| Focus (SHOULD) | `htmx:afterSwap` with target `#item-modal-container` and a `[data-receipt-modal]` inside: focus `[data-receipt-quantity]` or `.btn-receipt-confirm` or `[data-modal-close]` |
| Opener tracking | `click` on `.btn-receipt-item` remembers the card id |

No `innerHTML` of server text, no `eval`, no inline handler, no console output, no new
third-party script. Exactly one `htmx.ajax(` call (the guard in `wishlist.js` keeps counting one
there).

#### `wishlist.js` additions

- `swapWishCard` wrapper (U-19), run at load (after the inline script defined the global):

  ```javascript
  const original = window.swapWishCard;
  window.swapWishCard = (card, markup) => {
    const holder = document.createElement('template');
    holder.innerHTML = markup;
    const root = holder.content.firstElementChild;
    if (root && root.id === card.id && root.classList.contains('item-card')) {
      original(card, markup);
      return;
    }
    const gone = document.createElement('p');
    gone.className = 'item-card-unavailable';
    gone.setAttribute('role', 'status');
    gone.textContent = 'Желание больше недоступно. Обновите страницу.';
    card.replaceWith(gone);
  };
  ```

  Guarded: when `original` is not a function the wrapper is not installed. The text does not say
  why (UA-6).
- Stale reorder (U-11, SHOULD): `htmx:responseError` handler, guarded
  (`detail && detail.xhr && typeof detail.xhr.getResponseHeader === 'function'`, the same guard as
  in `receipt.js`, so the stub's `{target}`-only events are ignored), acts only when
  `getResponseHeader('X-Reorder-Refusal') === 'stale_order'`: writes «Список изменился.
  Обновляем.» into `#list-notice` (`textContent`) and calls `window.location.reload()` after a
  short delay. It works because the 400 is not swapped and `isError` stays true, so htmx fires
  `htmx:responseError` (decision 11). Server side `_reordered_response` adds
  `headers={"X-Reorder-Refusal": "stale_order"}` to the existing `HTTPException(400)`; the JSON
  body `{"detail": "Invalid item order"}` stays (pinned by
  `test_invalid_permutation_gives_400_event_and_keeps_order`). `#items-list` is never touched
  by this path. Move up/down/drag already use the active list only (`list_wish_items`, cards in
  `#items-list`); first/last flags are recomputed because a full receipt re-renders the list. The
  `swapWishCard` wrapper needs no extra guard (it receives a string, not an event).

### Concurrency and consistency

- Receipt, new card or list, and gifted rows come from one `store.execute` transaction (`BEGIN
  IMMEDIATE`), so the response is consistent with the commit. A concurrent receipt, promise or
  edit serialises; the loser gets `quantity_above_remaining` or `nothing_remaining` with the
  then-current remaining quantity and the effect fragments of the table above.
- The refusal effect read is a second transaction after the rollback; it is read-only and may
  show a newer state, which is the intended "refresh".
- A second tap is stopped client-side only (U-4); the server is not idempotent
  (WISHENKA-61). Two deliberate taps are two legal acts.
- Busy: `InventoryBusyError` from `store.execute` becomes 503 with the neutral sentence; nothing
  changed; the dialog stays open with the chosen quantity (only `#receipt-feedback` changes; the `<select>` value is untouched and the button is re-enabled by `done`).

### Security and surprise

- Authz: all decisions stay in the service (membership first). The page shows the control and the
  section to members only; the routes re-check. Anonymous: 401. Cookie sessions: CSRF header added
  by the existing inline listener (verified path: `htmx.ajax` dispatches `htmx:configRequest`);
  no second path. A stale CSRF token gives the generic sentence.
- Surprise: the dialog, fragments, notice, gifted section, archive section and refusals are
  rendered from `WishItemRecipientViewDTO`/`GiftedItemDTO`/primitive context only. The cabinet
  marker is shown to the giver only. `X-Receipt-Refusal` and `X-Reorder-Refusal` carry only a closed reason. No count
  is rendered to non-members. The owner card shows «Осталось N из M» only with `is_member`; a
  giver still sees `×M` (U-21).
- XSS: ALL out-of-band fragments (notice, feedback, close dialog, card, list, gifted, archive
  glue, stale archive/restore bodies, including the user's wish title and the refusal sentences)
  are rendered by Jinja (autoescape) or escaped with `markupsafe.escape`; no fragment is built by
  f-string interpolation of a title or sentence. Jinja autoescape for every server text; JavaScript uses `textContent` and `replaceWith`
  with created elements only; `data-remaining` is an int.
- Strict-CSP: no new inline script, handler or behaviour-carrying style (N-2); one new `src`
  script from the same origin.

### Russian copy table (N-8)

Fixed by the requirements unless marked NEW (NEW wording is derived by this design, meaning fixed
by the named requirement, to be confirmed at review).

| Place | Text | Source |
| ----- | ---- | ------ |
| Card button | «Получено» | U-1 |
| Dialog title | «Отметить получение» | U-2 |
| Dialog remaining | «Осталось: N» | U-2 |
| Quantity label | «Сколько штук получено» | NEW (N-4 label) |
| Summary N>1 | «Будет отмечено получено: K шт. из N оставшихся» | U-3 |
| Summary N=1 | «Будет отмечено получено: 1 шт.» | U-3 |
| Final act | «Это действие нельзя отменить.» | U-2 |
| Buttons | «Отметить полученным», «Отмена» | U-2 |
| Blocked dialog button | «Закрыть» | NEW (U-8 stale dialog) |
| Refusals and busy | the eight sentences (seven refusal reasons and busy) of the routes table above; the generic failure has its own row | U-8, U-9 |
| Generic failure | «Не удалось сохранить отметку. Повторите попытку.» | U-8 |
| Confirmation | «Отмечено получено: K шт. («Title»)» | U-5, U-6 (title in parentheses is this design's reading of "names the wish") |
| Owner badge | «Осталось N из M» | U-7 |
| Details | «Запрошено: M», «Получено: K», «Осталось: N» | NEW (U-7) |
| Archive row | «Осталось N» | U-10 |
| Archive dialog extra | «Архивируется только неполученная часть: полученные штуки останутся в разделе «Подаренные».» | NEW (U-10) |
| Stale archive/restore | «Это желание уже полностью получено.» | U-10 |
| Reorder stale | «Список изменился. Обновляем.» | U-11 |
| Section heading | «Подаренные (N)» | U-12 |
| Entry | «Получено: K из M», «{K} шт.», «≈ 15.11.2026 (дата примерная)» | U-13 |
| Section failure | «Не удалось загрузить «Подаренные». Обновите страницу.» | U-15 |
| Cabinet marker | «Желание получено владельцем» | U-17 |
| Stale giver card | «Желание больше недоступно. Обновите страницу.» | U-19 |

None of the new view texts contains «бронь», «забронировано», «даритель», «куплено», «занято»,
«занят» (the cabinet marker and the cabinet's own existing words are giver-side and out of that
rule). The inline script of `base.html` itself contains «занято» (giver busy text), so
booking-word tests must scope to the new partials and responses, not to the whole page.

### Traceability

| ID | Design element | Planned files |
| -- | -------------- | ------------- |
| U-1 | card button under the `can_edit_wishlist` block, `remaining_quantity > 0` | `item_card.html` (P14) |
| U-2 | `item_receipt_modal.html`, GET route | `item_receipt_modal.html` (P7), `receipts_ui.py` (P8, P9) |
| U-3 | `<select>` 1..N or hidden 1, summary line, `receipt.js` change handler, clamp | P7, P16 |
| U-4 | form fields only `quantity`; in-flight guard; failure keeps dialog; CSRF via inline listener | `receipt.js` (P17), POST route (P10, P12) |
| U-5 | OOB card, notice, gifted | `receipts_ui.py` (P10) |
| U-6 | OOB `innerHTML:#items-list` list re-render, empty text, first/last flags | P11 |
| U-7 | badge and details, `is_member` | `item_card.html`, `items_ui.py`, `sharing.py` (P1) |
| U-8 | refusal table, sentences, `X-Receipt-Refusal` header, guarded `beforeSwap` override, feedback reset, generic failure | P8, P12, P13, P17 |
| U-9 | busy 503, neutral sentence, dialog kept with the chosen quantity | P12, P17 |
| U-10 | archive «Осталось N», dialog text, `nothing_remaining` HTML response | P3, P15 |
| U-11 | `X-Reorder-Refusal: stale_order`, notice and reload, list never swapped | `items_ui.py`, `wishlist.js` (P11, P19) |
| U-12 | `can_view_gifted`, section include, hidden when empty, archived list | `wishlist_detail.html`, `items_ui.py` (P6), partial (P5) |
| U-13 | `GiftedRow`, dates, approximate marker | `gifted_view.py` (P4), partial (P5) |
| U-14 | no controls in the partial | P5 |
| U-15 | OOB refresh, fail-soft failure text | P4, P5, P6, P10, P13, P15 |
| U-16 | separate containers; archive unchanged source | P5, P6 |
| U-17 | cabinet marker | `reservations_list.html` (P2) |
| U-18 | link omitted when `wish_received`, actions rule unchanged | P2 |
| U-19 | `swapWishCard` wrapper; template guard | `wishlist.js` (P18), `item_card.html` (P1) |
| U-20 | recipient-safe context only; tests scan the new partials; `item_title=""` for non-members | all new partials (P5, P7, P9, P10, P13, P15) |
| U-21 | `is_member` gate; share page untouched | P1 |
| N-1 | route and browser tests for booking words and fields | Step 3 tests |
| N-2 | `receipt.js`, wrapper, no inline code; inline script snapshot hash (T-6) | P16 to P19 |
| N-3 | existing session and CSRF; no control without identification | P10, P14 |
| N-4 | labels, native controls, `role="alert"`, Escape, focus | P7, P16 |
| N-5 | tests, stub extension in test code only | Step 3 |
| N-6 | page layer only, `receipts.py` read-only | all |
| N-7 | UI-path events: fields = the 22 table only (no `operation`), logger name tells channels apart, own scan test | P8 to P13, T-2 |
| N-8 | copy table, `miniapp.css` | P20 |

| DoD | Covered by |
| --- | ---------- |
| 1 | P7, P8, P9, P14, P16, P17; T-2, T-3, B-1 |
| 2 | P1, P10; T-2, T-3 |
| 3 | P12, P13, P17; T-2, B-4, B-4b |
| 4 | P17; B-3 |
| 5 | P4, P5, P6; T-4 |
| 6 | P5; T-4 |
| 7 | P10, P11; T-2, B-2 |
| 8 | P3, P15 (the refusal is shown in the visible `#list-notice` status region, so it is also announced); T-3 |
| 9 | P2; T-5 |
| 10 | P1, P18; T-3, B-5 |
| 11 | all; T-2 to T-5, B-* plus existing surprise tests |
| 12 | Step 8 |
| 13 | P16 to P19; T-6 |
| 14 | P7, P16; T-2, B-1 |
| 15 | all; the diff and existing 23 tests |
| 16 | P8 to P13; T-2 (`test_ui_logging_once_per_outcome`) |

## Implementation Plan

Rule for every step: all previously green tests stay green and the red tests assigned to the step
(and earlier steps) turn green; each step is at most 80 lines of production change (target 70 or
less). Order is checked: nothing is used before it is defined.

| Step | Change | Files | LOC | Defines / uses |
| ---- | ------ | ----- | --- | -------------- |
| P1 | `is_member` context (`_editor_card_flags`, page context, card route), card badge and details, giver guard | `items_ui.py`, `sharing.py`, `item_card.html` | ~35 | defines `is_member` |
| P2 | cabinet marker and link omission | `reservations_list.html` | ~8 | uses existing `CabinetRow.wish_received` |
| P3 | archive section «Осталось N», archive dialog sentence (`has_received` in `archive_confirm_ui`) | `archived_items_section.html`, `item_archive_modal.html`, `items_ui.py` | ~20 | none |
| P4 | `gifted_view.py`: `GiftedAct`, `GiftedRow`, `utc_day`, `build_gifted_rows`, `read_gifted_rows`, the two constants | `gifted_view.py` | ~60 | defines rows, read, constants |
| P5 | `partials/gifted_items_section.html` (container, failure, empty, details, acts) | `gifted_items_section.html` | ~45 | uses P4 |
| P6 | page wiring: gifted rows fail-soft, `can_view_gifted`, `#list-notice`, include | `items_ui.py`, `wishlist_detail.html` | ~30 | uses P4, P5 |
| P7 | `partials/item_receipt_modal.html` | `item_receipt_modal.html` | ~45 | template only |
| P8 | `receipts_ui.py` core: `_SENTENCES`, reason mapping from `_REFUSALS`, logging helpers, `_refusal_fragment` (plain sentence fragment plus header) | `receipts_ui.py` | ~70 | uses P4 constants; no routes yet |
| P9 | GET dialog route (open and blocked state, `item_title=""` rule, `ui_receipt_form_*` logs), router include in `create_app` | `receipts_ui.py`, `app.py` | ~65 | uses P7, P8; its `nothing_remaining` blocked state has no OOB until P13 |
| P10 | POST route, partial receipt: parsing, action, close dialog, notice, card fragment (`card_oob` root attribute), gifted fragment, success log | `receipts_ui.py`, `item_card.html` | ~80 | uses P1, P4, P5, P6, P8, P9 |
| P11 | POST full receipt: list fragment (`innerHTML:#items-list`, first/last flags, empty text) | `receipts_ui.py` | ~30 | uses P10 |
| P12 | POST plain refusals and busy: mapping, status, header, sentence fragment, logs | `receipts_ui.py` | ~55 | uses P8, P10 |
| P13 | `_effect_fragments` for POST (card plus dialog re-rendered with `oob=True` for above-remaining; list, gifted and blocked dialog for nothing-remaining), best-effort degrade, and the GET `nothing_remaining` extension (list plus gifted OOB) | `receipts_ui.py` | ~75 | uses P7, P9, P10, P11, P12 |
| P14 | card «Получено» button | `item_card.html` | ~12 | uses the P9 route |
| P15 | `_nothing_remaining_response` for archive and restore | `items_ui.py` | ~50 | uses P4 constants, P5, P6 |
| P16 | `receipt.js` part A (summary, dismissal, focus, opener) and the `<script src>` tag | `receipt.js`, `base.html` | ~60 | uses P7 markup |
| P17 | `receipt.js` part B (submit guard, feedback reset, `htmx.ajax`, generic failure, guarded `beforeSwap` override with the closed reason set) | `receipt.js` | ~75 | uses P7, P10, P12, P13 |
| P18 | `wishlist.js` `swapWishCard` wrapper | `wishlist.js` | ~35 | uses inline global |
| P19 | stale reorder: `X-Reorder-Refusal` header in `items_ui`, guarded `htmx:responseError` handler in `wishlist.js` | `items_ui.py`, `wishlist.js` | ~35 | uses P6 `#list-notice` |
| P20 | `miniapp.css` (dialog backdrop and sheet scoped to `.receipt-backdrop`/`.receipt-sheet`, notice, gifted, feedback) | `miniapp.css` | ~50 | uses classes of P5, P7 |

Dependency check: P5 needs P4; P6 needs P4, P5; P8 needs the P4 constants; P9 needs P7, P8 (no effect fragments); P10
needs P1, P4, P5, P6, P8, P9 (route lives in the same module; `card_oob` is defined inside P10);
P11 needs P10; P12 needs P8 and the P10 route; P13 needs P11 (list fragment), P10 (card fragment),
P12 (fallback), P7 (dialog re-render with `oob`), P9 (the GET it extends); P14 needs the P9 route; P15 needs P4, P5, P6 (no import of
`receipts_ui`, shared constants come from `gifted_view.py`); P17 needs P7 ids and the P10, P12,
P13 responses; P19 needs P6. P16 and P17 are inert without the markup of P7 (delegated listeners),
so the order template, routes, scripts is safe. Docs (Step 8) and logs review (Step 6) follow
Step 4.

### Failing Repro plan for Step 3

Sequence: research (this document), red tests written first, then P1 to P20 until green. Common
rules: `pytestmark = pytest.mark.timeout(...)` at module level, bounded waits, helpers from
`tests/receipt_support.py` (`new_symbol`, `attr_of`, `app_env`, `bearer`, `seed_wish`) so a
missing component is one readable red assertion, not a collection error. Route and markup tests
use `TestClient` and BeautifulSoup; behaviour needing real JS uses the Chromium infrastructure.
No production code is written in Step 3. Booking-word checks scan only the new partials and
responses (not full pages, because the inline script contains «занято»). Seeded promises use
booking numbers that cannot collide with logged numbers (37, 41, 53 as in
`test_receipt_observability.py`) and giver names that are searched for.

`tests/test_receipt_ui_routes.py` (T-2):

| Test | Asserts | Forced red because |
| ---- | ------- | ------------------ |
| `test_get_modal_content_for_member` | 200; title, wish title, «Осталось: N», `<select name=quantity>` with options 1..N and 1 selected, summary line, «Это действие нельзя отменить.», both buttons, label bound to select, `role="alert"` region, no `on*` attribute, no `<script>`, no `style` attribute; a wish titled `<script>alert(1)</script>` appears escaped and no `<script>` element exists | route is 404 |
| `test_get_modal_busy_is_503_with_header` | patched `receipts_ui._execute` raises `InventoryBusyError` on GET: 503, `X-Receipt-Refusal: busy`, neutral sentence, no form | 404 |
| `test_modal_template_oob_switch` (direct template render) | default render has no `hx-swap-oob`; `oob=True` gives `hx-swap-oob="outerHTML"` on the `#item-receipt-modal` root, `blocked=True` renders no form | template missing |
| `test_get_modal_remaining_one_has_no_choice` | hidden `quantity=1`, no select, «Будет отмечено получено: 1 шт.» | 404 |
| `test_get_modal_has_no_booking_data` | with promises 37/41 and giver names seeded, none of the names or numbers or words in U-8 in the partial | 404 |
| `test_get_modal_refusals_blocked_state` | member with archived wish, fully received, archived list: contract status, header, sentence, no form, «Закрыть», wish title shown; `wishlist_not_active` for both an archived list (409) and a deleted list (404); `nothing_remaining` GET carries the list and gifted OOB fragments (P13); non-member (`forbidden`) and unknown wish (`not_found`): contract status, header, sentence, no form, and the seeded wish title is absent from the body and there is no `.receipt-wish` element (`item_title=""`) | 404 |
| `test_post_partial_receipt_fragments` | 201; OOB card with «Осталось 3 из 5» and `hx-swap-oob="true"`, notice «Отмечено получено: 2 шт.», close dialog, gifted section with «Получено: 2 из 5» and a dated act; a wish titled `<script>alert(1)</script>` is escaped in the notice, card and gifted fragments (no `<script>` element); the 201 body contains none of «занято», «забронир», «бронь», «даритель», «куплено» | 404 |
| `test_post_full_receipt_removes_card_and_fixes_flags` | OOB `innerHTML:#items-list`, removed card absent, first card has disabled up and last disabled down, empty-list text when none left, gifted entry «Получено: 5 из 5» | 404 |
| `test_post_co_author_and_recipient_views` | co-author gets gifter-view card; recipient gets no booking markup after receipt | 404 |
| `test_post_refusals_by_reason` (parametrised, 9 rows: one per `_REFUSALS` class; `wishlist_not_active` covered for both the archived 409 and the deleted 404 list) | status, `X-Receipt-Refusal`, exact sentence, no English message, no booked number, N shown for `quantity_above_remaining`, list OOB for `nothing_remaining`, card plus re-rendered dialog (`hx-swap-oob="outerHTML"` on `#item-receipt-modal`) for above-remaining, list plus gifted plus blocked dialog (no form) for `nothing_remaining` | 404 |
| `test_post_refusal_effect_read_failure_degrades` | `receipts_ui._execute` passes the first call through and raises `InventoryBusyError` (and once `PermissionDeniedError`) on the second (the effect read), for `quantity_above_remaining` and `nothing_remaining`: status stays 409, header stays, sentence present, no card, list, gifted or dialog fragment, no 500 | route missing |
| `test_post_non_integer_quantity_is_quantity_invalid` | `abc`, empty, `0`, `-1`, `3.0` give 400 and the first sentence, not 422 | 404 |
| `test_post_busy_is_503_and_changes_nothing` | patched `receipts_ui._execute` raises `InventoryBusyError`; 503, header `busy`, neutral sentence without «занято/занят», `received_quantity` unchanged | route missing |
| `test_post_unauthenticated_and_csrf` | no credentials 401; cookie session without CSRF header 403 (middleware) | route missing |
| `test_ui_reason_table_matches_json_route` | every class in `receipts._REFUSALS` has a UI sentence and the same reason and status | module missing |
| `test_ui_logging_once_per_outcome` (the own never-logged scan of the new logger) | caplog on `wishenka.web.receipts_ui`: exactly one `receipt_recorded_http` / `receipt_refused` / `receipt_inventory_busy` per outcome; extra keys are a subset of `{wishlist_id, item_id, actor_id, reason, http_status, remaining_quantity}`; `remaining_quantity` only for the two reasons; no `operation`, quantity, title, giver names, booking numbers, `user_id`; no `notification`, `outbox`, `push` | module missing |

`tests/test_gifted_section_ui.py` (T-4): `test_section_shown_to_owner_admin_member_with_count`,
`test_section_hidden_when_empty`, `test_section_absent_for_giver_anonymous_share_and_stranger`
(also no count in the page text), `test_section_visible_on_archived_list_without_edit_controls`,
`test_section_separate_from_archive` (partly received archived wish: archive row «Осталось N»,
gifted entry present, fully received only in gifted), `test_entry_content_and_order` (title, price,
recipient, «Получено: K из M», acts with `dd.mm.yyyy`, newest first; a wish titled
`<script>alert(1)</script>` is escaped and the section has no `<script>` element), `test_approximate_date_marked`
(via a back-filled receipt), `test_section_has_no_controls_or_booking_data`,
`test_read_failure_shows_text` (monkeypatched `list_gifted_items` raises `PermissionDeniedError`;
page still 200 with the active list). Red: no section markup.

`tests/test_receipt_card_ui.py` (T-3): owner badge and details (`Осталось 3 из 5`, three detail
spans), nothing received unchanged, giver and share viewers keep `×5` and never see «Осталось»,
button present for members on an active list and absent for giver, anonymous, archived list
(`hx-get` path and `data-no-toggle`, no `on*`), archive confirm text only for a received part,
restore returns the remaining quantity and leaves the gifted section data unchanged, archive and
restore of a fully received wish return 409, every top-level element of that stale 409 body carries
`hx-swap-oob` (restore targets `#items-list` with `beforeend`, the edit-modal archive targets the
card with `outerHTML`, so any non-OOB top-level content would be swapped into the list or card), `X-Receipt-Refusal: nothing_remaining`, sentence and
list/section fragments.

- `test_giver_card_fully_received_has_no_booking_controls` (direct
  `templates.get_template("partials/item_card.html").render`): the gifter-view DTO is built so the
  guard is the only thing that can remove the controls: `is_recipient=False`,
  `is_fully_received=True`, `received_quantity == quantity`, `remaining_quantity=0`, and the stale
  booking fields that make controls appear today: `available_quantity=1`, `is_reserved_by_me=True`
  with `my_reservation_id`, `my_reservation_status='active'`, `my_latest_reservation_quantity=1`;
  context `viewer_identified=True`, `wishlist_active=True`. Asserts no «Забронировать», no
  «Изменить», no «Отменить бронь», no purchase control and no `hx-post`/`hx-patch` reservation
  attribute. A second render with `is_reserved_by_me=False`, `available_quantity=1` asserts no
  reserve form. Red today because `can_promise` does not look at `is_fully_received`, so those
  controls are rendered; green after P1.
- `test_stale_reorder_has_distinct_marker_header`: invalid permutation gives 400, the unchanged
  JSON body `{"detail": "Invalid item order"}`, header `X-Reorder-Refusal: stale_order` and no
  `X-Receipt-Refusal` header. Red: header absent.

`tests/test_cabinet_received_marker.py` (T-5): marker present for a fully received wish on an active
list with actions and no «К желанию»; purchased promise shows marker and «Куплено» and no
«completed»; partly received: no marker and link present; archived list: marker, no action forms;
closed promise: no row; marker text has no digits and no quantity words. Red: no marker.

`tests/test_receipt_static_script.py` (T-6): `/static/receipt.js` served as JavaScript and
referenced with `defer` after `wishlist.js`; the inline script text of the page contains no
`receipt` and is unchanged from HEAD `7fb5503` (SHA-256 constant fixed in Step 3; no existing
test pins a length; changes only with WISHENKA-140);
`wishlist.js` still has exactly one non-comment `htmx.ajax(` and `receipt.js` exactly one; the page
and the new partials carry no `on*` attribute; `receipt.js` does not contain `X-Reorder-Refusal`
or `stale_order` and `wishlist.js` does not contain `X-Receipt-Refusal` (the two marker
namespaces never meet); the NEW handlers (the `htmx:beforeSwap` override in `receipt.js` and the `htmx:responseError`
handler in `wishlist.js`; not the existing `wishlist.js` `htmx:beforeSwap` handler, which uses
`event.detail.target` only) contain the `getResponseHeader` function guard (source check); every
`reason` of `receipts._REFUSALS` and `busy` appears in `receipt.js` and no other reason-like value
does (the closed set mirrors the table, so a reason added by WISHENKA-158 turns the test red).
Red: file absent.

`tests/test_receipt_modal_browser.py` (B-1 to B-6, `pytest.mark.browser`, module timeout 45):

| Test | Asserts | Forced red because |
| ---- | ------- | ------------------ |
| B-1 `test_summary_updates_and_dismiss_changes_nothing` | the dialog opened with `htmx.ajax('GET', .../receipt, {target:'#item-modal-container', swap:'innerHTML'})` (the stub ignores `hx-get`); changing the select rewrites the summary; Cancel and Escape close it, no POST recorded; focus first moves to the select and returns to the card summary; keyboard: Tab order reaches select, confirm, cancel; Enter submits | script absent |
| B-2 `test_partial_and_full_receipt_update_page` | submit sends one POST with body `quantity=2` only; dialog closes; card shows «Осталось 3 из 5»; section shows the entry without reload; full receipt removes the card and the section count updates | script and routes absent |
| B-3 `test_second_tap_sends_no_second_request` | two quick clicks and an Enter during flight: exactly one POST (network and `__ajaxCalls`); button re-enabled after the response | no guard |
| B-4 `test_refusal_then_generic_failure_replaces_sentence` | lost race (receipt made through the REST API after the page loaded): sentence with N in `#receipt-feedback`, dialog open, button enabled; then `page.set_bearer('bad')` and a retry: the old sentence is replaced by the generic sentence «Не удалось сохранить отметку. Повторите попытку.» (the feedback was emptied when the retry started); a first-attempt failure with a bad bearer gives the generic sentence as well | script absent |
| B-4b `test_busy_keeps_dialog_and_chosen_quantity` | the server answers 503 `busy` for the first attempt (patched `receipts_ui._execute` raising `InventoryBusyError` once, in-process fixture server or an injected `app.state.wishlist_service`): the neutral busy sentence, dialog still open, the `<select>` value is still the chosen one (3 of 5, not reset to 1), the submit button is enabled; a second attempt succeeds | script absent |
| B-4c `test_before_swap_override_is_guarded_and_closed` | synthetic `htmx:beforeSwap` events: `detail = {target}` only (no `xhr`) throws nothing and changes nothing; a fake `xhr` with `X-Receipt-Refusal: quantity_above_remaining` gets `shouldSwap=true`, `isError=false`; a fake `xhr` with an unknown `X-Receipt-Refusal` value, with `X-Reorder-Refusal: stale_order`, or without any header stays `shouldSwap=false`, `isError=true`; console is clean | script absent |
| B-5 `test_stale_giver_card_is_neutral` | share page as viewer; owner fully receives via REST; dispatch a synthetic `htmx:afterRequest` (200) on a reservation button so the inline handler fetches the card (404); the card becomes «Желание больше недоступно. Обновите страницу.», no `{"detail"` text, no controls; a valid refresh still swaps and keeps expansion | wrapper absent (raw body is inserted today) |
| B-6 `test_stale_reorder_keeps_list_and_shows_notice` | owner page; the wish list is changed through REST after the page loaded (one wish archived) so the permutation is stale; `htmx.ajax('POST', .../items/reorder, {target:'#items-list', swap:'innerHTML'})` as `wishlist.js:112` does, with `receipt.js` loaded: the card ids in `#items-list` are unchanged (not swapped), the text `Invalid item order` and `{"detail"` appear nowhere in `#items-list`, `#list-notice` shows «Список изменился. Обновляем.», a page reload happens (bounded wait); also for the move up/down path when exercised by the same call | notice handler absent |

Every browser test asserts `assert_clean_console` and no external requests.

**Stub extension (test code only, `tests/browser_assets/htmx_stub.js`)**, written in Step 3:
honour `swap: 'none'`; build `detail.xhr = {status, getResponseHeader}` and dispatch
`htmx:beforeSwap` with `shouldSwap = status < 400`, `isError = status >= 400` (handlers may change
them; the stub reads both back after the event, as htmx 1.9.12 does) before swapping, honour a
`shouldSwap === false` result by not swapping, and dispatch `htmx:responseError` when the response
was not swapped and `isError` is still true; process out-of-band elements `hx-swap-oob` with
values `true`, `outerHTML`, `innerHTML`, `<style>:<selector>` and `delete` (removed from the main
content; OOB is applied also when `swap: 'none'` or when the main swap is skipped but only for a
response that `beforeSwap` accepted); keep the existing contract (`window.__ajaxCalls`,
`__ajaxPending`, innerHTML swap for 2xx without OOB, `htmx:beforeSwap` with `detail.target`,
`htmx:afterSwap`). The stub still does not process `hx-*` attributes. Step 3 runs the full
existing browser suite (53 tests) after the stub change to prove it is additive (existing code
paths dispatch events with `detail.target` only, and the new handlers guard against a missing
`xhr`). Helpers added to `tests/browser_helpers.py`: `record_receipt(seeded, item_id, quantity)`
(REST, Bearer), `open_receipt_dialog(page, seeded, item_id)`, `posts_to(page, suffix)`.

Residual that tests cannot cover offline: the real htmx 1.9.12 handling of OOB inside a response
re-enabled by `beforeSwap` (verified in the htmx 1.9.12 source: OOB is handled in `selectAndSwap`
before the swap and `swap: 'none'` still processes it; `isError` is read back after `beforeSwap`)
and the real `hx-get` button click. Markup tests assert the attributes; the stub covers the
script.

### Existing tests the plan breaks

Search done over `tests/` for markup, static-script, route-list, archive section, cabinet row,
`can_edit_wishlist` and log-event assertions. Result: no existing test needs an edit if the plan
is followed. The at-risk assertions and why each survives:

| Existing test | Risk | Attached step and resolution |
| ------------- | ---- | ---------------------------- |
| `tests/test_wishlist_touch_reorder.py` (one `htmx.ajax(` in `wishlist.js`) | a second call in `wishlist.js` | P17: the call lives in new `receipt.js`; P18, P19 add no `htmx.ajax` |
| `tests/test_wishlist_static_script.py` (no `on*` attributes on pages, `#items-list` guards, inline script markers, script order) | new markup, `#list-notice`, new script tag | P6, P14, P16: no `on*`, no `hx-target="#items-list"` element with `outerHTML`, `#items-list` not re-emitted in reorder/move responses, inline script untouched, `receipt.js` after `wishlist.js` and htmx |
| `tests/test_items_ui_error_mapping.py::test_invalid_permutation_gives_400_event_and_keeps_order` (JSON body `Invalid item order`) | U-11 | P19: only a header (`X-Reorder-Refusal`) is added to the existing `HTTPException` |
| `tests/test_gift_receipt_api.py::test_archive_restore_routes_nothing_remaining` (HTML 409) | P15 changes the HTML body | status stays 409; the test asserts the status only |
| `tests/test_wish_items_list_reorder_ui.py` (archive section after archive and restore, `badge-quantity` for quantity 6, RBAC) | card and section markup | P1, P3: unchanged when nothing is received; section gating by `can_edit_wishlist` unchanged |
| `tests/test_wish_card_giver_controls.py`, `test_reservations_surprise_invariant.py`, `test_surprise_*` | card template | P1: new branches only when `is_member` and `received_quantity > 0` or `is_fully_received`; giver and recipient cards without receipts render as before |
| `tests/test_reservations_cabinet_ui.py` (rows, link, inline script branches) | cabinet template, `base.html` | P2: marker and link omission only for `wish_received`; inline script not edited, `<script src>` tag is not an inline script |
| `tests/test_receipt_notices.py::test_settings_storage_only` (no route path contains `notif`) | new paths | paths contain `receipt`, no `notif` |
| `tests/test_wishenka_112_structure.py` (`_DOMAIN_ERRORS` has five classes, reorder callback type) | `items_ui` edits | `_DOMAIN_ERRORS` and `_reordered_response` signature untouched (P15 and P19 add code beside them) |
| browser suite (`test_wishlist_cards_browser.py`, mouse and touch reorder, 53 tests) | stub extension (test code) | Step 3 runs the suite after the stub change; the extension is additive |
| `tests/test_receipt_observability.py`, notice walk | new log events | P8 to P13: UI events use the new logger `wishenka.web.receipts_ui` (its logger-name equality filter on `wishenka.web.receipts` does not match; the file is not edited), no `operation`, no notice-path field or word; the UI scan is `test_ui_logging_once_per_outcome` |
| browser suite, every page loads `receipt.js` and `wishlist.js` | handlers see the stub's `{target}`-only `htmx:beforeSwap` | P17, P19: both handlers guard `detail && detail.xhr && typeof detail.xhr.getResponseHeader === 'function'`; B-4c pins it |

## Observability and docs plan

Step 6 (`50-observability.md`): verify the events table above is exactly what the code writes;
confirm one record per outcome, field subsets (`caplog` test: only the 22 table fields, no `operation`), absence of `quantity`, titles,
giver data and `user_id`; confirm no notice-path words; note that `receipt_refused` counted by
`reason` now covers both channels (distinguish by logger `wishenka.web.receipts_ui`; there is no
`operation` field on the UI records); metrics stay derived from logs (WISHENKA-84); the browser logs
nothing.

Step 8 (docs): `doc/dev/gift-receipt.md` (status header and «Not implemented» list: UI done;
new section «Mini App screens»: routes, refusal to sentence table, marker header, fragments,
logging rows `ui_receipt_form_*` and UI use of the JSON event names, troubleshooting); 
`doc/dev/miniapp.md` (new subsection 9.9 receipt dialog and «Подаренные», `receipt.js`, the
`swapWishCard` wrapper, the `X-Receipt-Refusal` mechanism and the separate `X-Reorder-Refusal` marker, updates to 9.1, 9.7, 9.8, inline-script
note, stub limits); `doc/dev/reservations.md` (cabinet marker and link rule);
`doc/dev/items.md` (card badges, archive section text); `doc/dev/testing.md` (browser test
modules, stub extension, new helpers); `doc/dev/verification-matrix.md` if it lists surfaces.
Remove every «no UI yet / planned» statement (TD-1.12).

## Divergences from WISHENKA-22 and WISHENKA-23

1. **23 section 6 "HTMX layer calls the same service methods through `items_ui._execute`".**
   Followed (full snapshot, same helper), but in a new module `receipts_ui.py` that imports the
   helper. Refinement, not a change: `execute_wish` is not used because the response needs the
   list and gifted rows from the same transaction.
2. **22 `50-observability.md` hand-off and 23 event names.** 22 says "route-level records of the
   receipt route"; there is no UI record today. The design reuses the 23 event names on a new
   logger, with only fields of 22's table (no `operation`; 22 lists none for `receipt_refused`,
   and `receipt_recorded_http` / `receipt_inventory_busy` are 23 additions absent from the 22
   table; 23's JSON route keeps writing `operation` unchanged). `receipt_recorded_http` of the
   JSON route has `operation` and `item_id`; the UI record carries
   `wishlist_id`, `item_id`, `actor_id`.
3. **22 plan item 4 / 23 text "hiding giver controls on the card of a fully received wish is a
   WISHENKA-24 task".** The premise is only partly right: a fully received wish never reaches a
   giver card (projection omits it, card route 404). The template guard is added as defence in
   depth; the real defect is the raw 404 body in the card refresh, fixed by the wrapper.
4. **U-13 / UA-4 "dates as the cabinet shows event days".** The cabinet shows ISO `yyyy-mm-dd`
   (`reservations_ui._event_day`); the example in U-13 and the wishlist page header use
   `dd.mm.yyyy`. The design keeps the shared convention (UTC calendar day) and the `dd.mm.yyyy`
   format of U-13.
5. **22/23 imply a refusal is shown by htmx.** With htmx 1.9.12 a 4xx/5xx is not swapped, so the
   design adds the receipt-only `X-Receipt-Refusal` marker and the guarded `beforeSwap`
   override (decision 4); the status codes of the JSON contract are kept. The reorder 400 is
   deliberately not overridden (decision 11).

## Q&A

- Q1. Why not `hx-post` on the form like the other modals? A. The in-flight guard must be
  proven in the browser and the offline stub only implements `htmx.ajax` (decision 6); the CSRF
  header is still added by the same listener.
- Q2. Why does the stale card become neutral by a content check and not by status? A. The inline
  script passes only the markup to `swapWishCard`; the content check also covers 401, 500 and a
  network failure (SHOULD) and needs no change of the inline script.
- Q3. Why is the gifted section refreshed by the receipt response and not by a new route? A. One
  transaction gives a consistent view; a route would be unused (decision 9). The failure text
  remains reachable through the fail-soft read.
- Q4. Why a second read after a refusal? A. The refused act rolled back; the stale effects need
  current data. It is read-only.
- Q5. Does the dialog show other quantities than the remaining one? A. No: remaining and the
  chosen number only.
- Q6. What about a co-author who is the recipient? A. The service projects the recipient view
  (`project_wish_item`), so no booking data is rendered (UA-5).
- Q7. Why two header names? A. The override must apply only to server HTML fragments built for
  OOB application; the reorder 400 has a JSON body and must stay unswapped, so it uses
  `X-Reorder-Refusal` and nothing overrides it (decisions 4 and 11).
- Q8. Why is `operation` not logged by the UI path? A. N-7 allows only the fields of 22's table;
  the logger name already tells the channels apart.

## Issues found

1. **Existing defect (not fixed here):** htmx 1.9.12 does not swap 4xx/5xx, so the 409/503
   re-render of `submit_edit_item` documented in `miniapp.md` 9.6, the archive 409 and the reorder
   400 are invisible to users. This story fixes the receipt, archive/restore `nothing_remaining`
   and (SHOULD) stale reorder only. Recommend a Debt ticket: send `X-Receipt-Refusal` from the edit
   modal 409/503 responses (the `receipt.js` override already handles it, only if the body is an
   HTML fragment built for OOB application).
2. **Existing defect:** `.modal-backdrop` and `.modal-sheet` have no CSS (Tailwind classes are
   not loaded), so the older modals render as plain blocks at the end of the page. The new dialog
   gets scoped rules (P20); the older modals are not touched. Debt candidate.
3. **Requirements wording:** U-13 and UA-4 say dates follow the cabinet convention but the cabinet
   uses ISO; resolved as divergence 4. The labels «Сколько штук получено», «Закрыть», the details
   labels and the archive dialog sentence are new texts needing review (copy table, NEW).
4. **Test scoping:** N-1 booking-word tests must not scan whole pages (inline script contains
   «занято»).
5. **Accepted limits:** the «Подаренные» details element re-collapses after a receipt swap; the
   dialog has no focus trap (`aria-modal` not set); reload is the refresh for a stale reorder;
   the quantity `<select>` lists every number up to the remaining quantity; real-htmx OOB handling
   of a `beforeSwap`-enabled error response is verified in the source but not testable offline.
6. **Coupling:** `receipts_ui.py` reads the private `_REFUSALS` of `receipts.py`; WISHENKA-158
   (split receipt code) must keep the table importable; a test guards the contract.
7. **Existing defect (noted, not fixed):** the edit-modal archive path swaps the card with
   `outerHTML` and its target can already be detached when the response arrives (pre-existing
   `TypeError` in htmx); the stale 409 body of this story is OOB-only, so it adds no new exposure.
8. **Scope check:** no change of `receipts.py`, services, store, migrations, DTOs or notices;
   DoD 15 holds by construction.
