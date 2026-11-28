# WISHENKA-298: Technical Debt Analysis

No new technical debt. This task did not change product code. The
anonymous share already shows the free remainder, and a missing caller
is already logged with `is_recipient` false and `projection_mode`
`anonymous_gifter`. There is no new follow-up.

Reviewed: `project_wish_item` and `WishlistAccessPolicy.is_recipient_id`,
`view_public_share` in `wishenka/web/routes/sharing.py`, the two
standing checks, `10-requirements.md`, `20-architecture.md`,
`30-failing-repro.md`, `40-code-cleanup.md`, and
`50-observability.md`.

## Shortcuts Taken

None. The architecture already names this projection. No second DTO,
client gate, or rewrite of the two checks was added.

## Code Quality Issues

None. `is_recipient_id` returns false when `user_id` is `None` before
it compares the owner. `view_public_share` sets `is_recipient` only
when `current_user` exists, and the share-view log does not store the
secret token. This task added no hardcoded timeout, status, or secret.

## Missing Tests

No `do-testing` blocker. No new test was added.
`tests/test_surprise_role_context.py` declares
`pytestmark = pytest.mark.timeout(30)`, which covers
`test_share_link_visit_creates_no_account`.
`tests/test_wishlists_htmx_observability.py` declares
`pytestmark = pytest.mark.timeout(10)`, which covers
`test_wishlist_shared_view_observability`. Neither function has a
timeout override.

Step 4 re-ran both nodes: 2 passed, 1 warning in 0.85s (exit 0). The
warning is `StarletteDeprecationWarning` from `fastapi/testclient.py`.

## Performance Concerns

None. The public resolve still loads the list once and projects in
memory. No extra query or new hot path was added.

## Follow-up Tasks

None. There is no new follow-up.

WISHENKA-356, WISHENKA-357, and WISHENKA-311 are existing tickets. They
are not new follow-ups, and this task did not open them.

User documentation under `doc/` was left unchanged. The page a guest
sees did not change. Developer docs still belong to Step 8.
