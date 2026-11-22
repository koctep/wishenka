# WISHENKA-288: Technical Debt Analysis

## Summary and Blockers Verdict

- **Blockers**: `0` blockers (`PASS` eligible for Step 7).
- **Unticketed Follow-ups**: `0` new tickets required. Remaining screen-level UX redesign,
  delete confirmation, and creation-flow fixes are intentionally covered by Sprint 2120 stories
  `WISHENKA-289`..`WISHENKA-296`, and all observed test-baseline or browser-helper issues already
  have Jira tracking keys.
- **Scope Reviewed**: `wishenka/web/static/miniapp.css`, `wishenka/web/static/miniapp.js`,
  `wishenka/web/templates/partials/member_list.html`, `wishenka/web/templates/settings.html`, and
  `tests/test_visual_identity_browser.py`.

## Shortcuts Taken

1. **Foundation-only class hook rollout across existing templates and Mini App views**:
   - `WISHENKA-288` defines shared palette tokens (`--canvas`, `--surface`, `--ink`, `--muted`,
     `--accent`, `--accent-dark`, `--danger`, `--focus`) and component rules in
     `wishenka/web/static/miniapp.css` (`lines 1-61, 78-97, 112, 208-213, 231, 266-288,
     331-344`), and adds `.btn-primary` / `.btn-danger` to representative controls in
     `wishenka/web/static/miniapp.js` (`lines 32-37, 128, 164, 202, 361-363, 388, 506, 529`),
     `wishenka/web/templates/settings.html` (`lines 66-68, 145, 158`), and
     `wishenka/web/templates/partials/member_list.html` (`lines 34-35`).
   - Screen-specific templates and secondary/action classes (`.btn-save`, `.btn-cancel`,
     `.btn-archive-item`, `.btn-confirm-archive`, `.btn-receipt-confirm`, `.btn-secondary` in
     `wishenka/web/templates/partials/item_quick_add.html`, `.settings-link`/`.back-link`,
     `wishenka/web/templates/partials/reservations_list.html`, `item_card.html`, `share_modal.html`,
     and Mini App favorite/link-reset actions) keep their existing DOM and handlers.
   - **Trade-off (intentional by scope)**: Preserves existing test selectors and `miniapp.js`
     function boundaries (such as `source_between` checks in
     `tests/test_reservations_cabinet_ui.py`), leaving screen-level UX redesign, delete
     confirmations, and wishlist creation fixes to `WISHENKA-289`..`WISHENKA-296`.

2. **Legacy uncompiled Tailwind utility strings retained beside semantic classes**:
   - `wishenka/web/templates/base.html` loads only `/static/miniapp.css` (no Tailwind CSS build).
     Existing utility classes in `wishenka/web/templates/partials/member_list.html`
     (`lines 34-35`: `text-xs text-red-600 font-medium px-2 py-1 border rounded`) remain next to
     `btn-delete btn-danger` so existing template selectors stay intact without template churn.

3. **Scoped Telegram theme pair boundary (`miniapp.css:9-11, 104, 198-214, 256-344`)**:
   - The app shells use explicit light tokens (`--canvas`, `--surface`, `--ink`), while
     `.receipt-sheet` and `.modal-sheet` consume the paired Telegram variables `--receipt-bg` /
     `--receipt-text` (`--tg-theme-bg-color` / `--tg-theme-text-color`) with `--focus:
     var(--receipt-text)`, `color: inherit` on `:is(h1, h2, h3)`, and paired `--receipt-bg` /
     `--receipt-text` on `.btn-modal-close` and `.btn-cancel`.
   - Inside `.modal-sheet`, non-checkbox `<input>` elements (`input:not([type="checkbox"])`,
     specified as `type="text"` on `lines 35, 121, 172`, `type="url"` on `lines 46, 141`, and
     `type="number"` on `lines 56, 91`) in `wishenka/web/templates/partials/item_edit_modal.html`
     keep browser default field colors rather than `--receipt-bg` / `--receipt-text` (unlike
     `.modal-sheet select, .modal-sheet textarea` and `.receipt-sheet .quantity-control input`),
     and `.quick-add-container` (`line 104`) retains its pre-existing
     `background: var(--tg-theme-bg-color, #ffffff)` wrapper around `.quick-add-form`
     (`background: var(--surface)`). Accepted per `ai-tasks/WISHENKA-288/20-architecture.md`.

