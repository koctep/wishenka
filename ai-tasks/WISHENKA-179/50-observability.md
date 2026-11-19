# WISHENKA-179: Observability Implementation

## Logging Implementation

### Existing Structured Logging Evaluated (No New Ad-Hoc Logs Needed)

No new production logs were added because existing structured logging in `WishlistStore.execute_with_connection` (`wishenka/wishlists/store.py`) and the bot capture callback handler (`wishenka/bot/capture.py`) already covers the new atomic seam and post-commit guarantees:

- **ERROR**: `wishenka/wishlists/store.py` (`WishlistStore.execute_with_connection`, lines 1604-1607) — `event="wishlist_store_integrity_error"` on non-token-collision `IntegrityError` (plus `_raise_for_storage_error` for `SQLAlchemyError` on line 1621).
- **ERROR**: `wishenka/wishlists/store.py` (`WishlistStore._flush_receipt_effects`, lines 1012-1018) — `event="receipt_notice_enqueue_failed"` with `error_class` if outbox notice enqueueing fails during `_write`.
- **ERROR**: `wishenka/bot/capture.py` (callback handler around `store.execute_with_connection(mutate)`, lines 682-685) — `event="bot_capture_action_error"` when `execute_with_connection(mutate)` raises.
- **WARNING**: `wishenka/wishlists/store.py` (`WishlistStore.execute_with_connection`, lines 1590-1596, 1610-1616) — `event="wishlist_token_collision_retry"` with `attempt` on capability/public/invite token collisions before retry.
- **INFO**: `wishenka/bot/capture.py` (lines 686-690) — `event="bot_capture_save"` with `outcome` (`"saved"`, `"unavailable"`, `"unsafe_url"`, `"invalid"`, `"expired"`) after `store.execute_with_connection(mutate)` completes for `command == "save"`.
- **DEBUG** (post-commit only): `wishenka/wishlists/store.py` (`WishlistStore._execute_once`, lines 1699-1701):
  - `_log_flushed_notices(flushed)` (lines 340-356) — emits `event="receipt_notice_skipped"` (`outbox_id`, `gate`) or `event="receipt_notice_created"` (`outbox_id`) only after `self._immediate(work)` commits.
  - `_log_flushed_shared_events(flushed_shared)` (lines 359-372) — emits `event="shared_notice_events_queued"` (`kind`, `queued_count`) after commit.
  - `flush_pending_commit_logs(pending_commit_logs)` (line 1701, defined in `wishenka/wishlists/service.py`) — flushes domain `PendingCommitLog` records after commit so rolled-back or retried attempts do not emit premature commit logs.

### Log Structure

Log format used:
- Structured logs: yes (`extra={"event": ..., ...}`)
- Includes context: yes (`attempt`, `error_class`, `outcome`, `outbox_id`, `gate`, `kind`, `queued_count` — without PII or large payloads)
- Log levels: `ERROR`, `WARNING`, `INFO`, `DEBUG`

## Metrics Implementation (if applicable)

### Performance Metrics

N/A — the repository does not expose Prometheus/OpenTelemetry metric registries in `wishenka/wishlists/store.py` or `wishenka/bot/capture.py`; existing structured logging provides operational visibility.

### Business Metrics

N/A — covered by structured `event="bot_capture_save"` (`outcome`) and post-commit notice/domain logs.

### System Health Metrics

N/A — no new system health metrics required for this internal store seam refactor.

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A for this codebase)
- [ ] Grafana dashboards (N/A for this codebase)
- [ ] Alerting rules (N/A for this codebase)
- [x] Log aggregation (structured `extra={"event": ...}` fields preserved across `execute_with_connection` and `bot/capture.py`)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (verified `extra={"event": ...}` fields in `wishenka/wishlists/store.py` and `wishenka/bot/capture.py`)
- [x] Post-commit log flushing (`flushed`, `flushed_shared`, `pending_commit_logs`) executes only after `self._immediate(work)` commits in `WishlistStore._execute_once`
- [x] Logging works in error scenarios (`wishlist_store_integrity_error`, `wishlist_token_collision_retry`, `receipt_notice_enqueue_failed`, `bot_capture_action_error`)
- [x] Large data structures are not logged (draft JSON, URLs, tokens, and full item payloads are excluded)

## Notes

`WishlistStore.execute` delegates directly to `WishlistStore.execute_with_connection`, so all store operations and `wishenka/bot/capture.py:mutate` share the exact same retry, error-mapping, and post-commit log flushing behavior.
