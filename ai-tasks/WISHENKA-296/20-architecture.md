# WISHENKA-296: No empty wishlist is created when the user leaves the creation flow

## Research

### Verified baseline (facts checked in code on master, 93829b9)

- **Creation happens on the click.** `showHome()` (`wishenka/web/static/miniapp.js:368`) renders
  `button(t('miniapp.home.create_wishlist'), pending(async () => { api('/api/wishlists',
  {method: 'POST', body: '{}'}); await showList(list.id) } ...), 'btn-primary home-create-btn')`
  (`miniapp.js:379-383`). Any failure (including a failed `showList`) lands in one `catch` that
  shows `miniapp.home.create_failed`. This is the whole root cause; there is no form.
- **Server accepts an empty body.** `WishlistInput` (`wishenka/web/routes/wishlists.py:34-40`) has
  four optional fields; `create_wishlist` route (`routes/wishlists.py:177-204`) passes
  `title=body.name or ""` to `WishlistService.create_wishlist` (`wishenka/wishlists/service.py:585`).
  The same `WishlistInput` is also the body of `PATCH /api/wishlists/{id}` (settings), so it must
  stay permissive for PATCH. No 422/validation handler is customised: `grep exception_handler`
  finds only the Starlette HTTP handler in `wishenka/web/unavailable.py:63`, so a pydantic failure
  returns FastAPI's default `422 {"detail": [{"loc": ["body", "name"], "msg": ..., "type": ...}]}`.
  Precedent for field constraints through pydantic: `CreateItemDTO.title = Field(min_length=1,
  max_length=255)` (`wishenka/items/schemas.py:32`).
- **Callers of `POST /api/wishlists`.** Production: only the Mini App home button
  (`miniapp.js:380`). The bot never creates a list (`wishenka/bot/capture.py:182-190`,
  `wishenka/bot/entry.py:88` only open the Mini App with `startapp=create`); server-rendered pages have no
  creation. Everything else is tests (see "Existing tests").
- **No client routing.** `grep pushState|popstate|BackButton|beforeunload miniapp.js` is empty: the
  Mini App is a single page that swaps `root` content (`root.replaceChildren(...)`). Browser back,
  Telegram close/back, tab close and reload therefore leave or restart the page; with no request
  before confirmation each of them creates nothing by construction (D6, D8). No history entry is
  pushed by the new form, so nothing changes about back behaviour.
- **Pending guard.** `withPending(control, action, message)` (`miniapp.js:87-100`) keeps a
  `WeakSet` keyed by the control element, disables it, sets `aria-busy`, `.is-pending`, and writes
  the pending status line; it re-enables the control in its own `finally` (`:94-100`), i.e. only
  after the action returned. `pending(action, msg)` adapts it to `button()` handlers
  (`miniapp.js:102-104`). The guard is per control, not per request. The existing burst test
  (`tests/test_cross_screen_comfort_browser.py:465`) clicks `.home-create-btn` three times and
  asserts one `POST` through a `fetch` wrapper `API_PRELOAD` (lines 90-112) that classifies
  `POST /api/wishlists` as `create`.
- **Settings form to mirror.** `settingsForm(list)` (`miniapp.js:~668`): `<form
  class="wishlist-settings-form">`, four `label.settings-field` blocks (name, description,
  event_title, event_date as `datetime-local`), hint spans, `.form-actions.settings-form-actions`
  with a `type=submit` Save and a Cancel button. Date semantics: value `YYYY-MM-DDTHH:mm`
  interpreted as UTC and sent as `new Date(`${v}Z`).toISOString()`, empty means `null`. Settings
  has no validation and no inline errors; it reports `save_failed` through `#status`.
- **`showList(id)` returns `true`/`false`** (`miniapp.js:~855`, `return true` on success, `return
  false` after showing `miniapp.list.load_failed`). Its Back button calls `showHome`
  (`miniapp.js:777`), which reloads `/api/wishlists`, so a freshly created list appears in "My
  wishlists" without client patching.
- **Deep link.** `start()` (`miniapp.js:976-984`): after `bootstrap()` and `showHome()`, for
  `startapp=create` it only runs `root.querySelector('button')?.focus()`. Unchanged by this task
  (D9). Existing test `tests/test_home_overview_browser.py:527-538` already asserts that this link
  leaves `GET /api/wishlists == []`.
- **i18n.** `wishenka/i18n/catalog.py` EN/RU tables; keys with prefixes `nav.`/`miniapp.` are
  embedded in the shell (`catalog.py:~1317`). Reusable existing keys: `miniapp.home.create_wishlist`
  (275/921), `miniapp.home.create_failed` (276/922), `miniapp.wishlist_settings.field_{title,
  description,event,date}` and `hint_{title,description,event,date}` (343-351 / 996-1004),
  `miniapp.wishlist_settings.cancel`, `nav.back`, `nav.working`.
- **CSS.** Tokens `--danger #a61335`, `--focus`, `--touch-target 44px`, `--border-subtle`,
  `--muted`; global `button, input { min-height: var(--touch-target) }` (`miniapp.css:42`),
  `input { width: 100%; max-width: 100% }` (`:63`), `#app .form-actions` flex-wrap rules
  (`:111-117`), `.settings-field-label/-hint` (`:130-132`), `.history-error` (danger, bold,
  `:298`), `:focus-visible` outline (`:54`), `#app .home-create-btn` (`:167`).
- **Existing facts about title length.** The 255 limit for lists is documented only
  (`doc/dev/miniapp.md:447`); Python `len()` counts code points, JS `.length` counts UTF-16 units.

### Findings that shape the design

0. **`showHome` has no staleness guard.** After `root.replaceChildren(...)` it awaits
   `Promise.all([...])` (`miniapp.js:391`), appends the sections (`:427`, `:452`, `:492`, `:539`) and
   awaits the reservations card (`:542`) without checking that it is still the current screen. The
   history screen has the guard (`let historyRenderToken` `:232`, `const token = ++historyRenderToken`
   `:333`, checks `:348`, `:357`). Today it did not matter because home had no sibling screen
   reachable during its load; with a form reachable from the home buttons, a tap on Create during a
   slow load would let the late sections be appended under the form, and Cancel -> `showHome()`
   during an in-flight `showHome()` would append two sets of sections. The design adds the same
   token pattern to `showHome` (D-2).
