# WISHENKA-291: Observability Implementation

## Scope and Decision

The task presents existing profile settings more clearly and calls existing endpoints. It adds no
server operation, worker or endpoint, so no production logging or metric code was added. A gap
review of every API path the page uses found each successful mutation already logged, so adding
route-level logs would only duplicate events (a first attempt produced duplicate
`notification_*_updated` records and was reverted). Only a contract test was added.

## Logging Implementation

### Existing logs relied on

- **INFO** `wishenka/users/store.py`: `locale_explicit_updated` (previous/new locale and source),
  `birthdate_explicit_updated` (`has_year` only), `birthdate_explicit_cleared`.
- **INFO** `wishenka/notices/preferences.py`: `notification_global_updated` (category names,
  counts) and `notification_wishlist_updated` (`wishlist_id`, role, updated and cleared counts).
- **WARNING** `wishenka/web/routes/profile.py`: `locale_invalid_request`,
  `birthdate_invalid_request`, `birthdate_user_not_found`, `notification_global_invalid_request`,
  `notification_wishlist_invalid_request`, `notification_wishlist_not_found`,
  `account_deletion_rejected`, plus malformed JSON body warnings.
- **DEBUG** `wishenka/wishlists/deletion.py`: `account_deletion_preview_computed`.
- **INFO/ERR** `wishenka/wishlists/deletion.py`: `account_deleted`, `account_deletion_already_deleted`, `account_deletion_failed`.
- `wishenka/web/app.py` request logging (method, masked path, status, elapsed ms).

### Log Structure

- Structured logs: yes (`extra` fields rendered by `JsonFormatter`).
- Includes context: event name, internal `user_id`, `wishlist_id`, counts.
- Levels used: INFO, WARNING, ERROR. No birthdate values, list titles, tokens or other users'
  reservation data are logged.
- Client side: the browser shows save, error, retry and unknown-state feedback to the user. The
  project has no client telemetry convention, so none was added; client-only failures are not
  reported (requests that reach the server are covered by request logs).

## Metrics Implementation

None added. The project has no metrics exporter for these paths; request completion logs carry
status and duration. No new business or health metric is warranted for a presentation change.

## Monitoring Integration

- [ ] Prometheus metrics (not applicable)
- [ ] Grafana dashboards (not applicable)
- [ ] Alerting rules (not applicable)
- [ ] Log aggregation (existing infrastructure unchanged)

## Validation Results

- [x] Logs are correctly formatted (rendered through `JsonFormatter` in the new test)
- [x] Logging works in error scenarios (invalid locale, birthdate and notification payloads)
- [x] Large data structures and PII are not logged (no birth year, name, list title, bearer
  token or telegram id in the success events)
- [x] New contract tests: `tests/test_personal_settings_observability.py` (2 tests, 30 s timeout,
  `caplog` on `wishenka.users`, `wishenka.notices.preferences`, `wishenka.web.profile`):
  success events fire once per mutation in order; rejected requests emit WARNING and no
  success event.

## Notes

Run with `make test PYTEST_JOBS=2 PYTEST_ARGS='tests/test_personal_settings_observability.py -q'`.
`make analyze` passes (ruff, format, mypy).
