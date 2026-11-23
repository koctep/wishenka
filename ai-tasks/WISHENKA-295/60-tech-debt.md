# WISHENKA-295: Technical Debt Analysis

No blockers were found. The delete route is owner-only, uniform 404 for non-owner and unknown id
(pinned by `tests/test_wishlist_delete_observability.py`), idempotent without sliding the
retention window, and the Mini App flow has an explicit confirmation. Reviewed: the diff of
`wishenka/web/routes/wishlists.py`, `routes/miniapp.py`, `static/miniapp.js`, `static/miniapp.css`,
`i18n/catalog.py`, the four `tests/test_wishlist_delete_*.py` modules, `40-code-cleanup.md`,
`50-observability.md` and risks R-1..R-9 of `20-architecture.md`. All delete test modules carry
`pytest.mark.timeout` (30 / 20 / 45 / 30). Every item below is NON-BLOCKER.

Interaction with the known access-model leak (WISHENKA-302 favorites, WISHENKA-303 history):
none introduced and not a blocker. `list_favorites` (`wishenka/wishlists/service.py:3216`) and
`record_view` / `get_history` skip `DELETED` lists, so a deleted list disappears from the
favorites and history of non-members. Residual, pre-existing: leaked favorite and history rows
are not purged by deletion, so they reappear if the owner restores the list. This belongs to
WISHENKA-302 / 303 (purge or migrate leaked rows); add it to their scope, no new ticket.

## Shortcuts Taken

- **S-1 Route reads a private service member and the settings via `getattr`** (Medium).
  `wishenka/web/routes/wishlists.py:503` uses `service._wishlists.get(...)` (same pattern at
  `:316`, `:416`, `:218`, `:1004`), and `:499` / `:231` / `:565` plus `miniapp.py:24` each do
  `getattr(getattr(request.app.state, "settings", None), "wishlist_retention_days", 30)`. The
  default 30 is hard-coded in four route sites and again in `service.py:1135,1177`, while the
  real default lives in `wishenka/config.py:93`. Confirmed (R-3 accepted it knowingly). Fix: a
  public `WishlistService.get_wishlist_or_none(id)` (or a classify helper) and one
  `retention_days(request)` dependency reading `Settings` typed.
- **S-2 Retention arithmetic duplicated from restore** (Medium). `wishlists.py:528-538`
  re-implements the tz-normalisation and `updated_at <= now - retention` check that
  `WishlistService.restore_deleted_wishlist` (`service.py:1173-1215`) and
  `list_deleted_wishlists` (`:1140`) already contain. A change to the window rule (for example
  a dedicated `deleted_at` column instead of `updated_at`) must now be made in three places,
  and the delete path would silently diverge. Confirmed. Fix: a service method
  `is_retention_expired(wl, retention_days)` used by all three, or move the idempotent branch
  into the service (`delete_wishlist` returning an outcome) so the route no longer needs
  `_wishlists` or the arithmetic (closes S-1 for this route too).
- **S-3 `data-retention-days` shell coupling** (Low). `miniapp.py:24-49` renders the value into
  the HTML shell and `miniapp.js:581` reads it from `root.dataset`. The response of
  `DELETE` also carries `retention_days`, but the confirmation text needs the number before
  the call, hence the shell. Consequence: a stale cached shell after a settings change shows a
  wrong number (R-2 only guards missing or invalid values). Not wrong today because the value
  changes only with a deploy. Fix, if it ever becomes a runtime setting: expose it in an existing
  bootstrap API response (profile or list payload) instead of the shell.
- **S-5 Delete cancels purchased reservations silently** (Low, product decision).
  `service.delete_wishlist` (`wishenka/wishlists/service.py:1086-1132`) cancels ACTIVE and
  PURCHASED reservations and records no shared event or notice, unlike archive and restore
  (`_record_shared_event`). A giver who had already bought is cancelled silently, and restore
  does not bring the reservation back. Consistent with requirements Q5 (no new notification),
  so NON-BLOCKER; recorded as a product-decision residual. Fix: decide whether givers need a
  notice or a shared event on delete, and whether restore should reinstate reservations; fold
  into follow-up 1 or 3 if accepted.
