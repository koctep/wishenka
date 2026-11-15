# WISHENKA-166: measured data (Step 2 appendix)

Raw numbers behind `20-architecture.md`. Machine: 6 cores (`nproc`), 5909 MiB RAM, no swap, Linux 6.8, `/tmp` is virtiofs, `/dev/shm` is tmpfs 64 MiB `noexec`. Python 3.13.5 in `.venv`, pytest 9.2.0, pytest-timeout 2.4.0, pytest-asyncio 1.4.1, pytest-xdist 3.8.0 (experiments only, installed outside `.venv`).
Durations come from `pytest --durations=0`; one row is one phase (call, setup, teardown) of one test, tests below the 5 ms report threshold are not listed. Group assignment is by module name.

## A. Serial baseline on disk (`/tmp`), command of `make test` plus `--durations=0`

Result: **798 passed, 1 warning in 971.70 s (0:16:11)**. Sum of reported phases 957.7 s: call 384.5 s, setup 536.8 s, teardown 36.5 s.

### A1. Per module (seconds; sorted by total)

| total | call | setup | teardown | tests | group | module |
|---:|---:|---:|---:|---:|---|---|
| 81.6 | 6.2 | 73.2 | 2.2 | 36 | other | `tests/test_receipt_ui_routes.py` |
| 51.8 | 2.8 | 46.6 | 2.4 | 24 | other | `tests/test_items_ui_error_mapping.py` |
| 48.8 | 48.8 | 0.0 | 0.0 | 24 | other | `tests/test_wishlist_api.py` |
| 47.6 | 9.4 | 36.7 | 1.4 | 27 | other | `tests/test_preview_resource_reuse.py` |
| 47.0 | 47.0 | 0.0 | 0.0 | 22 | other | `tests/test_receipt_notices.py` |
| 41.8 | 41.8 | 0.0 | 0.0 | 13 | concurrency | `tests/test_shared_inventory_multiprocess.py` |
| 40.1 | 2.2 | 37.1 | 0.8 | 19 | other | `tests/test_reservation_actions_api.py` |
| 37.3 | 1.8 | 34.2 | 1.3 | 16 | other | `tests/test_gift_receipt_api.py` |
| 35.7 | 1.8 | 32.1 | 1.8 | 17 | other | `tests/test_wish_card_giver_controls.py` |
| 35.5 | 2.1 | 31.7 | 1.7 | 17 | other | `tests/test_wish_items_crud_api.py` |
| 27.9 | 27.9 | 0.0 | 0.0 | 6 | concurrency | `tests/test_booking_ceiling_r5.py` |
| 24.9 | 1.6 | 22.2 | 1.2 | 12 | other | `tests/test_wish_items_tma_ui.py` |
| 23.5 | 2.2 | 20.4 | 0.9 | 11 | other | `tests/test_reservations_cabinet_ui.py` |
| 22.9 | 0.4 | 21.4 | 1.1 | 10 | other | `tests/test_wishlist_static_script.py` |
| 22.1 | 1.5 | 19.2 | 1.4 | 12 | other | `tests/test_receipt_card_ui.py` |
| 22.0 | 0.2 | 20.7 | 1.2 | 5 | other | `tests/test_wishlist_touch_reorder.py` |
| 19.6 | 0.7 | 18.3 | 0.6 | 8 | other | `tests/test_receipt_static_script.py` |
| 18.1 | 1.2 | 15.8 | 1.1 | 9 | other | `tests/test_gifted_section_ui.py` |
| 17.2 | 17.2 | 0.0 | 0.0 | 9 | other | `tests/test_receipt_notices_extra.py` |
| 17.0 | 0.6 | 15.6 | 0.8 | 8 | other | `tests/test_wishlist_management_ui.py` |
| 16.5 | 16.5 | 0.0 | 0.0 | 2 | concurrency | `tests/test_wishlist_migrations_concurrency.py` |
| 16.3 | 4.7 | 11.1 | 0.5 | 6 | other | `tests/test_wishlist_sections_ui.py` |
| 16.2 | 16.2 | 0.0 | 0.0 | 7 | other | `tests/test_receipt_observability.py` |
| 16.2 | 1.8 | 12.8 | 1.5 | 7 | other | `tests/test_cabinet_received_marker.py` |
| 15.4 | 10.8 | 0.8 | 3.8 | 19 | browser | `tests/test_wishlist_touch_reorder_browser.py` |
| 13.8 | 0.3 | 13.0 | 0.6 | 4 | other | `tests/test_wishlist_management_observability.py` |
| 13.7 | 0.8 | 12.3 | 0.6 | 7 | other | `tests/test_wishlists_htmx_sharing.py` |
| 12.0 | 12.0 | 0.0 | 0.0 | 6 | migration | `tests/test_wishlist_alembic_migrations.py` |
| 11.6 | 11.6 | 0.0 | 0.0 | 6 | other | `tests/test_token_cleanup_observability.py` |
| 11.4 | 11.4 | 0.0 | 0.0 | 6 | other | `tests/test_token_cleanup_background.py` |
| 11.1 | 5.7 | 3.5 | 1.8 | 9 | browser | `tests/test_receipt_modal_browser.py` |
| 11.0 | 1.1 | 9.4 | 0.5 | 5 | other | `tests/test_wish_items_list_reorder_ui.py` |
| 10.3 | 5.3 | 0.9 | 4.1 | 21 | browser | `tests/test_wishlist_cards_browser.py` |
| 9.8 | 0.5 | 8.9 | 0.4 | 5 | other | `tests/test_wishlist_sections_observability.py` |
| 9.3 | 9.3 | 0.0 | 0.0 | 4 | migration | `tests/test_gift_receipt_migration.py` |
| 9.1 | 0.6 | 8.1 | 0.4 | 5 | other | `tests/test_wishlists_htmx_observability.py` |
| 9.0 | 9.0 | 0.0 | 0.0 | 7 | other | `tests/test_auth_user_store.py` |
| 8.6 | 5.1 | 1.1 | 2.4 | 13 | browser | `tests/test_wishlist_mouse_reorder_browser.py` |
| 7.9 | 7.9 | 0.0 | 0.0 | 3 | concurrency | `tests/test_receipt_concurrency.py` |
| 7.2 | 7.2 | 0.0 | 0.0 | 3 | migration | `tests/test_wishlist_migrations_observability.py` |
| 6.6 | 6.6 | 0.0 | 0.0 | 4 | other | `tests/test_wishlists_sqlite_repo.py` |
| 6.6 | 6.6 | 0.0 | 0.0 | 4 | other | `tests/test_wishlists_sqlite_repo_observability.py` |
| 5.4 | 5.4 | 0.0 | 0.0 | 4 | other | `tests/test_auth_user_store_observability.py` |
| 4.0 | 0.3 | 3.8 | 0.0 | 2 | other | `tests/test_surprise_role_context.py` |
| 3.9 | 0.2 | 3.7 | 0.0 | 2 | other | `tests/test_surprise_receipt_walk.py` |
| 3.4 | 3.4 | 0.0 | 0.0 | 1 | browser | `tests/test_wishlist_management_browser.py` |
| 2.7 | 0.4 | 2.3 | 0.0 | 1 | other | `tests/test_receipt_ui_observability.py` |
| 2.3 | 2.3 | 0.0 | 0.0 | 2 | other | `tests/test_metadata_extractor_service.py` |
| 1.7 | 1.7 | 0.0 | 0.0 | 2 | other | `tests/test_gift_receipt_service.py` |
| 1.4 | 1.4 | 0.0 | 0.0 | 13 | make/subprocess | `tests/test_browser_prerequisites.py` |
| 0.4 | 0.4 | 0.0 | 0.0 | 3 | other | `tests/test_item_input_parsing.py` |
| 0.3 | 0.3 | 0.0 | 0.0 | 2 | other | `tests/test_item_observability.py` |
| 0.2 | 0.2 | 0.0 | 0.0 | 5 | other | `tests/test_auth.py` |
| 0.1 | 0.1 | 0.0 | 0.0 | 3 | other | `tests/test_ssrf_and_response_limits.py` |
| 0.0 | 0.0 | 0.0 | 0.0 | 1 | other | `tests/test_observability.py` |
| 0.0 | 0.0 | 0.0 | 0.0 | 1 | other | `tests/test_infra.py` |
| 0.0 | 0.0 | 0.0 | 0.0 | 2 | other | `tests/test_encoding_nested_graph.py` |
| 0.0 | 0.0 | 0.0 | 0.0 | 1 | other | `tests/test_wishenka_112_structure.py` |

