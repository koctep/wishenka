# WISHENKA-26: Bot journeys and notification rules

## Goals

Specify coherent Telegram bot journeys and notification rules so people can enter the service,
add wishes with little friction, and receive useful updates without revealing a surprise to its
recipient. The outcome of this task is an agreed, reviewable scenario specification for the
subsequent bot and notification work.

## User Stories

- As a user, I can open the bot and reach list creation, my lists, help, and the Mini App.
- As a link recipient, I can open the specific shared wishlist without separate registration.
- As a contributor, I can send text or a product link to the bot and choose an eligible list when
  needed, review the wish, and explicitly save it.
- As a giver, I can receive relevant updates on wishes and reservations, subject to my settings.
- As a gift recipient, I can use the service without learning who reserved or purchased my gift.
- As a user, I can choose notification types globally and per wishlist; the list setting takes
  precedence when present.

## Definition of Done

- A scenario specification describes `/start` and all four menu destinations, normal and invalid
  shared-link entry, and the handoff to the intended wishlist in the Mini App.
- It describes text and link entry, zero, one, and multiple eligible target lists, the user's
  choice, preview or manual fallback, explicit save, confirmation, and cancellation or failure.
- A notification matrix identifies event, intended audience, exclusions, relevant preferences,
  and safe message content for significant wish and reservation changes, archival, gift receipt,
  collaborative changes, and event or birthday reminders.
- The matrix and example templates protect the recipient even when one person has multiple
  roles. They disclose no reservation, giver identity, purchase status, or indirect clue to the
  recipient. Suppression is required when a safe message cannot be constructed.
- Receipt notifications specify one notice per open reservation holder for each receipt, with no
  quantities, other givers, or suggestion of excess reservations; delivery failure does not
  undo the receipt. Preferences are respected.
- The specification identifies source-backed rules, explicit assumptions, and decisions deferred
  to later implementation tasks. It does not claim features are implemented.

## Task Description

### Scope and boundaries

This is a decomposition and design task. Its deliverable defines user-visible behavior and
acceptance examples for the subsequent menu/deep-link, incoming-wish, and notification tasks.
Implementation, support-channel design, profile settings screens, and delivery infrastructure
are outside this task. The product uses Python 3.12+; this task itself produces documentation.

### Functional requirements

1. `/start` offers Create wishlist, My wishlists, How it works, and Open Mini App. A shared
   wishlist link opens that particular list in the Mini App. A missing, invalid, or unavailable
   target has an understandable recovery path and must not expose private data.
2. A user may send or forward plain text or a product link. Plain text becomes a wish title. A
   supported link can supply product details for review; on missing or unsuccessful extraction,
   the link remains available and the user can supply the title manually. Saving is a separate
   explicit action.
3. Only lists in which the user may add wishes are eligible. One eligible list is selected
   automatically; with multiple eligible lists the user chooses. With none, the user is guided to
   create or obtain access to a list without silently saving a wish.
4. The user can cancel without creating a wish. Successful saving identifies the destination;
   invalid input, lost eligibility, and a failed save have understandable outcomes and do not imply
   success. The scenario specification must distinguish these outcomes.
5. Notifications and reminders cover meaningful wishlist and wish changes, reservation events,
   receipts, archives, collaborative changes, and tracked events or birthdays. A user controls
   types globally and per wishlist, with list-specific choices overriding global choices.
6. A person who is a recipient of a given wish must not receive information about its reservation,
   giver, or purchase, regardless of any other role that person holds. Apply that rule to message
   text and context, including links and previews; never use a generic message whose occurrence or
   destination reveals the hidden event.
7. Each giver holding an open reservation is eligible for one notice per receipt event, subject to
   notification settings. Its content omits quantities, other givers, and hints of excess
   reservations. Receipt remains recorded even when notification delivery fails.
8. The specification includes example messages in Russian and English, consistent with the
   selected product language, and explains which facts each audience may see.

### Non-functional requirements

- Privacy and surprise preservation take priority over completeness of a notification.
- Shared-link visits and booking require no additional registration or onboarding.
- Failed notifications must not reverse gift receipt; scenarios should give clear outcomes without
  exposing protected details.
- Journeys and examples must be understandable and testable from the user's perspective.

### Business entities

- **User:** Telegram participant with a language and notification preferences.
- **Wishlist:** a shareable collection with an owner, possible collaborators, and list preferences.
- **Wish:** a named desired gift, optionally with a product link and other details, and a recipient.
- **Recipient:** person for whom a wish is intended; their surprise must be protected.
- **Giver and reservation:** a person and their commitment to a wish, including purchase state.
- **Event and reminder:** a tracked occasion and a timely message about it.
- **Notification:** an event-related message addressed to an eligible user under their settings.

## Q&A

- **Why is this needed?** To make the bot, quick-add flow, and notifications consistent while
  preserving the core surprise invariant across subsequent implementation tasks.
- **Which rules are authoritative?** Product roles and privacy come from
  `specs/00-high.md`; menu, input, notification preferences, and receipt behavior come from
  `in-docs/spec.md`. The task description supplies the requested decomposition scope.
- **What is an eligible list?** A list in which the current user has permission to add a wish;
  viewing a shared list alone does not grant that permission.
- **Are exact reminder lead times and defaults specified?** No. The resulting specification must
  identify these as decisions for the implementation task rather than inventing product policy.
