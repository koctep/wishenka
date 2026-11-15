# WISHENKA-23: Technical Debt Analysis

Scope: the uncommitted change set of WISHENKA-23 (Steps 3 to 6) over base commit `b0bff5a`: gift receipt
domain rules, migrations `add_gift_receipts` and `add_notice_outbox`, the `wishenka/notices/` package
(queue store, worker, sender), `wishenka/web/routes/receipts.py`, the archive split and read models, and
the new tests. Nothing was changed in code or tests in this step. The stray untracked `core` file is not
part of the change set (Debt WISHENKA-126).

Verdict: **no BLOCKER for closing WISHENKA-23.** Definition of Done items 1 to 12 are met by automated
tests (evidence: 703 passed, 0 failed after Step 5, `40-code-cleanup.md`; 711 passed, 0 failed after
Step 6, `50-observability.md`; `make analyze` clean). What remains is NON-BLOCKER debt: five small new
tickets T1 to T5, items covered by existing tickets, accepted residuals, and close-out actions for the
orchestrator.

## Python test-timeout rule

Outcome: **satisfied, no BLOCKER.**

- Every new test module sets a module-level `pytestmark = pytest.mark.timeout(...)`: `test_gift_receipt_api.py`,
  `test_gift_receipt_migration.py`, `test_gift_receipt_service.py`, `test_receipt_concurrency.py`,
  `test_receipt_notices.py`, `test_receipt_notices_extra.py`, `test_receipt_observability.py`,
  `test_surprise_receipt_walk.py` (grep, one module mark each; 74 test functions).
- `tests/notice_support.py` and `tests/receipt_support.py` hold helpers only, no test functions.
- Evidence: `.venv/bin/pytest --collect-only -q -m "not timeout"` collects 0 tests (711 deselected), so no
  collected test in the whole suite lacks a timeout marker (the three edited existing modules included).
- Residual to watch: `test_run_loop_logs_one_error_per_failure_streak` relies on a real `asyncio.sleep(0.6)`
  window (item C-7), the timeout itself is present.

## Shortcuts Taken

