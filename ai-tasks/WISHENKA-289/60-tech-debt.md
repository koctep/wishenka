# WISHENKA-289: Technical Debt Analysis

## Summary and Blockers Verdict

- **Blockers**: `0` blockers (`PASS` eligible for Step 7).
- **Unticketed Follow-ups**: `0` new tickets required. Remaining screen-level UX stories
  (wishlist detail/sharing/members, personal settings, viewing history, cross-screen feedback
  polish, owner delete confirmation, and empty-wishlist creation exit handling) are owned by
  sibling Sprint 2120 stories `WISHENKA-290`..`WISHENKA-296`, and all observed baseline or test
  helper debt items are already tracked in Jira.
- **Scope Reviewed**: `wishenka/i18n/catalog.py`, `wishenka/web/static/miniapp.js`,
  `wishenka/web/static/miniapp.css`, `tests/test_home_overview_ui.py`, and
  `tests/test_home_overview_browser.py`.

## Shortcuts Taken

1. **Client-side collaborator-favorite deduplication in `showHome()` instead of changing
   `GET /api/favorites`**:
   - `showHome()` in `wishenka/web/static/miniapp.js` (`lines 260-265`) builds
     `activeIds = new Set(lists.map(l => l.id))` and filters `pureFavs` with
     `!activeIds.has(l.id) && !['owner', 'admin', 'member'].includes(l.role)`, leaving
     `GET /api/favorites` in `wishenka/web/routes/wishlists.py` unchanged.
   - **Trade-off (intentional per `ai-tasks/WISHENKA-289/20-architecture.md`)**: Enforces
     `owner > admin > member > favorite` role precedence on the Home overview while preserving
     direct `/api/favorites` API contract expectations in `tests/test_wishlist_sections_ui.py`.

2. **Preserved DOM structure, `source_between` slice boundaries, and minimal Node VM contracts in
   `wishenka/web/static/miniapp.js`**:
   - Kept `.top-nav.home-top-nav` (`lines 236-251`) with two `<button>` controls
     (`.btn-primary.home-create-btn` and `.home-nav-action`) plus `a.settings-link.home-nav-action`,
     kept `.wishlist-section` elements (`lines 269-273, 294-298, 319-323, 360-364`) as direct
     children of `#app`, placed helper functions (`formatDate`, `renderSectionHeader`,
     `renderEmptyState`, `wishlistCard` on `lines 139-189`) before `async function showHome(`
     (`line 231`), and kept `/web/reservations/card` `DOMParser` + `node()` construction
     (`lines 407-441`) inside `showHome()` before `function settingsForm(list)` (`line 445`).
   - **Trade-off (intentional)**: Avoids breaking `source_between` checks in
     `tests/test_reservations_cabinet_ui.py`, direct-child `root.querySelector('.wishlist-section')`
     scanning in `tests/test_miniapp_i18n_repro.py`, `.top-nav button` count assertions in
     `tests/test_visual_identity_browser.py`, and `root.querySelector('button')?.focus()` for
     `startapp=create` (`lines 688-690`).

3. **Preserved immediate `POST /api/wishlists` `{}` on Create click and legacy
   `miniapp.home.remove` catalog key**:
   - Clicking `.home-create-btn` in `wishenka/web/static/miniapp.js` (`lines 242-247`) continues to
     submit `POST /api/wishlists` with `body: '{}'` and transition to `showList(list.id)` so
     `WISHENKA-296` can modify empty-wishlist creation exit behavior without conflict.
   - `miniapp.home.remove` remains in `wishenka/i18n/catalog.py` (`lines 271, 817`) alongside the
     new `miniapp.home.remove_favorite` and `miniapp.home.remove_favorite_named` keys
     (`lines 272-273, 818-819`) for backward compatibility with existing i18n checks.

## Code Quality Issues

1. **Remaining raw hex literals and shared `.wishlist-card, .history-item` base rule in
   `wishenka/web/static/miniapp.css` (`NON-BLOCKER`)**:
   - `WISHENKA-289` added four custom properties in `:root` (`--surface-subtle`,
     `--border-subtle`, `--accent-soft`, `--muted-border` on `lines 16-19`), but four Home-related
     declarations still use literal hex colors: `.reservations-badge` (`color: #ffffff` on
     `line 126`), `.wishlist-section--collab` (`border-left: 4px solid #0f766e` on `line 130`),
     `.wishlist-card, .history-item` (`border: 1px solid #f5e3e9` on `line 151`), and
     `#app button.wishlist-card-open:hover:not(:disabled)` (`background: #fde2ea` on `line 182`).
   - `.wishlist-card, .history-item` (`lines 149-153`) defines a horizontal flex row that
     `#app .wishlist-card` (`lines 154-157`) overrides to `flex-direction: column` so
     `.history-item` rows in `showHistory()` (`wishenka/web/static/miniapp.js:213-225`) remain
     unchanged until `WISHENKA-292`.

2. **Minor accessibility and test-harness observations (`NON-BLOCKER`)**:
   - In `wishenka/web/static/miniapp.js`, active wishlist cards set per-card `aria-label` values
     on `.wishlist-card-open` (`line 182`) and `.wishlist-card-remove` (`lines 347-350`), whereas
     `.wishlist-card-restore` in `.deleted-section` (`lines 383-399`) uses only the visible
     `t('miniapp.deleted.restore')` label without a per-list `aria-label`.
   - `_NODE_HARNESS` in `tests/test_home_overview_ui.py` (`lines 227-252`) uses a regex-based
     `DOMParser.parseFromString` mock tailored to `partials/reservations_card.html` (real browser
     `DOMParser` parsing is verified by `tests/test_home_overview_browser.py`).
   - `_telegram_init_data` and `_set_user_locale` in `tests/test_home_overview_browser.py`
     (`lines 23-56`) duplicate the Telegram WebApp HMAC helper pattern from
     `tests/test_bot_menu_miniapp_e2e_browser.py` (already tracked under `WISHENKA-239`).

