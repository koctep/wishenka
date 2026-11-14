# WISHENKA-108: Technical Debt Analysis

Scope: `wishenka/web/static/wishlist.js`, `wishenka/web/templates/base.html`,
`partials/item_card.html`, `wishlist_detail.html`, `share_wishlist.html`,
`tests/test_wishlist_static_script.py` and the location-only edits in
`tests/test_wish_items_list_reorder_ui.py:136-140` and
`tests/test_wish_card_giver_controls.py:502`. Compared against `20-architecture.md` and
`10-requirements.md`.

Timeout markers (grep `pytestmark` over the three test files of this task):
`test_wishlist_static_script.py:28`, `test_wish_card_giver_controls.py:30` and
`test_wish_items_list_reorder_ui.py:30` each declare a module-level
`pytestmark = pytest.mark.timeout(30)`. No timeout-marker BLOCKER.

Pre-existing failures: none (full suite 523 passed, per the task brief; not re-run in this step,
no code changed). The untracked `core` file in the repository root (197,693,440 bytes,
`ls -l core`) is already ticketed as WISHENKA-126 and is not duplicated here. For `td-99-commit`:
stage files by explicit path so `core` is never added.

## Shortcuts Taken

- **Behaviour parity is proven by string matching and one throwaway manual run, not by
  automated execution of the JS.** There is no JS runner. The only dynamic evidence is the manual
  Chromium/CDP sanity run recorded in the roadmap (htmx stubbed, CDN blocked, not committed).
  Real htmx swaps, real HTML5 drag-and-drop events and the `swapWishCard` interaction are not
  covered by any automated test. Owned by WISHENKA-110 (Playwright/CDP tests); not duplicated.
- **The `console.warn` branch has no test** (`wishlist.js:93-104`: non-numeric or missing
  `data-wishlist-id`, or `window.htmx` absent; card is not moved, warning is written). The same
  gap holds for the `drop` guards (`wishlist.js:87-90`). Covered by the WISHENKA-110 scope.
- **Remaining inline script in `base.html`.** One inline `<script>` stays at
  `base.html:12-129`: CSRF fetch and `htmx:configRequest` (lines 13-23),
  `reservationRequestPath` (26), `swapWishCard` (35), reservation `htmx:afterRequest` handlers
  (49 onward). This was out of scope on purpose (`10-requirements.md`, "Out of scope"), but it
  means a strict CSP without `'unsafe-inline'` for scripts is still not achievable. Recorded as
  follow-up 1.
- **Remaining inline `onclick` attributes in modals** (verified by
  `grep -rn "onclick\|onkeydown\|onsubmit\|onchange\|oninput\|onload" wishenka/web/templates`;
  no `on*` handler remains outside these six; `base.html` has none):
  - `partials/item_edit_modal.html:11`, `:82`, `:96`, `:189` (close modal; quantity minus/plus
    with inline `parseInt` logic and hardcoded bounds `min_quantity` and `1000`),
  - `partials/item_archive_modal.html:32` (close modal),
  - `partials/item_preview_card.html:56` (clear quick-add preview).
  They are rendered only when the modal or preview is opened, so the wishlist pages themselves
  carry no inline handlers (test C proves this for the page HTML only, not for modal partials).
  They are also an obstacle to a strict CSP. Recorded in follow-up 1.
- **`window.htmx` and the CDN scripts are loaded synchronously, `wishlist.js` with `defer`**
  (`base.html:8-11`). This is consistent: classic scripts run in order, deferred scripts run
  after parsing, so `wishlist.js` always executes after htmx when the CDN is reachable, and
  `window.htmx` is checked at drop time. Judged: not a defect. The synchronous CDN scripts
  (telegram, htmx, json-enc from `unpkg.com`, no SRI) block parsing and are a pre-existing
  condition outside this task; noted only so it is not mistaken for new debt.

## Code Quality Issues

