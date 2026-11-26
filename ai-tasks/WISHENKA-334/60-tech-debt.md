# WISHENKA-334: Technical Debt Analysis

No new follow-up. The shipped change is the downgrade test
`test_downgrade_from_unify_user_keys_restores_earlier_identity` in
`tests/test_wishenka_188_user_key_unification_repro.py`.
`wishenka/wishlists/alembic/versions/unify_user_keys_and_cascades.py` is
unchanged. The module already declares `pytestmark = pytest.mark.timeout(30)`.
The new test does not override that mark.

## Shortcuts Taken

- **The check stops at this revision** (accepted). The test upgrades to
  `unify_user_keys_and_cascades` and downgrades to
  `add_receipt_delivery_fence`. It does not start from head. The chain above
  this revision is `add_share_access_and_purge_favorites`, then
  `purge_legacy_non_member_view_history`, then
  `add_view_history_recorded_seq`.
  `purge_legacy_non_member_view_history.downgrade` already raises
  `NotImplementedError`. This task did not edit that revision, so the refusal
  is not worse and is not a new follow-up.
- **The seed and the Alembic config stay local** (accepted). The test repeats
  the forward test's person, remembered links, and support ticket, then adds
  one wishlist and one invite token. It calls the private `_configured`
  helper. A shared migration runner is already
  [WISHENKA-335](https://pypost.atlassian.net/browse/WISHENKA-335). This task
  does not re-file it.

## Code Quality Issues

None from this change. `downgrade` in `unify_user_keys_and_cascades.py` was
not edited. The new test adds no import. It uses `command`, `_configured`,
`sql_exec`, `sql_rows`, `sqlite3`, and `Path`, which the file already
imported. Hardcoded `42` and `999001` match the forward test so the two
identities stay different.

## Missing Tests

The missing downgrade check recorded on WISHENKA-188 is the test that
shipped. It asserts the earlier identity on the four remembered links, the
earlier support-ticket owner and index, the token-only invite, and that
deleting the person or the wishlist does not remove those rows.

Reminders and ordinary wishlist access tokens stay out of the assertions.
The requirements leave them there. The forward test in the same file is
unchanged.

Timeout check: `pytestmark = pytest.mark.timeout(30)` at module scope covers
`test_downgrade_from_unify_user_keys_restores_earlier_identity`. There is no
`do-testing` blocker.

## Performance Concerns

None. The test uses one temporary SQLite file and the existing revision.
The table-rebuild path in `downgrade` is unchanged.

## Follow-up Tasks

No new follow-up.

Already filed, and not re-filed:

- The shared Alembic runner stays on
  [WISHENKA-335](https://pypost.atlassian.net/browse/WISHENKA-335). This test
  still calls `_configured` the way the forward test does.
- The one-way refusal in `purge_legacy_non_member_view_history` stays as it
  was. This task did not change that `downgrade` and did not file it again.

User documentation under `doc/` was left unchanged. The change is a test of
an existing migration, with no new screen or support flow.

### Pre-existing test failures

This step did not re-run the suite and observed no new failure. Step 5
reported the repro file as 6 passed. Nothing here is filed as
`NON-BLOCKER — pre-existing`.
