# WISHENKA-3: Technical Debt Analysis

## Shortcuts Taken

1. **Python Version Alignment (3.12 vs 3.13)**:
   - The container environment (`Dockerfile`) and CI workflow (`.github/workflows/ci.yml`) are configured for Python 3.12, whereas local development and tests run on Python 3.13. `pyproject.toml` defines `requires-python = ">=3.12"`. While fully compatible at current stage, testing against both versions in CI matrix would ensure no version regressions.
2. **Minimal Healthcheck Endpoint Without Database Ping**:
   - `GET /healthz` returns `{"status": "ok"}` synchronously without probing database connectivity, because the SQLite database models and engine are deferred to subsequent database integration tasks (e.g. WISHENKA-4).
3. **Dummy Bot Token in Docker Compose**:
   - `docker-compose.yml` provides a fallback `WISHENKA_BOT_TOKEN=${BOT_TOKEN:-dummy_bot_token}` for local development, deferring strict runtime validation until the bot engine initialization task.

## Code Quality Issues

1. **StarletteDeprecationWarning with TestClient**:
   - Running `pytest` emits `StarletteDeprecationWarning: Using 'httpx' with 'starlette.testclient' is deprecated; install 'httpx2' instead`. Future refactoring should migrate tests to asynchronous `httpx.AsyncClient(transport=ASGITransport(app=...))` to align with modern FastAPI/Starlette best practices and eliminate deprecation warnings.
2. **Co-location of Lifespan and Web Application Factory**:
   - The lifespan context manager and application factory reside directly in `wishenka.web.app`. As the application grows to incorporate background workers, aiogram bot dispatchers, and database connection pools, lifespan logic should be extracted into a dedicated lifecycle module.

## Missing Tests

1. **Docker Image Build and Container Smoke Test in CI**:
   - GitHub Actions CI (`.github/workflows/ci.yml`) executes `make check` on the host runner, but does not build `Dockerfile` or test running the container image with a curl/healthcheck probe.
2. **Error-Path Observability Tests (Unhandled Exceptions)**:
   - While `test_observability.py` tests JSON formatting and normal request logging middleware, there is currently no test verifying structured error logging when an unhandled exception occurs inside a route handler (caplog contract for 500 status codes).

## Performance Concerns

1. **Request Logging Volume on High-Frequency Healthchecks**:
   - The request logging middleware logs all HTTP requests at `INFO` level. In containerized environments with aggressive health checks (e.g. every 5–10 seconds), this may lead to excessive log volume. A filter or log-level reduction (to `DEBUG`) for `/healthz` should be considered for production.
2. **Dependency Installation Caching in Docker**:
   - `Dockerfile` runs `pip install --no-cache-dir .` without using a lockfile (`uv.lock` or pinned hashes). Using a pinned lockfile would improve reproducible build performance and security auditing.

## Follow-up Tasks

1. **Add Docker Image Build and Smoke Test to GitHub Actions CI**:
   - Jira: [WISHENKA-40](https://pypost.atlassian.net/browse/WISHENKA-40) (2 SP, Priority: Low)
   - Extend `.github/workflows/ci.yml` with a job or step to build the Docker image and verify the `/healthz` endpoint via container healthcheck.
2. **Migrate Test Suite to `httpx.AsyncClient`**:
   - Jira: [WISHENKA-41](https://pypost.atlassian.net/browse/WISHENKA-41) (1 SP, Priority: Low)
   - Replace `starlette.testclient.TestClient` in tests with `httpx.AsyncClient` to resolve Starlette deprecation warnings and natively test async handlers.
3. **Add 500 Error Handler Middleware and Caplog Error-Path Test**:
   - Jira: [WISHENKA-42](https://pypost.atlassian.net/browse/WISHENKA-42) (2 SP, Priority: Low)
   - Implement an exception handler middleware logging 500 errors with traceback and add a corresponding test satisfying the `do-testing` caplog contract.
4. **Optimize Healthcheck Endpoint Logging**:
   - Jira: [WISHENKA-43](https://pypost.atlassian.net/browse/WISHENKA-43) (1 SP, Priority: Low)
   - Add configuration or middleware rule to skip or downgrade request logging for `/healthz` endpoint to reduce log pollution.
