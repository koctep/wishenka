# WISHENKA-230: Technical Debt Analysis

## Shortcuts Taken

The three new tests use mocked DNS or pinned addresses and a fake inner backend to exercise
failure handling without live network access. This is the approved test architecture, not a
production shortcut. Pinned context tokens are reset in `finally`; the DNS test uses an
isolated cache. No application code or interface was changed.

## Code Quality Issues

No new production debt or architecture deviations were identified. Existing transport
injection uses private HTTPX/httpcore internals and remains tracked by
[WISHENKA-284](https://pypost.atlassian.net/browse/WISHENKA-284). The existing DNS resolver
converts a DNS error to an empty result, so the subsequent connection error does not retain
the original cause; `ai-tasks/WISHENKA-92/60-tech-debt.md` records this diagnostic trade-off.
The existing credential-handling limitation is tracked by
[WISHENKA-286](https://pypost.atlassian.net/browse/WISHENKA-286).

## Missing Tests

The new cases assert DNS failure and no unsafe connection, exhausted `OSError` wrapping and
logging, and duplicate IP attempts. The module declares `pytestmark = pytest.mark.timeout(30)`
for every test. The Step 4 focused suite passed 57 tests; Step 6 passed 16 connection and
logging tests. The tests do not use external DNS or network services.

The exhaustion tests use `OSError`; a dedicated exhaustion assertion for final
`httpcore.ConnectError` or `httpcore.ConnectTimeout` is not included. Existing failover tests
exercise an initial `httpcore.ConnectError` followed by success. The remaining variants are
low-risk additional coverage, not required by this task's specified `OSError` wrapping
case, and no new follow-up is proposed. Live-network behavior is outside the approved scope.

## Performance Concerns

The change adds three bounded offline tests and no production work. Sequential connection
attempts still each receive the full timeout; this pre-existing behavior is tracked by
[WISHENKA-231](https://pypost.atlassian.net/browse/WISHENKA-231).

## Follow-up Tasks

- **NON-BLOCKER — pre-existing:** Browser fixture setup fails when Chromium is absent;
  [WISHENKA-297](https://pypost.atlassian.net/browse/WISHENKA-297) tracks non-root setup.
  All 115 affected node IDs are recorded in `ai-tasks/WISHENKA-95/41-baseline-test-evidence.md`.
- **NON-BLOCKER — pre-existing:** The following failures were reproduced at the WISHENKA-95
  base commit and mapped to existing issues; details and the comparison are recorded in
  `ai-tasks/WISHENKA-95/41-baseline-test-evidence.md`:
  - WISHENKA-232: `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable`.
  - WISHENKA-264: `tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409`
    (`archive-confirm`, `archive`), `test_non_member_gives_404` (`archive-confirm`, `archive`),
    `test_unknown_item_gives_404` (`archive-confirm`, `archive`), and
    `test_unknown_wishlist_gives_404` (`archive-confirm`, `archive`) in the same module.
  - WISHENKA-245: `test_cleanup_cycle_survives_a_failing_notice_purge` in
    `tests/test_receipt_notices_extra.py`.
  - WISHENKA-235: `test_share_link_visit_creates_no_account` in
    `tests/test_surprise_role_context.py` and
    `test_anonymous_share_shows_availability_without_a_book_control` in
    `tests/test_wish_card_giver_controls.py`.
  - WISHENKA-226: `test_wishlist_shared_view_observability` in
    `tests/test_wishlists_htmx_observability.py`.

No new unticketed follow-up is required for the WISHENKA-230 scope.