| # | Shortcut / assumption | Where | Class | Priority | Disposition |
| - | --------------------- | ----- | :---: | :------: | ----------- |
| S-1 | Receipt and gifted routes answer 403 `forbidden` for a non-member and 404 for an unknown list or wish. Intended and consistent with the item routes: `routes/items.py:83` returns 403 for `PermissionDeniedError`, item ids are not secret (`20-architecture.md` section 3, check order), and list existence is not secret either (any non-deleted list is viewable by id or link, `in-docs/spec.md` 4.5, `WishlistAccessPolicy.can_view_wishlist`). No leak, no change needed | `wishenka/web/routes/receipts.py` (`_REFUSALS`), `GET /api/wishlists/{id}/gifted` | NON-BLOCKER | Low | Accepted by design (R-7.2 fixes only the wording of reasons, not the status codes). No ticket |
| S-2 | No access-revocation concept exists for givers: a list is viewable by anyone with the link and `can_view_wishlist` excludes only DELETED lists, so givers are normally non-members and a membership check at claim time would wrongly suppress legitimate non-member givers (FR-4.1). The one "no longer allowed" case, a deleted list, is skipped (`target_gone`) and tested (`test_notice_for_a_deleted_list_is_skipped_not_sent`). FR-4 says nothing about givers who lost access | `service.py` `_draft_receipt_notices`, `notices/worker.py` `notice_text` | NON-BLOCKER | Low | Accepted. No ticket. One open question for WISHENKA-154 (see Follow-up, group 2.7) |
| S-3 | Sender cancelled at shutdown after a DELIVERED result and before `complete` leaves the row `sending`; it is resent once after the lease. Accepted at-least-once residual, within the "at most one extra send per giver per act" rule (DoD 7) | `notices/worker.py`, `notices/store.py` `_settle_stale` | NON-BLOCKER | Low | Accepted, documented in Step 8. No ticket |
| S-4 | Two different `quantity_invalid` messages: route constant "Quantity must be a whole number of at least 1" and `QuantityInvalidError` default "Quantity must be a positive whole number". The test `test_receipt_route_reason_table` special-cases the digit check (strips "at least 1") | `routes/receipts.py`, `exceptions.py`, `tests/test_gift_receipt_api.py` | NON-BLOCKER | Low | New ticket T1 (one digit-free message, drop the special case; design table edit) |
| S-5 | `projection` now hides archived and not-active wishes from public and non-member viewers. A behaviour change outside the receipt route; no existing test relied on the old behaviour, and the new filter has its test (`test_projection_active_flag_and_public_filter`) | `wishenka/web/routes/wishlists.py` | NON-BLOCKER | Low | Accepted (follows the view rule of DoD 3). Step 8 documents it. No ticket |
| S-6 | Migration `add_gift_receipts` is irreversible (`downgrade` raises `NotImplementedError`); back-filled receipt dates are approximate (last wish update; `is_approximate`); fully received archived rows are normalised in place (AR-3, AR-5) | `alembic/versions/add_gift_receipts.py` | NON-BLOCKER | Low | Accepted by the architecture; the irreversibility and the approximation must be stated in the Step 8 migration notes (DoD 5). Counts are logged (`legacy_receipts_backfilled`, `legacy_archived_rows_normalised`) |
| S-7 | Notice texts are Russian-only, one hardcoded template with titles cut at 100 characters; no per-language or per-user rendering | `notices/worker.py` `_TEXT`, `TITLE_LIMIT` | NON-BLOCKER | Low | Existing WISHENKA-33 (RU/EN) and WISHENKA-34 (preferences) |
| S-8 | The notice worker runs inside every web process; rows are claimed through `BEGIN IMMEDIATE`; no leader election | `web/app.py` `_start_notice_worker` | NON-BLOCKER | Low | Accepted; correct by the claim lease and guarded settle writes. Single dispatcher to be agreed in WISHENKA-60 (group 2) |
| S-9 | Delivery guarantee is at-least-once with at most one extra send; a duplicate after a crash is by design (DoD 7) | `notices/*` | NON-BLOCKER | Low | Accepted, documented in `20-architecture.md` |
| S-10 | `item_fulfilled` is logged before commit, so a rolled-back receipt can leave a log line (the event name was kept, WISHENKA-22 item 1.5) | `service.py` `record_item_fulfillment` | NON-BLOCKER | Low | Accepted residual; same pattern as other existing events. Noted for the log-contract ticket T3 |
| S-11 | Enqueue failure has no own log event; it is indistinguishable from any receipt rollback. This is the closing of WISHENKA-22 item 1.6 (no presence leak) at the cost of diagnosability | `store.py` `_flush_receipt_effects` | NON-BLOCKER | Low | Accepted; diagnosability gap carried to T3 |
| S-12 | Defaults for the delivery limits are Settings fields (poll 5 s, max attempts 5, backoff base 30 s, backoff max 1800 s, request timeout 30 s, lease 300 s, window 300 s, retention 30 days). Four values are module constants: `CLAIM_BATCH_LIMIT = 50`, `TITLE_LIMIT = 100`, `MAX_ERROR_BACKOFF_SECONDS = 60.0`, and the doubling factor 2 of the backoff (`backoff_seconds`). Correction to a carry-over note: the poll interval and window ARE Settings, not hardcoded | `config.py`, `notices/store.py`, `notices/worker.py` | NON-BLOCKER | Low | Accepted: the constants are bounds with no operational reason to change; revisit only if they need tuning. No ticket |
| S-13 | No notice worker runs without a bot token (architecture divergence 8: a no-op sender would mark rows sent). A deployment without a token enqueues rows but never sends notices | `web/app.py` `_start_notice_worker` | NON-BLOCKER | Low | Accepted residual, by design. Step 8 states it as a deployment requirement. No ticket |
| S-14 | `updated_at` is only an approximate "sent" time: there is no `sent_at` column (architecture divergence 15; `50-observability.md` "Open for Step 7") | `notices/store.py` outbox table | NON-BLOCKER | Low | Accepted; revisit with the exporter (WISHENKA-84) or the shared outbox (WISHENKA-60), group 2. No ticket |
| S-15 | Step 4 minor deviations from the design: `_persist_wish` and `_write` return types changed (they return the flushed rows for the after-commit DEBUG logs); the field sets of `FlushedNotice` and `NoticeDraft` were chosen in Step 4 (the design did not fix them) | `store.py`, `service.py`, `notices/` | NON-BLOCKER | Low | Accepted, internal types only. Covered by T4 when the flush paths are unified. No ticket |
| S-16 | `tests/test_auth*.py` call `create_app` with a valid-looking `TEST_BOT_TOKEN`; since plan step 27 that starts a notice worker and a real aiogram `Bot`. Checked in Step 2: those tests assert only token absence from records and the auth counts | `tests/test_auth*.py`, `web/app.py` | NON-BLOCKER | Low | Accepted low residual: a future auth test that makes the worker poll could become timing-dependent. No ticket |
| S-17 | Presence residual (accepted in WISHENKA-22): on an otherwise idle system a window summary with non-zero counts appears after a window with open-promise receipts, so the summary must stay in operator-only logs (DEBUG/operator access) | `notices/worker.py` window summary | NON-BLOCKER | Low | Accepted. Defer to Step 8 docs (operator-only log rule); debt line recorded here. No ticket |
| S-18 | Pre-existing, left alone: unused `ReservationStatus.COMPLETED` in `models.py` (the product rejects a completed status; architecture divergence 12 context and Issues found) and the unreferenced `wishenka/wishlists/db_models.py` | `models.py`, `db_models.py` | NON-BLOCKER | Low | Left alone (pre-existing, not touched by this story). No ticket |

