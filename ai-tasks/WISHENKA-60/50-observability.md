# WISHENKA-60: Observability Implementation

## Logging Implementation

### Added Logs

- **INFO:** `NoticeStore.purge_finished` in `wishenka/notices/store.py` emits
  `notice_outbox_purged` on `wishenka.wishlists.notices` only when at least one terminal row is
  deleted, reporting `receipt_purged`, `reminder_purged`, and `total_purged` counts.
- **DEBUG:**
  - `WishlistStore` (`_log_flushed_shared_events` in `wishenka/wishlists/store.py`, backed by
    `EventProducer.record` in `wishenka/notices/events.py`) emits `shared_notice_events_queued` on
    `wishenka.wishlists.notices` after transaction commit when `reminder_outbox` rows are inserted,
    reporting `kind` and `queued_count`. Rolled-back transactions emit no queued event.
  - `claim_reminder` in `wishenka/notices/reminders.py` and `NoticeWorker.run_once` in
    `wishenka/notices/worker.py` emit `service_notice_skipped` on `wishenka.wishlists.notices`
    after transaction commit when a queued reminder/lifecycle notice is skipped (including
    recipient-exclusion authorization checks), reporting `outbox_id`, `reason` (`unauthorized`,
    `ineligible`, or `refresh_ineligible`), and `kind` (when claimed).
  - `NoticeStore.claim_next` in `wishenka/notices/store.py` and `NoticeWorker.run_once` in
    `wishenka/notices/worker.py` emit `receipt_notice_skipped_ineligible` on
    `wishenka.wishlists.notices` when a `notification_outbox` row is skipped as ineligible,
    reporting `outbox_id` and `attempt`.
- **Existing logs preserved:**
  - `receipt_notice_sent` (`DEBUG`) and `receipt_notice_window_summary` (`INFO`) continue to
    track delivered partial-receipt notices even when the remaining unreceived units of the wish
    are subsequently archived.
  - `service_delivery_window_summary` (`INFO`) continues to aggregate sent, retried,
    failed_terminal, uncertain, and skipped service deliveries.
- No new EMERG, ALERT, CRIT, ERR, WARNING, or NOTICE events were necessary.

### Log Structure

- Structured logs: yes (`extra={"event": ..., ...}` on `wishenka.wishlists.notices`).
- Includes context: yes (aggregate counts, event kind, skip reason, or opaque `outbox_id`).
- Log levels: `INFO`, `DEBUG`.
- Privacy invariants: no wishlist or wish titles, invite/public tokens, `user_id`, `chat_id`,
  `giver_user_id`, `wishlist_id`, `item_id`, `receipt_id`, or `event_type` join keys are emitted
  on `wishenka.wishlists.notices`.

## Metrics Implementation

The process has no metrics exporter configured. The structured `notice_outbox_purged`,
`receipt_notice_window_summary`, and `service_delivery_window_summary` counters provide throughput,
delivery, skip, and retention indicators for log aggregation without introducing a Prometheus or
Grafana dependency.

## Monitoring Integration

- Prometheus metrics: not configured.
- Grafana dashboards and alert rules: not configured.
- Log aggregation: compatible with the existing structured application logging pipeline.

## Validation Results

- `tests/test_wishenka_60_observability.py` verifies:
  - `shared_notice_events_queued` is logged after commit with `kind` and `queued_count`, and is
    suppressed on transaction rollback.
  - `notice_outbox_purged` logs `receipt_purged`, `reminder_purged`, and `total_purged` only when
    rows are deleted.
  - `service_notice_skipped` is logged when a giver becomes the wish recipient before delivery.
  - Partial-receipt delivery after wish archival logs `receipt_notice_sent` and
    `receipt_notice_window_summary` (`sent=1`) without leaking titles, tokens, or user IDs.
- `tests/test_wishenka_60_observability.py`, `tests/test_wishenka_60_repro.py`,
  `tests/test_service_notice_observability.py`, and `tests/test_receipt_observability.py` all pass
  (26 passed).
- `make analyze` (Ruff lint, Ruff format check, Mypy across 174 source files) passes with 0 errors.

## Notes

All new queue and event-emission logs are emitted only after the enclosing SQLite `BEGIN IMMEDIATE`
transaction commits so rolled-back operations never produce false operational signals.
