# Telegram bot journeys and notifications

Status: design for WISHENKA-27, WISHENKA-28 and WISHENKA-29, not a claim that the
features are implemented. Product invariants and functional scope come from
[the product concept](../specs/00-high.md) and [the functional specification](spec.md).
The receipt notification transaction already exists as documented in
[Gift receipt](../doc/dev/gift-receipt.md); the remaining flows below describe intended behavior.

## Entry and navigation

A private chat `/start` without a parameter displays the menu in the user's selected language:

| Action | Outcome |
| --- | --- |
| Create wishlist | Open the Mini App at the list creation flow. |
| My wishlists | Open the Mini App at the user's list collection. |
| How it works | Explain creating, sharing and reserving without revealing hidden reservations. |
| Open Mini App | Open the Mini App at its normal entry point. |

Example: `RU: Добро пожаловать! Создайте список желаний или откройте свои списки.`
`EN: Welcome! Create a wishlist or open your wishlists.`

For a shared-list start parameter, treat the parameter as untrusted. Resolve the link and hand
its intended target to the Mini App, which independently checks access and renders the
role-appropriate list. A valid shared link opens that list directly; no separate registration or
onboarding is required. The link alone does not grant permission to add wishes. A missing,
malformed, expired, deleted, or inaccessible target produces the same generic recovery message
and menu, without confirming the target's existence or showing private content:

- RU: `Не удалось открыть список. Проверьте ссылку или откройте свои списки.`
- EN: `Could not open the list. Check the link or open your wishlists.`

A parameter-free `/start` is normal menu entry, not an error. Restarting the bot must not
implicitly save an unfinished wish. Token encoding, link lifetime and exact app handoff belong to
WISHENKA-27; no parameter or hidden content should be exposed in a failure or preview.

## Adding a wish from a message

1. A user sends or forwards plain text or a product URL to the bot. A text input becomes the
   proposed title. A URL is retained as the product link and may provide extracted product details.
2. If extraction fails, is unsupported, or returns partial data, retain the URL and let the user
   enter or correct the title and other available fields manually. Do not present guessed data as
   confirmed. Empty or otherwise invalid input asks for a usable title or link without saving.
3. Find lists where this user currently has permission to add wishes. With none, explain that an
   eligible list is needed and offer creation or obtaining an invitation; do not silently save.
   With one, select it automatically and display its name. With multiple, ask the user to choose;
   viewing a shared list alone is not write permission.
4. Show a draft with destination, title, link when present and extracted fields, all editable.
   Offer explicit Save and Cancel actions. Before Save, no wish is created. Cancel discards the
   draft and acknowledges cancellation; it does not create or change a wish.
5. On Save, validate the draft and recheck the user's current permission and target availability.
   A successful save names the destination. If validation fails, keep the draft and identify the
   correction. If permission or availability changed, explain that the list is unavailable and
   offer a new eligible list or cancellation. If saving fails, report failure and offer retry or
   cancellation; never claim success or create a duplicate as a result of a retry.

Examples:

- Zero lists: `RU: Нет доступного списка. Создайте список или получите приглашение.`
  `EN: No eligible wishlist is available. Create one or obtain an invitation.`
- Choice: `RU: Выберите список для желания.` `EN: Choose a wishlist for this wish.`
- Preview: `RU: Проверьте желание и нажмите «Сохранить».`
  `EN: Review the wish and select Save.`
- Saved: `RU: Желание сохранено в списке «{list}».`
  `EN: The wish was saved to “{list}”.`
- Failed: `RU: Не удалось сохранить желание. Повторите попытку или отмените.`
  `EN: Could not save the wish. Retry or cancel.`
- Cancelled: `RU: Добавление отменено.` `EN: Adding the wish was cancelled.`

An implementation must define draft expiry and retry mechanics while preserving these outcomes.

## Notification policy

The matrix describes intended event coverage, not a promise of current delivery. A candidate is
eligible only if they have a relevant relationship, a deliverable bot destination and the relevant
notification type enabled. A per-list setting overrides the global setting when present; otherwise
use the global setting. Apply the preference to each candidate independently. Notification type
names below are conceptual; defaults, channel eligibility, retry limits and exact UI are deferred.

Before selecting a template, link, or preview, check the person's roles for the particular wish.
Its recipient is excluded from reservation, cancellation, purchase and reservation-derived
notifications even if they are also a collaborator or giver. Suppress the entire message if its
occurrence, timing, link, preview, or content could reveal a protected event. Never replace an
unsafe event with a generic message that still signals that event. A neutral list or occasion
message is permitted only when its trigger and destination are independent of protected activity.
Links must open a view authorized for the recipient; disable or sanitize previews where necessary.

