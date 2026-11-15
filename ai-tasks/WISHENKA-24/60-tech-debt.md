# WISHENKA-24: Technical Debt Analysis

Scope: the uncommitted change set of WISHENKA-24 (Steps 3 to 6) over HEAD `7fb5503`: the page layer of the
gift receipt (receipt dialog, owner card badge and button, «Подаренные» section, cabinet marker, refusal
and busy states) on top of the WISHENKA-23 contract. Production: `wishenka/web/gifted_view.py`,
`routes/receipts_ui.py`, `static/receipt.js`, `partials/item_receipt_modal.html`,
`partials/gifted_items_section.html`, and the edits in `items_ui.py`, `sharing.py`, `app.py`, `base.html`,
`wishlist.js`, `miniapp.css`, four partials and `wishlist_detail.html`. Tests: six new `test_*` modules,
`receipt_ui_support.py`, `browser_helpers.py`, `htmx_stub.js`. Nothing was changed in code or tests in this
step. The untracked `core` file (WISHENKA-126) and `ai-tasks/sprint-2110/` are not part of this change set.

Verdict: **no BLOCKER for closing WISHENKA-24.** No invariant is endangered: the surprise secrecy
(gifted, dialog and OOB fragments carry no booking or giver data; asserted by the T-2 to T-5 tests and the
log scan), XSS (all titles and sentences go through autoescape or `Markup.format`; `receipt.js` writes only
`textContent`), and data loss (receipts are recorded only by the existing service; the UI adds no write path).
Everything below is NON-BLOCKER. One of the carried findings is a pre-existing user-facing Bug
(older modals do not show 409/503 errors), not caused by this story.

## Python test-timeout rule

Outcome: **satisfied, no BLOCKER.** Checked with `ast` over every file added or changed by this task:

| File | Test functions | Timeout marker |
| ---- | :------------: | -------------- |
| `tests/test_receipt_ui_routes.py` | 16 (parametrised to 38) | module `pytestmark = pytest.mark.timeout(...)` |
| `tests/test_receipt_card_ui.py` | 12 | module mark |
| `tests/test_gifted_section_ui.py` | 9 | module mark |
| `tests/test_cabinet_received_marker.py` | 6 | module mark |
| `tests/test_receipt_static_script.py` | 9 | module mark |
| `tests/test_receipt_modal_browser.py` | 9 | `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]` (line 45) |
| `tests/test_receipt_ui_observability.py` | 1 | `pytestmark = pytest.mark.timeout(60)` (line 42) |
| `tests/receipt_ui_support.py`, `tests/browser_helpers.py`, `tests/browser_assets/htmx_stub.js` | 0 (helpers) | not applicable |

- `.venv/bin/pytest --collect-only -q -m "not timeout"` collects 0 tests (798 deselected): no collected test
  in the whole suite lacks a marker.
- Bounded waits in the browser tests: every `page.wait_for` has the default 5 s deadline
  (`browser_cdp.py:299`) or an explicit 3 or 10 s (`browser_helpers.py:244, 256, 268`); the local `_wait_until`
  is bounded by `timeout=6.0` (`test_receipt_modal_browser.py:90-103`); the quiet-period loop at 541-544 is
  bounded by a 2 s deadline. No unbounded loop or wait found.
- Residual: the quiet-period check in `test_unmarked_error_neither_shows_notice_nor_reloads` spends a fixed
  2 s of wall-clock time (negative assertion by waiting); acceptable, noted in T-6.

## Shortcuts Taken

