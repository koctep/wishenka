# WISHENKA-95: Observability Implementation

## Logging Implementation

This task adds offline regression tests only. It adds no production paths, log events, or log
fields, so no additional production logging is needed for this change.

Existing `wishenka.items` logging covers relevant execution paths:

- `ssrf_blocked` at WARNING records the host, IP, reason, and configured CIDR count when
  resolution or direct-IP validation rejects a destination in `wishenka/items/ssrf.py`.
- `dns_resolution_start` and `dns_resolution_success` at DEBUG, and
  `dns_resolution_failed` at INFO, describe DNS outcomes in the same module.
- `url_fetch_success` at INFO includes the effective URL and byte count in
  `wishenka/items/fetcher.py`. `fetch_and_extract_fallback` at WARNING records failures
  when the public metadata API returns fallback data.
- Preview service logging includes `item_preview_ssrf_blocked` and related fallback events.

The new redirect tests use an offline replay route and a stub DNS resolver. They verify
blocked dispatch and loop termination through exceptions and transport calls; their stub
resolver does not emit the production `ssrf_blocked` event. Existing production-path logging
tests cover that event and structured fields. The previously identified credential-handling
limitations remain tracked in [WISHENKA-286](https://pypost.atlassian.net/browse/WISHENKA-286).

## Metrics and Monitoring

No metrics were added: no new runtime behavior or performance indicator is introduced, and
there is no existing metrics collector to extend for these tests. No monitoring integrations or
alerting rules were changed.

## Validation Results

- `PYTHONPATH=. .venv/bin/pytest tests/test_ssrf_and_response_limits.py
  tests/test_observability.py tests/test_ssrf_configurable_settings.py -q`: **140 passed**.
- Existing tests exercise structured block, DNS, payload-size and preview logs, JSON formatting,
  and credential or HTML redaction. Log context uses targeted fields instead of raw bodies.
- No metrics collection was changed or validated. Full-suite baseline limitations and Jira
  references are recorded in `41-baseline-test-evidence.md`.
