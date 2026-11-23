# WISHENKA-295: Owner can delete their wishlist

## Research

### Verified baseline (facts checked in code on master, 931ef8d)

- **Domain delete exists, no HTTP route.** `WishlistService.delete_wishlist(wishlist_id, actor)`
  (`wishenka/wishlists/service.py:1086-1128`) loads the list with `get_wishlist_by_id`
  (raises `WishlistDeletedError` when already deleted, `service.py:651-674`), calls
  `_ensure_wishlist_active` (archived -> `WishlistArchivedError`, `service.py:562-566`) **before**
  the permission check, then `WishlistAccessPolicy.can_delete` (owner only,
  `wishenka/wishlists/policy.py:94-97`), sets `status = DELETED`, `updated_at = now`, and cancels
  `ACTIVE`/`PURCHASED` reservations of all items. It returns `None` and logs
  `wishlist_status_changed`. It does not touch `public_token`/`invite_token`: links stop working
  only because deleted lists are hidden by status (restore rotates them,
  `service.py:1173+`). No route calls it: `doc/dev/wishlists.md:126` says "There is no HTTP delete
  route", and `grep delete_wishlist wishenka/web` is empty. `tests/test_wishlist_deleted_restore.py`
  (lines 126, 228, 314) deletes through `service.delete_wishlist` inside `store.execute`.
- **Deleted-list lifecycle already works.** `GET /api/wishlists/deleted`
  (`wishenka/web/routes/wishlists.py:225`) and `POST /api/wishlists/{id}/restore-deleted`
  (`routes/wishlists.py:494-526`, 410 `retention_expired`), retention `settings.wishlist_retention_days`
  (default 30, `wishenka/config.py:93`), purge in `wishenka/wishlists/cleanup.py:82`. The home screen
  renders "Recently deleted" with `Restore` and days left (`wishenka/web/static/miniapp.js:494-540`).
- **Route layer.** `execute()` (`routes/wishlists.py:42-84`) runs the action through the
  transactional store and maps `WishlistNotFoundError`, `WishlistDeletedError`,
  `PermissionDeniedError` all to the same `404 "Wishlist not found"`, `WishlistArchivedError` to
  409, `WishlistRetentionExpiredError` to 410, and emits `wishlist_mutation_committed` for operations
  named in a fixed set (`create_wishlist`, `update_wishlist`, `change_status`, `reset_share`,
  `restore_deleted_wishlist`); the operation name is the endpoint function `__name__`.
  A catch-all `POST /api/wishlists/{id}/{operation}` exists (`routes/wishlists.py:529`) but it is
  POST-only, so a new `DELETE /api/wishlists/{id}` does not collide with it. Precedent for reading
  `service._wishlists.get(id)` directly in a route: `record_view` (`routes/wishlists.py:413`).
  CSRF is checked for every non-GET request by the existing middleware; `api()` in
  `miniapp.js:100-112` adds `X-CSRF-Token` for `DELETE` (already used by `DELETE /api/history`).
  `api()` always calls `response.json()` (so a `204` would break it).
- **Mini App list screen.** `showList()` (`miniapp.js:~686`) renders, for `manager` (owner or
  admin) of an `active` list, the section `.list-admin-section.list-settings-section`
  (`miniapp.js:738-743`) containing `<h2>`, subtitle and `settingsForm(list)`
  (`miniapp.js:579-625`); the form ends with `.form-actions.settings-form-actions` (Save =
  `submit`, Cancel = `.settings-cancel-btn`). `list.role` comes from the projection
  (`routes/wishlists.py:~150`); `owner` is the only role allowed to delete. The Mini App shell
  `wishenka/web/routes/miniapp.py:26-50` renders `<main id="app" data-bot data-miniapp data-locale>`
  and does not expose the retention period.
- **Reusable UI pieces.** `withPending(control, action, message)` / `pending()`
  (`miniapp.js:87-103`: per-control `WeakSet` guard, `disabled`, `aria-busy`, `.is-pending`,
  pending status line). `status(message, kind)` (`miniapp.js:73-80`, `role="status"` live region
  `#status`, `aria-live` assertive for `error`). The in-place destructive confirmation of the
  history screen, `renderHistoryFooter` (`miniapp.js:272-328`): the trigger button is replaced by
  a `role="group"` panel with title, body, Cancel and a `btn-danger` confirm, Escape closes,
  focus moves to Cancel, failure is shown as `role="alert"` inside the panel, success navigates and
  sets a `success` status. Its CSS is `miniapp.css:278-290` (`history-confirm*`, `btn-danger` at
  line 61). Result-after-navigation pattern: restore does `await showHome(); status(..., 'success')`
  (`miniapp.js:520-526`) because `showHome()` ends with `status('')`.
- **`node()` helper uses `textContent`** (`miniapp.js:27-31`), so any title passed through it is
  never parsed as HTML. The i18n `t()` substitutes `{param}` into the template string only
  (`miniapp.js:48-61`).
- **CSS**: `#app .form-actions` flex-wrap with `button { margin: 0; max-width: 100%; min-width: 0;
  overflow-wrap: anywhere }` (`miniapp.css:111-117`), `.list-settings-section` left border
  (`:122`), tokens `--danger #a61335`, `--touch-target 44px`, `--border-subtle`, `--surface-subtle`.
  `.btn-danger` is outlined danger (`:61`); a filled danger confirm already exists as
  `#app button.history-confirm-yes` (`:286-288`).
