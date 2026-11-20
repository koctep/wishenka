# WISHENKA-94: Observability Implementation

## Logging Implementation

### Added Logs

Describe added logging in [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py) (logger `wishenka.items`):
- **EMERG**: N/A - DNS caching is an in-memory optimization; no system-wide emergencies occur here.
- **ALERT**: N/A - No immediate operator paging required for DNS cache operations.
- **CRIT**: N/A - No critical system failures originate in the DNS cache layer.
- **ERR**: N/A - DNS resolution failures are handled gracefully (returning `[]` without negative caching).
- **WARNING**: [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py) (`_resolve_and_validate_uncached`, `resolve_and_validate_host`) - Existing SSRF block warnings (`event="ssrf_blocked"`) fire when any resolved IP or direct IP literal is forbidden, including on re-validation after TTL expiration.
- **NOTICE**: N/A - Python standard `logging` uses `INFO`/`DEBUG`/`WARNING`.
- **INFO**: [`wishenka/items/ssrf.py`](file:///home/src/wishenka/items/ssrf.py) (`_resolve_and_validate_uncached`) - Existing operational notification when OS DNS resolution fails (`event="dns_resolution_failed"` with `host` and `error`).
- **DEBUG**:
  - `DNSCache.get` (`event="dns_cache_expired"`): logged when a cached entry's monotonic TTL has elapsed (`host`, `port`).
  - `DNSCache.put` (`event="dns_cache_evicted"`): logged when an LRU entry is evicted to stay within `capacity` (`evicted_host`, `evicted_port`, `capacity`).
  - `resolve_and_validate_host` (`event="dns_cache_hit"`): logged when a valid, unexpired cached IP list is returned (`host`, `port`, `ip_count`).
  - `resolve_and_validate_host` (`event="dns_cache_miss"`): logged when a cold/expired hostname initiates an uncached resolution leader task (`host`, `port`).
  - `resolve_and_validate_host` (`event="dns_single_flight_coalesced"`): logged when a concurrent request joins an already in-flight DNS resolution on the same event loop (`host`, `port`).
  - `_resolve_and_validate_uncached` (`event="dns_resolution_start"` / `event="dns_resolution_success"`): logged before and after `loop.getaddrinfo` + SSRF IP verification.

### Log Structure

Log format used:
- Structured logs: yes (via `extra={"event": ..., ...}` dictionary fields compatible with the application's structured logging pipeline)
- Includes context: yes (`host`, `port`, `ip_count`, `evicted_host`, `evicted_port`, `capacity`)
- Log levels: `DEBUG`, `INFO`, `WARNING`

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: N/A - The project does not use Prometheus/OpenTelemetry metrics collectors; DNS cache efficacy is observable via structured log events (`dns_cache_hit`, `dns_cache_miss`, `dns_single_flight_coalesced`).
- **Throughput**: N/A
- **Error rate**: N/A

### Business Metrics

Business metrics:
- N/A - Internal SSRF/DNS resolution layer.

### System Health Metrics

System health metrics:
- **Resource usage**: N/A - Memory is strictly bounded by `DEFAULT_DNS_CACHE_CAPACITY = 512` and logged on eviction (`dns_cache_evicted`).
- **Component status**: N/A

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (not used in repository)
- [ ] Grafana dashboards (not used in repository)
- [ ] Alerting rules (not used in repository)
- [x] Log aggregation (structured `extra` fields on `wishenka.items` logger)

## Validation Results

Validation results:
- [x] Logs are correctly formatted
- [x] Metrics are collected correctly (N/A — log-based observability verified)
- [x] Logging works in error scenarios (SSRF blocks and `gaierror` uncached paths tested)
- [x] Large data structures are not logged (cache hit logs `ip_count` rather than dumping full cache structures)
- [x] Metrics are available for monitoring (structured log events verified via `caplog` in `tests/test_dns_cache.py`)

## Notes

- Verified via `TestDNSCacheBehavior.test_dns_cache_structured_logging_events` in [`tests/test_dns_cache.py`](file:///home/src/tests/test_dns_cache.py).
