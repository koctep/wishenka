# WISHENKA-307: Observability Implementation

## Scope and Decision

The task reskins the on/off switches of the personal settings page. The diff touches only
`wishenka/web/static/miniapp.css` (switch skin), `wishenka/web/templates/settings.html`
(`role="switch"`, `aria-labelledby`, label ids, `aria-hidden` on the state text) and
`wishenka/web/static/settings.js` (`aria-busy` in `refreshDisabled`), plus the new browser test
`tests/test_settings_switch_browser.py`. No Python file changed. There is no new endpoint,
server operation, worker or data path, and the requests the page sends are unchanged.

Gap review result: no real gap. Decision: no production logging or metric code added, and no
new test (the existing contract test covers the logged paths).

## Logging Implementation

### Existing logs relied on

- **INFO** `wishenka/users/store.py`: `locale_explicit_updated` (line 348),
  `birthdate_explicit_updated` (line 402), `birthdate_explicit_cleared` (line 437).
- **INFO** `wishenka/notices/preferences.py`: `notification_global_updated` (line 210) and
  `notification_wishlist_updated` (line 333). The switches call the global one.
- **WARNING** `wishenka/web/routes/profile.py`: invalid request and not-found events for locale,
  birthdate, global and wishlist notification updates, and account deletion rejection.
- **INFO/WARNING** `wishenka/web/app.py` request logging (lines 84-117): method, path, status
  and `duration_ms` for every request, including the switch saves.

### Log Structure

- Structured logs: yes (`extra` fields rendered by `JsonFormatter`).
- Includes context: event name, internal `user_id`, category names, counts.
- Levels used: INFO, WARNING. No birthdate values, list titles, tokens or reservation data are
  logged; the surprise invariant is not affected.
- Added logs: none.

## Metrics Implementation

None added. The change is presentational and creates no new operation to measure. The project
has no metrics exporter for these paths; request logs carry status and duration.

## Monitoring Integration

- [ ] Prometheus metrics (not applicable)
- [ ] Grafana dashboards (not applicable)
- [ ] Alerting rules (not applicable)
- [ ] Log aggregation (existing infrastructure unchanged)

### Monitoring checklist after release

- Requests to the notification settings endpoint keep the same status mix and `duration_ms` as
  before; a rise in 4xx would point to a broken client payload, not to the skin.
- `notification_global_updated` still appears once per successful toggle save.
- `notification_global_invalid_request` WARNING rate stays at its baseline.

## Validation Results

- [x] Diff read: no server-side file changed, no request or payload change
- [x] Every API path of the page already logs successful mutations (references above)
- [x] Logging works in error scenarios (WARNING events pinned by the existing test)
- [x] Large data structures and PII are not logged (nothing new is logged)
- [x] `make test-serial PYTEST_ARGS="tests/test_personal_settings_observability.py -q"`:
  2 passed
- [ ] `make analyze` not run: no code was added in this step

## Notes

The switch states (on, off, busy, disabled, unknown) are UI-only. The project has no client
telemetry convention, so none was added; client-only failures are not reported, while requests
that reach the server are covered by request logs. Visual and accessibility behavior is
covered by `tests/test_settings_switch_browser.py`, not by production observability.
