# Roadmap: WISHENKA-23

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] `ai-tasks/WISHENKA-23/00-roadmap.md` created from the template
  - [x] Implementation language recorded: Python 3.12+
  - [x] `ai-tasks/WISHENKA-23/10-requirements.md` written (backend subset of the WISHENKA-22 specification, requirement IDs R-1 to R-8 mapped to FR IDs)
  - [x] Scope guard: the ticket stays whole, out-of-scope list fixed (WISHENKA-34, WISHENKA-84, WISHENKA-153, WISHENKA-154, WISHENKA-24)
  - [x] Fix round 1 after review FAIL: CC-4 mapped, Step 2 wording removed from requirements, Definition of Done covers every R-ID, Q3 basis and TD-1.17 recorded
  - [x] Fix round 2: R-5.1 to R-5.3 added to a new Definition of Done item 4 (read data), later items renumbered, wording notes applied
- [x] **STEP 2: High-Level Architecture Design**
  - [/] `ai-tasks/WISHENKA-23/20-architecture.md` written (concrete design, traceability, plan, failing-repro plan)
  - [/] Fix round 1 after review FAIL: test-impact list (three intended edits), DTO defaults, surprise walk 2 helpers, plan renumbered to 27 steps with LOC, delivery bound (5xx ambiguous, request timeout, lease rule), non-blocking notes
  - [/] Fix round 2 after review FAIL: surprise second-walk log rule (named fields, duration stripped), plan reordered by dependency (31 steps, config before queue store, test edits attached to the breaking step), DTO mechanism (`mode="before"`, `MyReservationItemDTO` set explicitly), stale `sending` row settled first in `claim_next`, guarded settle writes, sender mapping order, token-test note
  - Review round 3: PASS. Non-blocking notes carried to Step 3/4: (1) the receipt route (plan step 28)
    needs the `include_router` line in app.py in the same step; (2) `notices/models.py` must import
    `ReceiptRecord` under `TYPE_CHECKING` only (with `from __future__ import annotations`) to avoid an
    import cycle with `wishenka/wishlists/__init__.py`; (3) give `head_revision()` a default or dummy URL;
    (4) migration row counts via `op.get_bind().execute(text(...)).rowcount`; (5) `claimed_at` from a
    claim token or monotonic source is cleaner than wall-clock seconds; (6) at close, note that
    10-requirements.md says one intended test edit while the architecture records three and governs.
