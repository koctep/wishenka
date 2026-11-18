# Developer Documentation Summary: WISHENKA-89

## Updated Files

- [`doc/dev/i18n.md`](../../doc/dev/i18n.md)

## Summary of Changes

Updated `doc/dev/i18n.md` to cover server-side rendered (SSR) web template, route, and script localization introduced in `WISHENKA-89`:

1. **Overview & Key Components**:
   - Added the SSR Web Views & Sharing Pages channel (`sharing.py`, `items_ui.py`, `receipts_ui.py`, `reservations_ui.py`, `gifted_view.py`, `base.html`, `wishlist.js`, `receipt.js`).
   - Documented `wishenka/i18n/formatters.py` (`format_date`), `web.*` namespaces in `wishenka/i18n/catalog.py`, and `_locale_context_processor` + `format_date` filter/global registration in `wishenka/web/templates.py`.
2. **API / Usage**:
   - Added `format_date(value, locale=DEFAULT_LOCALE)` signature and behavior (`DD.MM.YYYY` for `"ru"`, `MMM D, YYYY` for `"en"`, UTC normalization for naive `datetime`, `""` for `None`).
   - Added a **SSR Template & Script Localization** subsection documenting:
     - `LocaleDep` route wiring and automatic `locale` context injection via `_locale_context_processor`.
     - `web.*` catalog namespaces (`web.common.*`, `web.wishlist.*`, `web.item.*`, `web.receipt.*`, `web.share.*`, `web.invite.*`, `web.reservations.*`).
     - Jinja2 `t(...)` and `format_date` filter/global usage.
     - `data-i18n-*` attributes on `<body>` in `wishenka/web/templates/base.html` (`data-i18n-prepare-error`, `data-i18n-busy-error`, `data-i18n-receipt-failure`, `data-i18n-receipt-summary`, `data-i18n-item-unavailable`, `data-i18n-list-changed`) consumed by `base.html`, `receipt.js`, and `wishlist.js`.
   - Updated **Adding New Translation Keys** to reference `tests/test_ssr_i18n_repro.py`.
3. **Troubleshooting**:
   - Added guidance for diagnosing SSR routes/partials or client-side SSR notices falling back to English (`LocaleDep` missing on route or `data-i18n-*` attribute missing on `<body>`).
