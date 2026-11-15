# WISHENKA-24: Receipt Screen and «Подаренные» Section in the Mini App

Programming language for implementation: **Python 3.12+** (FastAPI UI routes, Jinja2
templates, HTMX 1.9.12 markup), **JavaScript** (classic script in `wishenka/web/static/`), CSS.
Recorded in `00-roadmap.md`.

Source of truth for behavior: the specification of the Done story WISHENKA-22 and the backend
contract of the Done story WISHENKA-23. This file does not copy them. It selects the frontend
subset that WISHENKA-24 must deliver and gives each item a stable ID (`U-n`) that maps back to
the WISHENKA-22 requirement and to the WISHENKA-23 contract element.

- `ai-tasks/WISHENKA-22/10-requirements.md`: FR-1 to FR-6, 19 corner cases (`CC-n` below),
  assumptions A to D, Q&A (`Q22-n` below).
- `ai-tasks/WISHENKA-22/20-architecture.md`: split of work, plan for WISHENKA-24, section 5
  (contract), Q6 (cabinet link), Q7.
- `ai-tasks/WISHENKA-22/60-tech-debt.md` (`TD-n.m` below, numbered as in the file): Group 1 items
  owned by this story 1.9, 1.10, 1.12, 1.14, 1.16, 1.17, and the Group 2 notes 2.4 and 2.5 that
  touch the receipt form.
- `ai-tasks/WISHENKA-22/50-observability.md`, the hand-off for WISHENKA-24 (route-level records
  of the receipt, no booking data in any view or client log); it becomes N-7.
- `ai-tasks/WISHENKA-23/10-requirements.md`, `20-architecture.md` section 6 and
  `60-tech-debt.md` (Group 1: 1.1, 1.2, 1.3; written `W23-TD-1.1` and so on below).
- `doc/dev/gift-receipt.md`: the implemented backend (real routes, DTOs, refusal reasons). Where
  it differs from the WISHENKA-22 draft, it wins (`C-n` below names the contract element).
- `in-docs/spec.md` sections 7.2 and 7.3, use case UC-07.

If this file and a WISHENKA-22 document disagree, WISHENKA-22 wins and this file is corrected.

## Goals

Why the story exists. An author receives gifts in real life. WISHENKA-23 made the backend able
to record that, to keep a dated history and to tell givers, but nothing in the Mini App calls it:
no screen records a receipt, no section shows the history, the giver cabinet does not render the
received marker, and the active list still shows a received wish at its full quantity. Without
this story the feature is invisible and the owner's list keeps listing gifts that already
arrived. The business value:

- The owner can record «я получил N штук» in a few taps and sees an honest list afterwards: what
  arrived leaves the active wishes (fully) or shrinks (partly), and what is still wanted stays.
- The owner keeps a warm, dated history of received gifts in «Подаренные», apart from wishes the
  owner deleted (archive), so a gift is never mistaken for a dropped wish.
- A giver whose promise is still open sees that the gift was received and can cancel, lower or
  keep the promise, without the product deciding for them.
- The surprise survives: nothing the owner or recipient sees reveals who promised, how many, or
  whether it was bought.

WISHENKA-23 delivered the backend only. This story delivers the screens on top of it and no
backend rule.

## Scope

### In scope (one vertical slice)

- The author's receipt screen: choose the quantity of received units, with explicit
  confirmation that the act is final (U-1 to U-4).
- The outcome of the act on the active list: reduced remaining quantity for a partly received
  wish, removal of a fully received wish (U-5, U-6, U-7).
- The closed set of refusals and the busy state, shown in Russian and without booking data
  (U-8, U-9).
- Archive section and archive/restore behavior for a partly received wish, and stale-list
  handling (U-10), and consistency of manual reordering with the active list (U-11, TD-1.14).
- The «Подаренные» section for authors, separate from the archive (U-12 to U-16).
- The giver side for a fully received wish: the «received» marker and actions in the cabinet,
  the cabinet link, no giver controls on the wish card (U-17 to U-19, TD-1.9, TD-1.16).
- Surprise rules in every new or changed view (U-20, U-21).
- Tests for the above (browser and route level) and the developer documentation update
  (Definition of Done 11 and 12).

### Out of scope

| Topic | Owner |
| ----- | ----- |
| Any backend rule, storage, migration, notice path, route or DTO change (the contract of WISHENKA-23 is fixed) | WISHENKA-23 (Done) |
| Notification settings screen and anything that writes settings | WISHENKA-34 |
| Metrics exporter (the UI adds no metrics beyond the existing log style) | WISHENKA-84 |
| Undo or correction of a receipt; the act is final (Q22-9) | WISHENKA-153 |
| Product decisions: assumptions A to D, public «already gifted» label, gifted history after list deletion, co-author who is the recipient, edit-form quantity lock, a «completed» state of a purchased promise | WISHENKA-154 |
| Moving the existing inline script of the base page and the six existing inline `onclick` attributes in three older partials (edit modal, archive modal, quick-add preview card) to static files (strict CSP) | WISHENKA-140 |
| A second CSRF path or a change of the CSRF mechanism | WISHENKA-123 |
| Server-side idempotency of repeated receipt taps (only a client-side double-tap guard is in scope, U-4) | WISHENKA-61 |
| Russian/English rendering of texts | WISHENKA-33 |
| Notice text and delivery (the bot only, no frontend API) | WISHENKA-23 |
| Editing, moving, promising, archiving or reopening from «Подаренные»; gifters seeing «Подаренные»; paging or filtering of the history | not planned (FR-5.6, Q22-6) |
| Shared purchase, money, thanking givers, secret gifts | excluded by the product |

