# WISHENKA-145: Technical Debt Analysis

Scope: `tests/browser_cdp.py` (`_real_htmx_bodies`, `CdpPage.__init__`, `CdpPage.set_cookie`, `CdpBrowser.new_page`), `tests/conftest.py` (`wishlist_server`, `_open_page`, `wishlist_page`), `tests/test_wishlist_htmx_smoke_browser.py` (`test_real_htmx_move_button_with_cookie_and_csrf`), and `tests/test_browser_prerequisites.py` (`test_browser_cdp_urls_match_base_template`). No production code (`wishenka/`) was modified.

Timeout markers check (`do-testing` / `td-60-tech-debt`):

- `tests/test_wishlist_htmx_smoke_browser.py:17`: `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`.
- `tests/test_browser_prerequisites.py:33`: `pytestmark = pytest.mark.timeout(30)`.
- `tests/browser_cdp.py` and `tests/conftest.py`: test driver and fixtures only (no test items).
- Internal waits in `tests/test_wishlist_htmx_smoke_browser.py` (`:38`, `:46`, `:55`) use bounded `page.wait_for(...)` polling.

**Blockers:** none. No timeout-marker or unbounded-wait `Blocker` issues.

## Shortcuts Taken

- **Low — Hardcoded `"session_id"` cookie name in `tests/conftest.py:326`:** `_open_page` passes `"session_id"` literally to `page.set_cookie("session_id", token, url)` instead of reading `Settings().session_cookie_name` (currently `"session_id"` by default in `wishenka/config.py`). If the default cookie name changes, cookie-mode browser tests will fail until updated.
- **Low — Hardcoded vendored `htmx` filenames in `tests/browser_cdp.py:123-128`:** `_real_htmx_bodies()` references `htmx-1.9.12.min.js` and `htmx-json-enc-1.9.12.js` directly, coupled to `HTMX_URL` and `JSON_ENC_URL` (`:38-39`). Upgrading `htmx` in `base.html` will be caught loudly by `test_browser_cdp_urls_match_base_template()`, and requires updating the vendored assets and constants together.
- **Low — `TELEGRAM_URL` remains an empty stub in `_real_htmx_bodies()` (`tests/browser_cdp.py:127`):** intentional per `10-requirements.md` (offline constraint and scope limited to `htmx` + cookie + CSRF).

## Code Quality Issues

- **Low — `accept_language` silently ignored when `auth_mode="cookie"` (`tests/conftest.py:324-329`):** `_open_page` only forwards `accept_language` to `page.set_bearer(token, accept_language=accept_language)` in the `else` branch. If a future test uses `wishlist_page(..., auth_mode="cookie", accept_language="...")`, `Accept-Language` will not be set on the tab.
- **Low — Fragile `<script src="...">` regex in `tests/test_browser_prerequisites.py:560`:** `re.findall(r'<script\s+src="(https://[^"]+)"', base_html)` assumes `src` is the first attribute after `<script` and uses double quotes. Adding an attribute before `src` (e.g., `<script defer src="https://...">`) would cause a false mismatch.
- **Low — `CdpPage.set_cookie` defaults `result.get("success", True)` (`tests/browser_cdp.py:192`):** defaulting to `False` would be stricter if CDP `Network.setCookie` ever omitted the `"success"` key; also `wishlist_page` docstring signature (`tests/conftest.py:337`) omits `auth_mode` and `use_real_htmx` (though the docstring body describes them).

## Missing Tests

- **Low — Single smoke scenario only (intentional scope boundary):** `test_real_htmx_move_button_with_cookie_and_csrf` covers `hx-post` move-down, `GET /api/auth/csrf`, `htmx:configRequest` (`X-CSRF-Token`), `#items-list` `innerHTML` swap, and reload persistence. Other `hx-*` flows (e.g., `json-enc` modal/form submissions, reserve/unreserve, move-up) and the existing 53 `WISHENKA-110` browser tests continue to use `htmx_stub.js` and `Bearer` auth, which is an explicit Non-Goal in `10-requirements.md`.
- **Low — Browser-level negative CSRF / Origin rejection path:** not exercised in Chromium (covered by server-side FastAPI/middleware tests).

## Performance Concerns

- **None:** `_real_htmx_bodies()` reads two small local files (`htmx-1.9.12.min.js` ~48 KB, `htmx-json-enc-1.9.12.js` ~356 B) once per `CdpPage(..., use_real_htmx=True)` instantiation with zero network calls.

## Follow-up Tasks

Pre-existing test failures: none found, so no `NON-BLOCKER — pre-existing` entries.
There are no `Blocker`, `High`, or `Medium` items.

1. **Low (`NON-BLOCKER`, `status: unticketed`):** In `tests/conftest.py` (`_open_page`), forward `accept_language` via `Network.setExtraHTTPHeaders` even when `auth_mode == "cookie"`, and read the session cookie name from `Settings().session_cookie_name` instead of hardcoding `"session_id"`.
2. **Low (`NON-BLOCKER`, `status: unticketed`):** In `tests/test_browser_prerequisites.py` (`test_browser_cdp_urls_match_base_template`), widen the `<script>` attribute regex to `r'<script\b[^>]*\bsrc="(https://[^"]+)"'` (or parse with `html.parser`) so attributes before `src` (such as `defer`) do not break the URL guard.