0b. **`home_script_problems`** (`tests/test_reservations_cabinet_ui.py:471-489`) scans the source
   between `async function showHome(` and `function settingsForm(` and forbids `innerHTML`,
   `insertAdjacentHTML`, `createContextualFragment` there and requires the card URL; code placed
   inside that slice inherits those rules. `showCreate` is therefore placed **before** `async function
   showHome(` (outside the slice) and follows the same no-HTML-injection rule by construction.
0c. **Harness limits.** The Node fake DOM `makeEl` (`tests/test_miniapp_i18n_repro.py:30-85`) has no
   `removeAttribute`, `classList`, `scrollIntoView`; its `querySelector` only understands `button`
   and `.wishlist-section`; `click()` dispatches only `click` listeners (no `submit`/`input`).
1. The smallest fix that satisfies "nothing before confirmation" is to remove the request from the
   click and put a form (new screen) between the click and the request. Everything else follows
   (cancel, reload, back, deep link) for free because no request exists before the Create submit.
2. `POST /api/wishlists` can only be made "title required" by a **new, creation-only input model**;
   the shared `WishlistInput` must stay as is for `PATCH`.
3. The double-submit guard is per element. Enter in a text field fires the form `submit` event, and
   a click on a `type=submit` button fires the same `submit` event. If the guard wraps the submit
   handler on one control (the Create button), taps and Enter share one lock.
4. After the POST succeeded the form must never come back (a retry would create a second list); the
   old code's single `catch` conflated "creation failed" with "opening the list failed".
5. `datetime-local` exposes an unparseable/partial value only as `value === ''` with
   `validity.badInput === true`; checking only `value` would silently drop a date the user typed.
   Chromium also accepts 5-6 digit years there: `new Date('20000-01-01T00:00Z')` is Invalid Date and
   `.toISOString()` throws `RangeError`. Building the payload must happen inside the error-handled
   block and the parsed date must be validated (NaN or year > 9999 is invalid).
6. A 422 does not always mean "title": `event_date` (pydantic `datetime`) can be rejected too, so
   the client needs the response body (`detail[].loc`) to place the message; `api()`
   (`miniapp.js:111-121`) currently throws without the body.
7. `showHome` only sets `tabindex="-1"` on its `<h1>`; nothing focuses it. The existing pattern is
   an explicit `root.querySelector('h1')?.focus()` (`miniapp.js:327`, `:646`).

## Implementation Plan

Smallest coherent change: one new Mini App screen function, one server input model, new i18n keys,
a few CSS rules, tests and docs. No migration, no change to the service rules, retention, settings
(PATCH), the bot, the deep link or the HTMX pages.

1. `wishenka/web/routes/wishlists.py`: new `WishlistCreateInput(WishlistInput)` with a required
   `name` (trimmed, 1-255 code points); `create_wishlist` uses it (D-1).
2. `wishenka/web/static/miniapp.js`: new `showCreate()` screen; the home button calls it instead
   of POSTing (D-2, D-3).
3. `wishenka/i18n/catalog.py`: new `miniapp.create.*` keys, EN and RU (D-4).
4. `wishenka/web/static/miniapp.css`: small `.create-*` / `.settings-field-error` block (D-5).
5. Tests updated/added (Test strategy), docs in Step 8 (Docs to update).

**Failing Repro (next Step 3).** Red tests written against unchanged code, before any production
change. Red means they fail now for the reported reason: "a click creates a list" and "an empty
body is accepted". The red tests use only what exists today: **reload and in-app navigation**
(there is no Cancel yet, and `history.back()` in a fresh CDP tab with a single history entry is a
no-op, so it is not used as a leave action in the red test).

- `tests/test_wishlist_create_validation_api.py` (new, no browser, style of
  `tests/test_wishlist_api.py`: `TestClient(create_app(settings))` with a bearer header). Red now
  because `{}` returns 201:
  `POST {}` -> 422; `{"name": ""}` -> 422; `{"name": "   "}` -> 422; `{"name": null}` -> 422; 256
  characters -> 422; 255 characters -> 201; after each rejected call `GET /api/wishlists` still
  has the same count; `"  Birthday  "` -> 201 and the stored/returned `name == "Birthday"`.
- `tests/test_wishlist_create_ui.py` (new, Node harness `_NODE_HARNESS` from
  `tests/test_miniapp_i18n_repro.py`, `timeout(20)`, no browser marker): home click on the create
  button issues **no** `POST /api/wishlists` and renders a form (red now: POST sent, no form).
- `tests/test_wishlist_create_browser.py` (new, CDP, `pytest.mark.browser` + `timeout(45)` per
  `tests/test_browser_prerequisites.py`, fixtures `wishlist_server`, `chromium_browser`,
  `open_miniapp` from `tests/browser_screens.py`): the reported scenario with today's means. Open
  home, click "Create wishlist", then **reload** the page (and, in a second case, navigate in-app to
  another screen and back), then `GET /api/wishlists` count equals the count before. Red now because
  the click creates a list. The Cancel/back/partial-fill cases are added in Step 4 once the form
  exists (they cannot be red-first: there is no form).
- Sequencing: research -> Step 3 red tests against unchanged code -> Step 4 implement until green,
  then the click-time tests of D1 are rewritten (not deleted) as part of the same step.

## Architecture

### Components

```
Home (showHome)                       Create screen (showCreate)              Server
 [Create wishlist] --click--> no request; root.replaceChildren(form) 
                                       Create (submit, Enter)  --POST /api/wishlists {name,...}--> WishlistCreateInput
                                         | withPending(createBtn)                                    | 422 -> inline error
                                         | client validation first                                   | 201 -> list projection
                                       Cancel --> goHome() = showHome() + h1.focus()  (nothing sent)
                                       201 --> showList(id)  (fallback goHome() on load failure)
showHome: ++homeRenderToken; stale loads (token mismatch) return before touching root/#status;
showCreate: ++homeRenderToken on entry
bot "Create wishlist" --startapp=create--> showHome() + focus first button   (unchanged, D9)
```