## Code Quality Issues

1. **Remaining raw hex literals and minor rule duplication in `wishenka/web/static/miniapp.css`**:
   - Some hover, disabled, border, card-surface, receipt, and archive rules still use literal hex
     values (`#fff0f4`, `#fff0f1`, `#ece6e9`, `#a7979e`, `#5d5056`, `#aa8998`, `#f5e3e9`, `#fffafd`,
     `#b91c1c`, `#991b1b`, `#15803d`, `#166534`) instead of dedicated CSS custom properties.
   - `.settings-link, .back-link` (`lines 78-88`) duplicates most of
     `a:where(.btn, .btn-primary, .btn-danger)` (`lines 33-43`) while omitting `box-sizing:
     border-box`, `background: var(--surface)`, and the `#fff0f4` hover fill.
   - `.btn-secondary` in `wishenka/web/templates/partials/item_quick_add.html` (`line 20`) relies
     on unclassed `button` styling without an explicit `.btn-secondary` rule (`NON-BLOCKER`).

2. **Minor test helper polish in `tests/test_visual_identity_browser.py`**:
   - `_open` (`lines 16-29`) omits `browser.ensure_alive()` before `new_page`, unlike `_open_page`
     in `tests/conftest.py` (`line 331`) and `_open_session_page` in
     `tests/test_bot_menu_miniapp_e2e_browser.py` (`line 149`).
   - Lines `229-232` interpolate hex constants with single-quoted f-strings instead of
     `js_str(...)`, and tests do not explicitly call `assert_clean_console(page)` or check
     `page.external_requests == []` (`NON-BLOCKER`; pages load offline).

3. **Explicit pytest timeout markers verified (`0` blockers)**:
   - `tests/test_visual_identity_browser.py` (`line 13`) declares module-level
     `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`; every test has an explicit
     timeout marker and bounded CDP waits (`page.wait_for`, `settle`, `open_receipt_dialog`).

## Missing Tests

- **Observed verification coverage in prior steps**:
  - Step 4 reported `38 passed` across visual identity, receipt theme/accessibility, i18n, surprise
    privacy, and Telegram Mini App suites, plus `make analyze`, `node --check`, and `git diff
    --check`.
  - Step 5 reported `68 passed` across `tests/test_visual_identity_browser.py`,
    `tests/test_receipt_theme_browser.py`, `tests/test_receipt_accessibility_browser.py`,
    `tests/test_bot_menu_miniapp_e2e_browser.py`, `tests/test_i18n_unit.py`, and
    `tests/test_i18n_sync.py`.
  - Step 6 reported `72 passed` across `tests/test_visual_identity_browser.py`,
    `tests/test_observability.py`, `tests/test_wishlist_management_observability.py`,
    `tests/test_account_deletion.py`, `tests/test_receipt_static_script.py`,
    `tests/test_i18n_unit.py`, and `tests/test_i18n_sync.py`.
  - Full-repository `make test` was not re-run in `WISHENKA-288` (known baseline failures and
    environment constraints are triaged below).
- **Minor untested visual edges in `WISHENKA-288` scope (`NON-BLOCKER`, low risk)**:
  - `tests/test_visual_identity_browser.py` covers Mini App `.top-nav`, `/settings`, archive/receipt
    modals (light and dark), and `/invite/...` `a.btn.btn-primary`. Computed styles on the other
    hooked buttons (`sharePanel`, `showHistory`, `settingsForm`, `memberControls`, `publicView`,
    `invitationView`, `member_list.html` `.btn-delete.btn-danger`), `.settings-link`/`.back-link`,
    hover transitions, and automated Russian-locale text wrapping checks are not directly asserted
    in `tests/test_visual_identity_browser.py` (EN/RU mobile views were visually verified in Step 4;
    screen-level E2E flows belong to `WISHENKA-289`..`WISHENKA-296`).