- **i18n**: `wishenka/i18n/catalog.py` has `en` and `ru` tables; `miniapp_catalog()` projects keys
  with prefixes `nav.`/`miniapp.` into the embedded JSON (`catalog.py:1256-1262`); neighbouring keys
  are `miniapp.wishlist_settings.*` (EN 341-358, RU 965-982) and `miniapp.deleted.*` (EN 395-403,
  RU 1021-1027). English product term for the section is "Gifted"; Russian is «Подаренные».

### Findings that shape the design

1. **Idempotency gap.** A second `service.delete_wishlist` on a deleted list raises
   `WishlistDeletedError`, which `execute()` maps to 404, and the same 404 is what a non-owner or an
   unknown id gets. Requirement 9 needs the owner to get a success on a repeat. So the route cannot
   just forward to the service; it must classify the list first.
2. **Archived check precedes the permission check in the service** (`service.py:1092-1095`): a
   non-owner deleting an archived list would get 409 (leaks that the list exists and is archived).
   The route therefore checks ownership before calling the service.
3. **Retention days are not known to the Mini App** before a delete; the confirmation needs the
   real number (requirement 3a).
4. **Doc mismatches** (`doc/dev/wishlists.md`): line 749-753 says `delete_wishlist(...) -> Wishlist`,
   actual return type is `None`; line 757 says it "invalidates tokens", it does not (tokens are
   rotated on restore only); line 126 says there is no HTTP delete route (will be false).

## Implementation Plan

Smallest coherent change: one HTTP route, one Mini App UI block, new i18n keys, a small CSS block,
one shell attribute. No new lifecycle state, no migration, no change to the service rules, the
retention period, "Recently deleted", or the settings page (`/settings`).

1. `wishenka/web/routes/wishlists.py`: new `DELETE /api/wishlists/{wishlist_id}` (`delete_wishlist`),
   add `"delete_wishlist"` to the committed-mutation set.
2. `wishenka/web/routes/miniapp.py`: add `data-retention-days="{int}"` to `<main id="app">`.
3. `wishenka/web/static/miniapp.js`: new `deleteWishlistControls(list)` called from `showList` only
   when `list.role === 'owner'`, appended after `settingsForm(list)` inside the settings section.
4. `wishenka/i18n/catalog.py`: new `miniapp.wishlist_delete.*` keys, EN and RU.
5. `wishenka/web/static/miniapp.css`: small `.wishlist-delete-zone` block built on existing tokens.
6. Docs in Step 8 (see "Docs to update").

**Failing Repro (next Step 3).** Red tests written before any production change, in three modules (API, Node-harness UI, CDP browser).

- `tests/test_wishlist_delete_api.py` (new, no browser, style of `tests/test_wishlist_deleted_restore.py`:
  real app + store via `create_app`, owner/other users by test auth cookies). Red now because the
  route does not exist (405/404 for every DELETE). Cases: owner `DELETE /api/wishlists/{id}` -> 200,
  `{"status": "deleted", "wishlist_id": id, "retention_days": 30}`; the list is gone from
  `GET /api/wishlists` and `GET /api/wishlists/{id}` (404), present in `GET /api/wishlists/deleted`
  with `days_remaining == 30`; second owner DELETE -> 200 same body, `updated_at` (deleted_at) not
  moved, one status transition; non-owner roles (admin, member, gifter-with-link, anonymous without
  session) -> admin/member/stranger 404 with the same body as unknown id, anonymous 401 as for every
  API, list unchanged, status still `active`; unknown id -> 404 identical body to a non-owner;
  non-owner DELETE on an already deleted list and on an archived list -> 404 (no 409 leak); owner
  DELETE on an archived list -> 409, unchanged; other lists of the owner and of another user
  unchanged; reservations of the deleted list become `cancelled` while other lists' reservations stay
  `active`; secrecy: response bodies for lists with and without reservations are byte-identical and
  contain no reservation keys; missing CSRF -> 403 and the list is unchanged (the request must use a **cookie session with a
matching Origin and no `Authorization: Bearer`**, because the CSRF branch applies only when
`cookie and not bearer`, `wishenka/web/security.py:35-47`; a Bearer request would skip the check
and prove nothing); repeat delete after the retention window but before purge (set `updated_at`
older than `retention_days` through the service/store) -> 410 `retention_expired`, status still
`deleted`, no new `wishlist_status_changed`; restore round-trip
  (`restore-deleted` -> 200, active, new tokens, reservations still cancelled).
- `tests/test_wishlist_delete_ui.py` (new, Node harness, `timeout(20)`, no browser marker; cases U1-U3
  under Test strategy). Red now because no zone is rendered, so U1/U2/U3 fail on the owner assertions.
- `tests/test_wishlist_delete_browser.py` (new, CDP, module marker `pytest.mark.timeout(45)` and
  `pytest.mark.browser` per `tests/test_browser_prerequisites.py` rules; fixtures `seed_wishlist`,
  `wishlist_server`, `chromium_browser` from `tests/conftest.py`; sibling helpers for opening a list
  screen are module-private in `tests/test_wishlist_detail_browser.py`, so the new module defines its
  own minimal `_open_list`). Red now because no control exists. See "Test strategy".
- Sequencing: research -> Step 3 red tests against unchanged code (every new API/UI assertion red;
  guards for non-owner secrecy of unknown id are green already and marked as regression guards)
  -> Step 4 implement until green.

## Architecture

### Components

