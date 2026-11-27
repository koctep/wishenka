# WISHENKA-220: Technical Debt Analysis

No blocker. This task only rewrote
`tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
so it matches the list notice an archive of a missing wish already shows.
Production code is unchanged. There is no new follow-up.

Reviewed: the rewritten node, `10-requirements.md`, `20-architecture.md`,
`40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

None. The check opens the archive dialog, posts item `999999`, and asserts
the existing Russian notice
«Желание или вишлист больше недоступны.», a closed dialog, the same card
order, and no reload. It does not listen for `htmx:responseError`. The
function name stays, because the requirements and the architecture cite
that node. The name is not a follow-up.

## Code Quality Issues

None that need a follow-up. The notice sentence is the catalog string the
architecture names for this Russian page. The two-second reload watch is
the bounded loop the architecture kept.

## Missing Tests

No `do-testing` blocker. The module already declares
`pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`, which covers
this node. `page.wait_for` is bounded, and the reload watch stops after
two seconds.

`test_stale_reorder_keeps_list_and_shows_notice` still covers the
stale-order notice and reload. An English page for the same notice is out
of scope: the architecture leaves that sentence as the catalog value of
`web.item.resource_not_found`.

## Performance Concerns

None. The check adds no server work. The two-second poll is the watch the
architecture already specified.

## Follow-up Tasks

None. There is no new follow-up.

Developer docs still describe the old check: an unmarked error that shows
no notice and does not reload, and the node as a known failure
(`doc/dev/testing.md`, `doc/dev/gift-receipt.md`). Updating those sentences
belongs to Step 8. User documentation under `doc/` was left unchanged. This
task does not add a screen, a sentence, or a role rule.
