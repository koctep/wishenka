# WISHENKA-157: Observability Implementation

Hardening of gift-receipt and notice-delivery observability contracts, building on `ai-tasks/WISHENKA-23/50-observability.md` (item T3 from `ai-tasks/WISHENKA-23/60-tech-debt.md`).

## Logging Implementation

### Added and Hardened Logs

Loggers in scope: `wishenka.wishlists` (domain), `wishenka.web.receipts` (HTTP route), `wishenka.wishlists.notices` (operator-only notice producer, worker, and lifecycle). Every record sets `extra={"event": ...}` with no exception messages, tokens, or large data structures.

- **EMERG / ALERT / CRIT**: N/A — no system-level emergencies or critical alerts introduced in this task.
- **ERR**:
  - `wishenka/wishlists/store.py:WishlistStore._flush_receipt_effects` — `receipt_notice_enqueue_failed` (logger `wishenka.wishlists.notices`, message `"Receipt notice enqueue failed"`). Emitted before re-raising when inserting into `notice_receipt_keys` or `notification_outbox` fails inside a receipt transaction. Carries only `{"event": "receipt_notice_enqueue_failed", "error_class": type(exc).__name__}` — no `wishlist_id`, `item_id`, `receipt_id`, `giver_user_id`, or `outbox_id`, preserving NFR-2 (no reservation-presence leak).
- **WARNING**:
  - `wishenka/web/routes/receipts.py:_refusal` — `receipt_refused` (logger `wishenka.web.receipts`). Closed field set verified by exact key-set equality: `{"event", "operation", "wishlist_id", "item_id", "actor_id", "reason", "http_status"}` plus `"remaining_quantity"` iff `reason in {"quantity_above_remaining", "nothing_remaining"}`.
  - `wishenka/web/routes/receipts.py:_busy` — `receipt_inventory_busy` (logger `wishenka.web.receipts`). Closed field set verified by exact key-set equality: `{"event", "operation", "wishlist_id", "item_id", "actor_id"}`. Identical bounded 503 response and log payload regardless of whether active reservations exist (CC-13).
- **NOTICE**: N/A — Python `logging` does not define a separate `NOTICE` level; significant domain/lifecycle events use `INFO`.
- **INFO**:
  - `wishenka/wishlists/service.py:WishlistService.record_item_fulfillment` + `wishenka/wishlists/store.py` (`PendingCommitLog`, `flush_pending_commit_logs`) — `item_fulfilled` (logger `wishenka.wishlists`). Deferred via `_defer_commit_logs = True` in `WishlistStore` hydration and flushed only after `self._immediate(work)` commits in `execute_wish`, `execute_wish_idempotent`, and `_execute_once`. Rolled-back receipt transactions (including outbox enqueue failures) never emit `item_fulfilled`. Standalone `WishlistService.in_memory()` keeps `_defer_commit_logs = False` for isolated unit tests.
  - `wishenka/wishlists/service.py:WishlistService.archive_wish_item` — `item_archived` (logger `wishenka.wishlists`). Removed `active_reservations_count` from `extra`; emits only `{"event": "item_archived", "item_id", "wishlist_id", "actor_id"}` so owner-stream logs never expose reservation presence.
  - `wishenka/web/app.py:_stop_notice_worker` — `receipt_notice_worker_stopped` (logger `wishenka.wishlists.notices`). Emits `INFO` with `{"event": "receipt_notice_worker_stopped"}` and no summary counts (`receipt_notice_window_summary` is not emitted on stop).
- **DEBUG** (operator-only, per-row):
  - `wishenka/notices/worker.py:NoticeWorker._debug` — `receipt_notice_retry_scheduled` (logger `wishenka.wishlists.notices`). Now includes `"max_attempts": self._max_attempts` alongside `event`, `outbox_id`, `attempt`, and `error_class` (when `result` is present).

### Log Structure

- Structured logs: **yes** (`extra={"event": ...}` with fixed message strings for new/updated events).
- Includes context: **yes** — owner-stream events carry business IDs (`wishlist_id`, `item_id`, `actor_id`); operator-only notice events carry `outbox_id`, `attempt`, `max_attempts`, `error_class` (and `receipt_notice_enqueue_failed` carries only `error_class`).
- Log levels used: `ERROR`, `WARNING`, `INFO`, `DEBUG`.

