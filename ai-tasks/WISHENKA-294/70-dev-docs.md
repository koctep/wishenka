# WISHENKA-294: Developer Documentation

## Changed Files

- `doc/dev/miniapp.md`
  - New section "Cross-Screen Comfort and Reliability Layer (WISHENKA-294)" after "Visual Identity
    Browser Verification": layout and touch rules, status and feedback regions, `withPending`,
    htmx pending and failure feedback, the unavailable page (scope, locale, privacy, log event,
    limits).
  - New troubleshooting item 16.
- `doc/dev/i18n.md`: `data-i18n-request-failed`, `web.unavailable.*` namespace, new item 7 with
  the five catalog keys (`nav.working`, `web.common.request_failed`, `web.unavailable.heading`,
  `web.unavailable.description`, `web.unavailable.auth`).
- `doc/dev/testing.md`: new section "Сквозные тесты комфорта и надёжности экранов
  (WISHENKA-294)" (module, assertions A1-A10, `tests/browser_screens.py`, `set_viewport`,
  `clear_cookies`, observability test, run rules, load-sensitive tests) and a pointer under
  "Известные ограничения".
- `doc/dev/architecture.md`: one-clause cross-reference in the `miniapp.md` entry.

## Deviations from `20-architecture.md` Recorded in the Docs

- Root font is `100% system-ui` with no line-height.
- `withPending` takes an optional `message`; `pending()` adapts it to `button()`.
- Quick-add clearance uses `main:has(#quick-add-bar)` with `max(token, 9rem)`.
- The 401 page keeps `WWW-Authenticate` through `headers=exc.headers`.

## Reconciled Stale Statements

Stale statements in `miniapp.md` (root font, select/textarea scope, `<body>` `data-i18n-*` list,
pending cleanup wording) were reconciled with the code.

## Follow-ups Linked

WISHENKA-308 (`PAGE_PATHS` `fullmatch`, `Vary: Accept`, test strength), WISHENKA-309 (`:has()`,
hidden `#feedback`), WISHENKA-310 (duplicated pending logic), WISHENKA-311 (load-sensitive tests),
WISHENKA-312 (create guard after WISHENKA-296).
