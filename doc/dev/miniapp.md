# Telegram Mini App Interface and Wishlist Management

## Overview

The Telegram Mini App (TMA) frontend and web layer provide a responsive, accessible interface
for managing personal and collaborative wishlists, administering members, and sharing gift links.

The Mini App runs inside the Telegram WebView and is served directly by FastAPI as a lightweight
server-rendered shell with progressive client-side enhancement. It operates in tandem with the
wishlists domain service and security middleware to satisfy four primary goals:

1. **Explicit Creation**: Create a wishlist only after the owner confirms a short creation form
   with a required title; leaving the form creates nothing (WISHENKA-296, replaces the former
   automatic empty list).
2. **Contextual Settings Management**: Let owners and administrators configure list metadata
   (title, description, event title, event date) with explicit persistence and cancellation.
3. **Collaborative Member Administration**: Provide distinct administrative controls for
   inviting collaborators, promoting/demoting administrators, and removing members.
4. **Secure Link Sharing**: Clearly separate public gift-selection links (`startapp=w_<token>`)
   from collaborator invitation links (`startapp=i_<token>`), protecting the Surprise Invariant
   and preventing accidental elevation of privileges.

---

## Architecture & Components

```
+---------------------------------------------------------------------------------+
|                           Telegram Client (WebView)                             |
|  - window.Telegram.WebApp (initData, openTelegramLink, shareUrl)                |
|  - Accessible HTML shell + static miniapp.js / miniapp.css                      |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
|                       BrowserSecurityMiddleware                                 |
|  - Enforces Origin header matches WISHENKA_APPLICATION_ORIGIN                   |
|  - Validates session-bound CSRF token (X-CSRF-Token) on state-changing requests |
|  - Adds Referrer-Policy: no-referrer, nosniff, and Cache-Control: no-store      |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
|                         FastAPI Web Endpoints                                   |
|  - GET /                               Mini App HTML shell with strict CSP      |
|  - GET /api/auth/csrf                  Session-bound CSRF token provider        |
|  - GET, PATCH /api/wishlists/{id}      Wishlist details & metadata settings     |
|  - /api/wishlists/{id}/members         Member administration & role management  |
|  - /api/wishlists/{id}/invite/reset    Collaborator invite token rotation       |
|  - /api/invitations/preview, accept    Collaborator onboarding flow             |
|  - GET, POST, DELETE /api/favorites    Favorites management & role badges       |
|  - GET, POST, DELETE /api/history      Viewing history tracking (20 bound)      |
|  - /web/wishlists/{id}/items/*         HTMX Quick Add, Preview & Edit Modal UI  |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
|                  WishlistService & SQLite Transactional Store                   |
|  - Contextual RBAC / ABAC policies (WishlistAccessPolicy)                       |
|  - Surprise Invariant projection filters                                        |
|  - Transactional serialization via BEGIN IMMEDIATE in SQLite WAL mode           |
+---------------------------------------------------------------------------------+
```

### Components

- **HTML Shell (`GET /`)**: Defined in
  [`wishenka.web.routes.miniapp`](../../wishenka/web/routes/miniapp.py). Renders an accessible
  skeleton (`#app`, `#status` live region) configured with `data-bot`, `data-miniapp`, and
  `data-locale` attributes, and embeds the bilingual `nav.*`/`miniapp.*` catalog in
  `<script id="miniapp-i18n" type="application/json">` (see [i18n.md](i18n.md)).
  Applies strict Content-Security-Policy (CSP) headers restricting frames to Telegram.
- **Client Script (`static/miniapp.js`)**: Pure JavaScript application. Parses navigation
  parameters (`startapp`, hash/query), manages views, localizes all UI screens via `t()`,
  `activeLocale()`, `roleLabel()`, and `formatDateTime()` backed by `#miniapp-i18n`, and performs
  API calls with session cookies and CSRF headers. Uses safe DOM manipulation (`textContent`)
  rather than HTML string interpolation to prevent Cross-Site Scripting (XSS).
