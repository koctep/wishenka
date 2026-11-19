# WISHENKA-140: Remove Remaining Inline JavaScript and Inline Event Handlers for Strict CSP

## Research

Inspection of the templates, static scripts, and test suite in `/home/src` identified the exact scope and existing contracts:

1. **Remaining inline `<script>` in `wishenka/web/templates/base.html` (lines 13–260)**:
   - Manages CSRF token preparation and caching (`prepareCsrf()`, `csrfToken`, `csrfPending`, `csrfGeneration`, `csrfTimeoutMs = 10000`).
   - Intercepts `htmx:confirm` for `.item-card` reservation controls when `data-viewer-identified` is set on `document.body`, queuing requests via `pendingGiverControls` (`WeakSet`) until `prepareCsrf()` resolves.
   - Intercepts `htmx:configRequest` for non-GET/HEAD/OPTIONS requests to attach `X-CSRF-Token` and `Idempotency-Key` (via `nextIdempotencyKey()`), respecting `requestSuppressesHeaders(elt)` and `explicitBearer(headers)`, and calling `giverPreparationError(card)` on failure.
   - Intercepts `htmx:afterRequest` for reservation requests (`reservationRequestPath(elt)`): clears `elt.dataset.idempotencyKey` on non-0/non-503 responses, refreshes `#reservations-cabinet` for `.reservation-row` actions, handles `403` (`Invalid CSRF token` cache invalidation), `503` busy notices, and refreshes `.item-card` via `swapWishCard(card, markup)` while preserving `aria-expanded` and `.item-card-details.hidden`.
   - Intercepts `htmx:beforeSwap` for 4xx/5xx `text/html` modal responses (`#item-modal-container`, `#item-edit-sheet`, `#item-archive-modal`, or OOB `#item-modal-container` to `#items-list`), excluding `X-Reorder-Refusal`, `X-Receipt-Refusal`, and reservation requests.
2. **Cross-template dependency in `wishenka/web/templates/settings.html` (line 159)**:
   - `settings.html` extends `base.html` and calls `typeof prepareCsrf === 'function' ? await prepareCsrf() : ''` inside `settingsFetch()`. Removing the inline script from `base.html` into an IIFE without exposing `window.prepareCsrf` would break CSRF attachment on `/settings`.
3. **Six inline `onclick` attributes across three partials**:
   - `wishenka/web/templates/partials/item_edit_modal.html`:
     - `.btn-modal-close` (line 11): clears `#item-modal-container`.
     - `.btn-step.btn-decrement` (line 82): decrements `#item-quantity-input` down to `{{ min_quantity }}` (also present as `min="{{ min_quantity }}"` on `#item-quantity-input`).
     - `.btn-step.btn-increment` (line 96): increments `#item-quantity-input` up to `1000` (also present as `max="1000"` on `#item-quantity-input`).
     - `.btn-cancel` (line 191): clears `#item-modal-container`.
   - `wishenka/web/templates/partials/item_archive_modal.html`:
     - `.btn-modal-close` (line 35): clears `#item-modal-container`.
   - `wishenka/web/templates/partials/item_preview_card.html`:
     - `.btn-preview-dismiss` (line 56): clears `#quick-add-preview-target`.
4. **Existing static JS conventions (`wishenka/web/static/wishlist.js`, `wishenka/web/static/receipt.js`)**:
   - Both are classic scripts loaded with `defer` after `htmx.org` inside `base.html`, wrapped in an IIFE with `'use strict';`, JSDoc comments, and delegated listeners on `document`.
5. **Existing tests that inspect the `base.html` inline script**:
   - `tests/test_receipt_static_script.py`: pins `INLINE_SCRIPT_SHA256` and asserts `len(inline) == 1`, `htmx.ajax(` count == 1 in both `wishlist.js` and `receipt.js`, and strict separation of `X-Reorder-Refusal` (`wishlist.js`) vs `X-Receipt-Refusal` (`receipt.js`).
   - `tests/test_wish_card_giver_controls.py`: `assert_expanded_refresh_clears_hidden(page_html)` inspects `inline_script(page_html)` for `swapWishCard`.
   - `tests/test_reservations_cabinet_ui.py`: `base_script(client, wishlist_id, headers)` inspects inline scripts from `/web/wishlists/{wishlist_id}` for `refresh_script_problems(...)`.

## Implementation Plan

