# Roadmap: WISHENKA-24

## Task Metadata

- **Implementation language**: Python 3.12+ (FastAPI web routes of the UI layer, Jinja2 templates, HTMX 1.9.12 markup), JavaScript (classic script in `wishenka/web/static/`, no inline JS), CSS

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [/] `ai-tasks/WISHENKA-24/00-roadmap.md` created from the template
  - [/] Implementation language recorded in Task Metadata: Python 3.12+ / Jinja2 / HTMX / JavaScript
  - [/] `ai-tasks/WISHENKA-24/10-requirements.md` written (frontend/TMA subset of the WISHENKA-22 specification on top of the WISHENKA-23 contract; requirement IDs U-1 to U-21 and N-1 to N-8 mapped to FR, CC, TD and contract elements)
  - [/] Scope guard: IN is one vertical slice (receipt modal, owner card, «Подаренные», cabinet marker, refusal and busy states); OUT is fixed with the Jira keys WISHENKA-33, 34, 84, 153, 154, 140, 123, 61
  - [/] Awaiting review and the acceptance gate (the orchestrator marks `[x]`)
  - [/] Fix round 1: after review FAIL, `10-requirements.md` corrected (neutral busy text, U-8 quantity wording, UI-level observability requirement N-7, Step-2 leakage removed, DoD items 13 to 16, traceability additions, onclick count, U-19 placement left to Step 2)
- [x] **STEP 2: High-Level Architecture Design**
  - [/] `ai-tasks/WISHENKA-24/20-architecture.md` written
  - [/] Fix round 1: after review FAIL (9 gaps), `20-architecture.md` corrected (receipt-only `X-Receipt-Refusal` marker vs `X-Reorder-Refusal` for stale reorder, feedback reset per attempt, best-effort refusal effect read, plan split into P1 to P20, guarded `beforeSwap` handlers, UI log fields = 22 table without `operation`, `item_title=""` for non-members, giver-guard DTO, busy-keeps-quantity test)
  - [/] Fix round 2 (non-blocking gaps): 7 reviewer gaps G1 to G7 and notes applied to `20-architecture.md` (GET `nothing_remaining` list OOB moved to P13, `oob` switch of the dialog, inline-script snapshot hash instead of a length claim, closed reason set source check, OOB-only escaping rule and `<script>` title cases, stale 409 OOB-only assertion, NEW-handlers wording)
- [x] **STEP 3: Failing Repro Test**
  - [/] Execution: automated RED tests written (no production code touched; `git diff -- wishenka` is empty). Review pending.
  - [/] `tests/test_receipt_ui_routes.py` (T-2): GET dialog (content, escaped title, busy 503, template oob switch, remaining 1, no booking data, blocked states per reason), POST partial and full receipt fragments, co-author and recipient views, refusals by `_REFUSALS` class (9 rows), degraded effect read, non-integer quantity, busy, 401/CSRF, reason table, UI log scan. Red reasons: route 404 (`{"detail":"Not Found"}`), missing header, `receipts_ui` module or `item_receipt_modal.html` missing.
  - [/] `tests/test_receipt_card_ui.py` (T-3): owner badge and details, button for members only, archive dialog text, archive section/restore, stale archive and restore OOB-only 409, giver guard (direct render), stale reorder header. Red: markup absent. Guards green today: `test_card_without_receipts_is_unchanged`, `test_giver_and_share_viewers_keep_multiplier`.
  - [/] `tests/test_gifted_section_ui.py` (T-4): section for owner/admin/member, hidden when empty, absent for non-members (owner control inside), archived list, separation from archive, entry content/order/XSS, approximate date, no controls or booking data, fail-soft read. Red: no `#gifted-items-section`.
  - [/] `tests/test_cabinet_received_marker.py` (T-5): marker, link omission, purchased promise, partial receipt, archived list, closed promise, neutral text. Red: no `.reservation-wish-received`.
  - [/] `tests/test_receipt_static_script.py` (T-6): `receipt.js` served and loaded after `wishlist.js`, inline script SHA-256 snapshot (guard, green today), one `htmx.ajax` per script, no `on*`, marker namespaces, closed reason set, `getResponseHeader` guards, hygiene. Red: `receipt.js` 404; `wishlist.js` lacks marker, wrapper and responseError handler.
  - [/] `tests/test_receipt_modal_browser.py` (B-1 to B-6 incl. B-4b, B-4c; `browser` mark, module `timeout(45)`): all red at the first step (`/static/receipt.js` not loaded).
  - [/] Test infrastructure (test code only): `tests/receipt_ui_support.py` (new), `tests/browser_helpers.py` (`record_receipt`, `archive_item_rest`, `open_receipt_dialog`, `posts_to`, `scroll_to`), `tests/browser_assets/htmx_stub.js` (additive: `beforeSwap` detail with `xhr`/`shouldSwap`/`isError`, `responseError`, `swap: 'none'`, OOB swaps). Existing browser suite re-run after the stub change: 54 passed.
  - [/] Review (separate subagent): re-ran all new files (80 red, 3 guards green) and the 54 existing browser tests; verified fixtures against the JSON route and a throwaway scratch implementation of the design (outside the repo: browser tests B-1 to B-6 green, mutants of the in-flight guard, feedback reset and closed reason set caught). Test-only edits: `tests/test_receipt_card_ui.py` (+`test_owner_card_has_no_booking_data`, +`test_list_notice_region_for_members_only`), `tests/test_receipt_static_script.py` (guard regex accepts `===`/`!==`).