## Performance Concerns

- None (`0` blockers). The CSS token/rule additions and `className` hooks in `miniapp.js` add zero
  network calls, timers, or backend queries.

## Deviations from Architecture

- None. Implementation matches `ai-tasks/WISHENKA-288/20-architecture.md`.

## Follow-up Tasks

### New Unticketed Follow-up Tasks

- None. No `BLOCKER` or genuine unticketed `Debt` item exists inside `WISHENKA-288` scope beyond the
  already-scoped Sprint 2120 stories (`WISHENKA-289`..`WISHENKA-296`) and existing tracked Jira
  `Debt` issues listed below.

### Intentionally Not Ticketed (Accepted Trade-offs / Low-Risk Polish)

- Raw hex literal cleanup for hover/disabled/card/archive accents, unifying `.settings-link`/
  `.back-link` with `.btn`, dark-theme styling for `text`/`url`/`number` `<input>`
  (`input:not([type="checkbox"])`) inside `.modal-sheet`, removing legacy uncompiled Tailwind
  utility strings, and minor `js_str` / `ensure_alive` / console assertions in
  `tests/test_visual_identity_browser.py` (low risk; can be folded into
  `WISHENKA-289`..`WISHENKA-296` or `WISHENKA-239` when those components are touched).

### Pre-existing Baseline Triage and Tracked Issues (Do NOT Duplicate)

All pre-existing environment limits, unrelated failing tests, and adjacent browser debt below are
already tracked in Jira; none is caused by `WISHENKA-288`:

- **`NON-BLOCKER — environment` — `WISHENKA-297`** (`already tracked`): Non-root Chromium browser
  setup (`Chromium is required for browser UI tests: no usable browser found on PATH` without
  extracted `/tmp/wishenka-chromium` and `WISHENKA_CHROMIUM_BIN`).
- **`NON-BLOCKER — pre-existing` — `WISHENKA-267`** (`already tracked`): Observed in Step 4;
  `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
  fails waiting for CSRF token (HTTP 401).
- **`NON-BLOCKER — pre-existing` — `WISHENKA-226`** (`already tracked`): Observed in Step 6;
  `tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability` fails
  because `wishenka/web/routes/sharing.py` logs `is_recipient=True` on anonymous `/share/{token}`.
- **`NON-BLOCKER — pre-existing` — `WISHENKA-235`** (`already tracked`): Anonymous share
  projection baseline failures in unrelated suites:
  - `tests/test_wish_card_giver_controls.py`
    (`test_anonymous_share_shows_availability_without_a_book_control`)
  - `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`

- **`NON-BLOCKER — baseline resolved in scope` — `WISHENKA-266`** (`already tracked`): Pre-existing
  baseline failure for dark-theme close-button contrast on
  `tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast[dark]`.
  `WISHENKA-288` fixed close-button contrast inside `.receipt-sheet` and `.modal-sheet`
  (`wishenka/web/static/miniapp.css:339-344`), and `tests/test_receipt_theme_browser.py` passed in
  Step 4 and Step 5 runs (tracked in `WISHENKA-266`; do not duplicate).
- **`NON-BLOCKER — related browser test debt` — `WISHENKA-239`, `WISHENKA-240`**
  (`already tracked`):
  - `WISHENKA-239`: Extract shared Telegram browser E2E helpers from
    `tests/test_bot_menu_miniapp_e2e_browser.py` into `tests/browser_helpers.py`.
  - `WISHENKA-240`: Add browser coverage for `window.Telegram.WebApp.initDataUnsafe.start_param`
    precedence in `wishenka/web/static/miniapp.js`.
