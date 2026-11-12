# WISHENKA-20: Technical Debt Analysis

## Shortcuts Taken

The cabinet page extends `base.html` and sets `viewer_identified`, so its
promise buttons use the listener already in that template. On
`DOMContentLoaded` the page requests `GET /api/auth/csrf` and stores the
token only when that response resolves. `htmx:configRequest` returns
without `X-CSRF-Token` while `csrfToken` is still empty, including when
that GET fails. A cookie mutation in that window is HTTP 403
`Invalid CSRF token`. The cabinet branch then treats 403 as
`notice=refused` and re-GETs the list, which is what
`20-architecture.md` specifies for 401, 403, and 404. The gifter sees
«Бронь не изменилась.» for a write that never reached the promise.
**NON-BLOCKER — Low.** The request fails closed and no row is stored.
This is the same script and the same empty-token window already tracked
for the wish card. It is not a second follow-up.
Jira: [WISHENKA-123](https://pypost.atlassian.net/browse/WISHENKA-123)

`showHome` in `miniapp.js` loads the home card with `fetch` and
`credentials: 'same-origin'`. That request is a GET. It does not post,
and it does not read the `base.html` token. It is not that window.

The cabinet read uses `WishlistStore.execute` (a full snapshot). The
architecture keeps `get_user_reservations` off
`_RESERVATION_INVENTORY_METHODS` and forbids a second write transaction
on these routes. That choice is not a shortcut.

`json-enc` is loaded from
`https://unpkg.com/htmx.org@1.9.12/dist/ext/json-enc.js`, the same host
and version as the HTMX script already in `base.html`. The cabinet page
does not set the Mini App CSP. The architecture specifies that
extension for the quantity form. It is not debt.

A 409 body that contains `available` is sent on as `notice=shortage`.
The list partial prints «Бронь не изменилась. Свободно: N.» with N
taken from `change_ceiling - reserved_quantity` for that row, which is
the wish remainder. Any other 409, and 401, 403, and 404, use
`notice=refused`. The list does not echo `detail`. That split is the
architecture. It is not a follow-up.

`change_ceiling` is `reservation.quantity + item.available_quantity`,
and the DTO default remains `0`. The for-name rules in
`_cabinet_recipient_name` follow the personal-list and collaborative
cases in the architecture. Neither is a shortcut.

## Code Quality Issues

The presenter, the three templates, the `showHome` insertion, and the
`.reservation-row` branch are the surface this task delivered. No
rename, split, or extra abstraction is waiting.

The row stores the status as «Забронировано» or «Куплено». The template
picks «Куплено» or «Вернуть в бронь» from that label. The query returns
only `ACTIVE` and `PURCHASED`, and those two words are the labels the
architecture puts on the row. That branch is not a follow-up.

The list refresh assigns the list partial with `outerHTML` and then
calls `htmx.process`. It does not assign the write `responseText`, and
it does not fetch the wish-card partial. That is the refresh the
architecture requires. It is not a follow-up.

## Missing Tests

`tests/test_reservations_cabinet_ui.py` sets
`pytestmark = pytest.mark.timeout(30)`. Every other collected module
under `tests/` declares `pytest.mark.timeout` at module scope.
`tests/test_preview_resource_reuse.py` also overrides one test at 120
seconds. `tests/__init__.py` collects no tests. Timeout markers are
present on every collected test. This check does not block closing the
task.

The Mini App was not opened in a browser. The architecture forbids that
pass: the harness is `create_app`, a bearer session, BeautifulSoup, and
no browser. The eleven tests request the served card, the cabinet page,
and the list partial. They also read the served `/static/miniapp.js`
and the inline script from a page that extends `base.html`. Those
checks cover `showHome` (the card URL, `node()`, no HTML assignment,
and no fetch from `publicView` or `invitationView`) and the cabinet
branch (list refresh, no wish-card fetch, no `responseText` in the
cabinet, and the 503 sentence leaving `#reservations-cabinet` in
place). A browser pass is not a follow-up.

Those tests use a bearer token. They do not send a cookie mutation
through the page script, so they do not cover the empty-token window.
That gap is WISHENKA-123, not a second item.

## Performance Concerns

Each promise write stays one `execute_wish` transaction with
`BEGIN IMMEDIATE`. The cabinet GET is one full snapshot, which is the
read the architecture requires, and the home adds one card GET after
the three sections load. A success refresh replaces the list partial.
The CSRF request is the one GET per identified `base.html` load already
on the wish card. This task adds no new latency target. Nothing here is
a follow-up.

## Follow-up Tasks

No follow-up below blocks closing WISHENKA-20. Nothing new is opened.
The full-snapshot read, the unpkg `json-enc` script, the 409
`available` check, the status-label button branch, and the decision not
to open the Mini App in a browser are not follow-ups.

The empty-token window is the existing wish-card item. The cabinet uses
that same `base.html` script, so it is not filed again.

- **NON-BLOCKER — Low: Cookie click before the CSRF fetch has no
  X-CSRF-Token.** Same `htmx:configRequest` listener. Hold the unsafe
  request until the token is set. Do not paint that CSRF 403 as a
  refused booking. Keep a real 403 on the existing `notice=refused`
  refresh. Bearer requests stay valid without the header.
  Jira: [WISHENKA-123](https://pypost.atlassian.net/browse/WISHENKA-123)
