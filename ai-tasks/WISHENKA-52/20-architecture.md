# WISHENKA-52: Nonblocking HTML metadata extraction

## Research

- `ItemPreviewService.fetch_preview` in `wishenka/items/service.py` and
  `UrlMetadataService.fetch_and_extract` in `wishenka/items/fetcher.py` each call the same
  synchronous `HtmlMetadataExtractor.extract` after the existing protected fetch. Their local
  exception handlers implement different fallback results and must remain in place.
- The parser uses BeautifulSoup with `html.parser`. Replacing it risks changing malformed HTML
  interpretation and extraction results. Existing tests in `tests/test_metadata_extractor_service.py`
  exercise metadata precedence, stores, fallbacks, and logging.
- Python's [`asyncio.to_thread`](https://docs.python.org/3.12/library/asyncio-task.html#asyncio.to_thread)
  moves synchronous work off the event-loop thread and propagates context variables. CPython's GIL
  limits CPU parallelism: thread offload allows loop scheduling but does not guarantee a latency
  bound under CPU saturation. A process pool can bypass the GIL but requires serialization and
  lifecycle management; see [Python's process pool documentation](https://docs.python.org/3.12/library/concurrent.futures.html#processpoolexecutor).
  Given the existing pure Python parser and unchanged output requirement, start with thread offload,
  verify actual responsiveness with a heavy document, and reconsider isolation if measurement fails.

## Implementation Plan

1. Before production changes, implement the failing tests described below and establish that each
   fails on the synchronous calls for the intended reason.
2. Await `asyncio.to_thread(HtmlMetadataExtractor.extract, html_text, base_url=final_url)` at both
   call sites, using `response_url` for preview. Keep each await inside its existing `try` block.
   The synchronous extractor, output DTOs, fetch, SSRF checks, byte limits, anti-bot detection,
   and local error handling remain unchanged. The default executor is shared and has bounded worker
   count; queueing and CPU contention remain possible under many concurrent heavy requests.
3. Run the red tests, existing metadata and security tests, and project quality gate. Assess real
   heavy-page responsiveness as well as deterministic scheduling. Document executor and cancellation
   behavior for developers. A cancelled await does not forcibly terminate a running thread.

### Failing repro for Step 3

Add async tests in `tests/test_metadata_extractor_service.py` for each public async entry point.
Mock the existing fetch layer with an HTML body larger than 1 MiB, without real network access.
Replace the extractor with a controlled synchronous function using bounded `threading.Event` waits:
mark entry, wait for a release signal, then return representative metadata. Schedule a concurrent
light coroutine after extraction starts and require it to complete before release; release in cleanup
and use explicit timeouts. The original inline call stalls the loop and fails a bounded independent
release/ordering check; the offloaded call permits the light coroutine to run. Ensure the fixture
cannot hang even on the original code (for example, use an independently timed helper thread).
Assert returned metadata and verify exceptions still reach each existing fallback handler.

Also exercise the real extractor on a representative >1 MiB HTML fixture alongside a lightweight
loop task, with a generous documented latency bound and bounded waits. This checks actual GIL
contention rather than assuming the controlled blocking function represents CPU work. Preserve the
existing extraction corpus as the parity regression suite. Research precedes red tests, which precede
production fixes; confirm intended failure before implementing and green afterward.

## Architecture

```text
Preview request                       URL metadata request
       |                                      |
       v                                      v
ItemPreviewService                    UrlMetadataService
       |                                      |
       +---------- protected async fetch -----+
                      |
                      v
          asyncio.to_thread on default executor
                      |
                      v
          HtmlMetadataExtractor.extract (unchanged)
                      |
                      v
        existing result mapping / local fallback
```

The services depend on the standard library's async executor boundary and the existing parser. The
fetcher retains network and SSRF ownership. The extractor remains a synchronous pure interface from
HTML and base URL to `ExtractedMetadata`; its callers asynchronously await the same result. Each
caller retains its own error handler and public return contract. No new external dependency or API
is introduced. Thread offload avoids a parser replacement and preserves parser logging in process.

## Q&A

- **Why not switch parser libraries?** Their HTML recovery behavior can alter metadata; the task
  explicitly requires unchanged extraction.
- **Is CPU parallelism guaranteed?** No. The GIL and executor saturation can increase latency;
  the heavy-document test validates the required responsiveness under its defined workload.
- **What happens on extraction errors?** The exception is raised at the await and the existing
  per-service fallback remains responsible for the result.
- **What about cancellation?** Cancelling the await cannot stop an already running worker; no
  new timeout or retry policy is introduced by this change.
