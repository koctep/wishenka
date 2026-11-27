# WISHENKA-266: Technical Debt Analysis

No new technical debt. This task did not change product code. The close
button already uses the receipt theme colors: `.receipt-sheet
.btn-modal-close` in `wishenka/web/static/miniapp.css` sets
`background: var(--receipt-bg)` and `color: var(--receipt-text)`. There is
no new follow-up.

Reviewed: that stylesheet pair, `10-requirements.md`, `20-architecture.md`,
`30-failing-repro.md`, `40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

None. The sheet selector already paints the close label and its own fill
from the receipt tokens. No second close-control rule, fixed dark color,
or new `:root` property was added. `wishenka/web/static/app.js` stays
unchanged and free of the substring `receipt`.

## Code Quality Issues

None. The measured pair is the shared block the architecture already
names, with `.modal-sheet .btn-modal-close` and `.modal-sheet
.btn-cancel`. The hover companion keeps `background: var(--receipt-bg)`
on the same selectors. This task did not add a hardcoded color, status,
or timeout.

## Missing Tests

No `do-testing` blocker. No new test was added.
`tests/test_receipt_theme_browser.py` declares
`pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`, which
covers `test_receipt_text_has_readable_contrast` for `fallback`, `light`,
and `dark`. The module has no function-level timeout override.

Those three nodes pass when collected after a module that finishes the
import (`4 passed` with
`tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`).
Collected alone, the same nodes ERROR in setup. That `ImportError` is
existing work, already WISHENKA-357, and is not a gap this task opened.

## Performance Concerns

None. The close control is an existing stylesheet pair. No request, poll,
or server work was added.

## Follow-up Tasks

None. There is no new follow-up.

The isolated collection error is already WISHENKA-357. It is not a new
follow-up. `NON-BLOCKER — pre-existing`. When
`tests/test_receipt_theme_browser.py` is collected alone, setup raises
`ImportError` and cannot import `WishlistStore` from the partially
initialized module `wishenka.wishlists.store`. The node ids are:

- `tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast[fallback]`
- `tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast[light]`
- `tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast[dark]`

User documentation under `doc/` was left unchanged. The close control a
person sees did not change. Developer docs still belong to Step 8.
