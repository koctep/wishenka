# WISHENKA-296: Failing repro (Step 3)

Three new modules, no production code touched (`wishenka/` is unchanged; `git status` shows only
the three test modules and `ai-tasks/`). They assert the behavior of `20-architecture.md`
(D-1 .. D-6, Test strategy, browser cases 1-10) and fail on current code because the feature is
missing: a tap on "Create wishlist" sends `POST /api/wishlists` with `{}` at once (the reported
bug), there is no form, and the API accepts a missing, blank or over-long title.

Existing tests were not edited (Step 4 does that, see the last section).

## Inventory

### `tests/test_wishlist_create_validation_api.py` (`timeout(30)`, no browser; 25 cases)

`TestClient(create_app(settings))` with a bearer header (style of `tests/test_wishlist_api.py`),
count of lists read through `GET /api/wishlists`.

- Red (15): `{}`, `null`, `""`, spaces, whitespace kinds, 256 characters, 256 after trim and
  optional fields without a name -> 422 with `detail[0].loc == ["body", "name"]` and the list
  count unchanged; five rejections in a row leave the account empty; 255 astral characters
  (255 code points, 510 UTF-16 units) accepted while 256 is rejected; `"  Birthday  "` stored and
  returned as `Birthday`; trimmed length decides the limit (5 spaces + 255 chars + 5 spaces is
  201); 422 body has the default FastAPI shape (`msg`, `type`); single-fire signal
  `wishlist_mutation_committed` with `operation == "create_wishlist"` fires once per valid
  request and never for a 422; a 422 for a 256+ character title carries no title or description
  in any log record (caplog, all loggers).
- Green regression guards (10): non-string `name` (number, list) still 422; exactly 255 characters
  201; valid creation keeps the owner projection (`role owner`, `status active`, tokens, no
  items, optional fields saved); optional fields omitted or `null`; unparseable `event_date`
  422 with `loc == ["body", "event_date"]` and nothing created; unauthenticated `{}` and
  `{"name": "x"}` still 401 (auth before body validation); cookie session with matching
  Origin but no CSRF header -> 403 and nothing created; PATCH keeps the permissive model
  (absent name keeps the old name, `{}` is a no-op, `{"name": ""}` and a 300-character name are
  accepted); a 201 logs neither title nor description.

### `tests/test_wishlist_create_form_ui.py` (`timeout(20)`, Node harness, no browser marker; 27 cases)

Patches `_NODE_HARNESS` from `tests/test_miniapp_i18n_repro.py` by string replacement (each
anchor asserted exactly once): a recording `fetch` (non-GET calls with body and headers, POST
reply scenarios 201 / 500 / network), `localStorage` / `sessionStorage` recorders, a step runner
(click by class or exact button text, fill an input by name and fire its `input` listeners,
submit the form once or `times` in the same tick) and a `create_flow` action. A handler
exception fails the test. What the fake DOM cannot show (inline error nodes, `aria-*`, focus, the
422 body mapping) is left to the browser module; `h1.focus()` is not asserted.

- Catalog (red): the eight `miniapp.create.*` keys exist in en and ru, are translated, share the
  same `{placeholders}` (`{max}` in `error_title_too_long`), reach `miniapp_catalog()`.
  Guard (green): no reservation wording in them (surprise invariant, D-8).
- Source layout (red): `showCreate` defined before `async function showHome(` (outside the slice
  scanned by `home_script_problems`) and `homeRenderToken` present.
- Home click (red, en/ru): zero non-GET requests, `h1 == miniapp.create.title`, a form exists.
- Form (red, en/ru): inputs `name, description, event_title, event_date` in order,
  `datetime-local` date, catalog labels and lead, `aria-required`, `autocomplete=off`,
  `novalidate`, submit button (`type=submit`, `btn-primary`, catalog text) before Cancel
  (`type=button`, `miniapp.wishlist_settings.cancel`); no storage writes while typing.
- Cancel (red, en/ru): returns to the home `h1`, no request, no form, no storage write; the form
  reopens with empty values.
- Validation (red): empty, blank, tab/newline and 256-character titles send nothing, keep every
  typed value, form stays, no "Creating..." status; a five-digit year sends nothing and throws
  nothing.
- Confirmation (red): valid submit -> exactly one `POST /api/wishlists` with CSRF header, trimmed
  `name`, `null` empty optionals, UTC ISO date, list screen shown; 255 code points sent; three
  submits in the same tick send one POST.
- Failure (red): 500 and network error keep the form and values, one request, `#status` equals
  `miniapp.home.create_failed` with `data-kind == "error"`; a second submit sends a second
  request (one per confirmed submit).

