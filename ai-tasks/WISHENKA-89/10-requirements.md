# WISHENKA-89: Localization of Server-Rendered Templates and Sharing/UI Views

## Goals

Eliminate mixed-language (Russian/English) user interfaces in all server-rendered web pages, interactive fragments, and sharing/collaboration flows. While core navigation, settings, and bot messaging already support Russian (`ru`) and English (`en`), the remaining server-rendered wishlist, item, sharing, invitation, and reservation views still display hardcoded Russian strings—even when an authenticated Telegram user or an anonymous visitor has an English locale active.

Completing localization for these views ensures a consistent, trustworthy multilingual experience across the entire web application.

## User Stories

1. **As an authenticated Telegram user** whose active language is English (auto-detected from Telegram or explicitly selected in settings), **I want** all wishlist detail pages, item creation/editing/archiving/receipt modals, item cards, member lists, and my reservations cabinet to appear in English **so that** I never encounter untranslated Russian labels or error messages.
2. **As an authenticated Telegram user** whose active language is Russian, **I want** all of those same pages, modals, and status messages to appear in natural Russian **so that** my experience remains seamless.
3. **As an anonymous visitor or giver** opening a public shared wishlist link or a co-author invitation link, **I want** the shared wishlist page, item cards, reservation controls, invitation preview, and error states to match my preferred language **so that** I can understand and interact with the wishlist without language barriers.
4. **As a wishlist owner or co-author**, **I want** sharing dialogs, member role badges, and server-side validation/conflict/confirmation messages to be displayed in my active language **so that** managing collaborators and items is clear in both supported languages.

## Definition of Done

1. **Full Template Coverage**: All server-rendered pages and partial UI fragments (wishlist detail, public shared wishlist, invitation preview/error, reservations cabinet, item cards, item quick-add/preview, item edit/archive/receipt modals, archived/gifted sections, share modal, member list, reservations list/card, and any remaining hardcoded strings in base/partially migrated templates) render all static UI text, labels, placeholders, aria-labels, confirmation prompts, and empty states in the resolved active locale (`ru` or `en`).
2. **Full UI Route Coverage**: All server-rendered UI endpoints (including sharing, invitation join, member management, item UI actions, receipt recording, and reservation UI fragments) resolve the active locale for the request and return localized validation errors, conflict notices, status labels, and confirmation messages.
3. **Locale Detection & Fallback**:
   - Authenticated Telegram users receive content in their saved profile language (derived from Telegram language settings or explicit user choice, with English as the fallback for unsupported languages).
   - Unauthenticated visitors (such as public share-link or invitation-link viewers) receive content in the explicitly requested language if provided, otherwise in their browser's preferred language, falling back to English when unsupported.
4. **Locale-Aware Formatting**: User-facing dates (such as wishlist event dates) and dynamic counts/quantities are formatted appropriately for the active locale (`ru` vs `en`) rather than using a single hardcoded format.
5. **No Untranslated Hardcoded UI Text**: No hardcoded Russian or English UI literals remain in the in-scope server-rendered templates or UI route responses; user-generated content (wishlist titles, item names, descriptions, custom recipient names) remains untouched.
6. **Automated Verification**: Automated tests verify both `ru` and `en` rendering across the localized pages, fragments, and UI error/notice responses, including anonymous locale fallback behavior.

## Task Description

### Problem & Current State

Previous localization work (`WISHENKA-33`) established the application's language resolution mechanism and localized the base layout shell (`base.html`), user settings (`settings.html`), bot messages, and a small subset of item modal strings. However:

- **Unlocalized Pages**: The wishlist detail view, public shared wishlist view, invitation preview/error view, and reservations cabinet page contain hardcoded Russian text and fixed date formatting.
- **Unlocalized / Partially Localized Fragments**: Most partial templates (member list, share modal, item quick-add, item preview, item archive modal, archived items section, gifted items section, reservations list, reservations card) have no localization at all, and partially migrated fragments (item card, item edit modal, item receipt modal) still contain numerous hardcoded Russian labels, badges, and button captions.
- **Unlocalized UI Route Responses**: Several UI route handlers (in sharing, item UI, receipt UI, and reservation UI) do not resolve the request locale and emit hardcoded Russian strings for role labels, validation errors, conflict notices, and action confirmations.

### Scope Boundaries & Non-Goals

- **Implementation Language**: Python (server-side web routes and Jinja2 HTML templates).
- **Supported Locales**: Russian (`ru`) and English (`en`) only; adding additional languages is out of scope.
- **Out of Scope (Tracked Separately)**:
  - Client-side Mini App JavaScript views (`miniapp.js`) — tracked in `WISHENKA-73`.
  - Profile locale endpoint cleanup and duplicate DB lookup optimization — tracked in `WISHENKA-192`.
  - Notice locale helper consolidation and migration/concurrency tests — tracked in `WISHENKA-193`.
- **User-Generated Content**: User-entered data (wishlist titles, item titles, notes, custom recipient names) is never translated.

## Q&A

- **Q: Why is this task needed if `WISHENKA-33` already added i18n?**
  **A:** `WISHENKA-33` built the core i18n foundation and localized the settings page and bot notifications, but left the majority of server-rendered wishlist, sharing, invitation, item, and reservation templates and UI routes with hardcoded Russian strings. As a result, English-locale users currently see a jarring mix of English navigation and Russian content.
- **Q: How should locale be determined for users who have not opened the app via Telegram (e.g., anonymous public share visitors)?**
  **A:** Authenticated users use their profile locale (which reflects their Telegram language code or explicit preference). Anonymous visitors use an explicit language query parameter if present, otherwise their browser's language preference, defaulting to English (`en`) for unsupported languages.
- **Q: Are Mini App client-side JavaScript views included in this task?**
  **A:** No. Client-side JavaScript localization is explicitly scoped to `WISHENKA-73`.
