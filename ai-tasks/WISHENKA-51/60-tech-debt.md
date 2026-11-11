# WISHENKA-51: Technical Debt Analysis

## Shortcuts Taken

1. **Hardcoded Inline Russian Strings in Templates and Responses**:
   All UI labels, button texts, role descriptions, and success messages are hardcoded directly
   in Russian inside Jinja2 templates and route responses
   (e.g., "Вы успешно присоединились к вишлисту"),
   deferring formal localization integration (gettext / Babel).
2. **Synchronous Template Rendering in Async Endpoints**:
   `templates.TemplateResponse` executes synchronous template compilation and rendering directly
   in the async route handlers. While negligible for current HTML fragment sizes, under heavy
   traffic it can introduce minor event-loop micro-delays.
3. **Basic Inline Error Presentation**:
   HTMX error handling uses inline error cards and standard HTTP status codes rather than a
   centralized toast/notification banner system on the client.

## Code Quality Issues

1. **Scattered Role and Status Label Translations**:
   Role display labels (e.g. Owner, Admin, Member in Russian) and reservation badges are
   defined separately in `wishenka/web/static/miniapp.js` and Jinja2 template partials
   (`member_list.html`, `item_card.html`), risking presentation inconsistency across views.
2. **Missing Client-Side HTMX Global Event Hooks**:
   `base.html` includes `htmx.org` but does not configure global HTMX event handlers
   (e.g., `htmx:responseError`, `htmx:timeout`, `htmx:sendError`) to inform users via toasts
   when network or authorization errors occur during partial swaps.

## Missing Tests

1. **Live Browser HTMX DOM Interaction Tests**:
   Existing tests thoroughly validate HTML responses, headers (`HX-Redirect`), status codes,
   and Surprise Invariant constraints via FastAPI `TestClient`, but do not execute live DOM
   swaps in a headless browser (e.g., Playwright) with client-side JavaScript.
2. **Rate Limiting and Abuse Prevention Tests**:
   Because rate limiting is not yet active on `/share/{token}` and `/invite/{token}`, tests
   verifying token request throttling under burst enumeration are absent.

## Performance Concerns

1. **Uncached Jinja2 Template Parsing**:
   `wishenka/web/templates.py` initializes `Jinja2Templates` with default `FileSystemLoader`
   without `FileSystemBytecodeCache`. In high-throughput production environments, repeated
   file-system stats and template re-compilations add avoidable CPU overhead.
2. **Susceptibility to Token Enumeration and Denial of Service**:
   Public endpoints `/share/{token}` and `/invite/{token}` do not enforce IP/user rate limits,
   leaving them open to automated crawler scanning or token-probing bursts.
3. **Absence of HTTP Cache Headers for Static Assets and Shared Views**:
   Public share views do not emit `ETag` or `Cache-Control: private, must-revalidate` headers,
   forcing full HTML regeneration on every reload.

## Follow-up Tasks

### DEBT-W51-1: Jinja2 Bytecode Caching and Template Compilation Optimization
- **Jira Issue**: [WISHENKA-87](https://pypost.atlassian.net/browse/WISHENKA-87)
- **Estimate**: 1 Story Point
- **Description**: Configure `jinja2.FileSystemBytecodeCache` in `wishenka/web/templates.py` for
  production environments to eliminate disk reads and template compilation overhead on repeated
  page renderings.
- **Impact / Severity**: Low. Improves server throughput under high concurrency.
- **Priority**: Low.
- **Blocker Status**: Non-blocker for WISHENKA-51.
- **Suggested Remediation**: Initialize `FileSystemBytecodeCache(directory=".cache/jinja2")`
  when running in non-debug mode.

### DEBT-W51-2: Rate Limiting on Public Capability URLs (/share, /invite)
- **Jira Issue**: [WISHENKA-88](https://pypost.atlassian.net/browse/WISHENKA-88)
- **Estimate**: 3 Story Points
- **Description**: Implement rate limiting middleware (e.g., slowapi or Redis token-bucket) on
  unauthenticated capability endpoints `/share/{token}` and `/invite/{token}` to guard against
  token enumeration attacks and brute-force scanning.
- **Impact / Severity**: Medium. Prevents abuse and excessive database queries from scanners.
- **Priority**: Medium.
- **Blocker Status**: Non-blocker for WISHENKA-51.
- **Suggested Remediation**: Add rate limiting decorators limiting anonymous IP access to
  e.g. 60 requests per minute per IP.

### DEBT-W51-3: Template Internationalization (i18n / gettext) for Mini App Views
- **Jira Issue**: [WISHENKA-89](https://pypost.atlassian.net/browse/WISHENKA-89)
- **Estimate**: 3 Story Points
- **Description**: Integrate standard gettext / Babel localization in FastAPI and Jinja2 templates
  so that role labels, button titles, and error messages can be translated according to the user's
  Telegram interface language (`Telegram.WebApp.initDataUnsafe.user.language_code`).
- **Impact / Severity**: Low. Enables multi-language support for international audiences.
- **Priority**: Low.
- **Blocker Status**: Non-blocker for WISHENKA-51.
- **Suggested Remediation**: Add Jinja2 `i18n` extension and load `.po`/`.mo` message catalogs
  based on user locale.

### DEBT-W51-4: Unified HTMX Client-Side Error Toast & Notification System
- **Jira Issue**: [WISHENKA-90](https://pypost.atlassian.net/browse/WISHENKA-90)
- **Estimate**: 2 Story Points
- **Description**: Implement a global HTMX event listener in `miniapp.js` or `base.html` that
  intercepts `htmx:responseError`, `htmx:sendError`, and custom `HX-Trigger` events to display
  unified, accessible toast banners for background partial failures.
- **Impact / Severity**: Low. Improves user experience and perceived responsiveness on errors.
- **Priority**: Low.
- **Blocker Status**: Non-blocker for WISHENKA-51.
- **Suggested Remediation**: Add toast container in `base.html` and attach HTMX error event
  listeners in `miniapp.js`.

### DEBT-W51-5: Headless Browser E2E Tests for HTMX Partial Swaps and Telegram Bridge
- **Jira Issue**: [WISHENKA-91](https://pypost.atlassian.net/browse/WISHENKA-91)
- **Estimate**: 5 Story Points
- **Description**: Create end-to-end integration tests using Playwright to verify client-side
  DOM replacement, modal interactions, and Telegram WebApp clipboard/sharing triggers.
- **Impact / Severity**: Low. Provides additional confidence in client-side script execution.
- **Priority**: Low.
- **Blocker Status**: Non-blocker for WISHENKA-51.
- **Suggested Remediation**: Add Playwright test suite covering interactive HTMX workflows.

## Blocker Review

None of the identified technical debt items block closing WISHENKA-51.
All acceptance criteria and Definition of Done items from `10-requirements.md` are completely met.
All 193 automated tests in the test suite pass with explicit timeouts.