Scope guard for the 3 SP estimate: every item in the «In scope» list is tied to a MUST
requirement below. Requirements marked SHOULD (U-11, the failure text of U-15, the second part
of U-19, the SHOULD part of N-4) are the first to move to a follow-up if the story outgrows its
size; they are not part of the Definition of Done. Any new item beyond the list needs the product owner and a new
ticket.

## Main Business Entities

Defined in WISHENKA-22 and WISHENKA-23 and used here without change: wish, received quantity,
remaining quantity, promise (open when intended or purchased), receipt record (wish, quantity,
date, no giver), gifted wish, archived wish, author (owner, administrator or member of the list,
see C-1).

Added by this story, in business terms:

- **Receipt screen**: the focused step where an author states how many units arrived. It shows
  the wish and the remaining quantity only.
- **«Подаренные» section**: the author's read-only history of received wishes, one entry per
  wish with its dated receipt acts.
- **«Received» marker**: the label on a giver's own promise in the cabinet saying that the owner
  received the wish fully.

## User Stories

- As an author, I want to mark a gift as received and choose how many units arrived, so that my
  list shows what I still want (U-1 to U-6).
- As an author of a wish for five units who got two, I want the card to show that three remain,
  so that I see the real state (U-5, U-7).
- As an author, I want a fully received wish to leave my active list, so that my list is not
  cluttered with things I already have (U-6).
- As an author, I want a readable reason when my receipt cannot be saved, so that I know whether
  to retry, refresh or stop (U-8, U-9).
- As an author, I want «Подаренные» to show what I received and when, separately from my
  archive, so that I never mix a gift with a dropped wish (U-12 to U-16).
- As a giver with an open promise on a received wish, I want my cabinet to show that it was
  received and keep my actions, so that I can decide what to do with my promise (U-17, U-18).
- As a giver, I want the wish card of a fully received wish to offer no booking controls and
  never to break (U-19).
- As a recipient or any other viewer, I want these screens to reveal nothing about promises,
  givers or purchases (U-20, U-21).

## Functional Requirements

Each ID shows the WISHENKA-22 and WISHENKA-23 items it implements in brackets. Priority is MUST
unless marked SHOULD. Contract elements are named `C-n` in the table at the end of this
section. Texts in «» are the fixed Russian wording; Step 2 may not change their meaning, and a
change of wording needs this file corrected first.

### Receipt screen (author)

- U-1. **Entry point and visibility.** The author sees a «Получено» action on the wish card of an
  active wish with remaining quantity above zero on an active list. It is not shown to givers,
  anonymous viewers, archived wishes, fully received wishes (they are not on the list), or when
  the list is archived. The control is shown by the same rule as the other author actions on
  the card. (FR-1.1, FR-1.2, C-1, CC-9)
- U-2. **Receipt screen content.** Activating the action opens a separate focused screen or modal
  (not an inline change of the card) with: a title «Отметить получение», the wish title, the
  remaining quantity («Осталось: N»), the quantity choice (U-3), the statement «Это действие
  нельзя отменить.» (assumption C, Q22-9), a primary button «Отметить полученным» and a
  secondary «Отмена». Cancelling or dismissing the screen changes nothing. The screen has no
  field or text about givers, promises, bookings, purchases or free quantity. (FR-1.3, FR-1.5,
  FR-6.1, FR-6.3, Q22-9)
- U-3. **Quantity choice.** The screen offers whole numbers from 1 to the remaining quantity and
  nothing else, with 1 preselected. The chosen quantity is visible in a confirmation line
  next to the button before the author submits («Будет отмечено получено: K шт. из N
  оставшихся»). A wish with remaining quantity 1 shows no choice and the line reads «Будет
  отмечено получено: 1 шт.». A wish with no stated quantity counts as one unit. The server stays
  the authority: the screen's limits are a convenience, not the rule. (FR-1.3, CC-1, CC-6, CC-7,
  CC-16, C-2)
- U-4. **Submit and double tap.** Submitting sends only the wish and the whole-number quantity,
  nothing about givers or bookings (C-2). While the attempt is in flight the submit button
  cannot be pressed again. After a refusal or a failure the screen stays open with the button
  available again and the reason shown (U-8). The attempt is made under the viewer's existing
  session and the same protection against forged requests as the other author actions; no new
  path is added (N-3). (FR-1.5, TD-2.4 client part, TD-2.5)

### Outcome on the active list (author)

