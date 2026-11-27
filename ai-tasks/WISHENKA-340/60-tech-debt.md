# WISHENKA-340: Technical Debt Analysis

No new follow-up. Favorites, recently deleted lists, the bot list offer,
and recording a visit load list headers. Membership is attached only where
the role or the permission needs this person's row. Wishes and reservations
stay unread on those openings. History listing and clearing were already
scoped and were not edited. The cabinet list still opens each list in full.
That read is the same per-id `get_wishlist` loop it had before this change,
so this change did not make it worse.

The repro timeout is present. In
`tests/test_wishenka_340_personal_hydration_repro.py`,
`pytestmark = pytest.mark.timeout(30)` covers
`test_personal_openings_load_headers_without_full_lists`. There is no
`do-testing` blocker.

Reviewed: `RepoWishlistOps.list_favorites`, `list_deleted_wishlists`, and
`record_view` (`wishenka/wishlists/repo_ops.py`),
`list_favorite_wishlist_ids`, `list_favorite_wishlists`,
`list_deleted_owner_moments`, `list_deleted_by_owner`,
`list_accessible_wishlist_ids`, `list_accessible_wishlists`, and
`get_wishlist_header` (`wishenka/wishlists/repository.py`), `_allowed` and
the save command (`wishenka/bot/capture.py`), `GET /api/favorites`,
`GET /api/wishlists/deleted`, `POST /api/history/{wishlist_id}`, and
`GET /api/wishlists` (`wishenka/web/routes/wishlists.py`),
`tests/test_wishenka_340_personal_hydration_repro.py`,
`20-architecture.md`, `40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

- **Favorite assembly is written twice** (accepted).
  `RepoWishlistOps.list_favorites` walks the ordered ids, headers, and this
  person's memberships. `WishlistRepository.list_favorite_wishlists` walks
  the same three reads. The screen calls the operations method. Nothing
  else calls the repository method. Both return headers with `items` empty.
  The architecture allowed the repository method to keep that assembly.
- **`list_deleted_by_owner` still loads every deleted header** (accepted).
  It reads moments, including lists past recovery, then loads those
  headers. It does not read wishes or reservations. The recovery screen
  does not call it. `list_deleted_wishlists` drops expired moments first
  and loads headers only for the lists still inside the window.
  `updated_at` on `wl_lists` is `NOT NULL`, so the moment skip for a
  missing timestamp does not drop a stored row.
- **These four openings stay on the write transaction** (accepted).
  `list_favorites`, `list_deleted_wishlists`, and `record_view` stay in
  `_SHARED_REPOSITORY_METHODS`. The bot offer runs inside the capture
  transaction that already wraps `_allowed`. Moving the reads onto
  `run_repository_read` would reopen the one-list save lock.
- **Recording a visit still checks the share grant for one list**
  (accepted). After the header and this person's membership,
  `record_view` calls `has_valid_share_access`, then `can_view_history`,
  then `user_exists`. That is one indexed grant read, including when the
  person is the owner. The history-page loop of grant reads is a different
  path and was not changed.
- **The cabinet list stays a full open** (out of scope).
  `list_accessible_wishlists` now takes ids from
  `list_accessible_wishlist_ids` and still calls `get_wishlist` once per
  id. `GET /api/wishlists` still uses that method and still returns each
  list's wishes. The id select, the order, and the per-id aggregate are
  the ones this route already used.

## Code Quality Issues

None that need a follow-up.

The membership attachment in `list_favorites`, `_allowed`, and
`record_view` is the same append `get_history` already uses. History
listing was left on its own copy. Recently deleted lists do not load
memberships. `can_restore_deleted` decides ownership from `owner_id`.

`list_favorite_ids` stays the unordered set the cabinet and the history
rows use for the favorite mark. Its filter matches
`list_favorite_wishlist_ids`. This task did not merge those two
statements.

Saving a captured wish still calls `RepoWishlistOps.add_wish_item`, which
opens that one chosen list in full. The offer no longer does.

## Missing Tests

No blocker. The timeout mark above is module-wide and the file has one
test.

The repro locks the visible lists and zero `wl_items` and
`wl_reservations` reads for favorites, recently deleted lists, the bot
offer, a stored visit, a deleted-list refusal, a hidden-list refusal, and
the missing-person refusal. Recently deleted lists and the deleted-list
refusal also lock zero `wl_members` reads. Favorites, the offer, and a
visit the person may record still read this person's membership, so those
cases do not assert a zero member count. An empty id list returns before
either batch. History listing and clearing stay outside the listener.

The repro does not count statements on `GET /api/wishlists`. That route
still uses `list_accessible_wishlists`. No follow-up.

## Performance Concerns

None added on the four openings. Each one reads the person's own ids,
then header rows, and membership rows only where the role or the
permission needs them. Expired deleted lists are not header-loaded on the
screen path. The cabinet path still pays one full aggregate per accessible
list, as it did before the id select was shared with the bot offer.

Header and membership batches still chunk at 500 ids. These openings do
not raise that size.

## Follow-up Tasks

No new follow-up. The four openings match the architecture. The cabinet
list staying full is the boundary this task shipped, and the per-id
`get_wishlist` loop is unchanged.

Already filed, and left in place:

- History listing and clearing stay on
  [WISHENKA-325](https://pypost.atlassian.net/browse/WISHENKA-325).
  `get_history` and `clear_history` were not edited.
- The one-list save lock stays on
  [WISHENKA-338](https://pypost.atlassian.net/browse/WISHENKA-338).
  These openings stay on the write transaction.
- `UserStore._read` stays on
  [WISHENKA-342](https://pypost.atlassian.net/browse/WISHENKA-342).
  This task did not touch that helper.
- The missing-person refusal stays on
  [WISHENKA-351](https://pypost.atlassian.net/browse/WISHENKA-351).
  `user_exists` and `view_history_user_missing` stay after the permission
  check.
- History share-grant batching stays on
  [WISHENKA-353](https://pypost.atlassian.net/browse/WISHENKA-353).
  The per-row grant loop in `get_history` was not part of this change.
  Recording one visit still reads that one grant.

Developer docs for these header reads are Step 8 of WISHENKA-340. No
separate key. User documentation under `doc/` was left unchanged. These
openings did not add a screen or a person-facing sentence.

### Pre-existing test failures

This step did not re-run the suite and observed no new failure. Nothing
here is filed as `NON-BLOCKER — pre-existing`.
