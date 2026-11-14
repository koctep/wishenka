# WISHENKA-111: Technical Debt Analysis

Scope: `wishenka/wishlists/migrations.py`, `wishenka/wishlists/alembic/`, `alembic.ini`, the
changes to `wishenka/wishlists/store.py` and `wishenka/web/app.py`, and the tests
`tests/test_wishlist_alembic_migrations.py` and `tests/test_wishlist_migrations_observability.py`.

Timeout markers: both test modules declare a module-level `pytest.mark.timeout` (10 s and 30 s),
so every collected test of this task is covered. No timeout-marker BLOCKER.

## Shortcuts Taken

- **Temporary file for `:memory:` stores.** `WishlistStore` backs `:memory:` with a
  `tempfile.mkstemp` file because Alembic uses a separate synchronous connection. This is a
  deliberate workaround of the sync/async split. If `dispose()` is never called (a test or a
  script that skips it), the file leaks in the system temp directory. Behaviour also differs from
  real in-memory SQLite (disk I/O, WAL files `-wal`/`-shm` next to the temp file).
- **Adoption signature rebuilt on every call.** `_baseline_signatures()` and
  `_marker_signatures()` each import the baseline revision and build a reference in-memory
  database on every adoption. It runs once, only for legacy files, so it is cheap, but it is not
  cached.
- **`_marker_signatures()` re-states historical DDL by hand.** The `ALTER TABLE ... ADD COLUMN`
  and `CREATE INDEX idx_wl_items_order` statements are duplicated from the later revisions rather
  than derived from them. If a revision is edited, the adoption contract can silently drift.
- **Adoption reads revisions via `importlib` by module path string**
  (`wishenka.wishlists.alembic.versions.base_normalized`) and reuses its `DDL` constant as a
  public contract of a migration file.
- **WAL is set outside Alembic.** `PRAGMA journal_mode=WAL` is executed in
  `upgrade_to_head_sync` after `command.upgrade`, because it is persistent database state and
  not a revision. This is a justified deviation, but it is one more place where the schema state
  is decided in application code rather than in a revision. It is not mentioned in
  `20-architecture.md`.
- **Error mapping is coarse.** `WishlistStore.initialize` maps `OSError`, `RuntimeError`,
  `ValueError` and `SQLAlchemyError` to one `RuntimeError("Unable to initialize wishlist storage")`.
  The cause is chained, but the actionable "unsupported schema" message the architecture asks for
  is visible only through the chain and the ERROR log.

## Code Quality Issues

- **`_adopt_known_schema` is too long (about 74 lines, `migrations.py` lines 126-199) and does
  six things:** reads tables, derives marker flags, selects the revision, validates markers,
  compares every table signature, then stamps and logs. It should be split into a pure `detect_revision(connection)`, a
  `validate_against_baseline(connection, flags)` and a thin stamping wrapper. The per-table loop
  has marker-specific branches (`wl_lists`, `wl_items`) that are hard to follow.
- **Marker flags are tuple-indexed** (`flags[0]`, `flags[1]`, `flags[2]`). A small named tuple or
  dataclass would remove the magic indexes.
- **Revision names and the `_TABLES` set are hardcoded in `migrations.py`** and duplicated from
  the baseline DDL. Adding a table or revision requires touching `migrations.py`, the revision
  file and the architecture document. The adoption map `_REVISIONS` also encodes the head
  (`add_item_order_index`) by name, so a new revision must update it; nothing enforces this.
- **Path resolution for config:** `_configured` locates `alembic.ini` with
  `Path(__file__).parents[2] / "alembic.ini"`, i.e. the repository root. This works from a source
  checkout only. If the package is installed as a wheel, the file is not part of the package and
  `Config(...)` points at a missing file. `script_location` and `sqlalchemy.url` are already set
  programmatically, so the ini file is nearly redundant; either build `Config()` without a file
  or ship the ini inside the package. Packaging of `wishenka/wishlists/alembic/` (templates,
  `versions/`) in `pyproject.toml` was not verified.
- **URL handling by string replace.** `_sqlite_url` and `_database_path` parse the URL with
  `str.replace` and `startswith`. URL query parameters (for example `?mode=ro`) or `file:` URIs
  would be treated as part of the file path. `sqlalchemy.engine.make_url` is the safer tool.
- **`env.py` offline mode is untested** and `alembic.ini` contains an unused logging section
  (`keys =` empty handlers, no `fileConfig` call).
- **Two sources of PRAGMA behaviour.** Foreign keys and busy timeout stay in the store connection
  hook, WAL moved to the migration runner. A short comment in the store pointing to the runner
  would help future readers.