### A2. Top 40 slowest tests (setup + call + teardown)

| s | test |
|---:|---|
| 9.30 | `tests/test_booking_ceiling_r5.py::test_repeated_contention_many_copies` |
| 8.67 | `tests/test_wishlist_migrations_concurrency.py::test_concurrent_startup_on_shared_database[legacy_base_normalized]` |
| 8.41 | `tests/test_booking_ceiling_r5.py::test_load_profile_one_copy_and_many_copies` |
| 7.98 | `tests/test_shared_inventory_multiprocess.py::test_locked_wish_raises_inventory_busy_and_leaves_balance` |
| 7.83 | `tests/test_wishlist_migrations_concurrency.py::test_concurrent_startup_on_shared_database[fresh]` |
| 6.67 | `tests/test_receipt_notices.py::test_send_timeout_is_ambiguous` |
| 4.87 | `tests/test_shared_inventory_multiprocess.py::test_receipt_is_not_capped_by_occupied_units` |
| 4.44 | `tests/test_preview_resource_reuse.py::test_cache_capacity_evicts_least_recently_used` |
| 4.31 | `tests/test_cabinet_received_marker.py::test_closed_promise_has_no_row` |
| 4.16 | `tests/test_wishlist_migrations_observability.py::test_fresh_database_logs_started_and_completed` |
| 4.02 | `tests/test_receipt_observability.py::test_notice_logger_info_records_are_one_summary_for_any_giver_count` |
| 3.90 | `tests/test_receipt_concurrency.py::test_two_receipts_race_spawned_processes` |
| 3.86 | `tests/test_wishlist_sections_ui.py::test_viewing_history_clear_endpoint` |
| 3.70 | `tests/test_receipt_notices.py::test_producer_skips_recipient_and_unpromised` |
| 3.66 | `tests/test_shared_inventory_multiprocess.py::test_increase_refused_leaves_earlier_promise` |
| 3.65 | `tests/test_receipt_modal_browser.py::test_summary_updates_and_dismiss_changes_nothing` |
| 3.64 | `tests/test_wishlist_alembic_migrations.py::test_fresh_and_memory_stores_reach_the_same_alembic_head` |
| 3.47 | `tests/test_receipt_notices.py::test_no_token_no_worker_and_lifespan` |
| 3.47 | `tests/test_receipt_ui_routes.py::test_get_modal_refusals_blocked_state[wish_archived]` |
| 3.45 | `tests/test_receipt_ui_routes.py::test_get_modal_refusals_blocked_state[list_archived]` |
| 3.44 | `tests/test_wishlist_management_browser.py::test_browser_copy_share_and_role_controls` |
| 3.34 | `tests/test_shared_inventory_multiprocess.py::test_lower_requested_quantity_sees_other_process_booking` |
| 3.29 | `tests/test_gift_receipt_api.py::test_receipt_route_unknown_field_422[extra1]` |
| 3.25 | `tests/test_wishlist_sections_ui.py::test_viewing_history_recording_ordering_deduplication_and_bounds` |
| 3.13 | `tests/test_gift_receipt_api.py::test_archive_restore_routes_nothing_remaining` |
| 3.07 | `tests/test_wishlist_static_script.py::test_items_list_wishlist_id_independent_of_query` |
| 3.06 | `tests/test_wishlist_migrations_observability.py::test_legacy_database_logs_adoption_with_revision` |
| 2.98 | `tests/test_shared_inventory_multiprocess.py::test_cancel_releases_units_once` |
| 2.97 | `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable` |
| 2.93 | `tests/test_booking_ceiling_r5.py::test_many_copies_one_unit_each` |
| 2.89 | `tests/test_booking_ceiling_r5.py::test_many_copies_whole_remainder` |
| 2.88 | `tests/test_shared_inventory_multiprocess.py::test_last_free_units_one_success_across_processes` |
| 2.88 | `tests/test_items_ui_error_mapping.py::test_unknown_item_gives_404[move]` |
| 2.87 | `tests/test_shared_inventory_multiprocess.py::test_smaller_quantity_releases_units_once` |
| 2.84 | `tests/test_gift_receipt_api.py::test_receipt_route_reason_table[list_deleted]` |
| 2.83 | `tests/test_wishlist_sections_ui.py::test_mini_app_home_sections_and_badges_browser` |
| 2.81 | `tests/test_receipt_notices.py::test_token_never_logged_with_real_bot` |
| 2.79 | `tests/test_shared_inventory_multiprocess.py::test_different_wishes_both_succeed` |
| 2.78 | `tests/test_items_ui_error_mapping.py::test_non_member_gives_404[archive]` |
| 2.68 | `tests/test_wishlist_management_ui.py::test_invitation_preview_is_read_only_and_confirmed_join_preserves_roles` |

