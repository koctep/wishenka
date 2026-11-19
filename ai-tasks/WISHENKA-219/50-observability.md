# WISHENKA-219: Observability Implementation

## Logging Implementation

### Added Logs

- **ERR**:
  - `wishenka/web/routes/reservations.py` (`complete_reservation`): `receipt_delivery_coordination_unavailable` when `wishlist_store` is missing on `app.state` (HTTP 503).
- **WARNING**:
  - `wishenka/web/routes/reservations.py` (`complete_reservation`): `reservation_complete_fence_blocked` and `reservation_complete_lock_busy` (with `error_class`, omitting `actor_id` per route privacy rules) when completion is deferred with HTTP 503.
  - `wishenka/wishlists/service.py` (`_transactional` / `complete_reservation`): `reservation_not_found`, `invalid_reservation_transition` (with `from_status`, `to_status`, `is_fully_received`), `reservation_complete_fence_blocked`, and `reservation_complete_lock_busy` (with `error_class`).
  - `wishenka/notices/fence.py` (`begin_attempt`, `finish_attempt`): `receipt_fence_busy` when a fence insert conflicts with an active fence; `receipt_fence_uncertain` when an attempt finishes with an uncertain outcome.
  - `wishenka/notices/operator.py` (`resolve`): `operator_notice_resolve_noop` when no matching `uncertain` row is found.
- **INFO**:
  - `wishenka/wishlists/service.py` (`complete_reservation`): `reservation_completed` with `wishlist_id`, `item_id`, `reservation_id`, `actor_id`.
  - `wishenka/wishlists/store.py` (`_persist_wish`): `receipt_notices_suppressed` on `wishenka.wishlists.notices` with `item_id`, `user_id`, `gift_skipped`, `reminder_skipped` when pending gift/reminder notices are skipped after promise completion.
  - `wishenka/notices/fence.py` (`defer_claim`, `resolve_attempt`): `receipt_claim_deferred` when an unsent claim is returned to `pending` without consuming an attempt; `receipt_fence_resolved` with `item_id`, `user_id`, `operator`, `resolved_rows` (without full `evidence` text).
  - `wishenka/notices/operator.py` (`resolve`): `operator_notice_resolved` with `queue`, `row_id`, `action`, `has_fence`, `operator`.
- **DEBUG**:
  - `wishenka/notices/fence.py` (`begin_attempt`, `finish_attempt`, `resolve_attempt`): `receipt_fence_stale_claim`, `receipt_fence_no_open_promise`, `receipt_fence_recorded`, `receipt_fence_cleared`, and `receipt_fence_resolve_noop`.
  - `wishenka/notices/worker.py` (`NoticeWorker.run_once`): restored `receipt_notice_skipped_ineligible` and `service_notice_skipped` (`reason=refresh_ineligible`), and added `receipt_notice_deferred` / `service_notice_deferred` (`reason=fence_active` or `reason=lock_busy`) on `wishenka.wishlists.notices` without polluting its `INFO+` summary stream.

### Log Structure

- Structured logs: yes (`extra={...}` fields formatted by `wishenka.logging.JsonFormatter` when `json_logs=True`)
- Includes context: yes (`event`, `item_id`, `reservation_id`, `queue`, `row_id`, `operator`, `error_class`, `reason`, etc.; omits sensitive payloads, `evidence` bodies, and route-level `actor_id`)
- Log levels: `ERR`, `WARNING`, `INFO`, `DEBUG`

## Metrics Implementation (if applicable)

### Performance Metrics

- **Response time**: Existing HTTP request duration middleware in `wishenka/web/app.py` covers `POST /api/wishlists/{wishlist_id}/items/{item_id}/reservations/{reservation_id}/complete`.
- **Throughput**: Existing `NoticeWorker` windowed counters (`_counts`, `_reminder_counts`) in `wishenka/notices/worker.py` emit `receipt_notice_window_summary` and `service_delivery_window_summary`.
- **Error rate**: Covered by `failed_terminal` and `uncertain` counters in `NoticeWorker` summaries and structured `WARNING`/`ERR` logs.

### Business Metrics

- `receipt_notices_suppressed`: `gift_skipped` and `reminder_skipped` counts logged on promise completion in `wishenka/wishlists/store.py`.
- `receipt_fence_resolved`: `resolved_rows` count logged on audited fence resolution in `wishenka/notices/fence.py`.

### System Health Metrics

- Not applicable (application uses structured logging and `NoticeWorker` windowed summary counters; no Prometheus/OS resource exporter in this repository).

## Monitoring Integration

- [ ] Prometheus metrics (not configured in repository)
- [ ] Grafana dashboards (not configured in repository)
- [ ] Alerting rules (not configured in repository)
- [x] Log aggregation (`wishenka.logging.JsonFormatter` structured JSON stdout logs)

## Validation Results

- [x] Logs are correctly formatted (verified via `caplog` in `tests/test_wishenka_219_observability.py` and `tests/test_receipt_observability.py`)
- [x] Metrics/counts are collected correctly (`gift_skipped`, `resolved_rows`, and `NoticeWorker` window summaries verified)
- [x] Logging works in error scenarios (invalid state, missing reservation, active fence, busy lock, noop operator resolve)
- [x] Large data structures are not logged (only bounded IDs, counts, `reason`, `error_class`, and short `operator` identifiers)
- [x] Static analysis & tests pass: `.venv/bin/ruff check wishenka tests`, `.venv/bin/ruff format --check wishenka tests`, `.venv/bin/mypy wishenka tests` (240 files), and `.venv/bin/pytest -n 0 tests/test_wishenka_219_*.py tests/test_receipt_observability.py` (45 passed).

## Notes

- Fence and lock logs in `wishenka/notices/fence.py` use `wishenka.notices.fence` rather than `wishenka.wishlists.notices` so that `INFO+` records on `wishenka.wishlists.notices` remain strictly bounded to windowed summaries as enforced by `tests/test_receipt_observability.py`.
- `ai-tasks/WISHENKA-219/00-roadmap.md` leaves Step 6 marked `[/]` for the orchestrator to mark `[x]` after review.
