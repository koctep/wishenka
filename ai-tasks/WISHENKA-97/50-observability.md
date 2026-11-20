# WISHENKA-97: Observability Implementation

## Logging Implementation

### Added Logs

Describe added logging in [`wishenka/items/cassettes.py`](file:///home/src/wishenka/items/cassettes.py) and [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py) (logger `wishenka.items`):
- **EMERG**: N/A - Cassette recording/replay and link preview scraping do not trigger system-wide emergencies.
- **ALERT**: N/A - No immediate operator paging required for testbench cassette operations or link preview anti-bot fallbacks.
- **CRIT**: N/A - No critical system failures originate in the cassette testbench or preview fallback layer.
- **ERR**: [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py) (`ItemPreviewService.fetch_preview`) - Existing `event="item_metadata_parsing_error"` when unexpected HTML parsing exceptions occur.
- **WARNING**:
  - [`wishenka/items/cassettes.py`](file:///home/src/wishenka/items/cassettes.py) (`CassetteTransport.handle_async_request`, `event="cassette_miss"`): logged when an unrecorded `(method, sanitized_uri)` is requested in strict offline `REPLAY` mode before raising `CassetteMissError` (`method`, `uri`, `cassette_path`, `marketplace`, `scenario`). The URI is sanitized via `sanitize_uri` before logging so sensitive query tokens or tracking parameters never leak into log streams.
  - [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py) (`ItemPreviewService.fetch_preview`, `event="item_preview_anti_bot"`): logged when an HTTP `403`/`429`/`503` response or a `200 OK` HTML body matching `CHALLENGE_SIGNATURES` (including Russian marketplace anti-bot screens such as Yandex SmartCaptcha, Avito IP firewall, Qrator, Cloudflare, and DDoS-Guard) triggers graceful fallback (`status_code`, `url_domain`, `input_type`, `duration_ms`, `fallback_reason="anti_bot_challenge"`).
- **NOTICE**: N/A - Python standard `logging` uses `INFO`/`DEBUG`/`WARNING`/`ERROR`.
- **INFO**:
  - [`wishenka/items/cassettes.py`](file:///home/src/wishenka/items/cassettes.py) (`CassetteTransport.handle_async_request`, `event="cassette_recorded"` / `event="cassette_refreshed"`): logged when a new interaction is recorded in `RECORD` mode or updated in `REFRESH` mode (`method`, `uri`, `status_code`, `mode`, `marketplace`, `scenario`, `cassette_path`).
  - [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py) (`ItemPreviewService.fetch_preview`, `event="anti_bot_challenge_detected"`): logged alongside `item_preview_anti_bot` for both HTTP status errors (`403`/`429`/`503`) and `200 OK` HTML challenge pages (`status_code`, `url_domain`, `input_type`, `duration_ms`, `fallback_reason="anti_bot_challenge"`).
- **DEBUG**:
  - [`wishenka/items/cassettes.py`](file:///home/src/wishenka/items/cassettes.py) (`Cassette.load`, `event="cassette_loaded"`): logged when a YAML cassette file is loaded and parsed from disk (`cassette_path`, `marketplace`, `scenario`, `interactions_count`).
  - [`wishenka/items/cassettes.py`](file:///home/src/wishenka/items/cassettes.py) (`Cassette.save`, `event="cassette_saved"`): logged when a sanitized cassette is persisted to disk (`cassette_path`, `marketplace`, `scenario`, `interactions_count`).
  - [`wishenka/items/cassettes.py`](file:///home/src/wishenka/items/cassettes.py) (`CassetteTransport.handle_async_request`, `event="cassette_replay_hit"`): logged when an incoming request matches a recorded cassette interaction (`method`, `uri`, `status_code`, `mode`, `marketplace`, `scenario`).

### Log Structure

Log format used:
- Structured logs: yes (via `extra={"event": ..., ...}` dictionary fields on the `wishenka.items` logger)
- Includes context: yes (`event`, `method`, `uri`, `status_code`, `mode`, `marketplace`, `scenario`, `cassette_path`, `interactions_count`, `url_domain`, `input_type`, `duration_ms`, `fallback_reason`)
- Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: `duration_ms` field emitted in `item_preview_anti_bot`, `anti_bot_challenge_detected`, and `item_preview_success` structured log events in [`wishenka/items/service.py`](file:///home/src/wishenka/items/service.py).
- **Throughput**: N/A - The project does not use an external Prometheus/OpenTelemetry metrics collector; request outcomes are tracked via structured log events.
- **Error rate**: Observable via `event="cassette_miss"`, `event="item_preview_anti_bot"`, and `event="anti_bot_challenge_detected"` structured log counts.

### Business Metrics

Business metrics:
- `fallback_reason="anti_bot_challenge"` and `url_domain` in `item_preview_anti_bot` / `anti_bot_challenge_detected`: tracks marketplace anti-bot degradation frequency per marketplace domain (`wishenka/items/service.py`).

### System Health Metrics

System health metrics:
- **Resource usage**: N/A - Cassette files and HTML payloads are bounded (`MAX_RESPONSE_BYTES = 2 MB`) and never dumped into logs.
- **Component status**: Cassette verification status is reported via CLI (`python -m wishenka.items.cassettes --verify`) and structured cassette events (`cassette_loaded`, `cassette_replay_hit`, `cassette_miss`, `cassette_recorded`, `cassette_refreshed`, `cassette_saved`).

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (not used in repository)
- [ ] Grafana dashboards (not used in repository)
- [ ] Alerting rules (not used in repository)
- [x] Log aggregation (structured `extra` fields on `wishenka.items` logger)

## Validation Results

Validation results:
- [x] Logs are correctly formatted
- [x] Metrics are collected correctly (structured log events and `duration_ms` verified)
- [x] Logging works in error scenarios (`cassette_miss` in offline `REPLAY` mode and `item_preview_anti_bot` / `anti_bot_challenge_detected` on `200 OK` and `403`/`503` anti-bot pages)
- [x] Large data structures are not logged (HTML bodies, raw YAML structures, and sensitive cookies/headers/query tokens are excluded from log records)
- [x] Metrics are available for monitoring (verified via `caplog` in `tests/test_marketplace_cassettes.py`)

## Notes

- Verified via `test_cassette_and_antibot_structured_logging_observability` in [`tests/test_marketplace_cassettes.py`](file:///home/src/tests/test_marketplace_cassettes.py).
