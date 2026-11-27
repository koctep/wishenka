# WISHENKA-264: Technical Debt Analysis

No new technical debt. This task only rewrote the eight archive assertions
in `tests/test_items_ui_error_mapping.py` so they expect the HTML list
notice those two actions already return. Product routes, the catalog, and
`app.js` are unchanged. There is no new follow-up.

Reviewed: the assertion rewrite, `10-requirements.md`,
`20-architecture.md`, `40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

None. The four parametrized tests stay, so the node ids stay. Archive
confirmation and archive send `Accept-Language: ru` and assert status,
`text/html`, the Russian catalog sentence in `#list-notice`, and an empty
`#item-modal-container`. The sentence is `t(catalog_key, "ru")`, not a
copied line. Reorder, move, and restore still assert JSON detail.
`_assert_refusal` branches on the sender functions because the architecture
keeps one setup per situation and two body shapes.

## Code Quality Issues

None. The rewrite adds the catalog lookup and a BeautifulSoup read of the
fragment `tests/test_item_modals_repro.py` already parses. It adds no
hardcoded notice, status, or timeout. The English JSON details for reorder,
move, and restore were already the contract for those routes.

## Missing Tests

No `do-testing` blocker. The module declares
`pytestmark = pytest.mark.timeout(30)` (`tests/test_items_ui_error_mapping.py`,
line 29). No test function overrides that mark. Collection of the module
reports 24 tests, and each carries timeout `(30,)`, including:

- `test_archived_wishlist_gives_409[archive-confirm]`
- `test_archived_wishlist_gives_409[archive]`
- `test_unknown_wishlist_gives_404[archive-confirm]`
- `test_unknown_wishlist_gives_404[archive]`
- `test_non_member_gives_404[archive-confirm]`
- `test_non_member_gives_404[archive]`
- `test_unknown_item_gives_404[archive-confirm]`
- `test_unknown_item_gives_404[archive]`

The new assertions do not wait, poll, or run an event loop of their own.
`asyncio.run` around the existing seed helpers is unchanged.

The eight nodes do not execute `app.js`. The architecture already treats
the existing `htmx:beforeSwap` handler as the page-swap check. That limit
is not a new gap, and an English archive page is out of scope: the
requirements name the Russian catalog sentences.

## Performance Concerns

None. Each archive refusal parses one small HTML fragment. No query, poll,
or route was added.

## Follow-up Tasks

None. There is no new follow-up. This change did not cause the other sprint
failures, so they are not listed here.

User documentation under `doc/` was left unchanged. The refusal a person
sees did not change. Any developer-doc sentence still belongs to Step 8.
