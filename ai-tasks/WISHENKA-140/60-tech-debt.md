# WISHENKA-140: Technical Debt Analysis

## Shortcuts Taken

- **Global `window.prepareCsrf` bridge**: `wishenka/web/static/app.js` exposes `window.prepareCsrf = prepareCsrf` on `window` so `wishenka/web/static/settings.js` (`settingsFetch()`) can continue calling `prepareCsrf()`. Once `settings.js` and `app.js` share an ES module, this global bridge can be removed.
- **Deferred `app.js` assumption for `settings.html`**: `wishenka/web/templates/base.html` loads `/static/app.js` with `defer`, meaning `window.prepareCsrf` is only populated after HTML parsing completes. This works for `settings.html` because `/static/settings.js` is also loaded with `defer` after `app.js` and `prepareCsrf()` is invoked inside user-triggered event handlers.
- **`innerHTML = ''` for container clearing**: `handleDelegatedClick` in `wishenka/web/static/app.js` clears `[data-clear-target]` containers using `container.innerHTML = ''` (preserving the prior inline `onclick` behavior) rather than `replaceChildren()`.

## Code Quality Issues

- **Duplicated reservation response handling in `wishenka/web/static/app.js`**: Inside the `htmx:afterRequest` listener (lines 287–409), the `.reservation-row` branch (lines 298–347) and the `.item-card` branch (lines 349–409) duplicate the `503` busy-slot message lookup (`data-i18n-busy-error`) and the `409`/`401`/`403`/`404` status-to-`notice` (`shortage` vs `refused`) mapping. Extracted verbatim from `base.html` to preserve parity; can be consolidated into shared helpers.
- **Duplicated `mock_fetch_preview` helper in tests**: `tests/test_csp_inline_removal_repro.py` and `tests/test_receipt_static_script.py` each define a local `mock_fetch_preview` async stub for testing `item_preview_card.html`.

## Missing Tests

- **No runtime browser/DOM execution tests for `app.js` delegated handlers**: `tests/test_csp_inline_removal_repro.py`, `tests/test_receipt_static_script.py`, `tests/test_reservations_cabinet_ui.py`, and `tests/test_wish_card_giver_controls.py` verify static serving of `/static/app.js`, deferred loading order, absence of inline `<script>`/`on*` attributes, and presence of `data-clear-target`/`data-qty-step`/`data-qty-target` attributes, while `node --check` verifies JS syntax. Actual DOM click execution (clearing `#item-modal-container` / `#quick-add-preview-target`, stepping `#item-quantity-input` within `[min, max]`, and `NaN`/empty input fallback) is not exercised in a browser/DOM runner (tracked under `WISHENKA-110`).
- **Timeout markers**: All new and modified pytest files (`tests/test_csp_inline_removal_repro.py`, `tests/test_receipt_static_script.py`, `tests/test_reservations_cabinet_ui.py`, `tests/test_wish_card_giver_controls.py`) include explicit `pytestmark = pytest.mark.timeout(30)`.

## Performance Concerns

- No significant performance concerns. `wishenka/web/static/app.js` is loaded with `defer` alongside `wishlist.js` and `receipt.js`, and `document`-level click delegation only runs `Element.closest()` on click events. Static asset `Cache-Control` / cache-busting is tracked separately under `WISHENKA-139`.

## Follow-up Tasks

- NON-BLOCKER — pre-existing: tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control — Jira: [WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235)
- Consolidate the duplicated `503` busy-notice lookup and `409`/`401`/`403`/`404` `notice` mapping between `.reservation-row` and `.item-card` handlers in `wishenka/web/static/app.js`. Jira: [WISHENKA-236](https://pypost.atlassian.net/browse/WISHENKA-236)
- Add browser/DOM execution tests (under [WISHENKA-110](https://pypost.atlassian.net/browse/WISHENKA-110)) for `[data-clear-target]` dismissal and `[data-qty-step]` clamping / `NaN` fallback in `wishenka/web/static/app.js`.