- **Raw PRAGMA interpolation.** `f"PRAGMA table_info({table})"` interpolates names. Inputs are
  internal constants (`_TABLES`, index names read from SQLite), so this is not exploitable, but
  it is a pattern that should not be copied.
- **Stray artifact at repository root: `core`.** See Follow-up Tasks.

## Missing Tests

- Adoption is tested end to end only for the base-normalized legacy shape and the two rejected
  shapes (ascending history index, malformed display-order marker). There is no test for adopting
  a legacy file already at `add_warn_on_delete_reserved`, `add_display_order` or head
  (`add_item_order_index`), although the architecture lists all four mappings.
- No test for rejection paths: an extra or missing table, a changed foreign key or cascade
  action, a legacy JSON `payload` column, a malformed warn-on-delete marker, a missing or extra
  index.
- No test for downgrade behaviour of the revisions. The policy itself is also incomplete, see
  "Deviations from Architecture"; a test is only meaningful once the policy is settled.
- No test for a non-SQLite URL (`ValueError` branch of `_database_path`) or for a database URL
  with parameters.
- No test for Alembic offline mode (`run_migrations_offline`).
- No test for a second startup on an already-migrated database (idempotent `upgrade head` as a
  no-op, with no second `adopted` log event).
- Multi-process startup is covered for fresh and legacy `base_normalized` files only; the lock
  timeout path (60 s, `TimeoutError`) has no test.
- No test that a failed adoption leaves the file byte-identical (no stamp, no
  `alembic_version` table). The rejection tests assert no stamp, but not the absence of other
  modification.
- Module timeout of 10 s on the Alembic test module is tight for slow CI runners, because each
  test runs real Alembic upgrades. This is not a missing marker, but flakiness risk; the
  observability module already uses 30 s.

## Performance Concerns

- Migration runs on every application start. For an up-to-date database this is one Alembic
  `upgrade head` no-op (script directory scan plus a version-table read) and one extra
  `sqlite3.connect` for WAL. Cost is small and measured by `duration_ms`, but there is no
  threshold or alert.
- Alembic runs through `asyncio.to_thread`, so the event loop is not blocked. During startup the
  store is unusable until it finishes; this is the intended behaviour.
- Table-recreating (batch) migrations on large SQLite files will lock the database and copy data.
  None of the current revisions need it, but the first such revision should be reviewed for lock
  duration.
- The 197 MB `core` file at the repository root is a disk and `git add -A` hazard, not a runtime
  concern.

## Deviations from Architecture

- WAL selection was moved into the migration runner (documented in the roadmap Step 4 and
  `40-code-cleanup.md`, not in `20-architecture.md`).
- `:memory:` stores use a temporary file with an owned `WishlistStore.dispose()`, and
  `web/app.py` shutdown calls `dispose()`. The architecture did not describe this.
- **Downgrade policy is not deliberate for most revisions.** `20-architecture.md` (line 73)
  requires each revision to have "a deliberate downgrade policy appropriate to the stored data".
  In `wishenka/wishlists/alembic/versions/` only two revisions have a working `downgrade()`:
  `base_normalized` (drops the baseline tables in reverse order, which destroys all wishlist
  data) and `add_item_order_index` (`DROP INDEX idx_wl_items_order`). `add_display_order` and
  `add_warn_on_delete_reserved` raise `NotImplementedError` (SQLite cannot drop a column without
  a table rebuild; only the second explains this in a comment). So `alembic downgrade` stops
  half-way at `add_display_order` and the `base_normalized` downgrade is a data-destroying
  operation with no guard or documentation. The policy (one-way vs supported, guards, message)
  is not recorded anywhere; see Follow-up item 4.
- Initialization failures are wrapped in a generic `RuntimeError` in the store (architecture says
  "raises" with an actionable error).
- The architecture says the migration environment obtains the URL "from the same application
  configuration path used by the store"; the implementation passes the URL programmatically via
  `Config.set_main_option`, which is equivalent in effect.
- Logging, which the architecture did not specify, was added in Step 6 and is validated by its
  own tests.

## Hardcoded Values

- Revision identifiers in `_REVISIONS`, the `_TABLES` set, and the `idx_wl_items_order` index
  name.
- URL prefix `sqlite+aiosqlite:///` in `_database_path` and the replacement in `_sqlite_url`.
- Marker defaults inside `_marker_signatures` (`INTEGER NOT NULL DEFAULT 1` / `DEFAULT 0`).
- `alembic.ini` location (repository root) and the `wishenka/wishlists/alembic` relative
  `script_location` in the ini.