### `tests/test_wishlist_create_form_browser.py` (`browser` marker + `timeout(45)`; 42 cases)

Real Chromium, plain browser without Telegram bridge, cookie session, own `open_home` factory on
`open_miniapp` with a `PRELOAD` fetch wrapper (`window.__t`: counts of create / home list /
list detail requests, modes `real | hold | 500 | 422name | 422date | 422unknown`, per-key
release, uncaught error log). Values are set through `evaluate`; Enter is `press_key("Enter")`
on the focused title input; the account is checked on the server through `GET /api/wishlists`.

1. Core bug (en, ru): tap Create, then reload -> the account has no new list; tap Create, then
   `showHistory()` / `showHome()` in app -> no list, zero create requests (red today: one empty
   list is created).
2. Opening (en, ru): the button opens the form, zero requests, h1, four inputs in order, Create
   and Cancel texts from the catalog, no home sections under the form.
3. Leaving the empty form by Cancel, `location.reload()`, navigate to `/`, in-app `showHome()` and
   `history.back()` (after a `pushState`) -> no list; after Cancel the home `h1` has the focus.
4. Partial fill then Cancel / reload -> no list; the reopened form is empty (no draft).
5. Valid create (en, ru): trimmed title, description, event name and date saved, `status
   active`, `role owner`, list opens (`.list-title`), one create request, Back shows the card;
   optional fields may stay empty.
6. Invalid input (en/ru x empty, blank, 256 chars): inline error with the catalog text
   (`{max}` = 255), `aria-invalid`, `aria-describedby`, `role=alert`, focus on the title, typed
   values kept, zero requests, no pending flash (status observer); fixing the title clears the
   error and the submit succeeds; five-digit year -> date error, no request, no uncaught error;
   mocked 422 with `loc` name / event_date -> field error, focus, values kept, no stale
   status, Create usable; 422 with an unknown `loc` -> `create_failed`, no inline error.
7. Double submit: real Enter, three same-tick clicks and two more Enters while the response is
   held -> exactly one request, Create and Cancel disabled, `aria-busy`, the four inputs read-only; after release the list
   opens; real tap burst; blank title + Enter never shows "Creating...".
8. Failure (en, ru): 500 -> `create_failed` assertive error, values kept, Create and Cancel
   enabled, Create focused, no `readonly` input, nothing created; retry creates exactly one list
   (two requests total). Post-creation list load failure (detail 500): home shown, `create_failed`
   not shown, `list.load_failed` error status, home `h1` focused, one list created and visible.
9. Staleness guard: Create during a held home load -> only the form (no sections, empty
   status); two overlapping held home loads -> one set of sections.
10. Layout (en, ru x 320, 412): no overflow or clipping, targets >= 44 px, six controls >= 44
    px, Create and Cancel reachable, contrast and Tab focus outline, accessibility tree (textbox
    named by the label with "(required)", `required`, `invalid`, description holds the error,
    alert, heading, buttons), tab order name -> description -> event -> date -> Create -> Cancel.
11. Guard (green): `?startapp=create` opens the home screen, no form, no list (D9).

## Run commands

```
make analyze
make test-serial PYTEST_ARGS="tests/test_wishlist_create_validation_api.py"
make test-serial PYTEST_ARGS="tests/test_wishlist_create_form_ui.py"
make test-serial PYTEST_ARGS="tests/test_wishlist_create_form_browser.py"
```

`make test-serial` takes `PYTEST_ARGS` (not `ARGS`). Add `-rfE --tb=line` for a short summary.

## Red evidence (unchanged production code)

`make analyze`: ruff check, ruff format check and mypy clean.

| Module | Result today | Failure reason |
| ------ | ------------ | -------------- |
| `..._validation_api.py` | 15 failed, 10 passed | `AssertionError: ... must be 422, got 201` (and the derived trim, count, signal and log assertions) |
| `..._form_ui.py` | 26 failed, 1 passed | zero-request assertions fail on the old `{}` POST; form assertions fail on missing form / missing catalog keys (`<missing catalog key ...>` marker); step errors say "feature missing" |
| `..._form_browser.py` | 41 failed, 1 passed | core cases: `tapping Create and leaving left 1 new list(s): [{'id': 1, 'name': '', ...}]`; all other cases: `PageWaitTimeout ... creation form (a tap on Create must open a form, not create a list)` |

Not caused by fixtures, imports or syntax: every module collects and runs, the green cases prove
the harness and servers work, and the core case shows the actual empty list created by a tap
followed by a reload (requirement 1, 4, 9).

