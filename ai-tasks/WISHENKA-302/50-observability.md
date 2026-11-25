# WISHENKA-302: Observability Implementation

## Logging Implementation

### Added Logs

Describe added logging:
- **EMERG**: N/A
- **ALERT**: N/A
- **CRIT**: N/A
- **ERR**: N/A
- **WARNING**:
  - `wishenka/wishlists/repo_ops.py` (`RepoWishlistOps.add_favorite`) and `wishenka/wishlists/service.py` (`WishlistService.add_favorite`) — `event="favorite_access_denied"` when a non-owner lacks membership or a valid `wl_share_access` grant; logs `wishlist_id` and `user_id` only, without leaking wishlist existence/title/owner PII or `public_token`.
  - `wishenka/wishlists/repo_ops.py` (`RepoWishlistOps.add_favorite`) and `wishenka/wishlists/service.py` (`WishlistService.add_favorite`) — `event="favorite_deleted_wishlist_denied"` (on soft-deleted wishlist) and `event="favorite_own_wishlist_denied"` (on self-favoriting), without duplicating logs at `wishenka/web/routes/wishlists.py`.
  - `wishenka/web/security.py` (`BrowserSecurityMiddleware.dispatch` using shared `sanitize_log_path`) — `event="csrf_origin_mismatch"` and `event="csrf_token_invalid"` redact public capability paths (`/api/public/wishlists/{token}`, `/share/{token}`, `/invite/{token}`, `/invite/{token}/join`) in both the log message and `extra["path"]` so `public_token` is never leaked on CSRF rejection. (`wishenka/web/app.py` `ShareTokenAccessFilter` and `RequestLoggingMiddleware` also reuse `sanitize_log_path`.)
- **NOTICE**: N/A
- **INFO**:
  - `wishenka/wishlists/repo_ops.py` (`RepoWishlistOps.get_wishlist_by_public_token`) and `wishenka/wishlists/service.py` (`WishlistService.get_wishlist_by_public_token`) — `event="share_access_granted"` when an authenticated non-owner resolves a non-deleted wishlist via its active share link (`wishlist_id`, `user_id`; `public_token` is never logged).
  - `wishenka/wishlists/repo_ops.py` (`RepoWishlistOps.remove_member`) and `wishenka/wishlists/service.py` (`WishlistService.remove_member`) — `event="favorite_access_revoked"` with `reason="member_removed"` (`wishlist_id`, `user_id`, `actor_id`) when removing a collaborator also removes their favorite because they hold no active share-link grant.
  - `wishenka/wishlists/repo_ops.py` (`RepoWishlistOps._revoke_share_access_and_favorites` called from `regenerate_public_token` and `restore_deleted_wishlist`) and `wishenka/wishlists/service.py` (`WishlistService._revoke_share_access_for_wishlist` called from `regenerate_public_token`, `restore_deleted_wishlist`, and `transfer_ownership`) — `event="share_access_revoked"` with `reason` (`"public_token_rotated"`, `"wishlist_restored"`, or `"ownership_transferred"`), `wishlist_id`, `actor_id`, `revoked_grants`, and `revoked_favorites` when grants or non-member favorites are revoked.
- **DEBUG**: N/A

### Log Structure

Log format used:
- Structured logs: yes (`extra={"event": ..., ...}` on `wishenka.wishlists` logger; no duplicate emission at HTTP route layer). Both `TextFormatter` (default when `log_json=False`, appending `key=value` pairs) and `JsonFormatter` (when `log_json=True`, emitting JSON lines with `"extra"`) preserve all structured `extra` fields in formatted output.
- Includes context: yes (`wishlist_id`, `user_id`, `actor_id`, `reason`, `revoked_grants`, `revoked_favorites`; excludes `public_token`, wishlist titles, and user PII)
- Log levels: `INFO`, `WARNING`

## Metrics Implementation (if applicable)

### Performance Metrics

N/A — the project uses structured application logging without Prometheus/OpenTelemetry metrics counters in the wishlist domain layer.

### Business Metrics

N/A

### System Health Metrics

N/A

## Monitoring Integration

Integration with monitoring systems (no external monitoring or log-aggregation system is configured in the repository):
- [ ] Prometheus metrics (N/A — not configured in the repository)
- [ ] Grafana dashboards (N/A — not configured in the repository)
- [ ] Alerting rules (N/A — not configured in the repository)
- [ ] Log aggregation (N/A — no external log collector is configured in the repository; structured stdout logs with `extra` fields on `wishenka.wishlists` are emitted via `TextFormatter` / `JsonFormatter` and ready for collection when an external collector is attached)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (`make analyze`: Ruff lint passed, Ruff format passed across 284 files, Mypy passed across 284 source files; both `TextFormatter` and `JsonFormatter` output verified in `tests/test_favorites_access_control.py::test_favorites_access_control_formatted_log_output`, `tests/test_favorites_access_control.py::test_csrf_rejected_public_reservation_does_not_leak_token`, and `tests/test_observability.py::test_text_formatter_preserves_extras`)
- [x] Metrics are collected correctly (N/A)
- [x] Logging works in error scenarios (`favorite_access_denied` WARNING and CSRF-rejected `POST /api/public/wishlists/{token}/items/{item_id}/reservations` WARNINGs verified in `tests/test_favorites_access_control.py` and `tests/test_wishlist_sections_observability.py`)
- [x] Large data structures are not logged (verified: only scalar IDs, counts, and reason strings; secret `public_token` and wishlist titles verified absent from `wishenka.*` log records and formatted `TextFormatter`/`JsonFormatter` outputs, including CSRF rejection paths)
- [x] Metrics are available for monitoring (N/A)

Targeted test execution:
- `rm -rf /dev/shm/wishenka-pytest-* && make test-serial PYTEST_ARGS="tests/test_favorites_access_control.py tests/test_wishlist_sections_observability.py tests/test_observability.py"`: **25 passed, 1 warning in 2.40s**.

## Notes

- Route-level handlers in `wishenka/web/routes/wishlists.py` and `wishenka/web/routes/sharing.py` intentionally do not emit duplicate `share_access_granted`, `favorite_access_denied`, `favorite_access_revoked`, or `share_access_revoked` logs.
- `WishlistRepository.revoke_share_access_for_wishlist`, `delete_non_member_favorites`, and `delete_favorite_if_no_share_access` in `wishenka/wishlists/repository.py` now return `int` deleted row counts so `RepoWishlistOps` only queues revocation events when rows are actually affected.
- `WishlistRepository.upsert_share_access` returns `bool` (`rowcount > 0`), and `WishlistStore._upsert_dirty_share_access` drops deferred `share_access_granted` logs when 0 rows are persisted (e.g., user missing from `users`), so `share_access_granted` is only emitted when a grant row is actually written.
- `share_access_granted`, `share_access_revoked`, and `favorite_access_revoked` are deferred via `WishlistService._emit_or_defer_commit_log` (flushed by `WishlistStore` after `conn.commit()`) and `WishlistRepository.defer_commit_log` (flushed by `get_wishlist_repository` after `conn.commit()`, cleared on rollback) so rolled-back transactions never emit these events, while standalone `WishlistService.in_memory()` calls continue to log immediately.
