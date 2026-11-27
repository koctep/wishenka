# WISHENKA-264: Archive refusals show the list notice and close the dialog

## Goals

A wishlist author who opens archive confirmation, or who confirms archive,
must see the refusal the wish dialogs already show when the list is
archived, the list is unknown, the caller is not a member, or the wish is
unknown. The refusal is one notice on the list, and the dialog closes. An
outsider must not be able to tell a missing list from a list they do not
belong to.

Both archive actions already answer with that HTML fragment from
`_modal_domain_error_response`. Status 409 carries
`web.item.archived_wishlist_error`. Status 404 carries
`web.item.resource_not_found`. In the Russian UI a missing wish writes
«Желание или вишлист больше недоступны.» into `#list-notice`
and closes the dialog. `app.js` swaps that fragment and clears `isError`, so
`htmx:responseError` does not fire and a generic failure does not replace
the notice.

The eight archive checks still call `resp.json()` and expect
`{"detail": ...}`. That read fails on the fragment
(`json.decoder.JSONDecodeError`). The JSON shape belongs to reorder, move,
and restore. The owed outcome for these two archive actions is the HTML
list notice. The failure was already present at base `e433223` when it was
found during WISHENKA-218.

This is debt on the gift lifecycle (parent epic WISHENKA-21): archiving a
wish is how a wish leaves the active list. This task does not add a screen
and does not change who may archive, what a successful archive does, or how
received gifts stay apart from the archive.

Implementation language: Python.

## User Stories

- As a **wishlist author** (owner, administrator, or member), when I open
  archive confirmation or confirm archive on an archived wishlist, I receive
  status 409 and the archived-wishlist notice in `#list-notice`
  (`web.item.archived_wishlist_error`). The dialog closes. The wish stays
  where it is.
- As a **wishlist author**, when I open archive confirmation or confirm
  archive for a wishlist that does not exist, or for a wish that is not on
  the list, I receive status 404 and the missing-resource notice in
  `#list-notice` (`web.item.resource_not_found`). In the Russian UI the
  notice is «Желание или вишлист больше недоступны.». The dialog
  closes.
  No wish is archived.
- As a **signed-in person who is not a member** of the wishlist, when I open
  archive confirmation or confirm archive, I receive the same 404 and the
  same missing-resource notice as for a wishlist that does not exist. The
  notice does not reveal that the list exists or that I lack membership.
- As a **person looking at the list**, the page swaps that HTML into
  `#list-notice` and clears the error flag, so `htmx:responseError` does
  not fire and a generic failure message does not replace the notice.
- As a **maintainer**, the eight archive nodes in
  `tests/test_items_ui_error_mapping.py` describe this HTML notice and
  status for both archive confirmation and archive.

## Definition of Done

Both actions are in scope, and only these two:

- **Archive confirmation** — open the confirmation for one wish on a
  wishlist (`archive_confirm_ui`).
- **Archive** — confirm archiving that wish (`archive_item_ui`).

Each of the four refusals is the existing HTML fragment from
`_modal_domain_error_response`: status 409 with
`web.item.archived_wishlist_error`, or status 404 with
`web.item.resource_not_found`. The fragment clears the open item dialog and
writes that localized sentence into `#list-notice`. `app.js` swaps the
fragment and clears `isError`, so `htmx:responseError` does not fire.

| Situation | Who acts | Status | Notice |
| --- | --- | --- | --- |
| Wishlist is archived | A member of that wishlist | 409 | `web.item.archived_wishlist_error` |
| Wishlist is unknown | A signed-in author | 404 | `web.item.resource_not_found` |
| Caller is not a member | A signed-in non-member | 404 | `web.item.resource_not_found` |
| Wish is unknown | A member of a known, active wishlist | 404 | `web.item.resource_not_found` |

The visible sentence is the catalog text for the active locale. In the
Russian UI the 409 sentence is
«Вишлист в архиве — изменения недоступны.»
and the 404 sentence is
«Желание или вишлист больше недоступны.».
The acceptance criterion is this HTML list notice. `{"detail": ...}` is
the body for reorder, move, and restore. It is the criterion for those
routes only.

1. **Archived wishlist.** Both actions return 409 and the HTML list notice
   for `web.item.archived_wishlist_error`. The dialog closes. The wish is
   not archived by the attempt.
2. **Unknown wishlist.** Both actions return 404 and the HTML list notice
   for `web.item.resource_not_found`. The dialog closes.
3. **Non-member.** Both actions return 404 and the same HTML list notice as
   an unknown wishlist. The notice does not say that the caller lacks
   access, and it does not name the wishlist.
4. **Unknown wish.** Both actions return 404 and the same HTML list notice.
   In the Russian UI `#list-notice` reads «Желание или вишлист больше
   недоступны.» and the dialog closes. No other wish on the list is
   archived.
5. **Page handling.** `app.js` swaps the fragment into the page and clears
   `isError`. `htmx:responseError` does not fire, so it does not overwrite
   `#list-notice`.
6. **Standing checks.** These eight nodes pass by asserting that HTML notice
   and status. They pass without calling `resp.json()` and without expecting
   `{"detail": ...}`:

   - `test_archived_wishlist_gives_409[archive-confirm]`
   - `test_archived_wishlist_gives_409[archive]`
   - `test_unknown_wishlist_gives_404[archive-confirm]`
   - `test_unknown_wishlist_gives_404[archive]`
   - `test_non_member_gives_404[archive-confirm]`
   - `test_non_member_gives_404[archive]`
   - `test_unknown_item_gives_404[archive-confirm]`
   - `test_unknown_item_gives_404[archive]`