- **Deviation from architecture: `getAttribute` instead of `dataset`.** The architecture says the
  id is read from `list.dataset.wishlistId` (`20-architecture.md`, "DnD", item 1); the code uses
  `list.getAttribute('data-wishlist-id')` (`wishlist.js:92`). Functionally identical for this
  attribute, and the static test accepts either (`'wishlistId' in body or 'data-wishlist-id' in
  body`, `test_wishlist_static_script.py:142`). Same style as the rest of the file
  (`getAttribute('aria-expanded')`, `getAttribute('data-item-id')`). Recorded as an accepted
  deviation, no action required.
- **Hardcoded API prefix and selectors in JS.** The URL `/web/wishlists/${id}/items/reorder`
  (`wishlist.js:112`) duplicates the route defined server-side (`wishenka/web/routes/items_ui.py:38` router prefix and `:861` route
  `/items/reorder`); a route rename would break reordering silently (the browser would get a
  404 and the UI had already reordered). The architecture accepted this explicitly ("путь
  остаётся в JS как префикс API"). Selectors are hardcoded as well: `#items-list` (`:76`, `:85`,
  `:113`), `.item-card` (`:86`, `:110`), `.item-card[draggable="true"]` (`:66`),
  `.item-card-details` (`:33`); only the first three constants are named
  (`SUMMARY_SELECTOR`, `TOGGLE_EXCLUSION`, `WISHLIST_ID_PATTERN`, `:11-13`). Cheap improvement:
  expose the reorder URL as `data-reorder-url="{{ url_for(...) }}"` on `#items-list` next to
  `data-wishlist-id`, which also removes the numeric-id regex. Follow-up 3.
- **Slight inconsistency in guards for `event.target.closest`.** `findSummary`, `dragstart` and
  `dragover` guard with `event.target.closest ? ... : null` (`wishlist.js:45`, `:65`, `:76`), but
  `toggleWishCard` calls `event.target.closest(...)` unguarded (`:25`). It is only reached after
  `findSummary` succeeded, so the target is an element and there is no bug. Low priority tidiness.
- **Long `drop` handler.** The handler at `wishlist.js:81-117` mixes drop-target resolution,
  validation, DOM mutation and the htmx call, and builds the warning with a small `causes`
  array. Readable at 37 lines; extracting `validateReorder()` and `submitReorder()` would help
  once touch DnD (WISHENKA-109) reuses the same logic. Not worth a separate ticket; address
  inside WISHENKA-109.
- **Module-level mutable `dragged`** (`wishlist.js:16`) is reset on `drop` and `dragend`; if the
  source card is removed from the DOM mid-drag by a concurrent htmx swap, `dragend` may not fire
  on it and the variable stays set until the next `dragstart`/`drop`. Not reproduced here; I
  have not verified the browser behaviour. Mention only for the WISHENKA-110 scenarios.

## Missing Tests

- **No automated test for real behaviour of `wishlist.js`**: toggle on click and Enter/Space,
  exclusion of interactive targets, `preventDefault` only for keydown, DnD drop calculation
  (`clientY` midpoint, `insertBefore`), htmx POST payload, `console.warn` branch. WISHENKA-110
  owns this (Playwright/CDP).
- **`tests/test_wishlist_static_script.py` is string matching and therefore brittle in places.**
  - `"' '" in body` (line 133) and `"drop" in body` (line 137) pass on almost any text; they do
    not prove the Space key or the drop handler (for example a comment would satisfy them).
  - The selector check `EXCLUSION_SELECTOR in body` (line 131) breaks on any harmless reformat
    (reordered selector list, double quotes, a constant split across lines) while behaviour stays
    the same; conversely it passes if the selector is only in a comment.
  - Markers such as `"/items/reorder"` and `"window.location"` are searched in the whole body,
    comments included.
  - `tests/test_wish_items_list_reorder_ui.py:137` asserts `"onclick" not in html` as a plain
    substring over the whole page; a wish title containing the text "onclick" would fail it
    (test C in the new module correctly inspects attributes through BeautifulSoup).
  - The inline-script absence checks (test A, lines 100-104) are the stronger kind: they check
    the output of the server and fail on regression of the extraction.
  Judged acceptable as a stopgap given the architecture's explicit test strategy
  ("смысловые признаки"); it should be replaced or complemented by behavioural browser tests
  from WISHENKA-110, after which the string asserts on `wishlist.js` contents can be deleted.
  Follow-up 4.
