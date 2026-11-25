# Wishlist Database Migrations (Alembic)

Introduced in [WISHENKA-111](https://pypost.atlassian.net/browse/WISHENKA-111). Schema changes of
the wishlist database are versioned Alembic revisions. The former ad-hoc table creation (`CREATE TABLE IF NOT EXISTS`)
and `ALTER TABLE` code in `WishlistStore` is removed.

## Overview

- The wishlist store (`wl_*` tables) reaches the Alembic head revision on every application start,
  before it serves requests.
- A fresh database is built by the revision chain. An existing database created by the previous
  ad-hoc code is recognized, stamped with the matching revision and then upgraded. Recognized
  legacy data is preserved without being overwritten, with an explicit security remediation
  exception: `add_share_access_and_purge_favorites` irreversibly purges legacy non-member
  `wl_favorites` rows that lack verified share-link access, and
  `purge_legacy_non_member_view_history` irreversibly purges unverified non-member
  `wl_view_history` rows, on upgrade to head.
- Concurrent startup of several processes on one database file is serialized by a lock file.
- The `users` table of `UserStore` is also managed by Alembic (`unify_user_keys_and_cascades`):
  `UserStore.initialize()` delegates schema setup to `upgrade_to_head(self.database_url)` instead of
  maintaining duplicate DDL (see [users.md](users.md)).

## Architecture

| Component | Location | Role |
| --- | --- | --- |
| Migration runner | `wishenka/wishlists/migrations.py` | Adoption of legacy schema, `alembic upgrade head`, WAL selection, lock, logging |
| Alembic environment | `wishenka/wishlists/alembic/env.py` | Online mode on a short-lived synchronous connection (`NullPool`); offline mode emits SQL |
| Revisions | `wishenka/wishlists/alembic/versions/` | Ordered schema revisions |
| Revision template | `wishenka/wishlists/alembic/script.py.mako` | Template for `alembic revision` |
| Config | `alembic.ini` (repository root) | `script_location`, default `sqlalchemy.url` |
| Store | `wishenka/wishlists/store.py` | `WishlistStore.initialize()` calls the runner; `dispose()` cleans up |

Revision chain (linear):

1. `base_normalized` - the nine baseline tables `wl_lists`, `wl_members`, `wl_items`,
   `wl_reservations`, `wl_favorites`, `wl_view_history`, `wl_tokens`, `wl_invite_tokens`,
   `wl_counters` with their indexes.
2. `add_warn_on_delete_reserved` - `wl_lists.warn_on_delete_reserved INTEGER NOT NULL DEFAULT 1`.
3. `add_display_order` - `wl_items.display_order INTEGER NOT NULL DEFAULT 0`.
4. `add_item_order_index` - index `idx_wl_items_order ON wl_items(wishlist_id, display_order)`.
5. `add_gift_receipts` - table `wl_receipts` (no giver column) and `idx_wl_receipts_item`;
   back-fills one approximate record (`is_approximate = 1`, date = the wish's `updated_at`) per wish
   with `received_quantity > 0` and no record; clears `is_archived` on fully received archived
   rows. Idempotent, irreversible. Logs `legacy_receipts_backfilled` and
   `legacy_archived_rows_normalised` (INFO, field `rows`).
6. `add_notice_outbox` - tables `notification_outbox`, `user_notification_settings`,
   `wl_list_notification_settings` and `idx_notice_outbox_due`.
7. `add_bot_drafts` - table `bot_drafts` and indexes `ix_bot_drafts_owner`, `ix_bot_drafts_expiry`
   (see [bot-scenarios.md](bot-scenarios.md)).
8. `add_bot_capture_order` - table `bot_capture_order` (see [bot-scenarios.md](bot-scenarios.md)).
9. `add_birthday_reminders` - tables `bot_destinations`, `birthday_entries`, `birthday_input`,
   `reminder_outbox`, `notice_rate_slots`, `notice_scheduler_cursors` and indexes
   `idx_notice_rate_second`, `idx_reminders_due` (see [notifications.md](notifications.md)).
10. `add_notice_uncertain` - adds `requires_membership` to `reminder_outbox`, rebuilds
    `notification_outbox` with `status = 'uncertain'`, `claim_token`, and `requires_membership`,
    and creates `notice_receipt_keys` (see [notifications.md](notifications.md)).
11. `add_support_channel` - tables `support_input` and `support_tickets` with index
    `idx_support_tickets_owner_time` (see [bot-support.md](bot-support.md)).
12. `add_idempotency_records` - table `wl_idempotency_records` and index
    `idx_wl_idempotency_expires_at` (see [idempotency.md](idempotency.md)).
13. `add_user_locale` - adds `locale` and `locale_source` to `users` (see [i18n.md](i18n.md)).
14. `add_deleted_session_revocations` - table `deleted_session_revocations` (see [users.md](users.md)).
15. `add_notice_retention_columns` - adds `birthday_entries.deleted_at`,
    `bot_destinations.updated_at`, and `notice_receipt_keys.created_at` with their retention
    indexes, anonymizes legacy `deleted = 1` birthday rows, and backfills timestamps (see
    [notifications.md](notifications.md)).
16. `add_user_fk_cascades` - ensures `users` and `idx_users_telegram_id` exist, rebuilds
    `wl_members`, `wl_favorites`, and `wl_view_history` with
    `user_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE`, and removes
    orphaned rows whose `user_id` or `wishlist_id` has no matching parent row (see
    [wishlists.md](wishlists.md)).
17. `add_bot_capture_order_retention` - adds `updated_at INTEGER` and
    `idx_bot_capture_order_updated_at` to `bot_capture_order`, and backfills existing rows (see
    [bot-scenarios.md](bot-scenarios.md)).
18. `add_reminder_outbox_updated_at` - adds `updated_at INTEGER` and
    `idx_reminder_outbox_status_updated(status, updated_at)` to `reminder_outbox`, and backfills
    `COALESCE(claimed_at, next_attempt_at)` (see [notifications.md](notifications.md)).
19. `add_receipt_delivery_fence` - creates `receipt_delivery_fence` and
    `receipt_delivery_fence_audit` for per-giver receipt delivery coordination and audited fence
    resolution (see [notifications.md](notifications.md)).
20. `unify_user_keys_and_cascades` - consolidates `users` DDL (including `birth_day`,
    `birth_month`, `birth_year`, `birthdate_source`) in Alembic, migrates `bot_destinations`,
    `birthday_entries`, `birthday_input`, `support_input`, and `support_tickets` to
    `users(telegram_id)` with `ON DELETE CASCADE`, and adds `ON DELETE CASCADE` foreign keys on
    `wl_tokens`, `wl_invite_tokens` (backfilling `wishlist_id`), and `reminder_outbox` (`user_id`,
    `list_id`, `item_id`, `birthday_id`). Cleans orphaned rows during table rebuilds and logs
    `unify_user_keys_orphans_cleaned` / `unify_user_keys_migration_completed`.
21. `add_share_access_and_purge_favorites` - creates `wl_share_access` and
    `idx_wl_share_access_wishlist` for verified share-link access grants, and irreversibly purges
    legacy non-member `wl_favorites` rows as a security remediation. Logs
    `legacy_non_member_favorites_purged` (INFO, field `rows`; see [wishlists.md](wishlists.md)).
22. `purge_legacy_non_member_view_history` (head) - deletes `wl_view_history` rows whose user
    is neither the wishlist owner, nor a current `wl_members` row, nor a `wl_share_access`
    grant matching `wl_lists.public_token`. One-way security remediation (WISHENKA-303).
    Logs `legacy_non_member_view_history_purged` (INFO, field `rows`; see
    [wishlists.md](wishlists.md#viewing-history-access-wishenka-303)). `downgrade()` logs
    `wishlist_migration_downgrade_refused` and raises `NotImplementedError`.

Details of revisions 5 and 6 are in [gift-receipt.md](gift-receipt.md), revisions 7 and 8 in
[bot-scenarios.md](bot-scenarios.md), revisions 9 and 10 in [notifications.md](notifications.md),
revision 11 in [bot-support.md](bot-support.md), and revision 12 in [idempotency.md](idempotency.md).
The legacy-adoption map (`_REVISIONS`) still stops at `add_item_order_index`; adoption stamps that
revision and `upgrade head` then applies every later revision, including
`purge_legacy_non_member_view_history`.

`head_revision(database_url=...)` in `migrations.py` returns the head id from the script
directory without opening a database (the URL only builds the config, default in-memory). Tests
derive the expected head from it instead of a literal.

Column convention: after `upgrade_to_head()` every column above is guaranteed to exist, so the
store and repository code reads `warn_on_delete_reserved` and `display_order` directly. Do not
probe rows with `hasattr`/`getattr` and do not substitute defaults for a missing column. A missing
column is a schema bug and surfaces as an `AttributeError` (HTTP 500), not as a silent default.
Keep `None` guards for values that are nullable in the database. A new column goes in through a new
revision, see [Adding a new revision](#adding-a-new-revision).

Startup flow (`WishlistStore.initialize()` -> `upgrade_to_head()` -> `upgrade_to_head_sync()`,
run in `asyncio.to_thread` so the event loop is not blocked):

1. Log `wishlist_migration_started`.
2. Acquire the cross-process lock (file databases only; a `:memory:` store is backed by a temporary
   file and is locked like any file database, see [`:memory:` stores](#memory-stores)).
3. Adopt a recognized legacy database (stamp), if needed.
4. `alembic upgrade head`.
5. Select `PRAGMA journal_mode=WAL` on a separate `sqlite3` connection (file databases only; a
   `:memory:` store is backed by a temporary file and gets WAL like any file database).
6. Release the lock and log `wishlist_migration_completed` (or `wishlist_migration_failed`).

The application lifespan (`wishenka/web/app.py`) calls `wishlist_store.initialize()` at startup
and `wishlist_store.dispose()` at shutdown.

### WAL selection

`journal_mode=WAL` is persistent database state. It is selected once here, in the migration
startup, under the migration lock. It is deliberately not set on every pooled connection: two
workers racing to change the journal mode contend for SQLite's exclusive mode-change lock. The
store connection hook (`_configure_immediate_transactions`) sets only `foreign_keys=ON` and
`busy_timeout=5000` (plus `isolation_level = None` and `BEGIN IMMEDIATE` on `begin`).

### `:memory:` stores

Alembic uses its own synchronous connection, and a SQLite `:memory:` database is local to one
connection. `WishlistStore("sqlite+aiosqlite:///:memory:")` therefore creates an isolated
temporary file (`tempfile.mkstemp`, prefix `wishenka-`, suffix `.sqlite`) and points both the
async engine and Alembic at it. `await store.dispose()` disposes the engine and removes the
temporary file and its `.migrate.lock` sidecar. Always call `dispose()` for a `:memory:` store
(not `store.engine.dispose()`), otherwise the file stays in the system temp directory.
`dispose()` unlinks only the temporary file and the `.migrate.lock` sidecar. It does not remove
the `-wal` and `-shm` sidecars next to the temporary file; SQLite normally deletes them when the
last connection closes cleanly, but they can remain after a crash or an unclean close.
Because the store is backed by a real file, the migration lock and WAL selection run for
`:memory:` stores too. Only a direct `upgrade_to_head_sync("sqlite+aiosqlite:///:memory:")` call
skips both (the lock needs a path and the WAL step is guarded by `path is not None`).
`initialize()` does not dispose the store when it fails; the caller must (WISHENKA-132).

### Migration lock

Several service copies may start against one database file. `_migration_lock` takes an exclusive
`fcntl.flock` on the sidecar `<db>.migrate.lock` (next to the database, mode `0600`, ignored by
git via `*.migrate.lock`) and holds it for adoption, upgrade and WAL selection together. A late
process re-reads the state after acquiring the lock, sees `alembic_version` and runs a no-op
`upgrade head`.

- The wait is bounded: polling every 50 ms for at most 60 s, then a `TimeoutError`
  ("Timed out waiting for another process to finish wishlist migration").
- The lock relies on `fcntl`, so it is POSIX-only. The module imports `fcntl` at import time, so
  the wishlist package does not load on Windows.
- `:memory:` stores are locked too: `WishlistStore.__init__` rewrites the URL to a temporary file
  path. Only a direct `upgrade_to_head_sync("sqlite+aiosqlite:///:memory:")` call uses no lock.
- The sidecar file is not deleted for file databases; it is harmless.

## Usage

### Normal operation

Nothing to run manually. `WISHENKA_DATABASE_URL` (default `sqlite+aiosqlite:///data/wishenka.db`)
selects the database; the application migrates it on start. Only SQLite URLs of the form
`sqlite+aiosqlite:///<path>` are supported. Any other URL makes `WishlistStore.__init__` raise
`ValueError("Wishlist storage requires SQLite")` at construction, before `initialize()` and
without the "Unable to initialize wishlist storage" wrapper. The migrations-level
`ValueError("Wishlist migrations support only SQLite URLs")` is reachable only by calling
`upgrade_to_head_sync` or `upgrade_to_head` directly.

### Adding a new revision

1. Create a revision file from the repository root (the generation needs no database):

   ```bash
   alembic -c alembic.ini revision -m "add example column" --rev-id add_example_column
   ```

   The file lands in `wishenka/wishlists/alembic/versions/` as `<rev-id>_<slug>.py`, generated from
   `wishenka/wishlists/alembic/script.py.mako` (which scaffolds
   `ROLLBACK_POLICY = "reversible"`). Alembic fills `down_revision` with the current head; keep the
   chain linear. The existing revisions use descriptive string ids and plain `<rev-id>.py` file
   names, so rename the generated file to match.
2. Implement `upgrade()` with `op.execute(...)` or `op.add_column(...)`. For SQLite, use
   `op.batch_alter_table` for operations it cannot do in place, and review the lock duration of
   table rebuilds on large files. If `upgrade()` inspects live database state (for example via
   `PRAGMA`), guard that inspection with `context.is_offline_mode()` so offline SQL generation
   continues to work.
3. Set `ROLLBACK_POLICY` (`"reversible"` or `"one-way"`) and implement `downgrade()` accordingly:
   either a safe reverse operation or an explicit `NotImplementedError` refusal with
   backup-restoration guidance (see [Downgrade policy](#downgrade-policy)).
4. Update `_REVISIONS` in `wishenka/wishlists/migrations.py` if the new revision changes the
   structural markers used to recognize legacy databases. The adoption map names the head
   revision explicitly and nothing enforces this (WISHENKA-129). A legacy database already at
   the previous head must still be adopted at the right revision.
5. Add tests (see [Testing](#testing)) and update this document and the domain documents that
   describe the changed columns.

To apply the revisions to a database without starting the application, use the same entry point
as the store:

```bash
python -c "from wishenka.wishlists.migrations import upgrade_to_head_sync; \
upgrade_to_head_sync('sqlite+aiosqlite:///data/wishenka.db')"
```

This is the supported way: it takes the lock, adopts legacy files and selects WAL. The plain
`alembic upgrade` CLI is not equivalent: `alembic.ini` carries only the placeholder
`sqlalchemy.url = sqlite://` (an in-memory database), and the CLI neither adopts legacy files nor
selects WAL. Do not run migrations by hand against a database used by a running service.

### Offline SQL generation

To inspect the DDL statements without connecting to a live database, run Alembic in offline mode
from the repository root:

```bash
alembic -c alembic.ini upgrade head --sql
```

Programmatically, `command.upgrade(_configured(url), "head", sql=True)` writes the same SQL script
without creating or opening a database file (`env.py` routes to `run_migrations_offline()` with
`literal_binds=True`). Revisions that inspect live tables during online upgrades
(`add_gift_receipts`, `add_notice_uncertain`, `add_user_locale`, `add_notice_retention_columns`,
`add_user_fk_cascades`, and `add_bot_capture_order_retention`) branch on `context.is_offline_mode()`
so offline script generation completes cleanly.

### Legacy-schema adoption rules

A database file that has wishlist tables but no `alembic_version` table was created by the
pre-Alembic code. `_adopt_known_schema` stamps it (without changing data) only if it matches a
known historical shape exactly:

- The set of user tables equals the nine baseline tables.
- The markers select exactly one revision:

  | `warn_on_delete_reserved` column | `display_order` column | `idx_wl_items_order` index | Stamped revision |
  | --- | --- | --- | --- |
  | no | no | no | `base_normalized` |
  | yes | no | no | `add_warn_on_delete_reserved` |
  | yes | yes | no | `add_display_order` |
  | yes | yes | yes | `add_item_order_index` |

  Any other combination is rejected.
- The marker columns and the index must have exactly the historical definitions (types,
  `NOT NULL`, defaults, key order and direction).
- With the markers excluded, every table must equal the baseline structural signature: columns,
  foreign keys (including cascade actions) and indexes (including the descending
  `idx_wl_view_history_user_time` key).

After stamping, `upgrade head` applies the remaining revisions. A rejected database is not
stamped and not modified; the runner logs `wishlist_migration_failed` and the store raises.
A database that already has `alembic_version`, or no wishlist tables, is not adopted.

Behaviour change: the old store dropped and recreated all `wl_*` tables when `wl_lists` had a
legacy JSON `payload` column. That destructive path is gone; such a database is now rejected as
an unsupported schema.

## Configuration

| Setting | Where | Value |
| --- | --- | --- |
| `WISHENKA_DATABASE_URL` (`Settings.database_url`) | environment | `sqlite+aiosqlite:///<path>`; default `sqlite+aiosqlite:///data/wishenka.db` |
| `script_location` | set programmatically by `migrations._configured` | `wishenka/wishlists/alembic` (absolute path of the package directory) |
| `sqlalchemy.url` | set programmatically | the application URL with `sqlite+aiosqlite://` replaced by `sqlite://` |
| Lock file | constant `_LOCK_SUFFIX` | `<db>.migrate.lock` |
| Lock wait | constants `_LOCK_TIMEOUT_SECONDS`, `_LOCK_POLL_SECONDS` | 60 s, polled every 0.05 s |
| `busy_timeout`, `foreign_keys` | store connection hook | `5000` ms, `ON` |
| `journal_mode` | migration startup | `WAL` (file databases; a `:memory:` store is a temporary file and gets it too) |
| `WISHENKA_ALLOW_DESTRUCTIVE_BASELINE_DOWNGRADE` | environment | Set to `"1"` to allow `base_normalized.downgrade()` to drop the 9 baseline tables (disposable/test databases only; refused by default) |

The runner locates `alembic.ini` as `<repository root>/alembic.ini` (`Path(__file__).parents[2]`),
so it works from a source checkout only (WISHENKA-130).

## Observability

All events are logged on the `wishenka.wishlists.migrations` logger with an `event` extra.
Database paths and URLs are never logged.

| Event | Level | Extra fields | When |
| --- | --- | --- | --- |
| `wishlist_migration_started` | INFO | - | Start of `upgrade_to_head_sync` |
| `wishlist_migration_legacy_schema_adopted` | INFO | `revision` | A recognized legacy database was stamped |
| `wishlist_migration_completed` | INFO | `duration_ms` | Adoption, upgrade and WAL selection finished (message: `Wishlist database migration completed in N ms`) |
| `wishlist_migration_failed` | ERROR (with traceback) | - | Any exception; it is re-raised after logging |
| `wishlist_migration_downgrade_refused` | WARNING | `revision` | A one-way revision's `downgrade()` (including `base_normalized` without `WISHENKA_ALLOW_DESTRUCTIVE_BASELINE_DOWNGRADE=1`) refused execution |
| `wishlist_migration_destructive_baseline_downgrade` | WARNING | - | `base_normalized.downgrade()` executed with `WISHENKA_ALLOW_DESTRUCTIVE_BASELINE_DOWNGRADE=1` |
| `user_fk_migration_orphans_cleaned` | WARNING | `table`, `rows_removed`, `rows_kept` | `add_user_fk_cascades` upgrade removed orphaned rows while rebuilding `table` |
| `user_fk_migration_table_rebuilt` | INFO | `table`, `rows_kept` | `add_user_fk_cascades` upgrade rebuilt `table` with `user_id` cascade FK (0 orphans removed) |
| `user_fk_migration_completed` | INFO | `tables`, `total_orphans_removed` | `add_user_fk_cascades` upgrade finished rebuilding all target tables |
| `user_fk_downgrade_table_rebuilt` | INFO | `table`, `rows_kept` | `add_user_fk_cascades` downgrade rebuilt `table` without `user_id` FK |
| `user_fk_downgrade_completed` | INFO | `tables` | `add_user_fk_cascades` downgrade finished |
| `legacy_non_member_view_history_purged` | INFO | `rows` | `purge_legacy_non_member_view_history` upgrade deleted unverified non-member `wl_view_history` rows (online mode; offline mode emits the `DELETE` only) |

`duration_ms` covers the whole sequence including the lock wait. A normal start of an up-to-date
database logs `started` and `completed` only. There is no alert threshold yet (WISHENKA-125).

## Troubleshooting

- **`Unable to initialize wishlist storage` at startup.** `initialize()` wraps `OSError`,
  `RuntimeError`, `ValueError` and `SQLAlchemyError` from migration into this message. The real
  cause is the exception chain and the `wishlist_migration_failed` ERROR record.
- **`Unsupported wishlist database schema: ...`** (`RuntimeError`, logged as `failed`). The
  database has wishlist tables without `alembic_version` and does not match any known historical
  shape: the message names the mismatch (tables, incompatible markers, an invalid marker or a
  table that differs from the baseline). Nothing was changed. Restore a backup or repair the
  schema by hand to a recognized shape; do not stamp it blindly, a wrong stamp makes later
  revisions fail or hide drift.
- **`Timed out waiting for another process to finish wishlist migration`** (`TimeoutError`).
  Another process held `<db>.migrate.lock` for more than 60 s. Check for a hung or very slow
  migration (a table rebuild on a large file). The lock is released by the kernel when the
  holding process exits, so a crashed process does not leave it stuck, and the leftover file
  itself is harmless.
- **Several instances start at once.** Expected and safe: one process migrates, the others wait
  on the lock, then run a no-op `upgrade head`. Covered by
  `tests/test_wishlist_migrations_concurrency.py`.
- **`Wishlist storage requires SQLite`** (`ValueError`, raised by `WishlistStore.__init__` at
  construction, not wrapped). `WISHENKA_DATABASE_URL` is not `sqlite+aiosqlite:///...`.
- **`Wishlist migrations support only SQLite URLs`** (`ValueError`). Seen only when
  `upgrade_to_head_sync` or `upgrade_to_head` is called directly with a non-SQLite URL; the store
  rejects such URLs earlier.
- **Temporary `wishenka-*.sqlite` files accumulate in the temp directory.** A `:memory:`
  store was not disposed. Call `await store.dispose()`.
- **Import error for `fcntl` on Windows.** Windows is not supported; see the lock section.

### Downgrade policy

Every Alembic revision module under `wishenka/wishlists/alembic/versions/` (and the template
`wishenka/wishlists/alembic/script.py.mako`) declares a module-level `ROLLBACK_POLICY` constant
with one of two values:

- `"reversible"` — `downgrade()` reverses the schema change cleanly (any discarded transient or
  feature-specific data is noted below).
- `"one-way"` — `downgrade()` cannot safely reverse the change without data loss or a risky
  SQLite table rebuild. Calling `downgrade()` logs `wishlist_migration_downgrade_refused`
  (`WARNING`, `extra={"event": "wishlist_migration_downgrade_refused", "revision": ...}`) and
  raises `NotImplementedError` with backup-restoration guidance.

Production rollbacks across `"one-way"` revisions are handled by restoring a database backup taken
prior to the upgrade rather than running `alembic downgrade`.

#### Baseline safeguard (`base_normalized`)

`base_normalized` is classified as `"one-way"`. By default, `base_normalized.downgrade()` refuses
to run: it logs `wishlist_migration_downgrade_refused` (`revision="base_normalized"`) and raises
`NotImplementedError` without dropping any tables or data.

For disposable or test databases that intentionally need `alembic downgrade base`, set
`WISHENKA_ALLOW_DESTRUCTIVE_BASELINE_DOWNGRADE=1`. When this opt-in is set,
`base_normalized.downgrade()` logs `wishlist_migration_destructive_baseline_downgrade` (`WARNING`)
and drops all nine baseline tables in reverse dependency order.

#### Per-revision classification

| Revision | `ROLLBACK_POLICY` | `downgrade()` behavior |
| --- | --- | --- |
| `purge_legacy_non_member_view_history` | `one-way` | Logs `wishlist_migration_downgrade_refused` (`revision="purge_legacy_non_member_view_history"`) and raises `NotImplementedError` with backup-restoration guidance (purged unverified `wl_view_history` rows are not restored) |
| `add_share_access_and_purge_favorites` | `reversible` | Drops `idx_wl_share_access_wishlist` and `wl_share_access` (schema is reversible; the `upgrade()` purge of legacy non-member `wl_favorites` rows is intentionally irreversible as a security remediation) |
| `unify_user_keys_and_cascades` | `reversible` | Rebuilds `reminder_outbox`, `wl_invite_tokens`, `wl_tokens`, `support_tickets`, `support_input`, `birthday_input`, `birthday_entries`, and `bot_destinations` back to their pre-unification schemas (`users.id` mappings where applicable, no cascade FKs; orphaned rows removed during upgrade are not restored) |
| `add_receipt_delivery_fence` | `reversible` | Drops `receipt_delivery_fence_audit` and `receipt_delivery_fence` (discards active delivery fences and audit history) |
| `add_reminder_outbox_updated_at` | `reversible` | Drops `idx_reminder_outbox_status_updated` and `reminder_outbox.updated_at` if present (discards reminder retention timestamps) |
| `add_bot_capture_order_retention` | `reversible` | Drops `idx_bot_capture_order_updated_at` and `bot_capture_order.updated_at` if present (discards capture watermark retention timestamps) |
| `add_user_fk_cascades` | `reversible` | Rebuilds `wl_view_history`, `wl_favorites`, and `wl_members` in reverse order without `REFERENCES users(telegram_id) ON DELETE CASCADE` and recreates indexes (orphans cleaned during upgrade are not restored) |
| `add_notice_retention_columns` | `reversible` | Drops `idx_notice_receipt_keys_created`, `notice_receipt_keys.created_at`, `idx_bot_destinations_active_updated`, `bot_destinations.updated_at`, `idx_birthday_entries_deleted_at`, and `birthday_entries.deleted_at` (discards retention timestamps) |
| `add_deleted_session_revocations` | `reversible` | Drops `deleted_session_revocations` (discards session revocation records) |
| `add_user_locale` | `reversible` | Drops `locale_source` and `locale` from `users` if present (discards user locale preferences) |
| `add_idempotency_records` | `reversible` | Drops `wl_idempotency_records` and `idx_wl_idempotency_expires_at` (discards cached idempotency responses) |
| `add_support_channel` | `reversible` | Drops `idx_support_tickets_owner_time`, `support_tickets`, and `support_input` (discards support channel state) |
| `add_notice_uncertain` | `reversible` | Drops `requires_membership` from `reminder_outbox`, drops `notice_receipt_keys`, and rebuilds `notification_outbox` (mapping `uncertain` rows to `failed`) |
| `add_birthday_reminders` | `reversible` | Drops `notice_scheduler_cursors`, `notice_rate_slots`, `reminder_outbox`, `birthday_input`, `birthday_entries`, and `bot_destinations` (discards reminder and destination state) |
| `add_bot_capture_order` | `reversible` | Drops `bot_capture_order` (discards capture ordering watermarks) |
| `add_bot_drafts` | `reversible` | Drops `bot_drafts` (discards in-progress capture drafts) |
| `add_notice_outbox` | `reversible` | Drops `wl_list_notification_settings`, `user_notification_settings`, and `notification_outbox` (discards queued notices and settings) |
| `add_gift_receipts` | `one-way` | Logs `wishlist_migration_downgrade_refused` and raises `NotImplementedError` with backup-restoration guidance (normalised archived rows and receipt history cannot be reversed) |
| `add_item_order_index` | `reversible` | `DROP INDEX idx_wl_items_order` (no data loss) |
| `add_display_order` | `one-way` | Logs `wishlist_migration_downgrade_refused` and raises `NotImplementedError` with backup-restoration guidance (SQLite column drop requires rebuilding `wl_items`) |
| `add_warn_on_delete_reserved` | `one-way` | Logs `wishlist_migration_downgrade_refused` and raises `NotImplementedError` with backup-restoration guidance (SQLite column drop requires rebuilding `wl_lists`) |
| `base_normalized` | `one-way` | Guarded: logs `wishlist_migration_downgrade_refused` and raises `NotImplementedError` by default; logs `wishlist_migration_destructive_baseline_downgrade` and drops all 9 baseline tables only when `WISHENKA_ALLOW_DESTRUCTIVE_BASELINE_DOWNGRADE=1` |

A downgrade from the current head (`purge_legacy_non_member_view_history`) refuses
immediately. From `add_share_access_and_purge_favorites`, downgrade succeeds cleanly down
to `add_gift_receipts` and refuses at `add_gift_receipts` with backup-restoration guidance.

## Testing

| Module | Covers |
| --- | --- |
| `tests/test_wishlist_alembic_migrations.py` | Legacy database adopted at head with rows preserved; fresh and `:memory:` stores reach the same head; `dispose()` removes the temporary file; the application lifespan disposes its `:memory:` store; rejection of a legacy schema with an ascending history index and of a malformed `display_order` marker |
| `tests/test_wishlist_migrations_concurrency.py` | Several processes start concurrently on one file, fresh and legacy `base_normalized`; the expected head is `head_revision()` |
| `tests/test_gift_receipt_migration.py` | Back-fill and normalisation, repeatable upgrade, no giver column, irreversible downgrade, cascade on purge |
| `tests/test_wishlist_migrations_observability.py` | `started`/`completed` events, `legacy_schema_adopted` with `revision`, `failed` with re-raise, no paths in log fields |
| `tests/test_wishlist_migration_rollback_policy.py` | `ROLLBACK_POLICY` declared on all revisions; `base_normalized` default guard and `WISHENKA_ALLOW_DESTRUCTIVE_BASELINE_DOWNGRADE=1` opt-in; one-way refusal messages and `wishlist_migration_downgrade_refused` logs (including `purge_legacy_non_member_view_history`); reversible tail from `add_share_access_and_purge_favorites` to `add_gift_receipts`; idempotent second startup; non-SQLite URL rejection; offline SQL generation (`sql=True`) |

Run them with the project test target (see [infrastructure.md](infrastructure.md)), for example:

```bash
pytest tests/test_wishlist_alembic_migrations.py \
  tests/test_wishlist_migrations_concurrency.py \
  tests/test_wishlist_migrations_observability.py \
  tests/test_wishlist_migration_rollback_policy.py
```

## Known Limitations

Tracked as Debt issues; details in `ai-tasks/WISHENKA-111/60-tech-debt.md`.

- [WISHENKA-125](https://pypost.atlassian.net/browse/WISHENKA-125) - no alert on slow migration
  startup.
- [WISHENKA-126](https://pypost.atlassian.net/browse/WISHENKA-126) - stray `core` dump file at the
  repository root, not gitignored.
- [WISHENKA-127](https://pypost.atlassian.net/browse/WISHENKA-127) - missing tests: adoption of
  each mapped revision and of the rejection paths, byte-identical file on failure.
- [WISHENKA-129](https://pypost.atlassian.net/browse/WISHENKA-129) - `_adopt_known_schema` is long;
  historical marker DDL and the head revision name are duplicated in `migrations.py`.
- [WISHENKA-130](https://pypost.atlassian.net/browse/WISHENKA-130) - config depends on the
  repository-root `alembic.ini`; packaging of revisions is unverified; URL parsing uses string
  replace.
- [WISHENKA-131](https://pypost.atlassian.net/browse/WISHENKA-131) - the 10 s timeout of the
  Alembic test module is tight for slow CI.
- [WISHENKA-132](https://pypost.atlassian.net/browse/WISHENKA-132) - `initialize()` does not
  dispose a `:memory:` store on failure.
- [WISHENKA-133](https://pypost.atlassian.net/browse/WISHENKA-133) - redundant `:memory:` check
  in `WishlistStore.__init__`.
- [WISHENKA-134](https://pypost.atlassian.net/browse/WISHENKA-134) - existing tests call
  `store.engine.dispose()` instead of `store.dispose()`.
