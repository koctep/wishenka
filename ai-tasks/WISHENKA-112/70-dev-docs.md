# WISHENKA-112: Developer Documentation Updates

## Overview

WISHENKA-112 is a behaviour-preserving refactor: `_NOT_FOUND_ERRORS` became `_DOMAIN_ERRORS` and the
reorder callback takes only the current ids (`wishenka/web/routes/items_ui.py`), and the
`hasattr`/`getattr` probes for guaranteed columns were removed from `wishenka/wishlists/store.py` and
`wishenka/wishlists/repository.py`. No API, route, status code, log event or schema changed.

## Checked

Search over `doc/`, `specs/`, `in-docs/`, `README*` for `_NOT_FOUND_ERRORS`, `_DOMAIN_ERRORS`,
`_reordered_response`, `_raise_http`, `hasattr`, `getattr`, `probe`/`probing`:

- No document names the old or new error tuple, the helper, or the callback signature. Nothing is stale.
- HTTP statuses of the items routes are already documented where they matter and are unchanged:
  `doc/dev/items.md` (error table, `WishlistArchivedError` -> 409, reorder `ValueError` -> 400),
  `doc/dev/miniapp.md` (404 for non-members, `ui_items_reordered` / `ui_items_reorder_rejected` events).
  A mention of a private tuple name would only go stale, so no note was added there.
- `doc/dev/migrations.md` documents the revisions that add the two columns but not the rule that code
  can rely on them. This was a real gap.

## Changed

- [`doc/dev/migrations.md`](file:///home/src/doc/dev/migrations.md): added a short "Column convention"
  paragraph after the revision chain. Columns created by revisions are guaranteed after
  `upgrade_to_head()`, so code reads them directly with no `hasattr`/`getattr` probing and no silent
  defaults; a missing column is a schema bug that surfaces as `AttributeError` (HTTP 500).

## Not changed

- `doc/dev/architecture.md`, `testing.md`, `miniapp.md`, `items.md`, `wishlists.md`: no stale text and
  no gap for this task.
- No code, tests, Jira or git state touched in this step.
