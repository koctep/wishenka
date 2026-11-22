# WISHENKA-289: Observability Implementation

## Logging Implementation

### Added Logs

N/A — no server-side or client-side logging was added in `WISHENKA-289`.

Audit of `WISHENKA-289` scope (`git diff`):

- `wishenka/i18n/catalog.py`: adds 13 paired `en`/`ru` `miniapp.home.*` entries in `CATALOG`
  (`miniapp.home.lead`, `miniapp.home.reservations_hint`, `miniapp.home.my_wishlists_sub`,
  `miniapp.home.my_wishlists_empty_hint`, `miniapp.home.collaborating_sub`,
  `miniapp.home.collaborating_empty_hint`, `miniapp.home.favorites_sub`,
  `miniapp.home.favorites_empty_hint`, `miniapp.home.deleted_sub`, `miniapp.home.open_wishlist`,
  `miniapp.home.open_wishlist_named`, `miniapp.home.remove_favorite`, and
  `miniapp.home.remove_favorite_named`). All 13 keys carry the `miniapp.` prefix and are embedded
  into `<script id="miniapp-i18n">` by `miniapp_catalog()` on `GET /`.
- `wishenka/web/static/miniapp.js`: adds client DOM/formatting helpers (`formatDate`,
  `renderSectionHeader`, `renderEmptyState`), refines `wishlistCard()` and `showHome()` to render
  `.home-lead`, `.top-nav.home-top-nav`, `.reservations-card` (parsed from `/web/reservations/card`
  via `DOMParser` and constructed with `node()`), direct-child `.wishlist-section` regions
  (`--owned`, `--collab`, `--favorites`, and conditional `--deleted`) with
  `owner > admin > member > favorite` deduplication, `.wishlist-card-open` /
  `.wishlist-card-remove` actions, and two-part `.empty-state` blocks. Introduces no new backend
  routes, API calls, state transitions, debug `console.log` calls, or client telemetry beacons.
- `wishenka/web/static/miniapp.css`: adds `#app`-scoped Home layout, `.reservations-card`, section
  left-border cues, card action hierarchy, `.empty-state`, and `<= 412px` mobile wrap rules. Served
  under `/static` via `StaticFiles` in `wishenka/web/app.py` behind `RequestLoggingMiddleware` and
  `BrowserSecurityMiddleware`.
- `tests/test_home_overview_ui.py` and `tests/test_home_overview_browser.py`: automated Node VM,
  i18n contract, and headless Chromium layout/interaction test suites; no production code.

### Existing Production Observability

All execution paths exercised by the Home overview retain existing server and client observability:

- **HTTP lifecycle, security, and JSON formatting** (`wishenka/web/app.py`,
  `wishenka/web/security.py`, `wishenka/logging.py`):
  - `wishenka.web`: `RequestLoggingMiddleware.dispatch` logs `HTTP request started` (`DEBUG`:
    `method`, `path`), `HTTP request completed` (`INFO`: `method`, `path`, `status_code`,
    `duration_ms`), and `HTTP request unhandled exception` (`ERROR` via `logger.exception`:
    `method`, `path`, `duration_ms`) across `GET /`, `/static/*`, `/web/reservations/card`,
    `/web/reservations`, `/settings`, and `/api/*` endpoints while redacting capability tokens in
    `/api/public/wishlists/{token}`, `/share/{token}`, and `/invite/{token}` (mirrored by
    `ShareTokenAccessFilter` on `uvicorn.access`).
  - `wishenka.web.security`: `BrowserSecurityMiddleware.dispatch` logs `origin_mismatch`,
    `csrf_origin_mismatch`, and `csrf_token_invalid` at `WARNING`.
  - `JsonFormatter` (`wishenka/logging.py`) formats structured JSON log lines with `extra` fields
    when `settings.log_json` is enabled.
- **Mini App shell and i18n catalog** (`wishenka/web/routes/miniapp.py`,
  `wishenka/i18n/catalog.py`):
  - `wishenka.web.miniapp`: `miniapp` (`GET /`) emits `miniapp_shell_requested` (`INFO`) and
    `miniapp_catalog_embedded` (`DEBUG`: `locale`, `key_count`) without logging full catalog
    dicts.
  - `wishenka.i18n`: server `t()` emits `i18n_missing_translation_key` (`WARNING`: `i18n_key`,
    `locale`, `fallback_locale`) if a server translation key is missing for a locale.
