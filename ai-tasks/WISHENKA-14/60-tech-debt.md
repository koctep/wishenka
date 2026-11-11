# WISHENKA-14: Technical Debt Analysis

## Shortcuts Taken

1. **Per-Request `ItemPreviewService` Instantiation Without Preview Cache**:
   - **Context**: In [`preview_item_input`](file:///home/src/wishenka/web/routes/items_ui.py#L190-L193), when `request.app.state.item_preview_service` is not pre-configured, a new [`ItemPreviewService`](file:///home/src/wishenka/items/service.py#L40) instance is created on each `POST /web/wishlists/{wishlist_id}/items/preview` HTMX request, establishing an ephemeral `httpx.AsyncClient` without caching recently resolved URL previews.
   - **Trade-off**: Keeps the HTMX route handler stateless and self-contained, but repeated edits to a pasted URL or transitioning from preview to creation re-runs external network requests if not cached.
   - **Compromise**: Accepted for the initial TMA UI rollout; persistent HTTP pooling and TTL preview caching are already tracked in backlog issue **[WISHENKA-53](https://pypost.atlassian.net/browse/WISHENKA-53)**.

2. **Direct Inspection of `svc._items` for Reduction Lock Aggregate and Placeholder Member Labels**:
   - **Context**: In [`get_edit_item_modal`](file:///home/src/wishenka/web/routes/items_ui.py#L452) and [`submit_edit_item`](file:///home/src/wishenka/web/routes/items_ui.py#L601), the UI handler accesses `svc._items.get(item_id)` directly to compute `locked_quantity = item.reserved_quantity + item.received_quantity` because [`WishItemRecipientViewDTO`](file:///home/src/wishenka/wishlists/schemas.py#L22) intentionally omits reservation counters to enforce the **Surprise Invariant** on recipient list views. Additionally, [`_collaborative_members`](file:///home/src/wishenka/web/routes/items_ui.py#L63-L79) formats non-owner co-authors as `"Участник #<user_id>"` because [`WishlistMember`](file:///home/src/wishenka/wishlists/models.py#L72) stores `user_id` without joined user profile names from [`UserStore`](file:///home/src/wishenka/users/store.py).
   - **Trade-off**: Avoided widening `WishItemRecipientViewDTO` or introducing cross-store SQL joins between `WishlistStore` and `UserStore` within the scope of this frontend story.
   - **Compromise**: Preserves the Surprise Invariant strictly (gifter identities and individual reservations are never exposed in HTML or logs) while deferring a dedicated domain method and user display name hydration to a follow-up task.

3. **CSS-Only Fixed Bottom Positioning Without Dynamic `visualViewport` Keyboard Listener**:
   - **Context**: [`wishenka/web/static/miniapp.css`](file:///home/src/wishenka/web/static/miniapp.css#L27-L36) anchors `.quick-add-container` using `position: fixed; bottom: 0; padding: 0.75rem 1rem max(12px, env(safe-area-inset-bottom))` without a JavaScript `window.visualViewport` resize/scroll listener or Telegram WebApp `viewportChanged` offset handler.
   - **Trade-off**: Relies on native mobile WebView viewport resizing when the software keyboard appears. On older iOS Telegram WebView builds where `position: fixed` elements do not automatically shift above the virtual keyboard, the bar may require manual scroll adjustment.
   - **Compromise**: Keeps client-side CSS lightweight and dependency-free for MVP while scheduling dedicated mobile `visualViewport` and Telegram `HapticFeedback` integration in `miniapp.js`.

## Code Quality Issues

1. **Inline JavaScript Event Handlers in Templates and Raw OOB HTML Strings in Python Routes**:
   - **Context**: [`partials/item_edit_modal.html`](file:///home/src/wishenka/web/templates/partials/item_edit_modal.html#L82-L96) and [`partials/item_preview_card.html`](file:///home/src/wishenka/web/templates/partials/item_preview_card.html#L56) use inline `onclick="..."` handlers for modal/preview dismissal and quantity stepper bounds checking. Meanwhile, [`quick_add_item`](file:///home/src/wishenka/web/routes/items_ui.py#L327-L337), [`submit_edit_item`](file:///home/src/wishenka/web/routes/items_ui.py#L710), and [`archive_item_ui`](file:///home/src/wishenka/web/routes/items_ui.py#L769-L772) assemble HTMX Out-of-Band (`hx-swap-oob`) reset markup as hardcoded Python f-strings, duplicating the `#quick-add-input` attributes from [`partials/item_quick_add.html`](file:///home/src/wishenka/web/templates/partials/item_quick_add.html#L9-L17).
   - **Impact**: Inline `onclick` handlers prevent enforcing a strict Content Security Policy (`script-src 'self'` without `'unsafe-inline'`), and duplicating `#quick-add-input` in Python code risks attribute divergence if the partial template changes.
   - **Remediation**: Move client-side stepper logic, modal dismissal, and Telegram WebApp Haptic Feedback hooks into delegated event listeners in `wishenka/web/static/miniapp.js`, and render OOB swap fragments via Jinja2 partials/macros.

2. **Manual Form Field Parsing and Duplicated Service Execution Helper in `items_ui.py`**:
   - **Context**: [`wishenka/web/routes/items_ui.py`](file:///home/src/wishenka/web/routes/items_ui.py#L82-L106) manually parses and strips HTML form parameters via `_parse_optional_int` and `_parse_priority` across `quick_add_item` and `submit_edit_item`, duplicating field normalization rules from [`CreateItemDTO`](file:///home/src/wishenka/items/schemas.py#L31) and [`UpdateItemDTO`](file:///home/src/wishenka/items/schemas.py#L50). Additionally, [`_execute`](file:///home/src/wishenka/web/routes/items_ui.py#L44-L49) duplicates the `request.app.state` lookup helper from [`wishenka/web/routes/items.py`](file:///home/src/wishenka/web/routes/items.py#L33).
   - **Impact**: Increases maintenance overhead when adding new item attributes or adjusting validation constraints.
   - **Remediation**: Consolidate form parsing into reusable Pydantic form models (building on **[WISHENKA-103](https://pypost.atlassian.net/browse/WISHENKA-103)**) and extract `_execute` into a shared FastAPI dependency in `wishenka/web/dependencies.py`.

## Missing Tests

1. **Headless Browser (Playwright) E2E Tests for HTMX DOM Swaps, Stepper JS, and Mobile Virtual Keyboard**:
   - **Context**: [`tests/test_wish_items_tma_ui.py`](file:///home/src/tests/test_wish_items_tma_ui.py) comprehensively validates server-rendered HTML partials, `hx-swap-oob` fragments, RBAC visibility, Reduction Lock HTTP 409 error recovery, XSS escaping, and observability logs via FastAPI `TestClient`.
   - **Gap**: `TestClient` does not execute browser JavaScript or HTMX client-side DOM morphing (`htmx.min.js`). Client-side behaviors such as `delay:500ms` debounce cancellation during rapid typing, client-side `+`/`-` stepper button interactions at `min_quantity`, and mobile `visualViewport` keyboard layout shifts are not verified in a real browser engine.
   - **Remediation**: Add a Playwright browser test suite with mobile device emulation testing live HTMX swaps, stepper buttons, and keyboard viewport behavior.

2. **Explicit Timeout Verification in Test Suite**:
   - **Status**: **VERIFIED NON-BLOCKER**. All test modules strictly adhere to the timeout requirement; [`tests/test_wish_items_tma_ui.py`](file:///home/src/tests/test_wish_items_tma_ui.py#L37) explicitly declares `pytestmark = pytest.mark.timeout(30)`, preventing hung test processes.

## Performance Concerns

1. **Redundant Outbound URL Scrapes During Live Input Preview**:
   - **Context**: Every debounced URL change or paste in `#quick-add-input` triggers [`preview_item_input`](file:///home/src/wishenka/web/routes/items_ui.py#L144), which invokes `ItemPreviewService.fetch_preview(raw_input)` without an application-level TTL cache or shared `httpx.AsyncClient` connection pool.
   - **Impact**: Repeatedly pasting the same marketplace link or minor edits to query parameters cause redundant TCP/TLS handshakes (150–350 ms) and synchronous HTML parsing on the event loop.
   - **Cross-Reference**: Tracked in existing backlog issues **[WISHENKA-53](https://pypost.atlassian.net/browse/WISHENKA-53)** (*Persistent HTTP client pool and preview cache*, 3.0 SP) and **[WISHENKA-52](https://pypost.atlassian.net/browse/WISHENKA-52)** (*Non-blocking HTML parsing with threadpool or high-performance parser*, 2.0 SP).

2. **Direct Hotlinking of Unoptimized External Marketplace Images**:
   - **Context**: [`partials/item_card.html`](file:///home/src/wishenka/web/templates/partials/item_card.html#L6-L8), [`partials/item_preview_card.html`](file:///home/src/wishenka/web/templates/partials/item_preview_card.html#L19-L21), and [`partials/item_edit_modal.html`](file:///home/src/wishenka/web/templates/partials/item_edit_modal.html#L146-L148) render `<img src="{{ item.image_url }}">` directly from external marketplace CDNs without `loading="lazy"`, `referrerpolicy="no-referrer"`, or thumbnail proxy caching.
   - **Impact**: Wishlists with dozens of items load full-resolution marketplace images on mobile networks, and strict marketplace CDN `Referer` policies or expiring image URLs can result in broken thumbnails inside Telegram WebView.
   - **Optimization**: Add `loading="lazy"` and `referrerpolicy="no-referrer"` to all item image tags and introduce an optional backend thumbnail proxy/cache.

## Follow-up Tasks

- **Existing Backlog Cross-References**:
  - **[WISHENKA-53](https://pypost.atlassian.net/browse/WISHENKA-53)**: *Persistent HTTP client pool and preview cache* (3.0 Story Points, Medium, Target Epic: `WISHENKA-10`) — directly addresses ephemeral `httpx.AsyncClient` instantiation and uncached URL previews in `POST /web/wishlists/{id}/items/preview`.
  - **[WISHENKA-52](https://pypost.atlassian.net/browse/WISHENKA-52)**: *Non-blocking HTML parsing with threadpool or high-performance parser* (2.0 Story Points, Medium, Target Epic: `WISHENKA-10`) — prevents synchronous BeautifulSoup parsing from blocking concurrent HTMX UI requests.
  - **[WISHENKA-103](https://pypost.atlassian.net/browse/WISHENKA-103)**: *DRY refactoring of CreateItemDTO and UpdateItemDTO schemas* (1.0 Story Points, Low, Target Epic: `WISHENKA-10`) — provides the shared schema foundation for unifying form validation in `items_ui.py`.

- **[WISHENKA-104](https://pypost.atlassian.net/browse/WISHENKA-104) (DEBT-1): Extract inline template JS and hardcoded OOB HTML into `miniapp.js` and Jinja2 partials**
  - *Estimation*: 2.0 Story Points
  - *Description*: Replace inline `onclick` attributes in [`partials/item_edit_modal.html`](file:///home/src/wishenka/web/templates/partials/item_edit_modal.html) and [`partials/item_preview_card.html`](file:///home/src/wishenka/web/templates/partials/item_preview_card.html) with delegated event listeners in `wishenka/web/static/miniapp.js` (including Telegram WebApp `HapticFeedback` and `visualViewport` keyboard positioning), and move raw Python OOB swap strings in [`wishenka/web/routes/items_ui.py`](file:///home/src/wishenka/web/routes/items_ui.py#L327-L337) into reusable Jinja2 partials so strict CSP (`script-src 'self'`) can be enabled.
  - *Priority*: Medium
  - *Target Epic*: WISHENKA-10

- **[WISHENKA-105](https://pypost.atlassian.net/browse/WISHENKA-105) (DEBT-2): Encapsulate item edit context in `WishlistService` and hydrate collaborative member names**
  - *Estimation*: 2.0 Story Points
  - *Description*: Replace direct `svc._items.get(item_id)` access in [`wishenka/web/routes/items_ui.py`](file:///home/src/wishenka/web/routes/items_ui.py#L452) with a public domain method `WishlistService.get_item_edit_context(...)` returning `locked_quantity` safely, and hydrate collaborative wishlist member display names from `UserStore` instead of fallback `"Участник #<id>"` labels.
  - *Priority*: Medium
  - *Target Epic*: WISHENKA-10

- **[WISHENKA-106](https://pypost.atlassian.net/browse/WISHENKA-106) (DEBT-3): Playwright headless browser E2E test suite for TMA HTMX flows and mobile keyboard viewport**
  - *Estimation*: 3.0 Story Points
  - *Description*: Add automated Playwright browser tests with mobile viewport emulation verifying client-side HTMX DOM swaps (`hx-swap-oob`), 500ms input debounce cancellation, quantity stepper button bounds, and `visualViewport` Quick Add Bar positioning.
  - *Priority*: Low
  - *Target Epic*: WISHENKA-10

- **[WISHENKA-107](https://pypost.atlassian.net/browse/WISHENKA-107) (DEBT-4): External product image lazy-loading, `no-referrer` policy, and thumbnail proxy evaluation**
  - *Estimation*: 1.0 Story Points
  - *Description*: Add `loading="lazy"`, `referrerpolicy="no-referrer"`, and fallback image placeholder handling to item thumbnails in [`partials/item_card.html`](file:///home/src/wishenka/web/templates/partials/item_card.html), [`partials/item_preview_card.html`](file:///home/src/wishenka/web/templates/partials/item_preview_card.html), and [`partials/item_edit_modal.html`](file:///home/src/wishenka/web/templates/partials/item_edit_modal.html) to prevent hotlink blocks and reduce mobile bandwidth consumption.
  - *Priority*: Low
  - *Target Epic*: WISHENKA-10

- **Pre-existing test failures**:
  - `None` (All 301 automated tests in the test suite pass with 0 errors).