Pattern: client-side screen function in the existing single-file vanilla-JS Mini App (same style as
`showHistory`, `settingsForm`); server-side thin input model plus pydantic validation (same style as
`CreateItemDTO`). No router, no draft store, no new JS module.

### D-1 Server contract (`POST /api/wishlists`)

Decision: **server-side enforcement in addition to the client check** (defence in depth; the API
must not be able to produce an untitled list from any caller, and it is the only way the
requirement "validation rules" is a property of the product and not of one client).

```python
class WishlistCreateInput(WishlistInput):
    """Creation payload: unlike settings edits the title is required."""
    name: str          # required; non-null
    @field_validator("name")  # mode="after": value is already a str
    @classmethod
    def _title(cls, v): v = v.strip(); 1 <= len(v) <= 255 else raise ValueError(...)
```

- Rules: `name` is required (missing or `null` -> 422), whitespace is trimmed first (leading and
  trailing, `str.strip()`), the trimmed value must have 1-255 characters (`len()` = code points),
  whitespace-only -> 422. The **trimmed** value is stored and returned (the client also sends the
  trimmed value; both sides agree, so the list never keeps leading/trailing blanks).
- Optional fields (`description`, `event_title`, `event_date`) are unchanged: no new length limits
  (the settings PATCH has none either; consistency, smallest change). `event_date` is still a
  pydantic `datetime`; an unparseable value already gives 422. Adding limits for optional fields to
  both create and PATCH is recorded as a follow-up candidate (Step 7), not done here.
- Error shape: FastAPI default `422 {"detail": [{"loc": ["body","name"], "msg": ..., "type": ...}]}`,
  consistent with every other pydantic-validated route (items, profile). No custom handler.
- Client mapping of status: `api()` (`miniapp.js:111-121`) throws an `Error` with `.status` but not
  the body. Small change: before throwing, `api()` also stores the parsed JSON body as `err.body`
  (`try { err.body = await response.json(); } catch (_) {}`; harmless for every other caller, which
  ignores it). `mapFailure` reads the body defensively: only when `error.status === 422` and
  `Array.isArray(error.body?.detail)` (detail may be a string from an `HTTPException`, or the body
  may be absent/non-JSON; those fall to `create_failed`). A 422 is then mapped by `detail[].loc`: last element `name` -> title inline error
  (`error_title_required`), `event_date` -> date inline error (`error_date_invalid`); both messages
  may be shown. A 422 whose `loc` is not recognised, any other status and any network error ->
  the existing `miniapp.home.create_failed` (D-3 failure). A server 422 for `name` after a passing
  client check is only reachable by a stale client or by a trim difference (JS `trim()` vs Python
  `strip()` treat a few Unicode spaces differently); this 422 mapping is the safety net, the values
  stay in the form.
- Callers: only the Mini App sends `POST /api/wishlists` in production; tests that use it are listed
  in "Existing tests". `PATCH`, `WishlistService.create_wishlist` (service layer keeps `title: str
  = ""`, so service-layer fixtures that create lists directly are unaffected) and the bot are
  unchanged.
- No idempotency key (requirement 7 / F6 stays a known limitation). A 4xx/5xx response produced by
  the application means the store transaction was not committed (`execute()` runs each action in
  one store transaction), so a retry after such a seen failure cannot duplicate. The limitation is
  wider than "response lost": a proxy 502/504 or a client/proxy timeout can also follow a committed
  creation, and the user then sees `create_failed`; a retry can then create a second list. This is
  part of F6, documented, not solved here (idempotency key is a follow-up).

### D-2 Entry point change and the home render guard

`showHome()`: the button handler becomes `button(t('miniapp.home.create_wishlist'), showCreate,
'btn-primary home-create-btn')`; no `pending`, no `api`, no `try/catch` at that site (opening a
local screen cannot fail; a second tap before the next tick only re-renders the same empty form,
`showCreate` is synchronous). This is the only creation entry point (requirement 10); the bot deep
link keeps `showHome()` + `focus()`.

**Staleness guard for `showHome` (same pattern as `historyRenderToken`).** Module-level
`let homeRenderToken = 0;` declared before `showCreate`. `showHome` starts with `const token =
++homeRenderToken;` and, after every `await`, returns without touching `root` or `#status` when
`token !== homeRenderToken`: after the `Promise.all` (`:391`), inside its `catch` (before the load
error status), and after **both** awaits of the reservations-card block: `await fetch(...)`
(`:542`) and `await cardResponse.text()` (`:546`, inside the inner `try/catch`), before inserting
the card and before the final `status('')`. `showCreate` also does `++homeRenderToken` on entry, which invalidates any
home load still in flight. Result: tapping Create during a slow home load shows only the form (the
late sections are dropped, the stale "Loading" status is replaced by `status('')`), and Cancel ->
`showHome()` during an earlier in-flight `showHome()` appends exactly one set of sections (the older
call is stale). The home handlers that call `showHome()` after restore/favorite also get a fresh
token. "Latest wins" holds only among `showHome` and `showCreate` (the only functions bumping
the token); `showHistory`/`showList` do not bump it, which is pre-existing and not a regression. The token lines are inside the slice scanned by
`home_script_problems` and add no forbidden construct.

### D-3 Mini App creation form (`showCreate()` in `miniapp.js`)

Placement: `async function showCreate()` (synchronous body) is placed **immediately before**
`async function showHome(` so it is outside the slice scanned by `home_script_problems` (finding
0b); it still uses only `node()`/`textContent`, never HTML injection. It runs `++homeRenderToken`,
`status('')`, renders, then explicitly calls `root.querySelector('h1')?.focus()` (the `<h1>` has
`tabindex="-1"`) so a screen-reader user hears the new context; the title input is the first tab stop.

