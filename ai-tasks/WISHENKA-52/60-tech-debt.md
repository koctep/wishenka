# WISHENKA-52: Technical Debt Analysis

## Shortcuts Taken

Both callers use the shared default executor to preserve the existing parser and result format.
This follows the architecture and adds no parser dependency. Cancelling a request does not stop
an extraction already running in a worker. The executor has a bounded number of threads, but
submissions may queue and retain HTML documents while waiting.

## Code Quality Issues

The two service entry points each own an explicit offload call and their distinct error handling.
This small duplication keeps the existing fallback behavior clear; no refactoring is required for
this task. There are no new production hardcoded values or deviations from the selected design.

## Missing Tests

- The real-parser test measures an in-process `/healthz` request while a page larger than 1 MiB
  is being parsed, with a one-second upper bound and an explicit overlap assertion. It covers both
  extraction paths, but it does not establish latency guarantees on every deployment or load.
- The affected test module has `pytestmark = pytest.mark.timeout(30)`. No pre-existing failures
  were observed: the last full suite reported 312 passed.
- Saturation, queue growth, and cancellation under multiple simultaneous heavy extractions are
  not covered by a load test. The tests also use a BeautifulSoup private parser callback to
  observe real parsing, which may need adjustment after a dependency update.

## Performance Concerns

The Python parser still competes for the GIL with the event-loop thread. Thread offload permits
loop progress, but neither guarantees a particular latency nor isolates CPU under concurrent load.
Executor queueing and already-running work after cancellation can increase memory use and delay
other work sharing the default executor. Existing response size limits still apply per document.

## Follow-up Tasks

- **NON-BLOCKER — Medium: Characterize and bound concurrent extraction load.** Measure request
  latency, executor queueing, and memory under representative concurrent heavy pages and cancelled
  requests. Based on results, introduce an appropriate admission limit or isolated worker strategy
  and observable queue/parse timings. Preserve SSRF protection, output parity, and response limits.
  This is distinct from the immediate acceptance check above, which concerns a single concurrent
  lightweight request.
  Jira: [WISHENKA-113](https://pypost.atlassian.net/browse/WISHENKA-113)
