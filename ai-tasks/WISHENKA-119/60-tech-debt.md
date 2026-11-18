# WISHENKA-119: Technical Debt Analysis

## Shortcuts Taken

None introduced in `WISHENKA-119`. Production code (`wishenka/web/routes/items_ui.py`, `wishenka/i18n/catalog.py`, `wishenka/i18n/dependencies.py`, and `wishenka/web/templates/partials/item_edit_modal.html`) already implemented localized busy-error handling from `WISHENKA-89`, and `WISHENKA-119` only added parametrized regression test coverage in `tests/test_item_busy_responses.py`.

## Code Quality Issues

- **Stale docstring on `submit_edit_item` (`wishenka/web/routes/items_ui.py:623`)** — `low` (`NON-BLOCKER` for closing `WISHENKA-119`):
  - The docstring reads `"""Save item edits or re-render modal with 409 Conflict if Reduction Lock is violated."""` and omits the HTTP `503 Service Unavailable` (`InventoryBusyError`) re-render path (lines 700–724). This is pre-existing and does not affect runtime behavior.
- **Locale catalog (`wishenka/i18n/catalog.py`, `web.item.edit_busy_error` at lines 380 and 866)**:
  - Clean. Both `"en"` and `"ru"` entries state all three required facts (wish busy, edit not saved, can submit again) and preserve the surprise invariant (no gifter details).

## Missing Tests

- **`Accept-Language: ru` HTTP header fallback path on `submit_edit_item` (`tests/test_item_busy_responses.py`)** — `low` (`NON-BLOCKER` for closing `WISHENKA-119`):
  - `test_item_edit_busy_renders_submitted_fields` verifies the `"ru"` locale via `user_store.set_locale(OWNER_ID, "ru")` (profile locale path in `get_request_locale`), and `en-default` when no user locale is set.
  - It does not directly exercise `POST /web/wishlists/{wishlist_id}/items/{item_id}/edit` with an `Accept-Language: ru` HTTP header when the user has no persisted `UserRecord` in `user_store`.
  - Low risk because `get_request_locale` (`wishenka/i18n/dependencies.py:42-46`) and `resolve_accept_language` are already covered by `tests/test_i18n_unit.py` and `tests/test_i18n_sync.py`.
- **Timeout markers**:
  - Clean. `tests/test_item_busy_responses.py:25` defines `pytestmark = pytest.mark.timeout(30)`.

## Performance Concerns

None. `submit_edit_item` uses `LocaleDep` (already resolved per request) and an in-memory catalog lookup (`t("web.item.edit_busy_error", locale)`) on `InventoryBusyError`, adding negligible overhead.

## Follow-up Tasks

No **BLOCKER** items exist for closing `WISHENKA-119`. Optional low-priority follow-ups (`NON-BLOCKER`):

1. **[`low` / `NON-BLOCKER`] Add `Accept-Language: ru` header case to `tests/test_item_busy_responses.py`** -> [WISHENKA-208](https://pypost.atlassian.net/browse/WISHENKA-208): Exercise `submit_edit_item` returning HTTP 503 with the Russian busy alert when `Accept-Language: ru` is sent without a persisted `UserRecord` locale.
2. **[`low` / `NON-BLOCKER`] Update `submit_edit_item` docstring in `wishenka/web/routes/items_ui.py`** -> [WISHENKA-208](https://pypost.atlassian.net/browse/WISHENKA-208): Document the HTTP 503 `InventoryBusyError` modal re-render behavior alongside 409 Conflict.