## B. Serial on tmpfs (`/dev/shm` basetemp, patched clone, no xdist)

Result (generation 1, random order): **798 passed in 114.54 s** and **116 s wall** in two runs. Sum of reported phases 109.9 s: call 90.7 s, setup 8.2 s, teardown 11.0 s. Longest single test 5.94 s, longest module 13.4 s.

### B1. Top 25 slowest tests

| s | test |
|---:|---|
| 5.94 | `tests/test_shared_inventory_multiprocess.py::test_locked_wish_raises_inventory_busy_and_leaves_balance` |
| 5.81 | `tests/test_booking_ceiling_r5.py::test_repeated_contention_many_copies` |
| 5.05 | `tests/test_receipt_notices.py::test_send_timeout_is_ambiguous` |
| 4.03 | `tests/test_booking_ceiling_r5.py::test_load_profile_one_copy_and_many_copies` |
| 2.54 | `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads` |
| 2.32 | `tests/test_wishlist_migrations_concurrency.py::test_concurrent_startup_on_shared_database[legacy_base_normalized]` |
| 2.32 | `tests/test_wishlist_migrations_concurrency.py::test_concurrent_startup_on_shared_database[fresh]` |
| 2.22 | `tests/test_receipt_concurrency.py::test_two_receipts_race_spawned_processes` |
| 2.14 | `tests/test_shared_inventory_multiprocess.py::test_receipt_is_not_capped_by_occupied_units` |
| 1.85 | `tests/test_wishlist_management_browser.py::test_browser_copy_share_and_role_controls` |
| 1.85 | `tests/test_wishlist_sections_ui.py::test_mini_app_home_sections_and_badges_browser` |
| 1.64 | `tests/test_wishlist_mouse_reorder_browser.py::test_reorder_skipped_with_exactly_one_warning[id-missing]` |
| 1.61 | `tests/test_preview_resource_reuse.py::test_cache_capacity_evicts_least_recently_used` |
| 1.30 | `tests/test_metadata_extractor_service.py::test_real_heavy_extraction_keeps_loop_responsive[preview]` |
| 1.26 | `tests/test_receipt_modal_browser.py::test_stale_reorder_keeps_list_and_shows_notice` |
| 1.21 | `tests/test_metadata_extractor_service.py::test_real_heavy_extraction_keeps_loop_responsive[metadata]` |
| 1.17 | `tests/test_wishlist_touch_reorder_browser.py::test_next_tap_after_suppression_window_toggles[drop]` |
| 1.09 | `tests/test_shared_inventory_multiprocess.py::test_lower_requested_quantity_sees_other_process_booking` |
| 1.07 | `tests/test_wishlist_touch_reorder_browser.py::test_next_tap_after_suppression_window_toggles[cancel]` |
| 1.05 | `tests/test_wishlist_touch_reorder_browser.py::test_touch_cancel_paths_send_nothing[lostpointercapture]` |
| 0.98 | `tests/test_booking_ceiling_r5.py::test_many_copies_one_unit_each` |
| 0.96 | `tests/test_booking_ceiling_r5.py::test_many_copies_whole_remainder` |
| 0.82 | `tests/test_wishlist_touch_reorder_browser.py::test_touch_drag_handle_reorders[expanded-card]` |
| 0.77 | `tests/test_shared_inventory_multiprocess.py::test_smaller_quantity_releases_units_once` |
| 0.75 | `tests/test_wishlist_mouse_reorder_browser.py::test_repeated_reorder_without_reload` |

