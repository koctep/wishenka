# WISHENKA-291: Technical Debt Analysis

No blockers were found. Every acceptance criterion in `10-requirements.md` is covered by the
implementation and by passing tests. The items below are non-blocking follow-ups.

## Shortcuts Taken

No temporary production workaround was identified. The page keeps the existing server contracts,
endpoints, selectors, authorization and CSRF handling. Locale buttons now use a CSRF-protected
`fetch` instead of HTMX, as designed in `20-architecture.md`; this is a planned deviation from the
shared HTMX refresh pattern, not a shortcut.

No new production logging was added (see `50-observability.md`). Client-side failures that never
reach the server are not reported, because the project has no client telemetry convention.

## Code Quality Issues

### settings.js reconciliation complexity (NON-BLOCKER, medium)

`wishenka/web/static/settings.js` is 913 lines. Almost all of it sits in one `initController`
closure (about 770 lines). The closure holds the per-category serialization queue, pending notes,
rejection restore, GET reconciliation after 5xx or network loss, unknown/disabled state with
retry, derived inherited badges, birthdate draft handling, locale reconcile and the deletion
flow. The global, per-list override, birthdate, locale and deletion handlers each implement a
similar mutate, reconcile and retry sequence (`retryGlobal`, `retryOverride`,
`runLocaleReconcile` and the birthdate retry). The result is correct and tested, but adding a
sixth setting means copying the pattern again, and a fix to the reconciliation rules has to be
applied in several places.

Suggested follow-up: extract a shared "mutate, classify the response, reconcile, retry" helper
and split the controller into per-section modules. Behaviour must stay unchanged, so the 39
browser tests act as the safety net. No acceptance criterion depends on this.

### Long lines in templates and catalog (NON-BLOCKER, low)

This task added 0 long lines in `wishenka/i18n/catalog.py` (checked by character count, not
bytes, because Cyrillic text doubles the byte length). `wishenka/web/templates/settings.html`
has 17 lines over 100 characters now (18 at HEAD), so none were added. The remaining long lines
are pre-existing: those in `settings.html` and one line in `catalog.py` (about line 1088). A
Jinja attribute list or a translated sentence is hard to wrap without changing the rendered
text. The `make analyze` gate passes. Wrapping is a formatting-only change, worth doing only
together with a template restructure (see follow-up 3).

## Missing Tests

### Wishlist-notification and deletion rejection logging (NON-BLOCKER, low)

`tests/test_personal_settings_observability.py::test_rejected_settings_mutations_emit_no_success_event`
covers rejected locale, birthdate and global-notification payloads only. It does not exercise
these rejection paths, whose WARNING events are listed in `50-observability.md`:

- `PUT /api/profile/notifications/wishlists/{id}` with an invalid payload
  (`notification_wishlist_invalid_request`) and with an unknown or inaccessible list
  (`notification_wishlist_not_found`).
- A rejected account deletion (`account_deletion_rejected`).

These events exist in production code, and the browser tests cover the matching UI behaviour,
but nothing pins the log contract (event name present, no success event, no list title in the
log) for these routes. A future change to `profile.py` could drop the events unnoticed.

Suggested follow-up: extend the observability test with these three cases using the existing
`_capture` and `_events` helpers.

### Other coverage notes (informational)

Both new modules carry explicit pytest timeouts (`pytest.mark.timeout(30)` and
`pytest.mark.timeout(45)`), so there is no timeout-marker blocker. Browser tests run in Chromium
only; other engines and Telegram clients are not exercised. No criterion requires them, and no
task is needed.

The Step 4 roadmap records one Step 3 conformance failure (module timeout) in the full run. It is
resolved by the module-level timeout marker above.

## Performance Concerns

None measured. Reconciliation issues one extra GET only after a 5xx or a network failure, and
mutations per category are serialized, which limits concurrent requests per control. Rendering
grows with the number of accessible wishlists as before, and no regression was identified.

## Follow-up Tasks

Follow-ups were filed in Jira after the blocker review (SAFE TO CLOSE).

1. **Refactor `settings.js` reconciliation into a shared helper and per-section modules.**
   NON-BLOCKER, priority Medium. Jira: [WISHENKA-300](https://pypost.atlassian.net/browse/WISHENKA-300)
2. **Add observability tests for wishlist-notification and account-deletion rejection paths.**
   NON-BLOCKER, priority Low. Jira: [WISHENKA-299](https://pypost.atlassian.net/browse/WISHENKA-299)
3. **Wrap pre-existing long lines in `settings.html` (17) and `catalog.py` (line ~1088).**
   NON-BLOCKER, priority Low (do together with item 1 if the template is touched). Jira:
   [WISHENKA-301](https://pypost.atlassian.net/browse/WISHENKA-301)

### Pre-existing test failures

The full `make test` run showed 16 failures that reproduce on the base commit 762922f
(repro: `make test`). Each is **NON-BLOCKER — pre-existing**, not caused by this task, and
already tracked in Jira, so no duplicate issues are needed here.

- NON-BLOCKER — pre-existing, WISHENKA-264, in `tests/test_items_ui_error_mapping.py`, each
  with params `[archive]` and `[archive-confirm]`:
  - `::test_archived_wishlist_gives_409`
  - `::test_unknown_wishlist_gives_404`
  - `::test_non_member_gives_404`
  - `::test_unknown_item_gives_404`
- NON-BLOCKER — pre-existing, WISHENKA-235:
  `tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control`
- NON-BLOCKER — pre-existing, WISHENKA-245:
  `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
- NON-BLOCKER — pre-existing, WISHENKA-265:
  `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
- NON-BLOCKER — pre-existing, WISHENKA-220:
  `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
- NON-BLOCKER — pre-existing, WISHENKA-232:
  `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`
- NON-BLOCKER — pre-existing, WISHENKA-267:
  `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
- NON-BLOCKER — pre-existing, WISHENKA-298 (new Debt filed for failures on base commit 762922f):
  - `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
  - `tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability`

Note: WISHENKA-235 (`test_anonymous_share_shows_availability_without_a_book_control`) and
WISHENKA-298 (`test_share_link_visit_creates_no_account`) are related shared-view failures but
separate keys; each test maps to exactly one key.