- Migration lock sidecar suffix `.migrate.lock` and its 60 s bounded wait (`fcntl.flock`,
  POSIX only; the sidecar stays next to a real database file, is gitignored, and is removed
  with the `:memory:` temporary store).
- Temp file prefix and suffix `wishenka-` / `.sqlite`.
- Test timeouts (10 s, 30 s).

## Documentation Debt (for Step 8)

- Stale statements that describe removed behaviour (line numbers re-checked against the
  working tree):
  - `doc/dev/miniapp.md:459` says the `warn_on_delete_reserved` column is "added to `wl_lists`
    by the store migration".
  - `doc/dev/items.md:402` ("Dynamic Schema Migration") describes a runtime
    `ALTER TABLE wl_items ADD COLUMN display_order` run by `WishlistStore._init_db`. That
    runtime ALTER is gone and `_init_db` does not exist; the schema is now created by Alembic.
  - `doc/dev/items.md:411` says the store `connect` hook sets `PRAGMA journal_mode=WAL`, and the
    PRAGMA table at `doc/dev/items.md:998` lists `journal_mode` = `WAL` under `connect`. The
    `connect` hook now sets only `foreign_keys` and `busy_timeout`; WAL is set in
    `upgrade_to_head_sync` (`migrations.py:219`).
  - `doc/dev/items.md:623` says `display_order` is added by an `ALTER TABLE` migration (and the
    same note covers `warn_on_delete_reserved`).
  - `doc/dev/architecture.md:16` lists `PRAGMA journal_mode = WAL;` among connection settings,
    next to `foreign_keys` and `busy_timeout`. It is stale for the same reason.
- `doc/dev/architecture.md` is therefore both stale (the WAL line) and incomplete: it has no
  description of the Alembic workflow (how to add a revision, the adoption rule, the
  unsupported-schema error, the downgrade policy) and no note on the WAL move or the `:memory:`
  temporary file. Step 8 should cover this.

## Follow-up Tasks

There are no BLOCKER items. Every item below is NON-BLOCKER; none prevents moving to Step 8,
commit, or closing WISHENKA-111.

1. **NON-BLOCKER — pre-existing:** Chromium-dependent browser UI tests fail both at the base
   commit and now (Jira WISHENKA-124, already filed):
   - `tests/test_wishlist_management_browser.py::test_browser_copy_share_and_role_controls`
   - `tests/test_wishlist_sections_ui.py::test_mini_app_home_sections_and_badges_browser`
2. **NON-BLOCKER:** Stray core dump `core` at the repository root (untracked, not gitignored).
   Jira: [WISHENKA-126](https://pypost.atlassian.net/browse/WISHENKA-126)
   Evidence: `file core` reports an ELF aarch64 core file from
   `/home/src/.venv/bin/python3 .venv/bin/pytest`, 197,693,440 bytes, modified 2026-11-12 07:09,
   which falls within this task's Step 5 full-suite run (the roadmap Step 5 note mentions an
   extended active pytest process; the link between that process and the dump is not verified).
   It was not deleted by this step. Actions: the owner deletes it after confirming nobody needs it for debugging
   (do not commit it), add `core` and `core.*` to `.gitignore`, and open a follow-up to find why
   pytest crashed (possible native-extension or Chromium/Playwright crash, possibly related to
   WISHENKA-124). Make sure `td-99-commit` stages files by explicit path.