3. **Explicit pytest timeout markers and bounded waits verified (`0` blockers)**:
   - `tests/test_home_overview_ui.py` (`line 21`) declares `pytestmark = pytest.mark.timeout(20)`
     and bounds Node VM execution via `subprocess.run(..., timeout=10)` (`line 406`).
   - `tests/test_home_overview_browser.py` (`line 20`) declares
     `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]` and bounds all HTTP and CDP
     waits (`httpx.Client(..., timeout=10)` and `page.wait_for(...)`).

## Missing Tests

- **Verified test coverage in `WISHENKA-289`**:
  - `102 passed` across `tests/test_home_overview_ui.py` (`13` tests),
    `tests/test_home_overview_browser.py` (`6` tests across `412x800` and `360x800` in `en`/`ru`),
    `tests/test_visual_identity_browser.py`, `tests/test_reservations_cabinet_ui.py`,
    `tests/test_wishlist_sections_ui.py`, `tests/test_wishlist_deleted_restore.py`,
    `tests/test_miniapp_i18n_repro.py`, `tests/test_bot_menu_miniapp_e2e_browser.py`,
    `tests/test_i18n_unit.py`, and `tests/test_i18n_sync.py`, plus observability suites
    `tests/test_observability.py` and `tests/test_wishlist_management_observability.py`.
- **Minor untested edges in `WISHENKA-289` scope (`NON-BLOCKER`, low risk)**:
  - `formatDate(iso)` fallback branch for unparseable date strings
    (`if (isNaN(parsed.getTime())) return String(iso);` in `wishenka/web/static/miniapp.js:142`) is
    not exercised with a malformed date string in `tests/test_home_overview_ui.py`.
  - `tests/test_home_overview_ui.py` does not separately assert the `#status` error message when
    `DELETE /api/favorites/{id}`, `POST /api/wishlists`, or `GET /api/wishlists` returns HTTP 500
    (covered in existing suites; cross-screen loading/error feedback polish belongs to
    `WISHENKA-294`).

## Performance Concerns

- None (`0` blockers). `showHome()` fetches `/api/wishlists`, `/api/favorites`, and
  `/api/wishlists/deleted` in parallel via `Promise.all` (`wishenka/web/static/miniapp.js:254-258`)
  and performs `O(N)` `Set`-based deduplication (`lines 262-265`). Removing a favorite (`line 343`)
  or restoring a deleted wishlist (`lines 388, 393`) re-runs `showHome()` to refresh all sections
  rather than mutating the DOM in place, which is negligible for personal wishlist counts
  (`NON-BLOCKER`).

## Deviations from Architecture

- None. Implementation matches `ai-tasks/WISHENKA-289/20-architecture.md`.

## Follow-up Tasks

### New Unticketed Follow-up Tasks

- None. No `BLOCKER` or new unticketed `Debt` issue exists inside `WISHENKA-289` scope beyond the
  already-planned Sprint 2120 stories (`WISHENKA-290`..`WISHENKA-296`) and existing tracked Jira
  `Debt` issues listed below.

### Intentionally Not Ticketed (Accepted Trade-offs / Low-Risk Polish)

- Extracting CSS variables for `#0f766e` and `#fde2ea`, decoupling `.history-item` from
  `.wishlist-card` when `WISHENKA-292` redesigns Viewing history, adding a per-list `aria-label`
  to `.wishlist-card-restore`, and testing the `formatDate` invalid-date fallback (low risk; can be
  folded into `WISHENKA-292` / `WISHENKA-294` or `WISHENKA-239` when those files are touched).

### Pre-existing Baseline Triage and Tracked Issues (Do NOT Duplicate)

All pre-existing environment requirements, unrelated baseline test issues, and adjacent browser or
server debt below are already tracked in Jira; none is caused by `WISHENKA-289`:

- **`NON-BLOCKER — environment` — `WISHENKA-297`** (`already tracked`): Non-root Chromium browser
  setup requiring `/tmp/wishenka-chromium` (`WISHENKA_CHROMIUM_BIN` and `LD_LIBRARY_PATH`).
- **`NON-BLOCKER — pre-existing` — `WISHENKA-267`** (`already tracked`):
  `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
  CSRF token readiness failure (HTTP 401).
- **`NON-BLOCKER — pre-existing` — `WISHENKA-226`** (`already tracked`):
  `tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability` anonymous
  `/share/{token}` `is_recipient` log field mismatch.
- **`NON-BLOCKER — pre-existing` — `WISHENKA-235`** (`already tracked`): Anonymous share
  availability projection baseline failures in `tests/test_wish_card_giver_controls.py` and
  `tests/test_surprise_role_context.py`.
- **`NON-BLOCKER — pre-existing` — `WISHENKA-265`, `WISHENKA-220`** (`already tracked`): Existing
  tracked tech-debt items in adjacent modules outside `WISHENKA-289` scope.
- **`NON-BLOCKER — related browser test debt` — `WISHENKA-239`, `WISHENKA-240`**
  (`already tracked`):
  - `WISHENKA-239`: Consolidate shared Telegram WebApp browser E2E helpers into
    `tests/browser_helpers.py`.
  - `WISHENKA-240`: Add browser test coverage for
    `window.Telegram.WebApp.initDataUnsafe.start_param` precedence in
    `wishenka/web/static/miniapp.js`.