**Navigation helper.** `goHome()`: `const done = showHome(); root.querySelector('h1')?.focus();
return done;` (the skeleton `<h1>` is rendered synchronously by `showHome` before its first
`await`). It is used by Cancel and by the post-creation `showList` failure fallback; nothing else
focuses the home `<h1>` today (`showHome` only sets `tabindex`), so the explicit `focus()` is part
of this design and is asserted in tests.

Structure (built at render time with `node()`, `button()`, `append`, `setAttribute` only, because the
Node fake DOM `makeEl` supports only those plus `focus`; error nodes are created lazily and kept in
closure variables, see "Inline errors"):

```
h1[tabindex=-1]                        miniapp.create.title  "Create wishlist"
p.section-subtitle                     miniapp.create.lead
form.wishlist-settings-form.wishlist-create-form[novalidate]
  label.settings-field                 (title)  span.settings-field-label "Title (required)"
                                       input[name=name][aria-required=true][autocomplete=off]
                                       span.settings-field-hint#create-hint-name
                                       span.settings-field-error#create-error-name[role=alert]  (created on error)
  label.settings-field                 (description) input[name=description]  + hint span
  label.settings-field                 (event) input[name=event_title]        + hint span
  label.settings-field                 (date) input[type=datetime-local][name=event_date] + hint span
  div.form-actions.settings-form-actions.create-form-actions
    button[type=submit].btn-primary.create-submit-btn  "Create"
    button[type=button].create-cancel-btn              "Cancel"
```

Only `span` elements live inside a `label` (no `<p>`, same as the settings form). Fields and
semantics are the settings ones: same input names, labels and hints (`miniapp.wishlist_settings.
field_*`, `hint_*` reused verbatim; only the title label differs to mark it required:
`miniapp.create.field_title`), same date handling. `novalidate` keeps the browser's native bubble
out of the way so messages are identical across engines and the Telegram WebView. No `maxlength`
(it would silently truncate a paste and contradict "keep what I typed"; the limit is an error).
The Cancel label reuses `miniapp.wishlist_settings.cancel` (single key; no `miniapp.create.cancel`).

**Client validation** (`validate()`, pure, returns `{field, key, params}` items), run on submit
**before** any request and before `withPending`:

1. title: `value.trim()` empty -> `error_title_required`; `[...trimmed].length > 255` (code points,
   like Python `len()`) -> `error_title_too_long` with `{max: 255}`.
2. date: if `validity?.badInput` is true -> `error_date_invalid`; else if `value` is non-empty,
   `d = new Date(`${value}Z`)` must satisfy `!isNaN(d)` and `1 <= d.getUTCFullYear() <= 9999`
   (Chromium accepts 5-6 digit years, for which `new Date(...)` is Invalid Date and `toISOString()`
   throws `RangeError`; the server rejects year > 9999 too) -> otherwise `error_date_invalid`. A
   missing `validity` (Node harness) skips only the badInput branch.
3. description and event name: no rules (D-1).

**Inline errors (accessible).** `showFieldError(name, message)` creates (or reuses, stored in a
closure map `errors[name]`) a `span.settings-field-error` with `id="create-error-<name>"`,
`role="alert"`, text via `textContent`, appended to that field's `label`; sets on the input
`aria-invalid="true"` and `aria-describedby="create-hint-<name> create-error-<name>"`. Clearing
(`clearFieldError`) empties the stored node's text, detaches it with `parentNode?.removeChild?.()`
guarded by optional calls, and resets the attributes with `setAttribute('aria-invalid', 'false')`
(no `removeAttribute`, `classList` or `scrollIntoView` is required; `scrollIntoView?.()` is an optional
call). The first invalid field gets `input.focus()`; `role="alert"` makes later errors announce too.
An error is cleared when the user edits that field (`input` event) and all are cleared at the start
of each submit. Typed values stay because the form is never re-rendered. No `#status` write for a
validation error (no duplicate announcement); a stale `#status` is cleared with `status('')`.

**Submit, pending and double-submit guard.** One `submit` handler on the form calls
`event.preventDefault()` and covers a click on Create **and** Enter in any control. Order:

1. `if (submitting) return;` (second guard, also set for the whole navigation after success);
2. clear errors, `validate()`; on problems show them, focus the first invalid field, return - **no
   `withPending`, so a blank title never flashes "Creating..."** and no request is made;
3. `await withPending(createBtn, send, t('miniapp.create.pending'))` where `send` builds the payload
   **inside** `try`, performs the `POST`, and on success also awaits the navigation (so the lock is
   held until the form is replaced and a late Enter cannot produce a second POST).

The `WeakSet` in `withPending` is keyed by `createBtn`, so taps, Enter and any mix share one lock
(`withPending` registers the control synchronously before its first `await`, so two submit events in
the same tick cannot both pass). While `send` runs, `submitting = true`, Cancel is `disabled` (and
its click handler returns early on `submitting`), and the inputs get `readonly` (not `disabled`:
values stay visible/selectable). The intent of `test_create_wishlist_burst_sends_a_single_post`
(a burst sends one POST) is preserved.

`send()` (inside `withPending`):

```js
let data;
try {
  data = buildPayload();   // trims; event_date via new Date(`${v}Z`).toISOString(); may throw RangeError
} catch (_) { showFieldError('event_date', t('miniapp.create.error_date_invalid')); return 'invalid'; }
let list;
try { list = await api('/api/wishlists', {method: 'POST', body: JSON.stringify(data)}); }
catch (error) { return mapFailure(error); }          // 422 -> field errors by detail[].loc (Array.isArray(body?.detail)); else 'failed'
if (!(await showList(list.id))) {                   // committed; the form never returns
  await goHome();
  status(t('miniapp.list.load_failed'), 'error');
}
return 'created';
```

