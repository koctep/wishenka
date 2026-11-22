# WISHENKA-290: Technical Debt Analysis

## Shortcuts Taken

The detail screen continues to use the existing Mini App DOM and API helpers. It does not add a
second component framework or change server contracts. No temporary production workaround was
identified. After a successful mutation, the screen replaces stale controls while it refreshes;
if refresh fails, it displays a retry instead of retaining a revoked link or outdated actions.

## Code Quality Issues

The detail renderer and event handlers remain in the existing `miniapp.js` module, with
`showList` coordinating rendering and refresh. This follows the current module's design but
increases its responsibilities. A component extraction could be useful if further detail-screen
work makes it harder to maintain; the present change does not require a separate follow-up.

The new styling uses existing design tokens, apart from the fixed teal border already used for
the collaborator section. It carries no new configuration, schema, or migration requirement.

## Missing Tests

The two new test modules cover English and Russian labels, roles, mobile layout, settings,
sharing, member actions, and refresh failures. Both have explicit pytest timeouts. Browser tests
run in Chromium; other browser engines and Telegram clients are not exercised. No acceptance
criterion requires a second browser engine, and a new cross-browser infrastructure task is not
needed for this change.

## Performance Concerns

The screen performs an existing GET after mutations to obtain authoritative state. The change
introduces no additional request per action or new backend query. Rendering grows with the number
of wishes and members as before; no measured performance regression or optimization need was
identified.

## Follow-up Tasks

The full `make test` run had 2,023 passes, two skips and 16 failures. The failures below were
reproduced with the same initial failure against clean base commit
`2d842ae8cb2292910906561574ada439317226a1`. They are **NON-BLOCKER — pre-existing** and match
the existing issues linked below. They do not require duplicate Jira issues. Test node IDs in
each fenced block are exact.

### Archive error mapping

Jira: [WISHENKA-264](https://pypost.atlassian.net/browse/WISHENKA-264)

```text
tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive-confirm]
tests/test_items_ui_error_mapping.py::test_archived_wishlist_gives_409[archive]
tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive-confirm]
tests/test_items_ui_error_mapping.py::test_unknown_wishlist_gives_404[archive]
tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive-confirm]
tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive]
tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive-confirm]
tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[archive]
```

### Anonymous gift availability

Jira: [WISHENKA-235](https://pypost.atlassian.net/browse/WISHENKA-235)

```text
tests/test_wish_card_giver_controls.py::test_anonymous_share_shows_availability_without_a_book_control
tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account
```

### Notice cleanup

Jira: [WISHENKA-245](https://pypost.atlassian.net/browse/WISHENKA-245)

```text
tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge
```

### Stale giver card

Jira: [WISHENKA-265](https://pypost.atlassian.net/browse/WISHENKA-265)

```text
tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral
```

### Shared-view observability

Jira: [WISHENKA-226](https://pypost.atlassian.net/browse/WISHENKA-226)

```text
tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability
```

### Unmarked receipt error

Jira: [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220)

```text
tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads
```

### Receipt migration

Jira: [WISHENKA-232](https://pypost.atlassian.net/browse/WISHENKA-232)

```text
tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable
```

### HTMX move action

Jira: [WISHENKA-267](https://pypost.atlassian.net/browse/WISHENKA-267)

```text
tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf
```
