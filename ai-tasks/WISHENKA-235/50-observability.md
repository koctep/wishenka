# WISHENKA-235: Observability Implementation

## Logging Implementation

### Added Logs

No new event. `public_wishlist_resolved` already records a public-token
resolve. Its `projection_mode` value for a missing caller was
`anonymous_safe`. That name meant the silent recipient view. A missing
caller now receives the giver projection, so that value lied about the
view. The same event now reports the view that was served.

`RepoWishlistOps.get_wishlist_by_public_token` in
`wishenka/wishlists/repo_ops.py` still emits one `INFO` record on
`wishenka.wishlists` after `project_wishlist_view`. The message is
`Public wishlist resolved: wishlist_id=%s identified=%s projection_mode=%s`.
Structured fields stay `event`, `wishlist_id`, `identified`, `user_id`,
`projection_mode`, and `items_count`.

`projection_mode` for a missing caller:

- `anonymous_gifter` when the served view is the giver projection. That
  is every active item as `WishItemGifterViewDTO`, and also an empty
  active list (`user_role` is unset for a missing caller).
- `anonymous_safe` only when a missing caller is served no giver view.
  Current `project_wish_item` does not take that branch: a missing id
  is not a recipient, so the giver view is what an anonymous share logs.

An identified caller is unchanged: `gifter` or `recipient_safe`.
`identified` stays false and `user_id` stays null for a missing caller,
so the anonymous share is distinct from an identified giver
(`projection_mode=gifter`, `identified=true`).

`view_public_share` in `wishenka/web/routes/sharing.py` already logs
`wishlist_shared_view` with `is_recipient=false` for a missing caller.
That flag does not claim the silent recipient card, so it was left as
it is. It does not carry `projection_mode`.

The record does not include wish titles, descriptions, reservation
rows, or member lists.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none added
- **WARNING**: none added. A missing public token still logs
  `public_token_not_found` without the token.
- **NOTICE**: none
- **INFO**: `public_wishlist_resolved` in
  `wishenka/wishlists/repo_ops.py`. A missing caller on the giver
  projection logs `projection_mode=anonymous_gifter`.
- **DEBUG**: none

### Log Structure

Log format used:

- Structured logs: yes (`extra={"event": "public_wishlist_resolved", ...}`
  on `wishenka.wishlists`)
- Includes context: yes (`wishlist_id`, `identified`, `user_id`,
  `projection_mode`, `items_count`)
- Log levels: `INFO` for the resolve. `WARNING` for a missing token is
  unchanged.

## Metrics Implementation (if applicable)

No new metric and no new collector.

### Performance Metrics

None added. HTTP request logging still records `duration_ms` in
`wishenka/web/app.py`. This task does not change that middleware.

### Business Metrics

The existing `public_wishlist_resolved` dimension changes for the
anonymous share. Count `projection_mode=anonymous_gifter` for an
anonymous share that used the giver projection. `anonymous_safe` is no
longer the value for that path. `recipient_safe` and `gifter` are
unchanged for identified callers.

### System Health Metrics

None added.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No integration is added. The resolve event remains a structured log on
`wishenka.wishlists`.

## Validation Results

Validation results:

- [x] Logs are correctly formatted — same `INFO` message and `extra`
  keys; only the anonymous giver value changed
- [x] Metrics are collected correctly — no new metric; the mode string
  is the dimension
- [x] Logging works in error scenarios — the same test still records
  one `WARNING` `public_token_not_found` and does not log the token
- [x] Large data structures are not logged — fields stay ids, a
  boolean, a count, and the mode string
- [x] Metrics are available for monitoring — `caplog` on
  `test_public_projection_observability_logs_without_leaking_tokens`
  in `tests/test_wishenka_63_repro.py` expects `anonymous_gifter`,
  then `recipient_safe`, then `gifter`. That test passed.

## Notes

`anonymous_safe` described the silent recipient view from WISHENKA-63.
Leaving it on the giver projection would tell an operator the wrong
card was served. Renaming that one value is the whole observability
change. Share and invite tokens stay out of the message and `extra`,
as the same test checks.