- U-5. **Partial receipt result.** After a successful act that leaves units remaining, the screen
  closes, the wish stays on the active list and its card shows the remaining quantity and that
  part was received (U-7), and a short confirmation names only the wish and the quantity
  received now («Отмечено получено: K шт.»). The «Подаренные» section shows the wish (U-15)
  without a page reload. (FR-2.1, FR-2.2, FR-6.1, CC-1, CC-19, C-3)
- U-6. **Full receipt result.** After the act that brings received up to requested, the screen
  closes and the card leaves the active list at once, the same confirmation is shown, and the
  wish appears in «Подаренные» without a page reload. If the active list becomes empty, the
  existing empty-list text is shown. The first and last positions of the remaining cards (the
  disabled «up» on the first and «down» on the last) are correct afterwards. (FR-2.3, FR-5.3,
  C-3)
- U-7. **Owner card for a partly received wish.** The card of a wish with received quantity above
  zero shows «Осталось N из M» in its compact badges instead of the plain «×M», and its details
  show the requested, received and remaining quantity. A wish with nothing received looks as it
  does today. The card shows no booking, occupied or free-quantity data to the author or
  recipient (the existing giver block stays hidden for recipient views). (FR-2.2, FR-6.1,
  FR-6.3, C-4, CC-1)

### Refusals and busy state (author)

- U-8. **Closed set of refusals in Russian.** Every refusal of the receipt is shown on the
  receipt screen as one fixed Russian sentence chosen by the kind of refusal (the closed set of
  reasons of the inherited contract, C-5), never by the English message text and never from free
  text. The sentences, and the extra effect on the list, are:

  | Kind of refusal | Russian sentence | Effect on the list |
  | --------------- | ---------------- | ------------------ |
  | quantity is not a whole number of at least 1 | «Укажите целое число не меньше 1.» | none |
  | quantity above the remaining one | «Нельзя отметить больше, чем осталось. Осталось: N.» with N, the remaining quantity that comes with the refusal | the card is refreshed to the current remaining quantity (a lost race) |
  | nothing remains to receive | «Это желание уже полностью получено.» | the card leaves the list |
  | the wish is archived | «Желание в архиве. Восстановите его, чтобы отметить получение.» | none |
  | the list is not active | «Вишлист не активен, отметить получение нельзя.» | none |
  | the viewer has no right | «У вас нет права отмечать получение в этом вишлисте.» | none |
  | the wish is not found | «Желание не найдено. Обновите страницу.» | none |
  | not signed in, a server failure other than the busy outcome, a network error, or any response that is not one of the above | «Не удалось сохранить отметку. Повторите попытку.» | none |

  The busy outcome has its own sentence (U-9). None of the sentences contains the words «бронь»,
  «забронировано», «даритель» or «куплено», and none states or implies how many units are
  booked, occupied or free. The only quantity a refusal shows is the remaining one, in the
  sentence for «quantity above the remaining one» (the «nothing remains» refusal carries a
  remaining quantity of 0 and shows none), plus the fixed minimum 1 in the first sentence. The
  confirmation line of U-3 and the result text of U-5 are not refusals and show the quantity the
  author chose. The refusal is also announced to assistive technology (N-4). (FR-6.2, FR-2.5,
  FR-1.2, CC-6 to CC-9, C-5, W23-TD-1.3)
- U-9. **Busy (retryable).** The busy outcome (C-6) shows «Не удалось сохранить отметку сейчас.
  Повторите попытку.», keeps the screen open with the chosen quantity and the button available,
  and changes nothing on the list. The sentence is deliberately neutral and close to the generic
  failure sentence of U-8: it names nobody, does not mention a booking and must not contain
  «занято» or «занят», because for an owner or recipient such a word hints that something holds
  the wish, which the presence rules of WISHENKA-22 and WISHENKA-23 forbid (U-7, U-20). A
  repeated tap after it is a normal new attempt. (Architecture section 3 of WISHENKA-22, C-5,
  C-6)

### Archive, restore and reordering of the active list (author)

- U-10. **Archive section and stale cards.** The archive section keeps listing only archived
  wishes that are not fully received. For a wish with a received part it shows the unreceived
  quantity («Осталось N») next to the title, because only that part is archived. The archive
  confirmation of a wish with a received part says that only the unreceived part moves to the
  archive and the received part stays in «Подаренные». Restoring returns the card with its
  remaining quantity (U-7) and does not change «Подаренные». An archive or restore request that
  the server refuses because nothing remains to receive (C-7; a stale card of a wish that was
  fully received by another author) is not silent: the author sees «Это желание уже полностью
  получено.» and the list is refreshed. (FR-3.8, FR-5.2, CC-10, CC-11, C-7)
- U-11. **Manual order stays valid (SHOULD).** Move up, move down and drag-and-drop reorder only
  the cards of wishes that are active (not archived and with remaining quantity above zero), and
  keep working after a receipt removed a card. A reorder that the server refuses because the
  submitted set no longer equals the active set (a stale page) shows «Список изменился.
  Обновляем.» and refreshes the list instead of failing silently. (TD-1.14, AR-1 of
  WISHENKA-22, C-8)

