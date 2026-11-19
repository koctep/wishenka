# WISHENKA-128: Observability Implementation

## Logging Implementation

### Added Logs

Logger used across the migration subsystem: `wishenka.wishlists.migrations`.

- **ERROR**: [wishenka/wishlists/migrations.py](file:///home/src/wishenka/wishlists/migrations.py#L278-L283) — `logger.exception` with `event="wishlist_migration_failed"` on migration or legacy-adoption failures (existing).
- **WARNING**:
  - [wishenka/wishlists/alembic/versions/base_normalized.py](file:///home/src/wishenka/wishlists/alembic/versions/base_normalized.py#L79-L83) — `event="wishlist_migration_downgrade_refused"`, `revision="base_normalized"` when `downgrade()` is called without `WISHENKA_ALLOW_DESTRUCTIVE_BASELINE_DOWNGRADE=1` (added).
  - [wishenka/wishlists/alembic/versions/base_normalized.py](file:///home/src/wishenka/wishlists/alembic/versions/base_normalized.py#L89-L93) — `event="wishlist_migration_destructive_baseline_downgrade"` when `downgrade()` executes with `WISHENKA_ALLOW_DESTRUCTIVE_BASELINE_DOWNGRADE=1` (existing).
  - [wishenka/wishlists/alembic/versions/add_warn_on_delete_reserved.py](file:///home/src/wishenka/wishlists/alembic/versions/add_warn_on_delete_reserved.py#L26-L30) — `event="wishlist_migration_downgrade_refused"`, `revision="add_warn_on_delete_reserved"` when one-way `downgrade()` is refused (added).
  - [wishenka/wishlists/alembic/versions/add_display_order.py](file:///home/src/wishenka/wishlists/alembic/versions/add_display_order.py#L25-L29) — `event="wishlist_migration_downgrade_refused"`, `revision="add_display_order"` when one-way `downgrade()` is refused (added).
  - [wishenka/wishlists/alembic/versions/add_gift_receipts.py](file:///home/src/wishenka/wishlists/alembic/versions/add_gift_receipts.py#L78-L82) — `event="wishlist_migration_downgrade_refused"`, `revision="add_gift_receipts"` when one-way `downgrade()` is refused (added).
- **INFO**:
  - [wishenka/wishlists/migrations.py](file:///home/src/wishenka/wishlists/migrations.py#L258-L261) — `event="wishlist_migration_started"` at the start of `upgrade_to_head_sync()` (existing).
  - [wishenka/wishlists/migrations.py](file:///home/src/wishenka/wishlists/migrations.py#L215-L219) — `event="wishlist_migration_legacy_schema_adopted"` with `revision` when `_adopt_known_schema()` stamps a legacy schema (existing).
  - [wishenka/wishlists/migrations.py](file:///home/src/wishenka/wishlists/migrations.py#L286-L290) — `event="wishlist_migration_completed"` with `duration_ms` on successful completion (existing).
  - [wishenka/wishlists/alembic/versions/add_gift_receipts.py](file:///home/src/wishenka/wishlists/alembic/versions/add_gift_receipts.py#L65-L73) — `event="legacy_receipts_backfilled"` and `event="legacy_archived_rows_normalised"` with `rows` count during online `upgrade()` (existing).

### Log Structure

- Structured logs: yes (via `extra={...}` fields: `event`, `revision`, `duration_ms`, `rows`)
- Includes context: yes (revision ID on adoption and downgrade refusals; duration in ms on completion; row counts on backfill/normalization)
- Sensitive data excluded: yes (no `db_path`, `database_url`, or row payloads are logged)
- Log levels: `INFO`, `WARNING`, `ERROR`

## Metrics Implementation (if applicable)

### Performance Metrics

- **Migration duration**: `duration_ms` field emitted in `wishlist_migration_completed` structured log at [wishenka/wishlists/migrations.py](file:///home/src/wishenka/wishlists/migrations.py#L285-L290) (existing).

### Business Metrics

- Not applicable (schema migration lifecycle).

### System Health Metrics

- Not applicable beyond structured startup migration events (`started` / `completed` / `failed`) and downgrade refusal/destructive-downgrade warnings.

## Monitoring Integration

- [ ] Prometheus metrics (not used in this repository for migration lifecycle)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Structured Python logging via `wishenka.wishlists.migrations` (`extra={"event": ...}`)

## Validation Results

- [x] Logs are correctly formatted (`make analyze` — Ruff lint, Ruff format check, and Mypy passed across 217 source files)
- [x] Logging works in error and refusal scenarios (`tests/test_wishlist_migrations_observability.py`, `tests/test_wishlist_migration_rollback_policy.py` — 20 passed in 48.46s across all 3 migration/observability test files)
- [x] Large data structures and sensitive paths/URLs are not logged (verified by `_assert_no_sensitive_data` in `tests/test_wishlist_migrations_observability.py` and `revision`-only context in downgrade refusal logs)

## Notes

- `ai-tasks/WISHENKA-128/00-roadmap.md` has STEP 6 marked `[/]` with `ai-tasks/WISHENKA-128/50-observability.md` listed as sub-item; `[x]` is left for the orchestrator after review passes.