3. **NON-BLOCKER:** Add the missing adoption tests: legacy files at each of the four mapped
   Jira: [WISHENKA-127](https://pypost.atlassian.net/browse/WISHENKA-127)
   revisions, and rejection of extra or missing tables, changed foreign keys, changed cascade
   actions, legacy `payload` columns, malformed warn-on-delete marker and index drift; add a
   byte-identical-on-failure assertion.
4. **NON-BLOCKER:** Decide and document the downgrade policy required by `20-architecture.md`
   Jira: [WISHENKA-128](https://pypost.atlassian.net/browse/WISHENKA-128)
   (declare which revisions are one-way, make `base_normalized.downgrade()` refuse or warn
   because it drops all data, give both `NotImplementedError` revisions a clear message), then
   add tests for it. Also add tests for idempotent second startup, non-SQLite URL, offline mode,
   (concurrent multi-instance startup is covered by
   `tests/test_wishlist_migrations_concurrency.py`, see the migration lock).
5. **NON-BLOCKER:** Refactor `_adopt_known_schema` into detect/validate/stamp functions with a
   Jira: [WISHENKA-129](https://pypost.atlassian.net/browse/WISHENKA-129)
   named marker structure; derive marker signatures from the revision files or a shared manifest
   instead of restating DDL; derive the head revision from the Alembic `ScriptDirectory`.
6. **NON-BLOCKER:** Make packaging and URL parsing robust: build `Config` without depending on
   Jira: [WISHENKA-130](https://pypost.atlassian.net/browse/WISHENKA-130)
   the repository-root `alembic.ini` (or ship it in the package), verify revisions are included
   in the built wheel, and use `sqlalchemy.engine.make_url` for SQLite URL handling.
7. **NON-BLOCKER:** Raise the 10 s timeout of `tests/test_wishlist_alembic_migrations.py` to
   Jira: [WISHENKA-131](https://pypost.atlassian.net/browse/WISHENKA-131)
   30 s, or measure typical runtime on CI first.
8. **NON-BLOCKER:** Update `doc/dev/miniapp.md`, `doc/dev/items.md` and
   Jira: covered by Step 8 of WISHENKA-111 (no separate issue).
   `doc/dev/architecture.md` for the Alembic workflow and the deviations above (covered by
   Step 8 of this task; list here so it is not lost if Step 8 is narrowed). The exact stale
   lines are `miniapp.md:459`, `items.md:402`, `items.md:411`, `items.md:623`, the PRAGMA table
   at `items.md:998`, and `architecture.md:16`.
9. **NON-BLOCKER:** Add a startup migration duration alert or log-based check if migrations ever
   Jira: [WISHENKA-125](https://pypost.atlassian.net/browse/WISHENKA-125)
   become non-trivial (batch table rebuilds).

10. **NON-BLOCKER:** `WishlistStore.initialize()` does not dispose the store when it fails
   Jira: [WISHENKA-132](https://pypost.atlassian.net/browse/WISHENKA-132)
    (`store.py`, `initialize` only wraps the exception). For a `:memory:` store the owned
    temporary file and engine then leak unless the caller calls `dispose()`. The application
    lifespan is safe because `initialize()` runs inside its `try` and `finally` calls
    `dispose()` (`web/app.py`), so this affects scripts and tests that call `initialize()`
    directly. Dispose (or document that callers must) on failure.
11. **NON-BLOCKER:** Dead branch in `WishlistStore.__init__`: after the `:memory:` rewrite to a
   Jira: [WISHENKA-133](https://pypost.atlassian.net/browse/WISHENKA-133)
    temporary file, `if path != ":memory:":` is always true, so the condition is redundant.
    Make the `mkdir` unconditional.
12. **NON-BLOCKER:** Existing tests bypass `WishlistStore.dispose()` and call
   Jira: [WISHENKA-134](https://pypost.atlassian.net/browse/WISHENKA-134)
    `store.engine.dispose()` directly. `grep -rln "engine.dispose()" tests` finds seven modules
    (31 call sites). Each was checked: all construct `WishlistStore` (no other engine type), all
    use a file database under `tmp_path` (`sqlite+aiosqlite:///{db_path}`), and none uses
    `:memory:` (`grep memory` over the seven modules finds nothing). Per module:

    | Module | `engine.dispose()` lines | Database | Module-level timeout |
    | --- | --- | --- | --- |
    | `tests/test_booking_ceiling_r5.py` | 148, 217, 259 | file | `pytestmark` 120 s (line 28); some tests also set 30/60/90/120 s |
    | `tests/test_shared_inventory_multiprocess.py` | 213, 309, 321, 943 | file | `pytestmark` 60 s (line 36) |
    | `tests/test_token_cleanup_background.py` | 149, 288, 319, 378 | file | `pytestmark` 10 s (line 19) |
    | `tests/test_token_cleanup_observability.py` | 92, 175, 261, 314, 357 | file | `pytestmark` 10 s (line 21) |
    | `tests/test_wishlist_api.py` | 242, 243, 262, 263, 457, 508, 530 | file | `pytestmark` 30 s (line 17) |
    | `tests/test_wishlists_sqlite_repo_observability.py` | 65, 178, 234, 282 | file | `pytestmark` 10 s (line 26) |
    | `tests/test_wishlists_sqlite_repo.py` | 47, 94, 143, 204 | file | `pytestmark` 10 s (line 15) |

    Because every one of them uses a file database, `engine.dispose()` leaves nothing behind
    today: no temporary file is owned, so no leak. There is no `:memory:` user among them, so no
    actual leak risk was found. It would become a leak (the owned temporary file from the
    `:memory:` workaround is not removed) if any of these tests is switched to `:memory:`. Move
    them to `await store.dispose()`. Every module declares a module-level timeout, so there is no
    timeout-marker BLOCKER.

All follow-ups are ticketed: item 1 is WISHENKA-124, items 2-7 and 9-12 have Debt issues WISHENKA-125 to WISHENKA-134, and item 8 is covered by Step 8.
