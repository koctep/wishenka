# WISHENKA-9: Technical Debt Analysis

## Shortcuts Taken

1. **Snapshot-rewrite persistence in WishlistStore**:
   - `WishlistStore._write` follows the existing project pattern of clearing and rewriting the entire `wl_favorites` and `wl_view_history` tables on every write transaction (`DELETE FROM wl_favorites`, `DELETE FROM wl_view_history` followed by bulk inserts).
   - This was done to maintain architectural parity with existing snapshot store semantics, but scales with O(N) in total rows across all users instead of incremental row upsert/delete operations.

2. **Client-side triggered history recording**:
   - In `wishenka/web/static/miniapp.js`, viewing history is recorded via a fire-and-forget client-side request `api('/api/history/${id}', {method: 'POST'}).catch(() => {})` inside `showList(id)` rather than being implicitly tracked by the server during authenticated `GET /api/wishlists/{id}`.
   - If a client fails to fire or is interrupted, the view is not captured.

3. **Hardcoded UI localization in Mini App**:
   - Role badge labels in `miniapp.js` (`Владелец`, `Администратор`, `Соавтор`, `Избранное`) are hardcoded in Russian inside `roleLabel()`, while header elements ('My wishlists', 'Viewing history') are in English. The application currently lacks a centralized i18n/localization mechanism.

## Code Quality Issues

1. **Redundant double-logging between Route Handlers and Service Methods**:
   - Both the FastAPI route handlers (`wishenka/web/routes/wishlists.py`) and the domain service (`wishenka/wishlists/service.py`) emit structured logs for the same events (`favorite_added`, `favorite_removed`, `view_history_recorded`, `view_history_cleared`).
   - Route handlers duplicate validation checks (such as checking deleted wishlist status or self-favoriting guard) and emit warning logs before calling service methods that repeat the exact same checks and log statements.

2. **Event name copy-paste discrepancy in `record_view`**:
   - In `wishenka/wishlists/service.py` (lines 1800–1807) and `wishenka/web/routes/wishlists.py` (lines 346–353), the deleted wishlist check in `record_view` logs the event as `favorite_deleted_wishlist_denied` instead of `view_history_deleted_wishlist_denied`.

3. **In-memory filtering across global history in WishlistService**:
   - In `wishenka/wishlists/service.py`, `record_view`, `get_history`, and `clear_history` perform list comprehensions over the global in-memory `self._view_history` list (`[e for e in self._view_history if e.user_id == user.telegram_id]`). As viewing history accumulates across multiple users, global list traversals become less efficient.

## Missing Tests

1. **Concurrent view history updates under race conditions**:
   - Sequential ordering, deduplication, and bounds (20 entries) are verified in `tests/test_wishlist_sections_ui.py`, but concurrent asynchronous `record_view` calls for the same user/wishlist under heavy parallel load were not simulated.

2. **Multi-user view history isolation at scale**:
   - While tests verify that User A and User B maintain distinct histories, there is no stress test verifying that pruning User A's history past 20 items leaves User B's entries completely unaffected when both have extensive history lists.

3. **Automated accessibility testing (a11y)**:
   - While DOM regions, `aria-label` attributes, and badge role spans were added, automated axe-core/accessibility scans for screen reader tree compatibility in Telegram Mini App have not yet been integrated into CI.

## Performance Concerns

1. **Write lock contention on frequent view tracking**:
   - Because viewing history is recorded on every wishlist view, and every write transaction locks and flushes the entire SQLite snapshot, high view traffic will create frequent database rewrite transactions.
   - Migrating viewing history to an append-only table with indexed user queries will be required for production scaling.

2. **Two HTTP roundtrips on Mini App home view**:
   - Opening the home screen initiates two parallel API requests (`/api/wishlists` and `/api/favorites`). Consolidating or caching these responses would improve load latency on high-latency mobile networks.

## Follow-up Tasks

1. **Incremental CRUD persistence for Favorites and History**:
   - Refactor `WishlistStore` to update `wl_favorites` and `wl_view_history` via targeted `INSERT`, `DELETE`, and `UPDATE` statements rather than full table snapshot flushes.
   - Priority: Medium.
   - Jira: [WISHENKA-72](https://pypost.atlassian.net/browse/WISHENKA-72) (3 SP)

2. **Deduplicate route-level logging and fix event name typo**:
   - Remove redundant log statements in `wishenka/web/routes/wishlists.py` where `WishlistService` already provides comprehensive audit logging.
   - Fix event name in `record_view` deleted wishlist check to `view_history_deleted_wishlist_denied`.
   - Priority: Low.
   - Jira: [WISHENKA-70](https://pypost.atlassian.net/browse/WISHENKA-70) (1 SP)

3. **Server-side implicit view recording**:
   - Record view events directly inside `GET /api/wishlists/{id}` when an authenticated session is present, eliminating the client-side extra `POST /api/history/{id}` roundtrip.
   - Priority: Medium.
   - Jira: [WISHENKA-71](https://pypost.atlassian.net/browse/WISHENKA-71) (2 SP)

4. **Mini App i18n localization**:
   - Introduce a structured localization dictionary or helper for Mini App interface strings, ensuring consistent Russian/English display across all views and badges.
   - Priority: Low.
   - Jira: [WISHENKA-73](https://pypost.atlassian.net/browse/WISHENKA-73) (3 SP)
