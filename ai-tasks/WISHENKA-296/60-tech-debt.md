# WISHENKA-296: Technical Debt Analysis

No blockers were found. `POST /api/wishlists` now requires a trimmed title of 1-255 code points
(`WishlistCreateInput`, `wishenka/web/routes/wishlists.py:43-55`); the Mini App creates a list only
from an explicit confirmation of the new creation form (`showCreate`, `miniapp.js:378`), leaving or
cancelling creates nothing, and a single request is guaranteed by `withPending(createBtn, ...)`
(`miniapp.js:533`). Reviewed: the diff of `routes/wishlists.py`, `static/miniapp.js`,
`static/miniapp.css`, `i18n/catalog.py`, the four `tests/test_wishlist_create_*.py` modules and the
updated existing tests, `40-code-cleanup.md`, `50-observability.md` and risks R-1..R-10 of
`20-architecture.md`. All new test modules carry `pytest.mark.timeout` (30 / 20 / 45 / 30). Every
item below is NON-BLOCKER.

Interaction with the known access-model leak (WISHENKA-302 favorites, WISHENKA-303 history): none.
Creation touches neither favorites nor history; the new list is private to its owner until shared,
and the change adds no read path. Not a blocker.

## Shortcuts Taken

- **S-1 `api()` stores `err.body` only for 422; the real defect is a weak wait in another test**
  (Low, confirmed). `miniapp.js:120-123` parses the body only for status 422 (design R-10 said
  every error). Reason recorded in Step 4: parsing the body on a 500 delayed the failure enough to
  break `tests/test_history_screen_browser.py::test_load_failure_shows_alert_and_retry_recovers[500]`.
  Evidence: that test waits (`:643-647`) on `!!.history-error || #status.innerText.trim() !== ''`,
  which accepts any non-empty status, including the transient "Loading" text, and then asserts
  `role == "alert"` immediately (`:655`), so it races with the render. The shortcut in `api()` is
  harmless and arguably right (only the 422 mapping needs a body), but a future reader will not
  know why other statuses are excluded, and the weak wait hides the same race for any later change
  of timing. Fix: wait for the `.history-error` element itself (drop the `or status` branch, or
  require the status to equal the failure text) and keep a one-line comment in `api()` (exists:
  `:121`). Test-only change; closes the root cause.
- **S-2 Title rule exists only in the create validator; PATCH, invisible characters and optional
  fields are open** (Medium, confirmed, R-8).
  (a) `WishlistCreateInput` does cap the title at 255 (trimmed, 1-255 code points,
  `wishlists.py:43-55`), but there is no DB length constraint on the title, so 255 is enforced only
  there. `WishlistInput` (`:34-40`, `name: str | None`) still backs the settings `PATCH` (`:472`),
  so a list can be renamed to blank or to any length. Whether "title required" also covers editing
  is a product-owner decision; PATCH-to-blank is accepted as debt, not a requirement gap, because
  requirements 2-3 are about creation.
  (b) Only `description` and `event_title` are unbounded, at creation on both the client
  (`miniapp.js:430-460`, no `maxlength`, `validate()` checks only title and date) and the server.
  (c) Invisible-only titles (MEDIUM, missed earlier): Python `str.strip()` and JS `trim()` do not
  remove zero-width, format or control characters (U+200B, U+2060, U+FEFF, RTL marks). A title made
  only of them passes the 1-255 validation and renders blank, because the
  `list.name || t('miniapp.common.untitled_wishlist')` fallback (`miniapp.js:212, 647, 683, 759,
  950, 1050`) does not trigger on a non-empty string. There is no Unicode normalization either.
  Fix: reject (or strip) invisible-only titles in `WishlistCreateInput` and in `validate()`
  with the same rule, and use it in the shared contract below.
  Fix for (a)/(b): one shared validator for title and agreed maxima for description and event
  title on create and PATCH (if the product owner extends the rule), mirrored in the forms.