- **S-4 HTML/htmx owner-side deletion absent** (Low, by design). The web (non-Mini App) list
  screen has no owner delete (decision in `20-architecture.md:188,569-573`). Not a defect;
  recorded so product decides whether the web UI needs parity. Fix: a product decision, then
  a route plus partial; reuse the same service outcome as in S-2.

## Code Quality Issues

- **C-1 410 failure message is inserted into a detached panel** (Medium, accessibility).
  `miniapp.js:640-657`: on 410 `confirmDelete()` awaits `showHome()`, which calls
  `root.replaceChildren(...)`, so `panel`, `failure` and `yesBtn` are detached; then
  `failure.textContent` / `panel.insertBefore(failure, actions)` / `yesBtn.focus()` act on
  nodes that are not in the document. The visible message works only through `status(...)`
  (`:651`); the `role="alert"` paragraph is never announced and keyboard focus is lost to
  `body`. Confirmed by reading the control flow; no test asserts focus after 410. Fix: in the
  expired branch skip the detached-panel code and move focus to the home `h1`
  (`tabindex=-1`, as the success path does), plus a browser test for focus after 410.
- **C-2 Identical "Cancel" label twice on one screen** (Medium, accessibility).
  `miniapp.wishlist_settings.cancel` (`catalog.py:353`, button at `miniapp.js:691`) and
  `miniapp.wishlist_delete.cancel` (`catalog.py:414`, button at `miniapp.js:590`) both render
  "Cancel" / "Отмена" on the owner list screen. Screen-reader users in a button list, and
  speech-control users ("click Cancel"), cannot tell which one discards the form and which
  closes the delete panel. Confirmed; Step 4 already worked around it in tests (the "ambiguous
  Cancel label" fix). Fix: give the delete cancel an accessible name, for example
  `aria-label` "Cancel deleting «title»", or change the visible text to "Keep wishlist" /
  "Оставить список"; assert it in the accessibility-tree test
  (`tests/test_wishlist_delete_browser.py:290`).
- **C-3 410 log text says "restore" for a delete** (Low). `wishlists.py:68` logs
  "Wishlist restore rejected because retention window expired: %s" for every operation that
  goes through the shared `execute()`, including `delete_wishlist`. The `operation` field
  disambiguates, the message does not. Confirmed. Fix: "Wishlist operation rejected because
  retention window expired" (check `tests/` for assertions on the old text first).
- **C-4 Non-owner attempts are logged server-side only** (Low, accepted). The
  `wishlist_delete_denied` WARNING (`wishlists.py:523`) is the only trace; the client gets a
  uniform 404 on purpose (no list-existence leak). No rate limiting or alert exists; the
  suggested alert on bursts per `user_id` (`50-observability.md`) is not configured anywhere in
  the repository. Fix: add the alert rule when log aggregation rules are introduced; no code.
- **C-5 Dev-doc mismatches in `doc/dev/wishlists.md`** (Low; to be fixed in Step 8, listed
  here so they are tracked if Step 8 is skipped). (a) `delete_wishlist` is documented as
  returning `Wishlist` (`:749-753`) but the service returns `None` (`service.py:1086-1090`);
  (b) "invalidates tokens" (`:757`) is not what `delete_wishlist` does (it sets the status and
  cancels reservations; token rotation happens on restore); (c) "There is no HTTP delete route"
  (`:126`) is now false; (d) the event table (~`:1470-1514`, `wishlist_restored_from_deleted` at `:1514`) lacks `wishlist_delete_denied`,
  `wishlist_delete_not_found`, `wishlist_deleted_by_owner`. Fix: Step 8, no new ticket if done
  there.

## Missing Tests

- **T-1 Tests import private helpers and patch the harness by string** (Low).
  `tests/test_wishlist_delete_ui.py:21,123-130` imports `_NODE_HARNESS` from
  `tests/test_miniapp_i18n_repro.py` and patches it with `str.replace` anchors
  (`_PATCHES`, `:29`); `tests/test_wishlist_delete_browser.py:290` calls `page._send(...)`
  (`# noqa: SLF001`); `tests/test_wishlist_delete_api.py:209` reads `service._reservations`.
  Any edit of the source harness text breaks the UI module through the anchor assertion.
  Confirmed. Fix: expose a public harness builder with a scenario hook for `retentionDays`
  and focus tracking, a public `page.accessibility_tree()` helper in `tests/browser_screens.py`,
  and a public service query for reservation status (or assert through the API).
- **T-2 No test for focus and announcement after 410** (Medium, goes with C-1). The 410
  scenario asserts the status text and the list reload but not focus or the alert.
- **T-3 Chromium-only browser run** (Low). Same limitation as WISHENKA-307 (no WebKit/Gecko);
  the panel uses plain DOM, no known risk. Covered by WISHENKA-313 scope (cross-browser check).

## Performance Concerns

None. One O(1) dict lookup and one status write per delete; no new queries or polling. The
full suite takes about 64 minutes (`make test-serial`); `make test` (xdist) is the working
path, and the budget is tracked by `make test-bench`. That is a repository-level cost, not
introduced here (the four delete modules add 119 tests, about 1 minute), so no new ticket;
the existing suite-speed discussion stays where it is.

## Follow-up Tasks

1. **Move delete classification and retention arithmetic behind the service: add a public
   lookup and an `is_retention_expired` / outcome-returning `delete_wishlist`, replace the
   four `getattr(... "wishlist_retention_days", 30)` route sites and the hard-coded 30 with one
   typed accessor; drop `service._wishlists` from `wishlists.py:503` (and the sibling sites).**
   NON-BLOCKER (works and is tested; maintainability and drift risk), priority Medium.
   Covers S-1, S-2, S-3. Jira: [WISHENKA-316](https://pypost.atlassian.net/browse/WISHENKA-316)
2. **Fix focus and a11y of the delete panel: expired (410) path must not touch the detached
   panel and must move focus to the home heading; give the delete "Cancel" a distinct
   accessible name; add browser tests for both.** NON-BLOCKER (the error is visible in the
   status line, no data risk), priority Medium. Covers C-1, C-2, T-2.
   Jira: [WISHENKA-317](https://pypost.atlassian.net/browse/WISHENKA-317)
3. **Neutral wording for the shared retention-expired log (`wishlists.py:68`) and the doc
   mismatches of C-5 if Step 8 does not fix them; configure the alert on bursts of
   `wishlist_delete_denied` when alert rules exist.** NON-BLOCKER (text only), priority Low.
   Covers C-3, C-4, C-5. Jira: [WISHENKA-318](https://pypost.atlassian.net/browse/WISHENKA-318)
4. **Harden the delete tests: public harness hook instead of `_NODE_HARNESS` string patching,
   public accessibility-tree helper instead of `page._send`, no `service._reservations`.**
   NON-BLOCKER (test maintainability), priority Low. Covers T-1.
   Jira: [WISHENKA-319](https://pypost.atlassian.net/browse/WISHENKA-319)
5. **Add the leaked favorite and history rows of deleted lists to the scope of the access-model
   tickets** (no new ticket): WISHENKA-302 and WISHENKA-303 (purge on delete or on restore).
   NON-BLOCKER, pre-existing, priority High (inherited). Jira:
   [WISHENKA-302](https://pypost.atlassian.net/browse/WISHENKA-302),
   [WISHENKA-303](https://pypost.atlassian.net/browse/WISHENKA-303).

Considered and dropped: HTML/htmx parity (S-4, product decision, no ticket); T-3 (covered by
WISHENKA-313); the suite duration (repository-level, not caused by this task).

### Pre-existing test failures

Verified on a clean `git archive HEAD` copy of the repository (the working tree changes of this
task not applied): `tests/test_receipt_modal_browser.py` fails exactly two tests, the same two
as with the task changes (2 failed, 7 passed in both runs). Neither is unticketed, so no new
item is recorded:

- `tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral` — NON-BLOCKER —
  pre-existing. Jira: [WISHENKA-265](https://pypost.atlassian.net/browse/WISHENKA-265).
- `tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads`
  — NON-BLOCKER — pre-existing. Jira: [WISHENKA-220](https://pypost.atlassian.net/browse/WISHENKA-220).

The rest of the base-commit failures are listed in `ai-tasks/WISHENKA-292/60-tech-debt.md`
(section "Pre-existing test failures"; WISHENKA-232, 235, 245, 264, 267, 298 and others). They
are not touched by this task.