1. **Create `wishenka/web/static/app.js`**:
   - Wrap all base-layout behavior in an IIFE with `'use strict';` and JSDoc annotations per `lsr-javascript`.
   - Move the CSRF, HTMX (`htmx:confirm`, `htmx:configRequest`, `htmx:afterRequest`, `htmx:beforeSwap`), reservation cabinet/card refresh (`swapWishCard`), and idempotency logic verbatim in behavior from `base.html`.
   - Expose `window.prepareCsrf = prepareCsrf` so `settings.html` continues to work unchanged.
   - Add a delegated `click` listener on `document` handling:
     - `[data-clear-target]`: queries the selector in `data-clear-target` and sets `innerHTML = ''`.
     - `[data-qty-step][data-qty-target]`: reads the target `<input>`, parses `min` (fallback `1`), `max` (fallback `1000`), and `value` (falling back to `min` if `NaN` so empty/non-numeric values never produce `NaN`), and updates `input.value` clamped to `[min, max]`.
2. **Update `wishenka/web/templates/base.html`**:
   - Remove the inline `<script>...</script>` block (lines 13–260).
   - Add `<script src="/static/app.js" defer></script>` after `json-enc.js` and before `/static/wishlist.js` and `/static/receipt.js`.
3. **Update modal and preview partials to declarative `data-*` attributes**:
   - `wishenka/web/templates/partials/item_edit_modal.html`: replace `onclick` on `.btn-modal-close` and `.btn-cancel` with `data-clear-target="#item-modal-container"`; replace `onclick` on `.btn-decrement` with `data-qty-step="-1" data-qty-target="#item-quantity-input"` and on `.btn-increment` with `data-qty-step="1" data-qty-target="#item-quantity-input"`.
   - `wishenka/web/templates/partials/item_archive_modal.html`: replace `onclick` on `.btn-modal-close` with `data-clear-target="#item-modal-container"`.
   - `wishenka/web/templates/partials/item_preview_card.html`: replace `onclick` on `.btn-preview-dismiss` with `data-clear-target="#quick-add-preview-target"`.
4. **Update existing inline-script-inspecting tests**:
   - Update `tests/test_receipt_static_script.py` to assert zero inline `<script>` elements in `base.html` pages and verify `/static/app.js` is served as JS with `defer` after `htmx.org`.
   - Update `tests/test_wish_card_giver_controls.py` (`assert_expanded_refresh_clears_hidden`) and `tests/test_reservations_cabinet_ui.py` (`refresh_script_problems` callers) to inspect `/static/app.js` instead of `base.html` inline scripts.

**Mandatory — Failing Repro (next Step 3):**
- **File**: `tests/test_csp_inline_removal_repro.py` (uses FastAPI `TestClient`, `create_app`, isolated `tmp_path` SQLite DB, and `BeautifulSoup` — no live browser or external network).
- **What it asserts (desired behavior)**:
  1. Rendered owner wishlist page (`GET /web/wishlists/{id}`) and public share page (`GET /share/{token}`) contain zero inline `<script>` tags (tags without `src`), and load `<script src="/static/app.js" defer>` after `htmx.org` and before `/static/wishlist.js` and `/static/receipt.js`.
  2. `GET /static/app.js` returns HTTP `200` with a JavaScript `Content-Type`.
  3. Rendered modal and preview fragments (`item_edit_modal.html`, `item_archive_modal.html`, `item_preview_card.html` via their routes or template rendering) contain zero `on*` attributes and carry `data-clear-target`, `data-qty-step`, and `data-qty-target` attributes on the corresponding controls.
- **How to force failure without live external deps**: Running `pytest tests/test_csp_inline_removal_repro.py` against the current repository fails immediately because `base.html` still embeds the inline `<script>`, `/static/app.js` returns `404`, and the three partials still contain `onclick` attributes.
- **Sequencing**: Research (Steps 1–2) → write red test `tests/test_csp_inline_removal_repro.py` and verify it fails (Step 3) → implement `app.js`, update `base.html` and the three partials, and update existing inline-script tests until all tests pass (Step 4).

## Architecture

### Module Diagram