| # | Shortcut / assumption | Where | Class | Priority | Disposition |
| - | --------------------- | ----- | :---: | :------: | ----------- |
| S-1 | The browser tests run the own htmx stub, never real htmx. The stub was extended (`beforeSwap` detail with `xhr`, `shouldSwap`, `isError`, `responseError`, `swap: 'none'`, OOB swaps) to imitate real htmx 1.9.12. Divergences that are still true: B-3 gates `window.fetch` (`test_receipt_modal_browser.py:220-257`) but real htmx sends XHR, so the gate would not hold a request under real htmx; the `assert_clean_console` assertions of B-1 to B-6 (lines 172, 213, 282, 325 and others) would fail under real htmx because it logs `console.error` for every unswapped 4xx; the stub swaps nothing for status >= 400 (`htmx_stub.js:112` and the swap guard after it) so its header text "all additive, the old contract is kept" (`htmx_stub.js:12`) is not strictly true any more (older tests that expected a swap of an error body would now differ) | `tests/browser_assets/htmx_stub.js`, `tests/test_receipt_modal_browser.py` | NON-BLOCKER | Medium | Existing WISHENKA-145 (real-htmx smoke test, vendored copy). Add to its scope: a real-htmx receipt run (open dialog, partial and full receipt, a marked refusal, `beforeSwap` override), plus fixing the stub docstring (T-1) |
| S-2 | The stub docstring claims additivity; see S-1 (text only) | `tests/browser_assets/htmx_stub.js:12` | NON-BLOCKER | Low | Folded into T-1 (docstring and the fetch-gate note) |
| S-3 | Focus is not returned to the card after a successful receipt: the dialog container is emptied by the OOB swap and the card is replaced (`receipt.js` `closeDialog` runs only for Cancel, Escape and the backdrop; `openerCardId` is never used after success). Keyboard and screen-reader users land on `body` | `receipt.js:46-55`, POST response of `receipts_ui.py:366-376` | NON-BLOCKER | Medium | NEW (T-2) |
| S-4 | Accepted limits of the dialog, none tested: no focus trap (Tab leaves the dialog to the page behind, which is not `inert`), no `aria-modal`, `<details>` of «Подаренные» re-collapses after every OOB swap, the quantity `<select>` lists every number from 1 to remaining (a wish of quantity 500 renders 500 options) | `item_receipt_modal.html:1-2, 18-22`, `gifted_items_section.html:6` | NON-BLOCKER | Low | NEW (T-2): one a11y and UX unit with S-3 |
| S-5 | The edit-modal archive button has no `hx-target` (`item_edit_modal.html:180`), so a marked 409 (OOB-only body) swaps whitespace into the button via the default self target. Harmless today because the body is OOB-only, but fragile | `item_edit_modal.html:180`, `items_ui.py` `_nothing_remaining_response` | NON-BLOCKER | Low | NEW (T-3), merged with the older-modal fix |
| S-6 | `receipts_ui.py` imports the private name `receipts._REFUSALS` (`receipts_ui.py:29`, loop at 66) to keep the status and reason table in one place. It is read-only, but the contract is an underscore name; WISHENKA-158 (split of receipt code) must keep it importable or provide a public accessor | `wishenka/web/routes/receipts_ui.py:29, 66`, `wishenka/web/routes/receipts.py:38` | NON-BLOCKER | Low | Existing WISHENKA-158 (real scope: split receipt code out of `service.py`, unify flush sites in `store.py`) does not cover web-layer imports: carry the constraint as a note on 158 (the receipt module move must keep `receipts._REFUSALS` importable) and the web-side rename to a public name is a line of T-4 |
| S-7 | `receipts_ui.py` also imports three private helpers of `items_ui.py` (`_editor_card_flags`, `_execute`, `_items_list_html`, line 28): cross-module use of underscore names | `receipts_ui.py:28` | NON-BLOCKER | Low | NEW (T-4) |
| S-8 | New Russian texts have not been reviewed by the product owner or a language reviewer: the ten refusal and notice sentences (`receipts_ui.py:46-55, 374`), the dialog, the gifted section, the stale-card text (`wishlist.js:547`), the reorder notice (`wishlist.js:564`), the archive sentence (`item_archive_modal.html`), the cabinet marker «Желание получено владельцем». Specifically the pluralisation: «шт.» is used with every number (no declension), and the summary «Будет отмечено получено: N шт. из M оставшихся» is grammatically stiff | see list | NON-BLOCKER | Low | Existing WISHENKA-33 for RU/EN rendering; a one-time wording review is NEW (T-5) |
| S-9 | Pre-existing defect, not introduced here: htmx 1.9.12 does not swap 4xx and 5xx responses by default, so older modals that answer an error with a re-rendered form show nothing. Confirmed in the code: edit-modal 409 (quantity below booked) and 503 busy re-render (`items_ui.py` edit handler, body is the modal with `error_message`), archive 409 (`_raise_http`), reorder 400 are all invisible to the user. This story fixed only its own paths (marked receipt refusals via the `beforeSwap` override, stale reorder via `responseError`, stale archive/restore via an OOB-only 409). Dedupe check: no `60-tech-debt.md` under `ai-tasks/` mentions it. The nearest ticket is WISHENKA-90 (global `htmx:responseError` toast, from WISHENKA-51), which names the symptom class but not this defect; its description is notification toasts for network failures, not rendering the server's own error fragment | `wishenka/web/templates/partials/item_edit_modal.html` and the item error handlers in `items_ui.py`, `wishlist.js:552-567` | NON-BLOCKER | **High** (user-visible data-entry failure) | NEW Bug (T-3). Propose to link it to WISHENKA-90 or fold it into one general `beforeSwap` policy for error fragments |
| S-10 | `.modal-backdrop` and `.modal-sheet` have no CSS anywhere (the Tailwind utility classes on the older modals are never loaded: `base.html` links only `/static/miniapp.css` and no Tailwind script). So the edit modal and the archive modal render as plain unstyled blocks in the page flow; the archive confirm button is covered by the fixed quick-add bar (`.quick-add-container` z-index 40). The receipt modal is styled by its own `.receipt-backdrop` and `.receipt-sheet` (`miniapp.css`, z-index 100) and is not affected | `wishenka/web/templates/partials/item_edit_modal.html:1-3`, `item_archive_modal.html:1-3`, `miniapp.css` | NON-BLOCKER | Medium | NEW Bug (T-3), same ticket as S-9: both are "older modals are not usable on mobile" (edit/archive modals) |
| S-11 | Success notice composed with an f-string in the route: `f"Отмечено получено: {count} шт. («{done.title}»)"` (`receipts_ui.py:374`). Escaped by `oob_text` (`Markup.format`), tested with `<script>` titles, so not an XSS; the style is the exception in a module that otherwise keeps texts in `_SENTENCES` | `receipts_ui.py:374` | NON-BLOCKER | Low | T-4 (move to the sentence table) |