After `await withPending(...)` returns (the control has been re-enabled by `withPending`'s `finally`,
`miniapp.js:94-100`) the handler restores state for the non-created outcomes: `submitting = false`,
Cancel enabled, inputs not `readonly`, and **then** moves focus: `'failed'` -> `createBtn.focus()`;
`'invalid'`/422 -> the first invalid field. Focus is never attempted inside `send`, because the button
is still disabled there. `withPending` leaves its "Creating..." text in `#status`, so `send` calls
`status('')` itself in the `'invalid'` (RangeError) path and `mapFailure` calls `status('')` for a
recognised 422 (the `'failed'` path overwrites it with `create_failed`). If `withPending` returns
`undefined` (the call was blocked by the `WeakSet` because a request is already running), the
handler does nothing: it must not reset `submitting`, re-enable Cancel or drop `readonly`, which
belong to the running request.

Optional text values are trimmed, an empty result is sent as `null` (settings sends `value || null`
without trimming; the difference is invisible, and whitespace-only descriptions are avoided).

**Success.** `showList(list.id)` as before (list appears at once, first wish can be added, Back
returns to home, which reloads and lists it under "My wishlists"; requirement 6). If `showList` returns
`false` after a committed creation, the code does not show `create_failed` and never re-enables
Create: `await goHome()` (explicit `h1.focus()`), then `status(list.load_failed, 'error')`; the new
list is visible under "My wishlists". No duplicate is possible because the form is gone.

**Failure.** Network error, non-422 status, or a 422 with an unrecognised `loc`: the form stays, values
are kept, `#status` shows `miniapp.home.create_failed` as an assertive error (same key and
`status(..., 'error')` contract as asserted today), Create/Cancel re-enabled, inputs not `readonly`,
focus on Create (after `withPending` returned, see above). Retry sends a new `POST`; per D-1 an
application-level failure cannot have committed a list (proxy timeouts remain the F6 limitation).

**Cancel.** `button(t('miniapp.wishlist_settings.cancel'), () => { if (!submitting) goHome(); },
'settings-cancel-btn create-cancel-btn')`. Nothing is sent or stored (no `localStorage`/
`sessionStorage`), so the next open is an empty form (requirement 5). Focus lands on the home `<h1>`
(explicit, asserted). `Escape` is not bound (consistent with the settings form). Reload, tab/app
close, Telegram back/close, browser back leave or reload the page: no request existed (requirements
4, 11). No `Telegram.WebApp.BackButton` or `MainButton` is used (D8).

**Deep link.** Untouched (D9): `showHome()` + `focus()` on the first button, which now only opens the form.

### D-4 i18n keys (EN + RU, `miniapp.` prefix so they reach the embedded catalog; parity enforced by existing catalog tests)

| Key | EN | RU |
| --- | -- | -- |
| `miniapp.create.title` | Create wishlist | Создание вишлиста |
| `miniapp.create.lead` | Give your wishlist a title. You can add the other details now or later in its settings. | Дайте вишлисту название. Остальное можно указать сейчас или позже в настройках. |
| `miniapp.create.field_title` | Title (required) | Название (обязательно) |
| `miniapp.create.submit` | Create | Создать |
| `miniapp.create.pending` | Creating... | Создание... |
| `miniapp.create.error_title_required` | Enter a title for the wishlist. | Введите название вишлиста. |
| `miniapp.create.error_title_too_long` | The title is too long: at most {max} characters. | Название слишком длинное: не больше {max} символов. |
| `miniapp.create.error_date_invalid` | Enter a valid date and time or clear the field. | Введите корректные дату и время или очистите поле. |

Reused unchanged: `miniapp.home.create_wishlist` (home button), `miniapp.home.create_failed`
(failure), `miniapp.wishlist_settings.cancel` (Cancel; the only cancel key), `miniapp.wishlist_settings.field_{description,event,date}` and `hint_{title,
description,event,date}`, `miniapp.list.load_failed`. Wording is a final draft; Step 4 may polish
phrasing but not semantics. The old `miniapp.common.untitled_wishlist` stays (legacy lists, D4).
No key mentions reservations (surprise invariant).

### D-5 CSS (`miniapp.css`, tokens only)

- `#app .settings-field-error { display: block; margin: .25rem 0 0; color: var(--danger);
  font-weight: 600; font-size: .9rem; overflow-wrap: anywhere }` and an `::before` warning glyph
  or text prefix is **not** needed: the message text itself says what is wrong (not colour-only).
- Form actions: the markup uses `.form-actions.settings-form-actions.create-form-actions`; no
  `#app .create-form-actions` rule is needed (it would duplicate `.form-actions`, `:111-117`).
  Cancel adds `create-cancel-btn` next to `settings-cancel-btn`, and the neutral style comes from
  extending the existing selector list at `miniapp.css:142` (`#app :is(.settings-cancel-btn,
  .share-reset-btn, .invite-revoke-btn)`), which already matches the shared class.
- `#app .settings-field input[aria-invalid="true"] { border-color: var(--danger); border-width:
  2px }` (state is also in the DOM attribute and the message text).
- `.wishlist-create-form` reuses `.wishlist-settings-form` rules; Create is `btn-primary`.
- Targets: every control keeps `min-height: var(--touch-target)` (44 px); no fixed widths, so at
  320 px the two buttons wrap and long text wraps (`overflow-wrap: anywhere`); inputs are `width:
  100%`. `:focus-visible` outline already exists (`:54`). `readonly` inputs get no special style.
- No animation added (nothing to gate behind `prefers-reduced-motion`).

### D-6 Accessibility outcomes

- Keyboard: DOM order h1 -> title -> description -> event -> date -> Create -> Cancel; Enter submits
  from any text field (native implicit submission with the submit button as default button; the
  `datetime-local` input is also a form control, Enter there submits too); Space/Enter on buttons.
- Screen reader: each input is labelled by its wrapping `label`; hint and error are linked by
  `aria-describedby`; invalid state by `aria-invalid`; errors are `role="alert"`; the first invalid
  field receives focus; pending is announced by the `#status` live region plus `aria-busy`; failure
  is the assertive `#status` error; success moves to the list screen (`showList` own focus/status),
  cancel lands on the home screen with an explicit `h1.focus()` (`goHome()`, D-3; `showHome` itself only sets `tabindex`), `status('')`.
