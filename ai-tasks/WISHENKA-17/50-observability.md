# WISHENKA-17: Observability Implementation

## Logging Implementation

### Added Logs

Describe added logging:
- **EMERG**: None (in-process domain service; system emergencies handled at supervisor level)
- **ALERT**: None (alert conditions handled via metrics alerting)
- **CRIT**: None (critical service degradation handled at process infrastructure)
- **ERR**: None (unhandled runtime exceptions propagate to FastAPI exception handlers)
- **WARNING**:
  - `wishenka/wishlists/service.py:create_reservation` — `self_reservation_blocked`: recipient attempt to reserve own item blocked per Surprise Invariant
  - `wishenka/wishlists/service.py:create_reservation` — `insufficient_quantity_blocked`: reservation requested quantity exceeds available unreserved balance
  - `wishenka/wishlists/service.py:update_reservation_quantity` — `insufficient_quantity_blocked`: reservation quantity increase delta exceeds available inventory
  - `wishenka/wishlists/service.py:create_reservation` — `item_not_found`, `reservation_blocked_archived`, `reservation_blocked_deleted`, `reservation_blocked_archived_item`: reservation attempts on nonexistent or archived items/wishlists
  - `wishenka/wishlists/service.py:mark_reservation_purchased` — `reservation_not_found`, `access_denied`, `invalid_reservation_transition`: invalid purchase transition attempts or unauthenticated ownership
  - `wishenka/wishlists/service.py:revert_reservation_to_active` — `reservation_not_found`, `access_denied`, `invalid_reservation_transition`: invalid revert transition attempts
  - `wishenka/wishlists/service.py:cancel_reservation` — `reservation_not_found`, `access_denied`, `reservation_already_cancelled`: invalid cancellation attempts
  - `wishenka/wishlists/service.py:update_reservation_quantity` — `reservation_not_found`, `access_denied`, `reservation_update_blocked`: quantity adjustment errors
  - `wishenka/wishlists/service.py:record_item_fulfillment` — `item_not_found`, `access_denied`, `fulfillment_quantity_exceeded`: gift fulfillment violations
- **NOTICE**: None
- **INFO**:
  - `wishenka/wishlists/service.py:create_reservation` — `item_reserved`: gifter successfully reserved units of a wish item
  - `wishenka/wishlists/service.py:mark_reservation_purchased` — `reservation_purchased`: gifter marked reservation as purchased
  - `wishenka/wishlists/service.py:revert_reservation_to_active` — `reservation_reverted`: gifter reverted purchased reservation back to active status
  - `wishenka/wishlists/service.py:cancel_reservation` — `reservation_cancelled`: gifter cancelled reservation, restocking available inventory
  - `wishenka/wishlists/service.py:update_reservation_quantity` — `reservation_quantity_updated`: gifter adjusted reserved quantity
  - `wishenka/wishlists/service.py:record_item_fulfillment` — `item_fulfilled`: wishlist author recorded gift receipt and item fulfillment
- **DEBUG**:
  - `wishenka/wishlists/service.py:get_wishlist_view` — `wishlist_view_projected`: role-aware projection constructed without sensitive leaks

### Log Structure

Log format used:
- Structured logs: yes (all events use `extra={"event": "<event_name>", ...}` with syslog-compatible JSON formatter)
- Includes context: yes (`event`, `wishlist_id`, `item_id`, `user_id`, `reservation_id`, `quantity`, `delta`, `available_quantity`)
- Log levels: DEBUG, INFO, WARNING

#### Structured Event Schema:

| Event Name | Level | Core Context Fields | Description |
| --- | --- | --- | --- |
| `item_reserved` | INFO | `event`, `wishlist_id`, `item_id`, `user_id`, `reservation_id`, `quantity` | Emitted when a gifter successfully reserves item units |
| `reservation_purchased` | INFO | `event`, `wishlist_id`, `item_id`, `user_id`, `reservation_id`, `quantity` | Emitted when a gifter transitions reservation to `PURCHASED` |
| `reservation_reverted` | INFO | `event`, `wishlist_id`, `item_id`, `user_id`, `reservation_id`, `quantity` | Emitted when a reservation is reverted from `PURCHASED` to `ACTIVE` |
| `reservation_cancelled` | INFO | `event`, `wishlist_id`, `item_id`, `user_id`, `reservation_id`, `quantity` | Emitted when a reservation is cancelled and restocked |
| `reservation_quantity_updated` | INFO | `event`, `wishlist_id`, `item_id`, `user_id`, `reservation_id`, `quantity`, `old_quantity` | Emitted when a reservation's quantity is increased or decreased |
| `item_fulfilled` | INFO | `event`, `wishlist_id`, `item_id`, `user_id`, `quantity`, `received_quantity`, `total_quantity` | Emitted when a recipient/author records received quantity |
| `self_reservation_blocked` | WARNING | `event`, `wishlist_id`, `item_id`, `user_id`, `recipient_user_id` | Emitted when recipient attempts self-reservation (Surprise Invariant) |
| `insufficient_quantity_blocked` | WARNING | `event`, `wishlist_id`, `item_id`, `user_id`, `requested_quantity`, `available_quantity` | Emitted when create or update reservation exceeds unallocated quantity |

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: tracked at HTTP/ASGI middleware level (`http_request_duration_seconds`)
- **Throughput**: tracked at ASGI middleware level (`http_requests_total`)
- **Error rate**: tracked via HTTP 4xx/5xx status codes and logged WARNING/ERROR count

### Business Metrics

Business metrics:
- `wishlist_reservations_created_total`: total number of reservations created (`event="item_reserved"`)
- `wishlist_reservations_purchased_total`: total reservations transitioned to purchased (`event="reservation_purchased"`)
- `wishlist_reservations_cancelled_total`: total reservations cancelled (`event="reservation_cancelled"`)
- `wishlist_items_fulfilled_total`: total items marked received/fulfilled (`event="item_fulfilled"`)
- `wishlist_self_reservations_blocked_total`: count of prevented recipient self-reservations (`event="self_reservation_blocked"`)

### System Health Metrics

System health metrics:
- **Resource usage**: memory, CPU, and event-loop lag monitored via Uvicorn process metrics
- **Component status**: SQLite WAL connection pool and `ItemConcurrencyCoordinator` active locks

## Monitoring Integration

Integration with monitoring systems:
- [x] Standard structured logging with syslog/JSON compatibility
- [x] Contextual attributes on all reservation events
- [ ] Prometheus metrics (exportable via log metric aggregators or future telemetry exporter)
- [ ] Grafana dashboards (querying Loki / ELK aggregated log stream)
- [ ] Alerting rules (alerting on sustained `insufficient_quantity_blocked` or unexpected 5xx rates)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (standardized `wishenka.wishlists` logger with `extra` dict payload)
- [x] Metrics / structured events are collected correctly (validated in `tests/test_reservation_observability.py`)
- [x] Logging works in error scenarios (`self_reservation_blocked`, `insufficient_quantity_blocked`, access violations)
- [x] Large data structures are not logged (only scalar entity identifiers, delta values, and numeric quantities logged)
- [x] Zero surprise leaks in recipient audit trails: recipient queries and views produce zero logs revealing gifter identities or reservation status

## Notes

### Zero Surprise Leaks Guarantee
In compliance with the Surprise Invariant:
1. Recipient views (`WishItemRecipientViewDTO`) do not contain `available_quantity`, `is_fully_reserved`, `reservations`, or gifter identity fields.
2. In audit and diagnostics logs, log records emitted during recipient interactions (viewing wishlist detail, checking personal reservations cabinet) never contain gifter Telegram IDs, reservation IDs, or gifter names.
3. Automated test `test_zero_surprise_leaks_in_recipient_audit_trails` rigorously asserts that zero reservation or gifter attributes are attached to or emitted within recipient session logs.
