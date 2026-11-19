# WISHENKA-209: Technical Debt Analysis

## Shortcuts Taken

- **`quantity` parsed by FastAPI `Form()` as `int` instead of `str | None`**: In `submit_new_item` (and `submit_edit_item`) in `wishenka/web/routes/items_ui.py`, `quantity: Annotated[int, Form()] = 1` is validated by FastAPI/Pydantic before entering `_parse_item_modal_form`. If a client submits a non-numeric or empty `quantity`, FastAPI returns a `422 Unprocessable Entity` JSON response rather than re-rendering the modal with a `400` error banner and preserved form state (unlike `price` and `recipient_user_id`, which are accepted as `str | None` and parsed via `_parse_optional_int`).
- **Pre-existing `submit_edit_item` form-error path not aligned with `submit_new_item`**: In `submit_new_item`, form-level validation errors (`parsed.validation_error is not None`) still execute the wishlist lookup so `is_collaborative_snapshot` and `collaborative_members_snapshot` are preserved in the re-rendered modal. In `submit_edit_item`, the early return on `parsed.validation_error is not None` still passes hardcoded `is_collaborative=False`, `collaborative_members=[]`, and `min_quantity=1`. Left untouched in WISHENKA-209 to keep scope focused on the Create Item modal.
- **`store_name` not carried through the Create Item modal**: `quick_add_item` accepts `store_name` from URL preview metadata, whereas `get_new_item_modal` and `submit_new_item` do not accept or preserve `store_name`.

## Code Quality Issues

- **Duplicate form-parsing logic in `quick_add_item`**: `quick_add_item` in `wishenka/web/routes/items_ui.py` still performs inline `_parse_optional_int`, `_parse_priority`, and string stripping instead of reusing `_parse_item_modal_form` (which is shared between `submit_new_item` and `submit_edit_item`).
- **Empty-string coercion asymmetry**: `_parse_item_modal_form` sets `clean_desc`, `clean_link`, `clean_image`, `clean_cat`, and `clean_recip_name` to `""` when submitted as empty strings. `submit_new_item` explicitly converts them with `or None` before calling `svc.add_wish_item(...)`, whereas `submit_edit_item` passes the raw `parsed.clean_*` values to `svc.update_wish_item(...)`.
- **Currency and priority normalization on error re-render**: In `wishenka/web/templates/partials/item_edit_modal.html`, `CURRENCY_OPTIONS` comparison uses exact equality `(form.currency or DEFAULT_CURRENCY) == code` (no `.upper()` normalization in `_parse_item_modal_form`), and an invalid `priority` string causes none of the `<option>` elements to be marked `selected`.
- **TemplateResponse boilerplate**: `get_new_item_modal` and `get_edit_item_modal` duplicate `templates.TemplateResponse("partials/item_edit_modal.html", ...)` context construction that could share a small rendering helper with `_render_item_modal_error`.

## Missing Tests

- **Timeout markers**: `tests/test_wishenka_209_create_modal_repro.py` declares `pytestmark = pytest.mark.timeout(30)` at module level (no blocker).
- **Missing `POST /web/wishlists/{wishlist_id}/items/new` `201 Created` happy-path test**: No test in `tests/test_wishenka_209_create_modal_repro.py` or `tests/test_wish_items_tma_ui.py` exercises a successful `POST /items/new` submission verifying `201 Created`, rendered `item_card.html`, and OOB resets (`#quick-add-preview-target`, `#quick-add-input`, `#empty-items-placeholder`, `#item-modal-container`).
- **Missing domain error (`404`/`409`) tests for `POST /items/new`**: No test covers `WishlistArchivedError` (`409` OOB notice), `PermissionDeniedError`, `WishlistNotFoundError`, or `WishlistDeletedError` (`404` OOB notice) on `POST /items/new`.
- **Missing invalid-priority `400` test on `POST /items/new`**: `_parse_priority` error handling is not exercised for `POST /items/new` in `tests/test_wishenka_209_create_modal_repro.py`.
- **Missing non-numeric `recipient_user_id` test on collaborative `POST /items/new`**: The `|string` comparison in `item_edit_modal.html` is tested for valid numeric `CO_AUTHOR_ID`, but not for an invalid non-numeric `recipient_user_id` string.

## Performance Concerns

- **Extra wishlist read on form-level validation errors**: `submit_new_item` executes `_execute(request, action)` to read the wishlist and collaborative members even when `parsed.validation_error is not None`, in order to preserve collaborative recipient `<select>` options on `400` responses. This is a single primary-key lookup (and enforces membership/active status before rendering the modal), so the overhead is negligible.

## Follow-up Tasks

- **Handle `quantity` as `str | None` in `_parse_item_modal_form`**: Accept `quantity` as `str | None` in `submit_new_item` and `submit_edit_item` so non-numeric/empty quantity submissions return a `400` modal re-render instead of FastAPI `422` JSON. — Jira: [WISHENKA-273](https://pypost.atlassian.net/browse/WISHENKA-273)
- **Align `submit_edit_item` form-level `400` error handling**: Preserve `is_collaborative`, `collaborative_members`, and `min_quantity` on form-level validation errors in `submit_edit_item` (matching `submit_new_item`). — Jira: [WISHENKA-272](https://pypost.atlassian.net/browse/WISHENKA-272)
- **Add missing `POST /items/new` tests**: Cover `201 Created` happy path (card + OOB resets), `404`/`409` domain error OOB notices, invalid `priority` `400`, and non-numeric `recipient_user_id` on collaborative wishlists. — Jira: [WISHENKA-274](https://pypost.atlassian.net/browse/WISHENKA-274)
- **Unify `quick_add_item` form parsing**: Refactor `quick_add_item` to reuse `_parse_item_modal_form` (or a shared base parser) and eliminate duplicated parsing/stripping logic. — Jira: [WISHENKA-275](https://pypost.atlassian.net/browse/WISHENKA-275)
