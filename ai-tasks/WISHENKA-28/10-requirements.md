# WISHENKA-28: Add wishes through the Telegram bot

## Goals

Let a person capture a gift idea as soon as they encounter it by sending or forwarding text or a
product link to the bot. They can review and save the wish in an authorized wishlist without
opening the Mini App, reducing friction while preserving control over the destination and data.
The implementation language is Python 3.12+.

## User Stories

- As a wishlist owner or authorized collaborator, I can send or forward text to propose a wish.
- As a user, I can send a product link and review available product information before saving.
- As a user with several eligible lists, I can choose the intended list and see the destination.
- As a user, I can correct a draft, cancel it, or retry a failed save without unwanted duplicates.
- As a gift recipient, I do not learn hidden reservation or purchase information from this flow.

## Definition of Done

1. In a private bot conversation, a user can send or forward usable text or a product link and
   begin a wish draft without opening the Mini App. Plain text supplies the proposed title; a link
   remains attached to the draft. Sending or forwarding alone does not create a wish.
2. A recognizable product link triggers available product information extraction. Available
   title, photo, price, and other supported information is presented for review. Unsupported,
   unavailable, unsafe, failed, or partially successful extraction preserves the submitted link,
   makes missing information clear, and allows the user to supply or correct the title and other
   supported fields manually. The system does not represent guessed details as confirmed facts.
3. Only active lists where the current user is allowed to add wishes are offered as destinations.
   Viewing a shared list alone is not permission to add. With one eligible list, select it
   automatically and show its name; with several, let the user choose with inline buttons; with
   none, explain that the user needs an eligible list and offer creation or an invitation without
   saving a wish.
4. The draft shows its destination, title, link when present, and available extracted details.
   The user can edit the title and the remaining supported wish fields, including extracted values,
   before saving. A valid title is required; other fields follow existing wish validation rules.
5. Save is an explicit action. Only a valid draft and a currently eligible, available destination
   can be saved. A successful save creates one wish in the selected list and identifies that list
   to the user. The resulting wish is available through the existing wishlist experience.
6. Cancel discards the draft and confirms cancellation without creating or changing a wish. Empty,
   unsupported, or invalid input gives understandable guidance and does not create a wish.
7. If permission or list availability changes before saving, do not save to that list; explain the
   destination is unavailable and allow a new eligible choice or cancellation. Validation and
   temporary save failures retain the usable draft and offer correction or retry and cancellation.
   A retry or repeated action must not create duplicate wishes or falsely report success.
8. A stale, expired, or superseded choice or save action cannot create a wish or expose another
   person's draft. The user receives understandable guidance and can start a fresh draft. The
   draft's lifetime and replacement behavior are specified and consistently enforced.
9. The journey's prompts, choices, validation, success, failure, and cancellation messages support
   Russian and English using the user's available product language with a usable fallback. Messages
   do not disclose another person's list content, reservation status, buyer, or purchase details.
10. Existing bot entry, help and navigation remain usable. The flow does not grant list membership,
    modify existing wishes, or expose private content merely because a link or message was sent.

## Task Description

### Functional scope

A user submits text or a product link in a private conversation, reviews the resulting draft,
selects an eligible wishlist when necessary, and explicitly saves or cancels. A forwarded message
is treated as the submitted content, not as proof of a sender's identity or list permissions.
A preview may use available extraction, but a wish can still be added manually when extraction is
unsupported or unsuccessful. The user can inspect and correct all supported fields before saving.

### Non-functional requirements

- Authorization is checked against the acting user and the selected list, including at save time.
- Link processing must not expose private resources or cause unsafe access on the user's behalf;
  invalid or unsafe links produce a safe, understandable outcome without silent network access.
- Drafts and actions must remain private to their owner and not leak sensitive submitted content or
  product-link secrets to other users. User-visible failures must not reveal private list details.
- Repeated submissions, interruptions, and temporary failures have predictable outcomes; a single
  confirmed save must not be duplicated by retrying the same action.
- The product's surprise rule remains in force regardless of the user's other roles in the list.
- The interaction stays usable within Telegram and gives clear feedback when action is required.

### Constraints and assumptions

- Existing product roles and permissions determine eligible lists and valid wish fields; the task
  adds no new membership or authorization model. Lists that are deleted or otherwise unavailable
  are not eligible.
- Product metadata extraction uses supported capabilities already available to the service. The
  set of supported stores and completeness of third-party data are not guaranteed; successful
  manual entry does not depend on an external site being reachable.
- The service supports Russian and English; language preference management is separate work.
- A wish has a required title and may include description, photograph, product link, price,
  currency, quantity, priority, category, and comment according to existing product rules.
- Draft lifetime and the interaction when a second message arrives are design decisions. The
  selected policy must communicate the effect to the user and prevent accidental saves or loss
  presented as a successful save.
- Notifications, support conversations, and creation or editing of wishlist permissions are
  outside this task. Existing bot navigation and wish creation rules must remain compatible.

### Business entities

- **User:** a Telegram person acting on their own behalf in a private bot conversation.
- **Wishlist:** an available personal or shared list with an owner and defined contributor rights.
- **Wish:** a titled gift idea in one wishlist, with optional product and descriptive fields.
- **Draft:** the user's unsaved proposed wish and selected destination, subject to expiry or
  cancellation; it is not itself a saved wish.
- **Product link and preview:** a submitted reference and any available, editable product details;
  preview information can be absent or incomplete.
- **Gift recipient:** a person for whom a wish is intended, whose surprise must remain protected.

### Scenarios

1. A user with one eligible list sends text, reviews the proposed title and named list, and saves;
   one wish appears in that list and the bot confirms its destination.
2. A user with several eligible lists forwards a product link, selects a list, corrects extracted
   details, and explicitly saves. A shared list they may only view is not offered.
3. A product page cannot be parsed. The user retains its link, enters a title manually, reviews
   the draft, and saves without leaving Telegram.
4. A user has no eligible lists. The bot explains how to obtain one and creates no wish.
5. A user's access is revoked after list selection. Save is rejected without leaking list details;
   the user can choose another eligible list or cancel.
6. A save response is interrupted. The user retries the same action and receives an accurate result
   without creating a second wish. A stale action after cancellation or expiry cannot save.

## Q&A

- **Why is this needed?** To capture ideas quickly from Telegram without requiring the user to open
  the Mini App, while keeping an explicit review and save step.
- **Which lists are eligible?** Only lists where the acting user can currently add wishes. A public
  viewing link is not sufficient; eligibility is rechecked when saving.
- **Is parsing required to succeed?** No. The product link is retained, and the user can supply a
  valid title and other details manually when extraction is unavailable or incomplete.
- **What defines the journey?** `specs/00-high.md`, `in-docs/spec.md`, and the agreed bot journey
  in `in-docs/bot-scenarios.md`. Existing wish validation and access rules continue to apply.
