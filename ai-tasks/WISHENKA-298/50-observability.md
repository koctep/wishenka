# WISHENKA-298: Observability Implementation

## Logging Implementation

### Added Logs

This step adds no log. The anonymous share already records a missing
caller, and that record does not include the secret token.

`view_public_share` in `wishenka/web/routes/sharing.py` emits
`wishlist_shared_view` at `INFO` on `wishenka.web.sharing`. The message
is `Wishlist shared view accessed: wishlist_id=%s is_recipient=%s
is_collab=%s`. Structured fields are `event`, `wishlist_id`,
`is_recipient`, and `is_collaborative`. A missing caller makes
`is_recipient` false, because the flag is set only when `current_user`
exists. `public_token` is not a field and is not interpolated into the
message.

`get_wishlist_by_public_token` in `wishenka/wishlists/repo_ops.py` emits
`public_wishlist_resolved` at `INFO` on `wishenka.wishlists`. When the
caller is missing and the projected items are giver DTOs,
`projection_mode` is `anonymous_gifter`. An empty active list with no
role uses the same mode. Structured fields stay `event`, `wishlist_id`,
`identified`, `user_id`, `projection_mode`, and `items_count`. The
secret token is not among them. `identified` is false and `user_id` is
null for that caller.

`record_share_view_if_authenticated` returns without writing a visit
when the caller is missing. A failed public lookup still logs
`wishlist_shared_view_failed` or `public_token_not_found` without the
token value. Those paths are unchanged.

The records do not include wish titles, descriptions, reservation rows,
or member lists.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none
- **WARNING**: none added. A missing or deleted public token still logs
  without the token value.
- **NOTICE**: none
- **INFO**: none added. Existing `wishlist_shared_view` records
  `is_recipient` false for a missing caller. Existing
  `public_wishlist_resolved` records `projection_mode`
  `anonymous_gifter` for that same giver projection.
- **DEBUG**: none

### Log Structure

Log format used:

- Structured logs: yes. Both events already use `extra={"event": ...}`.
- Includes context: yes. Share view: `wishlist_id`, `is_recipient`,
  `is_collaborative`. Resolve: `wishlist_id`, `identified`, `user_id`,
  `projection_mode`, `items_count`. The secret token is absent from
  both.
- Log levels: `INFO` for the two existing success events. `WARNING`
  for a failed public lookup is unchanged.

## Metrics Implementation (if applicable)

No new metric and no new collector.

### Performance Metrics

None added. HTTP request logging still records `duration_ms` in
`wishenka/web/app.py`. This step does not change that middleware.

### Business Metrics

None added. An anonymous giver share is already countable as
`wishlist_shared_view` with `is_recipient` false, and as
`public_wishlist_resolved` with `projection_mode` `anonymous_gifter`.

### System Health Metrics

None added.

## Monitoring Integration

This step adds no integration:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

## Validation Results

No product code was edited. The existing emitters and
`tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability`
already require one `wishlist_shared_view` record per visit, `is_recipient`
false for a guest, and the secret token absent from the captured text.
Step 4 re-ran that check: 2 passed, 1 warning in 0.85s (exit 0). This
step did not re-run it and did not add a log to validate.

- [x] Logs are correctly formatted
- [ ] Metrics are collected correctly
- [ ] Logging works in error scenarios
- [x] Large data structures are not logged
- [ ] Metrics are available for monitoring

The metric boxes stay open because this step adds no metric.

## Notes

The secret token stays out of the share-view log and out of the resolve
log. This step does not add a field, a message argument, or a metric
that would carry it.
