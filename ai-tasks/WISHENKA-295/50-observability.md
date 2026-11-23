# WISHENKA-295: Observability Implementation

## Scope and Decision

Logs only (no metrics backend exists for this area; D-7). Gap review of each path of
`DELETE /api/wishlists/{id}` found one real gap: a non-owner attempt was logged only by
`execute()` as `wishlist_permission_denied` with `operation` and no ids, so an attack or client bug
could not be traced to a user and list. One WARNING event was added; everything else was already
in place from Step 4 and is now pinned by tests.

## Logging Implementation

### Added Logs

- **WARNING** `wishlist_delete_denied` (`wishenka/web/routes/wishlists.py`, `delete_wishlist`,
  before `PermissionDeniedError`): fields `wishlist_id`, `user_id`. Server-side only; the response
  is still the uniform 404 identical to an unknown id.

### Existing logs pinned per path

| Path | Status | Events (level) |
| ---- | ------ | -------------- |
| Success | 200 | `wishlist_status_changed` (INFO, from/to, `actor_id`), `wishlist_mutation_committed` (INFO, `operation`), `wishlist_deleted_by_owner` (INFO, `outcome=deleted`, `retention_days`) |
| Repeat in window | 200 | `wishlist_deleted_by_owner` (`outcome=already_deleted`), no second status change |
| Unknown id | 404 | `wishlist_delete_not_found` (WARNING, `wishlist_id`, `user_id`) |
| Non-owner | 404 | `wishlist_delete_denied` (new) and `wishlist_permission_denied` (WARNING) |
| Archived | 409 | `wishlist_archived_mutation_blocked` (WARNING, `operation`) |
| Expired window | 410 | `wishlist_retention_expired` (WARNING, `operation`) |
| Unexpected error | 500 | request middleware `unhandled exception` (ERROR, `method`, `path`, `duration_ms`; the test asserts level and `path`) |

All requests also get the request-completed INFO line (method, path with id, status, duration).

### Log Structure

- Structured logs: yes (`extra` fields rendered by `JsonFormatter`).
- Context: event, `wishlist_id`, `user_id` / `actor_id` (existing convention), enums and counts.
- Never logged: title, item titles, share/invite tokens, reservation counts/states/persons, gifter.

## Metrics Implementation

None. No metrics module exists for wishlists; counts are derivable from events
(`outcome` makes repeats countable).

## Monitoring Integration

- [ ] Prometheus / Grafana / alerting rules (not applicable)
- [x] Log aggregation: existing JSON logs; suggested alerts on a burst of
  `wishlist_delete_denied` per `user_id` and on 5xx of `DELETE /api/wishlists/{id}`.

## Validation Results

- [x] `tests/test_wishlist_delete_observability.py` (8 tests, timeout 30): events, levels, fields
  per path; non-owner vs unknown id responses byte-identical; no title, item title, tokens,
  gifter name or id in any record message, extra or JSON line
- [x] Logging works in error scenarios (403-class, 409, 410, 500 covered)
- [x] `make analyze` clean; 103 tests green across the four delete modules

## Notes

Deliberately not added: ids on the 409/410 `execute()` logs (the request log path carries the
id; changing the shared `execute()` fields affects all operations); a client-side telemetry; a
log for CSRF/auth failures (existing middleware). The new denied log reveals list existence only
in server logs.

### Deviation from the D-7 table

`wishlist_delete_denied` is an addition: the D-7 table in `20-architecture.md` lists only the
existing `wishlist_permission_denied` (`operation` only, no ids) for non-owners. That event cannot
say who tried to delete which list, so a server-only WARNING with `wishlist_id` and `user_id` was
added. It does not change the response, which stays the uniform 404.

### Step 8 follow-up (dev docs)

Add `wishlist_delete_denied`, `wishlist_delete_not_found` and `wishlist_deleted_by_owner` to the
event table in `doc/dev/wishlists.md` (~lines 1470-1514; see `20-architecture.md` lines 373-376).

### Validation notes

- "Logs are correctly formatted": ticked; the tests format every captured record with
  `JsonFormatter`, parse it as JSON and read the `extra` fields.
- "Large data structures are not logged": ticked; all delete events carry only ids, counts and
  enums, and the leak scan covers every captured record.