- Not colour-only: error text, `aria-invalid`, thicker border; required marked by the label text
  "(required)" not by an asterisk alone.
- Touch targets >= 44 px; 320 px: no horizontal overflow.

### D-7 Observability (Step 6)

Logs only. No new server events are needed. Note: `wishlist_created` is emitted **twice** per
creation, once by the service (`wishenka/wishlists/service.py:641`) and once by the route
(`routes/wishlists.py:196`, logger `wishenka.web.wishlists`); it is not a single-fire signal unless
filtered by logger. The single-fire signal is `wishlist_mutation_committed` with
`operation="create_wishlist"` (`execute()`, one record per committed creation); Step 6 and the tests
count that one (or `wishlist_created` per logger). With the fix the count of committed creations
equals the count of confirmed valid submits. Validation rejections are visible as `422` in the access log; a dedicated
warning is not added (pydantic rejects before the handler runs and a custom handler would be a new
global behaviour). Step 6 verifies by `caplog` that the records of a 201 and of a 422 never contain
the title, description or event name (PII/user text). Client side has no telemetry (consistent with
the rest of the Mini App).

### D-8 Surprise invariant (specs/00-high.md 4.3)

The form contains no reservation, receipt or "gifted" data and the creation response is the existing
owner projection of a brand-new list (no items). All texts are identical for every user. Validation
errors are generic and carry no list or user data (the 422 body echoes the submitted `input`, only
to the submitting owner). No notification is sent on creation (unchanged). Risk: none new.

### Requirement-to-design traceability

| Requirement | Design |
| ----------- | ------ |
| 1 Nothing before confirmation | D-2 click opens `showCreate`, no request; D-3 POST only from Create submit; red repro browser test |
| 2 Form with Create and Cancel, title required | D-3 structure, D-1 required title, D-4 keys |
| 3 Validation before creation, message next to the problem, keep input | D-3 client validation + inline errors, form never re-rendered, D-1 server 422 |
| 4 Leaving creates nothing | D-2 home render token, D-3 Cancel/`goHome()` / reload / back / close (no request, no storage, no history entry); browser tests |
| 5 No data survives | D-3 no draft storage; browser test reopens empty |
| 6 Successful creation as before | D-3 success `showList`, fallback `showHome`; service/tokens/defaults untouched |
| 7 Failure and retry | D-3 failure, D-1 transaction semantics, known limitation F6 documented |
| 8 Double submit | D-3 validate first, then `withPending(createBtn)` shared by click and Enter, readonly inputs, burst test rewritten |
| 9 Reopening section | follows from 1 and 4; browser test reloads and counts lists |
| 10 All entry points the same | D-2 single entry; deep link untouched (D9), existing test kept |
| 11 Leaving without Telegram controls | D-3 in-app Cancel, no BackButton dependency; D8 |
| 12 Same in Mini App and browser | one code path, no Telegram-only API; tests in plain Chromium without bridge |
| 13 Texts, accessibility, touch | D-4, D-5, D-6, 320 px browser test |
| 14 Other behaviour unchanged | PATCH model untouched (D-1), legacy untitled fallback kept, no cleanup (D4) |

### Docs to update (Step 8)

- `in-docs/spec.md` 4.2 (lines ~80-84: replace "automatically creates an empty personal list" and
  "title may be set later" with: creation is by an explicit form with a required title) and UC-01
  (line ~417: "enters the title and confirms").
- `in-docs/bot-scenarios.md:15`: row "Create wishlist" -> "Open the Mini App at the home screen, where
  creation starts."
- `doc/dev/miniapp.md`: the `api()` helper docs (it now also exposes the parsed error body as `err.body`); goal 1 (line ~12, rename from "Frictionless Creation"), section "Frictionless
  Wishlist Creation" (lines ~435-441): rewrite as "Wishlist creation form" (screen, fields, validation,
  keys `miniapp.create.*`, guard, failure/cancel behaviour, no draft); settings field list
  (line ~447) mention that the creation title is enforced server-side (1-255 after trim) while PATCH
  is not (follow-up); also `:335-337` ("Create-button scope" note says WISHENKA-296 will change the
  flow: rewrite as the new guard on the form's Create button), `:803-806` (home action list item 1:
  the button now opens the form and no longer submits `POST /api/wishlists` with `{}`), `:1578` (route
  table row "Creates an empty personal wishlist": requires `name`, 422 otherwise), `:237` (class
  mention stays valid), the guarded-controls list at `:331`, and a short note on the home render
  token and the `miniapp.create.*` keys.
- `doc/dev/wishlists.md:59` route list: `POST /api/wishlists` requires `name`, 422 on blank/over 255
  (and the `create_wishlist` description near line 591: the service itself still accepts any
  title; the HTTP layer validates).