## Code Quality Issues

| # | Issue | Class | Priority | Disposition |
| - | ----- | :---: | :------: | ----------- |
| C-1 | `wishenka/wishlists/service.py` grew by about 300 lines (now 2600). `record_item_fulfillment` is about 114 lines (guards, receipt, `item_fulfilled` log, notice drafting call). The module mixes reservation, receipt, archive and read-model code | NON-BLOCKER | Low | T4 (split by concern) |
| C-2 | `wishenka/wishlists/store.py` (1370 lines): `_persist_wish` and `_write` both call `_flush_receipt_effects` and both return flushed rows for the after-commit DEBUG logs; the two flush call sites are duplicated logic | NON-BLOCKER | Low | T4 |
| C-3 | Fail-open guard `if wl is not None:` in `record_item_fulfillment` (`service.py` about 2156). Unreachable in production (the store always sets `item.wishlist`). If it ever were reached, the permission check is skipped instead of failing closed. Sites read one by one: the fail-open permission/context guards are 1063 and 1558 (list-state check skipped), 1600 (`ctx` set to None, `can_reserve_item` skipped) and 2156; the sites 2421, 2485, 2503 and 2566 are existence/error-branch conditions (missing or deleted list in favorites and view history), not access guards, and are left alone | NON-BLOCKER | Low | T5 (the four guards fail closed: assertion or raised error, not a silent skip) |
| C-4 | Two different `quantity_invalid` messages and a special-case digit check in a test (see S-4) | NON-BLOCKER | Low | T1 |
| C-5 | Pre-existing `item_archived` event logs `active_reservations_count` on the owner stream. Pre-existing, not worsened by this story; the receipt route adds no such field | NON-BLOCKER | Low | T3 (log contract) |
| C-6 | `receipt_notice_retry_scheduled` lacks `max_attempts` (the WISHENKA-22 observability table lists it) | NON-BLOCKER | Low | T3 |
| C-7 | `last_error_class` is cleared on success, so failures-by-class totals are not derivable from the table; the `ambiguous` flag is never cleared, so the gauge counts historical rows | NON-BLOCKER | Low | T3 |
| C-8 | `tests/test_receipt_notices_extra.py::test_run_loop_logs_one_error_per_failure_streak` is timing-based (`2 <= calls < 12` after `asyncio.sleep(0.6)`); small flake risk under load | NON-BLOCKER | Low | T3 (drive with an injected clock or event instead of wall-clock) |
| C-9 | `tests/test_receipt_observability.py` lines 271 and 282: the closed-field check for `receipt_refused` / `receipt_inventory_busy` is a blacklist; replace by exact key-set equality. Wording "a stop writes nothing" in docs and tests is inaccurate: the stop emits INFO `receipt_notice_worker_stopped` (no counts) | NON-BLOCKER | Low | T3 (test) and Step 8 (wording) |
| C-10 | Roadmap cosmetics: STEP 2 sub-items keep `[/]` marks under an `[x]` step | NON-BLOCKER | Low | Orchestrator close-out; no ticket |
| C-11 | `10-requirements.md` says one intended existing-test edit while the architecture records three (migrations `_HEAD`, surprise role context, shared inventory multiprocess line 602). The architecture governs (divergence 12) | NON-BLOCKER | Low | Recorded here; requirements file is not edited. No ticket |
| C-12 | `WishService.notice_drafts` property is unused in production and kept only because `tests/test_gift_receipt_service.py` asserts on it (`40-code-cleanup.md`) | NON-BLOCKER | Low | Kept; revisit with T4 (a test-only seam in production code). No ticket |