### Event matrix

- **Wish created or edited:** Relevant collaborators and affected givers where applicable;
  exclude the actor. Preference: `wish changes`. Include authorized list and wish details only,
  without reservation data. Suppress if the event or destination reveals protected activity.
- **Reservation created, changed or cancelled:** Affected giver, or other givers only where they
  need to act. Preference: `reservation changes`. Never notify the wish recipient; exclude the
  actor unless a confirmation is requested. Include only their own reservation and authorized
  wish, without other giver identities.
- **Purchase status changed:** The affected giver. Preference: `reservation changes`. Never
  notify the wish recipient; exclude the actor unless a confirmation is requested. Include only
  their own status, without other giver information.
- **Wish or list archived:** Affected collaborators and open reservation holders, excluding the
  actor. Preference: `archive`. The recipient sees only an independent, safe list change. Include
  authorized list or wish details; a giver may manage their own remaining reservation.
- **Gift receipt recorded:** Each holder of an open planned or purchased reservation.
  Preference: `receipt`. Exclude the wish recipient even with overlapping roles; send one notice
  per eligible holder per receipt. Include the wish and receipt fact only, with no quantity,
  other givers or hints of excess reservations.
- **Collaborator or membership changed:** The affected participant and authorized list managers,
  excluding the actor. Preference: `collaboration`. Include only membership or list changes within
  their permissions. Suppress if the event or link reveals protected activity.
- **Event or birthday approaches:** Users tracking the occasion or list. Preference: `reminders`.
  Include the occasion and date only where authorized; no protected event may trigger or alter
  the message, and no reservation or purchase facts may be included.

A receipt remains recorded if delivery fails. It never closes, buys, or changes a reservation:
each giver decides what to do with their own reservation. For each receipt event, enqueue at most
one notice per eligible open reservation holder, including purchased reservations, after applying
the recipient exclusion and preferences. Never include received or reserved quantities, other
givers, or a suggestion that reservations exceed the remaining quantity.

### Message examples

Variables such as `{list}` and `{wish}` are displayed only when the recipient is authorized to
see them. Localization follows the product language selected by the user. These examples do not
weaken the matrix's audience and suppression rules.

- Wish change:
  - RU: `В списке «{list}» изменено желание «{wish}».`
  - EN: `“{wish}” changed in “{list}”.`
- Own reservation:
  - RU: `Ваша бронь желания «{wish}» обновлена.`
  - EN: `Your reservation for “{wish}” was updated.`
- Archive:
  - RU: `Желание «{wish}» перемещено в архив.`
  - EN: `“{wish}” was archived.`
- Receipt to eligible giver:
  - RU: `Для желания «{wish}» отмечено получение подарка.`
  - EN: `A gift was marked received for “{wish}”.`
- Collaboration:
  - RU: `Ваш доступ к списку «{list}» изменён.`
  - EN: `Your access to “{list}” has changed.`
- Reminder:
  - RU: `Приближается событие «{event}»: {date}.`
  - EN: `“{event}” is approaching: {date}.`

Receipt links, if used, lead only to the giver's authorized view; a user who is also the gift
recipient receives no receipt notice for their own wish. No recipient-facing template mentions a
reservation or purchase. A person who holds multiple roles is evaluated once for each wish, with
the recipient restriction taking precedence.

## Acceptance examples

- A valid shared list link opens the intended list without onboarding; a malformed or inaccessible
  link gives the same recovery message and reveals no list details.
- A user with one eligible list sees it selected; one with several must choose; one with none is
  offered creation or invitation. Cancel and failed Save leave no newly created wish.
- A failed product extraction preserves the link and allows a manual title before explicit Save.
  If access is revoked before Save, no wish is saved and the user can choose again or cancel.
- A recipient who is also a collaborator or giver receives no reservation or purchase notice,
  including indirect notifications through links, previews or event-specific timing.
- For a receipt with two eligible open givers, each receives at most one notice for that receipt;
  a disabled list preference suppresses the corresponding notice. Neither notice exposes counts
  or other givers. A delivery failure leaves the receipt and reservations unchanged.
- A list-specific disabled reminder overrides a globally enabled reminder for that list; without
  a list override, the global choice applies.

## Deferred decisions

WISHENKA-27 owns deep-link encoding, expiry, handoff, and invalid-link handling details.
WISHENKA-28 owns supported parsers, editable field details, draft lifetime and safe retry mechanics.
WISHENKA-29 owns event-to-recipient mapping details within the matrix, preference defaults and
category mapping, reminder lead times, delivery retries, deduplication and Telegram constraints.
Birthday data sources and notification behavior for users who have not started the bot remain
product or implementation decisions. No default or delivery guarantee is inferred here.