```mermaid
flowchart TB
    Base["base.html<br/>(no inline script; loads deferred scripts)"]
    AppJS["static/app.js<br/>(CSRF, HTMX lifecycle, card/cabinet refresh,<br/>delegated clear-target & qty-step)"]
    WishlistJS["static/wishlist.js<br/>(card toggle & DnD reorder)"]
    ReceiptJS["static/receipt.js<br/>(receipt dialog & focus trap)"]
    Settings["settings.html<br/>(calls window.prepareCsrf)"]
    Partials["Partials: item_edit_modal, item_archive_modal,<br/>item_preview_card (data-clear-target, data-qty-step)"]

    Base -->|loads defer| AppJS
    Base -->|loads defer| WishlistJS
    Base -->|loads defer| ReceiptJS
    AppJS -->|exposes window.prepareCsrf| Settings
    AppJS -->|delegated click listeners| Partials
```

### Module Responsibilities

| Module | Responsibility |
| --- | --- |
| `wishenka/web/static/app.js` | Global app wiring: CSRF token fetching/caching (`window.prepareCsrf`), HTMX reservation headers (`X-CSRF-Token`, `Idempotency-Key`), `htmx:confirm` queuing, `htmx:afterRequest` cabinet/card refresh (`swapWishCard`), `htmx:beforeSwap` modal error handling, and delegated `click` handlers for `[data-clear-target]` and `[data-qty-step]`. |
| `wishenka/web/templates/base.html` | Base HTML shell: loads external/static scripts (`app.js`, `wishlist.js`, `receipt.js` with `defer`) and provides `data-viewer-identified` and `data-i18n-*` attributes on `<body>`; contains zero inline executable scripts. |
| `wishenka/web/templates/partials/item_edit_modal.html` | Edit/create item modal markup with `data-clear-target="#item-modal-container"` on close/cancel buttons and `data-qty-step` / `data-qty-target` on `-`/`+` quantity buttons. |
| `wishenka/web/templates/partials/item_archive_modal.html` | Archive confirmation modal markup with `data-clear-target="#item-modal-container"` on the cancel button. |
| `wishenka/web/templates/partials/item_preview_card.html` | Quick-add preview card markup with `data-clear-target="#quick-add-preview-target"` on the dismiss button. |

### Architectural Patterns & Justification

1. **Dedicated `/static/app.js` over merging into `wishlist.js` or `receipt.js`**:
   - Preserves existing invariants in `tests/test_receipt_static_script.py`: `wishlist.js` and `receipt.js` each keep exactly one `htmx.ajax(` call and their refusal header namespaces (`X-Reorder-Refusal` vs `X-Receipt-Refusal`) remain strictly isolated.
   - `app.js` applies to all pages extending `base.html` (including reservations cabinet and settings), not just wishlist pages.
2. **Document-level Event Delegation with `data-*` attributes**:
   - Modals (`#item-modal-container`) and quick-add previews (`#quick-add-preview-target`) are injected dynamically via HTMX swaps. Delegated `click` listeners on `document` work identically on initial load and after any HTMX swap without re-binding.
   - Reading `min` and `max` from the target `<input>` element avoids duplicating Jinja template bounds inside JS.
3. **IIFE encapsulation with explicit `window.prepareCsrf` bridge**:
   - Keeps internal state (`csrfToken`, `csrfPending`, `csrfGeneration`, `pendingGiverControls`) private inside the IIFE while preserving backward compatibility for `settings.html` (`typeof prepareCsrf === 'function'`).

### Main Interfaces

- **DOM `<body>` contract**:
  - `data-viewer-identified="true"` — enables CSRF pre-fetch and HTMX header injection.
  - `data-i18n-prepare-error`, `data-i18n-busy-error` — localized fallback error messages.
- **Declarative action attributes**:
  - `data-clear-target="<CSS selector>"` — clears `innerHTML` of the matched container on click.
  - `data-qty-step="-1" | "1"` + `data-qty-target="<CSS selector>"` — steps the target `<input type="number">` value within its `[min, max]` bounds.
- **Global JS bridge**:
  - `window.prepareCsrf(): Promise<string>` — returns cached or freshly fetched CSRF token (or `''` on timeout/failure).

## Q&A

- **Q**: Why expose `window.prepareCsrf` instead of keeping it private inside the IIFE?
  **A**: `wishenka/web/templates/settings.html` (outside the scope of WISHENKA-140) calls `prepareCsrf()` when `typeof prepareCsrf === 'function'`. Exposing `window.prepareCsrf` prevents a regression on `/settings`.
- **Q**: Why not add the `Content-Security-Policy` header in this task?
  **A**: Enabling the CSP header is explicitly out of scope for WISHENKA-140 and tracked as a follow-up step once inline scripts and handlers are removed.
