# WISHENKA-303: Observability Implementation

## Logging Implementation

### Added Logs

Describe added logging:
- **EMERG**: N/A
- **ALERT**: N/A
- **CRIT**: N/A
- **ERR**: N/A
- **WARNING**:
  - `wishenka/wishlists/repo_ops.py` (`RepoWishlistOps.record_view`) and `wishenka/wishlists/service.py` (`WishlistService.record_view`) — `event="view_history_access_denied"` when a non-owner lacks membership or a valid `wl_share_access` grant; logs `wishlist_id` and `user_id` only, without leaking wishlist existence/title/owner PII or `public_token`.
  - `wishenka/wishlists/repo_ops.py` (`RepoWishlistOps.record_view`) and `wishenka/wishlists/service.py` (`WishlistService.record_view`) — `event="view_history_deleted_wishlist_denied"` when attempting to record view history on a soft-deleted wishlist, without duplicating logs at `wishenka/web/routes/wishlists.py`.
  - `wishenka/wishlists/alembic/versions/purge_legacy_non_member_view_history.py` (`downgrade`) — `event="wishlist_migration_downgrade_refused"` with `revision="purge_legacy_non_member_view_history"` when one-way migration downgrade is refused.
- **NOTICE**: N/A
- **INFO**:
  - `wishenka/wishlists/repo_ops.py` (`RepoWishlistOps.remove_member`) and `wishenka/wishlists/service.py` (`WishlistService.remove_member`) — `event="view_history_access_revoked"` with `reason="member_removed"` (`wishlist_id`, `user_id`, `actor_id`) emitted post-commit when removing a collaborator also deletes their viewing history because they hold no active share-link grant.
  - `wishenka/wishlists/repo_ops.py` (`RepoWishlistOps._revoke_share_access_and_favorites` called from `regenerate_public_token` and `restore_deleted_wishlist`) and `wishenka/wishlists/service.py` (`WishlistService._revoke_share_access_for_wishlist` called from `regenerate_public_token`, `restore_deleted_wishlist`, and `transfer_ownership`) — `event="share_access_revoked"` emitted post-commit with `reason` (`"public_token_rotated"`, `"wishlist_restored"`, or `"ownership_transferred"`), `wishlist_id`, `actor_id`, `revoked_grants`, `revoked_favorites`, and `revoked_history` when grants, non-member favorites, or non-member view history rows are revoked.
  - `wishenka/wishlists/alembic/versions/purge_legacy_non_member_view_history.py` (`upgrade`) — `event="legacy_non_member_view_history_purged"` with `rows=purged` after purging legacy unverified non-member `wl_view_history` rows.
- **DEBUG**: N/A

### Log Structure

Log format used:
- Structured logs: yes (`extra={"event": ..., ...}` on `wishenka.wishlists` and `wishenka.wishlists.migrations` loggers; no duplicate access-control emission at HTTP route layer). Both `TextFormatter` (default when `log_json=False`, appending `key=value` pairs) and `JsonFormatter` (when `log_json=True`, emitting JSON lines with `"extra"`) preserve all structured `extra` fields in formatted output.
- Includes context: yes (`wishlist_id`, `user_id`, `actor_id`, `reason`, `revoked_grants`, `revoked_favorites`, `revoked_history`, `rows`, `revision`; excludes `public_token`, wishlist titles, and user PII)
- Log levels: `INFO`, `WARNING`

## Metrics Implementation (if applicable)

### Performance Metrics

N/A — the project uses structured application logging without Prometheus/OpenTelemetry metrics counters in the wishlist domain layer.

### Business Metrics

N/A

### System Health Metrics

N/A

## Monitoring Integration

Integration with monitoring systems (N/A — no external monitoring or log-aggregation system is configured in the repository):
- [ ] Prometheus metrics (N/A — not configured in the repository)
- [ ] Grafana dashboards (N/A — not configured in the repository)
- [ ] Alerting rules (N/A — not configured in the repository)
- [ ] Log aggregation (N/A — no external log collector is configured in the repository; structured stdout logs with `extra` fields on `wishenka.wishlists` are emitted via `TextFormatter` / `JsonFormatter` and ready for collection when an external collector is attached)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (`make analyze`: Ruff lint passed, Ruff format passed across 286 files, Mypy passed across 286 source files; both `TextFormatter` and `JsonFormatter` output verified in `tests/test_history_access_control.py::test_history_access_control_formatted_log_output` and `tests/test_observability.py::test_text_formatter_preserves_extras`)
- [x] Metrics are collected correctly (N/A)
- [x] Logging works in error scenarios (`view_history_access_denied` WARNING, `view_history_deleted_wishlist_denied` WARNING, and `wishlist_migration_downgrade_refused` WARNING verified in `tests/test_history_access_control.py` and `tests/test_wishlist_sections_observability.py`)
- [x] Large data structures are not logged (verified: only scalar IDs, counts, revision names, and reason strings; secret `public_token` and wishlist titles verified absent from `wishenka.wishlists` log records and formatted `TextFormatter`/`JsonFormatter` outputs)
- [x] Metrics are available for monitoring (N/A)

Targeted test execution:
- `rm -rf /dev/shm/wishenka-pytest-* && make test-serial PYTEST_ARGS="tests/test_history_access_control.py tests/test_wishlist_sections_observability.py tests/test_observability.py"`: **24 passed, 1 warning in 2.79s**.

## Notes

- Route-level handlers in `wishenka/web/routes/wishlists.py` (`get_history`, `record_view`, `get_public_wishlist_view`) and `wishenka/web/routes/sharing.py` (`view_shared_wishlist`) intentionally do not emit duplicate `view_history_access_denied`, `view_history_access_revoked`, or `share_access_revoked` logs.
- `WishlistRepository.delete_non_member_history` and `WishlistRepository.delete_history_if_no_share_access` in `wishenka/wishlists/repository.py` return `int` deleted row counts so `RepoWishlistOps` only queues `view_history_access_revoked` / `share_access_revoked` events when rows are actually affected.
- `view_history_access_revoked` and `share_access_revoked` are deferred via `WishlistService._emit_or_defer_commit_log` (flushed by `WishlistStore` after `conn.commit()`) and `WishlistRepository.defer_commit_log` (flushed by `get_wishlist_repository` after `conn.commit()`, cleared on rollback) so rolled-back transactions never emit these events (verified in `tests/test_history_access_control.py::test_history_access_control_events_not_emitted_on_transaction_rollback`), while standalone `WishlistService.in_memory()` calls continue to log immediately.