### B2. Per module, top 15

| total | call | setup | teardown | tests | group | module |
|---:|---:|---:|---:|---:|---|---|
| 13.4 | 9.3 | 0.6 | 3.5 | 19 | browser | `tests/test_wishlist_touch_reorder_browser.py` |
| 12.9 | 12.9 | 0.0 | 0.0 | 13 | concurrency | `tests/test_shared_inventory_multiprocess.py` |
| 11.9 | 11.9 | 0.0 | 0.0 | 6 | concurrency | `tests/test_booking_ceiling_r5.py` |
| 7.8 | 3.5 | 0.6 | 3.7 | 21 | browser | `tests/test_wishlist_cards_browser.py` |
| 7.4 | 5.6 | 0.3 | 1.6 | 9 | browser | `tests/test_receipt_modal_browser.py` |
| 7.2 | 4.0 | 0.9 | 2.2 | 13 | browser | `tests/test_wishlist_mouse_reorder_browser.py` |
| 6.1 | 6.1 | 0.0 | 0.0 | 21 | other | `tests/test_receipt_notices.py` |
| 4.6 | 4.6 | 0.0 | 0.0 | 2 | concurrency | `tests/test_wishlist_migrations_concurrency.py` |
| 3.4 | 2.8 | 0.6 | 0.0 | 27 | other | `tests/test_preview_resource_reuse.py` |
| 2.8 | 2.7 | 0.1 | 0.0 | 6 | other | `tests/test_wishlist_sections_ui.py` |
| 2.5 | 2.2 | 0.3 | 0.0 | 19 | other | `tests/test_reservation_actions_api.py` |
| 2.5 | 2.5 | 0.0 | 0.0 | 2 | other | `tests/test_metadata_extractor_service.py` |
| 2.3 | 2.3 | 0.0 | 0.0 | 3 | concurrency | `tests/test_receipt_concurrency.py` |
| 2.1 | 1.5 | 0.6 | 0.0 | 36 | other | `tests/test_receipt_ui_routes.py` |
| 2.1 | 2.1 | 0.0 | 0.0 | 10 | make/subprocess | `tests/test_browser_prerequisites.py` |


