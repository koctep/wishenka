# WISHENKA-119: Russian Busy Message in the Wish Edit Modal

## Goals

Ensure that a wish owner editing a wish in the web interface sees a clear, localized error message in their active language—specifically in Russian when using the Russian locale—when the wish is temporarily busy and the edit cannot be saved. This eliminates mixed-language UI feedback while preserving the surprise invariant (never revealing gifter identities) and keeping the user's entered form data intact so they can retry without retyping.

## User Stories

- **As a Wish Owner (Russian locale)**, when I submit edits to a wish that is temporarily busy, I want to see a Russian error message explaining that the wish was busy, my changes were not saved, and I can submit the form again, with the edit modal staying open and my entered values preserved, so I understand what happened in my language and can immediately retry.
- **As a Wish Owner (English locale)**, when I submit edits to a wish that is temporarily busy, I want to see the equivalent English error message with the edit modal staying open and my entered values preserved, so I can immediately retry.
- **As a Gifter**, I want the busy error message shown to the wish owner to never name or hint at any gifter, so that my gift reservation remains a surprise.
- **As an API Consumer**, when a wish edit fails because the wish is busy, I want the API error detail to remain in English and omit any gifter information, so existing API contracts remain stable.

## Definition of Done

1. When a wish edit submission via the web edit modal fails because the wish is temporarily busy:
   - The response status is HTTP 503 (Service Unavailable) and the edit modal remains open.
   - All submitted form fields remain populated with the user's entered values.
   - The wish's stored data remains unchanged.
   - In the Russian locale (`ru`), the modal displays a Russian error message that states all three facts:
     - the wish was busy,
     - the edit was not saved, and
     - the form can be submitted again.
   - In the English locale (`en`), the modal displays the English error message with the same three facts.
   - In all locales, the error message names no gifter and reveals no reservation or gifter details (surprise invariant).
2. When a wish edit via the JSON API fails because the wish is temporarily busy:
   - The response status is HTTP 503 (Service Unavailable).
   - The error detail remains in English (stating that the wish was busy and the attempt changed nothing) and names no gifter.
3. Automated verification confirms both the Russian-locale and English-locale modal busy responses (HTTP 503, modal open, submitted fields preserved, localized message, no gifter named) as well as the English API busy response.

## Task Description

### Problem Context

Previously (in WISHENKA-57), the wish edit modal displayed an English busy-error sentence even though the modal itself was in Russian. Since then, multi-locale support (Russian `ru` and English `en`) was introduced across the web interface, with English (`en`) as the default fallback locale when no user or request locale preference is specified.

This task ensures the business requirement from WISHENKA-57 is fully satisfied and verified:
- **Programming language**: Python.
- **Scope**:
  - In scope: The busy error message displayed in the wish edit modal for Russian (`ru`) and English (`en`) locales, keeping the modal open at HTTP 503 with submitted fields preserved, maintaining the surprise invariant (no gifter named), and keeping the JSON API error detail in English.
  - Out of scope: Changing the default fallback locale of the application, altering SQLite locking/retry behavior, or changing other unrelated UI/API error messages.
- **Main Business Entities**:
  - **Wish**: A wishlist item being edited by an owner/co-author.
  - **Wish Owner**: The user submitting edits through the wish edit modal.
  - **Gifter**: A user who may have reserved units of the wish (identity must remain hidden from the wish owner).
  - **Edit Modal**: The interactive form dialog where wish details are modified and re-rendered with validation/busy feedback on failure.
  - **Locale**: The user's active display language (`ru` or `en`).

## Q&A

- **Why is this task needed from a business perspective?**
  Users editing wishes in Russian must not encounter an untranslated English error message inside a Russian modal; they need clear, actionable feedback in their own language without losing their form input or compromising gift surprises.
- **What changed since the original WISHENKA-57 tech-debt item was recorded?**
  Multi-locale support was added to the web interface, including a Russian translation for the edit-busy message alongside the English one, while English remains the default locale when no locale preference is provided. This task verifies and ensures complete alignment with the Russian-locale requirement (HTTP 503, modal open, submitted fields preserved, Russian sentence with the three required facts, no gifter named) and the English API detail requirement.
- **What must happen for both `ru` and `en` locales?**
  In `ru`, the modal alert shows the Russian busy sentence; in `en` (and default fallback), it shows the English busy sentence. In both cases, HTTP 503 is returned, the modal stays open with submitted values, and no gifter is named.
- **Should the JSON API error detail also be translated?**
  No. The API detail stays in English ("The wish was busy and the attempt changed nothing") and must not disclose any gifter.