## Code Quality Issues

| # | Issue | Where | Class | Priority | Disposition |
| - | ----- | ----- | :---: | :------: | ----------- |
| C-1 | Duplicated assembly of the list, archive and gifted OOB fragments: `items_ui._nothing_remaining_response` (`items_ui.py:840-885`, wrapper at 872, gifted include at 876) rebuilds the `innerHTML:#items-list` wrapper and the gifted include inline, while `receipts_ui._list_oob` and `_gifted_oob` (lines 270-286) do the same through helpers. Two places must change together | `items_ui.py:870-880`, `receipts_ui.py:270-286` | NON-BLOCKER | Low | NEW (T-4): move `_list_oob`/`_gifted_oob` next to `oob_text` in `gifted_view.py` and use them in both |
| C-2 | `view_wishlist_detail` inner `action` now returns a six-element tuple (`items_ui.py:132-158`); the unpacking block is hard to read and one more flag means another tuple slot | `items_ui.py:132-160` | NON-BLOCKER | Low | T-4 (small frozen dataclass of the page state) |
| C-3 | `receipts_ui.py` is 376 lines with three 40 to 60 line functions: `_effect_fragments` (about 55), `get_receipt_dialog` (about 45) and `record_receipt_ui` (about 55). Dense, but each is a flat sequence with one decision per branch; no function is above the project limit | `receipts_ui.py:285-376` | NON-BLOCKER | Low | Accepted; revisit when WISHENKA-158 reshapes the receipt modules |
| C-4 | Selectors, ids and header names are repeated across layers with no shared source. `#item-modal-container` (`wishlist_detail.html:45`, `receipts_ui.py:375`, `receipt.js:12`, `items_ui.py` `oob_text("item-modal-container")`, archive modal `onclick`), `#list-notice` (template, `receipts_ui.py:374`, `items_ui.py:863`, `wishlist.js:562`), `#receipt-feedback` (template, `receipts_ui.py`, `receipt.js:16`), `X-Receipt-Refusal` (`gifted_view.py:15`, `receipt.js:17`), `X-Reorder-Refusal` (`items_ui.py:897`, `wishlist.js:23`), `/web/wishlists/{id}/items/{id}/receipt` (template line 12, route prefix). The refusal reason set exists three times: `receipts._REFUSALS`, `_SENTENCES` (Python) and `REFUSAL_REASONS` (`receipt.js:20-29`). Guarded only by the closed-set test `test_receipt_static_script` | see list | NON-BLOCKER | Low | NEW (T-4): one constants module for Python, a `data-` attribute or a rendered JSON of the reasons for the script; keep the closed-set test |
| C-5 | Visible texts are duplicated between the template and the script: «Будет отмечено получено: N шт. из M оставшихся» (`item_receipt_modal.html:23, 27`, `receipt.js:74`) and the generic failure sentence in `receipt.js:18` (the server has its own busy sentence in `_SENTENCES`) | `item_receipt_modal.html`, `receipt.js:18, 74` | NON-BLOCKER | Low | T-4 / WISHENKA-33 (i18n touches both) |
| C-6 | Hardcoded presentation values: `STALE_RELOAD_DELAY_MS = 800` and the two notice texts (`wishlist.js:24, 547, 564, 566`), CSS magic numbers (`z-index: 100`, `44px`, `42rem`, `90vh`, `max-height`, hex colours `#b91c1c`, `#15803d`, `#b45309`, `#dcfce7`, `#fef3c7` in `miniapp.css`, none through `--tg-theme-*` variables except the sheet background), the default currency `'RUB'` repeated (`gifted_view.py:58`, `archived_items_section.html:14`, `item_card.html:151`, `item_preview_card.html:8, 47`, `item_edit_modal.html:68`), and the hardcoded currency list RUB, USD, EUR, KZT, BYN with symbols in `item_edit_modal.html:67-68` (pre-existing, not touched here, but the same constant belongs in the shared currency source). The `RUB` default is pre-existing in the templates; the new copy is in `gifted_view.py` | see list | NON-BLOCKER | Low | NEW (T-6): CSS tokens and one `DEFAULT_CURRENCY`; dark theme check of the new colours (the Telegram theme variables are not used for text colours) |
| C-7 | `receipt.js` `submitReceipt` wraps `htmx.ajax` in `new Promise(resolve => resolve(...)).then(done, done)` to treat a synchronous throw and a rejection alike; readable but unusual, and `htmx.ajax` returns a promise in 1.9.12 only | `receipt.js:149-157` | NON-BLOCKER | Low | Accepted; revisit with the htmx upgrade (WISHENKA-145) |
| C-8 | Pre-existing `console.warn` calls in `wishlist.js` lines 107 and 143 (not new; listed by the Step 6 note) remain; the new code added none | `wishlist.js:107, 143` | NON-BLOCKER | Low | Accepted, pre-existing; falls under the client error reporting of WISHENKA-90 |
| C-9 | Observability notes from Step 6 that are not defects: pre-existing `ui_items_reorder_rejected` carries `user_id` next to `actor_id` (not on the receipt path); `ui_receipt_form_refused` and `receipt_refused` share the message "Receipt refused" (consumers must use `event`); the shared event names (`receipt_refused`, `receipt_inventory_busy`) are written by both the JSON route and the UI route on different loggers, so a metric derived by event name only double-counts and must filter by logger | `items_ui.py` reorder log, `receipts_ui.py:100`, `routes/receipts.py` | NON-BLOCKER | Low | Existing WISHENKA-157 (log-contract hardening, T3 of WISHENKA-23); add to its scope. No new ticket |
| C-10 | Roadmap cosmetics: sub-items of STEPS 1 to 4 keep `[/]` marks under `[x]` steps | `ai-tasks/WISHENKA-24/00-roadmap.md` | NON-BLOCKER | Low | Orchestrator close-out; no ticket |

