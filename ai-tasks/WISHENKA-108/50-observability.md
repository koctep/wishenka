# WISHENKA-108: Observability Implementation

## Scope Decision

The task moved browser-side behaviour (card toggle and drag-and-drop reorder) from inline JS in
`base.html` into `wishenka/web/static/wishlist.js`, and moved the wishlist id into
`#items-list[data-wishlist-id]`. No server-side behaviour changed. Server logging and metrics for
the reorder endpoint already exist and were only reviewed. The one genuine diagnostics gap was
the client `console.warn` text, which was improved. Nothing else was added.

## Logging Implementation

### Added Logs

- **EMERG / ALERT / CRIT / ERR / NOTICE / INFO / DEBUG**: N/A. No new server logging. A static
  script has no log channel besides the browser console, and a toggle or drag handler is not worth
  logging in normal operation.
- **WARNING**: `wishenka/web/static/wishlist.js` (drop handler) - the single deliberate
  `console.warn`, emitted when a drop cannot be turned into a reorder request. This is the only
  code change in the step. Before: `wishlist.js: reorder skipped, missing wishlist id or htmx`
  (did not say which one). After, the message names each cause that applies:
  - `#items-list[data-wishlist-id] is not numeric (got "<value>")`
  - `window.htmx is not loaded (CDN blocked or script order)`
  
  joined by `; ` after the prefix `wishlist.js: reorder skipped: `. The message is actionable: it
  points at the template attribute or at the script load order. It carries no user data beyond
  the attribute value, which is a template-rendered id or an empty string.

### Existing server-side logs (reviewed, not changed)

`wishenka/web/routes/items_ui.py`, endpoint `POST /web/wishlists/{id}/items/reorder`:
- **INFO**: `ui_items_reordered` with `wishlist_id`, `actor_id`, `user_id`, `item_count`.
- **WARNING**: `ui_items_reorder_rejected` with `reason=invalid_permutation` (also returns 400).
- Move up/down (`POST /items/{item_id}/move`) shares only the rejection path: `_reordered_response`
  emits the same `ui_items_reorder_rejected` WARNING (reason=invalid_permutation, 400). On success it
  logs a different INFO event, `ui_item_moved` (wishlist_id, item_id, actor_id, user_id,
  direction; no item_count). `ui_items_reordered` is emitted only by `POST /items/reorder`.
- Missing or non-numeric `wishlist_id` never reaches the server: the client skips the request.
  The client warning above is the only trace of it.

### Log Structure

- Structured logs: server yes (`extra={"event": ...}`); client no (plain console text).
- Includes context: yes (server ids and counts; client cause and offending attribute value).
- Log levels: server INFO and WARNING; client `console.warn`.

## Metrics Implementation (if applicable)

N/A. The project has no metrics stack, and no behaviour changed that needs one.

### Performance Metrics

- **Response time / throughput / error rate**: N/A. Static file requests appear in the uvicorn
  access log (path, status, latency of the process) like every other request, so a 404 or 5xx on
  `/static/wishlist.js` is visible there. No application metric is added.

### Business Metrics

- N/A. No product behaviour changed.

### System Health Metrics

- N/A. Static serving uses Starlette `StaticFiles` mounted at `/static` in
  `wishenka/web/app.py`. The security middleware in `wishenka/web/security.py` sets
  `Cache-Control: no-store` on all responses, including `/static/*`. Effect: the browser
  re-downloads `wishlist.js` on each page load, so a deployed fix reaches users immediately and no
  cache-busting is needed. The cost is one extra small request per page. No change was made;
  it is recorded as a trade-off for Step 7 (tech-debt analysis).

## Monitoring Integration

- [ ] Prometheus metrics: N/A (no metrics stack)
- [ ] Grafana dashboards: N/A
- [ ] Alerting rules: N/A
- [ ] Log aggregation: N/A. Uvicorn access and application logs cover the server side.
- Client error telemetry: none exists. A grep over `wishenka/` for `sentry`, `onerror`,
  `client error` and `telemetry` found nothing. Not invented here. Possible follow-up: a small
  client-error beacon endpoint or an external error tracker, if client-side failures start to
  matter. This is out of scope for a refactor of 2 SP.

## Validation Results

- [x] Logs are correctly formatted: `node --check wishenka/web/static/wishlist.js` OK.
- [ ] Metrics are collected correctly: N/A
- [x] Logging works in error scenarios: the message is built from the same condition as the
  skip branch. The existing test `tests/test_wishlist_static_script.py` was not changed (no
  assertion touches the warning text) and passes: 11 passed.
- [x] Large data structures are not logged: only the id attribute value and fixed text.
- [ ] Metrics are available for monitoring: N/A
- [x] `make analyze` is green (ruff, ruff format, mypy).

## Notes

- The warning path is not covered by an automated test. It was not added because the task only
  asked to keep the existing tests green, and the branch is a diagnostics-only path.
- The pattern check runs twice in the failure path (once in the condition, once per cause). It is
  cheap and only runs on a failed drop.
