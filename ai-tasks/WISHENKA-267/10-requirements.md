# WISHENKA-267: Signed-in move obtains a CSRF token

## Goals

A signed-in giver reorders a wish on a list in the real browser. The browser
already holds that person's session cookie. Before the move is sent, the page
obtains a CSRF token bound to that session, and the move is accepted.

Today that check stops before the move. At base `e433223`,
`tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
waits 5 seconds for a CSRF token from `/api/auth/csrf` and still sees no
token (last value false). The move is never confirmed.

Who may reorder a wish, what a move means, and surprise secrecy stay as they
are. Making the wait longer than 5 seconds is not an acceptable outcome. The
WishlistStore import cycle (WISHENKA-357) and the shared Mini App script stay
outside this change.

Implementation language: Python.

## User Stories

- As a **signed-in giver** with a session cookie, I move a wish in the real
  browser, the page obtains a CSRF token for my session, and the move is
  accepted.
- As that giver, I see the wish in its new place on the list, and the new
  place is still there after I reload the list.
- As a **recipient**, I still never learn who reserved or bought a wish
  because of this move.
- As a person who is not allowed to reorder this list, I do not gain a move
  control from this change.
- As a **maintainer**, I can trust
  `test_real_htmx_move_button_with_cookie_and_csrf` to show that a cookie
  session yields a CSRF token and that the move is accepted, within the
  existing 5 second wait.

## Definition of Done

1. **Token.** A signed-in giver who opens the list in the real browser with
   the session cookie obtains a CSRF token from `/api/auth/csrf` before the
   move is sent. The token is present within the existing 5 second wait.
2. **Move accepted.** That giver moves one wish down. The move request is
   accepted, and the list shows the new order.
3. **Persistence.** After the list is reloaded, the new order is still the
   order on the list.
4. **Standing check.**
   `tests/test_wishlist_htmx_smoke_browser.py::test_real_htmx_move_button_with_cookie_and_csrf`
   passes. It is no longer the timeout recorded at `e433223` (5 seconds,
   CSRF token from `/api/auth/csrf`, last value false).
5. **Wait.** The 5 second wait in that check is not lengthened to make it
   pass.
6. **Unchanged rules.** Who may move a wish, and what a recipient may learn,
   stay as they are.
7. **Out of this task.** The WishlistStore circular import (WISHENKA-357) is
   not fixed here. `wishenka/web/static/app.js` is not edited to add the
   substring `receipt`.

## Task Description

### Problem

Reordering a wish is a normal action for a signed-in giver on a list they
may edit. The real browser holds the session cookie and must obtain a CSRF
token so the move is accepted as that person's action.

The standing check never reaches the move. It waits 5 seconds for the CSRF
token from `/api/auth/csrf` and the token is still absent. Found while
working WISHENKA-218. The cause is not diagnosed in this step.

### Scope

- A signed-in giver, session cookie present, obtains a CSRF token in the
  real browser and a move of one wish is accepted.
- The new order remains after reload.
- The standing check above describes that outcome within its existing 5
  second wait.

### Constraints

- Do not lengthen the 5 second wait as the way to pass the check.
- Leave who may move a wish, and what moving it does, unchanged.
- Leave surprise secrecy unchanged.
- Leave the WishlistStore circular import to WISHENKA-357.
- Leave `wishenka/web/static/app.js` free of the substring `receipt`. Do not
  edit that file to add it.
- The baseline commit on the ticket is `e433223`. This step records that
  known failure and does not re-run the historical baseline.

### Non-goals

- A new move control, a new list screen, or a new sign-in method.
- A longer wait, a retry loop, or a skipped CSRF check in the standing test.
- Repair of the WishlistStore circular import (WISHENKA-357).
- Any edit of `wishenka/web/static/app.js` that introduces the substring
  `receipt`.
- Other failing checks from the sprint.

### Main entities

- **Giver** — the signed-in person who moves a wish on a list they may edit.
  In the standing check this person is the list owner, identified by the
  session cookie.
- **Wishlist** — the list whose wish order changes.
- **Wish** — the entry the giver moves.
- **Session cookie** — the proof that the browser is that signed-in giver.
- **CSRF token** — the session-bound token the page must obtain before the
  move is accepted. Absent after 5 seconds in the recorded failure.
- **Move** — changing the wish's place on the list (one step down in the
  standing check). The request is accepted and the new order persists.
- **Recipient** — must not learn giver identity, a reservation, or a
  purchase from this move.

## Q&A

- **Q:** Why does this task exist?
  **A:** A signed-in giver must be able to move a wish in the real browser
  when the session cookie is already present. The page must obtain a CSRF
  token and the move must be accepted. At `e433223` the standing check times
  out after 5 seconds still waiting for that token (last value false), so
  the move is never confirmed.

- **Q:** Who is the giver in this check?
  **A:** The signed-in person who may reorder wishes on the list. The
  standing check signs in the list owner with the session cookie and moves
  one wish. This task does not give a person who only reserves gifts a new
  right to reorder someone else's list.

- **Q:** What must happen in the browser?
  **A:** With the session cookie, the page obtains a CSRF token from
  `/api/auth/csrf` within the existing 5 second wait. The giver then moves
  a wish, the move is accepted, and the new order remains after reload.

- **Q:** May the 5 second wait be increased?
  **A:** No. Passing by waiting longer is out of scope.

- **Q:** Does this task fix the WishlistStore circular import?
  **A:** No. That import cycle remains WISHENKA-357.

- **Q:** May the shared Mini App script carry the word receipt?
  **A:** No. `wishenka/web/static/app.js` is not edited to add the substring
  `receipt`.
