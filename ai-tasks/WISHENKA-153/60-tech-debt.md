# WISHENKA-153: Technical Debt Analysis

## Shortcuts Taken

1. **Dual notification pipelines (`notification_outbox` vs `reminder_outbox`):**
   - Initial receipt creation (`record_item_fulfillment`) writes to `notification_outbox` / `notice_receipt_keys` (which have `ON DELETE CASCADE` on `wl_receipts(id)` and a `(event_type, receipt_id, giver_user_id)` uniqueness constraint), whereas receipt cancellation and quantity correction (`receipt_reverted`, `receipt_increased`) are routed through `SharedEvent` / `reminder_outbox` in `wishenka/notices/events.py` and `wishenka/notices/reminders.py`.
   - While this cleanly avoided an Alembic migration and works reliably in `NoticeWorker.run_once()`, gift-receipt notifications are now split across two outbox tables and two authorization/rendering code paths.

2. **Reusing `ReceiptResultDTO.received_now` for `DELETE` and `PATCH`:**
   - In `wishenka/web/routes/receipts.py`, `cancel_receipt` (`DELETE`) returns `received_now=0` and `correct_receipt` (`PATCH`) returns `received_now=payload.quantity` (even when `new_quantity == old_quantity`, a no-op). `received_now` was originally named for newly recorded units; reusing `ReceiptResultDTO` avoids introducing a separate response schema, at the cost of slightly overloaded field semantics.

3. **Repurposing `form.dataset.idempotencyQty` for cancel forms in `wishenka/web/static/receipt.js`:**
   - `submitReceipt` falls back to `const qty = field ? field.value : 'cancel';` and stores it in `form.dataset.idempotencyQty` when a form has no `quantity` input (the cancel confirmation modal). Works as intended, but the dataset attribute name and JSDoc comments in `receipt.js` still reflect the original WISHENKA-24 record-only dialog.

4. **Repro test module docstring/filename:**
   - `tests/test_receipt_undo_correction_repro.py` retains its Step 3 docstring (`"Red failing repro tests for WISHENKA-153..."`) even though all 5 tests now serve as permanent regression tests.

## Code Quality Issues

1. **Duplicate open-promise giver filtering in `wishenka/wishlists/service.py`:**
   - `_record_receipt_change_event` (lines 356–365) and `_draft_receipt_notices` (lines 379–385) both iterate `item.reservations` with the same `ACTIVE`/`PURCHASED` + distinct `user_id` + `not WishlistAccessPolicy.is_recipient_id(...)` filter. Extracting a small helper (e.g. `_open_promise_giver_ids(item)`) would remove the duplication.

2. **Defensive `max(0, ...)` clamping in `wishenka/wishlists/service.py`:**
   - `cancel_item_receipt` (line 2592) and `correct_item_receipt` (line 2653) compute `item.received_quantity = max(0, ...)` instead of recomputing from `sum(r.quantity for r in item.receipts)` or asserting consistency. While safe, recomputing from `item.receipts` would guarantee `item.received_quantity` can never drift from `wl_receipts`.

3. **Idempotency key hash shape and replay logging in `wishenka/web/routes/receipts_ui.py`:**
   - `_execute_receipt_mutation_ui` (line 672) places `receipt_id` inside `request_hash_payload` (`{"receipt_id": receipt_id, ...}`) while `receipts.py` places `receipt_id` in the path dictionary. Both are deterministic, but keeping the same convention across JSON and UI routes is cleaner.
   - Additionally, `_execute_receipt_mutation_ui` (lines 690–696) emits `receipt_corrected_http` / `receipt_cancelled_http` `INFO` logs after `execute_wish_idempotent` even when the response is an idempotent replay rather than a fresh mutation.

4. **Stale file-level comments in `wishenka/web/static/receipt.js`:**
   - Header comment (line 2) still references only `WISHENKA-24` and `submitReceipt` JSDoc (line 136) still says `"Send the chosen quantity (the only field) once"`.

## Missing Tests

1. **Timeout markers check:** All 5 receipt/UI test files (`tests/test_receipt_undo_correction_repro.py`, `tests/test_gift_receipt_api.py`, `tests/test_gift_receipt_service.py`, `tests/test_gifted_section_ui.py`, `tests/test_receipt_ui_routes.py`) declare explicit module-level `pytestmark = pytest.mark.timeout(...)` — no timeout-marker blocker.
2. **Idempotency replay & conflict on new endpoints:** No dedicated test exercises `Idempotency-Key` replay (200 cached response without double-mutation or duplicate notice) and `IdempotencyConflictError` (409) on `DELETE / PATCH /api/wishlists/{wishlist_id}/items/{item_id}/receipts/{receipt_id}` or `POST .../edit` and `POST .../cancel` UI routes.
3. **Cross-item `receipt_id` isolation:** No explicit test verifies that passing a valid `receipt_id` belonging to a *different* `item_id` (or `wishlist_id`) returns `404 receipt_not_found` without modifying the other item's receipt.
4. **No-op `PATCH` and UI `POST .../edit` with unchanged quantity:** `WishlistService.correct_item_receipt` no-op behavior is tested at the service layer, but not explicitly through the `PATCH` JSON endpoint or `POST .../edit` UI route.
5. **UI `GET .../edit` and `GET .../cancel` error states:** No test directly checks `GET .../edit` or `GET .../cancel` returning `404` (`X-Receipt-Refusal: receipt_not_found`) when the receipt was concurrently deleted, or `409` (`blocked=True`) on an archived list.
6. **Client-side JS coverage for `receipt.js`:** No automated JS/DOM test covers `submitReceipt` when `quantity` is absent (cancel modal) or `REFUSAL_REASONS.has('receipt_not_found')` in `htmx:beforeSwap`.

## Performance Concerns

1. **Full-wishlist OOB re-render on every UI receipt edit/cancel (`wishenka/web/routes/receipts_ui.py`):**
   - `_read_full_mutation_state` and `_render_mutation_oob` re-query and re-render all three sections (`#items-list`, `#gifted-items-section`, `#archived-items-section`) on every `POST .../edit` and `POST .../cancel`. This matches existing `record_receipt_ui` behavior and is fast for typical wishlists, but could become noticeable on lists with hundreds of items.

## Follow-up Tasks

1. **Unify gift-receipt outbox or document split:** Either keep `reminder_outbox` for `receipt_reverted`/`receipt_increased` permanently (documenting the split) or migrate `notification_outbox` in a future schema pass if all receipt notices need unified tracking. Jira: [WISHENKA-216](https://pypost.atlassian.net/browse/WISHENKA-216)
2. **Extract `_open_promise_giver_ids` helper in `wishenka/wishlists/service.py`:** Deduplicate the open-promise giver selection between `_record_receipt_change_event` and `_draft_receipt_notices`. Jira: [WISHENKA-215](https://pypost.atlassian.net/browse/WISHENKA-215)
3. **Add missing edge-case tests:** Cover `Idempotency-Key` replay/conflict on `DELETE`/`PATCH` and UI `edit`/`cancel`, cross-item `receipt_id` isolation, and `GET .../edit|cancel` refusal responses. Jira: [WISHENKA-217](https://pypost.atlassian.net/browse/WISHENKA-217)
4. **Pre-existing failure (`NON-BLOCKER — pre-existing`):**
   - `tests/test_receipt_static_script.py::test_inline_script_is_unchanged_and_free_of_receipt_code` (failing at base commit `f72e804`, unrelated to WISHENKA-153).
   - Jira: [WISHENKA-214](https://pypost.atlassian.net/browse/WISHENKA-214)