### B3. Generation 2 (H1, serial tmpfs, file order): longest tests and modules (source of the Amdahl figures)

Sum of phases 110.9 s (call 90.8, setup 8.6, teardown 11.5); groups: browser 40.5 s, other 34.7 s, multiprocess 31.5 s, make/subprocess 2.0 s, migration 2.1 s. Longest test 5.92 s, longest module 13.5 s; ideal bound 110.9 / 6 = 18.5 s.

| s | longest tests |
|---:|---|
| 5.92 | `tests/test_shared_inventory_multiprocess.py::test_locked_wish_raises_inventory_busy_and_leaves_balance` |
| 5.70 | `tests/test_booking_ceiling_r5.py::test_repeated_contention_many_copies` |
| 5.05 | `tests/test_receipt_notices.py::test_send_timeout_is_ambiguous` |
| 3.95 | `tests/test_booking_ceiling_r5.py::test_load_profile_one_copy_and_many_copies` |
| 2.44 | `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads` |

| module total (s) | module |
|---:|---|
| 13.5 | `tests/test_wishlist_touch_reorder_browser.py` |
| 13.0 | `tests/test_shared_inventory_multiprocess.py` |
| 11.7 | `tests/test_booking_ceiling_r5.py` |
| 9.5 | `tests/test_receipt_modal_browser.py` |
| 8.0 | `tests/test_wishlist_mouse_reorder_browser.py` |
| 7.4 | `tests/test_wishlist_cards_browser.py` |
| 6.1 | `tests/test_receipt_notices.py` |
| 4.7 | `tests/test_wishlist_migrations_concurrency.py` |

