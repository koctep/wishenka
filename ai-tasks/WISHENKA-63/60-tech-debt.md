# WISHENKA-63: Technical Debt Analysis

## Shortcuts Taken

- **Untyped dict mapping in legacy public endpoint (`wishenka/web/routes/wishlists.py`)**: `public_wishlist` (`GET /api/public/wishlists/{token}`) manually builds a `dict[str, Any]` from `WishlistDetailViewDTO` (renaming `view.title` to `"name"` and computing `"is_active"` inline as `not item.is_archived and (item.remaining_quantity or 0) > 0`) to preserve backward-compatible JSON keys rather than introducing a typed Pydantic response schema or retiring the legacy route.
- **Private flag escape hatch in `WishlistService.__init__` (`wishenka/wishlists/service.py`)**: Enforcing persistent `WishlistStore` uses a keyword-only `_allow_in_memory: bool = False` parameter combined with `WishlistService.in_memory()` instead of separating a pure in-memory domain engine from a store-backed service class.

## Code Quality Issues

- **Overlapping public JSON endpoints (`wishenka/web/routes/wishlists.py`)**: Both `GET /api/public/wishlists/{token}` (`public_wishlist`) and `GET /api/public/wishlists/{token}/view` (`public_wishlist_view`) remain active with slightly different response shapes (`name` vs `title`, `identified` flag, `is_active` field).
- **Conflated `is_recipient` log attribute for anonymous visitors (`wishenka/web/routes/sharing.py`)**: `view_public_share` computes `is_recipient = any(getattr(item, "is_recipient", False) for item in dto.items) or (not dto.is_collaborative and dto.user_role == WishlistRole.OWNER)`. Because `project_wish_item(item, None)` returns `WishItemRecipientViewDTO` (`is_recipient=True`) for anonymous visitors, `wishlist_shared_view` logs `is_recipient=True` for unauthenticated visitors on non-empty wishlists.
- **Indirect `projection_mode` inference (`wishenka/wishlists/service.py`)**: `WishlistService.get_wishlist_by_public_token` infers `projection_mode` (`"anonymous_safe"`, `"recipient_safe"`, `"gifter"`) by inspecting `isinstance(item, WishItemGifterViewDTO)` on the returned `view.items` rather than deriving it directly from `WishlistAccessPolicy.resolve_context(current_user, wl)`.

## Missing Tests

- No HTTP-level test in `tests/test_wishenka_63_repro.py` covers `GET /api/public/wishlists/{token}` returning `404` for a deleted wishlist.
- Collaborative admin and item-recipient Surprise Invariant checks are verified at the service layer (`get_wishlist_view` and `get_wishlist_by_public_token`), but not via an HTTP `GET /share/{public_token}` request with authenticated collaborative members.
- Timeout markers: `tests/test_wishenka_63_repro.py` has `pytestmark = pytest.mark.timeout(30)` (no missing timeout markers).

## Performance Concerns

- **Linear scan and full-store hydration (`wishenka/wishlists/service.py`, `wishenka/wishlists/store.py`)**: `WishlistService.get_wishlist_by_public_token` performs an `O(N)` scan (`next((w for w in self._wishlists.values() if w.public_token == public_token), None)`) over all wishlists in memory, and `WishlistStore._read` hydrates all wishlists into `WishlistService.in_memory()` per transactional read. Query-level optimization was explicitly out of scope for `WISHENKA-63` (`10-requirements.md`), but remains a scalability concern as data volume grows.

## Follow-up Tasks

- Unify or deprecate `GET /api/public/wishlists/{token}` in favor of `GET /api/public/wishlists/{token}/view` with a typed Pydantic response model (`wishenka/web/routes/wishlists.py`) — Jira: [WISHENKA-225](https://pypost.atlassian.net/browse/WISHENKA-225).
- Fix `is_recipient` observability logging in `view_public_share` (`wishenka/web/routes/sharing.py`) to distinguish anonymous visitors (`current_user is None`) from authenticated recipients, and derive `projection_mode` in `WishlistService.get_wishlist_by_public_token` from `WishlistAccessPolicy` — Jira: [WISHENKA-226](https://pypost.atlassian.net/browse/WISHENKA-226).
- Replace full-store hydration + linear `public_token` scan with an indexed `public_token` query in `WishlistStore` (out-of-scope scalability follow-up) — Jira: [WISHENKA-225](https://pypost.atlassian.net/browse/WISHENKA-225).
- Add HTTP-level regression tests for deleted wishlist `404` on `/api/public/wishlists/{token}` and authenticated collaborative member access on `/share/{public_token}` — Jira: [WISHENKA-226](https://pypost.atlassian.net/browse/WISHENKA-226).