### «Подаренные» section (author)

- U-12. **Availability and placement.** Members of the list (owner, administrator, member) see a
  separate «Подаренные» section on the list page, below the active wishes and apart from the
  archive section. It is not shown to givers, anonymous viewers or share-link viewers. It shows
  a count («Подаренные (N)», N = number of gifted wishes) and is not shown when there are no
  gifted wishes. It stays visible and readable when the list is archived (FR-5.7) even though
  the author actions are hidden then. (FR-5.1, FR-5.5, FR-5.7, C-9, UA-2, Jira description)
- U-13. **Entry content.** Each gifted wish is one entry with: the title, the price when set, the
  recipient name when set, «Получено: K из M» (received of requested), and the list of its
  receipt acts, each with the date (day, month, year, UTC calendar day, as the cabinet shows
  event days) and the quantity («2 шт.»). The order of entries and of acts is the order the
  backend returns (newest receipt first, acts oldest first). A back-filled act whose date is
  approximate (`is_approximate`) is marked as approximate («примерно», for example
  «≈ 15.11.2026 (дата примерная)») so that the author is not misled. An entry carries no giver
  name and no promise information. (FR-5.4, FR-6.1, FR-6.3, C-10, C-11, CC-19)
- U-14. **Read-only.** An entry has no edit, move, archive, restore, promise, receipt or delete
  action. The description and the store link of the wish may be shown but are not required.
  (FR-5.6)
- U-15. **Freshness and read failure (SHOULD for the failure text, MUST for freshness).** The
  section reflects the receipt acts made on the page without reloading it (U-5, U-6). If the
  section cannot be read (a failed or refused request), it shows «Не удалось загрузить
  «Подаренные». Обновите страницу.» in place of the entries and does not break the active
  list. (FR-5.1, C-9)
- U-16. **Separation from the archive.** The two sections are separate blocks with their own
  headings and counts. A wish with received units never appears as a whole in the archive
  section; a fully received wish appears only in «Подаренные»; a partly received wish may appear
  in the active list (remaining part), in «Подаренные» (received part) and, after archiving, in
  the archive (unreceived part), each time with the quantities of that part only. (FR-5.2,
  FR-5.3, CC-10, Jira description)

### Giver side for a received wish

- U-17. **Cabinet marker.** A cabinet row of the caller's open promise on a fully received wish
  (the cabinet already knows that the wish is fully received) shows the marker
  «Желание получено владельцем» (C-12). The
  marker stays until the giver cancels the promise. A purchased promise on a received wish has
  no «completed» state: it shows the marker, keeps its «Куплено» status and only the actions
  of U-18 (shortcut E in `60-tech-debt.md` of WISHENKA-22, TD-1.16, WISHENKA-154). The marker appears only for a
  fully received wish, not for a partly received one. It never states the received or requested
  quantity, never says that the promise is excess, and says nothing about other givers.
  (FR-3.6, FR-4.3 spirit, CC-4, TD-1.16)
- U-18. **Cabinet actions and link.** For such a row on an active list the cabinet offers the
  actions it already defines for an archived wish (lower, cancel, mark purchased or undo the
  purchase; no raising above the current quantity) and keeps the row in the active count.
  The «К желанию» link is not shown for a fully received wish, because the wish is not on the
  list any more (TD-1.9, Q6 of the WISHENKA-22 architecture, recommended). On an archived list
  the actions stay hidden as today. A giver whose promise is closed sees no row. (FR-3.2,
  FR-3.4, FR-3.6, CC-2, CC-3, CC-4, CC-13, C-12, Q7 of the WISHENKA-22 architecture)
- U-19. **Wish card of a fully received wish.** The wish card shows no giver controls for a fully
  received wish (no book, change, cancel, purchase, undo controls). The wish is not on the
  active list or the share page for non-members, so a card that is already on a giver's page
  when the wish becomes fully received must not stay actionable. MUST: after a giver action on
  such a card the refresh of the card never puts a raw error body into the page; the card is
  removed or replaced by the neutral «Желание больше недоступно. Обновите страницу.», which does
  not say why. The corrective behaviour is the requirement: today the card refresh of the base
  page puts the response text into the card whatever the outcome, which is the defect. Where
  the correction lives (for example in a static script, so that the existing inline script does
  not grow, N-2) is left to Step 2; moving that inline script is WISHENKA-140. SHOULD: the same
  neutral handling for a failed refresh in any other case.
  (FR-3.6, plan item 4 of WISHENKA-22, C-13)

### Surprise and privacy

- U-20. **No booking data in any new or changed view.** The receipt screen, the owner card, the
  confirmation, every refusal, the «Подаренные» section and the refreshed archive section carry
  no giver identity, promise, booked quantity, free quantity or purchase fact, in the visible
  text and in the markup (attributes, hidden elements). A recipient's page after a receipt has
  no new booking marker. A refusal never shows a quantity other than the remaining one
  and the fixed minimum 1 (U-8). The existing edit-form quantity lock stays unchanged and is not extended (Q22-12).
  (FR-6.1, FR-6.2, FR-6.3, invariants 1 and 4 of `specs/00-high.md`, CC-17)
