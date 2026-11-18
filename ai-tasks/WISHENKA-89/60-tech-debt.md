# WISHENKA-89: Technical Debt Analysis

> **Blocker Assessment**: **0 blockers** for closing `WISHENKA-89`. All acceptance criteria, `make analyze` (Ruff + Mypy), and all 1,105 tests (including `tests/test_ssr_i18n_repro.py` with explicit `pytest.mark.timeout(30)`) pass.

## Shortcuts Taken

1. **[MEDIUM | Follow-up Debt] Duplicated English fallback literals in `base.html`, `receipt.js`, and `wishlist.js`**
   - **Where**: `wishenka/web/templates/base.html` (inline `<script>`), `wishenka/web/static/receipt.js` (`DEFAULT_GENERIC_FAILURE`, `DEFAULT_SUMMARY_TEMPLATE`), `wishenka/web/static/wishlist.js` (`data-i18n-item-unavailable`, `data-i18n-list-changed`).
   - **Detail**: Client-side SSR scripts read localized strings from `document.body.getAttribute('data-i18n-*')`, with hardcoded English fallback strings if the attribute is missing. If `web.*` English copy in `wishenka/i18n/catalog.py` is edited later, these fallbacks can drift out of sync.
   - **Impact**: Low runtime risk (attributes are always rendered by `base.html` on full pages), minor maintenance burden.

2. **[LOW | Follow-up Debt] No Russian plural-form helper (`format_count`) for dynamic quantities**
   - **Where**: `wishenka/i18n/formatters.py`, `wishenka/i18n/catalog.py` (`web.receipt.summary_template` / `web.receipt.summary_many`).
   - **Detail**: `20-architecture.md` noted an optional plural-aware `format_count` helper. `formatters.py` implements `format_date` only, and quantity labels use invariant abbreviations (`шт.` / `pcs.`). In `receipt.js`, `data-i18n-receipt-summary` always uses `{chosen} шт. из {remaining} оставшихся`, which is grammatically slightly rough when `remaining == 1` (though `item_receipt_modal.html` avoids the dropdown when `remaining <= 1`).
   - **Impact**: Cosmetic only; no functional defect.

## Code Quality Issues

1. **[LOW | Follow-up Debt] Repeated `data-i18n-busy-error` attribute lookup in `base.html`**
   - **Where**: `wishenka/web/templates/base.html` (lines 147–148 and 209–210).
   - **Detail**: Two separate HTMX error handlers repeat `document.body.getAttribute('data-i18n-busy-error') || 'The wish is busy; the reservation was not changed. Please try again.'` instead of calling a small shared helper (e.g., `i18nAttr(name, fallback)`).

2. **[LOW | Follow-up Debt] Redundant UTC normalization before `format_date` in `gifted_view.py` and `reservations_ui.py`**
   - **Where**: `wishenka/web/gifted_view.py` (`utc_day`), `wishenka/web/routes/reservations_ui.py` (`_event_day`).
   - **Detail**: Both helpers normalize naive `datetime` values to UTC before calling `format_date(..., locale)`, even though `wishenka/i18n/formatters.py:format_date` already performs the exact same UTC normalization.

3. **[LOW | Follow-up Debt] Leftover Russian docstrings/comments in SSR receipt modules**
   - **Where**: `wishenka/web/gifted_view.py` (line 1), `wishenka/web/routes/receipts_ui.py` (line 334), `wishenka/web/static/receipt.js` (line 32).
   - **Detail**: Docstrings/comments still reference `«Подаренные»` / `«Получено»` in Russian; runtime output is fully localized.

## Missing Tests

1. **[MEDIUM | Follow-up Debt] No browser/DOM execution test for `receipt.js` and `wishlist.js` `data-i18n-*` rendering in English**
   - **Where**: `tests/test_ssr_i18n_repro.py`, `tests/test_receipt_static_script.py`, `tests/test_receipt_modal_browser.py`.
   - **Detail**: `test_ssr_i18n_repro.py` verifies that `base.html` renders `data-i18n-*` attributes and `test_receipt_static_script.py` checks attribute names statically, but no browser test triggers the live DOM error/summary paths in `receipt.js` (`data-i18n-receipt-summary`, `data-i18n-receipt-failure`) or `wishlist.js` (`data-i18n-item-unavailable`, `data-i18n-list-changed`) under `locale="en"`.

2. **[LOW | Follow-up Debt] Explicit assertion for `gifted_items_section.html` act date formatting in `ru` and `en`**
   - **Where**: `tests/test_ssr_i18n_repro.py`.
   - **Detail**: `test_ssr_i18n_repro.py` verifies `format_date` directly and asserts zero Cyrillic on `GET /web/wishlists/{id}` (which includes gifted items), but does not explicitly assert the formatted receipt act date string inside `gifted_items_section.html` in both `en` (`Dec 25, 2026` / current UTC day) and `ru` (`DD.MM.YYYY`).

3. **Timeout Markers Verification (No Blocker)**:
   - All 8 test files created or modified in `WISHENKA-89` (`tests/test_ssr_i18n_repro.py`, `tests/test_cabinet_received_marker.py`, `tests/test_receipt_modal_browser.py`, `tests/test_receipt_static_script.py`, `tests/test_reservations_cabinet_ui.py`, `tests/test_surprise_role_context.py`, `tests/test_wish_card_giver_controls.py`, `tests/test_wish_items_tma_ui.py`) have explicit `pytest.mark.timeout(...)` markers.

## Performance Concerns

1. **[MEDIUM | Tracked in WISHENKA-192] Duplicate `UserStore` lookup per authenticated SSR request**
   - **Where**: `wishenka/i18n/dependencies.py` (`get_request_locale` via `LocaleDep`).
   - **Detail**: `get_request_locale` calls `get_optional_current_user` and `user_store.get_by_telegram_id(...)` on every SSR request. Authenticated routes that also resolve the current user perform an extra auth/DB lookup. Caching the resolved user record on `request.state` or unifying dependencies is already scoped to `WISHENKA-192`.

## Follow-up Tasks

| Severity / Priority | Blocker for WISHENKA-89? | Summary | Suggested Scope |
| --- | --- | --- | --- |
| `medium` | No (Follow-up Debt -> [WISHENKA-206](https://pypost.atlassian.net/browse/WISHENKA-206)) | Add browser/DOM test coverage for `receipt.js` and `wishlist.js` `data-i18n-*` strings in `en` and `ru`, and remove or centralize duplicate JS fallback literals | `tests/test_receipt_modal_browser.py`, `wishenka/web/templates/base.html`, `wishenka/web/static/{receipt,wishlist}.js` |
| `medium` | No (Already tracked: [WISHENKA-192](https://pypost.atlassian.net/browse/WISHENKA-192)) | Deduplicate `user_store.get_by_telegram_id` lookup between `LocaleDep` and authenticated route dependencies | `wishenka/i18n/dependencies.py` |
| `low` | No (Follow-up Debt -> [WISHENKA-207](https://pypost.atlassian.net/browse/WISHENKA-207)) | Clean up minor SSR i18n polish: extract `i18nAttr` helper in `base.html`, drop redundant UTC normalization in `utc_day`/`_event_day`, translate 3 remaining Russian docstrings, and add explicit `gifted_items_section` act date assertions | `wishenka/web/templates/base.html`, `wishenka/web/gifted_view.py`, `wishenka/web/routes/{receipts_ui,reservations_ui}.py`, `tests/test_ssr_i18n_repro.py` |