## Missing Tests

| # | Gap | Class | Priority | Disposition |
| - | --- | :---: | :------: | ----------- |
| M-1 | No test ever runs real htmx (see S-1). The server markup is checked in `TestClient` tests and the script in a stub page; the connection (`hx-get` on the card button, `hx-swap-oob` of the card with `outerHTML`, `beforeSwap` override with the real `xhr`, the `htmx-request` classes, the CSRF header from `htmx:configRequest`) was verified once by hand in a scratch copy at Step 4 review (Chromium, htmx 1.9.12), not in the committed suite | NON-BLOCKER | Medium | Existing WISHENKA-145; extend its scope as in S-1 |
| M-2 | Focus: only "focus moves into the dialog" and "focus returns after Cancel/Escape" are tested (B-1). Not tested: focus after a successful receipt (S-3), after a refusal that replaces the dialog, tab order, a focus trap | NON-BLOCKER | Medium | T-2 |
| M-3 | Mobile and touch: no browser test of the dialog at phone width (412 px viewport is the default of the CDP page, so the sheet is exercised only there), of the 44 px touch targets, of the safe-area padding, or of the dialog covering the fixed quick-add bar (the visual overlay is only guaranteed by the `z-index: 100` rule, with no computed-style assertion) | NON-BLOCKER | Low | T-2 (add one overlay and touch-target assertion) |
| M-4 | Russian text: texts are asserted by exact string in tests, so a wording change updates many tests; there is no test of the plural forms because the texts do not decline (S-8). No test for a very long title in the dialog and the gifted row (CSS `overflow-wrap` on `.receipt-wish` only) | NON-BLOCKER | Low | T-5 |
| M-5 | Error paths not covered: a network failure (`htmx:sendError`) or an unclassified 500 in the receipt POST leaves the generic failure sentence (covered for the "no answer reached the page" case in B-3 only with a stubbed gate, not with a real failed request); a response with `X-Receipt-Refusal` outside the closed set is covered (B-4c) | NON-BLOCKER | Low | Covered by WISHENKA-145 and T-2 |
| M-6 | Older-modal error visibility (S-9, S-10) has no test at all; the pre-existing behaviour is untested because the stub swaps error bodies the other way round than real htmx | NON-BLOCKER | Medium | T-3 (write the failing test first: real htmx or the stub with real 4xx semantics) |
| M-7 | `tests/test_receipt_static_script.py` pins the inline script of `base.html` by SHA-256 (`test_receipt_static_script.py:113`): any intended edit of the inline script (for example WISHENKA-140) fails this test and needs a conscious hash update | NON-BLOCKER | Low | Accepted; note on WISHENKA-140. No new ticket |
| M-8 | One browser test (`test_unmarked_error_neither_shows_notice_nor_reloads`) proves a negative by waiting 2 s of wall-clock time | NON-BLOCKER | Low | Accepted, bounded (see timeout section) |