## Missing Tests

- **No live Telegram test.** The aiogram `Bot` is mocked everywhere (`Bot.send_message` patched). The real sender
  path is unverified: token handling, absence of a parse mode, the 4096 character limit (titles are cut at 100
  characters each, so the limit cannot be reached by the template), HTML escaping (no parse mode, plain text),
  and the real timeout and error mapping against Telegram. NON-BLOCKER, Low. New ticket T2 (opt-in smoke test
  skipped without credentials, plus a manual checklist).
- **No test with two real notice-worker processes.** The claim race of two workers is covered in one process
  with two stores (`test_fresh_claim_is_not_reclaimed_by_a_second_worker`, `test_long_drain_stamps_each_claim_with_its_own_time`);
  spawned processes exist only for the receipt race (`test_two_receipts_race_spawned_processes`). The WAL file
  locking across processes for the claim is therefore verified indirectly. NON-BLOCKER, Low. Include in T2.
- **CC-13 has indirect coverage only** (the bounded busy answer and no-leak property of the receipt path are asserted
  through the promise-style 503 test and the walk test, no dedicated test for CC-13 itself). NON-BLOCKER, Low. Include in T3.
- **DoD item 11 coverage.** All 19 corner cases are covered by the new files; only CC-13 is indirect (above).
- **Counters of window summary on a stop** have no test for "stop emits one INFO without counts" (see C-9). T3.
- **Giver access revocation** has no test because no such concept exists (S-2); the deleted-list case is tested (`test_notice_for_a_deleted_list_is_skipped_not_sent`).
- Pre-existing failing tests: none observed in this story (the full suite after batch 4 was green; baseline not needed).

## Performance Concerns

