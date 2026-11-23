# WISHENKA-295: Failing repro (Step 3)

Three new modules, no production code touched (`wishenka/` is unchanged, `git status` shows only
`tests/test_wishlist_delete_{api,ui,browser}.py` and `ai-tasks/`). They assert the behavior of
`20-architecture.md` (D-1 .. D-6, Test strategy) and fail on current code because the feature is
missing.

## Inventory

### `tests/test_wishlist_delete_api.py` (`timeout(30)`, no browser; 31 cases, all red)

Real app + store via `create_app`, six seeded users (owner, admin, member, other owner, gifter,
stranger), users and roles through the existing invitation flow, reservations through the service.

- Owner flow (R5, R6, R7): `DELETE /api/wishlists/{id}` -> 200
  `{"status": "deleted", "wishlist_id", "retention_days": 30}`; list gone from `GET /api/wishlists`
  and `GET /api/wishlists/{id}` (404), present in `/deleted` with `days_remaining == 30`, DB status
  `deleted`; hidden from admin and member, share and invitation links 404; other lists of the owner
  and of another user unchanged; reservations (active and purchased) of that list `cancelled`,
  others `active`; `retention_days` follows settings (7); restore round trip (200, active, new
  tokens, item kept, reservation still cancelled).
- Idempotency (R9): three owner DELETEs -> 200 with identical bodies, `updated_at` unchanged, exactly
  one `wishlist_status_changed` (caplog); repeat after the retention window but before purge ->
  410 `retention_expired`, row still `deleted` with the old `updated_at`, no status change logged.
- Who may delete (R2): admin, member, stranger, gifter and a favorite viewer (own test) -> 404 byte-identical to an unknown id,
  list unchanged; unknown id 404 `{"detail": "Wishlist not found"}`; anonymous 401; non-owner on a
  deleted or archived list -> same 404 (no 409 or existence leak); owner on an archived list -> 409,
  status stays `archived` (R10).
- CSRF: cookie session + Origin, no Bearer: missing token, wrong token and foreign Origin -> 403 and
  list unchanged; valid token -> 200. The three 403 checks already pass today (the CSRF middleware runs before
  routing); the test is red only through the final 200 assertion.
- Secrecy (R8): replies for a list with an active and a purchased reservation and for an empty list
  are identical except `wishlist_id`, only the three constant keys, no reservation words.
- Shell (D-2): `GET /` has `data-retention-days="{N}"` on `<main id="app">` for 30 and 7.
- Catalog (D-4, R3, R8, R11): all 12 `miniapp.wishlist_delete.*` keys exist in en and ru, reach
  `miniapp_catalog()`, same `{param}` sets; placeholders (`title`, `days`); no "immediately / at
  once / сразу / немедленно", no digits, "bought", "who" and similar; reservation words only inside
  the two fixed clauses of `consequences` and `restore_promise`; both promises carry `{days}`, name
  "Recently deleted" and «Gifted/Подаренные», the purge promise says permanent, the consequences
  mention links; confirm differs from cancel.

### `tests/test_wishlist_delete_ui.py` (`timeout(20)`, Node harness, no browser marker; 49 cases)

Patches `_NODE_HARNESS` by string replacement (each anchor asserted): `retentionDays` dataset
field, `replaceWith` / `remove` / `removeAttribute` / `focus` on the fake element, a `steps` runner
(click by class or exact button text, `twice`, Escape keydown), a `fetch` stub for
`DELETE /api/wishlists/1` and `/api/wishlists/deleted`. Parametrised en/ru.

- Control (green): patched harness clicks Back and the deleted section is served.
- U1 gating: owner + active + valid retention -> exactly one `.wishlist-delete-zone` inside
  `.list-settings-section`, not inside the form or `.form-actions`, trigger button
  `.wishlist-delete-open` with catalog text, heading, no `btn-primary` (red). Regression guards
  (green today, must stay green): admin, member, favorite, archived owner, archived admin render no
  zone; owner with retention missing, empty, `0`, `abc`, `-5`, `3.5`, `30 days` renders none.
- U2 real number: with `retentionDays="7"` the panel (after the trigger click) holds the exact
  `confirm_title`, `consequences`, `restore_promise` and `purge_promise` with 7, never "30"; role
  `group` with `aria-labelledby`/`aria-describedby`; trigger replaced; no request yet; buttons are
  Cancel then confirm, focus on Cancel; success message uses the response value (5), status kind
  `success`, one `DELETE /api/wishlists/1` with `X-CSRF-Token: csrf-123`, home screen and
  "Recently deleted" shown; title `<b>x</b>&amp;` is text only; double confirm sends one request;
  failure (500 and network error) keeps the panel, one `role="alert"` with the `failed` text, no
  success text, confirm enabled and focused; a 410 reply refreshes the home screen and shows the
  generic failure text, never success; Cancel and Escape send nothing, restore the trigger and focus it.
- U3: personal and shared (non-empty members) lists give identical panel and result texts after
  normalising the title.

### `tests/test_wishlist_delete_browser.py` (`timeout(45)` + `browser` marker; 15 cases, all red)

Helpers only from `tests/browser_cdp.py`, `tests/browser_screens.py` (`provision_user`,
`open_miniapp`, `api`, `width_problems`, `CONTRAST_JS`) and `tests/browser_helpers.py`; own
`open_list` fixture, no imports from other test modules. Real Mini App, cookie session.

