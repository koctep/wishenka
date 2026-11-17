# WISHENKA-73: Technical Debt Analysis

## Shortcuts Taken

1. **Both locales embedded inline in `GET /` HTML shell (`wishenka/web/routes/miniapp.py`):**
   `miniapp()` serializes both `en` and `ru` projections of `nav.*` and `miniapp.*` into `<script id="miniapp-i18n" type="application/json">` on every `GET /` response so `bootstrap()` can switch immediately from guest locale to `profileLocale` without an extra HTTP round-trip. This works well for 2 locales and ~100 keys, but payload size will grow linearly if additional locales or large Mini App screens are added in the future.
2. **Duplicated profile-locale application in `bootstrap()` (`wishenka/web/static/miniapp.js:499-511`):**
   The logic assigning `profileLocale`, `document.documentElement.lang`, and `root.dataset.locale` is repeated in both the `POST /api/auth/telegram` fallback branch and the `GET /api/auth/me` branch instead of using a single `applyProfileLocale(raw)` helper.
3. **Client-side i18n warnings stay in browser console (`wishenka/web/static/miniapp.js:7-22, 58-63`):**
   `loadI18nCatalog()` and `t()` emit diagnostics via `console?.warn?.(...)`, which helps local debugging but is not forwarded to backend log aggregation.

## Code Quality Issues

1. **Inline Node DOM harness in Python test file (`tests/test_miniapp_i18n_repro.py`):**
   The Node `vm` DOM/fetch stub (`_NODE_HARNESS`) is embedded as a multi-hundred-line raw string inside `tests/test_miniapp_i18n_repro.py`. If additional Mini App client UI tests are added, maintaining a custom DOM mock inside Python strings will become brittle compared to using a dedicated JS test file (e.g., `node --test`).
2. **No automated JS linter in `make analyze`:**
   `make analyze` checks Python with `ruff` and `mypy`, whereas `wishenka/web/static/miniapp.js` only has ad-hoc `node --check` syntax verification and no ESLint/style gate.
3. **Long rendering functions in `wishenka/web/static/miniapp.js`:**
   `showHome()` and `showList()` remain large monolithic DOM-builder functions (pre-existing structure preserved to minimize diff scope in WISHENKA-73).

## Missing Tests

1. **Explicit timeout markers:** Verified — **no missing timeout markers**. All touched test files (`tests/test_miniapp_i18n_repro.py`, `tests/test_i18n_unit.py`, `tests/test_i18n_sync.py`, `tests/test_wishlist_sections_ui.py`, `tests/test_wishlist_management_observability.py`) declare explicit `pytestmark = pytest.mark.timeout(...)` markers.
2. **Graceful degradation on missing/malformed `#miniapp-i18n` in `miniapp.js`:**
   There is no automated test verifying that `loadI18nCatalog()` and `t()` do not throw, emit `console.warn` once, and fall back to key names when `#miniapp-i18n` is missing or contains invalid JSON.
3. **Archived wishlist & interactive error-status paths in `miniapp.js`:**
   `tests/test_miniapp_i18n_repro.py` verifies `showHome`, `showHistory`, `showList` (active owner), `publicView`, `invitationView`, and `unavailableLink` in RU/EN, but does not exercise the `archived` state (`miniapp.list.archived_notice`, `miniapp.list.restore`) or failed-action status messages (`miniapp.wishlist_settings.save_failed`, `miniapp.public.reserve_failed`, `miniapp.invite.join_failed`) in the Node harness.

## Performance Concerns

1. **Per-request projection and JSON serialization in `GET /` (`wishenka/i18n/catalog.py`, `wishenka/web/routes/miniapp.py`):**
   `miniapp_catalog()` filters `CATALOG` and `json.dumps(...)` serializes + XSS-escapes the result on every `GET /` request. Since `CATALOG` is static at runtime, this is negligible today (~100 keys, 2 locales) but can be cached (e.g., `@functools.lru_cache` or module-level pre-serialized payload) to eliminate per-request allocations under higher traffic.

## Follow-up Tasks

- **NON-BLOCKER — Cache `miniapp_catalog()` / pre-serialize `#miniapp-i18n` payload:** Cache the projected `miniapp_catalog()` dict and/or pre-escaped JSON payload at module level in `wishenka/i18n/catalog.py` or `wishenka/web/routes/miniapp.py`. Jira: [WISHENKA-200](https://pypost.atlassian.net/browse/WISHENKA-200)
- **NON-BLOCKER — Extract `applyProfileLocale()` and add JS lint target:** Deduplicate locale-assignment in `bootstrap()` in `wishenka/web/static/miniapp.js` and consider adding a lightweight JS syntax/lint check to `Makefile` `analyze`. Jira: [WISHENKA-201](https://pypost.atlassian.net/browse/WISHENKA-201)
- **NON-BLOCKER — Expand `miniapp.js` edge-case tests:** Add Node tests covering missing/malformed `#miniapp-i18n` fallback warnings, missing-key warning deduplication, archived wishlist UI strings, and error-path status messages. Jira: [WISHENKA-202](https://pypost.atlassian.net/browse/WISHENKA-202)
