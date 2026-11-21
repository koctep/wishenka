# WISHENKA-114: Technical Debt Analysis

## Shortcuts Taken

- Arbitrary injected `httpx.AsyncClient` instances are deliberately unsupported and fail closed.
  Integrators must supply explicit routes. This is the approved safety boundary, but callers
  using the earlier private-client integration need to migrate to the new contract.
- Offline cassette verification uses a private fixture-only fetcher. It exercises preview and
  redirect behavior without resolving DNS; it does not replace live DNS and connection tests.
  The production path still validates destinations and uses the pinned direct transport.
- The HTTPX dependency is constrained to `>=0.28.0,<0.29`; 0.28.0 and 0.28.1 were exercised
  during development. New dependency versions require a deliberate compatibility review.

## Code Quality Issues

`wishenka/items/ssrf.py` still installs `SSRFSafeNetworkBackend` through HTTPX's `_pool` and
httpcore's `_network_backend`. Unknown pool or backend layouts now fail closed, and the installed
backend is checked before dispatch; a private backend change may still break startup or requests.
WISHENKA-114 removes private inspection from the injected-client routing decision, but does not
remove this separate pre-existing connection-layer dependency. HTTPX's version cap limits one
source of changes; it does not itself prove compatibility with every transitive httpcore release.

## Missing Tests

- All changed pytest modules declare explicit timeout markers; the resource-reuse module also
  supplies a longer timeout for its capacity test.
- The related route, cassette, and resource-reuse suite passed 90 tests; route and observability
  coverage passed 23 tests. The updated `test_url_tracking_params_cleaned_in_item_preview_service`
  case in `tests/test_metadata_extractor_service.py` passed independently through `make test`.
- `make test PYTEST_JOBS=4` reached the 600-second Makefile limit at 45%, so the complete suite
  remains unverified for this task. It logged three intermittent i18n failures before pytest
  emitted tracebacks. Those three tests passed twice on the base and twice on the WISHENKA-98
  task tree and are tracked as flaky by
  [WISHENKA-283](https://pypost.atlassian.net/browse/WISHENKA-283).
  Do not infer that unexecuted tests passed. The earlier metadata assertion was updated and
  passed separately as recorded above.

## Performance Concerns

Each preview creates a separate HTTPX client and wrapper set for isolation while borrowing the
underlying approved connection pools. It performs destination validation on each redirect and
fresh validation on cache hits; this intentionally trades latency for safety. No new production
throughput benchmark was run. Existing concurrent cache-miss duplication and extraction pool
saturation remain described in WISHENKA-53 and
[WISHENKA-113](https://pypost.atlassian.net/browse/WISHENKA-113).

## Follow-up Tasks

- **NON-BLOCKER — High: Remove the private connection-pinning hook.** Replace the
  `_pool._network_backend` dependency with a supported pinned-connection integration.
  The current implementation fails closed when the expected backend cannot be installed.
  Exercise supported HTTPX and
  httpcore versions, DNS rebinding, TLS hostname/SNI, and direct route ownership in an automated
  upgrade matrix. Until then, review both dependency changes before deployment. This is distinct
  from the injected-client routing work in WISHENKA-114. Jira: [WISHENKA-284](https://pypost.atlassian.net/browse/WISHENKA-284).
- **NON-BLOCKER — Medium: Restore a reliable full-suite quality gate.** Investigate why
  `make test PYTEST_JOBS=4` reached its 600-second limit at 45% in the current environment;
  retain bounded waits and establish a complete result without masking failures. Preserve exact
  logs and durations when reproducing. Jira: [WISHENKA-285](https://pypost.atlassian.net/browse/WISHENKA-285).
- **Already tracked:** the three intermittent i18n tests are in WISHENKA-283; extraction worker
  load/cancellation is in WISHENKA-113; the Starlette test-client deprecation is in WISHENKA-41.
  These items are not duplicated here.