```
miniapp.js (showList -> deleteWishlistControls)
   |  DELETE /api/wishlists/{id}  (X-CSRF-Token, JSON reply)
   v
routes/wishlists.py: delete_wishlist  --classify--> WishlistAccessPolicy.can_delete
   |  execute(request, action)  (store transaction, error mapping, mutation log)
   v
WishlistService.delete_wishlist  (unchanged: status DELETED, cancel reservations)
   v
existing: GET /api/wishlists/deleted -> "Recently deleted" -> POST .../restore-deleted
```

Pattern: thin route as an adapter over the existing service (same as `restore_deleted_wishlist`),
UI as a progressive in-place confirmation (same as history clear). No new JS module, no new service
method, no modal/focus-trap library.

### D-1 HTTP interface

`DELETE /api/wishlists/{wishlist_id}` (function `delete_wishlist` so `execute()` logs the mutation).

| Case | Result |
| ---- | ------ |
| Owner, list `active` | `200 {"status": "deleted", "wishlist_id": <id>, "retention_days": <N>}` |
| Owner, list already `deleted`, still inside the retention window (repeat, double tap) | `200`, identical body, **no** service call, `updated_at` untouched (deleted_at must not slide the retention window) |
| Owner, list `deleted` and `updated_at + retention_days <= now`, but not yet purged by cleanup | `410 {"code": "retention_expired", ...}` (same mapping and body as `restore-deleted`, `WishlistRetentionExpiredError` in `execute()`); no service call, nothing changes. The client shows the generic failure text (D-3) |
| Owner, list `archived` | `409 "Wishlist is archived"` (existing mapping, `WishlistArchivedError`) |
| Not the owner (admin, participant, favorite, stranger, deleted or archived list of someone else) | `404 {"detail": "Wishlist not found"}` |
| Unknown id | `404 {"detail": "Wishlist not found"}` (byte-identical to the previous row) |
| Unauthenticated | the existing auth dependency answer (401), unchanged |
| CSRF missing/invalid | the existing middleware answer (403), list unchanged |
| Retention expired and already purged | row gone from the store: `404` (the client shows the generic failure message, see D-3) |

Route action (pseudo-flow, no new service API):

1. `wl = service._wishlists.get(wishlist_id)` (precedent `record_view`); `None` -> raise
   `WishlistNotFoundError`.
2. `ctx = WishlistAccessPolicy.resolve_context(user, wl)`; `not can_delete(ctx, wl)` -> raise
   `PermissionDeniedError`. Done **before** any status-dependent answer so a non-owner never learns
   that a list is deleted or archived. Both exceptions already map to the one `404` body in `execute()`.
3. `wl.status == DELETED`: if `updated_at + retention_days <= now` (same threshold arithmetic as
   `restore_deleted_wishlist`, `service.py:1173+`) raise `WishlistRetentionExpiredError` (410);
   otherwise skip the service call (idempotent 200).
4. Otherwise `await service.delete_wishlist(wishlist_id, user)`; `WishlistArchivedError` -> 409 by
   `execute()`.
5. `retention_days` from `app.state.settings.wishlist_retention_days` (same `getattr` default 30 as
   the neighbouring routes). Reply body is constant and carries no title, reservation or member data.

Why `DELETE` + 200 JSON: matches the resource semantics and the existing `DELETE /api/history`;
`204` is rejected because `api()` parses JSON unconditionally. The service rule stays the single
authority for deletion; the route only adds classification, which fixes finding 1 and 2 without
changing service behaviour (existing tests that expect `WishlistDeletedError` from the service stay
valid). Concurrent double submit: the store serialises writers (SQLite WAL, one transaction per
`execute`), so the second request sees `DELETED` and returns the idempotent 200.

No HTML/HTMX counterpart: the web (non-Mini App) list screen has no settings block for owners
(`grep settings|delete wishlist_detail.html` only finds item/member controls), and the requirement
names the Mini App list settings. Recorded as Q&A.

### D-2 Retention days in the UI

The confirmation needs the real number before the request. `miniapp.py` always renders
`data-retention-days="{int(settings.wishlist_retention_days)}"` on `<main id="app">` (an `int`, so
it cannot inject markup). **One rule:** `miniapp.js` reads `Number(root.dataset.retentionDays)`; if
it is missing or not a positive integer, `deleteWishlistControls` returns `null` and the delete
action is not offered (the exact number cannot be shown, and a guessed number would be a false
promise). The default 30 appears nowhere in the client. After the request the result message uses
`retention_days` from the response, which is authoritative. Alternative
rejected: adding a field to the list projection (public API contract change, used by every list
read).

### D-3 Mini App UI: where, confirmation, states

**Placement.** `deleteWishlistControls(list)` returns `null` unless `list.role === 'owner'`
(requirement 2; admins keep Save/Cancel only). It is appended **inside the settings section but
outside the `<form>`**, as a last child after `settingsForm(list)`, so it is not in
`.form-actions`, not a submit control, and Enter in a text field cannot trigger it. Structure:

```
section.list-settings-section
  h2, p.section-subtitle, form.wishlist-settings-form (Save, Cancel)
  div.wishlist-delete-zone                      <- new, separated by a top border + spacing
    h3.wishlist-delete-heading  "Delete wishlist"        (aria-labelledby target)
    p.settings-field-hint       one-line danger hint
    button.wishlist-delete-open  "Delete wishlist..."    (outlined danger, like history-clear)
    div.wishlist-delete-confirm[role=group] (built at render time but NOT attached; a click replaces the button with it)
```

The idle trigger reuses the history-clear look (outlined `--danger` on a light surface, not filled,
not `btn-primary`) so it is never mistaken for Save, and its label has the ellipsis/"..." wording of
a step that asks for confirmation. A heading (`h3`) plus a thin `--border-subtle` rule separate it;
the destructive meaning is carried by words and the heading, not only colour.

