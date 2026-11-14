# Wishlist Database Migrations (Alembic)

Introduced in [WISHENKA-111](https://pypost.atlassian.net/browse/WISHENKA-111). Schema changes of
the wishlist database are versioned Alembic revisions. The former ad-hoc table creation (`CREATE TABLE IF NOT EXISTS`)
and `ALTER TABLE` code in `WishlistStore` is removed.

## Overview

- The wishlist store (`wl_*` tables) reaches the Alembic head revision on every application start,
  before it serves requests.
- A fresh database is built by the revision chain. An existing database created by the previous
  ad-hoc code is recognized, stamped with the matching revision and then upgraded. Recognized
  legacy data is never rewritten.
- Concurrent startup of several processes on one database file is serialized by a lock file.
- The `users` table of `UserStore` is not covered by Alembic. It still creates its structures in
  `UserStore.initialize()` (see [auth.md](auth.md)).

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
4. `add_item_order_index` (head) - index `idx_wl_items_order ON wl_items(wishlist_id, display_order)`.

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

   The file lands in `wishenka/wishlists/alembic/versions/` as `<rev-id>_<slug>.py`; Alembic
   fills `down_revision` with the current head (`add_item_order_index` at the time of writing),
   keep the chain linear. The existing revisions use descriptive string ids and plain
   `<rev-id>.py` file names, so rename the generated file to match.
2. Implement `upgrade()` with `op.execute(...)` or `op.add_column(...)`. For SQLite, use
   `op.batch_alter_table` for operations it cannot do in place, and review the lock duration of
   table rebuilds on large files.
3. Implement `downgrade()` deliberately: either a safe reverse operation or an explicit refusal
   (see [Downgrade caveats](#downgrade-caveats)).
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

### Downgrade caveats

Downgrades are not a supported operational path. The policy is not finalized (WISHENKA-128).
Current state of the `downgrade()` functions:

| Revision | `downgrade()` |
| --- | --- |
| `add_item_order_index` | Works: `DROP INDEX idx_wl_items_order` |
| `add_display_order` | Raises `NotImplementedError` (SQLite cannot drop a column without a table rebuild) |
| `add_warn_on_delete_reserved` | Raises `NotImplementedError` (same reason) |
| `base_normalized` | Drops all nine baseline tables in reverse dependency order and destroys all wishlist data; no guard |

So a downgrade from head stops after the index and fails at `add_display_order`. Never run
`alembic downgrade base` on a database with data; restore from a backup instead.

## Testing

| Module | Covers |
| --- | --- |
| `tests/test_wishlist_alembic_migrations.py` | Legacy database adopted at head with rows preserved; fresh and `:memory:` stores reach the same head; `dispose()` removes the temporary file; the application lifespan disposes its `:memory:` store; rejection of a legacy schema with an ascending history index and of a malformed `display_order` marker |
| `tests/test_wishlist_migrations_concurrency.py` | Several processes start concurrently on one file, fresh and legacy `base_normalized` |
| `tests/test_wishlist_migrations_observability.py` | `started`/`completed` events, `legacy_schema_adopted` with `revision`, `failed` with re-raise, no paths in log fields |

Run them with the project test target (see [infrastructure.md](infrastructure.md)), for example:

```bash
pytest tests/test_wishlist_alembic_migrations.py \
  tests/test_wishlist_migrations_concurrency.py \
  tests/test_wishlist_migrations_observability.py
```

## Known Limitations

Tracked as Debt issues; details in `ai-tasks/WISHENKA-111/60-tech-debt.md`.

- [WISHENKA-125](https://pypost.atlassian.net/browse/WISHENKA-125) - no alert on slow migration
  startup.
- [WISHENKA-126](https://pypost.atlassian.net/browse/WISHENKA-126) - stray `core` dump file at the
  repository root, not gitignored.
- [WISHENKA-127](https://pypost.atlassian.net/browse/WISHENKA-127) - missing tests: adoption of
  each mapped revision and of the rejection paths, byte-identical file on failure.
- [WISHENKA-128](https://pypost.atlassian.net/browse/WISHENKA-128) - downgrade policy is
  undecided; tests for idempotent second start, non-SQLite URL and offline mode are missing.
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
