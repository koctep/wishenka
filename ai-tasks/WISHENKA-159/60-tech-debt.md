# WISHENKA-159: Technical Debt Analysis

## Shortcuts Taken

- **Test-only detachment mechanism**: `tests/test_wishlist_fail_closed_repro.py` simulates a missing parent wishlist by mutating `service._items[item.id].wishlist = None` directly on the in-memory service state. This is appropriate because normal persistence and `WishlistService.add_wish_item` always attach `item.wishlist`, but it relies on internal `_items` storage.
- **Scope bounded to the four `WishItem` mutation guards**: Per `ai-tasks/WISHENKA-159/10-requirements.md`, only the four `wl is not None` guards on `WishItem` mutations (`update_wish_item`, `create_reservation`, `record_item_fulfillment`, `_validate_receipt_mutation_access`) were converted to fail-closed via `_require_item_wishlist(item)`. Related fail-open checks on `Reservation` mutations (`_ensure_reservation_writable` and `_guard_reservation_mutation` in `wishenka/wishlists/service.py:427-455`) and post-mutation notification helpers (`_record_reservation_confirmation` at `:310-324`, `_record_receipt_change_event` at `:372-396`) were intentionally left unchanged.

## Code Quality Issues

- **Repeated wishlist status checks across mutation methods**: After `wl = self._require_item_wishlist(item)`, each guarded method (`update_wish_item`, `create_reservation`, `record_item_fulfillment`, `_validate_receipt_mutation_access`) still performs its own `ARCHIVED` / `DELETED` status check with slightly varying error messages and logging. Consolidating these into a shared helper (similar to `_ensure_wishlist_active`) would reduce duplication, though it was kept out of scope to avoid altering existing error messages or log events.
- **Optional `WishItem.wishlist` model typing**: `WishItem.wishlist` in `wishenka/wishlists/models.py` remains typed as `Wishlist | None = None`, which requires runtime `_require_item_wishlist(item)` checks at every service boundary rather than enforcing non-nullability at construction/hydration time.

## Missing Tests

- **Observability log assertion**: `tests/test_wishlist_fail_closed_repro.py` verifies `WishlistNotFoundError` and zero state mutation across all five guarded entrypoints, and has explicit `pytestmark = pytest.mark.timeout(30)`, but does not assert via `caplog` that `WishlistService._require_item_wishlist` emits the `ERROR` log with `event="item_missing_parent_wishlist"`, `item_id`, and `wishlist_id`.
- **HTTP route / `WishlistStore` integration**: There is no route-level integration test verifying the HTTP 404 mapping when `WishlistNotFoundError` is raised from `_require_item_wishlist`, though existing route exception handlers already map `WishlistNotFoundError`.

## Performance Concerns

- None. `_require_item_wishlist` performs a single `is None` reference check on an already-loaded `WishItem` object with zero additional I/O or queries.

## Follow-up Tasks

- **Convert remaining fail-open `Reservation` mutation guards (`NON-BLOCKER`)**: Audit `_ensure_reservation_writable` (`wishenka/wishlists/service.py:427-433`) and `_guard_reservation_mutation` (`wishenka/wishlists/service.py:435-455`) where `item is not None` / `wishlist is not None` silently skips `ARCHIVED`, `DELETED`, and `is_recipient` checks if `reservation.wish_item` or `item.wishlist` is `None`. Jira: [WISHENKA-238](https://pypost.atlassian.net/browse/WISHENKA-238)
- **Add `caplog` assertion for `item_missing_parent_wishlist` (`NON-BLOCKER`)**: Extend `tests/test_wishlist_fail_closed_repro.py` to assert the structured `ERROR` log event emitted by `WishlistService._require_item_wishlist`. Jira: [WISHENKA-237](https://pypost.atlassian.net/browse/WISHENKA-237)