- U-21. **Public views unchanged.** No view for a giver without a promise, an anonymous visitor
  or a share-link visitor shows that a wish was received (no «already gifted» label, no count
  of gifted wishes). A fully received wish is simply absent for them, as the backend
  projection already does. (assumption D, Q22-6, WISHENKA-154)

### Contract elements used by the requirements

The table below is the **inherited fixed backend contract of WISHENKA-23 (an input constraint),
not a design of this step**. It is listed only so that each requirement can name the contract
fact it relies on; how the Mini App reaches these facts is Step 2.

| ID | Contract element of WISHENKA-23 (`doc/dev/gift-receipt.md`) |
| -- | ----------------------------------------------------------- |
| C-1 | Receipt allowed for a member of the list (owner, administrator, member) on an active list; the card's author actions follow the same rule |
| C-2 | `POST /api/wishlists/{wishlist_id}/items/{item_id}/receipts`, body `{"quantity": <int>}` only, `extra="forbid"`; cookie session needs the CSRF header |
| C-3 | Success 201 `ReceiptResultDTO`: `item` (recipient-safe), `received_now`, `received_quantity`, `remaining_quantity`, `is_fully_received` |
| C-4 | `WishItemRecipientViewDTO.remaining_quantity`; `is_active` and `is_in_archive` predicates |
| C-5 | Refusal `detail` = `{"reason", "message"[, "remaining_quantity"]}`; closed reasons `quantity_invalid`, `quantity_above_remaining`, `wish_archived`, `wishlist_not_active`, `nothing_remaining`, `forbidden`, `not_found`; messages are English and not for display |
| C-6 | `busy`: 503, nothing changed, retryable |
| C-7 | Archive and restore routes answer 409 «Nothing remains to receive» (`NothingRemainingError`) for a fully received wish; archive section lists `is_in_archive` wishes with `remaining_quantity` |
| C-8 | Reorder accepts exactly the active set (`is_active`), else 400 |
| C-9 | `GET /api/wishlists/{wishlist_id}/gifted`: members of a non-deleted list only; 403 `forbidden`, 404 `not_found` or `wishlist_not_active`; available when the list is archived |
| C-10 | `GiftedItemDTO`: wish fields, `quantity`, `received_quantity`, `receipts`; no reservation or giver field |
| C-11 | `ReceiptEntryDTO`: `received_at`, `quantity`, `is_approximate` |
| C-12 | `MyReservationItemDTO.is_fully_received`; `CabinetRow.wish_received` and `offer_actions = (wish archived or wish received) and list not archived` |
| C-13 | Public and giver projection omit a wish that is not `is_active` for non-members, so the card route answers 404 for a fully received wish |

## Definition of Done

The task is done when all items below hold and each is shown by an automated test or, for items
12 and 15, by the diff of the change set. SHOULD requirements (U-11, the failure text of U-15,
the second part of U-19, the SHOULD part of N-4) are checked when built but are not part of this
list. Requirements verified only in review, not in this list: the session and request-protection
part of N-3 (the visible part, no control without identification, is in item 1), the touch
target size and the SHOULD part of N-4, the layout and visual language of N-8 (its texts are in
items 3 and 12).

1. An author can open the receipt screen from the card of an active wish, choose a quantity from
   1 to the remaining quantity, see the final-act statement, and submit; givers, anonymous
   viewers, viewers without identification and archived lists never get the control. (U-1, U-2,
   U-3, U-4, N-3 visible part)
2. A partial receipt leaves the wish on the list with «Осталось N из M», and a full receipt
   removes the card from the list at once, both without a page reload; the confirmation names
   only the wish and the received quantity. (U-5, U-6, U-7)
3. Every refusal of the closed set, not-signed-in or unknown failure, and the busy case shows its
   fixed Russian sentence by kind of refusal, keeps the screen usable, contains no booking
   wording, no «занято/занят» and no booked number, and a lost race shows the current remaining
   quantity. (U-8, U-9)
4. A second tap during an in-flight receipt does not send a second request. (U-4)
5. The «Подаренные» section is shown to list members only, including on an archived list, is
   absent for everyone else and when empty, and is separate from the archive section. (U-12,
   U-16, U-21)
6. Each gifted entry shows the title, price and recipient when set, «Получено: K из M» and the
   dated acts, marks approximate dates, and has no controls and no giver or promise data. (U-13,
   U-14)
7. The section updates after a receipt without reload. (U-15, freshness part)
8. A wish with received units never shows as a whole in the archive; a partly received archived
   wish shows only its unreceived quantity; restore returns the remaining quantity and leaves
   «Подаренные» unchanged; a refused archive or restore of a fully received wish is announced.
   (U-10, U-16)
9. The giver cabinet renders the «Желание получено владельцем» marker and the promise actions for
   a fully received wish on an active list, omits the link to the wish, shows no «completed»
   state for a purchased promise, and shows no marker for a partly received wish. (U-17, U-18)