- **S-3 Lost response or proxy 502/504 after a committed creation can still produce a duplicate
  list** (Medium, confirmed, F6 / R-2). `POST /api/wishlists` has no idempotency key; the
  `withPending` guard covers taps and Enter in one page instance only, not a retry after a lost
  response. Accepted knowingly in design, documented, not solved. Fix: an optional
  `Idempotency-Key` header (client generates one per opened form, reused on retry) with a short
  server-side dedupe table or in-memory TTL map keyed by `(user_id, key)` returning the first
  result; test with a forced lost response.
- **S-4 Existing empty untitled lists are not cleaned up** (Low, D4). Lists created by the former
  automatic creation (`body: '{}'`) remain with an empty title. The owner can now delete them
  through WISHENKA-295, so no data risk. Fix, only if product wants it: a one-off migration or a
  home hint for untitled empty lists; otherwise leave as is. Folded into follow-up 1 (S-2 touches
  blank titles).

## Code Quality Issues

- **C-1 `mapFailure` reports "title required" for any 422 on `name`** (Low, confirmed).
  `miniapp.js:465-480` maps every `loc` ending in `name` to `miniapp.create.error_title_required`,
  even when the server rejected a too-long title. It is a safety net only: the client limit
  (`MAX_TITLE = 255`, code points) equals the server limit, so a mismatch arises only through the
  R-3 edge cases (`trim()` vs `strip()` on a few Unicode spaces). Then the user sees a wrong
  message for a title that is not empty. Fix: map by the pydantic error `type` or `msg`
  (`string_too_long` / the validator message) to `error_title_too_long`, or ship the limit from the
  server; add a browser or Node test with a crafted 422.
- **C-2 Minor leftovers in the new JS and tests** (Low, confirmed).
  (a) `clearFieldError` (`miniapp.js:417-418`) sets `err.textContent = ''` and then calls
  `wraps[name].removeChild?.(err)`; the text reset is redundant after removal and the `?.` exists
  only because the Node fake DOM lacks `removeChild` (D-3). Fix: use `err.remove()` if the harness
  gets it, or keep one of the two with a comment.
  (b) `tests/test_wishlist_create_form_ui.py:167` and
  `tests/test_wishlist_create_form_browser.py:92` carry the stale docstring "a key Step 4 has not
  added yet reads as a marker, not an error"; Step 4 added all eight `miniapp.create.*` keys, so
  the fallback marker and the sentence are dead. Fix: look the key up strictly (a missing key
  should fail the test) and drop the clause.
  (c) Duplicated helpers: `_table` (`..._form_ui.py:151`, `..._form_browser.py:87`),
  `_create_text` / `_text` (`..._form_ui.py:171`, `..._form_browser.py:91,99`) and `_open_form`
  (`..._form_ui.py:260`, `..._form_browser.py:149`) differ only slightly. Fix: move the catalog
  lookup helpers to a shared test helper module (`tests/browser_screens.py` or a small
  `tests/_catalog.py`); keep the per-harness `_open_form` separate if the implementations differ
  (Node vs CDP), but name them differently.
- **C-3 `showCreate` is a 165-line closure** (Low). `miniapp.js:378-541` mixes field building,
  validation, payload, failure mapping and submit. It works and is tested, but the local `inputs`,
  `wraps`, `errors` triple repeats the settings form (`showSettings` form of WISHENKA-291/307).
  Fix, when the next form arrives: extract a small field-with-error helper shared by the settings
  and creation forms. No separate ticket; grouped into follow-up 1 only if S-2 changes both forms.

## Missing Tests

- **T-1 No test pins "422 for a too-long title maps to a correct message"** (Low, goes with C-1).
  The browser tests cover blank title and invalid date; the 422-after-valid-client case (R-3) is
  covered only for the generic mapping.
- **T-2 No test for PATCH keeping the old permissive behaviour or for a decision on it** (Low, goes
  with S-2). The tests state creation rules only; when S-2 is fixed the rule needs tests on both
  routes.
- **T-3 Chromium-only browser run** (Low). Same limitation as WISHENKA-307 and R-4: `novalidate`
  custom errors, `datetime-local` tab stops and `aria-invalid` styling are not exercised in
  WebKit or Gecko. Covered by the scope of WISHENKA-313 (cross-browser check); add the creation
  form to its list.
