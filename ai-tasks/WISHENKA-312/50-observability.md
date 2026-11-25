# WISHENKA-312: Observability Implementation

## Scope and Decision

No new signal is required. One deliberate confirmation already sends one
`POST /api/wishlists` and commits one list. Steps 1–5 changed no production
code, and this step does not either. Existing creation logs stay as they are.

An operator sees one completed create handler as the INFO event
`wishlist_mutation_committed` with `operation=create_wishlist`. `execute()` in
`wishenka/web/routes/wishlists.py` (logger `wishenka.web.wishlists`) writes it
after the handler returns a result and before
`get_wishlist_repository()` commits the connection. The event means the
handler finished without a storage exception. It does not by itself prove the
later commit succeeded. A commit failure after that record is
`wishlist_store_error` from the repository dependency. A second request that
also finishes its handler records the event again.
Do not count `wishlist_created`: that event is written again on the same
success path (domain create, then the route handler).

## Logging Implementation

### Added Logs

None.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none added. A database exception inside the handler still logs
  `wishlist_store_error` from `execute()` and does not emit
  `wishlist_mutation_committed`. A commit failure after the handler returns
  logs `wishlist_store_error` from the repository dependency and can follow
  a `wishlist_mutation_committed` record.
- **WARNING**: none added. Permission, archive, and retention warnings on
  other wishlist mutations are unchanged and are not part of create.
- **NOTICE**: none
- **INFO**: none added. The operator signal already exists:
  `wishlist_mutation_committed` / `operation=create_wishlist`.
- **DEBUG**: none

Existing success records for one `POST /api/wishlists` (unchanged):

- `wishlist_mutation_committed` on `wishenka.web.wishlists`, with
  `operation=create_wishlist`. This records a finished handler, before the
  repository dependency commits.
- `wishlist_created` on `wishenka.web.wishlists` (route), with `wishlist_id`
  and `user_id`.
- `wishlist_created` on `wishenka.wishlists` (domain), with `wishlist_id`,
  `owner_id`, `format`, `time_type`, and `event_date`.

Opening the form, cancelling, or leaving sends no request, so nothing is
logged. A confirmation rejected before the handler (422) or without a session
(401) does not emit `wishlist_mutation_committed`. A later confirmation after
a visible failure is a new action and, if that handler finishes, emits the
same event once more. The commit is still the later dependency step.

### Log Structure

- Structured logs: yes for the existing records (`extra` on the Python
  loggers above). No new records.
- Includes context: yes on the existing records (`event`, `operation`,
  `wishlist_id`, `user_id` / `owner_id`).
- Log levels: INFO for the creation signals named above. No new levels.

Title, description, and tokens stay out of these records. The domain
`wishlist_created` extra still includes `event_date` when the owner set one.
That field was already there; this task does not change it.

## Metrics Implementation (if applicable)

### Performance Metrics

None. No new endpoint or query.

- **Response time**: none added
- **Throughput**: none added
- **Error rate**: none added

### Business Metrics

None. Finished create handlers are the count of `wishlist_mutation_committed`
with `operation=create_wishlist`. That count is not a count of commits.

### System Health Metrics

None. No new component.

- **Resource usage**: none added
- **Component status**: none added

## Monitoring Integration

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No new integration. The existing JSON logs already carry the event above.

## Validation Results

Checked by reading the current create path. No production file was edited, and
no logging test was added or re-run.

- [x] Logs are correctly formatted — existing `extra` events only; no new
  format
- [ ] Metrics are collected correctly — not applicable; no metrics added
- [x] Logging works in error scenarios — a database exception inside the
  handler does not emit `wishlist_mutation_committed`. A later commit failure
  can follow that event and is `wishlist_store_error` from the dependency.
- [x] Large data structures are not logged — no new logs; the existing
  creation records carry ids and short fields only
- [ ] Metrics are available for monitoring — not applicable

## Notes

A suppressed repeat of the same confirmation never leaves the browser, so it
cannot and should not produce a server log. Client telemetry for that
suppression would not tell an operator whether a list was stored. The server
event above records one finished create handler, not a completed commit.
