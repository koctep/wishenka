# WISHENKA-235: Technical Debt Analysis

## Shortcuts Taken

No shortcut was added to hide the book control or to skip the remainder.

`project_wish_item` in `wishenka/wishlists/service.py` now calls
`recipient_view` only when `WishlistAccessPolicy.is_recipient` is true.
A missing caller falls through to `WishItemGifterViewDTO`. Personal
promise fields stay at the empty values unless `current_user` is
present, so the branch never reads `telegram_id` on a missing user.
That is the projection agreed in `20-architecture.md`.

`RepoWishlistOps.get_wishlist_by_public_token` still keeps the string
`anonymous_safe` for a missing caller who is served no giver view.
Current `project_wish_item` does not take that path: a missing id is
not a recipient, and an empty active list logs `anonymous_gifter`
because `user_role` is unset. The string is dormant. It does not restore
the silent card.

## Code Quality Issues

`projection_mode` is still inferred by scanning `view.items` for
`WishItemGifterViewDTO`, then choosing a label. The anonymous label is
now `anonymous_gifter` when that scan says a giver view was served.
The mode is not taken from `WishlistAccessPolicy`. The same inference
already existed for `gifter` and `recipient_safe`.

The giver DTO is still built by copying each wish field in
`project_wish_item`. The anonymous and identified paths share that one
constructor. No third DTO was added.

## Missing Tests

Timeout markers on the modules this task edited are present. This is
not a timeout blocker.

- `tests/test_wish_card_giver_controls.py` sets
  `pytestmark = pytest.mark.timeout(30)`. That mark covers
  `test_anonymous_share_shows_availability_without_a_book_control` and
  `test_anonymous_share_shows_booked_without_a_book_control`.
- `tests/test_wishenka_63_repro.py` sets
  `pytestmark = pytest.mark.timeout(30)`. That mark covers the rewritten
  anonymous projection checks and
  `test_public_projection_observability_logs_without_leaking_tokens`,
  which expects `anonymous_gifter`.
- `wishenka/wishlists/service.py` and `wishenka/wishlists/repo_ops.py`
  are product modules. They do not collect tests.

No remaining test asserts `projection_mode` `anonymous_safe`. The only
mode assertion is the `anonymous_gifter` sequence in
`tests/test_wishenka_63_repro.py::test_public_projection_observability_logs_without_leaking_tokens`.

These public-list checks still omit `available_quantity`. They call
`GET /api/public/wishlists/{token}` (no `/view`). `public_wishlist`
builds an allowlist and does not dump the giver DTO. They still match
the accepted list answer and were left as written:

- `tests/test_wishlist_api.py::test_anonymous_public_view_hides_existing_reservation`
- `tests/test_wishlist_api.py::test_public_api_shows_persisted_wish_without_reservation_details`
- `tests/test_wishlist_management_ui.py::test_anonymous_public_display_ignores_stale_session_and_hides_reservation`

One test still expects the silent recipient payload on the projection
that this task changed. It is listed under Follow-up Tasks. The new
anonymous giver contract is already asserted in
`tests/test_wishenka_63_repro.py` (`/view` and
`get_wishlist_by_public_token(..., None)`). The gap is the leftover
Mini App check, not an untested share page.

## Performance Concerns

An anonymous item now sums occupying reservations with the same formula
an identified giver already used. The public resolve still loads the
wishlist once and projects in memory. No extra query or new hot path
was added.

## Follow-up Tasks

Must be fixed as follow-up. Caused by this change. The setup error is pre-existing.

- `tests/test_bot_entry_repro.py::test_anonymous_public_api_does_not_disclose_reservations`
  Jira: [WISHENKA-356](https://pypost.atlassian.net/browse/WISHENKA-356)

  The test opens `GET /api/public/wishlists/{token}/view` with no
  session. It asserts the JSON is unchanged after a friend reserves the
  wish, and that the item has neither `available_quantity` nor
  `is_fully_reserved`. `public_wishlist_view` dumps each projected item
  with `model_dump`. A missing caller is now `WishItemGifterViewDTO`,
  so those aggregate fields are present and change when a unit is
  taken. The docstring still calls that caller an unidentified
  recipient. The module mark is
  `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`.

  A fresh run of this node did not reach the assertion.
  `from wishenka.web.app import create_app` raises `ImportError` on
  `WishlistStore` while `wishenka.wishlists.store` is still loading
  (`store` → `repository` → `service` → `wishenka.auth` →
  `auth.dependencies` → `store`). The same import fails on base commit
  `f27bcac` with this task's diff absent.
  `NON-BLOCKER — pre-existing`.
  Jira: [WISHENKA-357](https://pypost.atlassian.net/browse/WISHENKA-357).
  The assertion contradiction above does not depend on that
  import, and it is tracked as WISHENKA-356.

Developer docs still describe the old fold. Step 8 should correct them.
`in-docs/spec.md` already says an anonymous visitor sees the free
remainder, so no end-user doc was edited here.

- `doc/dev/wishlists.md`: `project_wish_item(item, None)` is still
  described as `recipient_view`, and `projection_mode` for an
  unauthenticated `/view` is still `anonymous_safe` (public route list,
  sharing endpoint, and `get_wishlist_by_public_token`).
- `doc/dev/bot-scenarios.md`: an anonymous Mini App visitor is still
  described as receiving recipient-safe item data from
  `GET /api/public/wishlists/{token}/view`.
