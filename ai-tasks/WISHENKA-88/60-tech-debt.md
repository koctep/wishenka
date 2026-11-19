# WISHENKA-88: Technical Debt Analysis

## Shortcuts Taken

1. **Process-local in-memory rate-limit store (`wishenka/web/rate_limit.py`)**:
   - `SlidingWindowRateLimiter` keeps client timestamps in an in-memory `OrderedDict[str, deque[float]]` on `app.state.public_link_rate_limiter`.
   - This is intentional for the current single-process SQLite WAL deployment and avoids I/O overhead on allowed requests, but it does not share counters across multiple worker processes.
2. **Inline HTML 429 body in `_build_rate_limit_response` (`wishenka/web/rate_limit.py`)**:
   - `_build_rate_limit_response` constructs a minimal standalone HTML5 document with `html.escape(...)` instead of rendering a Jinja2 template, and returns the same full HTML document even for HTMX requests (`HX-Request: true` from `POST /invite/{token}/join`).
3. **`HEAD` requests not matched by `match_public_link_route` (`wishenka/web/rate_limit.py`)**:
   - `match_public_link_route` only matches `GET` for `/share/{token}` and `/invite/{token}` (and `POST` for `/invite/{token}/join`). Because FastAPI/Starlette automatically serves `HEAD` on `GET` routes, `HEAD /share/{token}` or `HEAD /invite/{token}` can probe token existence (`200` vs `404`) without hitting the rate limiter.
4. **Leftmost `X-Forwarded-For` parsing (`resolve_client_ip`)**:
   - When `public_rate_limit_trust_proxy_headers=True`, `resolve_client_ip` takes the leftmost IP from `X-Forwarded-For`. If an upstream proxy appends rather than overwrites `X-Forwarded-For`, a client can still spoof the leftmost value.

## Code Quality Issues

- **Scope boundary with JSON public endpoints**: `wishenka/web/routes/wishlists.py` exposes unauthenticated public JSON endpoints (`/api/public/wishlists/{token}`, `/api/public/wishlists/{token}/view`, `/api/public/wishlists/{token}/items/{item_id}/reservations`) that were outside WISHENKA-88's scope (`/share/{token}`, `/invite/{token}`, `/invite/{token}/join`) and remain unthrottled.
- **No `threading.Lock` on `SlidingWindowRateLimiter`**: Safe in single-threaded `asyncio` because `check_and_record` contains no `await`, but would require synchronization if ever invoked from worker threads.

## Missing Tests

All 10 tests in `tests/test_public_link_rate_limit.py` have explicit `pytest.mark.timeout(30)` markers (no timeout-marker blocker). Minor coverage gaps:
- `X-Real-IP` fallback in `resolve_client_ip` when `trust_proxy_headers=True` and `X-Forwarded-For` is absent.
- `resolve_client_ip` fallback to `"unknown"` when `request.client is None`.
- `HEAD /share/{token}` and `HEAD /invite/{token}` handling (currently bypassed; see Shortcuts Taken #3).
- Trailing-slash / multi-segment path edge cases in `match_public_link_route`.

## Performance Concerns

- **`_evict_expired` full scan at capacity (`wishenka/web/rate_limit.py`)**: When `len(self._buckets) >= self._max_clients` (default `10000`), `_evict_expired(cutoff)` iterates over all tracked buckets in `O(max_clients)` time on the request path. Acceptable at `10000` entries, but if `public_rate_limit_max_clients` is raised significantly, incremental or periodic cleanup would be preferable.
- **Single-process scaling**: Scaling to multiple Uvicorn/Gunicorn workers multiplies the effective rate limit by the number of workers unless backed by a shared store (SQLite/Redis).

## Follow-up Tasks

- **Include `HEAD` in `match_public_link_route` and add unit tests** (`Priority: Medium`, Jira: [WISHENKA-228](https://pypost.atlassian.net/browse/WISHENKA-228)): Treat `HEAD` identically to `GET` for `/share/{token}` and `/invite/{token}` in `wishenka/web/rate_limit.py` so token-probing via `HEAD` cannot bypass rate limiting, and add tests for `HEAD`, `X-Real-IP`, and `request.client is None`.
- **Rate-limit `/api/public/wishlists/{token}*` JSON endpoints** (`Priority: Low`, Jira: [WISHENKA-229](https://pypost.atlassian.net/browse/WISHENKA-229)): Evaluate applying `PublicLinkRateLimitMiddleware` (or a dedicated policy) to `/api/public/wishlists/{token}*` routes in `wishenka/web/routes/wishlists.py`.
- **HTMX-friendly 429 fragment & proxy-hop configuration** (`Priority: Low`, Jira: [WISHENKA-229](https://pypost.atlassian.net/browse/WISHENKA-229)): Return an HTMX-compatible 429 fragment for `HX-Request: true` on `POST /invite/{token}/join`, and consider supporting rightmost untrusted IP extraction if deployed behind proxies that append to `X-Forwarded-For`.