## Metrics Implementation

No Prometheus/OpenTelemetry exporter is implemented in this task (tracked separately under `WISHENKA-84`). Metrics remain log-derived (from `INFO`+ events) and SQL-derived over `notification_outbox`, with hardened semantics:

### Performance Metrics

- **Response time**: Existing `RequestLoggingMiddleware` duration logs (unchanged).
- **Throughput**: `item_fulfilled` (`INFO`, post-commit only — no longer inflated by rolled-back transactions).
- **Error rate**: `receipt_refused` (`WARNING`), `receipt_inventory_busy` (`WARNING`), and `receipt_notice_enqueue_failed` (`ERROR`, operator-only).

### Business Metrics & SQL Gauge Semantics

- **`last_error_class` current-state gauge** (`wishenka/notices/store.py:NoticeStore._settle`, `NoticeStore.complete`):
  - `last_error_class` is cleared to `NULL` when a row transitions to `sent`.
  - Therefore `SELECT last_error_class, count(*) FROM notification_outbox WHERE status IN ('pending', 'uncertain', 'failed') GROUP BY last_error_class` is a **current-state gauge** of unresolved/failed rows, not a historical failure counter.
- **`ambiguous` gauge** (`wishenka/notices/store.py:NoticeStore._settle`, `wishenka/notices/operator.py:resolve`):
  - `ambiguous = 1` marks rows with an unconfirmed send outcome; `operator.resolve(..., action="retry")` clears `ambiguous = 0` when returning an `uncertain` row to `pending`, while `action="fail"` leaves `ambiguous = 1` on `failed`.
  - Active unresolved ambiguity must be queried with `WHERE status = 'uncertain'`; historical ambiguity within the 30-day retention window is queried with `WHERE ambiguous = 1 AND status IN ('sent', 'failed')`.

### System Health Metrics

- **Resource usage**: N/A (not added in this task).
- **Component status**: `receipt_notice_worker_started` / `receipt_notice_worker_stopped` / `receipt_notice_worker_disabled` (`INFO`, `wishenka.wishlists.notices`), plus `receipt_notice_worker_error` (`ERROR`, once per failure streak).

## Monitoring Integration

- [ ] Prometheus metrics — N/A (deferred to `WISHENKA-84`)
- [ ] Grafana dashboards — N/A
- [ ] Alerting rules — N/A (no rule engine in repository)
- [x] Log aggregation — structured `extra={"event": ...}` records emitted to standard Python loggers (`JsonFormatter` / text formatter in `wishenka/logging.py`)

## Validation Results

Targeted `pytest` run: `.venv/bin/pytest tests/test_receipt_observability.py tests/test_receipt_concurrency.py tests/test_receipt_notices_extra.py tests/test_wish_items_crud_api.py -q` — **41 passed, 1 failed** (pre-existing baseline failure `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`, tracked separately under `WISHENKA-245`):

- [x] Logs are correctly formatted: `tests/test_receipt_observability.py` (12/12 passed), including exact key-set equality for `receipt_refused` and `receipt_inventory_busy`, `max_attempts` on `receipt_notice_retry_scheduled`, `item_archived` without `active_reservations_count`, and `receipt_notice_worker_stopped` at `INFO` without `receipt_notice_window_summary`.
- [x] Metrics are collected correctly: N/A for exporter (`WISHENKA-84`); SQL gauge semantics for `last_error_class` and `ambiguous` documented above.
- [x] Logging works in error scenarios: `test_enqueue_failure_rolls_back_without_item_fulfilled_and_logs_operator_error` verified `receipt_notice_enqueue_failed` (`ERROR`, `wishenka.wishlists.notices`, `error_class` only) without `item_fulfilled` on rollback; `test_run_loop_logs_one_error_per_failure_streak` verified deterministic `receipt_notice_worker_error` logging; `test_cc13_busy_503_bounded_and_identical_with_or_without_reservations` verified bounded 503 and identical `receipt_inventory_busy` logs with 0 vs. active reservations.
- [x] Large data structures are not logged: verified by closed-field exact key-set assertions (`_extras(record)`) and token/name absence checks.
- [x] Metrics are available for monitoring: log-derived counts and read-only SQL queries over `notification_outbox` are documented and consistent.