- **Modal partials are not covered by the "no inline handlers" test** (test C requests only the
  owner and share pages, whose HTML does not contain the modals). Becomes relevant when follow-up
  1 removes the modal `onclick` attributes.
- **No test that `data-wishlist-id` survives the OOB swap after archive** beyond the existing
  hx-swap guard (`test_guard_no_swap_replaces_items_list_container`, lines 186-212): the guard
  checks `hx-swap` values and fragment ids, not the live behaviour. Part of WISHENKA-110.

## Performance Concerns

- **`Cache-Control: no-store` applies to `/static/*`** (`wishenka/web/security.py:79` sets it on
  every response, including the mount at `wishenka/web/app.py:201`), so `wishlist.js`
  (3,868 bytes) is re-downloaded on every page load; the requirement's wording about a cacheable
  resource is not realised in practice. Judgement: **NON-BLOCKER, low value for now.** Before the
  change the same code (about 90 lines) was shipped inline in every HTML response with
  `no-store` as well, so there is no regression, and the file is small. A real fix needs a policy
  change (exclude `/static` from `no-store`, or use `Cache-Control: public, max-age=...` with a
  version or content hash in the URL, since the repository has no cache-busting today: neither
  `miniapp.css` nor `miniapp.js` has one). That also affects `miniapp.css` and `miniapp.js`, so
  it is a project-wide static-assets decision, not a `wishlist.js` task. Follow-up 2.
- No other concerns: delegated listeners on `document` are constant-cost; the `keydown` handler
  returns early for other keys; the `click` handler does one `closest` per click.

## Deviations from Architecture

Checked against `20-architecture.md`:

- Implemented as designed: new `wishenka/web/static/wishlist.js` (IIFE, `'use strict'`, no
  globals); `base.html:11` has `<script src="/static/wishlist.js" defer>` after the htmx and
  json-enc tags and before the remaining inline block; `onclick`/`onkeydown` removed from
  `item_card.html`; `data-wishlist-id="{{ wishlist.id }}"` on `#items-list` in
  `wishlist_detail.html:27` and `share_wishlist.html:27`; id validated by `/^\d+$/` and checked
  together with `window.htmx` before `insertBefore` (`wishlist.js:92-107`); no `window.location`
  in the file; `toggleWishCard` is no longer global (no other template or code references it,
  `grep -rn toggleWishCard wishenka tests`).
- Deviation 1 (accepted): `getAttribute` instead of `dataset` (see Code Quality).
- Deviation 2 (accepted, improvement): the warning text names the exact cause (`causes` list,
  `wishlist.js:94-101`); the architecture only said `console.warn`. Recorded in
  `50-observability.md`.
- Deviation 3 (accepted, not a behaviour change): the architecture planned the reorder tests
  edit as "check the page references `/static/wishlist.js`"; the test additionally asserts
  `"onclick" not in html` (`test_wish_items_list_reorder_ui.py:137`), see the brittleness note.
- Not a deviation but a stale artifact: developer documentation still describes the old
  location (`doc/dev/miniapp.md:443`, `doc/dev/wishlists.md:316`, `doc/dev/reservations.md:335`
  say `toggleWishCard` lives in `base.html`). This is the planned Step 8 scope
  (`20-architecture.md`, Implementation Plan, item 6), not debt.

## Hardcoded Values

- `/web/wishlists/${wishlistId}/items/reorder` (`wishlist.js:112`), see follow-up 3.
- Selectors and class names (`.item-card`, `.item-card-summary`, `.item-card-details`,
  `#items-list`, `[data-no-toggle]`), keys `'Enter'` and `' '`, swap mode `'innerHTML'`,
  field name `item_ids` (must match the backend form field). All form the documented DOM
  contract in the architecture ("Модули и ответственность").
