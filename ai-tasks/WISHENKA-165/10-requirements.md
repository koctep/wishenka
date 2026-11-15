# WISHENKA-165: Consistent presentation and currency defaults

## Goals

Make the wishlist interface consistent and readable in Telegram's light and dark themes, and
reduce the risk that presentation and currency choices drift when the product is maintained.
The business reason is inferred from the Jira debt description and WISHENKA-24 finding C-6.

## User Stories

- As a wishlist participant, I can read receipt status and notices in both light and dark themes.
- As a wishlist owner, I see a consistent default currency when creating, editing, previewing,
  archiving, and reviewing received wishes.
- As a wishlist owner, I can choose the same supported currencies in the edit form as before.
- As a maintainer, I can change shared presentation and currency choices consistently.

## Definition of Done

- Receipt and notice text, surfaces, and status indications remain legible in light and dark
  Telegram themes, including when theme information is unavailable.
- Existing receipt layout, overlay order, touch targets, and stale-page reload behavior are
  preserved unless a readability adjustment is needed.
- Wishes without a currency consistently display and default to RUB in the affected views and
  form; explicitly selected currencies are preserved.
- The edit form continues to offer RUB, USD, EUR, KZT, and BYN with their existing symbols.
- Repeated presentation values, the stale reload delay, the default currency, and the currency
  options are maintained consistently across their affected uses.
- Existing gift receipt, wishlist, and currency behavior remains intact; checks cover the affected
  display and defaulting behavior in both themes.

## Task Description

The receipt work exposed repeated visual values, theme-independent text colors, and duplicated
currency defaults and options. This debt makes visual consistency and future maintenance harder.
The scope is the existing wishlist and receipt presentation, stale reload timing, and currency
defaults and options referenced by WISHENKA-24 C-6 and Jira WISHENKA-165. Currency conversion,
new currencies, changes to prices, and redesign of unrelated screens are outside scope.

Business entities are a wish (including optional price and currency), a currency (code and display
symbol), and a theme (light, dark, or unavailable). A wishlist owner edits a wish and reviews it;
participants view wishes and receipt notices in the active theme.

Implementation languages: Python, JavaScript, CSS, and HTML templates.

## Q&A

- **Why address technical constants?** To keep the interface readable and currency defaults
  consistent while making later changes less error-prone. This is inferred from C-6 and the task.
- **What happens when currency is absent?** Preserve the existing RUB default; the product
  specification describes currency as optional (`in-docs/spec.md`, wish fields).
- **Must the reload delay change?** No. Preserve its existing timing while making it consistent.
- **Sources:** Jira WISHENKA-165 and `ai-tasks/WISHENKA-24/60-tech-debt.md`, C-6 and T-6.