| # | Concern | Class | Priority | Disposition |
| - | ------- | :---: | :------: | ----------- |
| P-1 | Every idle worker poll opens `BEGIN IMMEDIATE` (a write-lock transaction) in every process every ~5 s, even when no row is due. With N web processes this is N lock acquisitions per interval competing with promises and receipts. A read-only due-row precheck before taking the write lock would avoid it | NON-BLOCKER | Medium | Existing WISHENKA-118 (independent wishes share one SQLite writer); add the precheck to its scope. No new ticket |
| P-2 | `claim_next` runs a due query with a title join per claim (50-row look-ahead, one claim per transaction). Fine at current volumes (one row per giver per act) | NON-BLOCKER | Low | Accepted |
| P-3 | `GET /gifted` uses the full snapshot `execute` path (loads all wishes of the list with reservations and receipts) although it needs only receipts | NON-BLOCKER | Low | Accepted until list sizes justify a targeted query; relates to WISHENKA-118 and WISHENKA-59 (verify index scope for `wl_receipts`: the migration creates one index). No ticket |
| P-4 | Receipt transaction holds the writer lock longer (reads open promises and settings, inserts one outbox row per giver) | NON-BLOCKER | Low | WISHENKA-118 (as predicted by WISHENKA-22) |
| P-5 | Outbox grows: `purge_finished` removes finished rows after `receipt_notice_retention_days` (default 30) in the cleanup cycle. WISHENKA-22's conditional retention ticket is **not needed** (retention is built here); table and worker sharing with WISHENKA-60 must be agreed when it is built | NON-BLOCKER | Low | WISHENKA-60 (group 2) |

## Follow-up Tasks

Classification rule: BLOCKER means broken, incomplete or unsafe relative to the acceptance criteria of
WISHENKA-23 (Definition of Done 1 to 12). **There are no BLOCKERs.** `Jira:` stays `not yet created` until
the sync step links it. The Jira tool was not called; keys other than those known from the task context are
marked "to be verified".

### Group 1. Covered by the other story WISHENKA-24 (no new ticket)

| # | Item | Where fixed | Priority | Class |
| - | ---- | ----------- | :------: | :---: |
| 1.1 | Contract usable by WISHENKA-24 after plan steps 1 to 14 and 23 to 26; routes and DTO names are final (receipt route, `GET /gifted`, `GiftedItemDTO`, `MyReservationItemDTO.is_fully_received`, `CabinetRow.wish_received`). Close-out action: comment on WISHENKA-23 and WISHENKA-24 (orchestrator, TD-1.17) | roadmap Step 4 batch 4, `20-architecture.md` section 5 | High | NON-BLOCKER |
| 1.2 | Receipt screen, browser tests, cabinet marker UI, "completed" state decision (FR-3.6, WISHENKA-22 item 1.16), cabinet link target (item 1.9), reorder UI | `10-requirements.md` out-of-scope list | Medium | NON-BLOCKER |
| 1.3 | WISHENKA-24 maps the `quantity_invalid` reason by its code; if T1 changes the message text, the UI must not depend on the old wording (the `forbidden` 403 contract stays, S-1) | this file, S-4 | Low | NON-BLOCKER |

### Group 2. Covered by an existing ticket (key)

| # | Item | Existing ticket | Note | Class |
| - | ---- | :-------------: | ---- | :---: |
| 2.1 | Idle poll takes a write lock in every process every ~5 s (P-1); receipt transaction longer writer lock (P-4); gifted full-snapshot read (P-3) | WISHENKA-118 | Ask to include the read-only precheck for the idle poll | NON-BLOCKER |
| 2.2 | One outbox table and one dispatcher for receipt notices and booking events; retention rule and days (P-5); no leader election (S-8) | WISHENKA-60 | Must be agreed when WISHENKA-60 is built; this story's `notification_outbox` and worker are the candidate base | NON-BLOCKER |
| 2.3 | Russian-only hardcoded notice template (S-7) | WISHENKA-33 | RU/EN rendering | NON-BLOCKER |
| 2.4 | Settings screen and per-user preferences; this story only stores and looks up the two setting levels (DoD 8) | WISHENKA-34 | Settings tables exist, rows written by tests only | NON-BLOCKER |
| 2.5 | Metrics exporter; metrics of this story are derived from logs (`50-observability.md`) | WISHENKA-84 | No exporter in the project; also the missing `sent_at` (S-14) | NON-BLOCKER |
| 2.6 | Undo or correct a gift receipt | WISHENKA-153 | Receipt is final in this story | NON-BLOCKER |
| 2.7 | Product-owner decisions A to D, Q6, Q8, Q11, Q12 | WISHENKA-154 | Unchanged. Open question for its scope (not a ticket): `remove_member` only edits the member list and never touches reservations, so a removed member keeps an open promise and still gets a receipt notice as an ordinary non-member giver; what should happen to the promise or notice of a removed member on a collaborative list? | NON-BLOCKER |
| 2.8 | Stray untracked 197 MB `core` file in the working tree | WISHENKA-126 | Do not duplicate; do not commit `core` (exclude in the commit step) | NON-BLOCKER |
| 2.9 | Index scope for `wl_receipts` foreign key and the predicates | WISHENKA-59 (to be verified) | Migration adds one index on the receipt table | NON-BLOCKER |
| 2.10 | Double submit of the receipt command | WISHENKA-61 (to be verified) | A deliberate second receipt is legal | NON-BLOCKER |