- [x] **STEP 4: Development**
  - [x] P1: `is_member` flag (`_editor_card_flags`, page context, card route), owner badge «Осталось N из M» and three detail spans, giver guard `not is_fully_received` in `item_card.html`; files `items_ui.py`, `sharing.py`, `item_card.html`; green: owner badge, unchanged/giver/share guards, booking-data, giver-guard tests of `test_receipt_card_ui.py`
  - [x] P2: cabinet marker `.reservation-wish-received` and link omission in `reservations_list.html`; `tests/test_cabinet_received_marker.py` all green
  - [x] P3: archive row «Осталось N», archive dialog sentence (`has_received` in `archive_confirm_ui`); files `archived_items_section.html`, `item_archive_modal.html`, `items_ui.py`
  - [x] P4: `wishenka/web/gifted_view.py` (`GiftedAct`, `GiftedRow`, `utc_day`, `build_gifted_rows`, `read_gifted_rows`, `RECEIPT_REFUSAL_HEADER`, `NOTHING_REMAINING_TEXT`)
  - [x] P5: `partials/gifted_items_section.html` (context `gifted_rows`, `oob`)
  - [x] P6: page wiring (`can_view_gifted`, `gifted_rows`, `#list-notice` for members, section include); `tests/test_gifted_section_ui.py` all green
  - [x] P7: `partials/item_receipt_modal.html` (`oob`, `blocked`, optional title, label bound to select, `role=alert`); `test_modal_template_oob_switch` green
  - [x] P8: `wishenka/web/routes/receipts_ui.py` core (`_SENTENCES` incl. `busy`, `_classify` reading `receipts._REFUSALS` read-only, `_log`/`_log_refusal` on logger `wishenka.web.receipts_ui`, `_refusal_fragment`); added `oob_text` to `gifted_view.py` (escaping OOB element helper); green: `test_ui_reason_table_matches_json_route`
  - [x] P9: GET dialog route `get_receipt_dialog`, `_check_receipt_open`, `_blocked_dialog`, router include in `app.py`; green: GET tests
  - [x] P10: POST partial receipt (`record_receipt_ui`, `_read_state`, `_card_oob`, `_gifted_oob`, notice, success log); `card_oob` root attribute in `item_card.html`
  - [x] P11: full receipt list fragment (`_list_oob`, `innerHTML:#items-list`)
  - [x] P12: plain refusals and busy (status, `X-Receipt-Refusal`, sentence, logs)
  - [x] P13: `_effect_fragments` (above-remaining card plus OOB dialog; nothing-remaining list, gifted, blocked dialog), best-effort degrade on `WishlistError`, GET `nothing_remaining` extension; `tests/test_receipt_ui_routes.py` 38/38 green
  - [x] P14: owner card button `btn-receipt-item` in `.item-actions` (`item.remaining_quantity > 0`)
  - [x] P15: `items_ui._nothing_remaining_response` (409, header, OOB-only body) replaces `_raise_nothing_remaining` in archive and restore; `_DOMAIN_ERRORS` untouched
  - Deviation: P8 adds a small helper `oob_text` to `gifted_view.py` (shared by both route modules without an import cycle) instead of per-module literals. Reason: no f-string interpolation of titles and sentences.
  - Deviation: GET dialog reads the wish through `get_wishlist_by_id` and `wishlist.items`, so a non-member of a DELETED list gets `wishlist_not_active` (404) instead of `forbidden`. Reason: `get_wishlist_by_id` raises before membership can be checked; the GET is advisory, POST keeps the service order.
  - Deviation: `_quantity_of` maps non-integer text to 0 so the service refuses it as `quantity_invalid` after its guards (membership first), instead of raising before the service call.
  - [x] P16: `static/receipt.js` part A (summary line with clamp, dismissal by `[data-modal-close]`/Escape/backdrop, opener registration and return focus, focus into the dialog on `htmx:afterSwap`) and one `<script src="/static/receipt.js" defer>` tag after `wishlist.js` in `base.html` (inline script untouched); green: `test_receipt_script_is_served_as_javascript`, script order, B-1
  - [x] P17: `receipt.js` part B (delegated `submit` with in-flight guard, `aria-busy`, disabled button, feedback reset first, single `htmx.ajax('POST', ..., {target: '#receipt-feedback', swap: 'none', values: {quantity}})`, generic-failure post-condition in `finishAttempt`, guarded `htmx:beforeSwap` override keyed only on `X-Receipt-Refusal` in the closed set); green: T-6 receipt checks, B-2, B-3, B-4, B-4b, B-4c
  - [x] P18: `wishlist.js` `swapWishCard` wrapper (guarded by `typeof original === 'function'`; neutral `p.item-card-unavailable` «Желание больше недоступно. Обновите страницу.»); green: B-5, T-6 hygiene
  - [x] P19: `items_ui.py` `REORDER_REFUSAL_HEADER` and `headers={...: "stale_order"}` on the stale reorder 400 (JSON body unchanged); `wishlist.js` guarded `htmx:responseError` listener on `document` (notice in `#list-notice`, reload after 800 ms); green: `test_stale_reorder_has_distinct_marker_header`, B-6, `test_new_handlers_guard_a_missing_xhr`
  - [x] P20: `miniapp.css` (38 lines): `.receipt-backdrop` fixed overlay (z-index 100 over `.quick-add-container` 40), `.receipt-sheet`, feedback, confirm button, `#list-notice`, `.item-card-unavailable`, gifted, archive remaining, cabinet marker, badge-received; touch targets >= 44px
  - Review PASS (real htmx 1.9.12 verified in headless Chromium on a scratch copy: dialog, partial/full receipt, refusals with X-Receipt-Refusal, busy, stale card, XSS, stale reorder; 796 passed in the scratch copy). Carried to Step 5/7: (1) test hole — mutation deleting the X-Reorder-Refusal check in the wishlist.js responseError listener survives; add a browser test with an unmarked responseError (no notice, no reload); (2) stub-vs-real divergences: B-3 gates window.fetch (real htmx uses XHR), console.error assertions in B-4/B-6 would fail under real htmx, the stub swaps nothing >= 400 now (docstring 'additive' not strictly true) -> debt; (3) real htmx logs console.error for unswapped 4xx (expected); (4) focus is not returned after a successful receipt; (5) the edit-modal archive button has no hx-target so a marker 409 swaps whitespace into the button (harmless); (6) older archive modal confirm button is covered by the fixed quick-add bar (pre-existing, no CSS).