10. The wish card offers no giver controls for a fully received wish, and a stale giver card
    never turns into a raw error body. (U-19)
11. No new or changed view reveals booking data to the owner, the recipient or the public, and
    the existing surprise tests still pass; new tests walk the receipt screen, the owner card,
    «Подаренные» and the refusals for recipient silence. (U-20, U-21, N-1, N-5)
12. The developer documentation (`doc/dev/gift-receipt.md`, `doc/dev/miniapp.md`,
    `doc/dev/reservations.md` cabinet text, `doc/dev/items.md` where it describes the card and
    the archive section) describes the new screens as current behavior, removes the «no UI yet»
    statements, and records the Russian texts and the stale-card behavior. Closes the «planned»
    notes of TD-1.12. (all U, N-8 texts, TD-1.12)
13. No new inline handler, inline script or behavior-carrying inline style is added by the
    change, and the existing static-script rule test (the wish card partial is free of inline
    handlers) still passes. (N-2)
14. The receipt control and the receipt screen are operable by keyboard, every control and the
    quantity choice are labelled, and refusal and busy sentences are announced to assistive
    technology. (N-4 MUST part)
15. The change set touches only the Mini App page layer: no change of domain rules, storage,
    migrations, the notice path or the JSON interfaces of WISHENKA-23, and their existing tests
    stay green. (N-6)
16. Every receipt attempt made through the Mini App is logged once per outcome (accepted,
    refused by kind, busy), and the records carry no giver or booking data and no quantity
    beyond what the WISHENKA-22 observability table allows. (N-7)

## Non-functional Requirements and Constraints

- N-1. **Surprise and privacy** are tested, not assumed: new browser and route tests assert the
  absence of the words listed in U-8 and U-9 (including «занято/занят») and of booking fields in
  the HTML of the new views for the owner, a recipient and a public viewer; the existing
  surprise tests and the existing test of giver controls on the wish card stay green.
- N-2. **Strict-CSP readiness.** The change adds no new inline behavior: no inline script, no
  inline event handler and no behavior-carrying inline style. The existing violations (the inline
  script of the base page and six inline `onclick` attributes in three older partials) are
  WISHENKA-140; they are not extended and not fixed here. The existing check that the wish card
  partial is free of inline handlers keeps passing. No new third-party script is added.
- N-3. **Identification and request protection.** The receipt screen and the «Подаренные» read
  work under the viewer's existing session and the existing protection against forged requests,
  exactly as the other author actions (WISHENKA-123 owns any change). A viewer without
  identification gets no receipt control.
- N-4. **Accessibility basics, as the project does them plus the quantity choice.** MUST: every
  control is operable by keyboard; every control, including the quantity choice, has a label;
  refusal and busy sentences are announced to assistive technology; icon-only controls keep a
  label; the screen can be dismissed by a visible button; touch targets are at least as large as
  the existing 44 px targets (verified in review, not in the Definition of Done). SHOULD
  (verified in review, not in the Definition of Done): dismissal by the Escape key, and dialog
  semantics with focus handling (the older modals have none).
- N-5. **Tests.** Python 3.12+ with `pytest`, in `tests/`, with module-level timeouts and bounded
  waits (`doc/dev/testing.md`). Behavior of the real script and markup is tested in headless
  Chromium; server-rendered views are tested at route level. Testing approach note: the
  offline browser stubs do not process every markup-driven behavior, so such flows are covered at
  markup level or the stub is extended in test code only, never in production code.
- N-6. **Layer boundary.** Production changes are limited to the Mini App page layer (pages,
  templates, styles, scripts and the page routes that serve them). No change of domain rules,
  storage, migrations, the notice path or the JSON interfaces of WISHENKA-23. Basis:
  `ai-tasks/WISHENKA-23/20-architecture.md` section 6 states that the HTMX layer calls the same
  service methods and needs no JSON route; how the page layer does it is Step 2. If a missing
  contract element is found, it is recorded as a defect against WISHENKA-23, not worked around
  here.
- N-7. **Observability.** Every receipt attempt made through the Mini App is logged once per
  outcome: accepted, refused (by the closed kind of refusal) and busy. The records carry no giver
  or booking data and no quantity beyond what the WISHENKA-22 observability table allows; a
  refusal is recorded by kind and wish only. The Mini App adds no client-side logging of wish or
  booking data, and no metrics (WISHENKA-84). The backend's own records for the JSON route do not
  cover a receipt made through the Mini App, so the page layer must produce the equivalent
  records; the mechanism is Step 2. (WISHENKA-22 observability hand-off for WISHENKA-24)
- N-8. **Language and look.** All user-visible texts are Russian and are fixed in the requirements
  above (U-1, U-2, U-3, U-5, U-7, U-8, U-9, U-10, U-11, U-12, U-13, U-15, U-17, U-19). Layout is
  mobile-first for the Telegram Mini App, in the width of the existing page and the existing
  visual language (cards, badges, bottom-sheet modal as in the archive confirmation); verified in
  review, not in the Definition of Done.

