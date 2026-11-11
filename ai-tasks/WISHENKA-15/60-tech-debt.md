# WISHENKA-15: Technical Debt Analysis

## Shortcuts Taken

- **Inline JavaScript in `base.html`**: `toggleWishCard` and the drag-and-drop reorder
  handlers are inlined in the global `<head>` of
  [base.html](file:///home/src/wishenka/web/templates/base.html), so they load on every page.
  They should live in a static JS file.
- **Reorder URL derived from `window.location.pathname`** with a regex
  (`/web/wishlists/(\d+)`). The handler breaks silently if the route layout changes. A
  `data-wishlist-id` attribute on `#items-list` would be sturdier.
- **HTML5 drag-and-drop only**: native DnD does not work on touch devices, including Telegram
  mobile clients. The up/down buttons are the touch fallback, so drag is a desktop-only
  enhancement.
- **Ad-hoc schema migration**: `warn_on_delete_reserved` is added to `wl_lists` through a
  `PRAGMA table_info` check and `ALTER TABLE` in
  [store.py](file:///home/src/wishenka/wishlists/store.py), not through a migration framework.
  This matches the existing `display_order` approach.
- **Hardcoded values**: Russian UI strings are in templates with no i18n layer. The
  `"RUB"` currency fallback and the `"Resource not found"` / `"Invalid item order"` messages
  are hardcoded.
- **Unpinned CDN scripts**: htmx is loaded from unpkg with no SRI hash. This is pre-existing.

## Code Quality Issues

- `_NOT_FOUND_ERRORS` includes `WishlistArchivedError`, but `_raise_http` maps that error to
  409. The name is misleading and the tuple should be renamed (e.g. `_DOMAIN_ERRORS`).
- `_reordered_response` takes a `reorder` callable that receives an unused `svc` argument.
  The batch endpoint passes `lambda _svc, _cur: item_ids`. The signature can be simplified.
- `_archived_section_html` hardcodes `can_edit_wishlist=True`, and `_items_list_html` does
  the same. This is safe because the callers are owner-only routes, but the coupling is
  implicit.
- `store.py` uses a redundant `hasattr(r, "warn_on_delete_reserved")` check next to the
  `None` check. The column is always selected.
- `item_card.html` is growing: it holds compact and expanded states, the reservation
  badge, edit, move and archive actions. It could be split into sub-partials.

## Missing Tests

- All five tests in `tests/test_wish_items_list_reorder_ui.py` carry
  `pytestmark = pytest.mark.timeout(30)`, so there is no timeout blocker.
- The JavaScript behaviour is not covered by any automated test. This includes card
  toggling, the DnD ordering and ids payload, and the `aria-expanded` and `hidden`
  synchronisation. Tests only check the server-rendered markup and endpoints. A
  browser-level (Playwright) test is missing.
- There is no explicit test for the migration path that adds `warn_on_delete_reserved` to
  an existing database.
- Concurrent reorder (two sessions) and stale `item_ids` (an item archived mid-drag) are
  covered only by the generic invalid-permutation 400 path.
- There is no keyboard-accessibility test for the card toggle (Enter/Space).

## Performance Concerns

- Every move or reorder re-renders the whole `#items-list` and does two `list_wish_items`
  reads, plus a write. This is acceptable for typical wishlist sizes (tens of items). It
  may need an optimistic or partial swap for very large lists.
- The store rewrites `display_order` for the full list on each reorder (O(n) writes).
- Inline JS adds a few hundred bytes to every page and is not cacheable separately from
  the HTML.

## Follow-up Tasks

- Move the inline JS from `base.html` into a static file (`/static/wishlist.js`), and read
  the wishlist id from a `data-` attribute instead of parsing the URL. (NON-BLOCKER) Jira: [WISHENKA-108](https://pypost.atlassian.net/browse/WISHENKA-108)
- Add touch-friendly drag reordering (pointer events or a library such as SortableJS) for
  Telegram mobile clients. (NON-BLOCKER) Jira: [WISHENKA-109](https://pypost.atlassian.net/browse/WISHENKA-109)
- Add browser-level tests for card toggling and drag-and-drop. (NON-BLOCKER) Jira: [WISHENKA-110](https://pypost.atlassian.net/browse/WISHENKA-110)
- Introduce a proper DB migration mechanism (e.g. Alembic) to replace the ad-hoc `ALTER TABLE`
  checks. (NON-BLOCKER) Jira: [WISHENKA-111](https://pypost.atlassian.net/browse/WISHENKA-111)
- Small cleanup: rename `_NOT_FOUND_ERRORS`, simplify the `reorder` callable signature, and
  drop the redundant `hasattr`. (NON-BLOCKER) Jira: [WISHENKA-112](https://pypost.atlassian.net/browse/WISHENKA-112)
- No pre-existing failing tests were found: the latest `make test` run reported 306 passed.
- Jira keys: none created in this step (the orchestrator decides on ticketing).
