# WISHENKA-50: Observability Implementation

## Logging Implementation

### Added Logs

Structured logging events added for token TTL management, background cleanup, and repository:
- **ERR**:
  - `wishenka.wishlists.cleanup`: `background_cleanup_failed` - logged when an operational
    exception occurs during background cleanup (includes `error`, `duration_ms`, and `exc_info`).
- **INFO**:
  - `wishenka.wishlists.cleanup`: `background_worker_started` - background worker startup event
    including configured `interval_seconds`.
  - `wishenka.wishlists.cleanup`: `background_worker_stopped` - worker termination event emitted
    gracefully when the background task is cancelled or stopped during lifespan shutdown.
  - `wishenka.wishlists.cleanup`: `background_cleanup_completed` - cleanup cycle summary with
    `duration_ms`, `expired_tokens_cleaned`, and `wishlists_purged`.
  - `wishenka.wishlists.repository`: `wishlist_repo_mutation` with `entity="invite_token"` and
    `operation="cleanup_expired"` - logged when expired tokens are revoked.
  - `wishenka.wishlists.repository`: `wishlist_repo_mutation` with `entity="wishlist"` and
    `operation="purge_archived"` - logged when soft-deleted wishlists past retention are purged.

### Log Structure

Structured logging schema:
- Structured logs: yes (all events use `extra` dict formatted as JSON via `JsonFormatter`).
- Includes context: yes (timestamps, durations, counts, entity, operation, error messages).
- Log levels: `INFO`, `ERROR`.
- Zero-leakage invariant: capability tokens (e.g., `invite_token`, `public_token`) are NEVER
  emitted in log records, messages, or extra metadata.

#### Schema of Events and Attributes

1. `background_worker_started`:
   - `event`: `"background_worker_started"`
   - `interval_seconds`: `int` (cleanup interval in seconds)

2. `background_worker_stopped`:
   - `event`: `"background_worker_stopped"`

3. `background_cleanup_completed`:
   - `event`: `"background_cleanup_completed"`
   - `duration_ms`: `float` (execution time in milliseconds)
   - `expired_tokens_cleaned`: `int` (count of expired invite tokens revoked)
   - `wishlists_purged`: `int` (count of soft-deleted wishlists permanently removed)

4. `background_cleanup_failed`:
   - `event`: `"background_cleanup_failed"`
   - `error`: `str` (human-readable error description)
   - `duration_ms`: `float` (time elapsed before failure)

5. `wishlist_repo_mutation` (invite token cleanup):
   - `event`: `"wishlist_repo_mutation"`
   - `entity`: `"invite_token"`
   - `operation`: `"cleanup_expired"`
   - `count`: `int` (number of modified rows)

6. `wishlist_repo_mutation` (archived wishlist purge):
   - `event`: `"wishlist_repo_mutation"`
   - `entity`: `"wishlist"`
   - `operation`: `"purge_archived"`
   - `count`: `int` (number of deleted wishlists)
   - `threshold`: `str` (ISO-8601 retention cutoff timestamp)

## Metrics Implementation

### Performance Metrics

- **Execution time**: `duration_ms` recorded for both successful cycles and failure paths in
  `background_cleanup_completed` and `background_cleanup_failed`.
- **Database lock latency**: repository mutation execution duration captured via caller cycles.

### Business & Operational Indicators

- **Token churn rate**: `expired_tokens_cleaned` per cleanup cycle.
- **Data retention throughput**: `wishlists_purged` per cleanup cycle.
- **Failure rate**: `background_cleanup_failed` occurrences relative to completed cycles.

### System Health Metrics

- **Worker status**: tracked via `background_worker_started` and `background_worker_stopped`.
- **Component health**: worker catches operational errors without crashing loop or app lifespan.

## Monitoring Integration

- [x] Structured JSON logs via `JsonFormatter` compatible with vector/fluentbit/Loki/ELK.
- [x] Standard syslog levels (`INFO`, `ERROR`).
- [ ] Prometheus metrics exporter (planned follow-up).
- [ ] Grafana alert on consecutive `background_cleanup_failed` events.

## Validation Results

Validation via automated test suite `tests/test_token_cleanup_observability.py`:
- [x] Logs are correctly formatted: verified with `JsonFormatter` and schema assertions.
- [x] Metrics and attributes are collected correctly (`duration_ms`, `interval_seconds`, `count`).
- [x] Logging works in error scenarios (`background_cleanup_failed` with exception context).
- [x] Large data structures are not logged (only count integers and elapsed milliseconds).
- [x] Zero-leakage verification: raw capability tokens are never leaked to logs or extras.

## Notes

- Background cleanup logs use `wishenka.wishlists.cleanup` logger.
- Repository mutations use `wishenka.wishlists.repository` logger.
- Web lifespan properly manages worker lifecycle and emits start/stop observability events.