## Task Description

Today the product has a working backend for gift receipt and no way to use it. The owner's page
shows the quantity of a wish as requested, the archive section lists only title and price, the
cabinet computes `wish_received` and `offer_actions` for a received wish but renders neither a
marker nor a link rule, and the card of a received wish is simply gone from the giver's list
projection. The business rule stays as WISHENKA-22 fixed it: receipt and promise are independent
facts, the owner records only what arrived, the giver decides about their own promise, and no
view of the owner or recipient reveals bookings.

This story makes that rule usable in the Mini App with the smallest complete slice: the receipt
screen, its result on the list, the closed set of refusals, the «Подаренные» section kept apart
from the archive, and the giver's cabinet marker.

Constraints:

- The surprise principle and the privacy rules stay in force (`specs/00-high.md`, invariants 1 and
  4); the receipt screen is the owner's view and uses recipient-safe data only.
- Limit on booked units and the over-booked state are backend facts; the UI neither computes nor
  shows them to the owner or recipient.
- The receipt is final: there is no undo and no «reopen» (assumption C).
- No change of the backend contract; where the UI needs something the contract lacks, it is a
  defect of WISHENKA-23, not a UI workaround.
- The new screens look and behave like the existing wish page, archive section and giver
  cabinet (visual language and flows); how the existing building blocks are reused is Step 2.

### Assumptions of this story

These are taken for now, are consistent with assumptions A to D of WISHENKA-22 and are listed so
nobody reads them as product decisions. Product decisions stay with WISHENKA-154.

- UA-1. The receipt action lives on the wish card next to the other author actions and opens a
  focused modal over the list; a separate page is not needed (the specification says
  «отдельный экран», which is satisfied by the focused modal).
- UA-2. «Подаренные» is hidden when no wish has a received part, like the archive section, so a
  new list is not cluttered. If the product wants it always visible, that is a one-line change.
- UA-3. The default quantity is 1: the act is final, a smaller act can always be followed by
  another, and a larger one cannot be reduced.
- UA-4. Dates are shown as the UTC calendar day (`dd.mm.yyyy`), the same convention the cabinet
  uses for event days.
- UA-5. A co-author who is also the recipient of a wish may record receipt (assumption B,
  Q22-11); the screen shows recipient-safe data only, so no leak arises.
- UA-6. A neutral «Желание больше недоступно» is used for a stale giver card because the reason
  (archived, received, deleted) must not be disclosed to a giver without a promise.

## Q&A

- Q1. The ticket is a technical request («модальное окно, вкладка»). Why do we need it?
  A. Because the owner cannot otherwise tell the product what arrived: WISHENKA-23 built the
  rules but nothing calls them. The business goal is an honest list for the owner, a warm
  separate history, and givers who are told and keep control of their promise. See Goals.
- Q2. Is «вкладка» a tab or a section?
  A. A section on the list page (U-12). The Jira text allows either; a separate block below the
  active wishes needs no new navigation and matches the archive section pattern. The
  specification speaks of a «раздел».
- Q3. Who sees the receipt action and «Подаренные»?
  A. Members of the list: owner, administrator, member (C-1, C-9). WISHENKA-22 FR-1.1 says
  «author» and the specification 7.2 names the same set; the backend uses membership. No
  contradiction. Givers and anonymous viewers see neither (assumption D).
- Q4. May the screen warn the owner about bookings, for example «there are open promises»?
  A. No (FR-6.1 to FR-6.3). The owner learns nothing about promises from the receipt screen.
- Q5. Where does the giver of a fully received wish go from the cabinet?
  A. Nowhere: the link is omitted (U-18), as the WISHENKA-22 architecture (Q6) recommends. The
  wish is not on the list for non-members, and a link would lead to the list top.
- Q6. Why a neutral text for a stale giver card instead of «получено»?
  A. A giver without a promise must not learn that a wish was received (U-21, WISHENKA-154). The
  neutral text covers received, archived and deleted alike.
- Q7. Does the story reconsider the final nature of the act?
  A. No. Undo is WISHENKA-153. The screen says that the act cannot be undone (U-2).
- Q8. How is a lost race between two authors shown?
  A. As the refusals «quantity above the remaining one» or «nothing remains to receive» (U-8); the
  card is refreshed and the first one shows the current remaining quantity. The backend already guarantees that received never passes
  requested.
- Q9. Reordering belongs to this story?
  A. Partly. WISHENKA-22 item 1.14 gives the predicate to WISHENKA-23 (done) and «the reorder
  UI» to this story, while the plan list of WISHENKA-22 for this story does not name it. Only the
  consistency of the existing move and drag controls with the active predicate is in scope
  (U-11, SHOULD).

### Notes on the source documents

- The WISHENKA-22 plan speaks of a receipt command with indicative names. The delivered backend
  offers the receipt and the gifted history as machine-oriented interfaces (C-2, C-9), while the
  wish page works with HTML pieces, and nothing of the receipt or «Подаренные» exists for the page
  yet. Providing the page-facing part is part of this story (N-6, page layer only; WISHENKA-23
  architecture section 6 says no JSON route is needed) and is a Step 2 design question.