7. **Other routes.** Reorder, move, and restore keep their existing JSON
   detail bodies, including 409 `{"detail": "Wishlist is archived"}` and
   404 `{"detail": "Resource not found"}`.
8. **Surprise.** These refusals name no giver, reservation, or purchase.

## Task Description

### Problem

Archiving moves a wish off the active list and keeps history. Before that
happens, opening the confirmation and confirming the archive must refuse
four situations with the HTML list notice the dialogs already use:

- The wishlist is archived: status 409 and
  `web.item.archived_wishlist_error` in `#list-notice`. The dialog closes.
- The wishlist does not exist: status 404 and
  `web.item.resource_not_found` in `#list-notice`. The dialog closes.
- The caller is not a member: the same 404 notice, so membership is not
  disclosed.
- The wish is not on the list: the same 404 notice. In the Russian UI
  the notice is «Желание или вишлист больше недоступны.».
  The dialog closes.

`archive_confirm_ui` and `archive_item_ui` already return that fragment
from `_modal_domain_error_response`. `app.js` swaps it and clears
`isError`, so `htmx:responseError` does not fire.

`tests/test_items_ui_error_mapping.py` still calls `resp.json()` and
expects `{"detail": ...}` for those two actions. Parsing the fragment as
that object fails with `json.decoder.JSONDecodeError`. The eight nodes
listed in Definition of Done are the whole of this failure. They were found
during WISHENKA-218 at base `e433223`. The JSON detail body stays the
contract for reorder, move, and restore.

### Scope

- The status and the HTML list notice of archive confirmation and of
  archive for the four situations in the table, including dialog close and
  the page swap that keeps `htmx:responseError` from firing.
- Making the eight named nodes agree with that HTML notice.

### Constraints

- Do not change who may archive a wish.
- Do not change a successful archive: the wish still moves to the archive,
  and received gifts stay in "Gifted" rather than in the archive.
- Do not change opening confirmation when the wishlist is active, the caller
  is a member, and the wish is on the list, including the existing warning
  when a reservation or a received quantity is present and the wishlist asks
  for that warning.
- Do not replace the archive HTML refusal with a JSON detail body.
- Do not change reorder, move, or restore, including their existing 409 and
  404 JSON detail mapping.
- Do not change the refusal for an invalid wish order.
- Do not take on the other failures named in the old repro command.
  WISHENKA-220, WISHENKA-232, WISHENKA-235, WISHENKA-265, and the rest of
  that command are separate tickets.
- Keep surprise secrecy: these refusals name no giver, reservation, or
  purchase.

### Assumptions

- "Member" means owner, administrator, or member of the wishlist. A
  signed-in person outside that set is a non-member.
- The unknown-wishlist, non-member, and unknown-wish answers stay identical
  so an outsider cannot distinguish them.
- The notice text follows the active locale. The Russian sentences in
  Definition of Done are the catalog text for `ru`.
- The eight nodes are the acceptance checks. They describe the HTML notice
  the two archive actions already return. No new product screen is required.

## Main Entities

- **Wishlist.** A list of wishes. It is active or archived. An archived
  wishlist refuses both archive actions with status 409 and the
  archived-wishlist list notice.
- **Wish.** One item on a wishlist. Archiving it is what these two actions
  are for when the wish is on an active list and the caller is a member. A
  missing wish refuses both actions with status 404, the missing-resource
  list notice, and a closed dialog.
- **Author.** Owner, administrator, or member. Only an author may archive.
- **Non-member.** A signed-in person who is not an author of that wishlist.
  Their refusal matches a missing wishlist.
- **List notice.** The `#list-notice` sentence the person reads after a
  refused archive attempt. It is the HTML fragment from
  `_modal_domain_error_response`, not a JSON detail body.

## Q&A

- **Why is the owed outcome the list notice?** Archive confirmation and
  archive already answer the four refusals with the HTML fragment from
  `_modal_domain_error_response`. The person sees that sentence in
  `#list-notice`, and the dialog closes. `app.js` swaps the fragment and
  clears `isError`, so `htmx:responseError` does not fire.
- **Why do the eight checks fail today?** They call `resp.json()` and expect
  `{"detail": ...}`. The archive answers are HTML fragments, so that parse
  fails. The checks are owed the HTML notice and the status in the table.
- **Where does `{"detail": ...}` belong?** Reorder, move, and restore. Their
  409 and 404 bodies stay JSON. Those bodies are not the acceptance
  criterion for the two archive actions.
- **Why both actions?** Confirmation and the archive itself are the two
  moments a person tries to archive. Each of the four situations is refused
  on both, with the same status and the same list notice.
- **Why is the non-member answer the same as "not found"?** So the notice
  does not reveal that the wishlist exists.
- **What does a missing wish show?** Status 404, the dialog closes, and
  `#list-notice` shows the `web.item.resource_not_found` sentence. In the
  Russian UI that sentence is
  «Желание или вишлист больше недоступны.».
- **Are the other red nodes from the WISHENKA-218 run in this task?** No.
  Only the eight archive nodes in `tests/test_items_ui_error_mapping.py`.
