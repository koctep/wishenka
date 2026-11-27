# WISHENKA-214: Technical Debt Analysis

No blocker against this task's acceptance criteria. Edit and archive
refusals still surface in the open dialog. A gift-receipt refusal, including
one outside the swapped reason set, is claimed in `receipt.js` before shared
dialog handling runs. `app.js` steps aside on `detail.skipSharedDialog` and
on `[data-own-feedback]`, and the shared script contains no gift-receipt
token. Reorder and reservation exclusions are unchanged.

Reviewed: `wishenka/web/static/app.js` (`htmx:beforeSwap`,
`sharedFeedbackApplies`, the failure listeners), `wishenka/web/static/receipt.js`
(capture `htmx:beforeSwap` and `htmx:responseError`), the three receipt
dialog roots (`partials/item_receipt_modal.html`,
`partials/receipt_edit_modal.html`, `partials/receipt_cancel_modal.html`),
`tests/test_receipt_static_script.py`, `20-architecture.md`,
`40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

None that weaken the acceptance criteria. The owner-claim is the design in
`20-architecture.md`: `receipt.js` sets `detail.skipSharedDialog` in the
capture phase for every `X-Receipt-Refusal` value, opts into the swap only
for `REFUSAL_REASONS`, and stops `htmx:responseError` when that header is
present. `app.js` returns on the flag and treats
`[data-own-feedback]` as already reported. Server status, sentences, and
`X-Receipt-Refusal` stay as they were. htmx 2 `responseHandling` stays
unused because `base.html` pins htmx 1.9.12. That limit is the architecture,
and it is not a follow-up.

## Code Quality Issues

None that need a follow-up.

`skipSharedDialog` is a property on the htmx event detail, set only from
`receipt.js` and read only from `app.js`. The two classic scripts do not
share a module, so the name is the interface. `[data-own-feedback]` sits on
the three `#item-receipt-modal` roots and is what shared pending and
`#feedback` consult. Edit and archive partials stay unmarked.

The capture listener does not stop `htmx:beforeSwap`. `wishlist.js` still
cancels an in-progress touch reorder when the swap target is `#items-list`.
`X-Reorder-Refusal` and `reservationRequestPath` remain the other early
returns in `app.js`.

## Missing Tests

No `do-testing` blocker. `tests/test_receipt_static_script.py` declares
`pytestmark = pytest.mark.timeout(30)` at module scope, which covers
`test_shared_app_script_has_no_gift_receipt_reference`. That test compares
raw and comment-stripped `/static/app.js` case-insensitively and rejects
`X-Receipt-Refusal`, `.receipt-sheet`, and the substring `receipt`.
`tests/test_receipt_modal_browser.py` declares
`pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`.

`test_before_swap_override_is_guarded_and_closed` dispatches
`htmx:beforeSwap` with `target` set to `document.body`. A closed receipt
reason sets `shouldSwap` and clears `isError`. An unknown
`X-Receipt-Refusal` (`stale_order`, `something_else`), a reorder header,
an empty header map, and a detail without `xhr` leave the flags at
`[false, true]`.

`app.js` opts into a swap only for a modal target
(`#item-modal-container`, `#item-edit-sheet`, `#item-archive-modal`), a
trigger inside `#item-modal-container`, or an `#items-list` response that
carries an out-of-band modal. `document.body` is none of those, so an
unknown header that remains `[false, true]` still passes if the
`skipSharedDialog` early return is deleted. The return exists for a
modal-targeted `X-Receipt-Refusal: idempotency_conflict`. `receipt.js`
sets `detail.skipSharedDialog` and does not opt in, because
`idempotency_conflict` is outside `REFUSAL_REASONS`. No test uses a modal
target with that header. Deleting the early return would leave
`test_before_swap_override_is_guarded_and_closed` green and let `app.js`
swap that error.

Nothing asserts `data-own-feedback` on the three `#item-receipt-modal`
roots (`partials/item_receipt_modal.html`,
`partials/receipt_edit_modal.html`, `partials/receipt_cancel_modal.html`),
and nothing asserts that `#feedback` stays empty.
`test_new_handlers_guard_a_missing_xhr` checks the `getResponseHeader`
guard on the `receipt.js` `htmx:beforeSwap` handler. The capture
`htmx:responseError` listener that calls `stopPropagation` is outside
that assertion. Archive `nothing_remaining` is outside
`[data-own-feedback]`, so shared `#feedback` depends on that stop.

The receipt, reorder, reservation, and dialog browser tests from Step 4
remain the behavioral net for the dialog sentence, the receipt notice, and
the neighboring flows.

## Performance Concerns

None. The change adds one capture `htmx:beforeSwap` listener and one capture
`htmx:responseError` listener on `document`. Each reads one response header
and returns. No new wait, poll, or server round trip.

## Follow-up Tasks

- Add a test for the receipt claim seam. Jira:
  [WISHENKA-355](https://pypost.atlassian.net/browse/WISHENKA-355).
  Dispatch
  `htmx:beforeSwap` at a modal target with
  `X-Receipt-Refusal: idempotency_conflict` and assert `app.js` leaves
  `shouldSwap` and `isError` untouched after `receipt.js` sets
  `skipSharedDialog` and does not opt in. Assert `data-own-feedback` on
  the three `#item-receipt-modal` roots. Assert the capture
  `htmx:responseError` listener calls `stopPropagation` when that header
  is present, so `#feedback` stays empty. Archive `nothing_remaining`
  sits outside `[data-own-feedback]`, so shared `#feedback` depends on
  that stop.

Developer docs under `doc/dev/` still describe the previous shared-handler
exclusion (`.receipt-sheet` and `X-Receipt-Refusal` inside `app.js`). That
update belongs to Step 8. User documentation under `doc/` was left unchanged.
This task does not add a screen, a sentence, or a role rule.

### Pre-existing test failures

Recorded from Step 4. Both fail at `1acdffc` with `PageWaitTimeout`. This
step did not re-run them and did not change them. They are
`NON-BLOCKER — pre-existing`.

- `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
  — NON-BLOCKER — pre-existing. `PageWaitTimeout`. Jira:
  [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220)
- `tests/test_receipt_modal_browser.py::test_busy_keeps_dialog_and_chosen_quantity`
  — NON-BLOCKER — pre-existing. `PageWaitTimeout` waiting for the busy
  sentence. Jira:
  [WISHENKA-354](https://pypost.atlassian.net/browse/WISHENKA-354)