- [x] **STEP 3: Failing Repro Test**
  - [/] Execution done, awaiting review. 8 new files under `tests/` (no production change). All new tests assert the DESIRED behaviour and fail today for the reason listed; every file has a module `pytestmark = pytest.mark.timeout(...)`; new symbols are imported lazily inside the test (helpers `new_symbol`, `attr_of`, `exc_class`, `require_table` in `tests/receipt_support.py`), so collection stays clean. Fake sender: `tests/notice_support.py` (`FakeNoticeSender`, `send_result`); no Telegram contact.
  - [/] `tests/test_gift_receipt_service.py` (in-memory `WishlistService`, one store test). Red reasons: missing `WishItem.remaining_quantity/is_active/receipts` (`test_partial_then_full_receipt`, `test_unpromised_and_unstated_quantity`, `test_over_booked_state_and_promise_actions`); missing refusal classes (`test_refusals_closed_reasons[zero|negative|above_remaining|archived_wish|fully_received]`); `PermissionDeniedError` instead of the list-state reason (`test_refusals_closed_reasons[deleted_list]`, `test_archived_list_owner_gets_list_reason_not_forbidden`); missing `MyReservationItemDTO.is_fully_received` (`test_open_promise_on_fully_received_wish_stays_visible`); archived-set mismatch `{1,2,4} == {1,2}` (`test_views_share_one_active_predicate`); `KeyError remaining_quantity` (`test_projection_active_flag_and_public_filter`); missing `remaining_quantity` on DTO (`test_archive_split_and_restore`, `test_legacy_rows_in_views`); missing `list_gifted_items` (`test_gifted_read_authors_only_no_giver`); missing `GiftedItemDTO` (`test_gifted_dto_has_no_promise_fields`); table `wl_receipts` absent (`test_receipt_flushed_in_both_store_paths`). Guards that are GREEN today by design: `test_refusals_closed_reasons[non_member]`, `[gifter]`, `test_reduction_lock_after_receipt` (R-3.5).
  - [/] `tests/test_gift_receipt_api.py`. Red: receipt route 404 `{"detail":"Not Found"}` instead of 201/4xx/422/503/401 (`test_receipt_route_success_shape`, `test_receipt_route_reason_table[8 cases]`, `test_receipt_route_auth_and_csrf`, `test_receipt_route_unknown_field_422[2]`, `test_receipt_route_busy_503`); missing DTO fields (`test_new_dto_fields_have_defaults`); missing `GiftedItemDTO` (`test_gifted_route_and_read_data`); archive of a fully received wish answers 200 instead of 409 (`test_archive_restore_routes_nothing_remaining`).
  - [/] `tests/test_gift_receipt_migration.py`. Red: table `wl_receipts` absent after upgrade to head (`test_revisions_backfill_and_normalise`, `test_upgrade_is_repeatable`, `test_receipt_table_has_no_giver_column_and_downgrade_is_irreversible`, `test_cascade_on_purge_and_soft_delete_keeps_rows`).
  - [/] `tests/test_receipt_notices.py` (store-backed, SQL-level assertions). Red: table `notification_outbox` / settings tables absent (`test_producer_rules`, `test_producer_skips_recipient_and_unpromised`, `test_owner_with_promise_on_another_list_is_a_giver`, `test_settings_gate_matrix`, `test_settings_storage_only`); `WishlistStore._flush_receipt_effects` absent (`test_receipt_and_notice_atomic[execute_wish|execute]`); `wishenka.notices.*` module absent (lazy-import assertion, the intended defect is "component does not exist yet"): `test_sender_failure_leaves_receipt`, `test_rejected_fails_at_once_and_error_class_is_stored`, `test_at_most_one_extra_send`, `test_sender_outcome_order[3]`, `test_server_error_is_ambiguous[6]`, `test_unexpected_error_and_success_mapping`, `test_send_timeout_is_ambiguous`, `test_fresh_claim_is_not_reclaimed_by_a_second_worker`, `test_text_has_no_quantities`; `Settings.receipt_notice_*` fields absent (`test_retry_backoff_and_max_attempts`, `test_stale_sending_row_is_settled_not_sent`, `test_second_death_after_reclaim_fails_without_third_send`, `test_late_settle_write_is_ignored`, `test_lease_must_outlive_request_timeout`); no worker wiring (`test_token_never_logged_with_real_bot`: no `app.state.notice_task`; `test_no_token_no_worker_and_lifespan`: no INFO `receipt_notice_worker_disabled`).
  - [/] `tests/test_receipt_concurrency.py`. Red: `NothingRemainingError` absent (`test_two_receipts_race_same_process`, `test_two_receipts_race_spawned_processes`); table `wl_receipts` absent (`test_receipt_vs_promise_race`).
  - [/] `tests/test_surprise_receipt_walk.py` (NEW FILE, deviation from plan, see below). Red: `notification_outbox` absent (`test_recipient_walk_creates_no_notice_for_owner`); `GiftedItemDTO` absent (`test_second_walk_receipt_and_gifted_read_hide_the_booking`).
  - Existing tests NOT touched (their edits stay attached to dev steps 8, 9, 13): `tests/test_wishlist_migrations_concurrency.py` (green now, red once the first new revision exists until `_HEAD` is derived, step 8), `tests/test_surprise_role_context.py` (green now, red once the outbox table exists until the assertion is replaced, step 9), `tests/test_shared_inventory_multiprocess.py` line 602 (green now, red once `record_item_fulfillment` stops raising plain `ValueError`, step 13).
  - Deviations from the architecture table, for the reviewer: (1) the replaced absence assertion and the second walk of section 12 are written as new tests in a NEW file `tests/test_surprise_receipt_walk.py` instead of inside the protected `tests/test_surprise_role_context.py`; the step 9 and 29 edits of that file remain with dev (the new file stays valid next to them). (2) `test_lease_outlives_send_and_timeout_is_ambiguous` is split into `test_lease_must_outlive_request_timeout`, `test_send_timeout_is_ambiguous`, `test_fresh_claim_is_not_reclaimed_by_a_second_worker`; `test_cascade_on_purge_and_no_giver_column` is split in two; `test_second_death_after_reclaim_fails_without_third_send`, `test_rejected_fails_at_once_and_error_class_is_stored`, `test_unexpected_error_and_success_mapping`, `test_owner_with_promise_on_another_list_is_a_giver` and `test_projection_active_flag_and_public_filter` are added. (3) Assumed interfaces the design leaves open (tests will need adjusting only if Step 4 chooses otherwise): `NoticeStore(store, settings)`, `NoticeWorker(notice_store, sender, settings, clock=...)` with `await worker.run_once(now: int)`; `build_sender(settings)` returns an object whose `send(chat_id, text)` returns `SendResult` and is mapped from `aiogram.Bot.send_message` errors (the tests patch `Bot.send_message`); `SendOutcome` and `SendResult` live in `wishenka.notices.sender`; the app exposes the task as `app.state.notice_task`; the second ambiguous send is detected through `SendResult(AMBIGUOUS)` (an arbitrary exception from a fake sender is not exercised).
  - Review (separate subagent), test-only edits: `tests/test_receipt_notices.py::test_token_never_logged_with_real_bot` no longer clears the log, so startup records stay in the token scan (the idle check uses only the records after startup); added `test_notice_for_a_deleted_list_is_skipped_not_sent` (design 7, claim step 1, `target_gone`) and, in `tests/test_gift_receipt_api.py`, `test_receipt_route_non_integer_quantity_422` (design 6, body type error). Both new tests are red for the missing production component.
  - `make test` has no `PYTEST_ARGS`; narrowed runs used the `PYTEST` variable override, for example `make test PYTEST='.venv/bin/pytest tests/test_gift_receipt_api.py'`.
