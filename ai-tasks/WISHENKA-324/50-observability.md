# WISHENKA-324: Observability Implementation

Gift-receipt looks now take the wishlist repository as an argument. The
hidden slot and the empty-slot `get_wishlist_repository` opening are gone.
A finished look is the common case. This step does not log or count it.
Busy and storage failures keep the records they already write on the save
and on the read transaction. No production logger or metric was added.

## Logging Implementation

### Added Logs

None.

- **EMERG**: none. This service does not use that level.
- **ALERT**: none. This service does not use that level.
- **CRIT**: none. This service does not use that level.
- **ERR**: none added. A storage failure on a save still logs
  `wishlist_store_error`. A storage failure on a read still reaches
  `RequestLoggingMiddleware`.
- **WARNING**: none added. A busy save still logs
  `wishlist_inventory_busy` and `receipt_inventory_busy`. A busy read
  still logs `wishlist_read_busy`.
- **NOTICE**: none. This service does not use that level.
- **INFO**: none added. Opening a dialog and a successful record,
  correction, or cancellation keep the events they already write. A
  gift-receipt look does not gain an event of its own.
- **DEBUG**: none added.

### Records that already cover these paths

#### Successful screens

Logger `wishenka.web.receipts_ui` in `wishenka/web/routes/receipts_ui.py`.

- `ui_receipt_form_opened` (`INFO`) when the receipt dialog opens.
- `ui_receipt_entry_form_opened` (`INFO`) when the correction or
  cancellation dialog opens. `extra` includes `receipt_id`.
- `receipt_recorded_http` (`INFO`) after a successful record.
- `receipt_corrected_http` and `receipt_cancelled_http` (`INFO`) after a
  successful correction or cancellation. `extra` includes `receipt_id`.

`extra` is `event`, `wishlist_id`, `item_id`, and `actor_id`, plus
`receipt_id` on the entry and mutation events. A true repeat returns the
stored answer and writes the same success event the first response wrote.
The keyed list is composed on the save and does not add a look event.

#### Domain refusals

Same logger.

- `ui_receipt_form_refused` (`WARNING`) when the receipt dialog is blocked.
- `ui_receipt_entry_form_refused` (`WARNING`) when the correction or
  cancellation dialog is blocked.
- `receipt_refused` (`WARNING`) when a record, correction, or cancellation
  is refused, including `idempotency_conflict`.

`extra` adds `reason` and `http_status`. `remaining_quantity` is included
only for `QuantityAboveRemainingError` and `NothingRemainingError`. The
quantity-refusal look does not write another line. If that look fails, the
refusal status and sentence stay the ones already logged.

#### Busy save

`wishlist_inventory_busy` (`WARNING`), logger `wishenka.wishlists.store`,
`_raise_for_storage_error` in `wishenka/wishlists/store.py`.

Message: `Wishlist inventory change rolled back because the database was busy`.

`execute_wish` and `execute_wish_idempotent` still call that mapper.
`record_receipt_ui` and `_execute_receipt_mutation_ui` still catch
`InventoryBusyError` and write `receipt_inventory_busy` (`WARNING`,
`Receipt busy`) on `wishenka.web.receipts_ui`. This task does not edit
those functions' busy mapping.

#### Busy read

`wishlist_read_busy` (`WARNING`), same store logger,
`WishlistStore.read_transaction`.

Message: `Wishlist read failed because the database was busy`.

`extra`: `event` only. The method raises `InventoryBusyError`.

Openings use `WishlistReadRepo`, which enters `read_transaction`. A busy
opening still becomes `ui_receipt_form_refused` or
`ui_receipt_entry_form_refused` with reason `busy`.

The quantity-refusal look and the list read after an unkeyed save use
`run_repository_read`, which enters the same context manager. A busy
refusal look is swallowed after that warning, so the refusal sentence
stays. A busy list read after an unkeyed save still reaches
`receipt_inventory_busy`.

A failed `query_only` reset still logs
`wishlist_read_query_only_reset_failed` (`WARNING`) with `event` and
`error_type`.

#### Storage errors

A non-busy `SQLAlchemyError` inside `execute_wish` or
`execute_wish_idempotent` still logs ERROR `wishlist_store_error`
(`Wishlist storage operation failed due to database error`) and raises
`RuntimeError`. That path was not edited.

A non-busy `SQLAlchemyError` inside `read_transaction` is re-raised. It is
not a `WishlistError`, so a receipt route does not turn it into a refusal.
`RequestLoggingMiddleware` logs the unhandled exception with the method
and path. Openings already failed that way. The list read after an unkeyed
save and the quantity-refusal look now fail that way too. The middleware
line is the record. This step does not add a receipt event for it.

### Log Structure

Log format used:

- Structured logs: unchanged (`extra={"event": ...}` on the existing
  loggers)
- Includes context: unchanged (ids and reason on receipt UI events;
  `event` on a busy read or a busy save; `event` and `error_type` on a
  `query_only` reset failure)
- Log levels: none added

No wishlist body, wish list, gifted rows, or SQL text is written for
these screens.

## Metrics Implementation (if applicable)

No new metric. A gift-receipt look is not counted. This repository has no
Prometheus or OpenTelemetry series for these screens, and this step does
not add one.

### Performance Metrics

None.

### Business Metrics

None.

### System Health Metrics

None.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation (existing structured `event` fields; none added)

## Validation Results

Checked by reading the receipt routes, `read_transaction`,
`run_repository_read`, and the save error mapper. No production code was
edited, and no new log line was exercised.

- [x] Logs are correctly formatted — no new log line
- [x] Metrics are collected correctly — no new metric
- [x] Logging works in error scenarios — a busy save still logs
  `wishlist_inventory_busy` and `receipt_inventory_busy`; a busy read
  still logs `wishlist_read_busy`; a storage error on a save still logs
  `wishlist_store_error`; a storage error on a read still reaches
  `RequestLoggingMiddleware`
- [x] Large data structures are not logged — no new log
- [x] Metrics are available for monitoring — no new metric

## Notes

Passing the repository in is not a new failure mode. Logging every
gift-receipt look would record ordinary dialog and list traffic. The
empty-slot opening was the hidden fallback, not a signal of its own. Busy
and storage failures stay on the transaction that already reports them.