### Group 3. New debt needing a ticket

Conservative: carry-over notes are merged into five tickets with neutral ids T1 to T5 (titles are deduplicated
at the Jira sync step; these ids are unrelated to the ticket names of WISHENKA-22).

| # | (a) Title | (b) Why not covered | (c) Priority | (d) Class | (e) Jira |
| - | --------- | ------------------- | :----------: | :-------: | -------- |
| T1 | One digit-free `quantity_invalid` message for the receipt route and `QuantityInvalidError`, and drop the digit special case in `test_receipt_route_reason_table` | No ticket carries it. Cosmetic; needs an edit of the design table (route reasons) and of `tests/test_gift_receipt_api.py` (S-4, C-4) | Low | NON-BLOCKER | Jira: [WISHENKA-155](https://pypost.atlassian.net/browse/WISHENKA-155) |
| T2 | Test infrastructure: opt-in real-Telegram smoke test (skipped without credentials, plus a manual checklist) and a two-real-process notice-worker claim race test | No ticket; the sender is verified only with a mocked bot and one-process claim tests (Missing Tests) | Low | NON-BLOCKER | Jira: [WISHENKA-156](https://pypost.atlassian.net/browse/WISHENKA-156) |
| T3 | Test and log-contract hardening: exact key-set equality in `test_receipt_observability` closed-field checks; a non-wall-clock loop test replacing the `asyncio.sleep(0.6)` one; `max_attempts` on the retry event; enqueue-failure diagnosability decision; `last_error_class` and `ambiguous` semantics; `item_archived.active_reservations_count`; the `item_fulfilled` pre-commit log; the "a stop writes nothing" wording in docs and the test docstring; a direct CC-13 test | Residuals of Step 6 and its review (C-5 to C-9, S-10, S-11); WISHENKA-84 covers exporting, not the log fields. One coherent hardening unit | Low | NON-BLOCKER | Jira: [WISHENKA-157](https://pypost.atlassian.net/browse/WISHENKA-157) |
| T4 | Split the receipt code out of `service.py` (about 2600 lines) and unify the two flush call sites in `store.py` (`_persist_wish`, `_write`) | Code-quality debt created and widened by this story (C-1, C-2, S-15, C-12); no existing ticket | Low | NON-BLOCKER | Jira: [WISHENKA-158](https://pypost.atlassian.net/browse/WISHENKA-158) |
| T5 | Make the four fail-open `wl is not None` permission/context guards (`service.py` 1063, 1558, 1600, 2156) fail closed: assertion or raised error, not a silent skip | Pre-existing pattern, one site added by this story (C-3); no existing ticket | Low | NON-BLOCKER | Jira: [WISHENKA-159](https://pypost.atlassian.net/browse/WISHENKA-159) |

Counts: 5 new tickets (T1 to T5, all Low, all NON-BLOCKER); the existing keys used are WISHENKA-24, 33, 34, 59,
60, 61, 84, 118, 126, 153, 154 (the keys 59 and 61 are "to be verified").

Deliberately **not** ticketed: S-1, S-2 (no revocation concept), S-3 (accepted residual), S-5, S-6 (documented in
Step 8), S-12 to S-14, S-16 to S-18, C-10, C-11 (roadmap and document notes), C-12, P-2 and P-3 (accepted), the
conditional retention ticket of WISHENKA-22 (retention is built).

## Resolution of WISHENKA-22 Group 1 items owned by WISHENKA-23

| # | Item | Resolution |
| - | ---- | ---------- |
| 1.1 | Notification infrastructure minimum | Done: `wishenka/notices/`, revision `add_notice_outbox`, both settings levels, default on, worker and sender |
| 1.2 | Decide the split | Not applicable: story stayed whole; the confirmation comment on WISHENKA-23 is an orchestrator close-out action |
| 1.3 | Migration, back-fill, normalisation, counts | Done: `add_gift_receipts`, counts logged. Irreversibility and approximation (S-6) must appear in the Step 8 notes |
| 1.4 | Replace the surprise test assertions | Done in code and tests (`notice_rows`, `receipt_columns`, new `test_surprise_receipt_walk.py`); `doc/dev/verification-matrix.md` row is a Step 8 action |
| 1.5 | Keep or rename `item_fulfilled` | Decided: kept (S-10); `tests/test_reservation_observability.py` unchanged; `reservations.md` update in Step 8 |
| 1.6 | Enqueue failure must not reveal presence | Decided: no own event, indistinguishable rollback (S-11); diagnosability carried to T3 |
| 1.7 | Duplicates counter, last error class, retention | Done: `last_error_class` and `ambiguous` columns, retention 30 days with purge (P-5); semantics gaps carried to T3 (C-7); table sharing to WISHENKA-60 |
| 1.8 | Summary-window residual | Done: window setting (min 60 s), fixed grid, no heartbeat, DEBUG operator-only; access requirement to be stated in Step 8 docs (S-17) |
| 1.9 | Cabinet link target | Not applicable (WISHENKA-24, group 1.2 above) |
| 1.10 | All red tests under their own Step 3 | Done: 8 new files, 74 tests; CC-13 only indirect (Missing Tests, T3) |
| 1.12 | "Planned" notes in `doc/dev` become current | Carried to Step 8 of this story |
| 1.13 | Candidate metrics from logs | Done in `50-observability.md`; exporter WISHENKA-84; field gaps T3 |
| 1.14 | Shared "active" predicate | Done: `WishItem.is_active` / `is_in_archive`, used by active list, reorder, restore, cabinet, projection (`test_views_share_one_active_predicate`) |
| 1.15 | FR-5.7 versus soft delete | Done: gifted read serves members of a non-deleted list only; rows stay until purge and cascade on purge (migration test) |
| 1.17 | Contract for WISHENKA-24 | Carried: comment on WISHENKA-23 and WISHENKA-24 is an orchestrator close-out action (group 1.1) |
| 1.11, 1.16 | (belong to WISHENKA-22 Step 8 and WISHENKA-24) | Not applicable |

## Notes for the gate owner

- No BLOCKER. Timeout rule satisfied (0 of 711 collected tests lack a marker).
- Orchestrator close-out actions: comment on WISHENKA-23 and WISHENKA-24 (TD-1.17), split confirmation comment
  on WISHENKA-23 (TD-1.2), roadmap STEP 2 `[/]` cosmetics, exclude `core` from the commit.
- Step 8 must document: migration irreversibility and approximate dates, at-least-once residual, the
  projection behaviour change, the operator-only log condition, the stop event wording, `reservations.md`
  and `verification-matrix.md` updates.
- All five new tickets are Low priority; none blocks WISHENKA-24 or the commit.
- Step 8 should also state the deployment requirement of a bot token (S-13) and the operator-only summary rule (S-17).
