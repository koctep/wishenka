# WISHENKA-112: Small cleanup of the item UI routes and the wishlist store

## Goals

Three small readability defects, left over from WISHENKA-15, make the wishlist code harder to
read and easier to misuse. This task removes them without changing what the product does.

Business value:

- **Maintainability**: a name must say what it holds. A group of error types called "not found"
  that also contains the "archived" error (answered to users as a conflict, not as "not found")
  misleads the next developer and invites a wrong mapping in new routes.
- **Less noise**: an unused argument in the reorder helper and defensive checks for things that
  cannot happen make readers look for behaviour that does not exist.
- **Safety of future changes**: the less misleading code there is around reordering and loading
  wishlists, the lower the risk of an accidental behaviour change in later work.

Source: technical debt in `ai-tasks/WISHENKA-15/60-tech-debt.md` ("Code Quality Issues" and the
follow-up for WISHENKA-112). Jira: WISHENKA-112, type Debt, priority Low, 2 SP, label tech-debt.

## User Stories

- As a maintainer reading the item UI routes, I want the group of domain errors handled by the
  routes to have a name that matches its content (including the archived-wishlist error that is
  reported as a conflict), so that I do not assume archived lists are reported as "not found".
- As a maintainer changing the reorder or move-item flow, I want the helper that applies a
  reorder to ask its callers only for what it really uses, so that I do not have to guess what
  the unused input is for.
- As a maintainer reading the wishlist store, I want checks that can never trigger to be gone,
  so that I do not conclude that rows may lack columns the storage guarantees.
- As an owner or visitor of a wishlist, I want nothing to change for me at all.

## Definition of Done

Acceptance criteria (each verifiable by tests or by reading the code):

1. **Error group renamed**: the group of domain errors currently named `_NOT_FOUND_ERRORS` in
   the item UI routes has a name that does not claim "not found" only. The new name is used at
   every place that used the old one, and the old name no longer exists in the code base,
   tests and `doc/dev/`. The group content (the five error types) is unchanged.
2. **Reorder helper simplified**: the callable passed to the shared reorder helper
   (`_reordered_response`) in the item UI routes no longer receives the unused service
   argument. Both callers (full reorder and move up/down) are updated and the unused argument
   is gone from both. The helper still decides from the current order of item ids.
3. **Redundant `hasattr` checks removed**: in `wishenka/wishlists/store.py` the `hasattr`
   checks on result rows for columns that are always selected and always present are removed.
   Each remaining defensive check, if any, has a recorded reason (see "Task Description").
4. **Behaviour unchanged (invariant)**: see "Invariants" below; every item is verified by the
   existing tests.
5. **No test weakened**: all existing tests pass unchanged in meaning. No assertion is removed,
   loosened, skipped or marked expected-failure. Test edits, if any, are limited to what the
   renames force (for example an imported or patched name) and keep every assertion.
6. **Quality gate**: the repository checks (`make analyze` and `make test`) pass.
7. **Debt items re-verified**: the result of re-checking each debt item against the current
   code is recorded in this document (see "Task Description"). An item that is already
   resolved or does not apply is dropped explicitly, not silently.

### Invariants (must not change)

- **HTTP statuses**: an archived wishlist is still answered with 409 and the detail
  "Wishlist is archived"; missing or deleted wishlist, missing item and permission denied are
  still answered with 404 and the detail "Resource not found"; an invalid item order is still
  answered with 400 and the detail "Invalid item order".
- **Which routes map what**: all routes that handle this error group today (reorder, move,
  archive confirmation, archive, restore) keep the same mapping.
- **Responses**: response bodies, rendered lists and headers of the reorder and move routes
  are the same as before for the same input.
- **Reorder semantics**: no write is made when the order does not change; moving the first
  item up or the last item down changes nothing; a move of an unknown item is "not found".
- **Log events**: `ui_items_reordered` (reorder), `ui_item_moved` (move) and
  `ui_items_reorder_rejected` (invalid permutation, reason `invalid_permutation`) keep their
  level, message, event name and fields, and are emitted in the same situations. No new log
  events are added and none is removed.
- **Data loading**: wishlists and items are loaded with the same values as before, including
  the default of "warn on delete reserved" being enabled and the default item order being 0
  when the stored value is empty.
- **Storage**: no migration, no schema change, no change of selected columns.

## Task Description

### Problem

After WISHENKA-15 three small code-quality remarks were recorded as one debt ticket. They are
purely internal: nobody outside the code base can observe them.

### The three cleanups

1. **Name of the error group** (item UI routes). Current name: `_NOT_FOUND_ERRORS`. It holds
   `WishlistNotFoundError`, `WishlistDeletedError`, `ItemNotFoundError`,
   `PermissionDeniedError` and `WishlistArchivedError`. The shared error translator maps the
   archived error to 409 and everything else to 404. The group is used in the shared reorder
   helper and in the archive-confirmation, archive and restore routes (four places). The debt
   item suggested `_DOMAIN_ERRORS`; the final name is chosen at the architecture step, with
   the only requirement that it does not suggest "not found" alone.
2. **Reorder callable signature**. The shared helper takes a callable that receives the service
   and the current ids and returns the new ids. No caller uses the service: the full reorder
   route passes a lambda that ignores both arguments and returns the submitted ids, and the
   move route passes a function that ignores the service. The signature should only carry what
   is used (the current order of ids).
