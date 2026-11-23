# WISHENKA-296: Developer Documentation

## Changed Files

Product docs (this task reverses a documented product rule, decision D1):

- `in-docs/spec.md` (Russian)
  - 4.2 "Creation": the "automatic empty personal list" and "title may be set later" lines are
    replaced. Create wishlist opens a form; a list is created only after an explicit Create with
    a valid required title (1-255 characters after trim); description, event and date are
    optional; leaving the form creates nothing; success opens the new list.
  - UC-01 rewritten to the same flow.
- `in-docs/bot-scenarios.md` (English): the "Create wishlist" row now says the bot opens the
  Mini App at the home screen, where creation starts, and creates nothing.
- `specs/00-high.md` is not changed (not contradicted).

Developer docs:

- `doc/dev/miniapp.md`
  - Goal 1 renamed "Explicit Creation".
  - Create-button scope note rewritten (guard is now the form's Create button; A6 tests named;
    WISHENKA-312 and 322 for the rest); guarded-controls list clarified.
  - Section "1. Wishlist Creation" (was "Frictionless Wishlist Creation") rewritten.
  - New section "Wishlist Creation Form (WISHENKA-296)": `showCreate`, `goHome`,
    `homeRenderToken`, fields, validation (client and server), request and failure mapping,
    inline errors, focus table, CSS, the `api()` helper (`err.body` for 422 only), known limits.
  - Home button text no longer says "POST body {}"; route table row for `POST /api/wishlists`.
- `doc/dev/wishlists.md`: `POST /api/wishlists` contract (`WishlistCreateInput`, 422 shape,
  PATCH stays permissive), service note (validation is HTTP-only), event table
  (`wishlist_created` logged twice, `wishlist_mutation_committed` single-fire signal) and a note
  on the missing 422 event and `event_date` logging.
- `doc/dev/i18n.md` (English): section "Wishlist Creation Texts (WISHENKA-296)": eight
  `miniapp.create.*` keys, placeholders, reused settings keys.
- `doc/dev/testing.md` (Russian): section for the four new modules (25 / 27 / 42 / 11 = 105
  tests, counted with `.venv/bin/pytest --collect-only -q -n 0`; timeouts 30 / 20 / 45 / 30;
  `browser` marker on the browser module), corrected and updated tests, `PYTEST_ARGS` scoping
  note, limits; use case 7 of the home UI module and the WISHENKA-312 limitation note rewritten;
  pointer under "Известные ограничения".
- `doc/dev/architecture.md`: unchanged (it has no creation text).

## Reconciled Stale Statements

- `in-docs/spec.md` 4.2 and UC-01: "automatic empty list", "title may be set later".
- `miniapp.md` goal 1 "Frictionless Creation", section "1. Frictionless Wishlist Creation"
  (empty `{}` payload, "Мой вишлист" placeholder claim for the new list), home button
  "submits POST with body '{}'", route table "Creates an empty personal wishlist", and the
  Create-button scope note ("WISHENKA-296 changes that flow").
- `wishlists.md`: route list said only "creates a list; returns 201"; event table lacked
  `wishlist_mutation_committed` and the double `wishlist_created`.
- `testing.md`: use case 7 (click sends `POST` `{}`) and "re-check the guard and A6 after
  WISHENKA-296".
- `bot-scenarios.md`: "list creation flow" (there is no separate flow outside the Mini App).

## Deviations from `20-architecture.md` Recorded in the Docs

- `api()` stores `err.body` only for status 422 (design R-10: every error). Reason: a timing-weak
  wait in `tests/test_history_screen_browser.py` (500 case); see `60-tech-debt.md` S-1 and
  WISHENKA-321. Documented in `miniapp.md` with the warning not to widen it yet.
- Eight `miniapp.create.*` keys, not nine (D-4); documented in `i18n.md` with the reused keys.
- Three new tests were corrected in Step 4 (wrong expectations, intent kept): UI valid-submit
  (only `wishlist-create-form` must be gone, the list screen has its own form), browser
  `test_leaving_the_empty_form_creates_nothing[back]` (no history entry is pushed, so no home
  wait) and the Tab-order test (collapse native `datetime-local` stops). Recorded in `testing.md`.
- Four new test modules, not three: Step 6 added `tests/test_wishlist_create_observability.py`
  (the design's "Docs to update" listed three).
- A `422` on `name` always shows `error_title_required`, even for a too-long title (design
  implied a distinct message); documented as a known limit (WISHENKA-320, `60-tech-debt.md` C-1).
- Service `wishlist_created` logs `event_date` (pre-existing); documented, not changed.
- No code, test or architecture file was changed in this step.

## Follow-ups Linked

- [WISHENKA-320](https://pypost.atlassian.net/browse/WISHENKA-320): one title and length
  contract for create and PATCH, too-long 422 message, invisible-only titles, blank old titles.
- [WISHENKA-321](https://pypost.atlassian.net/browse/WISHENKA-321): fix the weak history wait,
  then let `api()` parse bodies uniformly; test helper cleanup.
- [WISHENKA-322](https://pypost.atlassian.net/browse/WISHENKA-322): idempotent creation.
- Scope additions: [WISHENKA-312](https://pypost.atlassian.net/browse/WISHENKA-312) (S-3
  pointer, close-out against the new tests),
  [WISHENKA-313](https://pypost.atlassian.net/browse/WISHENKA-313) (creation form in the
  cross-browser matrix),
  [WISHENKA-319](https://pypost.atlassian.net/browse/WISHENKA-319) (`page._send` call site).

## Product Confirmation Note

Decisions D1 (no automatic empty list; explicit confirmation of a form) and D2 (title becomes
required) were taken autonomously in the run and are written into `in-docs/spec.md` as the
current product rule. They still need the product owner's confirmation; both are reversible
(relax `WishlistCreateInput` and the form). Whether "title required" also covers editing via
PATCH is open (WISHENKA-320). The confirmation is tracked in the Jira comment of WISHENKA-296,
not as a Debt ticket.
