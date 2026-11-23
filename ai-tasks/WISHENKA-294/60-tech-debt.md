# WISHENKA-294: Technical Debt Analysis

No blockers were found. The acceptance criteria of `10-requirements.md` are covered by
`tests/test_cross_screen_comfort_browser.py` (48 of 48 pass) and the unit and observability
tests. All items below are NON-BLOCKER follow-ups; none prevents shipping this task.

## Shortcuts Taken

- The unavailable page covers only three GET routes (`wishenka/web/unavailable.py:19`,
  `PAGE_PATHS`: `/share/<token>`, `/web/wishlists/<id>`, `/web/reservations`). This is the
  designed scope (`20-architecture.md`, L6): sub-paths, `/api`, htmx and unknown routes stay
  JSON. Other server-rendered pages that can answer 404/401 would still show JSON. Not a defect,
  recorded so a future page does not forget to extend the regex.
- The "Create wishlist" `withPending` guard (defined at `wishenka/web/static/miniapp.js:87`, applied
  through `pending()` at the create call site, `miniapp.js:379`) is scoped to today's flow
  (`POST /api/wishlists {}` on click). The sprint
  bug WISHENKA-296 changes that flow (see `20-architecture.md`, L5 scope note and D6). Whoever
  lands it second must re-check the guard and assertion A6 for the create button. NON-BLOCKER:
  the guard is correct for the current flow and the other `withPending` targets are unaffected.
- Visual constants are hard-coded: `+ 16` clearance in `wishenka/web/static/app.js`
  (`trackQuickAddClearance`), the `9rem` fallback in `miniapp.css:326`, and the grey literals
  `#666`, `#555`, `#15803d` (`miniapp.css:446`, `:451`, `:454`) that are not design tokens.
  Cosmetic; contrast is covered by the A8 browser checks.

## Code Quality Issues

- Duplicated pending/feedback logic. `withPending()` and `status()` in `miniapp.js:79-103`
  (Mini App, `fetch`) and the `htmx:beforeRequest` / `releasePending` / `showRequestFailure`
  block in `app.js` (server pages, htmx) implement the same idea twice: busy attribute,
  disabled controls, a localized message, restore on completion. Impact: a change to the
  wording, the `data-kind` contract or the release rules must be made in two places. Fix: none
  needed now; if a third surface appears, extract a shared module.
- `app.js` registers a second `DOMContentLoaded` listener for `trackQuickAddClearance` beside
  the existing block. Cosmetic.
- `PAGE_PATHS` (`unavailable.py:19`) uses `^...$` with `.match`. In Python `$` also matches
  before a trailing newline, so a decoded path ending in `\n` is treated as a page URL and gets
  HTML instead of JSON. Use `fullmatch` (or `\Z`).
- `main:has(#quick-add-bar)` (`miniapp.css:326`) needs Chromium 105+ / Safari 15.4+. In an older
  Telegram WebView the rule is ignored and the content gets no bottom clearance, so the last
  card can sit under the fixed bar (the D3 defect returns there). Fix: set a class on `main`
  from `trackQuickAddClearance`, or move the padding to a rule that does not need `:has()`.
- `#feedback` is a `role="alert"` region hidden with `#feedback:empty { display: none }`
  (`miniapp.css:83`). Text inserted into a region that was `display: none` a
  moment earlier may not be announced (unverified; the region is `role="alert"
  aria-live="assertive"`, `base.html:24`). Fix: keep the region rendered and visually hidden when
  empty (clip, 1 px) instead of `display: none`, and check with a screen reader.

## Missing Tests

- `tests/test_cross_screen_comfort_browser.py:90`: `D4_SUSPECTS = ("a.item-link", "select ",
  "a ", "summary ")` and the control test (`:416`) skip lines by `startswith`. Entries are
  `<tag#id.class> WxH` (`label()` in `tests/browser_screens.py:292`), so bare `"a "`,
  `"select "` and `"summary "` skip only classless elements; other elements need an exact
  match. The suspects are matched loosely (any classless anchor, select or summary is
  skipped), so the control is weaker than documented. Fix: match the exact selectors of the
  four suspects. Also, `GEOMETRY_JS` caps `undersized` with `.slice(0, 12)`
  (`browser_screens.py:323`), which can truncate a report.