## Performance Concerns

| # | Concern | Class | Priority | Disposition |
| - | ------- | :---: | :------: | ----------- |
| P-1 | Page render for a member now reads the wishlist three times: `get_wishlist_by_id`, `get_wishlist_view`, and `list_gifted_items` (which calls `get_wishlist_by_id` again and filters the items in Python) inside one `_execute` (`items_ui.py:132-142`). The gifted read is skipped for non-authors (`can_view_gifted`). No per-item query inside a loop (no N+1); the three reads are whole-list snapshots | NON-BLOCKER | Low | Existing WISHENKA-118 (shared SQLite writer and snapshot cost); also see WISHENKA-23 P-3 |
| P-2 | A successful receipt answers with a full list or a card, plus the gifted section, plus the dialog container reset: `list_wish_items` and `list_gifted_items` are two more snapshots after the write (`_read_state`, `receipts_ui.py:231-234`). Payload: a partial receipt returns one card plus the section; a full receipt returns the whole `#items-list` (documented design: first and last flags and empty text come along). For a list of a few dozen wishes, a few KB | NON-BLOCKER | Low | Accepted by the architecture; WISHENKA-118 |
| P-3 | The select renders N options for a wish of quantity N (S-4), and the gifted section renders every act of every received wish with no paging (`gifted_items_section.html`) | NON-BLOCKER | Low | T-2 (cap or switch to a stepper above a threshold) |
| P-4 | `htmx:beforeSwap` and `htmx:afterSwap` handlers on `document` run for every htmx request of the page; both exit after one property check, negligible | NON-BLOCKER | Low | Accepted |

## Deviations from `20-architecture.md`

All deviations are already recorded in the roadmap Step 4 and in the architecture notes; none changes an
invariant. Re-verified against the code:

- `oob_text` helper added to `gifted_view.py` instead of per-module literals (roadmap, P8). In the code, so true.
- GET dialog reads the wish through `get_wishlist_by_id` and `wishlist.items`; a non-member of a DELETED list
  gets `wishlist_not_active` (404) instead of `forbidden` (`receipts_ui.py:144-152`). True, advisory GET only.
