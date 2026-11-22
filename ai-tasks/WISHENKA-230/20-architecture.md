# WISHENKA-230: Safe connection edge-case coverage

## Research

- `wishenka/items/ssrf.py` resolves a cache miss through `resolve_and_validate_host`.
  `_resolve_and_validate_uncached` converts `socket.gaierror` and `OSError` to an empty result.
  `SSRFSafeNetworkBackend.connect_tcp` raises `httpcore.ConnectError` and emits
  `ssrf_no_validated_ips` when that result is empty, without calling its inner backend.
- The backend deduplicates pinned addresses in input order and tries only those addresses. On
  exhaustion it emits `ssrf_all_pinned_connects_failed`; it propagates httpcore connection errors
  and wraps a final `OSError` in `httpcore.ConnectError` with exception chaining.
- `tests/test_ssrf_dns_rebinding.py` already provides asynchronous tests, an in-memory network
  stream, and a module-wide 30-second timeout. It exercises successful pinning and fallback, but
  not the requested failure and duplicate cases directly.
- The [pytest fixture documentation](https://docs.pytest.org/en/stable/builtin.html) describes
  `monkeypatch` for scoped substitutions and `caplog.records` for structured log assertions.

## Implementation Plan

1. Add focused asynchronous regression tests to `tests/test_ssrf_dns_rebinding.py`, using an
   injected fake inner backend that records connection calls and never accesses the network.
2. Simulate a DNS `socket.gaierror` through the async loop resolver on a cache miss. Clear the
   DNS cache around the test and isolate any pinned context. Assert `httpcore.ConnectError`, the
   `ssrf_no_validated_ips` warning, and zero inner backend calls, including to the hostname.
3. Supply deterministic validated addresses and have each fake connection raise `OSError`.
   Assert each unique IP was attempted, the final error is `httpcore.ConnectError` chained from
   the underlying error, and `ssrf_all_pinned_connects_failed` reports the expected count.
4. Supply repeated and distinct validated IPs. Force attempts far enough to observe each unique
   destination, assert the first-seen order and exactly one call per unique address, and confirm
   no hostname connection. Restore any context variables even on assertion failure.
5. Run the focused tests and repository quality checks. Classify unrelated failures against the
   established baseline, including the browser setup issue WISHENKA-297.

**Step 3 failing repro:** N/A — no behavioral change. This task adds coverage of existing
behavior, rather than fixing a known defect. If a new test exposes a defect, preserve and
independently review the offline failing test before modifying production code.

## Architecture

```text
pytest async cases
    | inject DNS response / pinned addresses; capture log records
    v
SSRFSafeNetworkBackend.connect_tcp(host, port, ...)
    | resolve_and_validate_host -> DNS cache / async resolver (fake for DNS failure)
    | validated addresses only, deduplicated in first-seen order
    v
fake AsyncNetworkBackend.connect_tcp -> recorded calls / deterministic OSError
    |
    +--> httpcore.ConnectError and structured warning observed by pytest
```

### Components and responsibilities

- **Test module:** owns fixtures, controlled inputs, assertions, bounded execution, and cleanup.
- **Resolver and DNS cache:** return validated addresses or an empty list on lookup failure;
  the failure test uses an isolated hostname and cache to exercise the actual conversion.
- **Safe network backend:** selects pinned or resolved addresses, rejects an empty set, forwards
  validated IPs to its injected backend, and reports exhaustion.
- **Fake inner backend:** implements the async `connect_tcp` interface, records arguments and
  produces controlled errors. It must not invoke a real network backend.
- **Log capture:** inspects `LogRecord` event and contextual fields without relying on rendered
  message formatting.

### Interfaces and dependencies

The subject is `await connect_tcp(host, port, timeout=None, local_address=None, socket_options=None)`
returning an `httpcore.AsyncNetworkStream` or raising `httpcore.ConnectError`. Resolver substitution
and injected backend behavior are scoped to each test; pinned context tokens are reset in
`finally`. The tests depend on `pytest`, `httpcore`, and existing project code only. No application
interface, configuration, or production dependency changes are planned.

## Q&A

- **Why test through the real resolver on lookup failure?** It verifies the conversion from
  `socket.gaierror` to an empty validated set, not just the backend's handling of a stubbed list.
- **Why force all duplicate-address attempts to fail?** A successful first call would short-circuit
  the loop and could not demonstrate that subsequent duplicate entries are skipped.
- **Are warning messages an interface?** Assertions target structured `event` and relevant fields,
  keeping tests independent of prose wording.