- **Home overview API and card endpoints** (`wishenka/web/routes/wishlists.py`,
  `wishenka/web/routes/reservations_ui.py`):
  - `wishenka.web.wishlists`:
    - `list_wishlists` (`GET /api/wishlists`) runs under `RequestLoggingMiddleware` and returns
      caller-scoped wishlist projections with zero reservation or giver fields (Surprise
      Invariant).
    - `list_favorites` (`GET /api/favorites`) emits `favorites_listed` (`INFO`: `user_id`,
      `count`).
    - `remove_favorite` (`DELETE /api/favorites/{wishlist_id}`, triggered by
      `.wishlist-card-remove`) emits `favorite_removed` (`INFO`: `wishlist_id`, `user_id`).
    - `list_deleted_wishlists` (`GET /api/wishlists/deleted`) emits `wishlist_deleted_listed`
      (`INFO`: `user_id`, `count`, `retention_days`).
    - `restore_deleted_wishlist` (`POST /api/wishlists/{wishlist_id}/restore-deleted`, triggered
      by `.wishlist-card-restore`) emits `wishlist_restored_from_deleted` (`INFO`: `wishlist_id`,
      `user_id`, `retention_days`) and `wishlist_mutation_committed` (`INFO`:
      `operation="restore_deleted_wishlist"`), or `wishlist_retention_expired` (`WARNING`:
      `operation="restore_deleted_wishlist"`) on HTTP 410 and `wishlist_permission_denied`
      (`WARNING`: `operation`) on `PermissionDeniedError`.
    - `create_wishlist` (`POST /api/wishlists`, triggered by `.home-create-btn`) emits
      `wishlist_created` (`INFO`: `wishlist_id`, `user_id`) and `wishlist_mutation_committed`
      (`INFO`: `operation="create_wishlist"`).
    - `get_history` (`GET /api/history`, triggered by `.home-nav-action` -> `showHistory()`) emits
      `view_history_listed` (`INFO`: `user_id`, `count`), and `record_view`
      (`POST /api/history/{wishlist_id}`, triggered on `showList(id)`) emits
      `view_history_recorded` (`INFO`: `wishlist_id`, `user_id`).
  - `reservations_card` (`GET /web/reservations/card` in
    `wishenka/web/routes/reservations_ui.py`) renders `partials/reservations_card.html` with
    `distinct_count` (`summary.total_distinct_items`) and is logged with status code and latency by
    `RequestLoggingMiddleware` (`wishenka.web`). Promise mutations remain on
    `wishenka/web/routes/reservations.py` (`wishenka.web.reservations`:
    `reservation_action_completed`, `reservation_action_refused`, `reservation_inventory_busy`,
    `reservation_permission_denied`, `reservation_idempotency_conflict`, `reservation_conflict`,
    and `reservation_validation_error`).
- **Client-side live-region feedback and graceful degradation**
  (`wishenka/web/static/miniapp.js`):
  - `#status` (`role="status"`, `aria-live="polite"`) announces loading and outcome states via
    `status(t(...))`: `nav.loading`, `miniapp.home.load_failed`, `miniapp.home.create_failed`,
    `miniapp.home.removed_from_favorites`, `miniapp.home.remove_favorite_failed`,
    `miniapp.deleted.restoring`, `miniapp.deleted.restored`, `miniapp.deleted.expired` (on HTTP
    410), and `miniapp.deleted.restore_failed`, clearing to `''` on normal Home render completion.
  - Non-blocking Home fallbacks: `api('/api/favorites').catch(() => [])`,
    `api('/api/wishlists/deleted').catch(() => [])`, and the `try / catch` around
    `fetch('/web/reservations/card', {credentials: 'same-origin'})` guarantee that transient
    secondary endpoint failures never blank out the primary Home sections.
  - Client `loadI18nCatalog()` and `t()` emit at most one `console?.warn?.(...)` per missing i18n
    key via `WARNED_MISSING_KEYS`.

### Log Structure

- Structured logs: `yes` (unchanged `extra={"event": ...}` records formatted by `JsonFormatter` in
  `wishenka/logging.py`; zero new log calls added in `WISHENKA-289`).
- Includes context: `yes` (scalar `wishlist_id`, `user_id`, `count`, `retention_days`, `operation`,
  `locale`, `key_count`, and HTTP `method`/`path`/`status_code`/`duration_ms`; no tokens, secrets,
  or large collection payloads).
- Log levels: none added (`DEBUG`, `INFO`, `WARNING`, `ERROR` already used on existing paths).

## Metrics Implementation (if applicable)

### Performance Metrics

N/A — no Prometheus, Grafana, OpenTelemetry, or StatsD metrics collector is wired in this
repository. Request duration (`duration_ms`) and `status_code` for `GET /`, `/static/*`,
`/api/wishlists`, `/api/favorites`, `/api/wishlists/deleted`, and `/web/reservations/card` are
recorded by `RequestLoggingMiddleware` in `wishenka/web/app.py`.

### Business Metrics

N/A — Home overview interactions remain observable via existing structured log events
(`miniapp_shell_requested`, `wishlist_created`, `favorites_listed`, `favorite_removed`,
`wishlist_deleted_listed`, `wishlist_restored_from_deleted`, `wishlist_retention_expired`, and
`view_history_listed`).

### System Health Metrics

N/A — no new background tasks, workers, or database tables were introduced; `/healthz` in
`wishenka/web/app.py` is unchanged.

## Monitoring Integration

- [ ] Prometheus metrics (N/A — no Prometheus exporter in repository)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (existing structured `extra` fields formatted by `JsonFormatter`)

## Validation Results

Checks executed after the final edit:

- [x] Logs are correctly formatted (verified via `tests/test_observability.py` and
  `tests/test_wishlist_management_observability.py`)
- [x] Metrics are collected correctly (N/A — repository uses structured request/event logs rather
  than a metrics exporter)
- [x] Logging and client live-region fallbacks work in error scenarios (HTTP 500 on
  `/web/reservations/card`, `/api/favorites` and `/api/wishlists/deleted` fallbacks, and HTTP 410
  on `/api/wishlists/{id}/restore-deleted`)
- [x] Large data structures are not logged (`miniapp_catalog_embedded` logs `key_count` only; list
  and favorite endpoints log scalar `count` and IDs only)
- [x] Static analysis, formatting, type checking, JS syntax, and markdown line-length checks pass

## Notes

- Because `WISHENKA-289` is a client Home overview layout, action-hierarchy, deduplication, and
  bilingual copy enhancement over existing endpoints, adding redundant client or server log calls
  would duplicate events already emitted by `wishenka.web`, `wishenka.web.miniapp`, and
  `wishenka.web.wishlists`.
