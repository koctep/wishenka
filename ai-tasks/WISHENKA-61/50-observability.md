# WISHENKA-61: Observability Implementation

## Logging Implementation

### Added Logs

- **INFO:**
  - `WishlistStore.execute_wish_idempotent` in `wishenka/wishlists/store.py` emits
    `idempotency_replay_hit` on `wishenka.wishlists.store` after transaction commit when a stored
    idempotent response is replayed (`outcome.replayed == True`), reporting `item_id`, `operation`,
    and `response_status`. Initial (non-replayed) mutations continue to emit
    `wishlist_inventory_committed` once per committed mutation.
  - `WishlistStore.cleanup_expired_idempotency_records` in `wishenka/wishlists/store.py` emits
    `idempotency_records_purged` on `wishenka.wishlists.store` only when at least one expired row is
    deleted, reporting `purged_count`.
  - `run_cleanup_cycle` in `wishenka/wishlists/cleanup.py` includes
    `idempotency_records_cleaned` in the `background_cleanup_completed` structured log event on
    `wishenka.wishlists.cleanup`.
- **WARNING:**
  - `parse_idempotency_key` in `wishenka/web/idempotency.py` emits `idempotency_key_invalid` on
    `wishenka.web.idempotency` when a malformed `Idempotency-Key` header is rejected with HTTP 400,
    reporting `method`, `route_path` (FastAPI route template, never raw URL), and `key_length`.
  - `execute` in `wishenka/web/routes/reservations.py` emits `reservation_idempotency_conflict` on
    `wishenka.web.reservations` when `IdempotencyConflictError` triggers HTTP 409, reporting
    `reason="idempotency_conflict"`, `operation`, and `item_id` / `reservation_id`.
- **Existing logs preserved:**
  - `wishlist_inventory_rolled_back` (`WARNING` on `wishenka.wishlists.store`) with
    `error_type="IdempotencyConflictError"` on transaction rollback.
  - `receipt_idempotency_conflict` (`WARNING` on `wishenka.web.receipts`) on JSON receipt 409.
  - `receipt_refused` with `reason="idempotency_conflict"` (`WARNING` on
    `wishenka.web.routes.receipts_ui`) on HTMX receipt 409.
- No new EMERG, ALERT, CRIT, ERR, or NOTICE events were necessary.

### Log Structure

- Structured logs: yes (`extra={"event": ..., ...}`).
- Includes context: yes (`operation`, `item_id`/`reservation_id`, `response_status`, `route_path`,
  `key_length`, `purged_count`, `idempotency_records_cleaned`).
- Log levels: `INFO`, `WARNING`.
- Privacy invariants: raw `Idempotency-Key` values, `request_hash`, `response_body`, public invite
  tokens, wishlist/wish titles, `actor_id` (on reservation/store logs), and Surprise Invariant
  reservation details are never emitted in idempotency logs.

## Metrics Implementation

The process has no metrics exporter configured. The structured `idempotency_replay_hit`,
`idempotency_key_invalid`, `reservation_idempotency_conflict`, `receipt_idempotency_conflict`,
`idempotency_records_purged`, and `background_cleanup_completed` (`idempotency_records_cleaned`)
events provide replay, conflict, validation-error, and retention counters for log aggregation
without introducing a Prometheus or Grafana dependency.

## Monitoring Integration

- Prometheus metrics: not configured.
- Grafana dashboards and alert rules: not configured.
- Log aggregation: compatible with the existing structured application logging pipeline.

## Validation Results

- `tests/test_wishenka_61_observability.py` verifies:
  - `idempotency_replay_hit` is logged once on replay while `wishlist_inventory_committed` is not
    duplicated, with no raw key, token, `actor_id`, or wish title leaked.
  - Payload mismatch 409 emits `reservation_idempotency_conflict` /
    `receipt_idempotency_conflict` and `wishlist_inventory_rolled_back` without leaking raw keys.
  - Malformed `Idempotency-Key` headers emit `idempotency_key_invalid` with `key_length` and
    route template (`{token}`), never the raw key or raw public token.
  - `idempotency_records_purged` is emitted only when expired rows are deleted, and
    `background_cleanup_completed` reports `idempotency_records_cleaned`.
- `tests/test_wishenka_61_observability.py`, `tests/test_booking_idempotency.py`,
  `tests/test_booking_idempotency_extended.py`, and `tests/test_token_cleanup_observability.py` all
  pass (29 passed).
- `make analyze` (Ruff lint, Ruff format check, Mypy across 179 source files) passes with 0 errors.

## Notes

`idempotency_replay_hit` is emitted only after `self._immediate(work)` commits and
`_verify_idempotent_replay_access` succeeds, so failed access checks on replay never emit false
replay-hit events.