- The WISHENKA-22 draft of the receipt DTOs differs from the delivered ones in minor ways
  (`is_approximate` on receipt entries was added by WISHENKA-23 and has no FR in WISHENKA-22);
  U-13 covers it.
- The route messages of the receipt are English and fixed; the UI shows its own Russian text per kind of refusal
  (U-8; W23-TD-1.3), so a later text change by WISHENKA-155 does not matter.
- `doc/dev/gift-receipt.md` says a wish id of another list is `not_found`; the UI treats it like
  any `not_found`.
- Three older partials still use six inline `onclick` attributes; the new modal must not copy
  that (N-2).

Sources used: the documents listed at the top, the current templates `wishlist_detail.html`,
`partials/item_card.html`, `partials/archived_items_section.html`,
`partials/item_archive_modal.html`, `partials/reservations_list.html`, `base.html`, the routes
`items_ui.py`, `reservations_ui.py`, `sharing.py`, `receipts.py`, the script `wishlist.js` and
the tests `test_wishlist_static_script.py`, `test_wish_card_giver_controls.py`,
`test_reservations_cabinet_ui.py`, `test_wishlist_cards_browser.py`.

## Traceability

| Source item (WISHENKA-22 unless marked `W23-`) | Requirement |
| ---------------------------------------------- | ----------- |
| FR-1.1, FR-1.2 | U-1, U-8 |
| FR-1.3 | U-2, U-3 |
| FR-1.4 | U-3 (no giver needed, nothing about givers on the screen) |
| FR-1.5 | U-2, U-4 |
| FR-2.1, FR-2.2 | U-5, U-7 |
| FR-2.3 | U-6 |
| FR-2.5 | U-8, U-9 |
| FR-3.2, FR-3.4 | U-18 |
| FR-3.6 | U-17, U-18, U-19 |
| FR-3.8 | U-10, U-16 |
| FR-4 | out of scope (bot only) |
| FR-5.1, FR-5.5, FR-5.7 | U-12, U-15 |
| FR-5.2, FR-5.3 | U-10, U-16 |
| FR-5.4 | U-13 |
| FR-5.6 | U-14 |
| FR-6.1, FR-6.2, FR-6.3 | U-2, U-7, U-8, U-13, U-20 |
| CC-1 | U-3, U-5, U-7 |
| CC-2, CC-3 | U-18 |
| CC-4 | U-17, U-18 |
| CC-6, CC-7, CC-8, CC-9 | U-8 |
| CC-10, CC-11 | U-10, U-16 |
| CC-13 | U-18 |
| CC-16 | U-3 |
| CC-17 | U-20 |
| CC-19 | U-5, U-13 |
| CC-5, CC-12, CC-14, CC-15, CC-18 | backend or notice behavior, nothing for the UI (CC-12 is the existing edit form, unchanged) |
| TD-1.9 | U-18 |
| TD-1.10 (all red tests, owners 23 and 24) | N-5, DoD 11; this story's red tests are made at its own Step 3 |
| TD-1.12 («planned» notes in `doc/dev`) | DoD 12 |
| TD-1.14 | U-11 |
| TD-1.16 | U-17 |
| TD-1.17 | satisfied: the contract is final in WISHENKA-23 (C-1 to C-13) |
| TD-2.4 client part, TD-2.5 | U-4, N-3 |
| Observability hand-off for WISHENKA-24 (`50-observability.md` of WISHENKA-22: route-level records, no booking data in template, script or client log) | N-7, U-20, DoD 16, DoD 11 |
| W23-TD-1.1 (contract usable by 24; routes and DTO fixed) | C-1 to C-13 (input constraint), N-6 |
| W23-TD-1.2 (receipt screen, browser tests, cabinet marker, «completed» decision, cabinet link, reorder UI) | U-1 to U-19 (screen, marker, link, reorder), N-5; «completed» state to WISHENKA-154 (U-17) |
| W23-TD-1.3 (map by refusal reason, not by message text) | U-8, Notes |

| Definition of Done item | Requirement |
| ----------------------- | ----------- |
| 1 | U-1, U-2, U-3, U-4 |
| 2 | U-5, U-6, U-7 |
| 3 | U-8, U-9 |
| 4 | U-4 |
| 5 | U-12, U-16, U-21 |
| 6 | U-13, U-14 |
| 7 | U-15 |
| 8 | U-10, U-16 |
| 9 | U-17, U-18 |
| 10 | U-19 |
| 11 | U-20, U-21, N-1, N-5 |
| 12 | all U, N-8 texts, TD-1.12 |
| 13 | N-2 |
| 14 | N-4 (MUST part) |
| 15 | N-6 |
| 16 | N-7 |

Requirements outside the Definition of Done, by design: U-11 (SHOULD), the failure text of U-15,
the second part of U-19, the SHOULD part of N-4, the touch target size of N-4, the request
protection part of N-3, the layout of N-8 (all verified in review). Every other U and N appears
in at least one row above.