- `_quantity_of` maps text that is not a whole number to 0 (`receipts_ui.py:243-247`) so the service refuses it
  after its guards. True.
- Real receipt dialog uses `receipt-backdrop` and `receipt-sheet` next to the old `modal-backdrop` and
  `modal-sheet` class names (S-10): the old names have no CSS, the receipt classes carry all the styling.
- CSP readiness checked: this task adds no inline handler and no inline script. The only new script
  reference is `<script src="/static/receipt.js" defer></script>` (`base.html`, `git diff` shows no other `on*`
  attribute or `<script>` added in any template; the new partials `item_receipt_modal.html` and
  `gifted_items_section.html` contain none). The `onclick` at `item_archive_modal.html:38` is **pre-existing**
  (`git show HEAD:` has it at line 32, the line number moved only because this task added a paragraph above it);
  it stays under WISHENKA-140.
- No deviation affects secrecy: the log and fragment tests (`test_receipt_ui_observability.py`, T-2 to T-5)
  assert that no booking data, giver names or notice words reach the page or the logs.

## Follow-up Tasks

Classification rule: BLOCKER means broken, incomplete or unsafe relative to the Definition of Done and the
invariants of WISHENKA-24 (surprise secrecy, XSS, data loss, missing timeout markers). **There are no
BLOCKERs.** `Jira:` stays `not yet created` for NEW items until the sync step links them. The Jira tool was
not called; existing keys are taken from the artifacts of other tasks.

### Group 1. Covered by an existing ticket (no new ticket; add scope)

| # | Item | Existing ticket | Note | Class |
| - | ---- | :-------------: | ---- | :---: |
| 1.1 | Real-htmx smoke test; stub fidelity (S-1, M-1) | WISHENKA-145 | Add the receipt flow, the `beforeSwap` override and the fetch-versus-XHR gate note to its scope | NON-BLOCKER |
| 1.2 | `receipts._REFUSALS` import (S-6) | WISHENKA-158 | Note only (scope of 158 stays: `service.py` split and `store.py` flush unification): the receipt module move must keep `receipts._REFUSALS` importable; the web-side rename to a public name is in T-4 | NON-BLOCKER |
| 1.3 | Log-contract hardening: shared event names and the "Receipt refused" message, pre-existing `user_id` on `ui_items_reorder_rejected` (C-9) | WISHENKA-157 | Scope addition only | NON-BLOCKER |
| 1.4 | Inline script and six `onclick` attributes (the archive modal `onclick`, the SHA-256 pin of M-7) | WISHENKA-140 | Update the hash test when the script moves | NON-BLOCKER |
| 1.5 | Snapshot and writer cost (P-1, P-2) | WISHENKA-118 | Scope addition | NON-BLOCKER |
| 1.6 | RU/EN rendering of all new texts (S-8, C-5) | WISHENKA-33 | | NON-BLOCKER |
| 1.7 | Global htmx error hooks (toast on `responseError`, `sendError`) | WISHENKA-90 | Related to T-3 but not the same work; link, do not merge blindly | NON-BLOCKER |
| 1.8 | Undo of a receipt, idempotency of repeated taps, CSRF mechanism, metrics exporter, settings | WISHENKA-153, 61, 123, 84, 34 | Out of scope of WISHENKA-24 by the requirements | NON-BLOCKER |
| 1.9 | Stray `core` file | WISHENKA-126 | Do not commit `core` | NON-BLOCKER |

### Group 2. New debt needing a ticket

