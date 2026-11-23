# WISHENKA-295: Developer Documentation

## Changed Files

- `doc/dev/wishlists.md`
  - Route list: `DELETE /api/wishlists/{id}` added; the sentence "There is no HTTP delete route"
    replaced by a pointer to it.
  - Permission matrix row names the route.
  - `delete_wishlist` section corrected (returns `None`, no token invalidation, `ARCHIVED`
    raises, reservations `ACTIVE` and `PURCHASED` are cancelled and not restored, silent-cancel
    product decision, 60-tech-debt S-5) and a new subsection "Owner delete route" with the
    classify-first table (404 unknown, 404 non-owner, 200 active, 200 idempotent in the window,
    410 after the window, 409 archived), the constant body and the `retention_days` source.
  - Audit event table: `wishlist_delete_not_found`, `wishlist_delete_denied`,
    `wishlist_deleted_by_owner` with level and fields.
- `doc/dev/miniapp.md`
  - New subsection "Wishlist Delete Zone (WISHENKA-295)": visibility rule, `data-retention-days`,
    markup and classes, panel with `history-confirm*` classes, focus, pending, success, failure,
    410, CSS hooks, text secrecy rules.
  - HTTP endpoints table row; troubleshooting item 17.
- `doc/dev/i18n.md`: `data-retention-days` on the shell; section "Wishlist Delete Texts" with the
  12 `miniapp.wishlist_delete.*` keys, placeholders and the catalog test constraints (only
  `consequences` and `restore_promise` may mention reservations, in fixed clauses).
- `doc/dev/testing.md`: section for the four modules (api 31, ui 49, browser 15, observability 8 =
  103 tests; timeouts 30 / 20 / 45 / 30; `browser` marker), `PYTEST_ARGS` scoping note,
  pointers to known failures and follow-ups;
  pointer under "Известные ограничения".
- `doc/dev/architecture.md`: one clause in the `miniapp.md` index entry.

## Reconciled Stale Statements

- `wishlists.md`: `delete_wishlist` returned `Wishlist` -> now `None` (`service.py:1086-1090`).
- `wishlists.md`: "invalidates tokens" removed; tokens rotate only on restore.
- `wishlists.md`: "There is no HTTP delete route in this API" replaced.
- `wishlists.md`: "Cancels all active reservations" -> `ACTIVE` and `PURCHASED`
  (`service.py:1086-1132`); restore does not reinstate them.
- Event table lacked the three delete events (60-tech-debt C-5 a-d are all closed here).

## Deviations from `20-architecture.md` Recorded in the Docs

- A repeat delete after the retention window is `410 retention_expired`, consistent with the
  architecture table; the docs state it as the final route behavior (`wishlists.py:537`).
- The confirmation panel carries the history classes
  (`history-confirm wishlist-delete-confirm`, `history-confirm-cancel`, `history-confirm-yes
  btn-danger`); there is no separate `.wishlist-delete-confirm` CSS rule (removed in Step 5).
- On `410` the client refreshes the home screen first and then writes the failure alert and
  focuses the confirm button on detached nodes, so the alert is not announced and focus is lost
  (known defect, WISHENKA-317); the docs describe the code, not the designed focus.
- Extra event `wishlist_delete_denied` beyond the D-7 table (Step 6).
- The shared 410 log text still says "restore" (`wishlists.py:68`, WISHENKA-318).
- The route reads `service._wishlists` and duplicates the retention arithmetic (WISHENKA-316).
- Per-module test counts follow the roadmap (31 / 49 / 15 / 8).

## Follow-ups Linked

- [WISHENKA-316](https://pypost.atlassian.net/browse/WISHENKA-316): service-level classify and
  typed retention accessor (S-1, S-2, S-3).
- [WISHENKA-317](https://pypost.atlassian.net/browse/WISHENKA-317): focus after 410, distinct
  Cancel name (C-1, C-2, T-2).
- [WISHENKA-318](https://pypost.atlassian.net/browse/WISHENKA-318): neutral 410 log text, alert
  on bursts of `wishlist_delete_denied` (C-3, C-4).
- [WISHENKA-319](https://pypost.atlassian.net/browse/WISHENKA-319): harden test helpers (T-1).
- WISHENKA-302 and WISHENKA-303: leaked favorite and history rows of deleted lists.
