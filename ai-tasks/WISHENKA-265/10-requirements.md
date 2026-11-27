# WISHENKA-265: A stale giver card becomes a neutral card

## Goals

A giver can still be looking at a wish card after that wish has left the
list, for example because the owner recorded that the gift was fully
received. The card on the giver's page must stop looking like a wish they
can still reserve. In its place the giver sees one neutral unavailable
card: the wish is no longer available, and they should refresh the page.
The card does not say why, does not name an error, and does not show a raw
failure.

That outcome is already the product rule for a giver card that is refreshed
into something other than the same wish card. It is not what the giver sees
today. At base `e433223`,
`tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral`
waits 5 seconds for the neutral replacement and the sentence is still
absent (last value false). The giver is left without the neutral card.

A wish that is still available keeps today's refresh: the card updates, and
a card the giver had opened stays open. This task does not add a screen and
does not change who may reserve, what a receipt means, or what a recipient
is allowed to learn.

Implementation language: JavaScript for the Mini App giver-card refresh,
and Python for the existing browser check.

## User Stories

- As a **giver** looking at a shared wishlist, when a wish I still see has
  become unavailable, the next refresh of that card replaces it with the
  neutral unavailable card. I do not see an error body, and I do not keep
  an actionable wish card for that wish.
- As a **giver** refreshing a wish that is still available, I still see the
  updated wish card, and a card I had opened stays open.
- As a **wishlist owner** who recorded that a gift was fully received, I
  do not need a new receipt screen. The giver who still has the old card
  simply stops seeing it as an available wish.
- As a **recipient**, I still never learn who reserved or bought a wish, or
  that a reservation exists, from this card.
- As a **maintainer**, I can trust `test_stale_giver_card_is_neutral` to
  describe the visible outcome: the stale card becomes the neutral
  unavailable card, and a still-available wish still refreshes.

## Definition of Done

1. **Stale giver card.** A giver card for a wish that is no longer
   available (the owner has fully received it while the card is still on
   the giver's page) is replaced, on the next refresh of that card, by one
   neutral unavailable card. The original wish card is gone. The neutral
   card shows the existing sentence and nothing else. Russian: "Желание
   больше недоступно. Обновите страницу." English: "This wish is no
   longer available. Please refresh the page." The page does not show a
   raw failure, including "Item not found" or a JSON error body. Other
   wishes on the page are not replaced by that message.
2. **Still-available wish.** Refreshing a giver card for a wish that is
   still available replaces that card with the current wish card. If the
   giver had the card open, it stays open. That wish does not become the
   neutral unavailable card.
3. **Standing check.** `test_stale_giver_card_is_neutral` passes because
   the neutral sentence is on the page and the still-available wish still
   refreshes as in item 2. The wait is not lengthened to hide a missing
   sentence.
4. **Surprise and roles.** The neutral card names no giver, reservation,
   purchase, quantity, or reason the wish left. Who may reserve, and who
   may record a receipt, is unchanged.
5. **Languages.** The Russian and English sentences already used for an
   unavailable wish remain the sentences the giver sees.

## Task Description

### Problem

A giver sees wish cards on a shared list and can reserve from a card while
the wish is still available. When the owner records that the wish was fully
received, that wish leaves the giver's list. A card that was already open
must not stay as a wish the giver can still act on.

The agreed outcome is a neutral unavailable card in that place. The
sentence asks the giver to refresh the page and does not explain the
receipt, the reservation, or an error. The standing check opens the share
page as a giver, fully receives one wish, refreshes that giver card, and
waits for this replacement. It also refreshes a second wish that is still
available and expects that card to update and stay open.

At base `e433223` the first wait ends after 5 seconds with the neutral
sentence still absent. The stale giver card has not become the neutral
card. The check fails before it can confirm the still-available wish.

### Scope

- The visible result of refreshing a giver card after the wish is no longer
  available: one neutral unavailable card, and no raw failure in its place.
- The visible result of refreshing a giver card for a wish that is still
  available: an updated wish card that stays open if it was open.
- The meaning of `test_stale_giver_card_is_neutral`: it guards both of
  those results.

### Constraints

- Do not change who may reserve a wish or who may record a receipt.
- Do not change what a full or partial receipt means for the owner's list.
- Do not change the existing Russian and English wording of the unavailable
  sentence.
- Keep surprise secrecy: the neutral card names no giver, reservation,
  purchase, quantity, or cause.
- A still-available wish keeps its current refresh, including an open card
  staying open.

### Non-goals

- A new sentence, a new screen, or a new reason code for the giver.
- A change to receipt confirmation, a stale list order, or an archive of a
  wish that is not on the list.
- Any other check in the receipt browser module.

### Main entities

- **Wishlist** — the shared list the giver is looking at.
- **Wish** — one entry. For the giver it is either still available or no
  longer available (for this task, because it was fully received).
- **Giver** — a person viewing the list by share link, with reservation
  controls on a wish that is still available.
- **Giver card** — the wish card on that page, including its open or closed
  detail. While the wish is available, a refresh updates this card and
  keeps it open if it was open.
- **Neutral unavailable card** — the plain status that replaces a giver
  card when the refresh is no longer that same wish. It carries the
  existing "no longer available, please refresh the page" sentence, offers
  no reservation action, and does not say why the wish left.
- **Wishlist owner** — the person who can record that a gift was received.
  A full receipt is what makes the giver's wish unavailable in this task.
- **Recipient** — must not learn giver identity, a reservation, or a
  purchase from the neutral card.

## Q&A

- **Q:** Why does the check time out?
  **A:** It waits until the stale giver card has become the neutral
  unavailable card. At `e433223` that sentence never appears, so the wait
  ends after 5 seconds with the condition still false. Lengthening the
  wait would not show the giver the neutral card.

- **Q:** What should the giver see instead of the old card?
  **A:** One neutral unavailable card in that place, with the existing
  sentence for their language. The original wish card is gone. The page
  does not show "Item not found" or a JSON error body.

- **Q:** Should a wish that is still available become that neutral card
  too?
  **A:** No. Its refresh still shows the current wish card, and a card the
  giver had opened stays open.

- **Q:** Does the neutral card explain that the gift was received?
  **A:** No. It only says the wish is no longer available and asks the
  giver to refresh the page. It names no giver, reservation, purchase,
  quantity, or cause.

- **Q:** Does this task change receipt, reserve, or surprise rules?
  **A:** No. Who may reserve, what recording a receipt does, and what a
  recipient is allowed to learn all stay as they are. Only the stale giver
  card's refresh must end as the neutral unavailable card.