- `doc/dev/testing.md`: entries for the three new modules; `:474-478` (item 7 says the create click
  sends `POST /api/wishlists` `{}`: rewrite) and `:681` (limitation note "re-check the create-button
  guard and A6 after WISHENKA-296": update, keep the WISHENKA-312 pointer).
- `doc/dev/architecture.md`: contains no creation text (grep for "creat" finds nothing relevant); no change.
- `specs/` is not contradicted: no change.

### Test strategy

**API (`tests/test_wishlist_create_validation_api.py`).** Cases of the Failing Repro section plus:
unauthenticated `POST {}` still 401 (auth before body); CSRF behaviour unchanged (cookie session
without header -> 403, nothing created); description/event/date accepted when present; unparseable
`event_date` -> 422; optional fields can be omitted; response `role == "owner"`, `status ==
"active"`, tokens present (requirement 6, unchanged); 422 `detail[0].loc == ["body", "name"]`; log
records of the request do not contain the submitted title (`caplog`, Step 6 reuses it).

**Node harness (`tests/test_wishlist_create_ui.py`, ru/en, `timeout(20)`).** Limited to what `makeEl`
supports (finding 0c): `click()` dispatches only `click` listeners, `querySelector` knows only
`button` and `.wishlist-section`, no `removeAttribute`/`classList`/`scrollIntoView`. Assertions made
here: home create click -> zero `POST /api/wishlists`, `h1 == t("miniapp.create.title")`, the form
tree has the four inputs with catalog labels (title label = `field_title`), Create (submit) and
Cancel (label = `miniapp.wishlist_settings.cancel`), no storage writes; the Cancel click renders home
(`h1 == t("miniapp.home.title")`) with no POST (the `h1.focus()` call is **not** asserted here: the fake
DOMs return null for `querySelector('h1')` and `focus` is a no-op; focus is asserted only in browser case 1
via `document.activeElement`); catalog parity of
`miniapp.create.*` and the `{max}` placeholder set. A module-local harness patch (same style as
`tests/test_wishlist_detail_ui.py:20-25`) lets the form's submit handler be invoked directly with a
fake event (`preventDefault` stub) and values preset on the inputs, to assert request bodies only:
blank title -> no POST; valid -> exactly one POST with the trimmed `name`, `null` for empty optionals;
a 500 stub -> form still in the tree. **Inline error text, `aria-invalid`, `aria-describedby`, error
focus and the 422 `loc` mapping are asserted in the browser tests**, not here, because the fake DOM
cannot represent them; the production code is nevertheless written so that those helpers use optional
calls and closure variables and cannot throw in the harness. `showCreate` sits before `async function
showHome(`, so `home_script_problems` (`tests/test_reservations_cabinet_ui.py:471-489`) does not scan
it; the home token lines inside showHome keep that test green (re-run).

**CDP browser (`tests/test_wishlist_create_browser.py`, ru/en, widths 320 and 412).** Uses
`open_miniapp` and an `API_PRELOAD`-style fetch wrapper for counting/holding (as
`tests/test_cross_screen_comfort_browser.py:90-112`):

0. Test mechanics: values are set through `page.evaluate` (assign `input.value` and dispatch an
   `input` event; `tests/browser_cdp.py` has no insert-text helper), buttons are clicked with
   `page.click`, Enter is real implicit submission: focus the title input, then `CdpPage.press_key("Enter")`
   (`tests/browser_cdp.py:406`); `requestSubmit()`/synthetic `keydown` are not used because they do not
   exercise implicit submission (cases 5 and 6 use `press_key`).
1. Open form, then leave by Cancel, by reload and by navigating to `/` again: count of `GET
   /api/wishlists` unchanged and zero create POSTs (requirement 1, 4, 9). `history.back()` is
   asserted only after an in-app `history.pushState` / second entry exists (in a fresh CDP tab with
   a single entry it is a no-op); the guarantee for back is "no request exists", asserted by the
   zero-POST counter. After Cancel `document.activeElement` is the home `<h1>`.
2. Partial fill (title typed) then Cancel and reload: no list; reopen form is empty (requirement 5).
3. Valid create: list opens (`#app .list-title` equals the typed title), Back shows it in "My
   wishlists" (requirement 6).
4. Invalid: blank and whitespace-only title and 256-char title: no POST, inline error text equals the
   catalog value, `aria-invalid="true"`, `document.activeElement` is the title input, other typed
   fields keep values, error accessible name/description via `Accessibility.getFullAXTree` or
   `aria-describedby` resolution; fixing the title clears the error and a submit succeeds. Also: a
   5-digit year in the date input (`20000-01-01T00:00`) -> date inline error, no POST, no exception
   (`window.onerror` counter stays 0), title value kept; a mocked 422 with `loc ["body","event_date"]`
   -> date error; with `loc ["body","name"]` -> title error; a mocked 422 with unknown `loc` -> the
   `create_failed` status. A blank title shows no "Creating..." status at any moment (status
   observer).
5. Burst: hold the response (`mode.create = 'hold'`), click Create three times, then press Enter in
   the title field twice, mix both: exactly one POST; Create/Cancel disabled and `aria-busy` while
   held; after release the list opens (replaces `test_create_wishlist_burst_sends_a_single_post`).
   Enter pressed while held adds no POST either.
6. Failure: `mode.create = '500'` -> `#status` equals `create_failed`, `data-kind == "error"`,
   `aria-live == "assertive"`, form and values still there, Create enabled and focused, a retry
   (mode back to real) creates exactly one list; `document.activeElement` is Create after the failure
   (replaces
   `test_create_wishlist_failure_is_announced_as_an_error`).
7. Layout: 320 px no horizontal overflow (`scrollWidth <= innerWidth`), all controls >= 44 px high,
   focus ring visible on the controls, 200-character unbroken title wraps; extend
   `assert_reachable` use at `tests/test_cross_screen_comfort_browser.py:966` with the create screen.
8. Deep link `?startapp=create`: home shown, create button focused, no form, no list (kept existing
   test `tests/test_home_overview_browser.py:527-538`).
9. Home staleness guard (new fetch-wrapper key `home` for `GET /api/wishlists`, mode `hold`):
   (a) open home (settled), click Create, click Cancel (home load A now held), click Create again
   during the held load, release: the page shows the form and **no** `.wishlist-section`, no stale
   "Loading" status; (b) click Create, hold, click Cancel (load A held), release A only after
   starting a second `showHome` through a second Create/Cancel round (load B): after releasing both
   exactly one set of sections (`.wishlist-section--owned` count 1). Also the post-creation fallback:
   force `GET /api/wishlists/<id>` to 500 after a successful create: the home is shown, the new list
   is under "My wishlists", `#status` equals `miniapp.list.load_failed`, `document.activeElement`
   is the home `<h1>`, and exactly one list was created.
10. Plain browser: all of the above run without a Telegram bridge (the CDP fixtures already do).

### Existing tests that need updating or may be affected

Must change (they assert click-time creation or post an empty/blank title):
- `tests/test_home_overview_ui.py:862-890` (`clickNavButtonIndex: 0` asserts `POST /api/wishlists` with
  body `{}`): rewrite to the new rule (no POST; form shown); also the harness stub at `:282` that
  answers `POST` with an untitled list (update to echo the body's `name`).
- `tests/test_cross_screen_comfort_browser.py:465-495` (burst test, docstring says "WISHENKA-296 may
  change this flow") and `:501-535` (failure test clicks `.home-create-btn` and expects the error):
  both rewritten against the form as in browser cases 5 and 6; `API_PRELOAD` can stay.
- `tests/test_wishlist_api.py` lines 33, 80, 186, 277, 282 post `json={}`: line 80 expects a 500 from a
  forced write failure (with `{}` it would now be 422 before the handler; use a valid name); 33,
  186, 277, 282 only need a list (use `{"name": "..."}`; 277/282 depend on token sequence, keep order);
  line 185 (unauthenticated `{}` -> 401) keeps its intent, change only if the auth/validation order
  makes it 422 (expected 401; verified at Step 3).
- `tests/test_wishlist_management_ui.py:80` posts `{}`: use a name.
- `tests/test_home_overview_browser.py:59` creates a deliberately **untitled** list through the API
  (`{"name": ""}`) to test the legacy fallback: it can no longer go through the API; seed it through
  the service/store layer (as the service-layer fixtures do) or create with a name and clear it with
  `PATCH` (PATCH still allows an empty name; confirm at Step 3).
Must stay green (re-run list): `tests/test_reservations_cabinet_ui.py` (`home_script_problems`, `:471-489`; it
constrains code inside showHome: no HTML injection, card URL required); all other `POST /api/wishlists` callers already pass a non-blank name
(`tests/conftest.py:276`, `tests/test_wish_items_crud_api.py`, `tests/test_wishlist_deleted_restore.py`,
`tests/test_personal_settings_browser.py:555,582,887`, `tests/test_history_screen_browser.py`,
`tests/browser_screens.py:205`, `tests/test_i18n_sync.py:417`, `tests/test_i18n_unit.py:311`,
`tests/test_reservation_actions_api.py:132`, `tests/test_wishlist_delete_*`); service-layer
`create_wishlist` fixtures are unaffected (service signature unchanged). Also re-run
`tests/test_home_overview_ui.py` (nav order and focus, create label at index 0),
`tests/test_bot_menu_miniapp_e2e_browser.py` (label only), `tests/test_i18n_unit.py:754-769` (source
still contains the home create key), catalog parity tests, `tests/test_wishlist_detail_*` (settings form
untouched), `tests/test_wishlist_delete_*` (zone untouched), `tests/test_wishlist_management_browser.py`.

### Risks

- **R-1 Spec reversal** (D1, D2) is a product decision taken autonomously; flagged for the product
  owner. The design is reversible: removing the required title only needs `WishlistCreateInput`
  to relax.
- **R-2 Lost-response duplicate** (F6): retry after a success whose response was lost (or a proxy
  502/504/timeout after a committed creation) can create a second list; documented, not solved (an idempotency key is a follow-up).
- **R-3 Code point vs UTF-16 mismatch**: client counts code points like Python; a combining or
  astral input cannot pass the client and fail the server; JS `trim()` vs Python `strip()` differ for
  a few Unicode spaces. The 422 `loc` mapping (D-1) is the safety net and keeps the typed values.
- **R-4 `novalidate` + custom errors** must be implemented for all engines identically; covered by
  browser tests in Chromium only (no other engines in the CI). The logic is plain DOM and does not
  use engine-specific bubbles.
- **R-5 Focus loss**: replacing `root` content drops the focused element; `showHome` never focuses
  its `<h1>` by itself, so focus is set explicitly (`goHome()`, `showCreate`), the first invalid
  field or Create after errors (after `withPending` returned, not inside it); covered by tests.
- **R-9 Home render token regression**: every `await` in `showHome` needs a staleness check; a
  missed one reintroduces late sections under the form. Covered by browser case 9 and by keeping
  all token checks in one place (after `Promise.all`, in `catch`, after the card `fetch` and after
  `cardResponse.text()`).
- **R-10 `api()` body exposure** (`err.body`) changes a shared helper; kept to a try/catch addition
  that cannot change thrown status or message.
- **R-6 Harness limits**: the Node fake DOM lacks several methods; the form is built with the
  available subset and errors are exercised in the browser tests (see D-3).
- **R-7 Overlap with other sprint tasks** touching `showHome`/`miniapp.js` (WISHENKA-312 re-checks the
  guard after this task): only the home handler body is replaced and one function added.
- **R-8 PATCH inconsistency**: after this task lists are created with title 1-255 but can be
  renamed to blank/any length through settings (out of scope, F4); candidate follow-up debt.

## Q&A

- **Client-only or server validation?** Both. The server rule is a creation-only model so PATCH is
  unaffected; no other production caller exists.
- **Why a separate screen and not a modal/inline home form?** A screen follows the app's navigation
  model (`root.replaceChildren`), has a trivial Cancel (`showHome`), needs no focus trap, and works
  the same in Telegram and in a browser.
- **Why `novalidate`?** One consistent, localized, announced message mechanism; native bubbles are
  not localized by the app and differ per WebView.
- **Why trim?** A whitespace-only title is "blank" (requirement 3); storing the trimmed value keeps
  lists tidy and client/server agree.
- **Why no draft?** Requirement 5 / D5.
- **Does the deep link open the form?** No (D9).
- **Idempotency key?** Out of scope (F6); the existing `nextIdempotencyKey()` helper is for other
  operations and is not wired to this route.
- **Open questions for the gate owner.** All resolved here by decision: (1) optional fields get no
  new length limits (follow-up candidate); (2) validation errors use `role="alert"` plus focus on
  the first invalid field (possible double announcement is accepted); (3) PATCH keeps accepting
  blank/any-length titles; (4) the untitled-list seed in `tests/test_home_overview_browser.py:59`
  moves to the service layer or PATCH. Product-owner confirmation of D1/D2 (spec reversal, required
  title) remains pending from Step 1.