Risk-area modules (H1): `test_booking_ceiling_r5.py` 11.7 s, `test_receipt_concurrency.py` 2.2 s, `test_shared_inventory_multiprocess.py` 13.0 s, `test_wishlist_migrations_concurrency.py` 4.7 s, `test_browser_prerequisites.py` 2.0 s.

## C. Six workers on tmpfs (`-n 6 --dist load`), top 15 tests by duration under load

Sum of reported phases 326.2 s (3.0 times the serial-tmpfs sum): the same tests run slower when six workers, their Chromium processes and spawned test processes share 6 cores.

| s | test |
|---:|---|
| 25.10 | `tests/test_booking_ceiling_r5.py::test_repeated_contention_many_copies` |
| 13.84 | `tests/test_shared_inventory_multiprocess.py::test_lower_requested_quantity_sees_other_process_booking` |
| 12.93 | `tests/test_wishlist_migrations_concurrency.py::test_concurrent_startup_on_shared_database[legacy_base_normalized]` |
| 11.54 | `tests/test_preview_resource_reuse.py::test_cache_capacity_evicts_least_recently_used` |
| 11.23 | `tests/test_shared_inventory_multiprocess.py::test_receipt_is_not_capped_by_occupied_units` |
| 11.20 | `tests/test_receipt_concurrency.py::test_two_receipts_race_spawned_processes` |
| 6.42 | `tests/test_shared_inventory_multiprocess.py::test_locked_wish_raises_inventory_busy_and_leaves_balance` |
| 5.26 | `tests/test_wishlist_mouse_reorder_browser.py::test_mouse_drop_before_or_after_target_midpoint[first-onto-third-bottom]` |
| 5.06 | `tests/test_receipt_notices.py::test_send_timeout_is_ambiguous` |
| 4.85 | `tests/test_browser_prerequisites.py::test_fixture_opt_out_is_ignored_in_ci` |
| 4.79 | `tests/test_wishlist_cards_browser.py::test_nested_controls_do_not_toggle[textarea]` |
| 4.56 | `tests/test_wishlist_touch_reorder_browser.py::test_next_tap_after_suppression_window_toggles[drop]` |
| 4.36 | `tests/test_wishlist_migrations_concurrency.py::test_concurrent_startup_on_shared_database[fresh]` |
| 4.34 | `tests/test_booking_ceiling_r5.py::test_load_profile_one_copy_and_many_copies` |
| 4.15 | `tests/test_wishlist_alembic_migrations.py::test_app_lifespan_disposes_its_memory_wishlist_store` |

## D. Re-measurement without pytest-randomly (generation 2, reference)

Generation 1 (sections B, C and the experiment index E below) ran with pytest-randomly 5.1.0 on `PYTHONPATH`
(random order). Generation 2 uses `-p no:randomly` (file order). Same machine, same scratch copy of `tests/` with the
fixes of `20-architecture.md` (tmpfs `basetemp`, Chromium profile and exec fakes on disk, port-file wait, J-runs also
fast `TMPDIR` and default-database isolation).

| Id | Setup | Wall | Result | Sum of phases | Memory (peak drop / min available, MiB, / Chromium procs; `/dev/shm` peak 4.3 to 5.6 MiB in generation 2) |
|---|---|---:|---|---:|---|
| H1 | serial, tmpfs | 114.1 s | 798 passed | 110.9 s (call 90.8, setup 8.6, teardown 11.5) | 744 MiB / 4073 MiB / 23 |
| H2 | `-n 6 --dist load`, tmpfs | 63.3 s | 798 passed | 312.6 s | 3036 MiB / 1823 MiB / 59 |
| H3 | `-n 6 --dist load`, tmpfs | 56.6 s | 798 passed | 274.5 s | 2949 MiB / 1837 MiB / 57 |
| H4 | `-n 6 --dist loadfile`, tmpfs | 47.8 s | 798 passed | 211.2 s | 2737 MiB / 1997 MiB / 42 |
| I1 | `-n 6 --dist load`, **disk**, original `tests/` | 981 s | **28 failed, 9 errors, 763 passed**, 31 timeout messages | n/a | 2953 MiB / 1828 MiB / 73 |
| J1 | H2 plus fast `TMPDIR`, default-DB isolation | 55.1 s | 798 passed | 256.6 s | 3115 MiB / 1697 MiB / 57 |
| J2 | serial, tmpfs, fast `TMPDIR` | 112.6 s | 798 passed | n/a | n/a |