| # | (a) Title | (b) Why not covered | (c) Priority | (d) Type | (e) Class | (f) Jira |
| - | --------- | ------------------- | :----------: | :------: | :-------: | -------- |
| T-3 | Older modals (edit, archive) show no 4xx/5xx answers and have no CSS: htmx does not swap error responses (edit 409 and 503 re-render, archive 409, reorder 400), `.modal-backdrop`/`.modal-sheet` are unstyled, the archive confirm button is covered by the fixed quick-add bar, the edit-modal archive button has no `hx-target` (S-5, S-9, S-10, M-6). Pre-existing, found while testing this story | No `60-tech-debt.md` mentions it (grep of `ai-tasks/*/60-tech-debt.md`: only WISHENKA-90 names the symptom class, as a toast feature). Evidence: `item_edit_modal.html:1-3, 180`, `item_archive_modal.html:1-3, 23-25, 38 (onclick, pre-existing)`, `base.html:7` (only `miniapp.css`), `wishlist.js:552-567` (this story's own fix for reorder only) | **High** | **Bug** | NON-BLOCKER | NEW |
| T-2 | Receipt dialog accessibility and mobile behaviour: focus after a successful receipt (S-3), focus trap or `inert` page and `aria-modal`, `<details>` that re-collapses after a swap, the select with N options (S-4, P-3), browser tests for focus, 44 px targets and the overlay over the quick-add bar (M-2, M-3) | Accepted limits of this story, not owned by any ticket | Medium | Debt | NON-BLOCKER | NEW |
| T-1 | Test infrastructure: fix the stub docstring ("additive" is not strictly true), make the stub gate XHR as well as `fetch`, and drop the `console.error` assertion where real htmx would log (S-1, S-2). Do together with WISHENKA-145 if that is taken first | WISHENKA-145 covers the real-htmx smoke test but not the cleanup of the stub and of the assertions that would fail under the real library | Low | Debt | NON-BLOCKER | NEW (or a sub-item of WISHENKA-145 at sync time) |
| T-4 | Web-layer structure: share the OOB helpers (`_list_oob`, `_gifted_oob`) between `items_ui.py` and `receipts_ui.py`, replace the private cross-module imports, including a public accessor for `receipts._REFUSALS` (S-6, S-7, C-1), a page-state dataclass instead of the six-tuple (C-2), a constants module for selectors, ids and header names and a single source of the reason set (C-4), move the success notice to the sentence table (S-11) | Created and widened by this story; WISHENKA-158 concerns `service.py` and `store.py` only (constraint noted on it, S-6) | Low | Debt | NON-BLOCKER | NEW |
| T-5 | Wording review of the new Russian texts, including the quantity forms (S-8, M-4); results feed the RU/EN work of WISHENKA-33 | Texts were written by the implementer only | Low | Debt | NON-BLOCKER | NEW |
| T-6 | CSS tokens and hardcoded values: colour and size constants in `miniapp.css`, Telegram theme variables for text colours and a dark-theme check, `STALE_RELOAD_DELAY_MS`, one `DEFAULT_CURRENCY` (C-6) | Not covered by any ticket | Low | Debt | NON-BLOCKER | NEW |

Created in Jira (Phase D): T-3 -> WISHENKA-160 (Bug, High, 5 SP), T-2 -> WISHENKA-161 (Debt, Medium, 5), T-1 -> WISHENKA-162 (Debt, Low, 2), T-4 -> WISHENKA-163 (Debt, Low, 5), T-5 -> WISHENKA-164 (Debt, Low, 2), T-6 -> WISHENKA-165 (Debt, Low, 3).

Counts: 6 new tickets (T-1 to T-6: one High Bug, one Medium, four Low), all NON-BLOCKER. Existing keys used:
WISHENKA-33, 34, 61, 84, 90, 118, 123, 126, 140, 145, 153, 157, 158.

Deliberately **not** ticketed: S-2 (merged into T-1), C-3, C-7, C-8 (pre-existing `console.warn`, accepted), C-10
(roadmap), M-7 and M-8 (accepted), P-4.

## Notes for the gate owner

- No BLOCKER. Timeout rule satisfied (0 of 798 collected tests lack a marker; all new and changed modules carry
  a module-level mark; browser waits are bounded).
- No production code or test was changed in this step; the full suite was not re-run (the last full run is
  797 passed at Step 5; the Step 6 test was added after).
- Step 8 should document: the receipt dialog contract (`X-Receipt-Refusal` closed set, `beforeSwap` override,
  `X-Reorder-Refusal`), the OOB-only 409 for stale archive and restore, `receipts._REFUSALS` as a dependency
  of `receipts_ui.py`, and the accepted limits S-3 and S-4.
- Orchestrator close-out: link T-3 to WISHENKA-90 when ticketed, note on WISHENKA-158 (keep `_REFUSALS` importable), scope comments on WISHENKA-145, 157 with the
  scope additions of Group 1, exclude `core` from the commit.