- `WISHLIST_ID_PATTERN = /^\d+$/` accepts `0` and leading zeros; the server remains the
  authority (returns an error for an unknown wishlist). Harmless.
- Script URL `/static/wishlist.js` without version (see Performance).
- Quantity bounds `1000` and `min_quantity` inside the modal `onclick`
  (`item_edit_modal.html:82`, `:96`), outside this task; part of follow-up 1.

## Out of Scope (existing tickets, referenced not duplicated)

- Touch-friendly drag-and-drop for mobile and Telegram: **WISHENKA-109**. HTML5 `dragstart`,
  `dragover`, `drop` do not fire on most touch devices, so reordering through DnD does not work
  there (move up/down buttons exist as the alternative, `item_card.html`, `hx-target="#items-list"`
  with `innerHTML`).
- Browser-level (Playwright/CDP) end-to-end tests of toggle and DnD: **WISHENKA-110**.
- Refactoring `items_ui.py`/`store.py`: **WISHENKA-112**. Checked: this task changes no Python
  production code and the reorder endpoint is untouched, so there is no overlap to record.
- Untracked `core` file: **WISHENKA-126**.

## Follow-up Tasks

There are no BLOCKER items. Every item below is NON-BLOCKER; none prevents Step 8, the commit,
or closing WISHENKA-108.

1. **NON-BLOCKER:** Move the remaining inline script to static files and remove the remaining
   Jira: [WISHENKA-140](https://pypost.atlassian.net/browse/WISHENKA-140)
   inline `onclick` handlers, so a strict CSP (no `'unsafe-inline'` for scripts) becomes
   possible. Inline script: `base.html:12-129` (CSRF, reservations and giver controls,
   `swapWishCard`). Inline handlers: `item_edit_modal.html:11,82,96,189`,
   `item_archive_modal.html:32`, `item_preview_card.html:56`. Then make the policy itself
   (CSP header) a separate step, and extend test C to the modal partials. The existing tests
   that read inline JS (`base_script()` in `tests/test_reservations_cabinet_ui.py`,
   `inline_script()` in `tests/test_wish_card_giver_controls.py`) must be rewritten to read the
   static file.
2. **NON-BLOCKER:** Decide the caching policy for `/static/*`: exclude static files from
   Jira: [WISHENKA-139](https://pypost.atlassian.net/browse/WISHENKA-139)
   `Cache-Control: no-store` (`security.py:79`) and add a version or content hash to asset URLs
   (`miniapp.css`, `miniapp.js`, `wishlist.js`). Low priority; combine with follow-up 1 when the
   number of static scripts grows.
3. **NON-BLOCKER:** Remove the hardcoded reorder URL from `wishlist.js`: render
   Jira: [WISHENKA-141](https://pypost.atlassian.net/browse/WISHENKA-141)
   `data-reorder-url` on `#items-list` from the route table, read it at drop time, drop the
   numeric regex, and add a server-side test that the attribute resolves to the reorder route.
   Best done together with WISHENKA-109 (touch DnD reuses the same submit path).
4. **NON-BLOCKER:** Replace the string-matching assertions on `wishlist.js` content in
   Jira: noted as a comment on [WISHENKA-110](https://pypost.atlassian.net/browse/WISHENKA-110) (no new issue).
   `tests/test_wishlist_static_script.py` (lines 129-144, notably `"' '"` and `"drop"`) and the
   `"onclick" not in html` substring in `tests/test_wish_items_list_reorder_ui.py:137` with
   behavioural browser tests after WISHENKA-110 lands. Also cover the `console.warn` branch
   there (`wishlist.js:93-104`). Dependency: WISHENKA-110, so this can be recorded as a note on
   that issue rather than a new one.
5. **NON-BLOCKER, already ticketed (reference only):** WISHENKA-109 (touch DnD), WISHENKA-110
   (browser tests), WISHENKA-126 (`core` file). WISHENKA-112 has no overlap.