* Slowdown under six workers: sum of phases 312.6 / 274.5 / 211.2 / 256.6 s against 110.9 s serial = 2.8 / 2.5 / 1.9 /
  2.3 times.
* Worst `duration / limit` under six workers: 0.24 (`test_shared_inventory_multiprocess.py::test_receipt_is_not_capped_by_occupied_units`,
  14.3 s of 60 s); `test_booking_ceiling_r5.py::test_repeated_contention_many_copies` 22.3 s of its 90 s mark.
* I1 failed modules (count of failed/errored tests): `auth_user_store_observability` 3, `auth_user_store` 2,
  `booking_ceiling_r5` 2, `shared_inventory_multiprocess` 4, `token_cleanup_background` 3, `token_cleanup_observability` 4,
  `wishlist_alembic_migrations` 2, `wishlist_management_browser` 1, `wishlist_migrations_concurrency` 1,
  `wishlists_htmx_sharing` 2 failed + 2 errors, `wishlists_sqlite_repo` 3, `wishlists_sqlite_repo_observability` 1 + 1,
  `wishlists_htmx_observability` 5 errors, `wishlist_management_observability` 1 error (`test_miniapp_shell_requested_log`).
* After J1 and J2: `/dev/shm` empty, no Chromium process; after J1, `/tmp/wk-*` holds the scratch copy's Chromium profile
  directories (the scratch copy does not clean them; the design does, D13).
* Validations in scratch: optional hook without xdist (works) and plain hook (`PluginValidationError`); hook runs before
  `pytest_configure`; `setpriv --pdeathsig KILL` leaves 0 processes after a parent `SIGKILL` (plain 9,
  `start_new_session` 9).

## D2. Step 4 verification results

To be filled during Step 4 (P7, P8): K=3 parallel runs, serial run, memory peak, leftovers, headroom audit.

## E. Experiment index, generation 1 (random order, pytest-randomly 5.1.0)

| Id | Setup | Wall | Outcome |
|---|---|---:|---|
| E0 | serial, disk | 971.7 s | 798 passed |
| E1 | `-n 6`, disk | killed after about 19 min | hang at 99 % |
| E2 | `-n 6`, disk | 842 s | 25 failed, 6 errors (28 timeouts of 10 s) |
| E3 | `-n 6`, tmpfs basetemp | 62 s | 788 passed, 10 failed (9 exec on noexec) |
| E4 | `-n 6`, disk, `synchronous=OFF` | 394 s | 4 failed, 2 errors |
| E5 | E3 plus exec fix | 52 s | 789 passed, 9 errors (CDP port-file race) |
| F1 | `-n 6 --dist load` | 51 s | 798 passed |
| F2 | `-n 6 --dist worksteal` | 70 s | 798 passed |
| F3 | `-n 6 --dist loadfile` | 51 s | 798 passed |
| F4 | `-n 4 --dist load` | 64 s | 798 passed |
| F5 | `-n 3 --dist load` | 65 s | 798 passed |
| F6 | `-n 6 --dist load` (repeat) | 63 s | 798 passed |
| G1 | serial, tmpfs, `--durations=0` | 116 s | 798 passed |
| G2 | `-n 6`, tmpfs, `--durations=0` | 66 s | 798 passed; memory peak drop 3090 MiB, min available 1542 MiB, 68 Chromium processes, `/dev/shm` 6.4 MiB (generation 1) |

E3 to G2 ran from a scratch copy of `tests/` with: tmpfs `basetemp` and `tmp_path_retention_policy=failed`, Chromium
profile on disk, exec-capable `tmp_path` in `test_browser_prerequisites.py`, non-empty port-file wait in
`browser_cdp.py`. The repository itself was not modified.