- **Shared Stylesheet (`static/miniapp.css`)**: Single CSS entrypoint loaded by both the Mini
  App shell (`GET /`) and `base.html` server-rendered views (including `settings.html` and
  `invite_preview.html`). Owns the shared light Wishenka visual palette, semantic button hierarchy,
  mobile touch targets, `:focus-visible` outlines, and the scoped Telegram theme boundary for
  `.receipt-sheet` and `.modal-sheet`. See
  [Shared Visual Identity and Palette Tokens](#shared-visual-identity-and-palette-tokens).
- **Wishlist Page Script (`static/wishlist.js`)**: Second static script, loaded by `base.html` on
  server-rendered wishlist pages (not by the Mini App shell, which loads only `miniapp.js`).
  Implements the card toggle and drag-and-drop reorder. See
  [9.8.1](#981-client-script-staticwishlistjs-wishenka-108).
- **Security Middleware (`BrowserSecurityMiddleware`)**: Defined in
  [`wishenka.web.security`](../../wishenka/web/security.py). Protects cookie-authenticated mutation
  requests against Cross-Site Request Forgery (CSRF) and Cross-Origin attacks.
- **Wishlist Routes (`wishenka.web.routes.wishlists`)**: Implements authenticated management APIs
  and public read projections.
- **HTMX Wish Item UI Routes (`wishenka.web.routes.items_ui`)**: Defined in
  [`wishenka/web/routes/items_ui.py`](../../wishenka/web/routes/items_ui.py). Serves server-rendered
  Jinja2 + HTMX views and partials for the wishlist detail page, universal quick-add bar, live URL
  preview card, detailed item creation/editing bottom-sheet modal, Reduction Lock enforcement, and
  safe item archiving/restoration.

---

## Presentation tokens and currency defaults

`wishenka/currency.py` defines `DEFAULT_CURRENCY` (`RUB`) and the ordered
`CURRENCY_OPTIONS` for the edit form: RUB, USD, EUR, KZT and BYN. Import the default for
new Python fallback paths instead of repeating it. `wishenka/web/templates.py` registers both
constants as Jinja globals, so item, preview, archive and edit partials can use them in direct
and out-of-band renders. Existing explicit currencies remain unchanged; the options list does
not impose a new validation rule. Historical migration defaults are intentionally unchanged.

`static/miniapp.css` owns semantic dimensions, layer (`--layer-receipt: 100` above
`--layer-quick-add: 40`), `--touch-target` (`44px`, enforced on `.receipt-sheet .btn-step` and
`.receipt-sheet .quantity-control input`), and receipt color tokens. The receipt sheet,
nested form and select use Telegram's `--tg-theme-bg-color` and `--tg-theme-text-color` as a
pair, with light fallbacks outside Telegram. The confirm button uses fixed green and white,
and the notice has its own explicit foreground/background pair. CSS responds to changed theme variables without a separate dark-mode switch. The
`STALE_RELOAD_DELAY_MS` constant in `static/wishlist.js` remains 800 ms; it controls reload
following a stale-order refusal.

To investigate unreadable receipt text, inspect the computed foreground and background on the
sheet, nested form and controls, and check that Telegram supplies a coherent pair of theme
variables. Representative light, dark and fallback palettes are covered by
`tests/test_receipt_theme_browser.py`; arbitrary custom palettes are not guaranteed to have
sufficient contrast. `tests/test_currency_defaults.py` checks defaults and explicit currencies
across views and DTO boundaries. These constants and presentation tokens have no environment
settings; change the source definitions when their defaults or choices must change.

### Shared Visual Identity and Palette Tokens

[`wishenka/web/static/miniapp.css`](../../wishenka/web/static/miniapp.css) establishes the light
Wishenka design system shared across the Mini App SPA (`#app`) and server-rendered `base.html`
pages (`.settings-page`, wishlist views, and `invite_preview.html`):

- **Palette and layout tokens (`:root`)**:
  - Light shell palette (`WISHENKA-288`): `--canvas` (`#fff7f9`, page background), `--surface`
    (`#ffffff`, card and field surface), `--ink` (`#351326`, primary plum foreground and headings),
    `--muted` (`#695663`, `.history-time`, `.section-subtitle`, and `.empty-hint`), `--accent`
    (`#8c2551`, primary fill, button border, `accent-color` of plain checkboxes, and the on
    track of the settings switches), `--accent-dark`
    (`#6f173f`, links, secondary button labels, and primary `:hover`), `--danger` (`#a61335`,
    `.btn-danger` border and label), and `--focus` (`#71319a`, `:focus-visible` outline).
  - Additive Home surface and border tokens (`WISHENKA-289`): `--surface-subtle` (`#fffafd`,
    card and empty-state surface), `--border-subtle` (`#edd8e0`, section, card, and reservations
    card borders), `--accent-soft` (`#fff0f4`, `.section-count`, `.wishlist-card-open`, and
    `.reservations-card:hover` fill), and `--muted-border` (`#d5c1ca`, dashed `.deleted-section`
    and `.wishlist-card-remove` borders).
  - Structural tokens: `--touch-target` (`44px`), `--content-width` (`42rem`), `--receipt-height`
    (`90vh`), `--layer-drag` (`10`), `--layer-quick-add` (`40`), `--layer-receipt` (`100`), and
    `--layer-modal` (`100`).
- **Surfaces, typography, and mobile spacing**:
  - `:root` sets `font: 100% system-ui, sans-serif; color: var(--ink); background: var(--canvas);`
    and `body` centers `--content-width` with `1rem` padding.
  - `section, form` render light `--surface` cards (`border-radius: 1rem`, soft plum shadow
    `0 3px 12px rgba(99, 33, 60, .08)`). `.birthdate-form` resets `margin: 0; padding: 0;
    box-shadow: none;`, whereas `.quick-add-form` sets `margin: 0 auto; padding: 0; max-width:
    var(--content-width); box-shadow: none;` to avoid nested card shadows.
  - `h1, h2, h3` use `var(--ink)`, `line-height: 1.2`, and `overflow-wrap: anywhere` so longer
    Russian and English headings wrap cleanly on mobile (`h1` uses
    `clamp(1.75rem, 6vw, 2.25rem)`).
  - `.top-nav`, `.locale-options`, and `.wishlist-card, .history-item` use `display: flex;
    flex-wrap: wrap;` with `.5rem` or `.25rem` gaps so action buttons, badges, and metadata wrap
    cleanly on narrow viewports.
  - Unscoped `button, input, a:where(.btn, .btn-primary, .btn-danger)` (`min-height:
    var(--touch-target)`, `box-sizing: border-box`, `font: inherit`, `margin: .25rem`) and
    unscoped `input` / `input:not([type="checkbox"])` (`width: 100%; max-width: 100%`,
    `border: 1px solid #aa8998`, `border-radius: .5rem`, `padding: .5rem` on non-checkboxes) do
    not set `background: var(--surface)` or `color: var(--ink)`, so non-checkbox `<input>`
    elements in `.modal-sheet` keep browser defaults. Only
    `:where(body) :is(select, textarea)` sets `background: var(--surface);
    color: var(--ink);` alongside `box-sizing: border-box`, `max-width: 100%`,
    `min-height: var(--touch-target)`, `font: inherit`, `border: 1px solid #aa8998`,
    `border-radius: .5rem`, and `padding: .5rem`.
- **Semantic action hierarchy, states, and 44 px link-button targets**:
  - **Base and secondary controls (`button, a:where(.btn, .btn-primary, .btn-danger)`)**: share
    `box-sizing: border-box`, `min-height: var(--touch-target)` (`44px`), `margin: .25rem`,
    `padding: .5rem .85rem`, `border: 1px solid var(--accent)`, `border-radius: .7rem`,
    `background: var(--surface)`, `color: var(--accent-dark)`, and `font-weight: 600`. Link
    buttons (`a:where(.btn, .btn-primary, .btn-danger)`) also enforce `display: inline-flex;
    align-items: center; justify-content: center; text-decoration: none;`, matching `<button>`
    geometry and touch targets. Enabled hover applies `#fff0f4` via
    `:where(button, a.btn, a.btn-primary, a.btn-danger):hover:not(:disabled)`. `.settings-link,
    .back-link` share `display: inline-flex; align-items: center;
    min-height: var(--touch-target); border: 1px solid var(--accent); border-radius: .7rem;
    color: var(--accent-dark); font-weight: 600; text-decoration: none;`, while using
    `padding: .25rem .75rem` (not `.5rem .85rem`) and omitting `box-sizing: border-box`,
    `justify-content: center`, `margin: .25rem`, `background: var(--surface)`, and the `#fff0f4`
    hover fill.
  - **Primary and selected state (`.btn-primary, .locale-option[aria-pressed="true"]`)**: filled
    `var(--accent)` background and border with `white` text, darkening to `var(--accent-dark)` on
    hover. Active language buttons in `settings.html` are driven by `[aria-pressed="true"]`
    (replacing the legacy `.locale-option.is-active` CSS rule).
  - **Destructive actions (`.btn-danger`)**: `border-color: var(--danger); color: var(--danger);`
    with `#fff0f1` hover on `:hover:not(:disabled)`.
  - **Disabled state (`button:disabled`)**: `background: #ece6e9; border-color: #a7979e; color:
    #5d5056; cursor: not-allowed;` (`.btn-move-up:disabled, .btn-move-down:disabled` also keep
    `opacity: .4`, and `.btn-receipt-confirm:disabled` keeps `opacity: .6; cursor: progress`).
  - **Keyboard focus (`:focus-visible`)**: `outline: 3px solid var(--focus); outline-offset: 3px;`.

### Scoped Telegram Theme Boundary

The Mini App shell (`#app`) and settings/SSR shells (`.settings-page` / `body`) stay locked to
the light Wishenka palette. Telegram theme variables are scoped strictly to overlay sheets and
the fixed quick-add bar so dark Telegram themes never mix with light-shell foregrounds:

- **Paired sheet variables**: `.receipt-sheet` and `.modal-sheet` bind
  `background: var(--receipt-bg); color: var(--receipt-text);` (defined as
  `--receipt-bg: var(--tg-theme-bg-color, #ffffff)` and
  `--receipt-text: var(--tg-theme-text-color, #29222b)`, with
  `--receipt-error: var(--receipt-text)`). `.quick-add-container` retains
  `background: var(--tg-theme-bg-color, #ffffff)` around `.quick-add-form`
  (`background: var(--surface)`).
- **Focus ring contrast (`--focus: var(--receipt-text)`)**: both `.receipt-sheet` and
  `.modal-sheet` override `--focus` to `var(--receipt-text)` so global `:focus-visible` outlines
  keep contrast against `--receipt-bg` in both light and dark Telegram palettes.
- **Heading foreground inheritance**: `.receipt-sheet :is(h1, h2, h3), .modal-sheet :is(h1, h2,
  h3) { color: inherit; }` (plus `.modal-header h2 { color: inherit; }`, covering
  `partials/share_modal.html` where `.modal-header` sits outside `.modal-sheet`) ensures sheet
  headings inherit `--receipt-text` instead of light-shell `var(--ink)`.
- **Nested form and control scoping**: `.receipt-sheet form`, `.receipt-sheet select`,
  `.receipt-sheet .quantity-control input`, `.modal-sheet select`, and `.modal-sheet textarea`
  explicitly use `--receipt-bg` and `--receipt-text` (`.modal-sheet form` uses `background:
  transparent; color: inherit; box-shadow: none;`). Light `select`/`textarea` styling is scoped
  to `:where(body) :is(select, textarea)`. That selector has zero specificity, so the
  `.modal-sheet select` and `.modal-sheet textarea` rules (receipt colors) always override it.
  Non-checkbox `<input>` elements in `.modal-sheet` (`partials/item_edit_modal.html`) keep
  default field colors.
- **Close, cancel, and modal action contrast**: `.receipt-sheet .btn-modal-close`,
  `.modal-sheet .btn-modal-close`, and `.modal-sheet .btn-cancel` set
  `background: var(--receipt-bg); color: var(--receipt-text);` (including
  `:hover:not(:disabled)`), preventing global `button` / `#fff0f4` rules from breaking contrast
  on dark Telegram themes. `.btn-save` uses `var(--accent)` / `var(--accent-dark)` with `#fff`
  text; `.btn-confirm-archive` and `.btn-archive-item` use `#b91c1c` / `#991b1b`.

### Semantic Button Class Contracts

- **`wishenka/web/static/miniapp.js`**:
  - `button(text, handler, className = '')` applies `className` when non-empty while preserving
    `type="button"`, `textContent`, click handlers, function boundaries, and `#status` live updates.
  - `'btn-primary'`: `showHome` create button (`'btn-primary home-create-btn'`), `sharePanel`
    Telegram share button, `settingsForm` save submit (`node('button', ..., {type: 'submit',
    class: 'btn-primary'})`), `publicView` reserve button, and `invitationView` accept button.
  - `'btn-danger'`: `showHistory` clear-history button and `memberControls` remove-member button.
  - Scoped Home action classes (`WISHENKA-289`): `'home-nav-action'` on `showHome` Viewing history
    button (paired with `a.settings-link.home-nav-action`), `'wishlist-card-open'` on
    `wishlistCard` primary open button, `'wishlist-card-remove'` on Favorites subordinate bookmark
    removal button, and `'wishlist-card-restore'` on Recently deleted restore button.
  - Default secondary (`className = ''`): Back, Copy link, Cancel, role toggle, revoke/replace
    link buttons, and detail-screen favorite toggle actions.
- **`wishenka/web/templates/settings.html`**:
  - `#birthdate-form button[type="submit"]` uses `class="btn-primary"` (distinct from secondary
    `#birthdate-clear-btn`).
  - `#delete-account-start-btn` and `#delete-account-confirm-btn` use `class="btn-danger"`
    (distinct from secondary `#delete-account-cancel-btn`).
  - `.locale-option` carries `aria-pressed="true"|"false"` (plus `is-active` when active); CSS
    styles the selected state via `.locale-option[aria-pressed="true"]`.
  - `<a href="/" class="back-link">` renders as a 44 px return link matching `.settings-link`.
- **`wishenka/web/templates/partials/member_list.html`**:
  - Owner member-removal `<button>` uses `class="btn-delete btn-danger text-xs text-red-600
    font-medium px-2 py-1 border rounded"`, keeping `.btn-delete` and legacy uncompiled Tailwind
    classes intact alongside `btn-danger` (`base.html` loads only `/static/miniapp.css` with no
    Tailwind build).
- **Other template semantic hooks**:
  - `wishenka/web/templates/invite_preview.html` uses `a.btn.btn-primary` (error return link) and
    `button.btn.btn-primary` (join submit), receiving shared `44px` button geometry.
  - `wishenka/web/templates/partials/item_quick_add.html` uses `class="btn-secondary text-sm"` on
    `#btn-quick-details` (styled by base `button` rules; no separate `.btn-secondary` CSS rule)
    and `class="btn-primary text-sm font-semibold"` on `#btn-quick-add`.

### Visual Identity Browser Verification

`tests/test_visual_identity_browser.py` (`pytestmark = [pytest.mark.timeout(45),
pytest.mark.browser]`) exercises real offline Chromium rendering at a `412x800` mobile viewport
using the shared CDP harness (`tests/browser_cdp.py`, `tests/browser_helpers.py`,
`tests/conftest.py`):

- Verifies coherent light `--canvas` and distinguishable `--surface` sections across `/` and
  `/settings`, primary vs secondary button distinction on home `.top-nav`, primary/secondary/danger/
  disabled/selected-locale/focus-visible states on `/settings`, light and dark Telegram theme
  `>= 4.5` contrast for `.modal-sheet` / `.receipt-sheet` headings and `:focus-visible` rings,
  and `>= 44x44` px touch-target geometry on `invite_preview.html` `a.btn.btn-primary`.
- Complements `tests/test_receipt_theme_browser.py` and
  `tests/test_receipt_accessibility_browser.py`; module details and run command are in
  [testing.md](testing.md#тесты-единого-визуального-стиля-wishenka-288).

### Cross-Screen Comfort and Reliability Layer (WISHENKA-294)

A shared layer in [`miniapp.css`](../../wishenka/web/static/miniapp.css), `miniapp.js`, `app.js` and
`base.html` keeps every key screen usable on a phone (320-412 px, RU and EN, long text) and gives
each action visible pending, success and error feedback. It adds no endpoint.

#### Layout and Touch Rules (`miniapp.css`)

- **Root font**: `:root` uses `font: 100% system-ui, sans-serif` (no `px`, no line-height), so the
  user's text-size setting scales every `rem` value. `body` sets `overflow-wrap: anywhere`;
  `:where(img, svg, video)` and `.badge` have `max-width: 100%`.
- **44px fields**: the field rule is `:where(body) :is(select, textarea)` (was `#app` and
  `.settings-page` only), so server-rendered selects (for example the giver select) get
  `min-height: var(--touch-target)`. `:where(summary)` gets the same minimum height.
- **Buttons from links**: the store link (`item_card.html`) and "Go to wish"
  (`reservations_list.html`) carry `class="btn"` to get the shared 44px geometry.
- **Quick-add row**: `.quick-add-row` wraps (`flex-wrap`); the input has `flex: 1 1 100%` below
  480 px (at least `min(10rem, 100%)` wide) and `flex: 1 1 10rem` above it.
- **Bar clearance**: `main:has(#quick-add-bar)` has
  `padding-bottom: max(var(--quick-add-clearance), 9rem)`. The token defaults to
  `calc(7.5rem + env(safe-area-inset-bottom, 0px))`; `trackQuickAddClearance()` in `app.js` sets it
  to `bar.offsetHeight + 16` px through a `ResizeObserver`, so the last card stays above the bar
  when the bar wraps or shows a preview. `:has()` needs Chromium 105+ (follow-up WISHENKA-309).

#### Status and Feedback Regions

- **`#status`** (Mini App page, `routes/miniapp.py`) and **`#feedback`** (`base.html`, first child
  of `<body>`, `role="alert" aria-live="assertive"`, hidden while empty) are `position: sticky;
  top: 0` under `--layer-status: 30`, so a message written while the user is lower on a long page
  stays visible (it was off screen before).
- `data-kind` is `pending`, `success` or `error`; CSS adds a leading icon and colors
  (`success` uses `--notice-bg`/`--notice-text`, `error` uses `--danger`). Absent `data-kind` is a
  neutral message.
- **`status(message, kind = '')`** (`miniapp.js`) sets text and `data-kind` (unknown kinds and an
  empty message clear it) and `aria-live`: `assertive` for `error`, `polite` otherwise. Every
  failure message in the Mini App passes `'error'`, loads pass `'pending'`, and confirmations pass
  `'success'`.

#### Pending Guard in the Mini App (`withPending`)

- **`withPending(control, action, message = t('nav.working'))`**: ignores a second call while the
  control is busy (a `WeakSet`, so a burst of taps runs `action` once). While it runs, the control
  is `disabled`, has `aria-busy="true"` and the class `is-pending` (`cursor: progress`), and
  `#status` shows `message` as `pending`. The control state (`disabled`, `aria-busy`,
  `is-pending`) is undone in `finally`; `#status` keeps the pending text until `action` replaces
  it with its own success or error text.
- **`pending(action, message)`** adapts it for `button()`, whose click handler now receives
  `(event, element)`.
- **Guarded controls**: create wishlist (the creation form's Create button), remove favorite
  (home), restore deleted wishlist (home,
  message `miniapp.deleted.restoring`), restore archived wishlist, favorite toggle, member
  remove, role change, revoke invite, reset public link. History clearing and the settings form
  keep their own existing pending state.
- **Create-button scope**: since WISHENKA-296 the home button only opens the creation form; the
  guarded control is the form's own Create button (`withPending(createBtn, send, ...)`,
  `miniapp.js:533`), shared by taps and Enter. Assertion A6 (a burst sends exactly one
  `POST /api/wishlists`) is carried by `test_enter_and_tap_burst_sends_exactly_one_post` and
  `test_real_tap_burst_sends_exactly_one_post` in `tests/test_wishlist_create_form_browser.py`
  and by `test_create_wishlist_burst_sends_a_single_post` in
  `tests/test_cross_screen_comfort_browser.py`. The remaining re-check and the unprotected retry
  after a lost response are tracked in WISHENKA-312 and WISHENKA-322.

#### htmx Pending and Failure Feedback (`app.js`, `base.html`)

- `htmx:beforeRequest` sets `aria-busy="true"` on the triggering element and, for non-GET
  requests (not the quick-add preview input), disables its submit buttons (or the element itself
  if it is a button) and clears `#feedback`. `htmx:afterRequest` restores them (`releasePending`).
- `htmx:sendError`, `htmx:timeout` and `htmx:responseError` fill `#feedback` with
  `web.common.request_failed` (from `data-i18n-request-failed` on `<body>`; English fallback in
  the script) and `data-kind="error"`.
- **Left alone**: reservation requests, `.receipt-sheet` and answers marked `X-Reorder-Refusal` or
  `X-Receipt-Refusal` keep their own messages; GET requests report no failure.
- The same pending/feedback logic exists in `miniapp.js` and `app.js` (WISHENKA-310).

#### Unavailable Page (`wishenka/web/unavailable.py`)

`install_unavailable_page(app)` (called in `create_app` after the routers) overrides the
Starlette `HTTPException` handler. It renders `templates/unavailable.html` only when all hold:

- method is `GET` and status is 404 or 401;
- the path matches `PAGE_PATHS` exactly: `/share/<token>`, `/web/wishlists/<id>`,
  `/web/reservations` (sub-paths, `/api/...` and unknown routes stay JSON);
- no `HX-Request` header;
- `prefers_html(Accept)`: `text/html` is listed with q > 0 and ranks above `application/json`
  (higher q, or equal q and earlier position). A missing header, `*/*` and JSON stay JSON.

Everything else is delegated to FastAPI's `http_exception_handler` (JSON unchanged).

- **Response**: the original status code and `headers=exc.headers`, so a 401 page keeps
  `WWW-Authenticate`. Body: `h1` (`web.unavailable.heading`), a paragraph (`web.unavailable.auth`
  for 401, `web.unavailable.description` for 404) and `a.unavailable-home` to `/`
  (`web.invite.go_home`, 44px button).
- **Locale**: `get_request_locale` (profile, then `?lang`, then `Accept-Language`;
  see [i18n.md](i18n.md#locale-resolution--precedence)); on any exception it logs a WARNING
  and falls back to `resolve_accept_language`. The locale is stored in `request.state.locale`.
- **Privacy**: the page is static text. It never shows the token, id, title or the reason, so a
  missing and a deleted wishlist look identical (surprise invariant).
- **Log**: one INFO event `unavailable_page_rendered` with `status_code` (401/404), `route_kind`
  (`share`, `wishlist`, `reservations`) and `locale`; no token or id. Count it by
  `extra.event`.
- **Limits**: `PAGE_PATHS` uses `$` with `.match` (a trailing `\n` also matches), and the response
  does not set `Vary: Accept` (WISHENKA-308).

Tests and the unavailable-page log test: see the WISHENKA-294 section of
[testing.md](testing.md#сквозные-тесты-комфорта-и-надёжности-экранов-wishenka-294).

---

## Security & CSRF Architecture

Because the Mini App operates in an embedded browser environment using cookie authentication
(`SameSite=None`), defense-in-depth protections prevent cross-site request forgery and data leakage.

### 1. Origin Verification

For unsafe HTTP methods (`POST`, `PATCH`, `DELETE`, `PUT`) using cookie sessions and for
`/api/auth/telegram`, `BrowserSecurityMiddleware` checks that the incoming `Origin` header
strictly matches the configured `application_origin`:

```python
if unsafe and request.url.path == "/api/auth/telegram":
    if origin != settings.application_origin:
        return JSONResponse({"detail": "Invalid origin"}, status_code=403)
```

Requests with missing or mismatched `Origin` headers are rejected with `403 Forbidden`.

### 2. Session-Bound CSRF Tokens

CSRF tokens are cryptographically derived from the user's active session cookie using HMAC-SHA256:

```text
token = HMAC-SHA256(csrf_secret_key, "wishenka-csrf-v1:" + session_cookie)
```

- The client retrieves a token via `GET /api/auth/csrf`.
- The token is sent in the `X-CSRF-Token` HTTP header on all mutating requests.
- The middleware computes the expected token for the current session and compares them in constant
  time (`hmac.compare_digest`).
- Tokens cannot be reused across different user sessions or stolen across origins.

### 3. Capability Token Redaction

Sharing tokens (`public_token`) and collaborator invitation tokens (`invite_token`) are bearer
capabilities. The application strictly adheres to the following token safety rules:

- **Header Delivery for Invites**: Invitation verification and acceptance use the `X-Invite-Token`
  request header instead of embedding tokens in API query strings.
- **Log Sanitization**: Raw token values are never written to application logs, audit events, or
  storage traces. Audit records capture only entity IDs (`wishlist_id`, `actor_id`).
- **HTTP Headers**: All responses include `Referrer-Policy: no-referrer`, preventing tokens in
  deep-link URLs from leaking to external websites.

---

## User Workflows & Management Views

### 1. Wishlist Creation

- **Trigger**: the home button "Create wishlist" (`home-create-btn`) opens the creation form
  (`showCreate`, `miniapp.js:378`). The button sends no request. The bot menu item "Create
  wishlist" and the deep link `startapp=create` open the home screen, where `create` only focuses
  this button (`miniapp.js:1158-1160`); nothing is created by them.
- **API Call**: `POST /api/wishlists` with `name` (required), `description`, `event_title`,
  `event_date`, sent only after the user confirms the form with a valid title.
- **Behavior**: the server creates an active personal wishlist with generated tokens and the
  trimmed title; a missing or invalid title is rejected with `422` and nothing is created.
- **UI State**: on success the client opens the new wishlist (`showList`) with the add-item entry
  point. Leaving the form (Cancel, closing the Mini App, navigating away) creates nothing.

Full description: [Wishlist Creation Form](#wishlist-creation-form-wishenka-296).

### 2. Wishlist Settings Management

- **Permissions**: Available only to `Owner` and `Admin` roles.
- **Fields**:
  - `name`: List title (string, 1-255 characters).
  - `description`: Optional text notes.
  - `event_title`: Optional event name (e.g., "День рождения").
  - `event_date`: Optional ISO-8601 UTC timestamp.
- **Nullability**: Sending `null` or empty values clears optional event fields, allowing the list
  to remain ongoing without an event.
- **Client Handling**:
  - The form is pre-populated with current settings from `GET /api/wishlists/{id}`.
  - Submitting sends `PATCH /api/wishlists/{id}` with the updated fields and CSRF header.
  - Cancelling reloads the detail from `GET /api/wishlists/{id}` without sending a settings PATCH.
    The best-effort history recording in `showList` still runs.
  - If a save fails, user inputs are preserved in the form along with an accessible error message.
  - A failed reload after a successful save reports that the save succeeded but refresh failed.
    A failed reload after cancel retains the loading error instead of claiming cancellation.

#### Wishlist Delete Zone (WISHENKA-295)

The owner of an `active` list can delete it from the list settings. The zone is rendered by
`deleteWishlistControls(list)` (`wishenka/web/static/miniapp.js:579`) and appended to the
`.list-settings-section` right after the settings form (`:831-832`), so it sits outside the `<form>`
and never submits with it. API contract and events:
[wishlists.md](wishlists.md#owner-delete-route-delete-apiwishlistsid).

- **Visibility rule**: `deleteWishlistControls` returns `null` (nothing rendered) unless
  `list.role === 'owner'` and `Number(root.dataset.retentionDays)` is a positive integer
  (`:580-582`). The settings section itself exists only for `owner`/`admin` of an `active` list
  (`:824-826`), so admins and members never see the zone, and a missing or invalid
  `data-retention-days` hides it instead of promising a wrong number of days.
- **Retention source**: `GET /` writes `data-retention-days="{int}"` on `<main id="app">` from
  `settings.wishlist_retention_days` (`wishenka/web/routes/miniapp.py:24,49`; default `30`). The
  texts use this value before the call; after a `200` the success text uses
  `result.retention_days ?? days` (`:644`). A stale cached shell can show an outdated number
  (WISHENKA-316).
- **Markup**: `div.wishlist-delete-zone` with `h3.wishlist-delete-heading`
  (`miniapp.wishlist_delete.heading`), `p.settings-field-hint` (`hint`) and the trigger
  `button.wishlist-delete-open` (`open`, "Delete wishlist...").
- **Confirmation panel**: the trigger is replaced in place (`openBtn.replaceWith(panel)`, `:621`)
  by `div.history-confirm.wishlist-delete-confirm[role="group"]` with `aria-labelledby`
  `wishlist-delete-title-{id}` and `aria-describedby` `wishlist-delete-body-{id}`. The panel
  re-uses the `history-confirm*` classes of the history screen: `p.history-confirm-title` (the
  exact list title as text, `confirm_title`; an empty name falls back to
  `miniapp.common.untitled_wishlist`; the title is set through text, never parsed as HTML), the
  body with three `p.empty-hint` (`consequences`, `restore_promise`, `purge_promise`, both
  promises with `{days}`), and `div.history-confirm-actions.wishlist-delete-actions` holding
  `button.history-confirm-cancel` (`cancel`) first and
  `button.history-confirm-yes.btn-danger` (`confirm`, "Yes, delete wishlist") second.
- **Focus**: opening focuses Cancel, never the destructive button. Cancel and Escape inside the
  panel (`closeConfirm`, `:624-629`) send nothing, remove any error, put the trigger back and
  focus it. They do nothing while a request is pending (`deleting`).
- **Pending**: the confirm button runs through `pending(..., miniapp.wishlist_delete.pending)`
  (`withPending`: `disabled`, `aria-busy="true"`, `.is-pending`, polite `#status`), so a double
  click or Enter sends one `DELETE`. Cancel is disabled while the request runs.
- **Success (`200`)**: `await showHome()`, then `#status` shows `done` (`{title}`, `{days}`) with
  kind `success` and focus moves to the home `<h1>` (`:642-646`). `showHome()` now renders that
  heading with `tabindex="-1"` (`:370`) so it can take focus, as the history heading does (`:340`).
  The list is then under "Recently deleted" (see
  [Recently Deleted Wishlists](#recently-deleted-wishlists-owner-restore)).
- **Failure**: any rejected request except `410` (404, 409, 5xx, network) clears the status line,
  keeps the panel open, inserts `p.history-error.wishlist-delete-error[role="alert"]` with
  `failed` before the buttons, re-enables the confirm button and focuses it
  (`:649-658`). The text is the same for every status: it never says why, so no existence or
  reservation detail leaks.
- **`410` (window expired)**: the code calls `showHome()` first, which re-renders the whole
  screen, then sets the error status `failed` (`:651`). The code after that still writes into the
  now detached panel (`failure` alert, `yesBtn.focus()`), so the alert is not announced and
  keyboard focus falls to `body`; the visible message comes only from `#status`. This is a known
  defect, fixed in WISHENKA-317; do not document or rely on a focus target for this path.
- **CSS** (`wishenka/web/static/miniapp.css:282-290`): `#app .wishlist-delete-zone` (top border
  `--border-subtle`, `min-width: 0`, `overflow-wrap: anywhere`), `.wishlist-delete-heading`,
  `#app button.wishlist-delete-open` (transparent, `--danger` border and text, wraps long text).
  The panel itself is styled by the existing `.history-confirm*` rules and `.btn-danger`; there is
  no separate `.wishlist-delete-confirm` rule (removed as a duplicate in Step 5). Hooks used by
  tests: `.wishlist-delete-zone`, `-open`, `-confirm`, `-actions`, `-error`,
  `.history-confirm-cancel`, `.history-confirm-yes`.
- **Known accessibility smell**: "Cancel" appears twice on the owner list screen
  (`miniapp.wishlist_settings.cancel` and `miniapp.wishlist_delete.cancel`) with the same visible
  text; tests select by class (WISHENKA-317).
- **Secrecy rules for texts**: the delete texts never name a reservation count, state or person,
  never promise immediate removal, and are identical for lists with and without reservations
  (`tests/test_wishlist_delete_browser.py::test_texts_are_identical_for_lists_with_and_without_reservations`).
  Reservations may be mentioned only in `consequences` and `restore_promise`, in fixed clauses;
  see [i18n.md](i18n.md#wishlist-delete-texts-wishenka-295).

### Wishlist Creation Form (WISHENKA-296)

Reverses the former rule "a wishlist is created automatically when the user taps Create"
(decision D1) and makes the title required (D2). Both decisions were taken autonomously in the
run and still need the product owner's confirmation (reversible: relaxing `WishlistCreateInput`
and the form is enough). Product wording: `in-docs/spec.md` 4.2 and UC-01.

#### Screen and Navigation (`miniapp.js`)

- **`showCreate()`** (`:378`, placed before `showHome`): increments `homeRenderToken`, clears
  `#status`, renders `<h1 tabindex="-1">` (`miniapp.create.title`), a lead `<p
  class="section-subtitle">` and `<form class="wishlist-settings-form wishlist-create-form"
  novalidate>`, then focuses the `<h1>`. The first tab stop is the title input. It is built only
  with `node()`, `textContent` and attributes (no HTML injection).
- **Fields**, in DOM order: `name` (text, `aria-required="true"`, `autocomplete="off"`),
  `description` (text), `event_title` (text), `event_date` (`datetime-local`). Each is wrapped
  in `label.settings-field` with `span.settings-field-label` and a hint
  `span.settings-field-hint#create-hint-<name>` linked by `aria-describedby`. Labels and hints
  reuse the settings keys (see [i18n.md](i18n.md#wishlist-creation-texts-wishenka-296)).
- **Actions** (`div.form-actions.settings-form-actions.create-form-actions`): Create
  (`button[type=submit].btn-primary.create-submit-btn`) and Cancel
  (`.settings-cancel-btn.create-cancel-btn`, reuses `miniapp.wishlist_settings.cancel`).
- **`goHome()`** (`:373`): calls `showHome()` and focuses the home `<h1>` (the skeleton `<h1>` is
  rendered synchronously before the first `await`). Used by Cancel (ignored while a request is in
  flight) and by the failure fallback after creation. Cancel pushes no history entry, so
  `history.back()` leaves the form on screen; nothing is created either way.
- **`homeRenderToken`** (`:372`): module-level counter. `showHome` takes `const token =
  ++homeRenderToken` (`:543`) and drops its result at `:566`, `:716`, `:719` and in the `catch`
  (`:752`) when the token is stale, so a slow home load cannot overwrite the creation form, nor a
  late failure write `miniapp.home.load_failed` over it. `showCreate` also increments it.

#### Validation and Request

- **Client rules** (`validate()`, `:438`): the trimmed title must not be empty
  (`error_title_required`) and must be at most `MAX_TITLE = 255` code points (`[...title].length`,
  `error_title_too_long`, `{max}`); the date must not be a native `badInput` and, when set,
  parse to a year 1-9999 (`error_date_invalid`). The `datetime-local` value is treated as UTC:
  `new Date(value + 'Z').toISOString()` (`buildPayload`, `:455`). Optional fields are trimmed
  and sent as `null` when empty. The form is `novalidate`; errors are custom, not native bubbles.
- **Server rules**: see [wishlists.md](wishlists.md) (`WishlistCreateInput`,
  `wishenka/web/routes/wishlists.py:43-54`). Client and server limits are equal, so a `422` after
  a valid client check arises only from `trim()` versus `strip()` differences on rare Unicode
  spaces.
- **Submit** (`form` submit handler, `:521-538`): `preventDefault`, ignored while `submitting`,
  previous errors cleared, client validation, then
  `withPending(createBtn, send, miniapp.create.pending)`.
  `send()` (`:501`) calls `setBusy(true)` (Cancel disabled, inputs `readonly`), posts once and, on
  success, `showList(list.id)`. If that list load fails it calls `goHome()` and then writes
  `miniapp.list.load_failed` as an error (the list already exists).
- **Errors**: `mapFailure` (`:465`) reads `err.body.detail[].loc` (last element). A `422` on
  `name` and/or `event_date` becomes inline errors on those fields (a `422` on `name` always
  shows `error_title_required`, even for an over-long title; follow-up WISHENKA-320). Any other
  failure (500, network, 401, 422 without a known field) shows `miniapp.home.create_failed` in
  `#status` as an error and keeps the form filled for retry.
- **Inline errors**: created lazily as `span.settings-field-error#create-error-<name>`
  (`role="alert"`), appended to the field label; the input gets `aria-invalid="true"` and
  `aria-describedby="create-hint-<name> create-error-<name>"`. Typing in a field removes its error
  and restores `aria-invalid="false"` and the hint-only description.

#### Focus Rules

| Moment | Focus |
| --- | --- |
| Form opened | the `<h1>` (`tabindex="-1"`), so the new context is announced |
| Client validation fails or `422` on a field | the first invalid field in DOM order |
| Other failure | the Create button, re-enabled |
| Cancel | the home `<h1>` via `goHome()` |
| Success | whatever `showList` focuses |

#### Styling (`miniapp.css`)

- `#app .settings-field-error` (`:131-134`): block, `var(--danger)`, bold, `.9rem`,
  `overflow-wrap: anywhere`.
- `#app .settings-field input[aria-invalid="true"]` (`:135`): danger border, `2px` (the state is
  not colour-only: text, `aria-invalid`, thicker border, and "(required)" in the label).
- The form otherwise reuses the settings form styles (`.wishlist-settings-form`,
  `.settings-field`, `.settings-form-actions`).

#### The `api()` Helper

`api(path, options)` (`:111`) adds the CSRF header for non-GET requests and throws an `Error`
with `status`. Since WISHENKA-296 it also sets `err.body` (the parsed JSON) **only for status
422** (`:121-123`). This deviates from `20-architecture.md` (R-10: every error): parsing the body
of a 500 delayed the failure enough to break the timing-weak wait of
`tests/test_history_screen_browser.py::test_load_failure_shows_alert_and_retry_recovers[500]`
(it accepts any non-empty status, including the transient loading text). The weak wait is the real
defect (WISHENKA-321); do not extend `err.body` to other statuses until it is fixed.

#### Known Limits

- No idempotency key: a retry after a lost response or a proxy 502/504 can create a second list
  (WISHENKA-322); the owner can delete it (WISHENKA-295).
- Invisible-only titles (zero-width characters) pass the 1-255 rule; settings editing (`PATCH`)
  does not follow the title rule (WISHENKA-320). Lists created before this change may still have
  an empty title; the UI shows `miniapp.common.untitled_wishlist` for them.
- Only Chromium is exercised by the browser tests (WISHENKA-313).

### Wishlist Detail Workspace (WISHENKA-290)

`showList(id)` in `static/miniapp.js` fetches the authenticated detail and renders a header with
the localized fallback title, role badge, optional event metadata, and description. The wishes
section appears immediately after the header. The detail is a summary; item editing remains on the
separate server-rendered wishlist page. The shared `static/miniapp.css` supplies responsive section,
action-row, and member-row styles; text and role labels come from `miniapp.*` catalog entries.

For an active list, owners and admins get settings, a public gift-link panel, and a member panel
with a separate collaborator-invitation link. Members cannot access those management controls.
An archived list instead shows an archive notice; only owners and admins can restore it. Non-owners
can toggle favorites. Server-side permission checks remain authoritative.

`sharePanel(token, prefix, title, options)` renders copy and Telegram share actions. Public links
use the `p` prefix and collaborator invitations use `i`; `linkFor` validates the bot, Mini App name,
and token before constructing either URL. Configure `WISHENKA_TELEGRAM_BOT_USERNAME` and
`WISHENKA_TELEGRAM_APP_SHORT_NAME` as described in the configuration reference below. If clipboard
access fails, the input is selected for manual copying. Tokens are bearer capabilities: do not log
the URL or token when debugging.

After a successful favorite, link rotation, membership, role, or restore mutation,
`refreshAfterMutation` clears the old controls before requesting the detail again. If the request
fails, it reports that the change succeeded and offers retry or back navigation; this prevents a
rotated, invalid link from remaining available to copy. For a settings save, `showList` returns a
boolean so the client can distinguish a failed PATCH from a successful PATCH followed by a failed
refresh. Inspect the detail GET and mutation response separately when diagnosing stale content.

The Node and Chromium regression tests cover localized detail regions, settings, sharing, member
actions, refresh failures, and mobile layout. Run them with:

```bash
make test PYTEST_JOBS=2 \
  PYTEST_ARGS='tests/test_wishlist_detail_ui.py tests/test_wishlist_detail_browser.py -q'
```

The browser tests require Chromium; see [testing.md](testing.md) for setup.

### Personal Settings Screen (WISHENKA-291)

#### Overview

`GET /settings` shows language, birthday, birthday reminders, account-wide notification defaults,
per-list exceptions and a separated account-deletion section. Every toggle is a skinned switch
(see [Settings switches](#settings-switches-wishenka-307)) with visible on/off text, per-list
rows show an "inherited" or "override" badge with the effective value, and every
change reports pending, saved, error or unknown state. Backend contracts, categories and
precedence are unchanged (see [users.md](users.md) and
[notifications.md][notification-preferences]).

[notification-preferences]:
    notifications.md#notification-preferences--birthday_reminders-priority-wishenka-34

#### Architecture

Server-rendered `settings.html` plus one controller, `initController()` in
`wishenka/web/static/settings.js`. The server is authoritative; the controller keeps the last
confirmed value per control and never stores a second copy of the data.

- **States** per control or feedback region: `idle` (confirmed value), `pending` (control
  disabled, `aria-busy="true"` on global switches, `settings.saving` note), `saved`
  (`settings.saved`), `error` (localized message, value restored or reconciled) and `unknown`
  (read also failed: controls stay disabled, `Retry`).
- **Serialization**: `exclusive(category, task)` queues mutations per notification category,
  covering the global toggle and all list overrides of that category; an older response cannot
  overwrite a newer effective value.
- **Restore vs reconcile**: only `DEFINITE_REJECTIONS` (`401`, `403`, `404`, `422`, rejected before
  any write) restore the last confirmed value. `5xx`, network loss and malformed success bodies
  are ambiguous: the controller reads the truth back (`GET /api/profile/preferences`, the list
  `GET`, or the profile preferences for birthdate and locale) and shows the committed value
  (`settings.confirmed_after_error` or `settings.not_saved_after_error`). If the read fails too,
  the affected controls become `unknown`, stay disabled and offer Retry (`settings.unknown_state`,
  `settings.retry`) until a read succeeds.
- **Inherited badges**: after a global change they are derived from confirmed global and override
  values (`deriveInheritedBadges`); explicit overrides never change.
- **Birthdate**: the form draft survives rejected saves; fields clear only after a confirmed
  clear. **Locale**: buttons use a CSRF fetch (`window.prepareCsrf`) instead of HTMX; the page
  reloads only after confirmed success, otherwise `settings.locale_reload_needed` / Retry.
- **Deletion**: preview (`GET /api/profile/deletion-preview`) must succeed before the confirm
  panel appears; `POST /api/profile/delete` is sent once, never retried. After a network or `5xx`
  failure the page says the outcome is unknown (`settings.delete_unknown`) and a fresh page
  load decides account status.

#### Usage

- **Endpoints**: `PATCH /api/profile/locale`, `GET /api/profile/preferences`,
  `PATCH /api/profile/birthdate`, `PUT /api/profile/notifications/global`,
  `GET|PUT /api/profile/notifications/wishlists/{id}`, `GET /api/profile/deletion-preview`,
  `POST /api/profile/delete`. No new endpoints or fields.
- **Selectors and ids the script depends on**: root `.settings-page` (with `data-i18n-*`),
  `input[data-global-category]` (`role="switch"`, `aria-labelledby="label-{category}"`), label
  `#label-{category}` (`#label-birthday_reminders` for the reminder switch),
  `select[data-wishlist-override]` (`data-wishlist-id`, `data-category`), badges
  `[data-effective-for="{wishlistId}-{category}"] strong`, state text `#state-{category}`
  (`aria-hidden`), `.locale-option` with `[data-locale-endpoint]`, `#birthdate-form`
  (`#birth-day`, `#birth-month`, `#birth-year`, `#birthdate-clear-btn`, `#birthdate-current`),
  `#toggle-birthday-reminders`, `#delete-account-start-btn`, `#delete-account-confirm-panel`,
  `#delete-account-confirm-btn`, `#delete-account-cancel-btn`, `#delete-impact-summary`. Feedback
  regions: `#locale-feedback`, `#birthdate-feedback`, `#birthday-reminders-feedback`,
  `#global-notifications-feedback`, `#wishlist-notifications-feedback`,
  `#delete-account-feedback` (live regions; Retry buttons carry `data-retry-for`).
  Renaming any of these breaks the controller and the browser tests.
- **i18n**: new `settings.*` keys (RU and EN) include `saving`, `rejected`, `not_saved_after_error`,
  `confirmed_after_error`, `refreshed`, `unknown_state`, `retry`, `reload`,
  `locale_reload_needed`, `delete_preview_failed`, `delete_unknown`, `deleting`,
  `precedence_hint`, `birthdate_priority_hint` and `birthdate_current_label`. Strings reach the
  script as `data-i18n-*` attributes on `.settings-page`; see [i18n.md](i18n.md).
- **Layout**: `miniapp.css` gives 44 px targets, wrapping of long list titles, a mobile card
  layout from 320 px, state badges and a separated danger zone. The switch look is described in
  [Settings switches](#settings-switches-wishenka-307).

#### Configuration

None: no settings, environment variables or schema changes.

#### Troubleshooting

- **Controls stuck disabled with "state unknown"**: the mutation was ambiguous and the
  reconciliation GET also failed. Press Retry (or reload); check `GET /api/profile/preferences`
  status in the request log.
- **Value reverted after an error**: expected for `401`, `403`, `404`, `422`; look for the
  WARNING events `notification_global_invalid_request`, `notification_wishlist_invalid_request`,
  `notification_wishlist_not_found`, `birthdate_invalid_request`, `locale_invalid_request`.
- **Saved but UI showed an error**: a `5xx` after commit; the UI reads the value back. Success
  events are `notification_global_updated`, `notification_wishlist_updated`,
  `locale_explicit_updated`, `birthdate_explicit_updated`, `birthdate_explicit_cleared`
  (no birthdate values, titles or tokens are logged; no client telemetry exists).
- **Deletion outcome unknown**: reload `/settings`; a redirect or `401` means the account is gone.
  See `account_deletion_rejected`, `account_deleted`, `account_deletion_failed`.
- **Switch looks like a plain checkbox, or a state looks wrong** (WISHENKA-307): check that the
  input is inside `.toggle-row`, that no rule after the switch block overrides `appearance`,
  `content` or `background` of `::before` / `::after`, and that the plain-disabled rule still
  sets only `opacity` and `cursor`. A switch stuck in the dashed pending look means
  `aria-busy` was not cleared: the category busy counter in `settings.js` did not return to 0.

#### Tests

```bash
make test PYTEST_JOBS=2 PYTEST_ARGS='tests/test_personal_settings_browser.py -q'
make test PYTEST_JOBS=2 PYTEST_ARGS='tests/test_personal_settings_observability.py -q'
```

`tests/test_personal_settings_browser.py` (real Chromium via CDP) covers states, badges,
failures, reconciliation, locale, birthdate and deletion;
`tests/test_personal_settings_observability.py` (`caplog`) covers the log
contract. Details: [testing.md](testing.md).

#### Settings switches (WISHENKA-307)

The five switches of `/settings` (birthday reminder and four notification categories) are native
checkboxes drawn as switches in `miniapp.css`; the defect of WISHENKA-291 was a default browser
look. Behavior, endpoints and save logic did not change.

- **Markup** (`settings.html`): the native `<input type="checkbox">` stays the source of truth
  (`checked`, `disabled`, change events, label click, Space). It gets `role="switch"` and
  `aria-labelledby="label-{category}"` (`label-birthday_reminders` for the reminder switch)
  pointing at `.toggle-label`; the `.toggle-state` text keeps its `#state-{category}` id but is
  `aria-hidden="true"`, so the state is announced once (from the switch role and `checked`).
- **Geometry**: input 52 px wide, `var(--touch-target)` high, `appearance: none`; the track is
  `::before` (`inset-block: 6px`, `2px` border, pill) and the thumb is `::after` (24 px circle,
  `inset-inline-start` 4 px off, 24 px on, 14 px unknown). `inset-inline-start` makes the thumb
  mirror in RTL. `.toggle-state` has `min-width: 5.5rem` (`0` below 360 px), `text-align: end`.
- **States** (no hard-coded colors, only tokens `--accent`, `--surface`, `--surface-subtle`,
  `--muted`, `--danger` and the global `--focus` outline):

  | State | Hook | Look |
  | --- | --- | --- |
  | off | none | `--surface-subtle` track, `--muted` border and thumb |
  | on | `:checked` | `--accent` track, `--surface` thumb with a check glyph |
  | focus | `:focus-visible` | global 3 px `--focus` outline, offset 3 px (no switch rule) |
  | pending | `[aria-busy="true"]` | dashed `--accent` border, ellipsis thumb, cursor `progress` |
  | unknown | `[data-unknown="1"]` | solid `--danger` border, `?` thumb, cursor `not-allowed` |
  | disabled | `:disabled`, no hook | `opacity: .55`, cursor `not-allowed` |

  Pending and unknown never show the accent fill, also when `checked`; an unknown switch that is
  retried (`aria-busy` again) keeps the centred thumb with a dashed border and the ellipsis.
- **Cascade**: order is base, `:checked`, `[data-unknown]`, `[aria-busy]`, then the plain
  disabled rule `:disabled:not([aria-busy="true"]):not([data-unknown="1"])`. It targets the
  input itself while the state rules target `::before` / `::after`, so it may set only `opacity`
  and `cursor` (never `content`, `background` or `border`); the `:not()` parts keep pending and
  unknown unfaded. A checked pending switch keeps the 24 px thumb offset of `:checked::after`
  (the busy rule sets no `inset-inline-start`); an unknown one is centred at 14 px.
- **`aria-busy`** (`settings.js`, `refreshDisabled`): one guard,
  `if (el.matches('[data-global-category]'))`, sets `aria-busy="true"` while the category busy
  counter is above 0 and removes it otherwise. Per-list selects get no attribute. The unknown
  look is left by the same path after a failed read (`data-unknown`, no `aria-busy`).
- **Motion and contrast**: the `.15s` transition of `background-color`, `border-color` and
  `inset-inline-start` is declared only under `prefers-reduced-motion: no-preference`. Under
  `forced-colors: active` the track and thumb use `Canvas`, `ButtonText`, `Highlight`,
  `HighlightText` and `GrayText` (disabled border).
- **Known limitations**: verified only in Chromium (CDP); iOS Safari and Firefox are unchecked, and
  the `aria-hidden` state text is not exposed to speech control
  ([WISHENKA-313](https://pypost.atlassian.net/browse/WISHENKA-313)). In forced colors a checked
  switch that is pending or unknown still gets the `Highlight` track (the dashed border is then
  invisible; the glyph carries the state), and at 320 px in `ru` a long label such as
  "Подтверждения" can break mid-word because the state text keeps 5.5 rem
  ([WISHENKA-314](https://pypost.atlassian.net/browse/WISHENKA-314)). The test module imports
  private helpers of `test_personal_settings_browser.py`
  ([WISHENKA-315](https://pypost.atlassian.net/browse/WISHENKA-315)). Per-list `<select>`
  overrides keep their native look.
- **Tests**: `tests/test_settings_switch_browser.py`, see [testing.md](testing.md).

### 3. Member Administration

Collaborative wishlists allow multiple users to maintain wish items together.

```
+---------------+-------------------+---------------------------------------------------+
| Role          | Assigned By       | Permissions                                       |
+---------------+-------------------+---------------------------------------------------+
| Owner         | Creator (Fixed)   | Full control: edit settings, invite/remove members|
|               |                   | promote/demote admins, transfer ownership, delete.|
| Admin         | Owner             | Edit settings, invite members, remove members,   |
|               |                   | rotate public & invite tokens. Cannot alter admins|
| Member        | Owner or Admin    | Add and edit wishlist items. Cannot edit settings |
|               |                   | or manage members.                                |
+---------------+-------------------+---------------------------------------------------+
```

#### Endpoints:
- `GET /api/wishlists/{id}/members`: Lists current members with roles and user identifiers.
- `PATCH /api/wishlists/{id}/members/{user_id}/role`: Changes member role (`admin` $\leftrightarrow$
  `member`). Only permitted for the `Owner`.
- `DELETE /api/wishlists/{id}/members/{user_id}`: Removes a collaborator. Owners can remove anyone;
  Admins can remove regular members; members cannot remove managers.

### 4. Collaborator Invitation Flow

Collaborator invitations grant editing access and must never be conflated with public gift links.

1. **Invitation Link Generation**:
   - URL format: `https://t.me/<bot_username>/<app_name>?startapp=i_<invite_token>`
   - Managers copy or share the invitation link from the membership panel.
   - Calling `POST /api/wishlists/{id}/invite/reset` revokes the previous token and issues a new
     one with a 7-day TTL.
2. **Invitation Preview**:
   - When opened via `startapp=i_<token>`, the client calls `GET /api/invitations/preview`
     with `X-Invite-Token: <token>`.
   - The server validates that the token is active, unexpired, and belongs to an active wishlist.
   - The UI displays the wishlist name, clearly communicates that the link grants collaborator
     access, and prompts for explicit confirmation. No state mutation occurs on preview.
3. **Invitation Acceptance**:
   - The user clicks the confirm button.
   - The client sends `POST /api/invitations/accept` with `X-Invite-Token: <token>` and CSRF token.
   - The user is added as a `Member`, and the wishlist format transitions to `collaborative`.

### 5. Public Gift-Selection Sharing

Public links allow gift givers to view items and make reservations without collaborator privileges.

- **URL format**: `https://t.me/<bot_username>/<app_name>?startapp=p_<public_token>`
- **Copy Link**: Copies the full URL to the clipboard using `navigator.clipboard.writeText`.
  Status is announced politely via `aria-live`.
- **Telegram Share**: Uses `window.Telegram.WebApp.openTelegramLink` with a `t.me/share/url`
  deep link to open the Telegram chat chooser.
- **Zero Onboarding**: Public viewers do not need to register, complete forms, or authenticate.
- **Surprise Protection**: Reservation counts, buyer names, and gift statuses are strictly
  withheld from recipients in compliance with the Surprise Invariant.

---

### 6. Categorized Home Screen Overview, Navigation & Card Anatomy (WISHENKA-289)

`showHome()` in [`wishenka/web/static/miniapp.js`](../../wishenka/web/static/miniapp.js) renders the
Mini App Home overview inside `#app`, combining a top navigation hub, the reservations summary
entry, and categorized direct-child `<section>` blocks styled by
[`wishenka/web/static/miniapp.css`](../../wishenka/web/static/miniapp.css).

#### Home Header & Top Navigation Hub

- **Header**: `<h1>` renders `t('miniapp.home.title')` (`Wishlists` / `Вишлисты`), followed by
  `<p class="home-lead">` with `t('miniapp.home.lead')`.
- **Navigation bar (`<nav class="top-nav home-top-nav">`)**: contains three direct controls (with
  exactly two `<button>` elements):
  1. **Create wishlist (`<button class="btn-primary home-create-btn">`)**: first `<button>` in
     `#app` so `startapp=create` focuses it via `root.querySelector('button')?.focus()` without
     auto-creating a list. Spans the full primary row on mobile (`flex: 1 1 100%`) and opens the
     creation form (`showCreate`, `miniapp.js:554`); it sends no request (WISHENKA-296).
  2. **Viewing history (`<button class="home-nav-action">`)**: secondary button (`flex: 1 1
     8.5rem`) transitioning to `showHistory()` in one tap.
  3. **Settings (`<a href="/settings" class="settings-link home-nav-action">`)**: localized
     `t('nav.settings')` link paired beside Viewing history on the secondary row.
- Every direct child of `#app .home-top-nav` enforces `box-sizing: border-box`, `margin: 0`,
  `min-width: var(--touch-target)`, `min-height: var(--touch-target)` (`44px`), and
  `max-width: 100%`.

#### Reservations Summary Card (`.reservations-card`)

After rendering the wishlist sections, `showHome()` performs a non-blocking
`fetch('/web/reservations/card', {credentials: 'same-origin'})`, parses the response HTML with
`new DOMParser().parseFromString(..., 'text/html')`, and constructs `<a class="reservations-card">`
via `node()` (`textContent` only, never `innerHTML`):

- **Structure**:
  - `<span class="reservations-card-main">` containing `<span class="reservations-title">`
    (extracted from `.reservations-title`) and `<span class="reservations-card-hint">`
    (`t('miniapp.home.reservations_hint')`).
  - `<span class="reservations-badge">` displaying `total_distinct_items`: distinct wishes on
    which the caller holds an occupying promise (`ACTIVE` or `PURCHASED`). Multiple promises or
    units on the same wish do not increment the badge.
- **Placement and non-blocking fallback**: inserted into `#app` before
  `root.querySelector('.wishlist-section')` via `root.insertBefore(card, firstSection)`. Any
  non-OK response, network error, or HTML fragment missing `a`, `.reservations-title`, or
  `.reservations-badge` is silently ignored in `try / catch`, leaving all wishlist sections
  rendered and usable.
- **Scope and privacy**: `publicView`, `invitationView`, and `GET /share/{public_token}` never
  request `/web/reservations/card`. On a personal list the owner is the recipient of every wish,
  so those wishes never count toward the owner's promises. Cabinet details are in
  [reservations.md](reservations.md#7-my-reservations-cabinet).

#### Direct-Child Wishlist Sections & Role Precedence Deduplication

`showHome()` fetches `/api/wishlists`, `/api/favorites` (`.catch(() => [])`), and
`/api/wishlists/deleted` (`.catch(() => [])`) in parallel via `Promise.all` and attaches each
category as a direct-child `<section role="region" aria-label="...">` of `#app`:

1. **My wishlists (`.wishlist-section.wishlist-section--owned`)**: active wishlists where
   `l.role === 'owner'` (`border-left: 4px solid var(--accent)`).
2. **Collaborating (`.wishlist-section.wishlist-section--collab`)**: active wishlists where
   `['admin', 'member'].includes(l.role)` (`border-left: 4px solid #0f766e`).
3. **Favorites (`.wishlist-section.wishlist-section--favorites`)**: external bookmarked wishlists
   filtered by `pureFavs` (`border-left: 4px solid var(--focus)`).
4. **Recently deleted (`.wishlist-section.deleted-section.wishlist-section--deleted`)**: rendered
   conditionally only when `Array.isArray(deletedLists) && deletedLists.length > 0` (completely
   omitted when empty), styled with `border-style: dashed; border-color: var(--muted-border);
   border-left: 4px solid var(--muted);`.

Each section opens with `renderSectionHeader(section, title, count, subtitle)`, which appends
`<div class="wishlist-section-header">` (`<h2>` + `<span class="section-count">`) and
`<p class="section-subtitle">`.

**Role Badges & Precedence Deduplication (`owner > admin > member > favorite`)**:

- `renderBadge(role)` renders `<span class="badge badge-${role}">` via `roleLabel(role)`:
  - `owner` $\rightarrow$ `Owner` / `Владелец` (`badge badge-owner`)
  - `admin` $\rightarrow$ `Admin` / `Администратор` (`badge badge-admin`)
  - `member` $\rightarrow$ `Collaborator` / `Соавтор` (`badge badge-member`)
  - `favorite` $\rightarrow$ `Favorite` / `Избранное` (`badge badge-favorite`)
- Because `GET /api/favorites` returns all rows from `wl_favorites` (including shared lists where
  the caller is `admin` or `member`), `showHome()` builds `activeIds = new Set(lists.map(l =>
  l.id))` and filters `pureFavs` with `!activeIds.has(l.id) && !['owner', 'admin',
  'member'].includes(l.role)`. Collaborator-favorited lists appear once in **Collaborating** with
  their operational badge (`Admin` or `Collaborator`) and are never duplicated into **Favorites**.

#### Scannable Wishlist Card Anatomy & Two-Part Empty States

Active cards are built by `wishlistCard(list, onClick, options = {})` as `<div
class="wishlist-card">` (`flex-direction: column` under `#app .wishlist-card`):

- **Header (`.wishlist-card-header`)**: `<h3 class="wishlist-card-title">` (`list.name ||
  t('miniapp.common.untitled_wishlist')`, `min-width: 0; flex: 1 1 11rem; overflow-wrap:
  anywhere;`) paired with `renderBadge(list.role)` (`margin-left: 0; flex-shrink: 0;`). The title
  is never rendered inside a `<button>`.
- **Optional non-sensitive metadata (`.wishlist-card-meta`)**: joins `list.event_title` and
  `formatDate(list.event_date)` (`toLocaleDateString` with `{day: 'numeric', month: 'short',
  year: 'numeric'}` in `ru-RU` / `en-US`, falling back to `String(iso)` on invalid dates) with
  `' · '`. Reservation counts, giver names, and purchase statuses are never included (Surprise
  Invariant).
- **Actions row (`.wishlist-card-actions`)**:
  - **Primary card action (`<button class="wishlist-card-open">`)**: visible label
    `t('miniapp.home.open_wishlist')` (`Open` / `Открыть`) and `aria-label`
    `t('miniapp.home.open_wishlist_named', {name: title})` (`Open: {name}` / `Открыть «{name}»`).
    Styled with `background: var(--accent-soft); border-color: var(--accent); color:
    var(--accent-dark); font-weight: 700; flex: 1 1 7rem;` (`#fde2ea` on hover) so it stands out
    over secondary card actions while leaving **Create wishlist** as the sole solid `.btn-primary`
    CTA on Home.
  - **Favorites subordinate removal (`<button class="wishlist-card-remove">`)**: passed via
    `options.secondaryAction` only in **Favorites** with visible label
    `t('miniapp.home.remove_favorite')` (`Remove from favorites` / `Убрать из избранного`) and
    `aria-label` `t('miniapp.home.remove_favorite_named', {name: itemTitle})`. Both `aria-label`
    templates start with the visible button text to satisfy WCAG 2.5.3 Label in Name. Styled with
    `background: var(--surface); border-color: var(--muted-border); color: var(--muted);
    font-weight: 600; flex: 1 1 9rem;` (never `.btn-danger`), calling
    `DELETE /api/favorites/${l.id}`, re-running `showHome()`, and announcing
    `t('miniapp.home.removed_from_favorites')`.
- **Two-part empty states (`renderEmptyState(noticeKey, hintKey)`)**: when **My wishlists**,
  **Collaborating**, or **Favorites** has `0` items, the section renders `<div
  class="empty-state">` (`background: var(--surface-subtle); border: 1px dashed
  var(--border-subtle);`) containing `<p class="empty-notice">` (why the section is empty) and
  `<p class="empty-hint">` (what the user can do next).
- **Mobile `<= 412px` wrap rules**: `box-sizing: border-box` on cards and controls, `flex-wrap:
  wrap` and `min-width: 0` on `.wishlist-section-header`, `.wishlist-card-header`, and
  `.wishlist-card-actions`, `overflow-wrap: anywhere` on titles, subtitles, metadata, hints, and
  action buttons, and `min-height: var(--touch-target)` (`44px`) on all interactive controls
  prevent horizontal overflow (`scrollWidth <= innerWidth`) at `412x800` and `360x800` in both EN
  and RU.

#### Recently Deleted Wishlists (Owner Restore)

When the authenticated caller owns soft-deleted wishlists still inside the retention window
(`WISHENKA_WISHLIST_RETENTION_DAYS`, default `30` days), `showHome()` renders
`.wishlist-section.deleted-section.wishlist-section--deleted` (`miniapp.deleted.heading`,
`miniapp.home.deleted_sub`):

- Each `.wishlist-card.deleted-wishlist-card` renders `.wishlist-card-header` with
  `<h3 class="wishlist-card-title">` (`l.name || t('miniapp.common.untitled_wishlist')`) and
  `<span class="history-time deleted-meta">` (`t('miniapp.deleted.days_left',
  {days: l.days_remaining})`), followed by `.wishlist-card-actions` containing
  `<button class="wishlist-card-restore">` (`t('miniapp.deleted.restore')`).
- Clicking restore disables the button, announces `miniapp.deleted.restoring`, sends
  `POST /api/wishlists/{id}/restore-deleted` with the session CSRF token, refreshes `showHome()`,
  and announces `miniapp.deleted.restored`.
- If the retention window expired before submission (`410 Gone`), `showHome()` refreshes and
  announces `miniapp.deleted.expired`; on other errors the button re-enables and announces
  `miniapp.deleted.restore_failed`.

#### Home Overview Localization Keys (`wishenka/i18n/catalog.py`)

In addition to preserved keys (`nav.settings`, `miniapp.home.title`,
`miniapp.home.create_wishlist`, `miniapp.home.viewing_history`, `miniapp.home.my_wishlists`,
`miniapp.home.collaborating`, `miniapp.home.favorites`, `miniapp.home.*_empty`,
`miniapp.home.remove`, and `miniapp.deleted.*`), `CATALOG` defines 13 paired EN/RU
`miniapp.home.*` keys embedded into `#miniapp-i18n`:

- `miniapp.home.lead`:
  - EN: `"Your lists, shared plans, and saved favorites in one place."`
  - RU: `"Ваши списки, совместные планы и избранное в одном месте."`
- `miniapp.home.reservations_hint`:
  - EN: `"Active and purchased gift promises"`
  - RU: `"Активные и купленные обещания подарков"`
- `miniapp.home.my_wishlists_sub`:
  - EN: `"Lists you created and manage"`
  - RU: `"Списки, которые вы создали и ведёте"`
- `miniapp.home.collaborating_sub`:
  - EN: `"Shared lists where you co-edit as admin or collaborator"`
  - RU: `"Общие списки, где вы участвуете как администратор или соавтор"`
- `miniapp.home.favorites_sub`:
  - EN: `"Friends' and family wishlists saved for quick access"`
  - RU: `"Сохранённые вишлисты друзей и близких для быстрого доступа"`
- `miniapp.home.deleted_sub`:
  - EN: `"Lists you can restore before the retention window expires"`
  - RU: `"Списки, которые можно восстановить до окончания срока хранения"`
- `miniapp.home.my_wishlists_empty_hint`:
  - EN: `"Tap Create wishlist above to start your first personal list."`
  - RU: `"Нажмите «Создать вишлист» выше, чтобы собрать свой первый список."`
- `miniapp.home.collaborating_empty_hint`:
  - EN: `"Ask a list owner for an invitation link to co-edit a wishlist together."`
  - RU: `"Попросите владельца списка прислать ссылку-приглашение для совместного ведения."`
- `miniapp.home.favorites_empty_hint`:
  - EN: `"Open someone's shared wishlist link and add it to favorites to keep it handy."`
  - RU: `"Откройте чужой вишлист по публичной ссылке и добавьте его в избранное."`
- `miniapp.home.open_wishlist`:
  - EN: `"Open"` / RU: `"Открыть"`
- `miniapp.home.open_wishlist_named`:
  - EN: `"Open: {name}"` / RU: `"Открыть «{name}»"`
- `miniapp.home.remove_favorite`:
  - EN: `"Remove from favorites"` / RU: `"Убрать из избранного"`
- `miniapp.home.remove_favorite_named`:
  - EN: `"Remove from favorites: {name}"` / RU: `"Убрать из избранного «{name}»"`

---

### 7. Favorites Management & Zero-Leak Guarantees

The Favorites feature provides quick access to external wishlists of interest without requiring
collaborator membership:

- **Adding to Favorites**: Calling `POST /api/favorites/{wishlist_id}` with session and CSRF
  adds the wishlist. On the wishlist detail screen (`showList`), a toggle button displays
  "Add to favorites" or "Remove from favorites".
- **Self-Favoriting Guard**: Users cannot favorite their own wishlists (`wl.owner_id == user_id`).
  Any self-favoriting attempt raises `ValueError`, returning HTTP 400
  (`Cannot favorite own wishlist`) and emitting a security warning audit event
  (`favorite_own_wishlist_denied`). The Mini App UI hides the favorite button for owned wishlists.
- **Removing from Favorites**: Calling `DELETE /api/favorites/{wishlist_id}` removes the entry.
- **Zero-Leak Guarantee (Surprise Invariant)**: Responses from `GET /api/favorites` return clean
  wishlist projections with public metadata (`id`, `name`, `description`, `event_title`,
  `event_date`, `status`, `role`, `is_favorite`). They strictly withhold all reservation entries,
  buyer identities, and item booking counts, ensuring complete privacy for gift surprises.

---

### 8. Viewing History & Automated Tracking

#### Overview

Viewing history lets users re-open recently visited wishlists. `showHistory()` (WISHENKA-292)
renders a scannable card list with a readable last-viewed time, a one-tap Open action, and a
deliberate, two-step "Clear history". The API contract is unchanged; the screen is client-side
only (`wishenka/web/static/miniapp.js`, `wishenka/web/static/miniapp.css`).

- **Automatic View Recording**: When an authenticated user opens any wishlist (`showList`), the
  client dispatches a background `POST /api/history/{id}`.
- **Deduplication**: Re-visiting a recorded wishlist updates `viewed_at`, no duplicate row.
- **20-Entry Bound**: At most 20 entries per user; the oldest is pruned on the 21st.
- **Zero-Leak Guarantees**: `GET /api/history` projects only sanitized list metadata and omits
  reservation records and buyer details; the screen renders only title, time and role badge.
- Entry point: the "Viewing history" button in the home top navigation.

#### Architecture

`showHistory()` renders a heading (`h1`, `tabindex="-1"`) and a
`section[role="region"][aria-busy]`, then fills the section by state:

| State | Section content | Hooks |
| --- | --- | --- |
| loading | `aria-busy="true"`, status `nav.loading`, no Clear | `section[aria-busy]` |
| error | alert plus Retry, no Clear | `.history-error[role=alert]`, `.history-retry` |
| empty | notice, hint, button to Home, no Clear | `.history-empty`, `.history-empty-action` |
| list | `ul.history-list` of `li.history-card` plus footer | see Usage |
| confirming | Clear replaced inline by confirmation group | `.history-confirm` |
| clearing | group `aria-busy`, both buttons disabled | `.history-confirm[aria-busy]` |
| clear-failed | alert inside the group, list kept, retry allowed | `.history-error` |

- **Helpers**: `renderHistoryCard(item)`, `renderHistoryEmpty()`, `renderHistoryFooter(count)`
  and `formatViewedAt(iso)`.
- **Confirm flow** (`renderHistoryFooter`): the first click on `.history-clear` sends no request;
  it swaps the button for `.history-confirm` and focuses Cancel (`.history-confirm-cancel`).
  Cancel or `Escape` swaps Clear back and restores focus to it. `.history-confirm-yes` sends
  exactly one `DELETE /api/history`; while it runs both buttons are disabled, repeated clicks and
  Cancel are ignored (`clearing` guard). On failure the group stays with a
  `miniapp.history.clear_failed` alert and the list is untouched. On success `showHistory()`
  re-renders (empty state), status `miniapp.history.cleared` is announced, focus moves to `h1`.
- **Time rendering** (`formatViewedAt`): under 60 s shows `miniapp.history.just_now`; under
  7 days a relative `Intl.RelativeTimeFormat` string (minute, hour or day, `numeric: 'auto'`);
  7 days or more an absolute `toLocaleString` (`dateStyle: medium`, `timeStyle: short`). The
  locale is `activeLocale()` (`ru-RU` or `en-US`). Output is `<time datetime=ISO title=ABSOLUTE>`.
  A missing or invalid `viewed_at` omits the `<time>` element (never "Invalid Date"). Without
  `Intl.RelativeTimeFormat` the absolute form is used.
- **Stale-render token**: module-level `historyRenderToken` is incremented per `showHistory()`
  call. After each `await` the call returns if its token is no longer current, so a slow
  response cannot overwrite a newer screen (navigation away, Retry, re-render after clear).
- **Layout**: cards wrap and shrink at 320 px (no overflow, targets of at least 44 px). Clear is
  a quiet secondary action below the list; the confirm button uses `btn-danger`. `.history-item`
  is kept on cards for the shared row rule; it is no longer shared with the home card rule.

#### Usage

- **Endpoints** (unchanged): `GET /api/history` (up to 20, newest first), `POST /api/history/{id}`
  (404 for missing or deleted lists), `DELETE /api/history` (clears the caller's history only).
  Service details: [wishlists.md](wishlists.md#get_history--clear_history).
- **Element hooks** used by `tests/test_history_screen_browser.py`: `ul.history-list`,
  `li.history-card`, `h2.history-title`, `.history-meta`, `time.history-time[datetime][title]`,
  `.badge` (role), `.history-open` (aria-label `miniapp.home.open_wishlist_named`),
  `.history-footer`, `.history-clear`, `.history-confirm`, `.history-confirm-title`,
  `.history-confirm-cancel`, `.history-confirm-yes`, `.history-error`, `.history-retry`,
  `.history-empty`, `.history-empty-action`. Renaming any of them breaks the tests.
- **i18n keys** (`miniapp.history.*`, RU and EN): `title`, `clear`, `cleared`, `clear_failed`,
  `empty`, `empty_hint`, `open_home`, `viewed_at`, `load_failed`, `retry`, `just_now`,
  `clear_confirm_title`, `clear_confirm_body` (`{count}`), `clear_confirm_yes`,
  `clear_confirm_cancel`, `clearing`. Family notes: [i18n.md](i18n.md#architecture).
- **Known access-model limitation (pre-existing, tracked)**: `POST /api/history/{id}` and
  `POST /api/favorites/{id}` check only that the list exists and is not deleted, not membership,
  so a user can record a guessable id and read its title and event fields back from
  `GET /api/history`. The redesign changed no contract and renders no extra fields. Decision and
  options: [60-tech-debt.md](../../ai-tasks/WISHENKA-292/60-tech-debt.md); Jira
  WISHENKA-303 (history) and WISHENKA-302 (favorites).

#### Configuration

None: no settings, environment variables or schema changes.

#### Troubleshooting

- **Empty vs error**: the empty state (`.history-empty`, no alert) means `GET /api/history`
  returned `[]` (nothing recorded, cleared, or lists deleted). The error state
  (`.history-error` with Retry) means the request failed; check the request log for
  `GET /api/history` and the event `view_history_listed` (`count`).
- **Entry missing after opening a list**: the background `POST /api/history/{id}` failed or got
  `404` (deleted list); look for `view_history_recorded`.
- **Clear stuck in "clearing"**: the `DELETE` never settled (slow or dropped connection). The
  buttons stay disabled by design to prevent duplicates; reload the screen. A failed request
  shows `miniapp.history.clear_failed` and re-enables the buttons.
- **Reading `view_history_cleared`**: emitted exactly once per `DELETE /api/history`, by
  `WishlistService.clear_history` (the route no longer logs it). Fields: `user_id`,
  `removed_count` (rows removed; `0` when already empty). Two events per request mean the
  route-level logger was reintroduced.

---

### 9. Wish Item Quick-Add Bar, Live Preview & Detailed Edit Sheet (HTMX UI)

The wish item UI in [`wishenka/web/routes/items_ui.py`](../../wishenka/web/routes/items_ui.py)
provides a mobile-first HTMX workflow for adding, previewing, editing, archiving, and restoring
wish items without full-page reloads.

#### 9.1. Wishlist Detail View & Role-Based UI Gating (`wishlist_detail.html`)
- **Endpoint**: `GET /web/wishlists/{wishlist_id}` (`view_wishlist_detail`).
- **Template**: [`wishenka/web/templates/wishlist_detail.html`](../../wishenka/web/templates/wishlist_detail.html).
- **Access Control**: Evaluates `can_edit_wishlist` via
  `WishlistAccessPolicy.can_add_or_edit_item(ctx, wishlist)`.
  - `can_edit_wishlist == True` only for active members (`OWNER`, `ADMIN`, `MEMBER`) when the
    wishlist status is `active`.
  - When `can_edit_wishlist` is false (anonymous guests, external gifters, or archived wishlists),
    both `#quick-add-bar` and the per-card `.btn-edit-item` triggers are omitted from the DOM.
  - All mutating UI endpoints enforce `_ensure_member_and_active`, returning `404 Not Found` for
    non-members and `409 Conflict` if the wishlist is archived.
- **Receipt context (WISHENKA-24, WISHENKA-161)**: the page also gets `is_member`
  (`ctx.is_member`), `can_view_gifted` (`WishlistAccessPolicy.can_view_gifted`, a member of a
  non-deleted list) and `gifted_rows` (read only when `can_view_gifted`, `None` on a domain
  error). For a member the template renders
  `<div id="list-notice" role="status" aria-live="polite" tabindex="-1">` above `#items-list`
  (the target of the receipt notice, programmatic focus after a full receipt, and the
  stale-reorder notice), and for `can_view_gifted`
  the section `#gifted-items-section` right after `#items-list`. The empty
  `<div id="item-modal-container">` is the target of every modal, including the receipt dialog.
  Details: [gift-receipt.md](gift-receipt.md#mini-app-ui-wishenka-24).

#### 9.2. Universal Quick Add Bar (`partials/item_quick_add.html`)
- **Template**: [`wishenka/web/templates/partials/item_quick_add.html`](../../wishenka/web/templates/partials/item_quick_add.html).
- **Viewport Positioning**: Pinned to the bottom of the screen via `.quick-add-container` in
  `static/miniapp.css` (`position: fixed; bottom: 0; padding-bottom: max(12px,
  env(safe-area-inset-bottom))`). Interactive controls enforce `min-height: 44px` touch targets.
- **Debounced Live Preview Trigger**: The input `#quick-add-input` (`name="raw_input"`) is bound
  with:
  - `hx-post="/web/wishlists/{{ wishlist.id }}/items/preview"`
  - `hx-trigger="input changed delay:500ms, paste"`
  - `hx-target="#quick-add-preview-target"` and `hx-swap="innerHTML"`
- **Actions**:
  - **«Добавить» (`#btn-quick-add`)**: Submits `#quick-add-form` via
    `hx-post="/web/wishlists/{{ wishlist.id }}/items/quick"` (`quick_add_item`), appending the new
    card to `#items-list` (`hx-swap="beforeend"`).
  - **«Подробнее» (`#btn-quick-details`)**: Opens the creation bottom-sheet modal via
    `hx-get="/web/wishlists/{{ wishlist.id }}/items/new"` (`get_new_item_modal`) with
    `hx-include="#quick-add-form"`, transferring any typed text or previewed metadata into the
    detailed form.

#### 9.3. Live URL Preview Card & Graceful Fallback (`partials/item_preview_card.html`)
- **Endpoint**: `POST /web/wishlists/{wishlist_id}/items/preview` (`preview_item_input`).
- **Template**: [`wishenka/web/templates/partials/item_preview_card.html`](../../wishenka/web/templates/partials/item_preview_card.html).
- **Plain Text Fast-Path**: When `UniversalInputClassifier.classify(raw_input)` returns
  `InputType.PLAIN_TEXT`, the endpoint immediately returns an empty `200 OK` HTML response without
  making outbound network requests.
- **Rich URL Preview**: For `EXPLICIT_URL`, `IMPLICIT_URL`, and `COMPOSITE_SHARE`,
  `ItemPreviewService.fetch_preview` extracts metadata and renders `#item-preview-card` with:
  - Product thumbnail (`preview.image_url`), store badge (`preview.store_name`), cleaned title
    (`preview.title`), and price (`preview.price`, `preview.currency`).
  - Hidden `<input type="hidden">` fields (`link`, `price`, `currency`, `image_url`, `store_name`,
    `title`) inside `#quick-add-form` so clicking «Добавить» persists all scraped fields in one tap,
    and clicking «Подробнее» carries them into the creation modal.
  - Dismiss button (`✕`, `.btn-preview-dismiss`) clearing `#quick-add-preview-target`.
- **Graceful Fallback (`preview.is_fallback` or missing title)**: When scraping hits anti-bot
  protection, timeouts, or SSRF restrictions, the preview card displays the sanitized URL and
  store badge alongside an inline `<input type="text" name="title">` prompting the user to enter
  the gift title manually or open «Подробнее».

#### 9.4. Quick-Add Submission & HTMX Out-of-Band (`hx-swap-oob`) Updates
- **Endpoint**: `POST /web/wishlists/{wishlist_id}/items/quick` (`quick_add_item`, quick-add route).
- **Behavior**: Creates the wish item via `WishlistService.add_wish_item` (preferring explicit
  `title` from preview/modal over `raw_input`, defaulting to `quantity=1` and `currency="RUB"`).
- **Response (`201 Created`)**:
  - Primary payload: Rendered [`partials/item_card.html`](../../wishenka/web/templates/partials/item_card.html)
    appended to `#items-list`.
  - Out-of-Band (`hx-swap-oob`) fragments in the same response:
    1. `<div id="quick-add-preview-target" hx-swap-oob="innerHTML"></div>` — clears the preview
       card.
    2. `<input type="text" id="quick-add-input" ... value="" hx-swap-oob="true" />` — resets the
       quick-add input field while preserving its HTMX attributes.
    3. `<div id="empty-items-placeholder" hx-swap-oob="delete"></div>` — removes the empty-list
       placeholder if present.
    4. `<div id="item-modal-container" hx-swap-oob="innerHTML"></div>` — closes the creation modal
       when submitted from `#item-detailed-form`.

#### 9.5. Detailed Creation & Edit Bottom-Sheet Modal (`partials/item_edit_modal.html`)
- **Template**: [`wishenka/web/templates/partials/item_edit_modal.html`](../../wishenka/web/templates/partials/item_edit_modal.html).
- **Creation Mode (`is_edit=False`)**:
  - Loaded via `GET /web/wishlists/{wishlist_id}/items/new` (`get_new_item_modal`, new-modal route).
  - Prepopulates `title`, `link`, `price`, `currency`, and `image_url` from query parameters or
    classifies `raw_input` via `UniversalInputClassifier`.
  - Submits to `POST /web/wishlists/{wishlist_id}/items/new` (`submit_new_item`), appending the
    new card to `#items-list` (`hx-swap="beforeend"`) and returning `201 Created` with OOB resets
    via `_render_created_item_response`.
  - On `400 Bad Request` validation errors (form parsing/empty title or domain `ValueError`),
    `_render_item_modal_error` (`is_edit=False`) re-renders `partials/item_edit_modal.html` with
    `HX-Retarget: #item-modal-container` and `HX-Reswap: innerHTML`, preserving all submitted form
    fields and collaborative recipient options/selection while displaying `[role="alert"]` inside
    the modal.
- **Edit Mode (`is_edit=True`)**:
  - Loaded via `GET /web/wishlists/{wishlist_id}/items/{item_id}/edit` (`get_edit_item_modal`).
  - Submits to `POST /web/wishlists/{wishlist_id}/items/{item_id}/edit` (`submit_edit_item`),
    replacing `#item-card-{item_id}` (`hx-swap="outerHTML"`) and closing `#item-modal-container`
    via `hx-swap-oob="innerHTML"`.
- **Supported Fields**: `title` (required, 1..255 chars), `link`, `price`, `currency` (`RUB`,
  `USD`, `EUR`, `KZT`, `BYN`), `quantity` (1..1000 stepper), collaborative recipient targeting
  (`recipient_user_id` dropdown and `recipient_name` input rendered only when
  `is_collaborative=True`), `description` (up to 4000 chars), `image_url` (with live thumbnail),
  `priority` (`low`, `medium`, `high`), and `category`.

#### 9.6. Quantity Minimum, HTTP 409 Recovery & Surprise Invariant

- The edit input and stepper use `min_quantity = max(1, received_quantity)`; the form does
  not expose occupied units or a booking hint.
- `POST /web/wishlists/{wishlist_id}/items/{item_id}/edit` returns HTTP 409 with the edit
  modal when quantity is below the received count. It preserves submitted values and shows a
  localized message referring only to received units.
- The recipient sees neither booking details nor giver identities. Templates use Jinja2
  auto-escaping for user-supplied fields.

#### 9.7. Safe Item Archiving & Restoration via HTMX
- **Archive**: `POST /web/wishlists/{wishlist_id}/items/{item_id}/archive` (`archive_item_ui`),
  triggered from the edit modal with `hx-confirm`. Calls `WishlistService.archive_wish_item`
  (preserving existing gifter reservations) and returns `200 OK` with OOB swaps deleting
  `#item-card-{item_id}` (`hx-swap-oob="delete"`) and emptying `#item-modal-container`.
- **Restore**: `POST /web/wishlists/{wishlist_id}/items/{item_id}/restore` (`restore_item_ui`).
  Calls `WishlistService.restore_wish_item` (appending the item to the tail of active items while
  retaining reservations) and returns `200 OK` with the rendered `partials/item_card.html`.
- **Fully received wish (WISHENKA-24)**: both routes answer `409` with the header
  `X-Receipt-Refusal: nothing_remaining` and a body made only of `hx-swap-oob` elements (dialog
  closed, `#list-notice` text, refreshed list, archive section and «Подаренные»), not the old
  JSON `detail`. The archive dialog adds a note about the received part when the wish has
  received units, and an archived wish with received units shows «Осталось N» in the archive
  section. See [gift-receipt.md](gift-receipt.md#stale-states).

#### 9.8. Vertical Items List: Compact/Expanded Cards, Manual Order, Archived Section (WISHENKA-15)
- **Layout**: `wishlist_detail.html` renders `#items-list` from `partials/items_list.html`, which
  includes `partials/item_card.html` per item (`is_first`/`is_last` drive disabled move buttons).
  Archived items render below via `partials/archived_items_section.html` (owner/editor only).
  The «Подаренные» section (`partials/gifted_items_section.html`, members only) sits between the
  list and the archive section.
- **Receipt (WISHENKA-24, WISHENKA-153)**: for a list member a wish with received units shows
  the badge «Осталось N из M» and the details «Запрошено», «Получено», «Осталось» instead of `×M`
  and «Количество». The button `.btn-receipt-item` («Получено», in `.item-actions`, while
  `remaining_quantity > 0`) opens the receipt dialog with `hx-get` into `#item-modal-container`.
  In «Подаренные» (`partials/gifted_items_section.html`), when `can_edit_wishlist` is true
  (active list + member), each receipt act with `receipt_id > 0` renders `.btn-receipt-edit` and
  `.btn-receipt-cancel` buttons opening `partials/receipt_edit_modal.html` (with `.quantity-control`
  and `44px` `--touch-target` `-`/`+` `.btn-step` buttons, WISHENKA-221) and
  `partials/receipt_cancel_modal.html`. `receipt.js` tracks `.btn-receipt-edit` and
  `.btn-receipt-cancel` openers via `openerGiftedItemId` to restore focus across
  `#gifted-items-section` OOB replacements. A giver card of a fully received wish has no promise
  controls. The flow, routes, refusals, accessibility (`aria-modal`, background `inert`, Tab trap,
  focus return, `gifted-items-details` open state, `RECEIPT_SELECT_MAX = 20` stepper), and
  invariants are in [gift-receipt.md](gift-receipt.md#mini-app-ui-wishenka-24).
- **Compact/expanded**: `.item-card-summary` is the compact row (`aria-expanded` starts `false`).
  `.item-card-details` is rendered with `hidden`. The delegated toggle in
  [`wishlist.js`](../../wishenka/web/static/wishlist.js) clears `hidden` to expand and sets it to
  collapse. Clicks on
  `a, button, input, select, textarea` or any `[data-no-toggle]` element do not toggle the card.
  Owners and editors also get a visible drag handle (`.item-drag-handle`, `⠿`) inside the collapsed
  summary, before the thumbnail. It is rendered only under `can_edit_wishlist`, carries
  `data-no-toggle`, and is the touch reorder grip (see 9.8.1). Giver controls are
  `.item-giver` inside that summary, so they stay on screen while the card is expanded. A
  successful promise refresh keeps an expanded card expanded by clearing `hidden` on the new
  details. The control list, own line, recipient omission, HTTP 503 busy sentence, and cookie
  CSRF behavior are in [reservations.md](reservations.md#6-wish-card-giver-controls).
- **Manual order** (editors only):
  - Buttons: `POST /web/wishlists/{id}/items/{item_id}/move?direction=up|down` (`move_item_ui`).
  - Drag-and-drop: `wishlist.js` handles native HTML5 `dragstart/dragover/drop` (mouse) and Pointer
    Events (touch, WISHENKA-109) on `.item-card[draggable="true"]` inside `#items-list`, then posts
    the full order to `POST /web/wishlists/{id}/items/reorder` with repeated form field `item_ids`
    (`reorder_items_ui`). Both paths end in the same `submitReorder` function.
  - Both return the re-rendered `partials/items_list.html` (`hx-target="#items-list"`). The submitted
    ids must be an exact permutation of the active items, otherwise `400`.
- **Archive flow**: `GET .../items/{item_id}/archive-confirm` (`archive_confirm_ui`) opens
  `partials/item_archive_modal.html`; it warns about active reservations when the wishlist flag
  `warn_on_delete_reserved` is true (default `1`; column added to `wl_lists` by the Alembic revision `add_warn_on_delete_reserved`, see [migrations.md](migrations.md)).
  `POST .../archive` and `.../restore` also refresh `#archived-items-section` via an OOB swap.

##### 9.8.1. Client Script (`static/wishlist.js`, WISHENKA-108)

[`wishenka/web/static/wishlist.js`](../../wishenka/web/static/wishlist.js) replaced the toggle and
drag-and-drop code that used to be inline in `base.html` and the `onclick`/`onkeydown` attributes of
`partials/item_card.html`. It is a classic script wrapped in an IIFE with `'use strict'`; it exposes
no globals (`toggleWishCard` is no longer a global function).

- **Loading**: `base.html` has `<script src="/static/wishlist.js" defer></script>` after the htmx
  and `json-enc` tags and before the remaining inline script. `defer` runs it after parsing, so
  the order after htmx is kept. All listeners sit on `document` (delegation), so cards that
  appear after an htmx swap or `swapWishCard` need no re-binding.
- **Toggle**: delegated `click` and `keydown` (`Enter` or Space) on the closest
  `.item-card-summary`. The event is ignored when its target is inside
  `a, button, input, select, textarea, [data-no-toggle]`. `preventDefault()` runs only for
  `keydown` on a non-interactive target, so Space does not scroll the page. The handler flips
  `aria-expanded` on the summary and `hidden` on the sibling `.item-card-details`.
- **Drag-and-drop reorder (mouse)**: delegated `dragstart`, `dragover`, `drop`, `dragend` on
  `.item-card[draggable="true"]` inside `#items-list`. On `drop` the script computes the side with
  `isAfterMidpoint` and calls `submitReorder`. Mouse and pen keep this native HTML5 path.
- **Shared submit point**: `isAfterMidpoint(clientY, rect)` is true when the pointer is below the
  vertical midpoint of the target card. `submitReorder(list, card, target, after)` checks the
  wishlist id and htmx (the skip path below), moves the card before or after the target, collects
  `data-item-id` of every `.item-card`, and posts it with `htmx.ajax('POST', ...)`, target
  `#items-list`, swap `innerHTML`, field `item_ids`. It is the only place of this script that
  calls `htmx.ajax`, for mouse and touch alike (`receipt.js` has its own single call).
- **Wishlist id**: read at drop time from `#items-list[data-wishlist-id]`, rendered by
  `wishlist_detail.html` and `share_wishlist.html` as `{{ wishlist.id }}`. The value must match
  `^\d+$`. The URL is no longer derived from `window.location`. No htmx swap replaces
  `#items-list` itself (all swaps target its inner HTML), so the attribute survives re-renders.
- **Skip path**: if the id is missing or not numeric, or `window.htmx` is not loaded, the card is
  not moved, no request is sent, and the script writes one `console.warn`. The text is
  `wishlist.js: reorder skipped: ` followed by the causes joined with `; `. The causes are
  `#items-list[data-wishlist-id] is not numeric (got "<value>")` and
  `window.htmx is not loaded (CDN blocked or script order)`. Nothing is logged on the server for
  this case.
- **Server events** for the reorder request (unchanged): `ui_items_reordered` (INFO,
  `POST .../items/reorder`), `ui_item_moved` (INFO, move buttons) and `ui_items_reorder_rejected`
  (WARNING, `reason=invalid_permutation`, HTTP 400).
- **Caching**: `BrowserSecurityMiddleware` sends `Cache-Control: no-store` on every response,
  including `/static/*`, so `wishlist.js` is downloaded on each page load and a fix reaches users
  at once. No cache-busting URL is used. Revisiting the policy is WISHENKA-139.
- **Inline script & handlers removed (WISHENKA-140)**: `base.html` no longer embeds an inline
  `<script>` (moved to `static/app.js`), and `item_edit_modal.html`, `item_archive_modal.html`, and
  `item_preview_card.html` no longer use inline `onclick` attributes. See section 9.8.2 below.
- **Known limits**: the reorder URL `/web/wishlists/{id}/items/reorder` is hardcoded in the script
  (WISHENKA-141). See also "Touch limits" below.
- **Touch reorder (WISHENKA-109)**: HTML5 drag events do not fire on most touch devices, so the
  script adds a Pointer Events gesture. It is limited to `pointerType === 'touch'`; mouse and pen
  keep the native path (a pen `pointerdown` returns early and falls through).
  - **Handle**: `.item-drag-handle` lives in the collapsed `.item-card-summary` (owner and editors
    only, inside a card with `draggable="true"` in `#items-list`). It has `touch-action: none`,
    `user-select: none`, `-webkit-touch-callout: none` and a 44 px minimum size in
    [`miniapp.css`](../../wishenka/web/static/miniapp.css). The summary itself has no
    `touch-action`, so a swipe elsewhere still scrolls the page.
  - **Gesture**: `pointerdown` on the handle arms the gesture, calls `setPointerCapture` on the
    handle (best effort) and disables Telegram swipes. The gesture becomes active when the pointer
    moves 4 px (`DRAG_START_THRESHOLD_PX`). A tap on the handle (less than 4 px) does nothing: no
    request, and no toggle (the handle is `data-no-toggle`). While active, the card follows the
    finger with `transform: translateY(...)` (page scroll is added). `document.elementFromPoint`
    finds the target card under the pointer, and `isAfterMidpoint` picks the side.
  - **Drop**: `pointerup` of an active gesture calls `submitReorder` when there is a target card
    other than the dragged one, and the dragged card is still a child of `#items-list`. A drop on
    the card itself, or outside the cards, sends nothing. The DOM order is changed only inside
    `submitReorder`, so a cancelled gesture leaves the list as it was.
  - **Cancel triggers**: `pointercancel`, `lostpointercapture`, a `pointerdown` of a second pointer,
    `Escape`, `visibilitychange` to hidden, window `blur`, and `htmx:beforeSwap` whose target is
    `#items-list`. No request is sent and the state is cleaned (transform, classes, indicators,
    capture, animation frame). While a gesture is in progress, `dragstart` and `contextmenu` are
    cancelled with `preventDefault`.
  - **Feedback classes**: `is-touch-dragging` on the moved card (raised, translucent, shadow,
    `pointer-events: none`), `drop-before` and `drop-after` on the target (3 px accent line above
    or below), and `is-touch-reordering` on both `html` and `body` (`user-select: none`,
    `overscroll-behavior-y: contain` on `html`). Expanded card details (`.item-card-details`)
    remain visible during touch drag (`hidden` and `aria-expanded` do not change), so the card
    keeps its height and the list does not jump at drag start (WISHENKA-142).
  - **Autoscroll**: a `requestAnimationFrame` loop scrolls the page by up to 14 px per frame when
    the pointer is within 64 px of the top or bottom window edge (`AUTOSCROLL_EDGE_PX`,
    `AUTOSCROLL_MAX_PX`), then updates the card position and the target. Speed is per frame, not
    per second.
  - **Click suppression**: after an active gesture ends (drop or cancel), the next capture-phase
    `click` is swallowed (`preventDefault` and `stopPropagation`). If no click follows, the flag
    expires after `CLICK_SUPPRESS_MS` (400 ms); a genuine tap inside that window is swallowed
    too.
  - **Telegram integration**: `window.Telegram.WebApp` is optional. On `pointerdown` the script
    calls `disableVerticalSwipes()` only when `isVersionAtLeast('7.7')` (Bot API 7.7) and
    `isVerticalSwipesEnabled === true`. When the gesture ends it calls `enableVerticalSwipes()`
    only if this gesture disabled them, so swipes disabled elsewhere stay disabled. Haptics need
    `isVersionAtLeast('6.1')` and `HapticFeedback`: `impactOccurred('light')` when the gesture
    becomes active, `selectionChanged()` when the target card changes. Every SDK call is in
    `try/catch`; a failure never blocks the reorder.
  - **Console warnings**: besides the reorder skip warning above, a failing SDK call writes one
    `console.warn` per page load:
    `wishlist.js: Telegram SDK call failed (<call>); later failures are not reported`, where
    `<call>` is `disableVerticalSwipes`, `enableVerticalSwipes`,
    `HapticFeedback.impactOccurred` or `HapticFeedback.selectionChanged`, followed by the caught
    error as a second argument.
  - **Server events**: unchanged. A touch drop posts the same request as a mouse drop, so
    `ui_items_reordered` and `ui_items_reorder_rejected` apply as before. Nothing new is logged on
    the server or sent to a client telemetry endpoint.
  - **Accessibility**: the handle is decorative (`aria-hidden="true"`, `title="Перетащить"`). The
    move up and move down buttons in the card details stay the keyboard and screen-reader way to
    reorder.
  - **Touch limits**: clients older than Bot API 7.7 cannot disable vertical swipes, so a downward
    swipe on the handle may still minimise the Mini App there. A swipe that starts on the Telegram
    header still closes it. The first-touch timing of `disableVerticalSwipes()`, native `dragstart`
    from a long press on Chrome Android, pull-to-refresh and the autoscroll speed are not verified
    on real devices; the manual checklist is WISHENKA-143. Tidying of the script (long lines,
    module split, palette variables) is WISHENKA-144.
- **Receipt additions (WISHENKA-24)**: the `swapWishCard` wrapper (a refresh that is not the same
  `.item-card` becomes `p.item-card-unavailable` «Желание больше недоступно. Обновите
  страницу.») and the `htmx:responseError` listener that reacts only to the header
  `X-Reorder-Refusal: stale_order` (notice «Список изменился. Обновляем.» in `#list-notice`, then
  `window.location.reload()` after `STALE_RELOAD_DELAY_MS` = 800 ms). Both guard a missing
  function or `xhr`.
- **Dialog script (`static/receipt.js`, WISHENKA-24)**: a second classic script, loaded
  `<script src="/static/receipt.js" defer>` after `wishlist.js` in `base.html`; IIFE, delegated
  listeners on `document`, texts via `textContent` only, no inline handler. It owns the quantity
  summary, dialog dismissal and focus, the single in-flight `htmx.ajax('POST', ...)` of the
  receipt and the guarded `htmx:beforeSwap` override keyed on `X-Receipt-Refusal` (htmx 1.9.12
  does not swap 4xx and 5xx). See
  [gift-receipt.md](gift-receipt.md#why-htmxbeforeswap-is-overridden).
- **Tests**: behavioural browser tests drive a real headless Chromium over CDP, offline, against a
  per-test server and database: `tests/test_wishlist_cards_browser.py` (card toggle),
  `tests/test_wishlist_mouse_reorder_browser.py` (mouse drag-and-drop) and
  `tests/test_wishlist_touch_reorder_browser.py` (touch reorder and its cancel paths), 53 tests in
  all, plus the nine tests of `tests/test_receipt_modal_browser.py` (WISHENKA-24) and the seven
  tests of `tests/test_receipt_accessibility_browser.py` (WISHENKA-161, WISHENKA-221). Their
  design, fixtures, fidelity limits, diagnostics and mutation proof are in
  [testing.md](testing.md). The htmx used there is an offline stub and touch is synthesized, so
  neither the real htmx wiring nor a real touch stack is covered. The string and CSS guards that
  were kept are weak by design (a comment can satisfy them): `tests/test_wishlist_static_script.py`
  checks that `/static/wishlist.js` is served, that `base.html` no longer inlines toggle or
  drag-and-drop code, that the cards carry no inline handlers, that `#items-list` has
  `data-wishlist-id` and that no hx-swap replaces `#items-list`; `tests/test_wishlist_touch_reorder.py`
  (WISHENKA-109) checks the four Telegram SDK tokens in `wishlist.js`, `-webkit-touch-callout: none`,
  that the summary does not block touch scrolling, the single `submitReorder` call point and the
  markup of `partials/item_card.html` (the handle is in the summary only for editors).
- **Related debts**: WISHENKA-139 (`no-store` caching of static JS), WISHENKA-140 (completed:
  inline JS and `onclick` extraction to `static/app.js`), WISHENKA-141 (hardcoded reorder URL; the change
  stays inside `submitReorder`), WISHENKA-142 (list jump when an expanded card is dragged),
  WISHENKA-143 (real-device checklist), WISHENKA-144 (tidying), WISHENKA-145 (real htmx smoke test
  instead of the stub), WISHENKA-146 (shared CDP driver for the older browser modules, `websockets`
  range), WISHENKA-147 (CI upload of failure diagnostics). UI debts of the receipt story:
  WISHENKA-160 (completed: modal CSS layering, `htmx:beforeSwap`, OOB/retarget error contracts)
  and WISHENKA-161 to 165 (list in [gift-receipt.md](gift-receipt.md#follow-up-tickets-of-the-ui)).

##### 9.8.2. Global App Script (`static/app.js`), Settings Script (`static/settings.js`), and Strict CSP Readiness (WISHENKA-140)

[`wishenka/web/static/app.js`](../../wishenka/web/static/app.js) and
[`wishenka/web/static/settings.js`](../../wishenka/web/static/settings.js) complete the extraction
of inline JavaScript and inline `on*` event handlers from SSR templates so a strict
`Content-Security-Policy` without `'unsafe-inline'` for scripts can be enforced.

- **Static JS architecture and `defer` load order**:
  - `wishenka/web/templates/base.html` loads external and static classic scripts in order:
    `telegram-web-app.js`, `htmx.org@1.9.12`, `json-enc.js`, `<script src="/static/app.js" defer>`,
    `<script src="/static/wishlist.js" defer>`, and `<script src="/static/receipt.js" defer>`.
  - `wishenka/web/templates/settings.html` extends `base.html` and appends
    `<script src="/static/settings.js" defer></script>` at the end of `{% block content %}` so it
    executes after `/static/app.js`.
  - Both `app.js` and `settings.js` are wrapped in an IIFE with `'use strict'` and JSDoc
    annotations, emitting no `console.log` or `console.debug` statements.
- **`window.prepareCsrf` bridge**:
  - `app.js` manages CSRF token fetching, 10 s timeout (`CSRF_TIMEOUT_MS = 10000`), and in-flight
    deduplication via `prepareCsrf()`, and explicitly exposes `window.prepareCsrf = prepareCsrf`.
  - `settings.js` (`settingsFetch()`) calls `window.prepareCsrf()` before `PATCH`/`PUT`/`POST`
    requests on `/settings` and attaches `X-CSRF-Token`. Because both scripts load with `defer`
    in order and `settingsFetch()` runs inside user-triggered event handlers, `window.prepareCsrf`
    is always initialized before invocation.
- **`<body>` and `.settings-page` `data-*` contracts**:
  - `<body>` in `base.html` provides `data-viewer-identified="true"` (when authenticated/identified,
    enabling `prepareCsrf()`, `htmx:confirm` queuing, and `X-CSRF-Token` / `Idempotency-Key`
    injection in `app.js`) and localized fallback strings: `data-i18n-prepare-error`,
    `data-i18n-busy-error`, `data-i18n-receipt-failure`, `data-i18n-receipt-summary`,
    `data-i18n-item-unavailable`, `data-i18n-list-changed`, and `data-i18n-request-failed` (see the
    WISHENKA-294 section).
  - `.settings-page` in `settings.html` provides localized strings read by `settings.js` via
    `getI18n()`: `data-i18n-saved`, `data-i18n-birthdate-source-explicit`,
    `data-i18n-invalid-birthdate`, `data-i18n-invalid-notification`, `data-i18n-state-enabled`,
    `data-i18n-state-disabled`, `data-i18n-delete-completed`, and `data-i18n-delete-failed`,
    plus the pending, rejection, reconciliation, retry, reload and deletion-outcome strings added
    by WISHENKA-291 (see
    [Personal Settings Screen](#personal-settings-screen-wishenka-291)).
- **Delegated click handlers (`handleDelegatedClick` in `app.js`)**:
  - Replaces all six inline `onclick` attributes across three dynamically swapped partials using a
    single `document.addEventListener('click', handleDelegatedClick)` listener:
    - `[data-clear-target]`: queries the target selector and sets `container.innerHTML = ''`. Used
      by `partials/item_edit_modal.html` (`.btn-modal-close`, `.btn-cancel` ->
      `#item-modal-container`), `partials/item_archive_modal.html` (`.btn-modal-close` ->
      `#item-modal-container`), and `partials/item_preview_card.html` (`.btn-preview-dismiss` ->
      `#quick-add-preview-target`).
    - `[data-qty-step][data-qty-target]`: reads `data-qty-step` (`-1` or `1`) and steps the target
      `<input>` (`#item-quantity-input` in `partials/item_edit_modal.html`), clamping to
      `[min, max]` with `DEFAULT_QTY_MIN = 1` and `DEFAULT_QTY_MAX = 1000` and falling back to `min`
      when the input value is empty or `NaN`.
- **Zero-inline-script / zero-inline-handler CSP readiness invariant and regression tests**:
  - Rendered HTML pages (`base.html` descendants) and dynamically loaded fragments must contain
    zero inline `<script>` elements (without `src`) and zero inline `on*` event-handler
    attributes.
  - `tests/test_csp_inline_removal_repro.py` verifies `/static/app.js` and `/static/settings.js`
    HTTP serving, zero inline scripts/handlers on owner (`/web/wishlists/{id}`) and public share
    (`/share/{token}`) pages, `defer` script order, and zero `on*` attributes plus `data-*`
    controls on `item_edit_modal.html`, `item_archive_modal.html`, and `item_preview_card.html`.
  - `tests/test_receipt_static_script.py` enforces zero inline `<script>` elements on `base.html`
    pages, verifies `/static/app.js` serving and `defer` order, and preserves isolation of
    `X-Reorder-Refusal` (`wishlist.js`) and `X-Receipt-Refusal` (`receipt.js`).

#### 9.9. Modal CSS Layering, `htmx:beforeSwap` & OOB Error Contracts (WISHENKA-160)

- **Modal CSS & Layering (`static/miniapp.css`)**:
  - `:root` defines `--layer-modal: 100` (equal to `--layer-receipt: 100` and above
    `--layer-quick-add: 40`), so `.modal-backdrop` (`position: fixed; inset: 0;
    z-index: var(--layer-modal)`) renders above `#quick-add-bar` and page content.
  - `.modal-sheet` renders as a scrollable bottom sheet (`max-width: var(--content-width)`,
    `max-height: 90vh`, `overflow-y: auto`, `padding-bottom: max(1rem, env(safe-area-inset-bottom))`)
    on mobile and centers as a rounded dialog at `@media (min-width: 640px)`.
  - Modal forms, alerts (`.alert-error`, `.alert-warning`), and action buttons (`.btn-save`,
    `.btn-archive-item`, `.btn-confirm-archive`, `.btn-cancel`, `.btn-modal-close`) enforce
    `min-height: var(--touch-target)` (`44px`). `.modal-sheet` sets `--receipt-bg`,
    `--receipt-text`, `--focus: var(--receipt-text)`, `:is(h1, h2, h3) { color: inherit; }`, and
    paired `--receipt-bg` / `--receipt-text` on `.btn-modal-close` / `.btn-cancel` (see
    [Scoped Telegram Theme Boundary](#scoped-telegram-theme-boundary)).
- **Inline Archive Target (`partials/item_edit_modal.html`)**:
  - `.btn-archive-item` carries `hx-target="#item-modal-container"` and `hx-swap="none"` so
    archive OOB responses never overwrite the button element itself.
- **Scoped `htmx:beforeSwap` 4xx/5xx Opt-In (`static/app.js`)**:
  - `htmx.org@1.9.12` sets `detail.shouldSwap = false` and `detail.isError = true` for any
    response with `status >= 400`. `static/app.js` registers a scoped `htmx:beforeSwap` listener that
    sets `detail.shouldSwap = true` and `detail.isError = false` only when `xhr.status >= 400`,
    `Content-Type` includes `text/html`, and one of the following holds:
    1. `detail.target.id` is `item-modal-container`, `item-edit-sheet`, or `item-archive-modal`;
    2. `detail.elt.closest('#item-modal-container')` is truthy; or
    3. `detail.target.id === 'items-list'` and `xhr.responseText` contains an `hx-swap-oob`
       fragment for `id="item-modal-container"`.
  - **Explicit Exclusions**: Responses carrying `X-Reorder-Refusal` (handled by `wishlist.js`
    `htmx:responseError`), `X-Receipt-Refusal` (handled by `receipt.js` `htmx:beforeSwap`),
    requests matching `reservationRequestPath(detail.elt)` (handled by `static/app.js`
    `htmx:afterRequest`), and non-HTML (e.g., JSON) responses are left untouched.
- **Server Error Response Contracts (`wishenka/web/routes/items_ui.py`)**:
  - **Recoverable create/edit-modal errors (`400` validation in `submit_new_item` with
    `is_edit=False` and in `submit_edit_item` with `is_edit=True`, plus `409` Reduction Lock and
    `503` Busy in `submit_edit_item`)**: `_render_item_modal_error` returns
    `partials/item_edit_modal.html` with `HX-Retarget: #item-modal-container` and
    `HX-Reswap: innerHTML` headers, preserving submitted form values (and collaborative recipient
    options/selection) while displaying `[role="alert"]` inside the modal without touching
    `#items-list` or `#item-card-{item_id}`.
  - **Unrecoverable modal/quick-add errors (`409` `WishlistArchivedError`, `404` missing/deleted/
    forbidden resource, quick-add `400` validation)**: `_modal_domain_error_response` /
    `_oob_modal_notice` return `text/html` `hx-swap-oob` fragments that clear
    `#item-modal-container` and write a localized notice into `#list-notice` via `oob_text`.

#### 9.10. External Product Image Lazy-Loading, No-Referrer & Broken-Image Fallback (WISHENKA-107)

External product thumbnails (`item.image_url`, `preview.image_url`, `form.image_url`) are rendered
across three Jinja2 partials with privacy, performance, and CSP-safe broken-image handling:

- **Template Contracts (`wishenka/web/templates/partials/`)**:
  - [`partials/item_card.html`](../../wishenka/web/templates/partials/item_card.html),
    [`partials/item_preview_card.html`](../../wishenka/web/templates/partials/item_preview_card.html),
    and [`partials/item_edit_modal.html`](../../wishenka/web/templates/partials/item_edit_modal.html)
    render `<img>` elements with:
    - `loading="lazy"` — defers off-screen image fetches until near the viewport.
    - `referrerpolicy="no-referrer"` — prevents leaking the TMA origin in `Referer` headers and
      avoids third-party hotlink rejections.
    - `data-img-fallback` — opts the image into the global capture-phase fallback handler.
  - Each `<img>` is paired with a pre-rendered sibling placeholder in the same parent container:
    `<div class="item-thumbnail-placeholder ..." aria-hidden="true" hidden>🎁</div>`.
  - When `image_url` is absent, `item_card.html` renders the visible `.item-thumbnail-placeholder`
    (without `hidden`), whereas `item_preview_card.html` and `item_edit_modal.html` omit the
    thumbnail/placeholder block altogether.
- **Thumbnail CSS & `[hidden]` Override (`static/miniapp.css`)**:
  - [`wishenka/web/static/miniapp.css`](../../wishenka/web/static/miniapp.css) defines
    `.item-thumbnail` and `.item-thumbnail-placeholder` at `3rem × 3rem` (`border-radius: 0.375rem`,
    `flex-shrink: 0`) for cards and previews, plus `--lg` modifiers (`.item-thumbnail--lg`,
    `.item-thumbnail-placeholder--lg` at `4rem × 4rem`) for `partials/item_edit_modal.html`.
  - `.item-thumbnail[hidden], .item-thumbnail-placeholder[hidden] { display: none; }` is required
    so the HTML `hidden` attribute overrides `.item-thumbnail-placeholder`'s `display: flex`.
- **Capture-Phase Fallback Handler (`handleImageError` in `static/app.js`)**:
  - [`wishenka/web/static/app.js`](../../wishenka/web/static/app.js) registers
    `document.addEventListener('error', handleImageError, true)` in the **capture phase** (because
    `error` events on `<img>` do not bubble). This covers both initial SSR HTML and dynamically
    swapped HTMX partials without inline `onerror` attributes (preserving strict CSP readiness).
  - When `event.target` is an `<img>` with `data-img-fallback`, `handleImageError` sets
    `target.hidden = true` and reveals `target.parentElement.querySelector('.item-thumbnail-placeholder')`
    (`placeholder.hidden = false`).
  - Do **not** inspect `img.complete && img.naturalWidth === 0` on `DOMContentLoaded`: with
    `loading="lazy"`, off-screen images not yet fetched can report `complete === true` and
    `naturalWidth === 0` before any network request is made.
- **Verification**: `tests/test_item_image_loading_repro.py` verifies SSR/HTMX template attributes,
  `.item-thumbnail[hidden]` / `--lg` CSS rules, capture-phase `handleImageError` behavior, and
  absence of inline `on*` handlers.

---

## HTTP Endpoints Reference

| Endpoint | Method | Auth | CSRF | Description |
| :--- | :---: | :---: | :---: | :--- |
| `/` | `GET` | No | No | Returns the Telegram Mini App HTML shell. |
| `/api/auth/csrf` | `GET` | Yes | No | Issues session-bound CSRF token for forms. |
| `/api/wishlists` | `GET` | Yes | No | Lists user's wishlists (owner and member). |
| `/api/wishlists` | `POST` | Yes | Yes | Creates a personal wishlist; `name` is required (trimmed, 1-255), otherwise `422`. |
| `/api/wishlists/deleted` | `GET` | Yes | No | Lists owner's soft-deleted wishlists within retention window. |
| `/api/wishlists/{id}` | `GET` | Yes | No | Returns wishlist details and item view. |
| `/api/wishlists/{id}` | `PATCH` | Yes | Yes | Updates title, description, or event. |
| `/api/wishlists/{id}` | `DELETE` | Yes | Yes | Owner soft-deletes the list (`200` idempotent in the retention window, `409` archived, `410` after the window, uniform `404` for non-owner or unknown). |
| `/api/wishlists/{id}/restore-deleted` | `POST` | Yes | Yes | Restores owner's soft-deleted wishlist with token rotation (`410` if expired). |
| `/api/wishlists/{id}/members` | `GET` | Yes | No | Returns list of members and roles. |
| `/api/wishlists/{id}/members/{uid}/role` | `PATCH` | Yes | Yes | Updates role (Owner only). |
| `/api/wishlists/{id}/members/{uid}` | `DELETE` | Yes | Yes | Removes member from wishlist. |
| `/api/wishlists/{id}/invite/reset` | `POST` | Yes | Yes | Rotates collaborator invite token. |
| `/api/invitations/preview` | `GET` | No | No | Previews invitation details via header. |
| `/api/invitations/accept` | `POST` | Yes | Yes | Accepts invite and joins wishlist. |
| `/api/favorites` | `GET` | Yes | No | Lists user's favorited wishlists. |
| `/api/favorites/{id}` | `POST` | Yes | Yes | Adds wishlist to user's favorites. |
| `/api/favorites/{id}` | `DELETE` | Yes | Yes | Removes wishlist from favorites. |
| `/api/history` | `GET` | Yes | No | Lists up to 20 recent wishlists. |
| `/api/history/{id}` | `POST` | Yes | Yes | Records wishlist viewing in history. |
| `/api/history` | `DELETE` | Yes | Yes | Clears viewing history for caller. |
| `/web/wishlists/{wishlist_id}` | `GET` | Optional | No | Renders TMA wishlist detail HTML page. |
| `/web/wishlists/{wishlist_id}/items/preview` | `POST` | Yes | Yes | Classifies input & renders preview card. |
| `/web/wishlists/{wishlist_id}/items/quick` | `POST` | Yes | Yes | Quick-adds item & returns card + OOB reset. |
| `/web/wishlists/{wishlist_id}/items/new` | `GET` | Yes | No | Renders prepopulated item creation modal. |
| `/web/wishlists/{wishlist_id}/items/new` | `POST` | Yes | Yes | Creates item from creation modal (`201`) or returns `400` modal with preserved state. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/edit` | `GET` | Yes | No | Renders item edit modal with Reduction Lock. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/edit` | `POST` | Yes | Yes | Saves item edits or returns 409 modal. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/archive` | `POST` | Yes | Yes | Archives item & removes card via OOB swap. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/restore` | `POST` | Yes | Yes | Restores archived item & renders card. |
| `/web/wishlists/{wishlist_id}/items/reorder` | `POST` | Yes | Yes | Persists full manual order (`item_ids`); returns items list. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/move?direction=up\|down` | `POST` | Yes | Yes | Moves item one step; returns items list. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/archive-confirm` | `GET` | Yes | No | Renders archive confirmation modal. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/receipt` | `GET` | Yes | No | Renders the receipt dialog; a refusal is the blocked dialog with `X-Receipt-Refusal`. |
| `/web/wishlists/{wishlist_id}/items/{item_id}/receipt` | `POST` | Yes | Yes | Records a receipt; answers with OOB fragments (201) or a marked refusal. |
| `/web/reservations/card` | `GET` | Yes | No | Home card. Badge is distinct wishes. |
| `/web/reservations` | `GET` | Yes | No | Cabinet page of the caller's promises. |
| `/web/reservations/list` | `GET` | Yes | No | Cabinet list partial used on refresh. |

---

## Structured UI Observability Events

The HTMX wish item UI router (`wishenka.web.items_ui`) emits structured telemetry records via
`extra={...}`:

| Event Name | Level | Context Attributes | Description |
| :--- | :---: | :--- | :--- |
| `ui_item_quick_add_preview` | `INFO` | `wishlist_id`, `actor_id`, `user_id`, `input_type`, `domain`, `store_name`, `is_fallback`, `duration_ms` | Universal input classified and preview or fallback rendered. |
| `ui_item_quick_add_success` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `has_link`, `price`, `quantity` | Wish item created via Quick Add Bar. |
| `ui_item_create_success` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `has_link`, `price`, `quantity` | Wish item created via detailed creation modal (`submit_new_item`). |
| `ui_item_create_validation_error` | `WARNING` | `stage`, `status_code`, `wishlist_id`, `actor_id`, `user_id` | Creation modal form rejected with HTTP 400 (`stage="form"` or `"domain"`); user input omitted. |
| `ui_item_edit_opened` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `mode`, `received_quantity` (edit only), `is_collaborative` | Item modal opened (`mode="create"` or `mode="edit"`). |
| `ui_reduction_lock_rejected` | `WARNING` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `requested_quantity`, `received_quantity` | Edit rejected (HTTP 409) due to quantity below received units. |
| `ui_item_edit_busy` | `WARNING` | `wishlist_id`, `item_id` | Edit modal returned HTTP 503 (`InventoryBusyError`); names no gifter. |
| `ui_item_edit_validation_error` | `WARNING` | `stage`, `status_code`, `wishlist_id`, `item_id`, `actor_id`, `user_id` | Edit form rejected with HTTP 400 (`stage="form"` or `"domain"`); user input omitted. |
| `ui_item_quick_add_validation_error` | `WARNING` | `reason`, `status_code`, `wishlist_id`, `actor_id`, `user_id` | Quick-add rejected with HTTP 400 (`empty_title`, `parse_error`, or `domain_validation`). |
| `ui_modal_domain_error` | `WARNING` | `operation`, `error_type`, `status_code`, `wishlist_id`, `item_id`, `actor_id`, `user_id` | Modal/UI endpoint hit `WishlistArchivedError` (409) or missing/forbidden resource (404). |
| `ui_item_edit_saved` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `quantity`, `has_recipient` | Wish item edits persisted via detailed edit modal. |
| `ui_item_archived` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id` | Wish item archived via HTMX UI. |
| `ui_item_restored` | `INFO` | `wishlist_id`, `item_id`, `actor_id`, `user_id` | Archived wish item restored via HTMX UI. |

The receipt router (`wishenka.web.receipts_ui`, WISHENKA-24, WISHENKA-153) writes
`ui_receipt_form_opened`, `ui_receipt_entry_form_opened`, `ui_receipt_form_refused`,
`ui_receipt_entry_form_refused`, `receipt_recorded_http`, `receipt_corrected_http`,
`receipt_cancelled_http`, `receipt_refused` and `receipt_inventory_busy` with `wishlist_id`, `item_id`, `actor_id` (plus `receipt_id` for
entry-level events) and, for refusals, `reason`, `http_status` and (two reasons only)
`remaining_quantity`. No `user_id` or title. The table is in
[gift-receipt.md](gift-receipt.md#log-events-of-the-ui).

### Telemetry Privacy Invariants
- **Zero Raw URLs Logged**: Only the normalized hostname (`domain`, e.g., `ozon.ru`) and canonical
  `store_name` are recorded; full URLs, paths, and query parameters are never written to logs.
- **Zero Secrets or Capability Tokens**: `public_token`, `invite_token`, and session tokens are
  never logged.
- **Surprise Invariant in Logs**: Edit UI logs omit occupied quantities and gifter identities.

---

## Configuration Reference

The following settings configure the Mini App and web security layer:

| Setting | Env Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| `application_origin` | `WISHENKA_APPLICATION_ORIGIN` | `http://testserver` | Expected Origin. |
| `csrf_secret_key` | `WISHENKA_CSRF_SECRET_KEY` | `wishenka_csrf...` | CSRF secret key. |
| `telegram_bot_username` | `WISHENKA_TELEGRAM_BOT_USERNAME` | `""` | Bot username for URLs. |
| `telegram_app_short_name`| `WISHENKA_TELEGRAM_APP_SHORT_NAME` | `""` | App name for deep links. |

---

## Troubleshooting & Common Issues

### 1. `403 Invalid origin`
- **Cause**: The `Origin` header sent by the client does not match `WISHENKA_APPLICATION_ORIGIN`.
- **Solution**: Set `WISHENKA_APPLICATION_ORIGIN` to match the actual domain serving the Mini App
  (e.g., `https://app.wishenka.example.com`).

### 2. `403 Invalid CSRF token`
- **Cause**: The request is missing the `X-CSRF-Token` header, or the token was derived from an
  expired or mismatched session cookie.
- **Solution**: Ensure the frontend requests `GET /api/auth/csrf` after session establishment and
  includes the token on all mutating requests.

### 3. `404 Invitation not found`
- **Cause**: The invitation token is expired (default TTL 7 days), malformed, or was rotated via
  `POST /api/wishlists/{id}/invite/reset`.
- **Solution**: Have a wishlist manager generate and share a new invitation link.

### 4. `409 Wishlist is archived`
- **Cause**: Mutation attempt (editing settings, resetting tokens, adding members) on an archived
  wishlist.
- **Solution**: Restore the wishlist via `POST /api/wishlists/{id}/restore` before editing.

### 5. Clipboard Copy Fails in Telegram WebView
- **Cause**: Some mobile WebViews restrict `navigator.clipboard` access without direct user gesture.
- **Solution**: The Mini App provides an explicit fallback input displaying the link so users
  can manually select and copy if the automated API fails.

### 6. `400 Cannot favorite own wishlist`
- **Cause**: An owner attempted to favorite their own wishlist via `POST /api/favorites/{id}`.
- **Solution**: The UI suppresses the favorite button on owned lists. On direct API calls, verify
  that caller does not match `wishlist.owner_id`.

### 7. `404 Wishlist not found` on Favorites or History
- **Cause**: The referenced wishlist does not exist or has been soft-deleted (`DELETED`).
- **Solution**: Deleted wishlists cannot be favorited or viewed in history. Ensure the wishlist ID
  is valid and active.

### 8. `409 Conflict` When Saving Item Quantity in Edit Modal (`ui_reduction_lock_rejected`)
- **Cause**: The requested `quantity` is below the number of already received units.
- **Solution**: The server preserves the fields in the HTTP 409 modal. Set `quantity` to at
  least `max(1, received_quantity)` and submit again.

### 9. Quick Add Bar (`#quick-add-bar`) Not Displayed on Wishlist Page
- **Cause**: The caller is viewing the wishlist as a guest/gifter (not an `OWNER`, `ADMIN`, or
  `MEMBER`), or the wishlist is in `ARCHIVED` status.
- **Solution**: Authenticate as an active wishlist member and ensure the wishlist is `active`.

### 10. Home Screen Has No «Мои бронирования» Card

- **Cause**: The caller has no session, so `GET /web/reservations/card`
  is HTTP 401. Or `showHome` did not run, because `publicView` or
  `invitationView` is showing a shared or invite link. Or the card
  fetch failed. A failed fetch leaves the three wishlist sections.
- **Solution**: Open the home screen with a session. The badge and the
  cabinet are documented in
  [reservations.md](reservations.md#7-my-reservations-cabinet).

### 11. Reorder Returns `400` or Drag-and-Drop Does Nothing
- **Cause**: `item_ids` is not an exact permutation of active items (stale page after another
  editor archived/added an item), or the card is not `draggable="true"` (non-editor view).
- **Solution**: Reload the wishlist page and retry; logged as `ui_items_reorder_rejected`.
  The stale-order 400 carries `X-Reorder-Refusal: stale_order`; `wishlist.js` then shows a notice
  in `#list-notice` and reloads the page by itself after 800 ms.

### 12. Touch Drag Does Nothing or the Mini App Minimises
- **Cause**: The gesture did not start on `.item-drag-handle` (only the handle starts it; a swipe on
  the rest of the card scrolls), the pointer is a pen or mouse (native HTML5 drag applies), or the
  reorder was skipped (see the `console.warn` texts in 9.8.1). Telegram older than Bot API 7.7
  cannot disable vertical swipes, so the Mini App can minimise on a downward swipe.
- **Solution**: Start from the `⠿` handle of a collapsed card, or use the move up and move down
  buttons in the card details. A tap shorter than 4 px does nothing by design. A drop on the card
  itself is ignored. After a drag, a tap within 400 ms is swallowed; tap again.

### 13. Receipt Dialog Shows Only a Generic Sentence or Nothing
- **Cause**: htmx 1.9.12 does not swap 4xx and 5xx answers. The dialog shows a refusal only when
  the answer carries `X-Receipt-Refusal` with a value of the closed set (`receipt.js`
  `REFUSAL_REASONS`); an unmarked error (network, 500) gives «Не удалось сохранить отметку.
  Повторите попытку.». The same default hides the errors of the older edit and archive modals
  (WISHENKA-160).
- **Solution**: Check the response headers of the `/web/.../receipt` request. See
  [gift-receipt.md](gift-receipt.md#refusals-and-the-marker-header).

### 14. External Product Thumbnail Shows Placeholder or Remains Visible Alongside It
- **Cause**: Either the external CDN returned an error (403/404/timeout) and `handleImageError` in
  `static/app.js` swapped the broken `<img>` for `.item-thumbnail-placeholder`, or the `[hidden]`
  CSS rule in `static/miniapp.css` is missing/overridden so `display: flex` keeps the hidden
  placeholder visible.
- **Solution**: Verify `img[data-img-fallback]` and its sibling `.item-thumbnail-placeholder[hidden]`
  share the same parent container, `static/app.js` is loaded, and
  `.item-thumbnail[hidden], .item-thumbnail-placeholder[hidden] { display: none; }` is present in
  `static/miniapp.css`.

### 15. Dark-Theme Modal Heading, Focus Ring, or Close Button Low Contrast

- **Cause**: A global rule (`h1, h2, h3 { color: var(--ink); }`, `:focus-visible`, or `button`
  surface colors) overrides the sheet's Telegram theme pair (`--receipt-bg` / `--receipt-text`),
  or a template renders `.modal-header` outside `.modal-sheet`.
- **Solution**: Keep the container inside `.receipt-sheet` or `.modal-sheet` (which set
  `--focus: var(--receipt-text)` and `:is(h1, h2, h3) { color: inherit; }`), ensure
  `.modal-header h2 { color: inherit; }` and `.btn-modal-close` / `.btn-cancel` sheet overrides
  remain intact, and verify with `tests/test_visual_identity_browser.py` and
  `tests/test_receipt_theme_browser.py`.

### 16. Server Page Shows JSON, or a Message Is Hidden or Silent (WISHENKA-294)

- **Cause**: The client sent `Accept: */*`, JSON, `HX-Request`, or the path is not one of the
  three page URLs (the unavailable page stays JSON there); or `#feedback` / `#status` lost
  `position: sticky` or `data-kind`; or a control is not wrapped in `pending()`.
- **Solution**: Check the request `Accept` header and `PAGE_PATHS` in
  `wishenka/web/unavailable.py`; look for the `unavailable_page_rendered` log event; verify
  `#feedback` exists in `base.html` and run `tests/test_cross_screen_comfort_browser.py`.

### 17. Delete Zone Is Missing or Delete Fails (WISHENKA-295)

- **No "Delete wishlist..." in the settings**: only the owner of an `active` list gets it. Check
  `data-retention-days` on `<main id="app">`: if it is missing, zero or not an integer the zone is
  hidden on purpose.
- **Generic failure text after confirming**: the client never shows the reason. Check the server
  logs for `wishlist_delete_not_found` / `wishlist_delete_denied` (404),
  `wishlist_archived_mutation_blocked` (409, the list must be unarchived first) or `wishlist_retention_expired` (410) and the request
  log.
- **List stays visible after a success text**: reload the home screen; the list should be under
  "Recently deleted" with `days_left`.