**Render-time rule (Node harness).** `tests/test_wishlist_detail_ui.py` runs the real `showList`
for role `owner` through `_NODE_HARNESS` in `tests/test_miniapp_i18n_repro.py`, whose fake DOM only
implements `append`, `replaceChildren`, `insertBefore`, `setAttribute`, `focus` (no `replaceWith`,
no `remove`); `tests/test_home_overview_ui.py` uses the same harness for `showHome`. So
`deleteWishlistControls` builds its whole tree at render time with `node()`, `button()`, `append`
and `setAttribute` only (the panel is created detached), and `replaceWith`, `remove`, `focus` and
`insertBefore` live only inside click/keydown handlers that the harness never fires. The home
`tabindex` is a `setAttribute` at render time and is harness-safe.

**Confirmation panel** (in-place, same pattern as `renderHistoryFooter`; the trigger is replaced by
the panel, focus goes to **Cancel**, so the destructive choice is never the default focus):

- `role="group"` with `aria-labelledby` (title) and `aria-describedby` (consequences paragraph),
  so a screen reader announces "Delete wishlist “<title>”?" and the text. `role="alertdialog"` is
  rejected: there is no focus trap or modal inertness here, and the history precedent uses `group`.
- Title line: `t('miniapp.wishlist_delete.confirm_title', {title})` placed with `node('p', text)`
  (`textContent`, never `innerHTML`; the title is the owner's own list name, falls back to
  `miniapp.common.untitled_wishlist` when empty). Long titles wrap (`overflow-wrap: anywhere`).
- Body, three short paragraphs, identical for every list (secrecy):
  1. consequences: disappears for everyone, share and invitation links stop working, any
     reservations are cancelled (generic, no count, no state);
  2. promise (a): restorable from "Recently deleted" within `{days}` days, comes back with its
     wishes and «Gifted» history, with new links, cancelled reservations stay cancelled;
  3. promise (b): after `{days}` days the list and its «Gifted» history are deleted permanently and
     cannot be restored. No "immediately" or "at once" anywhere.
- Buttons in `.wishlist-delete-actions` (flex-wrap, gap .5rem, like `history-confirm-actions`):
  `Cancel` first (focus, neutral), then `Yes, delete wishlist` (filled `--danger`, white text, reuses
  the `history-confirm-yes` rule via a shared selector). Distinct by label, position, fill and
  wording, not by colour alone.
- Escape on the panel = Cancel (same as history); Cancel returns the panel to the trigger and
  focuses the trigger; nothing is sent. Leaving the screen (Back, Save, Cancel of the form) simply
  re-renders `showList`/`showHome`; no state is kept, so a stale panel can never reopen.

**Submit and double-submit guard.** The confirm button is created with `pending(handler, message)`
(`withPending`): it is `disabled` + `aria-busy` + `.is-pending` while in flight and a second tap or
Enter is ignored by the per-control `WeakSet`. Cancel and the Escape handler are disabled while
`deleting` is true (a local flag like `clearing` in the history panel), so the panel cannot be
closed or re-submitted mid-flight, and the trigger cannot be pressed (it is not in the DOM while the
panel is open). Pending text: `miniapp.wishlist_delete.pending` ("Deleting...").

**Success.** On `200`: `await showHome(); status(t('miniapp.wishlist_delete.done', {title, days:
response.retention_days}), 'success'); root.querySelector('h1')?.focus();` (the home `<h1>` gets
`tabindex="-1"` so focus can land there; same pattern as the history screen). The order matches
restore (`showHome()` ends with `status('')`, so the message is set afterwards). `showHome` reloads
lists and `/api/wishlists/deleted`, so the list is absent from "My lists" and present in "Recently
deleted" with days left, with no client-side patching. The message is shown once (a single `status()`
write, replaced by the next status). The title in the message goes through `status()` which uses
`textContent`. If `showHome()` itself fails to load, it shows its own load-failed error and the
success text is still set afterwards (precedent: restore); accepted (R-4).