- **T-4 Accessibility-tree test uses a private CDP call** (Low). `tests/test_wishlist_create_form_browser.py:793`
  calls `page._send("Accessibility.getFullAXTree")  # noqa: SLF001`. Same pattern as WISHENKA-295
  T-1, which WISHENKA-319 already covers (public `page.accessibility_tree()` helper in
  `tests/browser_screens.py`). No new ticket: add this call site to the scope of WISHENKA-319.
- **T-5 `caplog` setup errors under `-p no:logging`** (Low, pre-existing pattern). The tests that
  use `caplog` (`tests/test_wishlist_api.py:21`, `tests/test_wishlist_management_ui.py:130`, and
  the new observability module) error at setup when pytest runs with `-p no:logging`; the
  repository's configured runs do not disable the plugin (no `no:logging` found in
  `pyproject.toml` or `Makefile`), so this is only a run-mode caveat. Not introduced here; no
  ticket, noted for completeness.

## Performance Concerns

None. One POST per creation, no polling; the form is plain DOM with one `input` listener per field.
The extra `homeRenderToken` checks in `showHome` (`miniapp.js:566,716,719`) are O(1). The full
suite takes about 64 minutes (`make test-serial`); `make test` (xdist) is the working path. That is
a repository-level cost, not introduced here (the four new modules add roughly one minute), so no
ticket.

## Observability and Data Notes

- **O-1 No dedicated server signal for a rejected creation** (Low, accepted in D-7 of the
  architecture). A 422 appears only in the request-completed line; there is no global
  `RequestValidationError` handler (`50-observability.md`, "Deliberately not added"). Counting is
  possible from the access line; a handler would change every route and the 422 body shape. Fix
  when a global validation handler is introduced for another reason; no ticket now.
- **O-2 The service `wishlist_created` record logs the user-entered `event_date`**
  (`wishenka/wishlists/service.py:646`, pre-existing, unchanged). Low-sensitivity data and useful
  for diagnosing date handling; titles, descriptions and event titles are not logged. Fix, if the
  privacy position tightens: log a boolean `has_event_date`. No ticket.

## Product Decision (not code debt)

- **D-1 Reversal of spec 4.2 / UC-01 and new required title** (needs product-owner confirmation,
  non-blocker; the owner also decides whether "title required" covers editing via PATCH, see S-2). Decisions D1 (no automatic empty list; explicit confirmation of a form) and D2
  (title becomes required) were taken autonomously in the run. They contradict the "automatic empty
  list" rule of `in-docs/spec.md` 4.2 and `doc/dev/miniapp.md`. The design is reversible
  (relaxing `WishlistCreateInput` is enough, R-1). Fix: the product owner confirms or rejects; if
  confirmed, Step 8 updates `in-docs/spec.md` and `doc/dev/miniapp.md`. Recorded in the Jira
  comment of this task, not as a Debt ticket.

## Overlap with Existing Jira Debts

- **WISHENKA-312** (re-check the create-button guard and A6 after 296, To Do): the intent is
  already retained by this task. The guard is now `withPending(createBtn, ...)` on the form submit
  (`miniapp.js:533`), shared by taps and Enter, plus `submitting` and `setBusy`; A6 is carried by
  `test_enter_and_tap_burst_sends_exactly_one_post` and `test_real_tap_burst_sends_exactly_one_post`
  (`tests/test_wishlist_create_form_browser.py:546,583`), and the old
  `test_create_wishlist_burst_sends_a_single_post` was moved to the form's Create button in
  `tests/test_cross_screen_comfort_browser.py`. What remains for 312: confirm the 422 and failure
  paths re-enable the form (covered, `setBusy(false)` at `:535`), decide whether the idempotency
  key (S-3) belongs there (it is the only unprotected path: a retry after a lost response), and
  close it with a link to these tests. Add the S-3 pointer to its scope.
- **WISHENKA-316..319** (295 debts): only WISHENKA-319 overlaps (T-4); add the call site. 316-318
  are delete-specific, no overlap.
- **WISHENKA-308..311, 313..315** (307 and 294 debts): only WISHENKA-313 overlaps (T-3, add the
  creation form to its browser matrix). 309 (quick-add spacing, `#feedback`), 310 (pending/feedback
  duplication) and 311 (load-sensitive browser tests) were checked for the new form: `showCreate`
  reuses `withPending` and `status()` rather than adding new pending code, so no new duplication;
  S-1 (weak wait) is a close relative of 311 in nature but a different test, so it stays in
  follow-up 2.

