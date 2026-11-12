# WISHENKA-19: Technical Debt Analysis

## Shortcuts Taken

`base.html` loads `GET /api/auth/csrf` after `DOMContentLoaded` when the
page is marked `data-viewer-identified`. The `htmx:configRequest` handler
returns without setting `X-CSRF-Token` while `csrfToken` is still empty,
including when that GET fails and the token stays empty. A cookie mutation
in that window has no header. `BrowserSecurityMiddleware` answers HTTP 403
`Invalid CSRF token`. The reservation handler treats 403 as
`notice=refused` and re-GETs the card, so a gifter sees
«Бронь не изменилась.» for a write that never reached the promise.
**NON-BLOCKER — Low.** The request fails closed and no row is stored.
After the token is set, the next click sends the header. Bearer calls
skip the cookie check. This is the follow-up below.

Fetching the token after load, and keeping it out of the HTML, is the
architecture. That choice is not a separate shortcut.

`json-enc` is loaded from
`https://unpkg.com/htmx.org@1.9.12/dist/ext/json-enc.js`, the same host
and version as the HTMX script already in `base.html`. The architecture
specifies that extension for HTMX 1.9.12. It is not debt.

A 409 body that contains `available` is sent on as `notice=shortage`.
Both shortage texts do: `Cannot reserve {quantity} units, available:
{available}` and `Cannot increase reservation by {delta}: {n} available`.
The other 409 details from the reservation router do not contain that
word. The card does not echo `detail`. That split is the architecture.
It is not a follow-up.

`_editor_card_flags` passes `viewer_identified` and `wishlist_active` as
true on quick-add, edit, move, reorder, and restore. Those routes already
ran `_ensure_member_and_active`, so the caller is identified and the list
is active. The list page, the share page, and the card partial pass the
real values. The hardcoded pair is not a follow-up.

The latest occupying row is `user_reservations[-1]`. The architecture
keeps store order (`id` ascending) and the in-memory append, and it
forbids a sort by `updated_at`. That is not debt.

## Code Quality Issues

The giver block, the five existing routes, and the two gifter fields are
the surface this task delivered. No rename, split, or extra abstraction
is waiting.

The book form carries `hx-ext="json-enc"`. The change control carries
`hx-ext="json-enc"` and `hx-include="closest form"` on the button. Both
send `{"quantity": N}` with `hx-swap="none"`. That is the architecture.
It is not a follow-up.

## Missing Tests

`tests/test_wish_card_giver_controls.py` sets
`pytestmark = pytest.mark.timeout(30)`.
`tests/test_wishlist_roles_lifecycle.py` sets
`pytestmark = pytest.mark.timeout(10)`. Every other collected module
under `tests/` declares `pytest.mark.timeout` at module scope.
`tests/test_preview_resource_reuse.py` also overrides one test at 120
seconds. `tests/__init__.py` collects no tests. Timeout markers are
present on every collected test. This check does not block closing the
task.

The HTMX click path was not run in a browser. The architecture says no
browser is required: the assertion is the refresh procedure in the served
page. `test_expanded_refresh_clears_hidden` reads that procedure from the
page script (`aria-expanded` before `outerHTML`, then `hidden` cleared on
the new details). The other giver cases assert the served markup and the
existing promise API. A browser click is not a follow-up.

Those tests use a bearer token. They do not send a cookie mutation
through the page script, so they do not cover the empty-token window.
That gap is the follow-up below, not a second item.

## Performance Concerns

Each promise write stays one `execute_wish` transaction with
`BEGIN IMMEDIATE`. The card then GETs the existing partial, which is the
refresh the architecture requires. The CSRF request is one GET per
identified page load. This task adds no new query and no new latency
target. Nothing here is a follow-up.

## Follow-up Tasks

No follow-up below blocks closing WISHENKA-19. The unpkg `json-enc`
script, the decision not to run the click path in a browser, the 409
`available` check, and the editor card flags are not follow-ups.

- **NON-BLOCKER — Low: Cookie giver click before the CSRF fetch has no
  X-CSRF-Token.** In `wishenka/web/templates/base.html` the token is
  stored only after `GET /api/auth/csrf` resolves. Until then, and if
  that GET fails, `htmx:configRequest` returns without the header. A
  cookie mutation is HTTP 403 `Invalid CSRF token`. The reservation
  branch treats every 403 as `notice=refused`, so the card says
  «Бронь не изменилась.» Hold the unsafe request until the token is
  set. Do not paint that CSRF 403 as a refused booking. Keep a real
  recipient 403 on the existing `notice=refused` refresh, and keep the
  token out of the HTML. Bearer requests stay valid without the header.
  Jira: [WISHENKA-123](https://pypost.atlassian.net/browse/WISHENKA-123)
