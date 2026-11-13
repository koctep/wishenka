# WISHENKA-49: Observability Implementation

## Logging Implementation

### Existing Signals

No source change is needed: the existing reservation transaction boundary already
emits structured, privacy-preserving operational signals.

- **WARNING**: `wishenka.wishlists.store` emits `wishlist_inventory_busy` when
  SQLite cannot acquire the write transaction and rolls it back.
- **WARNING**: `wishenka.wishlists.store` emits
  `wishlist_inventory_rolled_back` for rejected or failed inventory changes.
- **INFO**: `wishenka.wishlists.store` emits
  `wishlist_inventory_committed` with the item, operation, and number of
  reservations written after a successful transaction.
- **WARNING**: `wishenka.web.reservations` emits `reservation_inventory_busy`
  before returning a retryable HTTP 503 response.
- **WARNING**: `wishenka.web.reservations` emits `reservation_conflict` for a
  quantity refusal before returning HTTP 409.
- **INFO**: request middleware records method, sanitized path, status, and
  duration in milliseconds for every completed HTTP request.

### Log Structure and Privacy

`wishenka.logging.JsonFormatter` can emit JSON lines with timestamp, level,
logger, message, and structured extras. Transaction and route events carry only
operation and resource identifiers required for diagnosis; they omit gifter
identity and wish graph payloads. `ShareTokenAccessFilter` removes public
capability tokens from access-log paths.

## Metrics Implementation

No metrics backend is configured in this project. The existing logs provide the
operational inputs for a future dashboard without creating an unmaintained
second telemetry path:

- Busy rate: count `wishlist_inventory_busy` or `reservation_inventory_busy`.
- Refusal rate: count `reservation_conflict` by operation.
- Transaction success volume: count `wishlist_inventory_committed`.
- HTTP latency and availability: aggregate request middleware `duration_ms` and
  `status_code` fields.

Prometheus, Grafana, alerting rules, and external log aggregation are outside
this task's scope. They can consume the existing structured fields when the
product selects a monitoring platform.

## Validation Results

- Existing event names, fields, and log levels were inspected in the store,
  reservation routes, application middleware, and JSON formatter.
- The event payloads avoid large data structures and protect recipient surprise
  data by omitting gifter identity and share tokens.
- Focused R5 verification passed in Step 5; its six tests exercise the
  transaction boundary that produces these signals.
- No logging or metrics source change was made because WISHENKA-49 has no
  missing runtime behavior to implement.

## Notes

An `InventoryBusyError` is an observable retryable availability outcome, while
an `InsufficientQuantityError` is an expected inventory conflict. Operators can
distinguish them by the respective event names without inspecting user data.