**Failure.** Any thrown error (network, 404, 409, 403, 5xx): the panel stays open, buttons are
re-enabled (`withPending` finally + the local flag), a `role="alert"` paragraph
`miniapp.wishlist_delete.failed` is inserted before the actions ("Could not delete the wishlist. Nothing
was changed. Try again."), `status('')` is cleared, no success text is shown; Retry is the
same confirm button. After the failure the code calls `confirmBtn.focus()` explicitly (a control that
was `disabled` while pending can lose focus in some engines). For a 404/409 the same generic message is used (never states why: no existence
leak, no reservation talk). A **410** on delete (repeat after the retention window, before purge)
uses the same message, and the client additionally calls `await showHome()` as the restore flow
does on 410 (`miniapp.js:526-528`), so the list is shown as expired/gone instead of a dead panel;
the failure text is then set after the refresh, and no success text appears.

**Archived and non-manager screens.** Nothing is rendered: the settings section exists only for
`manager && status === 'active'` (`miniapp.js:736-737`), and the new block only for owners inside it.

### D-4 i18n keys (EN + RU, same meaning, `miniapp.` prefix so they reach the embedded catalog)

New keys, all required in both tables (parity is enforced by the existing catalog tests):

| Key | EN | RU |
| --- | -- | -- |
| `miniapp.wishlist_delete.heading` | Delete wishlist | Удаление вишлиста |
| `miniapp.wishlist_delete.hint` | Removes this wishlist from your active lists. You can restore it for a limited time. | Убирает вишлист из ваших активных списков. Его можно восстановить в течение ограниченного времени. |
| `miniapp.wishlist_delete.open` | Delete wishlist... | Удалить вишлист... |
| `miniapp.wishlist_delete.confirm_title` | Delete wishlist "{title}"? | Удалить вишлист «{title}»? |
| `miniapp.wishlist_delete.consequences` | The wishlist will disappear for everyone, its share and invitation links will stop working, and any reservations on it will be cancelled. | Вишлист исчезнет у всех, его ссылки для просмотра и приглашения перестанут работать, а все резервирования в нём будут отменены. |
| `miniapp.wishlist_delete.restore_promise` | You can restore it from "Recently deleted" on the home screen within {days} days. A restored wishlist returns with its wishes and "Gifted" history, but with new links; cancelled reservations stay cancelled. | Вы сможете восстановить его в разделе «Недавно удалённые» на главном экране в течение {days} дн. Восстановленный вишлист вернётся с желаниями и историей «Подаренные», но с новыми ссылками; отменённые резервирования не восстанавливаются. |
| `miniapp.wishlist_delete.purge_promise` | After {days} days the wishlist and its "Gifted" history are deleted permanently and cannot be restored. | Через {days} дн. вишлист и его история «Подаренные» будут удалены окончательно, и восстановить их будет нельзя. |
| `miniapp.wishlist_delete.cancel` | Cancel | Отмена |
| `miniapp.wishlist_delete.confirm` | Yes, delete wishlist | Да, удалить вишлист |
| `miniapp.wishlist_delete.pending` | Deleting... | Удаление... |
| `miniapp.wishlist_delete.done` | Wishlist "{title}" deleted. You can restore it from "Recently deleted" within {days} days. | Вишлист «{title}» удалён. Его можно восстановить в разделе «Недавно удалённые» в течение {days} дн. |
| `miniapp.wishlist_delete.failed` | Could not delete the wishlist. Nothing was changed. Try again. | Не удалось удалить вишлист. Ничего не изменилось. Попробуйте ещё раз. |

Wording is final-draft; Step 4 may polish phrasing but not the two promises, the generic
reservations clause, or the absence of "immediately/at once/сразу/немедленно". Existing wording
reused as is: "Recently deleted" = `miniapp.deleted.heading`, so Step 3 tests assert against the
catalog value, not literals. `{days}` always comes from `data-retention-days` or the response (a positive
integer), `{title}` from the list name; both are substituted by `t()` into a plain string and written
with `textContent`. No key mentions reservation state/count/people (verified by a catalog test, see
Test strategy).

### D-5 CSS (`miniapp.css`, tokens only, no literals except the white-on-danger already used)

- `#app .wishlist-delete-zone { margin-top: 1.25rem; padding-top: .75rem; border-top: 1px solid
  var(--border-subtle); min-width: 0; overflow-wrap: anywhere }` (visual separation from the form).
- `.wishlist-delete-heading { margin: 0 0 .25rem; font-size: 1rem }`.
- `#app button.wishlist-delete-open` copies `button.history-clear`: transparent background,
  `border-color: var(--danger)`, `color: var(--danger)`, `margin: 0`, `max-width: 100%`,
  `min-height: var(--touch-target)` (already global, `miniapp.css:42-44`).
- `.wishlist-delete-confirm { min-width: 0 }`, `.wishlist-delete-actions` copies
  `.history-confirm-actions` (flex-wrap, gap .5rem, buttons `margin: 0; max-width: 100%;
  overflow-wrap: anywhere`); the confirm button reuses the filled-danger rule by adding the selector
  to `#app button.history-confirm-yes`. Preferred implementation: reuse the `history-confirm*`
  classes as additional class names where the look is identical, and add only the zone and open
  button rules (smallest CSS).
- `.wishlist-delete-error` reuses `.history-error` (`color: var(--danger); font-weight: 600`).
- Targets: every button keeps the global `min-height: var(--touch-target)` (44 px); at 320 px the two
  buttons wrap onto separate lines (flex-wrap), long titles wrap via `overflow-wrap: anywhere`; the
  zone adds no fixed widths, so no horizontal overflow (the settings section already has
  `min-width: 0; overflow-wrap: anywhere`, `miniapp.css:106-110`).
- Themes: the Mini App shell has a single token skin in browser and Telegram (the same finding as
  WISHENKA-307: no dark/Telegram variables on these screens); using only tokens makes the block
  follow any later theme redefinition. Contrast: `--danger` on the light surface is 7.59:1 (WISHENKA-307
  Research), white on `--danger` the same pair; both above 4.5:1.
- No transition or animation added (nothing to gate behind `prefers-reduced-motion`).

### D-6 Accessibility outcomes

- Reachable by keyboard in DOM order after Save/Cancel of the form: trigger -> (open) Cancel ->
  Confirm. Enter/Space activate; Escape inside the panel cancels; no focus trap is needed because
  the panel is inline and not modal.
- Screen reader: the group is named by the title ("Delete wishlist “X”?") and described by the
  consequences; the choices are two native buttons with explicit labels; pending is announced by the
  existing `#status` live region and `aria-busy`; failure is `role="alert"`; success is announced by
  the polite `#status` plus focus on the home `<h1>`.
- Focus management: open -> Cancel; Cancel/Escape -> trigger; success -> home `<h1>`; failure ->
  `confirmBtn.focus()` is called explicitly after re-enabling; the user is never left
  on a removed element because the whole screen is re-rendered only on success, and then focus is set
  explicitly.
- Not colour-only: heading text, label wording ("Yes, delete wishlist"), outlined (idle) vs filled
  (confirm), position (Cancel first).
- Touch/320 px as above.

### D-7 Observability (Step 6) and logs

Logs only, no metrics backend exists for this area. All fields are ids, counts or enums; never the
title, tokens, user names or reservation data.

| Event | Level | Where | Fields |
| ----- | ----- | ----- | ------ |
| `wishlist_mutation_committed` (existing) | INFO | `execute()` after adding `delete_wishlist` to its set | `operation="delete_wishlist"` |
| `wishlist_deleted_by_owner` (new) | INFO | route, after success | `wishlist_id`, `user_id`, `retention_days`, `outcome` = `deleted` or `already_deleted` |
| `wishlist_status_changed` (existing) | INFO | service, once per real transition | `wishlist_id`, `actor_id`, `from_status`, `to_status` |
| `wishlist_permission_denied` (existing) | WARNING | `execute()` for non-owner | `operation="delete_wishlist"` |
| `wishlist_retention_expired` (existing) | WARNING | `execute()` for a repeat delete after the window | `operation="delete_wishlist"` |
| `wishlist_delete_not_found` (new) | WARNING | route, unknown id | `wishlist_id`, `user_id` |
| `wishlist_archived_mutation_blocked` (existing) | WARNING | `execute()` for the owner of an archived list | `operation` |

`outcome` makes repeats countable without a second `status_changed`. Client side: no telemetry
exists; failures are visible through server logs above. Step 6 documents the new events in
`doc/dev/wishlists.md` event table (~line 1474) and tests them with `caplog` per the `do-testing`
rules, including an assertion that no record contains the list title.

### D-8 Surprise secrecy (invariant analysis)

- Texts: identical for every list; the only variables are the title and the day count; the reservation
  clause is the fixed phrase "any reservations on it will be cancelled". Reviewed keys contain no
  count, no state, no verb implying that something is reserved or bought.
- Response: constant body, no item/reservation data, no member data. No new notification is sent
  (Q5 of the requirements): the route does not call any `notices` code; `service.delete_wishlist`
  does not publish shared events either (`_record_shared_event` is not called there), verified by
  reading the method.
- Pre-existing behaviour kept: deleted lists are hidden from members, favorites and history;
  reservations are cancelled by the service. The owner of a personal list is the recipient: the
  route returns no signal of any cancelled reservation.
- Non-owner paths leak nothing: same 404 body for unknown id, foreign list, deleted list and
  archived list (ownership check precedes the status branch).
- Timing/side channels: a non-owner request performs no write and no service call.

### Requirement-to-design traceability

| Requirement | Design |
| ----------- | ------ |
| 1 Finding the action | D-3 placement: separated zone in the owner settings, outside the form; browser test 1, UI test U1 |
| 2 Owner only | D-3 owner-only render; D-1 ownership check before status, 404 for everyone else; UI test U1 (admin/member), API tests |
| 3 Confirmation | D-3 panel, D-4 keys (consequences, two promises, same text for all lists), D-2 real days; catalog test, UI tests U2-U3, browser test 2 |
| 4 Cancel unchanged | D-3 Cancel/Escape send nothing; browser tests 3 |
| 5 Result | D-3 success flow (home, status, focus), D-1 body with `retention_days` |
| 6 Restoration | existing restore route, unchanged; browser test 5, API round trip |
| 7 Other data unaffected | route touches one list; API test of other lists |
| 8 Secrecy | D-8, D-4 generic clause, catalog test, UI test U3, browser test 8 |
| 9 Failure and repeat | D-3 failure + pending guard, D-1 idempotent 200 / 410 / 404 |
| 10 Which lists | D-3 only active owner lists; archived 409 |
| 11 Languages and themes | D-4, D-5 tokens only |
| 12 Accessibility, touch | D-6, D-5, browser test 7 |

### Docs to update (Step 8)

- `doc/dev/wishlists.md`: add the endpoint to the route list (~lines 60-80) with the status table of
  D-1; replace line 126 ("There is no HTTP delete route"); fix `delete_wishlist` signature
  (`-> None`, currently documented `-> Wishlist`, lines 749-753) and the sentence "invalidates tokens"
  (line 757): links stop because deleted lists are hidden, tokens are rotated on restore; mention
  the route-level idempotency and ownership-before-status order; add the new events to the log table
  (~line 1474); the permission matrix row at line 502 stays true.
- `doc/dev/miniapp.md`: new subsection "Wishlist deletion (WISHENKA-295)": placement in the owner
  settings, inline confirmation, keys `miniapp.wishlist_delete.*`, `data-retention-days`, focus and
  status behaviour, classes `wishlist-delete-*`; update the shell attribute list.
- `doc/dev/testing.md` (Russian section on wishlist/Mini App tests): entries for the two new modules.
- `doc/dev/architecture.md`: only if it enumerates wishlist routes (check at Step 8; otherwise no
  change). `specs/` and `in-docs/` are product docs: no change in this task.

### Test strategy

**API (`tests/test_wishlist_delete_api.py`, pytest, no browser).** Cases listed under Failing Repro.
Details: parametrise non-owner callers (admin member, plain member, stranger, favorite viewer) and
assert status 404 with `response.json() == unknown_id_response.json()`; secrecy test creates one list
with an active and a purchased reservation and one empty list and asserts the two success bodies
differ only in `wishlist_id`; other-lists test creates two lists of the owner and one of another
user and compares their projections before/after; idempotency test compares `updated_at` and counts
`wishlist_status_changed` log records (1) via `caplog`; CSRF test sends the DELETE without the header.
Existing test file `tests/test_wishlist_deleted_restore.py` provides the restore half.

**Catalog (`tests/test_wishlist_delete_i18n.py` or in the API module, no browser).** All
`miniapp.wishlist_delete.*` keys exist in `en` and `ru` with identical `{param}` sets; none of the
texts contains reservation words per a deny-list, except exactly two keys: `consequences` and
`restore_promise` (requirement 3a needs "cancelled reservations stay cancelled"). Each of those two
may contain only the fixed generic clause (EN "any reservations" / "cancelled reservations stay
cancelled", RU "все резервирования" / "отменённые резервирования не восстанавливаются"); the test
asserts the reservation words occur only inside those literal clauses, and that no key in the
family contains count/state/person wording (digits next to reservation words, "bought", "purchased",
"куплен", "кто", "who", "by whom"); promise keys do not contain "immediately", "at once", "сразу",
"немедленно"; both promises contain `{days}`.

**Node-harness UI (`tests/test_wishlist_delete_ui.py`, new, `pytestmark = pytest.mark.timeout(20)`,
no browser marker).** It reuses `_NODE_HARNESS` from `tests/test_miniapp_i18n_repro.py` and patches it
by string replacement exactly as `tests/test_wishlist_detail_ui.py:20-25` does. The shared harness
sets `rootEl.dataset` to `{locale, bot, miniapp}` only (`test_miniapp_i18n_repro.py:107-111`), so
under the D-2 rule every existing owner-screen harness test simply renders no delete zone and is
unaffected. The new module's patch adds a scenario field `retentionDays` (copied into
`rootEl.dataset.retentionDays` when set), a minimal `replaceWith` on the fake element and a
`clickSelector` scenario step so that the trigger click can build and attach the panel, plus a
scenario `fetch` stub for the `DELETE` reply. Parametrised `ru`/`en`.

- **U1 gating:** with `retentionDays="30"`: owner of an active list renders `.wishlist-delete-zone`
  inside `.list-settings-section` and outside the form; admin, member, favorite and archived render
  none; with the attribute missing, `"0"` or `"abc"` an owner renders none (D-2).
- **U2 real number:** with `retentionDays="7"`, after the trigger click both promise paragraphs
  contain `7` (never `30`), and after a stubbed `200 {"retention_days": 7}` the `done` message uses
  the response value; a response with another number (for example 5) shows 5.
- **U3 shared vs personal:** the same run for a personal list and for a collaborative list (the
  projection of the same owner with a non-empty `members` array and a shared-list flag; the panel
  code never reads either, which is exactly what the test proves); panel text and `done` message are identical after normalising the title, in `ru` and `en`.
  Runner: this Node harness module, not the browser.

**CDP browser (`tests/test_wishlist_delete_browser.py`).** Marker and `timeout(45)` as required by
`tests/test_browser_prerequisites.py`; parametrised `ru`/`en` and widths 320 and 375:

1. Owner list screen: `.wishlist-delete-zone` is inside `.list-settings-section`, outside the form
   (`!form.contains(zone)`), outlined (computed `background` transparent) and not in `.form-actions`;
   (admin/member and invalid-retention gating is in UI test U1, because `seed_wishlist`
   (`tests/conftest.py:265+`) creates only an owner list and a viewer token, so a browser test cannot
   cheaply seed admin/member; the API test seeds those roles through the service); archived list has no settings section.
2. Open: click trigger -> panel appears, trigger gone, `document.activeElement` is Cancel, group
   accessible name (CDP `Accessibility.getFullAXTree`) contains the exact title, text contains the
   catalog title/consequences/promises with `{days}` = 30 (the `wishlist_server` fixture,
   `tests/conftest.py:224-240`, has no retention override, so it runs the default), confirm button is not focused. A title with `<b>x</b>&amp;`
   renders literally (no element created).
3. Cancel and Escape: no `DELETE` request is made (request log via fetch wrapper or server access
   recorder), list status via API stays `active`, trigger refocused.
4. Confirm: click the filled button; during a held response (`fetch` override as in
   `tests/test_personal_settings_browser.py:606-625`) the button is `disabled`, `aria-busy=true`,
   Cancel disabled; a second click/Enter issues no second request (count 1). On release: URL stays
   `/`, `#app h1` is the home title and has focus, `#status` text equals the catalog `done` message
   with title and days, `data-kind="success"`, the list card is not among "My lists", "Recently
   deleted" shows it with the days-left text, and `status` is not repeated after a click on Restore.
5. Restore round trip in the same test: click `Restore` -> list is back in active lists.
6. Failure: force `DELETE` to fail (500 and network error): panel stays, `role="alert"` with the
   `failed` text, no success text, button re-enabled and `document.activeElement` is the confirm button, a
   retry succeeds.
7. Layout: at 320 px no horizontal overflow (`scrollWidth <= innerWidth`), all buttons >= 44 px
   high, a 200-character title with no spaces wraps inside the panel; focus ring present on the
   buttons (`outlineStyle != none`).
8. Secrecy in UI: run the open/confirm flow on a list with a reservation (seeded through the service)
   and on one without; the panel `innerText` and the result `#status` text are identical after
   normalising the title.

Server-side repeated confirm is covered by the API test; the browser tests assert only the client
guard.

### Existing tests that may be affected (all must stay green; run list for Step 4)

- `tests/test_wishlist_detail_browser.py` (owner screens now have an extra button and block inside
  `.list-settings-section`: the touch-target and "mobile order" test at lines 18-60 iterates buttons
  of that section and `.form-actions` groups; the wrap/overflow rules must still hold).
- `tests/test_wishlist_detail_ui.py` (`_detail()` runs the real `showList` in the Node harness;
  new classes are additions; `tests/test_wishlist_detail_ui.py:140-148` is only an order check of the
  top-level sections (header, wishes, settings, share, members), unaffected because the new block is
  nested inside the settings section; the archived test asserts the three admin classes are absent,
  which stays true). It and `tests/test_home_overview_ui.py` run `miniapp.js` in `_NODE_HARNESS`
  (`tests/test_miniapp_i18n_repro.py`); see the render-time rule in D-3.
- `tests/test_wishlist_deleted_restore.py::test_deleted_i18n_keys_and_miniapp_ui_wiring` (static wiring
  of the deleted section; unaffected, must be re-run) and the `miniapp.deleted.*` keys.
- `tests/test_miniapp_i18n_repro.py` and the catalog parity tests (new keys must exist in both).
- Mini App shell tests that compare the served HTML (`wishenka/web/routes/miniapp.py` tests under
  `tests/test_miniapp*`, `tests/test_bot_menu_miniapp_e2e_browser.py`): a new attribute on `<main>`.
- `tests/test_home_overview_browser.py` / `tests/test_home_overview_ui.py` (home `<h1>` gets
  `tabindex="-1"`; they read `h1.innerText`, unaffected, but the focus assertions must be reviewed).
- `tests/test_wishlist_api.py` (any test asserting that DELETE on `/api/wishlists/{id}` is 405/404 or
  that a route list is exact; grep at Step 3).
- `tests/test_cross_screen_comfort_browser.py` fit/contrast tests if they open an owner list screen.

### Risks

- **R-1 Accidental deletion.** Mitigated by: separate block outside the form, outlined trigger, a
  mandatory confirmation with the exact title, Cancel as default focus, no typing requirement
  (Q10 of the requirements).
- **R-2 Wrong day count.** The shell always renders `data-retention-days`. If it is missing or not
  a positive integer (for example a stale cached shell), the client does not offer the delete action
  at all, so a wrong or guessed number is never shown; the default 30 appears nowhere in the client.
- **R-3 Route classification uses a private service member** (`service._wishlists`), as
  `record_view` and others do; a later repository-backed service must offer a public read. Accepted,
  consistent with the surrounding routes; listed for Step 7 as potential debt.
- **R-4 `showHome()` load failure after a successful delete** shows the error status and then the
  success text overwrites it (restore precedent). The deletion is committed, the text is true.
- **R-5 Race: list changed meanwhile** (owner changes role, archived by an admin between open and
  confirm): service raises, user sees the generic failure, list state is whatever the server holds;
  a retry then yields the correct answer (409/404 generic failure). Acceptable and matches
  requirement 9.
- **R-6 Idempotent success hides a restore race** (owner deletes, restores on another device, taps
  delete again on the first device: it is deleted again, which is what the owner asked for).
- **R-7 Surprise invariant**: covered by D-8; the residual risk is a future key edit adding
  reservation wording, guarded by the catalog test.
- **R-8 Retention window sliding.** A repeat delete must not update `updated_at`; guarded by the route
  not calling the service for `DELETED` and by the idempotency test.
- **R-9 Overlap with sprint tasks** (WISHENKA-296 create-flow bug touches `showHome`/`showList` in
  `miniapp.js`; sprint runs tasks sequentially). The changes here add one function, one call site in
  `showList`, one `tabindex` on the home `<h1>`; no existing function body is restructured.

## Q&A

- **Why a new route and not reuse `POST /api/wishlists/{id}/{operation}`?** That route is for the
  archive/restore status toggle for owner and admin (`require_member(manager=True)` would let an
  admin reach it) and returns 409 for invalid state; deletion is owner-only and idempotent.
  `DELETE` on the resource is the natural verb and matches `DELETE /api/history`.
- **Why 200 for the repeat instead of 404?** Requirement 9: repeating or double-tapping must end in
  the same state without errors. 200 is returned only to the owner; everyone else gets 404.
- **Why not change `WishlistService.delete_wishlist` to be idempotent?** It would change a domain
  contract used by existing tests and by cleanup flows, and the permission-before-status order is
  a route concern; the route adapter is the smallest change. A service-level cleanup can be debt.
- **Why inline confirmation and not a modal?** Existing in-place pattern (history clear), no focus
  trap code, works the same in Telegram and in a mobile browser; the confirmation is reachable and
  announced via group name/description.
- **Why not type-the-title confirmation?** Requirement Q10: not needed; the exact title is shown.
- **Is the web (HTMX) list screen changed?** No: it has no owner settings block and the
  requirements target the list settings of the Mini App.
- **Does the standalone `/settings` page change?** No (it is the personal settings screen).
- **Open questions for the gate owner.**
  - OQ-1: confirm that the delete action is for the Mini App list screen only (no HTMX equivalent).
  - OQ-2 (closed): `data-retention-days` on `<main id="app">` is always rendered; if it is missing
    or not a positive integer the client does not offer the delete action. No fallback to 30 in the
    client. Reopen only if the product owner prefers a field on the owner projection.
  - OQ-3: confirm that an owner deleting an archived list gets 409 plus the generic failure text
    (requirement Q3 says restore first), instead of a dedicated hint.
  - OQ-4: confirm that the idempotent `already_deleted` answer is `200` (not `204`/`409`), and that a
    repeat after the retention window but before purge is `410 retention_expired` (consistent with
    restore), not `200`.