3. **Redundant `hasattr`** in `wishenka/wishlists/store.py`.

### Re-verification against current code (state after WISHENKA-111, commit ee5e12f)

| Debt item | Status | Evidence |
| --------- | ------ | -------- |
| `_NOT_FOUND_ERRORS` includes `WishlistArchivedError`, mapped to 409 | **Valid** | Tuple defined in `items_ui.py`; `_raise_http` maps the archived error to 409. No tests or `doc/dev/` mention the name. |
| `_reordered_response` callable has an unused `svc` argument | **Valid** | Callable type is `Callable[[WishlistService, list[int]], list[int]]`; the helper calls `reorder(svc, [...])`; the full-reorder caller passes `lambda _svc, _cur: item_ids` and the move caller defines `compute(_svc, current)`. |
| Redundant `hasattr(r, "warn_on_delete_reserved")` in `store.py` | **Valid, line numbers moved** | Now in the snapshot-loading code (around line 382); the select list always contains the column and the column is `NOT NULL DEFAULT 1` in the schema and in the migrations from WISHENKA-111, so the attribute always exists. |
| (not in the debt text) `hasattr(ir, "display_order")` in `store.py` | **Same defect, add to scope** | Around line 437, next to the previous one; the select list always contains `display_order` and the column is `NOT NULL DEFAULT 0`. Same reasoning, same cleanup. |

Notes on what the verification found:

- The debt text says "next to the `None` check". The `None` checks (`is not None`) are **not**
  part of this task: they are cheap value-level guards, and removing them would change loading
  behaviour for rows that bypass the schema default (for example rows written by external
  tools or old test fixtures). They stay as they are.
- Two sibling spots use the same pattern but are **outside the wording of the debt item**:
  `hasattr(row, "warn_on_delete_reserved")` in `wishenka/wishlists/repository.py`
  (`_row_to_wishlist`, whose callers select the column) and the `getattr(..., None)` for the
  same column in the single-item loading code of `store.py` (around line 893). Decision for the
  architecture step: `repository.py` is the same defect and may be cleaned in the same way if
  every row it receives provably comes from a select that includes the column; the
  `getattr(..., None)` call is a different construct and is left untouched unless it is
  trivially the same case. Whatever is decided is recorded in the architecture document. Any
  spot left alone is listed there as a reason, not forgotten.
- `hasattr` checks elsewhere (`sharing.py` role value, `items/fetcher.py` response content)
  concern different objects and are out of scope.
- The existing tests do not reference `_NOT_FOUND_ERRORS`, `_reordered_response` or the
  `hasattr` checks directly. They cover the behaviour through the HTTP routes (reorder UI,
  items CRUD UI) and through store snapshot loading.

### What to do with a debt item that turns out to be resolved or inapplicable

- If, at the architecture or development step, an item is found to be already resolved or
  not applicable (for example a `hasattr` check that guards a real case, such as rows from a
  select without the column), it is **not** changed. It is recorded with the reason in the
  roadmap sub-items and in the technical debt analysis, and removed from the acceptance
  criteria explicitly (the criterion is marked "dropped: reason"), not silently ignored.
- A check that guards a real case is kept and gets a short comment saying which case.

### Scope

In scope:

- Rename of the error group in `wishenka/web/routes/items_ui.py` and all its uses.
- Simplification of the reorder callable signature and both callers in the same file.
- Removal of redundant `hasattr` checks in `wishenka/wishlists/store.py` (both the
  `warn_on_delete_reserved` and the `display_order` checks); `repository.py` per the decision
  above.
- Developer documentation only if some document names a changed identifier (none found so far).

### Out of scope

- Any behaviour, response, status code, log event or message change.
- Migrations, schema changes, changes of selected columns, removal of `None` value guards.
- The other items of the WISHENKA-15 debt list: hardcoded `can_edit_wishlist=True`,
  `item_card.html` split, performance of full-list re-render, i18n, unpinned CDN scripts.
- Other debt tickets, including WISHENKA-125 to WISHENKA-147.
- Adding new tests for behaviour that already has coverage. A new test is added only if
  the architecture step finds a changed path without coverage.

### Constraints and assumptions

- Implementation language: Python.
- Project rules for Python and Markdown apply (type hints stay correct, no unused names left
  behind, readable naming).
- The refactor is mechanical; the diff should be small and reviewable by reading.
- Assumption: the schema guarantees from WISHENKA-111 hold for every database the store
  reads, because the store runs the migrations before reading.

## Q&A

- **Why is this task needed, if nothing changes for users?** To keep the code honest: a
  misleading name and dead defensive code cause wrong assumptions in future changes to the
  archive and reorder flows. Source: WISHENKA-15 technical debt analysis.
- **Is the archived error "not found"?** No. It is answered with 409 ("Wishlist is
  archived"). The group name must reflect that the group is "domain errors the routes
  translate", not only "not found".
- **Did WISHENKA-111 make any item obsolete?** No item is obsolete. It moved the store code
  (line numbers changed) and made the `hasattr` removal safer, because the columns are now
  guaranteed `NOT NULL` with defaults through the migrations.
- **Are the `None` checks removed too?** No, see the notes above.
- **Who approves?** No user approval gate: the autonomous runner accepts the step after an
  independent review.