- [x] **STEP 4: Development**
  - Batch 1 of 4 (plan steps 1-9), executed by an execution subagent; STEP 4 stays `[/]`. Plan steps 2 and 3, and 8 and 9, were written in one pass each but are separate logical changes (different DTOs / different revisions).
  - [x] plan step 1: `ReceiptRecord`, `WishItem.receipts` (default empty list), properties `remaining_quantity`, `is_fully_received`, `is_gifted`, `is_active`, `is_in_archive`; `ReceiptRecord` exported (`wishenka/wishlists/models.py`, +43 lines).
  - [x] plan step 2: defaulted `remaining_quantity` / `is_fully_received` on the two view DTOs with `mode="before"` validators, `MyReservationItemDTO.is_fully_received=False` (`wishenka/wishlists/schemas.py`). `tests/test_item_input_parsing.py` and `tests/test_surprise_role_context.py` stay green unedited; `test_new_dto_fields_have_defaults` green.
  - [x] plan step 3: `GiftedItemDTO`, `ReceiptEntryDTO`, `ReceiptRequestDTO` (`extra="forbid"`), `ReceiptResultDTO` (`wishenka/wishlists/schemas.py`).
  - [x] plan step 4: `WishRefusalError` and `QuantityInvalidError`, `QuantityAboveRemainingError`, `NothingRemainingError`, `WishArchivedError` (`exceptions.py`); `WishlistAccessPolicy.is_recipient_id` (`is_recipient` delegates), `can_view_gifted` (`policy.py`).
  - [x] plan step 5: `wishenka/notices/__init__.py`, `wishenka/notices/models.py` (`EVENT_GIFT_RECEIVED`, status and skip-reason constants, `NoticeDraft`, `NoticeSettings`, `FlushedNotice`); `ReceiptRecord` imported under `TYPE_CHECKING` only, no import cycle.
  - [x] plan step 6: nine `receipt_notice_*` fields and one `model_validator` (backoff max >= base, lease >= request timeout + 30, poll interval <= window) in `wishenka/config.py`; `test_lease_must_outlive_request_timeout` green.
  - [x] plan step 7: `WishlistService.__init__` effect attributes `_new_receipts`, `_new_notices`, `_notice_settings` and read-only `notice_drafts` property (`service.py`).
  - [x] plan step 8: revision `add_gift_receipts` (table, index, back-fill, normalisation, counts via `op.get_bind().execute(text(...)).rowcount` logged as `legacy_receipts_backfilled` / `legacy_archived_rows_normalised`, irreversible `downgrade`); public `head_revision(database_url=in-memory default)` in `migrations.py`. Test edit: `_HEAD = head_revision()` in `tests/test_wishlist_migrations_concurrency.py`.
  - [x] plan step 9: revision `add_notice_outbox` (outbox, two settings tables, index). Test edit: the absence assertion in `tests/test_surprise_role_context.py` replaced by `notice_rows` (zero rows, none for the owner) and `receipt_columns` (no column outside the fixed five) assertions; `_NOTICE_TABLES` and `notification_tables` removed.
  - Deviation (minor, step 5): `FlushedNotice(outbox_id, status, gate=None)` and `NoticeDraft` (frozen dataclass, `status` default `pending`) field sets are chosen here; the design names the types but not their fields beyond `NoticeDraft(giver_user_id, receipt, status, skip_reason)`.
  - Deviation (minor, step 6): range rules are `Field(...)` constraints (`gt`, `ge`, `le`) for single-field limits; `receipt_notice_backoff_max_seconds` and `receipt_notice_claim_lease_seconds` are checked in the model validator because they depend on other fields.
  - Batch 2 of 4 (plan steps 10-18), executed by an execution subagent; STEP 4 stays `[/]`.
  - [x] plan step 10: store loads receipts (`_read`, `_load_wish`, ordered `received_at, id`) and notice settings (`_read` full, `_load_wish` scoped to the wish's reservation holders and its list); helpers `_receipt_from_row`, `_notice_settings_from_rows` (`store.py`, +85 lines). Existing store/multiprocess/booking tests green.
  - [x] plan step 11: `WishlistStore._flush_receipt_effects(conn, service) -> list[FlushedNotice]` (inserts `wl_receipts`, sets `receipt.id`, inserts outbox rows with `next_attempt_at = now`, gate `list`/`user` for skipped); called from `_persist_wish` (now returns `(written, flushed)`) and `_write` (now returns `flushed`) (`store.py`).
  - [x] plan step 12: after-commit DEBUG `receipt_notice_created` / `receipt_notice_skipped` on logger `wishenka.wishlists.notices` (`outbox_id`, `gate` only) from `execute_wish` and `_execute_once`; public `WishlistStore.transaction(work)` (one `BEGIN IMMEDIATE` via `_immediate`, `work(conn)`) (`store.py`).
  - [x] plan step 13: guarded `record_item_fulfillment` (keyword-only `wishlist_id`, guard order of design section 3, `ReceiptRecord` appended to `item.receipts` and `_new_receipts`, `item_fulfilled` + `fully_received`) (`service.py`). Test edit: `tests/test_shared_inventory_multiprocess.py:602` `error_type` is `NothingRemainingError`. Full suite after this step: 640 passed, 54 failed, all 54 in the new red files of batches 3-4.
  - [x] plan step 14: `WishlistService._notice_gate` (list row, user row, default on) and `_draft_receipt_notices` (distinct ACTIVE/PURCHASED givers in first-reservation order, recipient excluded via `is_recipient_id`, skipped drafts with `setting_list`/`setting_user`), called inside the receipt lock (`service.py`).
  - [x] plan step 15: `get_wishlist_view` (`is_active` / `is_in_archive`) and `list_wish_items` (`is_active`; with `include_archived` `not is_fully_received`) (`service.py`).
  - [x] plan step 16: `reorder_wish_items` and restore tail order over `is_active`; `archive_wish_item` refuses `NothingRemainingError` when fully received; `restore_wish_item` refuses when `remaining_quantity == 0` (`service.py`). HTTP mapping is batch 4 (step 30).
  - [x] plan step 17: module function `recipient_view(item)` extracted (used by `project_wish_item` and `get_wishlist_view`, passes `remaining_quantity`); gifter view gets `remaining_quantity` / `is_fully_received`; `get_user_reservations` sets `is_fully_received` explicitly (`service.py`).
  - [x] plan step 18: `list_gifted_items(wishlist_id, actor)` (members of a non-deleted list only, newest receipt first then id, receipts oldest first, no reservation data) (`service.py`).
  - Deviation (minor, step 13/4 fix): the batch 1 default message of `QuantityInvalidError` contained the digit 1 ("at least 1"), which breaks the "fixed message holds no numbers" rule asserted by `test_refusals_closed_reasons[zero|negative]`; changed to "Quantity must be a positive whole number" in `exceptions.py`. The route message of the design table (step 28, batch 4) still says "at least 1" and `tests/test_gift_receipt_api.py:57` expects that exact text, so the route keeps its own constant.
  - Test-only fix: `tests/test_receipt_notices.py:268` ignore code changed to `method-assign` (mypy, once `_flush_receipt_effects` exists).
  - Deviation (minor, step 11/12): `_persist_wish` and `_write` return the flushed notice rows so the commit-time DEBUG logs (step 12) can be written after commit; design did not fix these return types.
  - Starting state for batch 3: `store.transaction(work)` takes `work(conn: AsyncConnection)` and returns its result; commit on success, rollback on error, busy errors are raw `SQLAlchemyError` (not mapped). Outbox rows are written with `status` `pending`/`skipped`, `attempts = 0`, `ambiguous = 0`, `claimed_at` NULL, `next_attempt_at` integer epoch seconds (UTC now), ISO `created_at`/`updated_at`. Still red until batches 3-4: notice worker, sender, queue store, app wiring, cleanup, receipt/gifted routes, items route mapping (step 30), cabinet and `projection` (step 31).
  - Batch 3 of 4 (plan steps 19-27), executed by an execution subagent; STEP 4 stays `[/]`.
  - [x] plan step 19: `NoticeStore(store, settings)`, `ClaimedNotice`, `backoff_seconds`, `claim_next` (due query with title join, `target_gone` skip, pending claim, 50-row limit) (`wishenka/notices/store.py`).
  - [x] plan step 20: stale `sending` branch (`_settle_stale`: ambiguous transition first, `failed` with `StaleClaim` when already ambiguous or at max attempts, otherwise `pending` with backoff; never returned), DEBUG `receipt_notice_retry_scheduled` / `receipt_notice_failed_terminal` after commit (`notices/store.py`). Note: the due query written in step 19 already selected stale rows, so step 19 alone would have claimed them as pending; steps 19 and 20 were written back to back and verified together.
  - [x] plan step 21: `complete`, `fail`, `reschedule` over one guarded `_settle` write (`status = 'sending' AND claimed_at`), DEBUG `receipt_notice_late_write_ignored` (`notices/store.py`).
  - [x] plan step 22: `NoticeStore.purge_finished(threshold)`; `run_cleanup_cycle(..., notice_store=None)` and `background_cleanup_worker(..., notice_store=None)` purge in their own `try` (`receipt_notice_purge_failed` WARNING, `receipt_notice_rows_purged` INFO only when rows > 0) (`notices/store.py`, `wishlists/cleanup.py`). Cleanup tests green; full suite after this step: 652 passed, 42 failed (24 in `test_receipt_notices.py` = worker/sender/wiring then missing, 18 in batch-4 files).
  - [x] plan step 23: `SendOutcome`, `SendResult`, `NoticeSender`, `classify_error` (ordered chain, `TelegramEntityTooLarge` before the network entry), `AiogramNoticeSender` (`AiohttpSession(timeout=...)`, plain text), `build_sender` (None for empty, `dummy_bot_token` or invalid token) (`wishenka/notices/sender.py`). The 10 sender tests went green.
  - [x] plan step 24: `NoticeWorker(store, sender, settings, clock)`, `run_once(now)` drains all due rows, `wait_for(send, request_timeout + 5)`, guarded settle by outcome, template with titles cut at 100 characters, per-row DEBUG events with `outbox_id` (`wishenka/notices/worker.py`).
  - [x] plan step 25: `NoticeWorker.run(stop)` loop: idle tick silent, one ERROR `receipt_notice_worker_error` (`error_class`) per failure streak, backoff capped at 60 s (`worker.py`).
  - [x] plan step 26: window counters `sent` / `retried` / `failed_terminal` (counted only when the guarded write changed a row), `flush_if_due(now)` on the fixed grid, one INFO `receipt_notice_window_summary` only for a window with rows, nothing on stop (`worker.py`).
  - [x] plan step 27: `create_app(settings, notice_sender=None)`, `app.state.notice_store` / `notice_task` / `notice_sender`, `_start_notice_worker` (INFO `receipt_notice_worker_started`, or `receipt_notice_worker_disabled` with `reason` `no_bot_token` / `disabled_by_setting`), `_stop_notice_worker` in the lifespan `finally` (cancel, `sender.close()`, `receipt_notice_worker_stopped`); cleanup worker gets the `NoticeStore` (`wishenka/web/app.py`).
  - Tests added (new file `tests/test_receipt_notices_extra.py`, module timeout 60): `purge_finished` retention, cleanup cycle purge and log-only-when-rows, failing purge survives, titles cut at 100 characters, promise cancelled after the receipt still gets its notice, `run` loop sends until stopped, one ERROR per failure streak with backoff, window summary on a fixed grid.
  - Deviation (minor, step 23): `sender.py` is about 120 lines with docstrings (plan estimate 85); the logic is within the step, docstrings and the `classify_error` helper account for the excess. The worker and store steps are likewise somewhat above their estimates for docstring reasons.
  - Deviation (minor, step 27): the start and stop INFO events are written by `web/app.py` on logger `wishenka.wishlists.notices` (the design puts them in the lifespan); `NoticeWorker.run` itself logs no start/stop.
  - Deviation (minor, step 21): the guarded late-write DEBUG is written by `NoticeStore._settle` (not by the worker) so all three settle methods log it identically; event name and field are as in the design.
  - Full suite at the end of batch 3: 684 passed, 18 failed (only batch-4 red tests: 16 in `test_gift_receipt_api.py`, `test_gift_receipt_service.py::test_projection_active_flag_and_public_filter`, `test_surprise_receipt_walk.py::test_second_walk_...`); `make analyze` clean.
  - Starting state for batch 4: notice path complete and green (`tests/test_receipt_notices.py` all passing, plus the extra file). `app.state.wishlist_store`, `notice_store`, `notice_task` exist; `routes/receipts.py` is not created and not included in `create_app` (plan steps 28-29 add the router include). Remaining red: `tests/test_gift_receipt_api.py` (receipt and gifted routes, 409 mapping of archive/restore, DTO test), `tests/test_gift_receipt_service.py` (one case), `tests/test_surprise_receipt_walk.py` (second walk). Plan steps 30-31 (items route mapping, cabinet, projection) remain.
  - Batch 4 of 4 (plan steps 28-31), executed by an execution subagent; STEP 4 stays `[/]`.
  - [x] plan step 28: `POST /api/wishlists/{wishlist_id}/items/{item_id}/receipts` with `ReceiptRequestDTO` (422 on unknown field or non-integer), closed class -> (status, reason, fixed message) table `_REFUSALS`, `remaining_quantity` for `quantity_above_remaining` / `nothing_remaining`, busy -> 503 `{"reason": "busy", "message": <promise sentence>}`, runs through `execute_wish(..., operation_name="record_item_fulfillment")` or the injected service; router included in `create_app` (`wishenka/web/routes/receipts.py` new, ~190 lines with docstrings and logs; `wishenka/web/app.py` +2). Logs `receipt_refused`, `receipt_inventory_busy`, `receipt_recorded_http` carry no giver or quantity data. `tests/test_gift_receipt_api.py` receipt tests green.
  - [x] plan step 29: `GET /api/wishlists/{wishlist_id}/gifted` (`response_model=list[GiftedItemDTO]`, full snapshot read, same refusal table) in the same router (already mounted in step 28). `test_second_walk_receipt_and_gifted_read_hide_the_booking` green without edits to the test.
  - [x] plan step 30: `NothingRemainingError` joins the 409 tuple of `routes/items.py::execute`; in `routes/items_ui.py` a separate `except NothingRemainingError` + `_raise_nothing_remaining` (409, fixed message) in `archive_item_ui` and `restore_item_ui`; `_DOMAIN_ERRORS` untouched (`test_wishenka_112_structure.py` green).
  - [x] plan step 31: `CabinetRow.wish_received` and `offer_actions = (is_item_archived or is_fully_received) and not is_wishlist_archived` (`reservations_ui.py`); `projection` adds `remaining_quantity`, `is_active` and hides not-`is_active` wishes from non-members and public viewers (`wishlists.py`). No existing test relied on archived wishes in the public/non-member projection, so the filter was not narrowed.
  - Deviation (test edit, step 28): `tests/test_gift_receipt_api.py::test_receipt_route_reason_table` asserted that no message holds a digit, while the same table requires the exact message "Quantity must be a whole number of at least 1" (design 6 and `_REASONS`); the test contradicted itself for `quantity_invalid`. The digit check now strips the fixed phrase "at least 1" first (it is a minimum, not a booked or received count); all other cases still must be digit-free.
  - Deviation (minor, step 28): the `reason` for 404 `WishlistNotFoundError` is `not_found`, `WishlistDeletedError` is `wishlist_not_active` (per table); the gifted read uses the same table, so a non-member gets 403 `forbidden` and an unknown list 404 `not_found` (design 6).
  - [x] Fix round 1 (review FAIL, one gap: tick-start `now` stamped every claim of a long drain, so a late row looked stale to a second process): `NoticeWorker.run_once(now=None)` reads `int(self._clock())` afresh per claim and per settle (`_time`); an explicit `now` stays a test override for the whole call; `run()` calls `run_once()` and `flush_if_due(self._clock())` (`notices/worker.py`). Regression test `test_long_drain_stamps_each_claim_with_its_own_time` (`tests/test_receipt_notices_extra.py`): fake clock advances by lease + 1 per send, `claimed_at` equals the clock at each claim, a second `NoticeStore.claim_next` during the last send returns None and leaves the row `sending`, `ambiguous = 0`; verified red against a tick-start variant of the worker, green now. Optional: lifespan stops the notice worker in an inner `finally` (`web/app.py`); `NoticeStore.fail(..., ambiguous=)` stores the flag for an AMBIGUOUS give-up, worker passes it (`notices/store.py`, `worker.py`); `notice_drafts` docstring made accurate (`service.py`).
- [x] **STEP 5: Code Cleanup**
  - [x] `ai-tasks/WISHENKA-23/40-code-cleanup.md` written (analyze clean; 2 over-long lines fixed in tests; no behaviour change; STEP 5 stays `[/]` until review)
- [x] **STEP 6: Observability**
  - [/] `ai-tasks/WISHENKA-23/50-observability.md` written (audit of all log calls; 3 logging fixes in `receipts.py` and `service.py`; `tests/test_receipt_observability.py` +8 tests; metrics derivation, no exporter; STEP 6 stays `[/]` until review)
- [x] **STEP 7: Technical Debt Analysis**
  - [/] `ai-tasks/WISHENKA-23/60-tech-debt.md` written (no BLOCKER; timeout rule satisfied; 5 new tickets N1-N5 proposed; WISHENKA-22 Group 1 resolved; awaiting review)
  - [/] Fix round 1 (review FAIL, gaps G1-G5 fixed in `60-tech-debt.md`: S-1/S-2 reworded, ticket N2 dropped, N1 reduced; new tickets renamed T1-T5 (all Low); real test evidence 703/711 cited; missing divergences and residuals added as S-13 to S-18, C-12; awaiting re-review)
- [x] **STEP 8: Dev Docs**
  - [/] `doc/dev/gift-receipt.md` rewritten to the implemented backend (status block, routes, refusal table, DTOs, views, `wl_receipts`, migrations, notice path, worker and lifespan, nine settings, logging, metrics, troubleshooting, not-implemented list, WISHENKA-155..159)
  - [/] Planned-change notes converted to current statements in `doc/dev/items.md`, `reservations.md`, `architecture.md`, `verification-matrix.md` (S6); notes added in `doc/dev/migrations.md` (revisions 5 and 6, `head_revision()`, downgrade table, tests) and `doc/dev/wishlists.md` (cascade and purge of receipts and outbox rows, cleanup cycle)
  - [/] Fix round 1 after review FAIL: cabinet actions render for an archived or fully received wish on an active list (only the «received» marker is WISHENKA-24); quantity wording, `WISHENKA_LOG_LEVEL`, deleted-list wording, items.md exception tree and full stop, missing service WARNING events
  - [/] `in-docs/spec.md` unchanged (no sentence is wrong against the implemented rules); awaiting review
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-23/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-23/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-23/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-23/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-23/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/` (`gift-receipt.md`, `items.md`, `reservations.md`, `architecture.md`, `verification-matrix.md`, `migrations.md`, `wishlists.md`)

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
