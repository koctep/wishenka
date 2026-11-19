# WISHENKA-107: Technical Debt Analysis

## Shortcuts Taken

- **Mocked Node VM DOM instead of a real browser test for `handleImageError`**: `tests/test_item_image_loading_repro.py::test_app_js_handles_image_error_in_capture_phase` evaluates `wishenka/web/static/app.js` in a Node `vm` sandbox with hand-rolled `document` / `img` stubs (and skips if `node` is unavailable), rather than exercising a real browser DOM via the existing Chromium/CDP test harness (`tests/browser_support.py`).
- **Pre-rendered sibling placeholder in all three partials**: Instead of a shared Jinja2 macro, the `<img ... data-img-fallback>` + `<div class="item-thumbnail-placeholder" ... hidden>🎁</div>` pair is written inline in `item_card.html`, `item_preview_card.html`, and `item_edit_modal.html`.
- **No live preview refresh on URL edit in `item_edit_modal.html`**: Changing `#item-image-url-input` does not dynamically update or reset the `4rem` preview thumbnail until the form is submitted and re-rendered by the server (consistent with the current SSR/HTMX modal design).

## Code Quality Issues

- **Minor template duplication**: The thumbnail + hidden placeholder markup (`loading="lazy"`, `referrerpolicy="no-referrer"`, `data-img-fallback`, `.item-thumbnail-placeholder[hidden]`, `🎁`) is repeated across `wishenka/web/templates/partials/item_card.html`, `item_preview_card.html`, and `item_edit_modal.html`. Extracting a Jinja2 macro would reduce drift risk if additional thumbnail contexts are added later.
- **Hardcoded placeholder visual**: The `🎁` emoji and `#f3e8ec` background color in `.item-thumbnail-placeholder` (`wishenka/web/static/miniapp.css`) are hardcoded rather than themed via CSS custom properties, and legacy Tailwind-style utility classes (`w-12`, `h-12`, `w-16`, `h-16`, `rounded`, `border`) remain in the templates alongside the explicit `.item-thumbnail` / `.item-thumbnail--lg` CSS rules.
- **Explicit timeout markers**: Verified — `tests/test_item_image_loading_repro.py` declares `pytestmark = pytest.mark.timeout(30)` (no blocker).

## Missing Tests

- **Real browser (Chromium/CDP) E2E test for image fallback & computed styles** (`NON-BLOCKER`): There is no browser-level test verifying that:
  1. A real `<img>` element failing to load in Chromium fires a non-bubbling `error` event caught by `document.addEventListener('error', handleImageError, true)` in `app.js`.
  2. `.item-thumbnail[hidden]` and `.item-thumbnail-placeholder[hidden]` (`display: none`) properly override `.item-thumbnail-placeholder { display: flex; }` in computed styles, and removing `hidden` restores `display: flex`.
  3. Dynamic HTMX swaps (`item_preview_card`, `item_edit_modal`, OOB `item_card`) trigger the fallback identically without re-binding listeners.

## Performance Concerns

- **Direct third-party image requests remain**: By design (`10-requirements.md`), server-side image proxying and caching were out of scope for `WISHENKA-107`. External marketplace CDNs can still fail due to hotlink rules beyond `Referer`, regional blocks, TLS/CSP (`img-src 'self' https:`), or link rot — in those cases the user now sees the fallback placeholder instead of a broken image icon, while bandwidth/availability still depend on the origin CDN.

## Follow-up Tasks

- **Browser E2E test for image fallback & CSS `[hidden]` behavior (`NON-BLOCKER`, Low)**: Add a Chromium/CDP test (using `tests/browser_support.py`) that loads a wishlist page with a broken `image_url` (e.g. local 404 route), asserts `img` becomes hidden and `.item-thumbnail-placeholder` has computed `display: flex`, and verifies HTMX-swapped `item_preview_card` / `item_edit_modal` fallback behavior. — Jira: [WISHENKA-271](https://pypost.atlassian.net/browse/WISHENKA-271)
- **Extract Jinja2 thumbnail macro (`NON-BLOCKER`, Low)**: Consolidate the `<img data-img-fallback>` + `.item-thumbnail-placeholder` markup from `item_card.html`, `item_preview_card.html`, and `item_edit_modal.html` into a shared partial/macro if more thumbnail surfaces are introduced. — Jira: [WISHENKA-270](https://pypost.atlassian.net/browse/WISHENKA-270)
