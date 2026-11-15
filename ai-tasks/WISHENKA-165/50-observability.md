# WISHENKA-165: Observability

## Assessment

This change centralizes existing currency defaults and presentation tokens. It adds no new
request, external dependency, state transition, failure branch, or timing operation. Theme
selection occurs in CSS using optional Telegram variables and fallbacks; there is no server-side
signal for the rendered palette. The existing stale-reload timer remains unchanged.

No new production logs or metrics are warranted for static constants or CSS rendering. Logging
currency values or individual theme renders would add noise without identifying a new operational
failure. The application does not gain a metrics exporter or monitoring integration in this step.

## Existing diagnostics

- `wishenka.web.items_ui` records structured warning events for busy item edits and rejected
  quantity changes, including relevant item and wishlist identifiers.
- `wishenka.items` records metadata extraction completion with domain, duration and presence
  flags, without logging extracted data structures.
- Existing logs and their levels are unchanged; this step adds no logging fields or sensitive data.

## Validation

The Step 4 and Step 5 quality gates passed (`make check`: 823 tests at Step 5). Browser tests
exercise representative light, dark and fallback themes; currency tests cover defaults and
explicit values. These validate presentation behavior but do not provide production telemetry.
No log or metric collection was changed, so no new log-format or metric-collection test applies.
Unexpected client-specific palettes remain a visual issue that cannot be measured by these logs.
