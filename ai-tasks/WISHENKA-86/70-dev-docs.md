# WISHENKA-86: Developer Documentation Summary

## Updated Documentation Files

- [`doc/dev/wishlists.md`](../../doc/dev/wishlists.md):
  - Documented `GET /api/wishlists/deleted` and `POST /api/wishlists/{id}/restore-deleted` in the HTTP API section, including `410 Gone` (`code: "retention_expired"`), `404` (missing / non-owner), `409` (archived), and token rotation behavior.
  - Documented `WishlistService.list_deleted_wishlists` and `WishlistService.restore_deleted_wishlist` (owner-only via `WishlistAccessPolicy.can_restore_deleted`, retention boundary `deleted_at > effective_now - timedelta(days=retention_days)`, `days_remaining` ceiling calculation, `public_token` / `invite_token` rotation, `invite_token_expires_at` reset, and `ACTIVE` / `ARCHIVED` handling).
  - Added audit events `wishlist_deleted_listed`, `wishlist_restored_from_deleted`, `wishlist_restore_retention_expired`, and `wishlist_retention_expired` to the Audit Event Reference table.
  - Added `WishlistRetentionExpiredError` to the domain exception hierarchy and troubleshooting guide, and updated `WishlistDeletedError` resolution notes.

- [`doc/dev/miniapp.md`](../../doc/dev/miniapp.md):
  - Documented the owner-only `Recently deleted` home screen section (`showHome()` in `wishenka/web/static/miniapp.js`) using `miniapp.deleted.*` i18n keys, `GET /api/wishlists/deleted`, `POST /api/wishlists/{id}/restore-deleted`, and `410 Gone` expiration handling.
  - Added `/api/wishlists/deleted` (`GET`) and `/api/wishlists/{id}/restore-deleted` (`POST`) to the HTTP Endpoints Reference table.
