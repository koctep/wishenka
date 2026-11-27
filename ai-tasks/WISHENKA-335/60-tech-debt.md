# WISHENKA-335: Technical Debt Analysis

No new follow-up. The shared apply procedure lives in
`wishenka.db.migrations`. Wishlist startup and person startup both call
`upgrade_to_head` there. The product history, older-wishlist adoption, and
the person-key revision stay in `wishenka.wishlists`. The compatibility
wrappers on `wishenka.wishlists.migrations` stay because the architecture
required them for existing imports.

The new repro has an explicit timeout mark. In
`tests/test_wishenka_335_shared_migration_runner.py`,
`pytestmark = pytest.mark.timeout(10)` covers
`test_wishlist_and_person_startup_call_shared_upgrade_to_head`. There is
no `do-testing` blocker.

## Shortcuts Taken

- **Compatibility wrappers stay** (accepted). `wishenka.wishlists.migrations`
  still exposes `_configured`, `head_revision`, `upgrade_to_head_sync`,
  `upgrade_to_head`, and `migration_lock_path`. Each wrapper delegates to
  `wishenka.db.migrations` with `PRODUCT_HISTORY`. The stores call the shared
  `upgrade_to_head`. The wrappers keep the WISHENKA-334 test and the other
  current imports working. This task does not edit that test.
- **The history stays with wishlists** (accepted). `PRODUCT_HISTORY`,
  `_adopt_known_schema`, the Alembic tree, and
  `unify_user_keys_and_cascades.py` stay in `wishenka.wishlists`. People and
  wishlists still share that one history.
- **The product binding loads the history lazily** (accepted).
  `upgrade_to_head_sync` in `wishenka.db.migrations` calls
  `_product_history()`, which imports `PRODUCT_HISTORY` inside the function.
  Person startup names `wishenka.db.migrations` and does not name
  `wishenka.wishlists`.
- **Adoption still parses the URL locally** (accepted). `_adopt_known_schema`
  keeps `_database_path` in `wishenka.wishlists.migrations`. The runner parses
  the URL again for the lock and for WAL. The adopt body stayed with the
  history, as the architecture required.
- **The wait stays a runner constant** (accepted). The file lock still waits
  60 seconds and polls every 0.05 seconds. Those values are
  `_LOCK_TIMEOUT_SECONDS` and `_LOCK_POLL_SECONDS` in
  `wishenka/db/migrations.py`. The history supplies the timeout sentence.

## Code Quality Issues

None that need a follow-up.

`configured` still loads `alembic.ini` from `Path(__file__).parents[2]`.
`wishenka/db/migrations.py` is two directories under the repository root, so
that relative path still finds the file. The architecture kept this lookup.

`WishlistStore` re-exports `upgrade_to_head` and lists it in `__all__`. The
repro asserts that this name and `UserStore`'s name are the shared function.

The repro imports `wishenka.auth.models` before the two stores. Loading the
auth package completes the wishlist-store import that `wishenka.auth`
already performs. That order belongs to the existing package layout.

## Missing Tests

No blocker. The timeout mark above is module-wide and the file has one test.

The repro asserts that both stores' `upgrade_to_head` is
`wishenka.db.migrations.upgrade_to_head`. It does not open a database.
Apply behavior stays covered by the existing migration checks, which still
call the wishlist wrappers. This task adds no second history and no second
script directory, so there is no second-history case to add here.

## Performance Concerns

None added. A file database still takes one sidecar lock for the whole
apply. A second startup still locks, sees `alembic_version`, skips another
adoption, and leaves `upgrade head` with nothing to change. An in-memory
URL still skips the lock. The 60 second wait is unchanged.

## Follow-up Tasks

No new follow-up. The move matches the architecture. The wrappers are the
compatibility surface that architecture required, so they are not a new
task.

Already filed, and left in place:

- The person-key downgrade check stays on
  [WISHENKA-334](https://pypost.atlassian.net/browse/WISHENKA-334).
  This task does not edit that test or
  `unify_user_keys_and_cascades.py`.
- User-scoped hydration stays on
  [WISHENKA-340](https://pypost.atlassian.net/browse/WISHENKA-340).
- `UserStore._read` stays on
  [WISHENKA-342](https://pypost.atlassian.net/browse/WISHENKA-342).
- The shared-method set stays on
  [WISHENKA-350](https://pypost.atlassian.net/browse/WISHENKA-350).
- The missing-user history skip stays on
  [WISHENKA-351](https://pypost.atlassian.net/browse/WISHENKA-351).
- Concurrent preview cookies stay on
  [WISHENKA-352](https://pypost.atlassian.net/browse/WISHENKA-352).
- History share-grant batching stays on
  [WISHENKA-353](https://pypost.atlassian.net/browse/WISHENKA-353).

An external `AsyncEngine` passed into `UserStore` still migrates
`self.database_url`. That gap is the one recorded on WISHENKA-188, and this
task leaves it there.

Step 8 owns `doc/dev/migrations.md` and the migration paragraph in
`doc/dev/architecture.md`. User-facing docs were left unchanged. Startup
still has no new screen and no new person-facing sentence.

### Pre-existing test failures

This step did not re-run the suite and observed no new failure. Nothing
here is filed as `NON-BLOCKER — pre-existing`.