Legitimately green regression guards (must stay green after Step 4): API 255 characters,
non-string name, valid creation projection, optional fields, bad date, unauthenticated 401,
PATCH permissive, no user text in 201 logs; UI `test_create_texts_never_mention_reservations`;
browser `test_deep_link_opens_home_without_a_form_and_creates_nothing`.

## Mapping to requirements

| Requirement | Tests |
| ----------- | ----- |
| 1 Nothing before confirmation | browser 1, 2; UI home click |
| 2 Form with Create and Cancel, title required | UI form, catalog; browser 2; API 422 |
| 3 Validation, message by the field, keep input | API 422 set; UI validation; browser 6 |
| 4 Leaving creates nothing | browser 1, 3; UI Cancel |
| 5 No data survives | browser 4; UI reopen empty, no storage |
| 6 Success as before | API projection; UI confirmation; browser 5 |
| 7 Failure and retry | UI failure; browser 8 |
| 8 Double submit | UI burst; browser 7 |
| 9 Reopening the section | browser 1, 3, 4 (server count after reload) |
| 10 Entry points, deep link | browser 11, `test_home_overview_browser.py` (existing) |
| 11 Leaving without Telegram controls | browser 3 (Cancel, back, reload, no bridge) |
| 12 Mini App = browser, en/ru | browser en/ru, plain Chromium |
| 13 Texts, accessibility, touch | UI catalog; browser 10 |
| 14 Other behaviour unchanged | API PATCH guard, observability guards |

## Existing tests that Step 4 must update (not edited here)

Baseline run on unchanged code (all selected tests pass today): see "Baseline" below.

| Test | Why |
| ---- | --- |
| `tests/test_home_overview_ui.py` ~862-890 (`clickNavButtonIndex: 0`) and harness stub ~282 | asserts a `POST /api/wishlists` with body `{}` on the click; must assert no POST and the form; the stub should echo the submitted `name` |
| `tests/test_cross_screen_comfort_browser.py` 465 (`test_create_wishlist_burst_sends_a_single_post`) and 501 (`test_create_wishlist_failure_is_announced_as_an_error`) | click `.home-create-btn` and expect the POST / error at click time; rewrite against the form (the new browser module has the replacement cases) |
| `tests/test_wishlist_api.py` 33, 80, 186, 277, 282 (`json={}`) | 422 after the change; use `{"name": ...}`; 80 expects a forced write failure (500) so it needs a valid name to reach the handler; 186 unauthenticated `{}` stays 401 (checked by `test_unauthenticated_empty_body_is_still_401`); 277/282 depend on token order |
| `tests/test_wishlist_management_ui.py:80` | posts `{}`; use a name |
| `tests/test_home_overview_browser.py:59` | creates an untitled list through `{"name": ""}` for the legacy fallback; seed through the service/store or create with a name and clear it with `PATCH` (PATCH still allows an empty name, checked by the PATCH guard) |

Also keep green: `tests/test_reservations_cabinet_ui.py` (`home_script_problems`).

## Baseline

Run on unchanged production code with
`make test-serial PYTEST_ARGS="tests/test_home_overview_ui.py tests/test_wishlist_api.py
tests/test_wishlist_management_ui.py tests/test_reservations_cabinet_ui.py
tests/test_cross_screen_comfort_browser.py::test_create_wishlist_burst_sends_a_single_post
tests/test_cross_screen_comfort_browser.py::test_create_wishlist_failure_is_announced_as_an_error
tests/test_home_overview_browser.py"`: **67 passed** in 234 s. So every test listed above passes
today and fails or needs changing only after the Step 4 behavior change.

## Notes for later steps

- Module names differ from the plan in `20-architecture.md` (`test_wishlist_create_ui.py` and
  `test_wishlist_create_browser.py`): they are `test_wishlist_create_form_ui.py` and
  `test_wishlist_create_form_browser.py` (API module name unchanged). Step 8 `doc/dev/testing.md`
  must use these names.
- Requirement 12 "all themes": themes share the same CSS tokens; they are covered by the token-based
  styling and the contrast check in `test_form_has_readable_text_and_a_visible_focus_ring`
  (default theme only; no per-theme browser run).

## Concerns

- Browser module runs about 2.5 minutes today (most cases wait the 3 s form timeout); after Step 4
  most waits resolve at once.
- The accessibility-tree test relies on Chromium exposing `required`, `invalid` and the
  `aria-describedby` description on the textbox node; Step 4 may need to adjust the assertion if
  the engine reports them differently, but not weaken the intent.
- UI-harness submit events are synthetic (`submit` listeners invoked directly); real implicit
  submission is covered only by the browser tests (`press_key("Enter")`).
- The 255-code-point API test uses emoji; SQLite stores it unchanged.
