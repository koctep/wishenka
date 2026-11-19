# WISHENKA-177: Technical Debt Analysis

## Shortcuts Taken

1. **Origin and path remapping between bot URL and `BrowserServer` (`tests/test_bot_menu_miniapp_e2e_browser.py:42, 90-93, 153`):**
   - `wishenka.bot.entry._url()` strictly requires an `https://` URL, whereas `BrowserServer` in `tests/conftest.py` listens on `http://127.0.0.1:<port>`.
   - `_extract_bot_menu_queries` configures `mini_app_url="https://example.test/miniapp"` and forwards only `parts.query` to `f"{server.base_url}/?{query}"`, bypassing the `/miniapp` path segment. While `miniapp.js` only inspects `?startapp=...`, this remapping is a test-harness compromise rather than exercising TLS/path parity.

2. **In-process fake bot transport and dummy token (`tests/test_bot_menu_miniapp_e2e_browser.py:35-39, 65`):**
   - `_extract_bot_menu_queries` monkeypatches `Bot.__call__` and uses a synthetic token (`"123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"`) with `SimpleNamespace` dependencies (`mini_app_url`, `wishlist_service`). It does not exercise `user_store` or `wishlist_store` persistence during `/start` (which are covered separately in unit/repro tests).

## Code Quality Issues

1. **Local `initData` signing and REST helper duplication risk (`tests/test_bot_menu_miniapp_e2e_browser.py:97-139`):**
   - `_build_telegram_init_data`, `_set_owner_locale_and_count`, and `_get_owner_wishlist_count` live inside `tests/test_bot_menu_miniapp_e2e_browser.py` and instantiate a new `httpx.Client` per call. If future browser E2E tests need Telegram `initData` signing or locale setup, these helpers should be consolidated into `tests/browser_helpers.py`.

## Missing Tests

1. **`Telegram.WebApp.initDataUnsafe.start_param` launch path (`wishenka/web/static/miniapp.js:569-571`):**
   - `miniapp.js` prioritizes `bridge?.initDataUnsafe?.start_param` over `URLSearchParams(location.search).get('startapp')`. The current browser E2E suite only exercises the URL query parameter (`/?startapp=...`) without a mocked `window.Telegram.WebApp.initDataUnsafe.start_param`.

2. **Distinct `collection` vs `home` routing (`wishenka/web/static/miniapp.js:581-586`):**
   - Currently `home` and `collection` both execute `bootstrap()` + `showHome()`, so the tests assert the same home/collection DOM for both intents. If `collection` is later given a dedicated view or scroll anchor, the test assertions should be updated to distinguish them.

## Performance Concerns

1. **External Telegram WebApp script fallback delay (`wishenka/web/static/miniapp.js:556-564`):**
   - `start()` injects `https://telegram.org/js/telegram-web-app.js` and waits up to 3,000 ms (`setTimeout(resolve, 3000)`) if the request hangs or fails in offline/sandboxed headless Chromium. Across 12 parametrized browser tests, this contributes noticeably to suite runtime (~17.49s for the module).

## Follow-up Tasks

- **Debt (Low):** Consider moving `_build_telegram_init_data` (and REST count/locale helpers in `tests/test_bot_menu_miniapp_e2e_browser.py:97-139`) into `tests/browser_helpers.py` if additional Telegram Mini App browser E2E tests are added. — Jira: [WISHENKA-239](https://pypost.atlassian.net/browse/WISHENKA-239)
- **Debt (Low):** Add a browser test case (or extend existing ones) covering `window.Telegram.WebApp.initDataUnsafe.start_param` precedence in `wishenka/web/static/miniapp.js:569-571`. — Jira: [WISHENKA-240](https://pypost.atlassian.net/browse/WISHENKA-240)
