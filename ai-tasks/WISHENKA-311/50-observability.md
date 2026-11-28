# WISHENKA-311: Observability Implementation

## Logging Implementation

### Added Logs

This step adds no log. The change is test-only. Product code was not
edited. The busy quick-add check and the viewing-history check already
exercise requests the server already records. No server log was added.
Secrets are not logged.

The quick-add request is `POST /web/wishlists/{wishlist_id}/items/quick`.
After the check releases the held send, these records already exist:

- **INFO** `wishenka.web` (`RequestLoggingMiddleware` in
  `wishenka/web/app.py`): `HTTP request completed` with `method`, a
  sanitized `path`, `status_code`, and `duration_ms`. The path drops the
  query string. Share and invite tokens are replaced before the line is
  written.
- **INFO** `wishenka.web.items_ui` (`quick_add_item` in
  `wishenka/web/routes/items_ui.py`): event `ui_item_quick_add_success`.
  Fields: `wishlist_id`, `item_id`, `actor_id`, `user_id`, `has_link`,
  `price`, `quantity`.
- **INFO** `wishenka.wishlists` (`add_wish_item` in
  `wishenka/wishlists/repo_ops.py`): event `item_created`. Fields:
  `item_id`, `wishlist_id`, `actor_id`, `recipient_user_id`, `quantity`,
  `display_order`, `has_recipient`.

The history read is `GET /api/history`. These records already exist:

- **INFO** `wishenka.web`: the same `HTTP request completed` line, with
  method, sanitized path, status, and duration.
- **INFO** `wishenka.wishlists` (`get_history` in
  `wishenka/wishlists/repo_ops.py`): event `view_history_listed`. Fields:
  `user_id` and `count`. The route handler in
  `wishenka/web/routes/wishlists.py` does not add a second event.
  `execute()` does not treat `get_history` as a mutation, so it does not
  write `wishlist_mutation_committed` for this read.

A failed read still uses the existing error path. A database error inside
`execute()` logs **ERR** `wishlist_store_error` on `wishenka.web.wishlists`.
An unhandled exception logs **ERR** `HTTP request unhandled exception` on
`wishenka.web`, with method, sanitized path, and duration. This step does
not add an error log.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none added
- **WARNING**: none added
- **NOTICE**: none
- **INFO**: none added
- **DEBUG**: none added. `HTTP request started` on `wishenka.web` is
  already DEBUG and stays below the default INFO level.

### Log Structure

Log format used:

- Structured logs: yes on the existing records (`extra` on the loggers
  above, JSON when `json_logs` is on). This step adds no log.
- Includes context: yes on the existing records (event name, ids, count,
  status, duration). This step adds no log.
- Log levels: INFO for the quick-add success, the item create, the
  history list, and the HTTP completion. ERR for the storage and
  unhandled-request failures named above. No level was added.

The wish title, raw input, link, image, description, and list title stay
out of these records. Session cookies, CSRF values, and capability tokens
stay out. `record_shared_event` stores a notification token in the
database and does not write that token to the log.

## Metrics Implementation (if applicable)

This step adds no metric. The parallel proof stays the primed two-worker
run from Step 4. The 600-second full suite stays WISHENKA-285.

### Performance Metrics

This step adds none.

- **Response time**: none. The existing HTTP completion line already
  carries `duration_ms` for the quick-add request and the history read.
- **Throughput**: none
- **Error rate**: none

### Business Metrics

This step adds none.

The existing `view_history_listed` count and the quick-add success event
already mark one completed read and one completed add.

### System Health Metrics

This step adds none.

- **Resource usage**: none
- **Component status**: none

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No integration is added. This step adds no log and no metric.

## Validation Results

Validation results:

- [x] Logs are correctly formatted — this step adds no log. The records
  above already use the application formatter.
- [x] Metrics are collected correctly — this step adds none
- [x] Logging works in error scenarios — no new error path. Storage and
  unhandled-request failures already log as named above.
- [x] Large data structures are not logged — this step adds no log. The
  history response body and the wish text are not written.
- [x] Metrics are available for monitoring — this step adds none

The suite was not re-run. Product code was not edited.

## Notes

The busy-form check holds the quick-add send until it releases it. The
completion line and `ui_item_quick_add_success` appear after that release.
The history check reads `GET /api/history` and retries one failed read
inside its poll. Each read that reaches `get_history` already logs
`view_history_listed`.

WISHENKA-357 and WISHENKA-285 are not fixed here. `wishenka/` was not
edited. STEP 6 stays `[/]` for the acceptance gate.