## Follow-up Tasks

1. **One title and length contract for create and settings: apply the 1-255 trimmed title (and
   agreed maxima for description and event title) to `PATCH` as well, mirror the limits on both
   forms, map a too-long 422 to the correct message, and decide on existing blank titles.**
   NON-BLOCKER (creation is correct; the inconsistency is a product-facing gap), priority Medium.
   Covers S-2 (incl. invisible-only titles, client and server), S-4, C-1, T-1, T-2, and C-3 if both forms change. Files:
   `wishenka/web/routes/wishlists.py:34-55,472`, `wishenka/web/static/miniapp.js:430-480`.
   Jira: [WISHENKA-320](https://pypost.atlassian.net/browse/WISHENKA-320)
2. **Remove the root cause of the history test race and tidy the new tests: wait for
   `.history-error` in `test_load_failure_shows_alert_and_retry_recovers`, then let `api()` parse
   bodies uniformly if wanted; strict catalog lookup and a shared catalog helper for the two new
   test modules; drop the redundant `err.textContent = ''` in `clearFieldError`.**
   NON-BLOCKER (test maintainability), priority Low. Covers S-1, C-2.
   Files: `tests/test_history_screen_browser.py:643-647`,
   `tests/test_wishlist_create_form_ui.py:151,167,171,260`,
   `tests/test_wishlist_create_form_browser.py:87,92,99,149`, `wishenka/web/static/miniapp.js:117-123,417-418`.
   Jira: [WISHENKA-321](https://pypost.atlassian.net/browse/WISHENKA-321)
3. **Idempotent wishlist creation: an `Idempotency-Key` for `POST /api/wishlists` so a retry after
   a lost response or a proxy 502/504 returns the first list instead of creating a duplicate.**
   NON-BLOCKER (documented in R-2, rare; the owner can delete the duplicate through WISHENKA-295),
   priority Low. Covers S-3. Files: `wishenka/web/routes/wishlists.py:192`,
   `wishenka/web/static/miniapp.js:378-541`.
   Jira: [WISHENKA-322](https://pypost.atlassian.net/browse/WISHENKA-322)
4. **Scope additions to existing tickets (no new ticket):**
   WISHENKA-312: what remains is the S-3 pointer and a close-out against the tests listed above.
   WISHENKA-319: add the `page._send` call at `tests/test_wishlist_create_form_browser.py:793`.
   WISHENKA-313: extend its scope from the settings-switch skins to the creation form cross-browser check (T-3).
   Jira: [WISHENKA-312](https://pypost.atlassian.net/browse/WISHENKA-312),
   [WISHENKA-319](https://pypost.atlassian.net/browse/WISHENKA-319),
   [WISHENKA-313](https://pypost.atlassian.net/browse/WISHENKA-313)

Considered and dropped: O-1 and O-2 (accepted observability trade-offs, no action until a global
validation handler or a privacy review exists); T-5 (run-mode caveat, pre-existing); the suite
duration (repository-level). D-1 is a product confirmation, tracked in the Jira comment of
WISHENKA-296, not a Debt ticket.

### Pre-existing test failures

The full run of this task (2383 passed, 2 skipped) had 16 failures, all in the known pre-existing
set and ticketed; the 17th case of the first run (the history 500 case) was caused by this change,
fixed, and is discussed in S-1. No new item is recorded. The list and the node ids are in
`ai-tasks/WISHENKA-295/60-tech-debt.md` (section "Pre-existing test failures") and
`ai-tasks/WISHENKA-292/60-tech-debt.md`:

- `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral` — NON-BLOCKER —
  pre-existing. Jira: [WISHENKA-265](https://pypost.atlassian.net/browse/WISHENKA-265).
- `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads` —
  NON-BLOCKER — pre-existing. Jira: [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220).
- The remaining 14 failures: NON-BLOCKER — pre-existing, ticketed in WISHENKA-232, 235, 245, 264,
  267, 298 (node ids in the 292 artifact). They are not touched by this task.