- [x] **STEP 5: Code Cleanup**
  - [/] `ai-tasks/WISHENKA-24/40-code-cleanup.md` written (analyze clean, 5 lines wrapped, 0 dead items, +1 browser test `test_unmarked_error_neither_shows_notice_nor_reloads` with mutation proof)
- [x] **STEP 6: Observability**
  - [x] `ai-tasks/WISHENKA-24/50-observability.md` written (audit of all UI log calls: 0 production defects; +`tests/test_receipt_ui_observability.py`, full-flow log scan with three promised givers; no exporter, metrics derived from events)
- [x] **STEP 7: Technical Debt Analysis**
  - [x] `ai-tasks/WISHENKA-24/60-tech-debt.md` written (no BLOCKER; timeout markers verified on all 7 new test modules, 0 of 798 collected tests unmarked; 6 new follow-ups T-1 to T-6 incl. a High Bug for older modals not showing 4xx/5xx and unstyled; existing keys WISHENKA-145, 157, 158, 140, 118, 90, 33). No code changed. Review pending.
- [x] **STEP 8: Dev Docs**
  - [x] Developer docs updated (docs only, no code or tests touched): `doc/dev/gift-receipt.md` (new section «Mini App UI (WISHENKA-24)»: routes, dialog flow, `X-Receipt-Refusal` set incl. `busy`, `beforeSwap` override, `X-Reorder-Refusal`, OOB-only 409, «Подаренные», cabinet marker, invariants, accepted limits S-3/S-4, UI log events, browser tests and stub divergences, tickets WISHENKA-160 to 165), `doc/dev/miniapp.md`, `doc/dev/items.md`, `doc/dev/reservations.md`, `doc/dev/architecture.md`, `doc/dev/testing.md`, `doc/dev/verification-matrix.md` (row S9). Awaiting review.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-24/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-24/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-24/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-24/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-24/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