- `tests/test_unavailable_page_observability.py` never asserts the logged `locale` value
  (the docstring promises "kind/status/locale") and has no case for a request without
  `Accept-Language` or with `ru`. Fix: assert `extra["locale"]` for `en` and `ru` requests.
- No test for the `PAGE_PATHS` newline case or for the `_locale` fallback branch
  (`unavailable.py:57`, lookup failure falls back to `Accept-Language`).

## Performance Concerns

None. The `ResizeObserver` in `app.js` observes one element and writes one custom property. The
exception handler adds one regex match per HTTP error. The browser module has 48 cases, each
opening pages at several widths, so it is the slowest part of the added tests (see follow-up 4).

## Follow-up Tasks

1. **Minor cleanup of the unavailable page and new tests: `fullmatch` for `PAGE_PATHS`, assert
   the logged `locale` (en/ru/no header), cover the `_locale` fallback, tighten
   `D4_SUSPECTS` to exact selectors, merge the second `DOMContentLoaded` listener; add
   `Vary: Accept` to both branches of
   `handle_http_exception` (`unavailable.py:64-90`), which serves HTML or JSON for the same
   URL depending on `Accept` and risks a shared-cache mix-up.**
   NON-BLOCKER (hardening and test strength only; no acceptance criterion depends on it),
   priority Low. Jira: [WISHENKA-308](https://pypost.atlassian.net/browse/WISHENKA-308).
2. **Make quick-add clearance and the feedback region robust in old WebViews and screen
   readers: replace `main:has(#quick-add-bar)` with a class set from JS, and replace
   `#feedback:empty { display: none }` with a visually hidden empty state; verify the alert is
   announced.** NON-BLOCKER (the target WebViews are modern Chromium; the screen-reader
   concern is unverified), priority Medium.
   Jira: [WISHENKA-309](https://pypost.atlassian.net/browse/WISHENKA-309).
3. **Remove the duplicated pending/feedback logic between `miniapp.js` and `app.js`
   (shared module) and move hard-coded colors and the `16`/`9rem` clearance to tokens; the
   htmx failure text in `app.js:561-562` is an English fallback duplicating
   the catalog key `web.common.request_failed`.**
   NON-BLOCKER (maintainability only), priority Low.
   Jira: [WISHENKA-310](https://pypost.atlassian.net/browse/WISHENKA-310).
4. **Stabilize load-sensitive browser tests.**
   `tests/test_cross_screen_comfort_browser.py::test_htmx_pending_request_marks_the_form_busy`
   (3 s `WAIT`, line 88) and
   `tests/test_history_screen_browser.py::test_control_opening_an_entry_moves_it_to_the_top...`
   fail only under parallel load and pass serially (observed in Step 4 runs by the
   development subagent; not recorded in the roadmap). Fix: wait on a condition
   with a longer bound or hold the request deterministically; keep `make test-serial` as the
   reference. NON-BLOCKER (passes serially; the failure is timing, not behavior), priority
   Medium. Jira: [WISHENKA-311](https://pypost.atlassian.net/browse/WISHENKA-311).
5. **Re-check the create-wishlist guard and assertion A6 after WISHENKA-296 changes the create
   flow.** NON-BLOCKER (the guard matches the current flow), priority Medium. Linked by key in
   the sprint, not a new defect.
   Jira: [WISHENKA-312](https://pypost.atlassian.net/browse/WISHENKA-312).

### Pre-existing test failures

The full-suite run showed only failures that are not caused by this task and that pass or fail
the same way on the base commit (see Step 4 triage in `00-roadmap.md`). The ids and Jira keys
are recorded in `ai-tasks/WISHENKA-292/60-tech-debt.md`; no duplicates are needed here.
