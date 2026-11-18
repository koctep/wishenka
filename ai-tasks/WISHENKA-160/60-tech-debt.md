# WISHENKA-160: Technical Debt Analysis

## Shortcuts Taken

1. **Form-validation error re-render in `submit_edit_item` omits DB metadata (`wishenka/web/routes/items_ui.py`)**:
   - When `submit_edit_item` fails early form validation (`400`, e.g., empty title or invalid numeric price/priority), `_render_edit_modal_error` is called with `locked_quantity=0`, `is_collaborative=False`, and `collaborative_members=[]` instead of querying the store. If the item had reserved quantity or belonged to a collaborative wishlist, the re-rendered modal temporarily drops the `min_quantity` hint and collaborative recipient selector until the next valid submission (backend validation on submit remains intact).
2. **Create-mode (`is_edit=False`) errors from `item_edit_modal.html` close the modal (`wishenka/web/routes/items_ui.py`)**:
   - In create mode, `#item-detailed-form` posts to `quick_add_item` (`/items/quick`), which is shared with the inline `#quick-add-bar`. On `400` validation errors, `quick_add_item` returns `_oob_modal_notice(...)`, closing `#item-modal-container` and showing the notice in `#list-notice` instead of re-rendering `item_edit_modal.html` (`is_edit=False`) with preserved form inputs.
3. **String-based OOB detection in `base.html` `htmx:beforeSwap` (`wishenka/web/templates/base.html`)**:
   - Because `item_archive_modal.html` targets `#items-list` (`hx-swap="none"`), `base.html` detects modal OOB error responses via substring checks (`responseText.indexOf('id="item-modal-container"') !== -1 && responseText.indexOf('hx-swap-oob') !== -1`). This is fragile if the modal container ID or attribute formatting changes.
4. **`htmx_stub.js` does not implement `HX-Retarget` / `HX-Reswap` (`tests/browser_assets/htmx_stub.js`)**:
   - Already tracked out-of-scope in **WISHENKA-145** / **WISHENKA-162**. As a result, `HX-Retarget: #item-modal-container` and `HX-Reswap: innerHTML` are verified at the HTTP/SSR route level, while browser CDP tests verify `htmx:beforeSwap` and modal DOM rendering separately.

## Code Quality Issues

1. **Long `submit_edit_item` handler (`wishenka/web/routes/items_ui.py`)**:
   - `submit_edit_item` spans ~180 lines and mixes form normalization, validation, store transaction execution, and 5 error/success rendering paths. Extracting form parsing/normalization into a small helper would improve readability.
2. **Hardcoded hex colors in modal CSS (`wishenka/web/static/miniapp.css`)**:
   - New modal styles use literal hex colors (`#e5e7eb`, `#888`, `#fef2f2`, `#b91c1c`, `#fecaca`, `#fffbeb`, `#b45309`, `#fde68a`, `#74283f`) instead of CSS theme variables. CSS token consolidation is already tracked out-of-scope in **WISHENKA-163**.
3. **Unused Tailwind utility classes in modal templates (`item_edit_modal.html`, `item_archive_modal.html`)**:
   - `base.html` does not load Tailwind CSS; legacy utility classes (`fixed`, `inset-0`, `bg-black`, `z-50`, `rounded-t-xl`, etc.) remain alongside `.modal-backdrop` / `.modal-sheet`. Keeping them is harmless, but they are dead classes.

## Missing Tests

1. **Full-suite `pytest` run**:
   - During Steps 4–6, targeted modal, reorder, busy-response, and observability suites passed, and `make analyze` (`ruff check`, `ruff format --check`, `mypy`) passed across 200/201 files. All new tests in `tests/test_item_modals_repro.py` (`timeout(45)`) and `tests/test_wishenka_160_observability.py` (`timeout(30)`) have explicit `pytest.mark.timeout` markers (no timeout-marker blocker).
2. **Create-mode modal (`get_new_item_modal` -> `quick_add_item`) 400 validation preservation**:
   - No dedicated test verifies whether submitting invalid optional fields (e.g., non-numeric price) from the *Create Item* modal preserves form inputs vs. falling back to `#list-notice`.
3. **FastAPI `422` `RequestValidationError` on malformed `quantity` (`int = Form(...)`)**:
   - If a client submits a non-integer `quantity` string, FastAPI returns `422` JSON, which `base.html` `htmx:beforeSwap` intentionally ignores (`text/html` check). Not tested as a UI flow since `<input type="number">` constrains normal input.

## Performance Concerns

- None. CSS modal rules are static, `htmx:beforeSwap` performs O(1) header/element checks with a small substring check only on `>= 400` HTML responses targeting `#items-list`, and no extra database queries were added.

## Follow-up Tasks

- **Preserve form state on Create Item modal (`is_edit=False`) 400 validation errors** (Low): Consider passing a source flag or dedicated modal-create endpoint so `get_new_item_modal` submissions re-render `item_edit_modal.html` with `error_message` and `submitted_form` instead of closing the modal via `_oob_modal_notice`.
  - Jira: [WISHENKA-209](https://pypost.atlassian.net/browse/WISHENKA-209)
- **Decompose `submit_edit_item` form parsing/validation** (Low): Extract form normalization and `submitted_form` construction into a dedicated helper in `wishenka/web/routes/items_ui.py` (can be folded into **WISHENKA-165** shared web-layer helpers).
- **Pre-existing / already-tracked items (no new tickets needed)**:
  - CSS design token consolidation for hardcoded colors: tracked in **WISHENKA-163**.
  - Shared web-layer helpers: tracked in **WISHENKA-165**.
  - Real `htmx` vendoring / `htmx_stub.js` `HX-Retarget` support: tracked in **WISHENKA-145** / **WISHENKA-162**.
  - Global error toast system for generic network/server errors: tracked in **WISHENKA-90**.
