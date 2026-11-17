# WISHENKA-73: Observability Implementation

## Logging Implementation

### Added Logs

Describe added logging:
- **EMERG**: N/A
- **ALERT**: N/A
- **CRIT**: N/A
- **ERR**: N/A
- **WARNING**:
  - `wishenka/web/static/miniapp.js` (`loadI18nCatalog()`): emits `console?.warn?.(...)` once at startup if `#miniapp-i18n` is missing/empty, not an object, or fails `JSON.parse`.
  - `wishenka/web/static/miniapp.js` (`t(key, params)`): emits `console?.warn?.(...)` once per missing translation key (tracked via `WARNED_MISSING_KEYS` `Set`, only when `I18N_CATALOG` is non-empty to avoid console spam if the catalog failed to load).
  - Existing backend `WARNING` log in `wishenka/i18n/catalog.py` (`t()`): continues to emit `i18n_missing_translation_key` with `i18n_key`, `locale`, and `fallback_locale` context.
- **NOTICE**: N/A
- **INFO**:
  - Existing `wishenka/web/routes/miniapp.py` (`miniapp()`): continues to emit `miniapp_shell_requested` on `GET /`.
- **DEBUG**:
  - `wishenka/web/routes/miniapp.py` (`miniapp()`): added structured `DEBUG` log `miniapp_catalog_embedded` with scalar fields `locale` and `key_count` (never logging the full catalog payload).

### Log Structure

Log format used:
- Structured logs: yes (Python backend via `logging` + `extra={...}`; client-side diagnostics via `console?.warn?.` in `miniapp.js`)
- Includes context: yes (`event`, `locale`, `key_count` on backend; `key` and `locale` / parse error on client)
- Log levels: `INFO` (existing), `DEBUG` (added in `miniapp.py`), `WARNING` (existing in `catalog.py` + `console.warn` in `miniapp.js`)

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- N/A — `miniapp_catalog()` is a pure in-memory dictionary projection and `GET /` request latency is already covered by the `wishenka.web` request logging middleware.

### Business Metrics

Business metrics:
- N/A — no new business metrics required for static UI translation delivery.

### System Health Metrics

System health metrics:
- N/A — no new system health metrics required.

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (structured JSON logs via `wishenka.logging` for `wishenka.web.miniapp`)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (verified via `tests/test_wishlist_management_observability.py::test_miniapp_catalog_embedded_debug_log` and `test_miniapp_shell_requested_log`)
- [x] Metrics are collected correctly (N/A)
- [x] Logging works in error scenarios (`miniapp.js` `loadI18nCatalog()` and `t()` fallback paths)
- [x] Large data structures are not logged (`miniapp_catalog_embedded` logs only `locale` and `key_count`, not the serialized catalog)
- [x] Metrics are available for monitoring (N/A)
- [x] `node --check wishenka/web/static/miniapp.js` passed (exit 0)
- [x] `make analyze` (`ruff check`, `ruff format --check`, `mypy`) passed across 196 source files
- [x] `make test` passed (`1092 passed, 4 warnings in 71.36s`)

## Notes

- Step 6 status in `ai-tasks/WISHENKA-73/00-roadmap.md` is left as `[/]` for the orchestrator to mark `[x]` after review passes.
