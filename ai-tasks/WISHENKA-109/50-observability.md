# WISHENKA-109: Observability Implementation

## Scope Decision

The task added a client-side touch reorder (Pointer Events gesture) in
`wishenka/web/static/wishlist.js`. The server contract is unchanged:
`POST /web/wishlists/{id}/items/reorder`. Server logs for that endpoint already exist and were
only reviewed. One genuine client diagnostics gap was found and fixed: the Telegram SDK failure
warning did not name the failing call. Nothing else was added.

## Logging Implementation

### Added Logs

- **EMERG / ALERT / CRIT / ERR / NOTICE / INFO / DEBUG**: N/A. A static script has no log
  channel except the browser console, and a drag gesture is not worth logging in normal operation.
- **WARNING**: `wishenka/web/static/wishlist.js`, `warnSdk(call, error)`. This is the only code
  change in the step. Before: `wishlist.js: Telegram SDK call failed` plus the error object, with
  no hint about which call threw. After:
  `wishlist.js: Telegram SDK call failed (<call>); later failures are not reported`, plus the
  error object. `<call>` is one of `disableVerticalSwipes`, `enableVerticalSwipes`,
  `HapticFeedback.impactOccurred`, `HapticFeedback.selectionChanged`. The warning is still emitted
  once per page load (`sdkWarned` flag), so a failing haptic call cannot flood the console during
  a drag. The text now says that later failures are suppressed, so a reader does not assume only
  one call failed. Note: `disableVerticalSwipes` is the label for the whole guarded block in
  `disableSwipes` (it also covers `isVersionAtLeast` and `isVerticalSwipesEnabled` reads).

### Client console calls (complete list, `grep console\. wishenka/web/static/*.js`)

1. `wishlist.js` `submitReorder` (shared by mouse drop and touch drop):
   `console.warn('wishlist.js: reorder skipped: <causes>')` where causes are
   `#items-list[data-wishlist-id] is not numeric (got "<value>")` and/or
   `window.htmx is not loaded (CDN blocked or script order)`. Unchanged from WISHENKA-108.
   Actionable: points at the template attribute or the script load order.
2. `wishlist.js` `warnSdk`: the Telegram SDK warning described above. Actionable: names the call;
   the attached error object carries the cause and stack.

There are no other `console.*` calls. Silent `catch` blocks (`telegramWebApp()` reading
`window.Telegram`, `releasePointerCapture`, `setPointerCapture`) are deliberate best-effort paths
with an inline comment. They fail only when the pointer is already gone or capture is unsupported,
and the gesture still works through document-level listeners, so a warning would be noise.

### Existing server-side logs (reviewed, not changed)

`wishenka/web/routes/items_ui.py`, endpoint `POST /web/wishlists/{id}/items/reorder`
(`reorder_items_ui`, via `_reordered_response`):
- **INFO**: event `ui_items_reordered` with `wishlist_id`, `actor_id`, `user_id`, `item_count`.
- **WARNING**: event `ui_items_reorder_rejected` with `wishlist_id`, `actor_id`, `user_id`,
  `reason=invalid_permutation`; the response is 400.
- Move up/down (`POST /items/{item_id}/move`): success logs INFO `ui_item_moved` (`wishlist_id`,
  `item_id`, `actor_id`, `user_id`, `direction`); rejection shares the same
  `ui_items_reorder_rejected` WARNING and the 400.
- A drop that the client skips (bad wishlist id, htmx missing) never reaches the server. The
  console warning above is the only trace of it.

### Log Structure

- Structured logs: server yes (`extra={"event": ...}`); client no (plain console text).
- Includes context: yes (server ids and counts; client failing call name and error object).
- Log levels: server INFO and WARNING; client `console.warn`.

### Limitations

- Touch and mouse reorders cannot be told apart in server logs. Both use the same endpoint with
  the same payload, and `ui_items_reordered` has no input-method field. Adding one would need a new
  request parameter or header, which this task does not justify. Possible follow-up only if the
  touch gesture needs rollout monitoring; not implemented.
- Cancelled gestures (Escape, second finger, pointercancel, drop on self) send no request and
  leave no trace by design.
- Real-device behaviour (Telegram WebView, swipe-minimize race) is not observable from logs; it is
  covered by the manual checklist in `20-architecture.md` section (d).

## Metrics Implementation (if applicable)

N/A. The project has no metrics stack and no behaviour changed that needs one.

### Performance Metrics

- **Response time / throughput / error rate**: N/A. Requests to `/static/wishlist.js` and
  `/static/miniapp.css` appear in the uvicorn access log like any other request, so a 404 or 5xx
  is visible there. The reorder POST is visible in the same log with its status (400 on rejection).
  No application metric is added.

### Business Metrics

- N/A. No product behaviour changed; the same reorder action is simply reachable by touch.

### System Health Metrics

- N/A. The security middleware (`wishenka/web/security.py`, line 79, WISHENKA-139) sets
  `Cache-Control: no-store` on all responses, including `/static/*`. A deployed fix to
  `wishlist.js` therefore reaches users on the next page load. No change was made.

## Monitoring Integration

- [ ] Prometheus metrics: N/A (no metrics stack)
- [ ] Grafana dashboards: N/A
- [ ] Alerting rules: N/A
- [ ] Log aggregation: N/A. Uvicorn access and application logs cover the server side.
- Client error telemetry: none exists. A repeated grep over `wishenka/` for `sentry`, `onerror`,
  `sendBeacon` and `telemetry` found no client-side hits (only unrelated `AuthValidationError`
  matches for `onerror`-like substrings in Python). Not invented here. Possible follow-up: a
  client-error beacon endpoint or an external error tracker, out of scope for a 3 SP debt task.

## Validation Results

- [x] Logs are correctly formatted: `node --check wishenka/web/static/wishlist.js` OK.
- [ ] Metrics are collected correctly: N/A
- [x] Logging works in error scenarios: `warnSdk` is called from the same catch blocks as before;
  only the label argument was added. `tests/test_wishlist_touch_reorder.py` and
  `tests/test_wishlist_static_script.py` were not changed and pass: 48 passed.
- [x] Large data structures are not logged: fixed text, a call name, and the caught error object.
- [ ] Metrics are available for monitoring: N/A
- [x] `make analyze` is green (ruff, ruff format, mypy).

## Notes

- The SDK-failure warning path has no automated test; no existing assertion touches its text. It
  was not added because it is a diagnostics-only path.
- Line length of the `warnSdk(...)` call in `haptic` exceeds typical JS width; the repo has no JS
  formatter, so it was left as is.
