# WISHENKA-140: Observability Implementation

## Logging Implementation

### Added Logs

No new application logs were added in this task (N/A for static-JS extraction):

- **Server-side (`/static/app.js` delivery)**: `wishenka/web/static/app.js` is served via FastAPI `StaticFiles` mounted at `/static` in `wishenka/web/app.py` and is already covered by `RequestLoggingMiddleware` (`wishenka.web` logger):
  - **DEBUG**: `RequestLoggingMiddleware.dispatch` (`wishenka/web/app.py`) — logs `HTTP request started: %s %s` with `method` and `path`.
  - **INFO**: `RequestLoggingMiddleware.dispatch` (`wishenka/web/app.py`) — logs `HTTP request completed: %s %s status=%d duration=%.2fms` with `method`, `path`, `status_code`, and `duration_ms`.
  - **ERR / Exception**: `RequestLoggingMiddleware.dispatch` (`wishenka/web/app.py`) — logs `HTTP request unhandled exception` via `logger.exception(...)` on unhandled errors.
- **Client-side (`wishenka/web/static/app.js`)**: Intentionally emits no `console.log` or `console.debug` statements in production to avoid browser console noise. Error states (CSRF preparation failure, `403` invalid CSRF, `503` busy lock) are surfaced to the user in the DOM via `[data-giver-busy]` and `[data-reservation-busy]` slots, while corresponding `/api/auth/csrf`, reservation mutations, and card/cabinet refresh requests are logged server-side by `RequestLoggingMiddleware`.
- **EMERG / ALERT / CRIT / WARNING / NOTICE**: N/A — no new server-side components or failure modes introduced.

### Log Structure

Log format used (existing `RequestLoggingMiddleware` in `wishenka/web/app.py` configured via `configure_logging`):
- Structured logs: yes (`extra={"method", "path", "status_code", "duration_ms"}`, JSON-capable via `settings.log_json`)
- Includes context: yes (HTTP method, path, status code, duration in ms)
- Log levels: `DEBUG`, `INFO`, `ERROR` (via `logger.exception`)

## Metrics Implementation (if applicable)

N/A — WISHENKA-140 is a pure client-side refactoring (extracting `base.html` inline `<script>` into `wishenka/web/static/app.js` and replacing 6 inline `onclick` attributes with delegated `data-*` handlers). It introduces no new backend endpoints, database queries, or background workers.

### Performance Metrics

- **Response time**: Covered for `/static/app.js` by `RequestLoggingMiddleware` (`duration_ms` field).
- **Throughput / Error rate**: Covered for `/static/app.js` by `RequestLoggingMiddleware` (`status_code` field).

### Business Metrics

- N/A (no new business events or endpoints).

### System Health Metrics

- N/A (static asset served by existing FastAPI `StaticFiles` mount).

## Monitoring Integration

Existing web application logging/monitoring applies without changes:
- [ ] Prometheus metrics (N/A — not used by this task)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (existing `wishenka.web` structured logs from `RequestLoggingMiddleware` cover `/static/app.js` and CSRF/reservation endpoints)

## Validation Results

- [x] `wishenka/web/static/app.js` contains no `console.log` / `console.debug` statements
- [x] `/static/app.js` is served through FastAPI `StaticFiles` under `RequestLoggingMiddleware` in `wishenka/web/app.py`
- [x] Large data structures are not logged
- [x] Error scenarios surface user-facing DOM notices (`[data-giver-busy]`, `[data-reservation-busy]`) without leaking tokens or sensitive payloads

## Notes

- No production code or test files were modified during Step 6; existing `RequestLoggingMiddleware` in `wishenka/web/app.py` already provides full HTTP request/response observability for `/static/app.js` and all HTMX/fetch endpoints invoked by it.