1. Owner list screen (en 375, ru 320): zone in the settings section, outside form and
   `.form-actions`, outlined (transparent background), >= 44 px, differs from Save, nothing shown
   before the click.
2. Open (en, ru): panel text has the exact title (`<b>x</b>&amp; 'quoted'` literal, no `<b>`
   element), consequences, both promises with 30, buttons Cancel then confirm, Cancel focused,
   trigger replaced, targets >= 44 px, AX tree group named with the exact title, no DELETE yet.
3. Cancel and Escape: no DELETE request reaches the server, trigger back and focused, status empty,
   list still `active`.
4. + 5. Confirm (en 375, ru 320): held response -> confirm `disabled`, `aria-busy=true`, Cancel
   disabled; second click, Enter and Escape change nothing (1 call); after release path `/`, home
   `h1` focused, `#status` equals the `done` text with `data-kind=success`, no card in "My lists",
   "Recently deleted" card with the days-left text, server status `deleted`, exactly one DELETE;
   Restore brings the list back, status text is the existing `restored` message.
6. Failure (500, network): panel stays, `role="alert"` with `failed`, no success status, confirm
   enabled and focused, list `active`; switch to pass-through and retry succeeds.
7. Layout (en 320, ru 320, en 375, long title with an unbroken 80-character word): no horizontal
   overflow, clipped text or target under 44 px (`width_problems(..., targets=True)`), long title
   wraps in the panel, Tab reaches the confirm button with a visible focus ring, no contrast
   failure on delete/confirm/danger elements.
8. Secrecy (en, ru): a list with a viewer reservation and a list without give identical panel and
   result texts after normalising the title.

## How it was run

```
make test-serial PYTEST_ARGS="tests/test_wishlist_delete_api.py -q"
make test-serial PYTEST_ARGS="tests/test_wishlist_delete_ui.py -q"
make test-serial PYTEST_ARGS="tests/test_wishlist_delete_browser.py -q"
make test-serial PYTEST_ARGS="tests/test_wishlist_delete_api.py tests/test_wishlist_delete_ui.py tests/test_wishlist_delete_browser.py"
make analyze
```

`make analyze`: ruff check, ruff format check and mypy on 265 files all pass.

## Red evidence (combined run: 70 failed, 25 passed, 95 collected)

| Module | Red | Green | Reason of the red |
|---|---|---|---|
| API | 31 | 0 | `DELETE /api/wishlists/{id}` (also for the favorite viewer) answers `405 Method Not Allowed` (every route and CSRF case; setup, seeding and the sibling routes work); `<main id="app">` has no `data-retention-days`; `miniapp.wishlist_delete.*` keys missing in en and ru (`missing en keys: [...]`) |
| UI | 24 | 25 | no `.wishlist-delete-zone` rendered (`assert 0 == 1`); click steps report `a click target is not rendered yet (feature missing): not found: {"cls":"wishlist-delete-open"}`; the 25 green are the harness control plus the non-owner and invalid-retention guards |
| Browser | 15 | 0 | `no .wishlist-delete-zone in the owner's settings` / `no .wishlist-delete-open trigger in the owner's settings (feature missing)`, reached after Mini App home, card click and the settings section loaded |

No red case is a fixture, import or syntax error: setup (users, invitations, reservations, long
and markup titles, Mini App open) completes in every case before the first feature assertion.
Existing suites were not changed.

## Mapping to requirements

| Requirement | Tests |
|---|---|
| 1 Finding the action | UI U1 zone, browser 1 |
| 2 Owner only | API non-owner/unknown/anonymous/deleted/archived, UI non-owner guards |
| 3 Confirmation (title, consequences, two promises, real days, same text, two choices) | API catalog tests, UI U2/U3, browser 2 |
| 4 Cancel unchanged | UI cancel/Escape, browser 3 |
| 5 Result | API owner flow, UI success, browser 4 |
| 6 Restoration | API restore round trip, browser 5 |
| 7 Other data unaffected | API other lists, hidden from members, links stop |
| 8 Secrecy | API reply identity, catalog deny-list, UI U3, browser 8 |
| 9 Failure and repeat | API idempotency and 410, UI/browser failure, double submit |
| 10 Which lists | API archived 409, UI archived guard |
| 11 Languages | API catalog en/ru parity, UI and browser run en and ru |
| 12 Accessibility, touch, 320 px | UI group/focus, browser 2 (AX name), 7 (layout, targets, focus ring, contrast) |
| D-2 retention days | API shell attribute, UI invalid retention guards and the real number |
| D-7 observability | only the `wishlist_status_changed` count is asserted here; the new log events are Step 6 |

## Notes for Step 4

- Test hooks the implementation must provide (from the architecture): classes
  `wishlist-delete-zone`, `wishlist-delete-open`, `wishlist-delete-confirm` (the `role="group"`
  panel), `wishlist-delete-actions` with Cancel as the first and the confirm button as the second
  button; the failure alert is a `role="alert"` element inside the panel; home `h1` focusable.
- The browser cases after the first interaction (open, hold, failure, layout, secrecy) cannot be
  proven against missing code; the first Step 4 run may need small test-only adjustments of
  selectors or waits, reviewed against the architecture.
- Archived-list absence of the settings section in the browser is covered by the Node harness
  (UI guard), not by a browser case.
